#!/usr/bin/env python3
"""Engine de matching cliente x FIDC.

Para cada cliente, calcula um score 0-100 contra cada fundo elegível, retorna
o top-N e exporta planilha Excel com abas por perfil.

Funções:
    score_perfil:     alinhamento de perfil clientexfundo (matriz em perfil_rules)
    score_risco:      penaliza distância entre apetite do cliente e risco do fundo
    score_retorno_fit: balanceia retorno vs. volatilidade conforme experiência
    score_historico:  bonifica fundos com histórico mais longo
    score_segmento:   bonifica alinhamento entre segmento do cliente e segmento do fundo
    calcular_match:   combina os 5 scores + bônus de segmento num único valor

Filtros hard (Fase 3 — substituição da heurística ``matches.engine``):
    - CVM 555: exclui fundos restritos a investidor qualificado quando o cliente
      não qualifica. Aplicado apenas se a coluna ``restricao_cvm_555`` existir
      no rating (defaul: ``False`` se ausente — não bloqueia ninguém).
    - Status ANBIMA: só fundos ativos (coluna opcional ``status_anbima``).
    - Mínimo de elegibilidade: ``match_score >= MIN_ELEGIBILIDADE`` (50).

Output novo (anexado a cada match):
    - ``MATCH_BREAKDOWN``: dict serializado com os componentes do score
    - ``ELEGIBILIDADE``: dict serializado com booleans dos filtros aplicados
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

# Permite importar libs internas mesmo executando como script direto.
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.lib.perfil_rules import score_perfil  # noqa: E402

DATA = ROOT / "data_real"
CLIENTES_PATH = os.environ.get("RADAR_CLIENTES", str(DATA / "clientes.csv"))
RATING_PATH = os.environ.get("RADAR_RATING", str(DATA / "rating_fidc.xlsx"))
OUTPUT_PATH = os.environ.get("RADAR_MATCHES", str(DATA / "matches.xlsx"))


# ─── Constantes do scoring ──────────────────────────────────────────────
# Mantidas no topo para uma calibragem futura ficar visível.
PESO_PERFIL = 0.40
PESO_RISCO = 0.30
PESO_RETORNO = 0.20
PESO_HISTORICO = 0.10

MIN_MESES_HISTORICO = 6
MIN_MATCH_SCORE = 20  # abaixo disso, descarta (antes do bônus de segmento)
MIN_ELEGIBILIDADE = 50  # match_score final mínimo para entrar no top-N
HISTORICO_FULL_SCORE = 24  # 24 meses → score 100
TOP_N_DEFAULT = 5

# Penalidades risco
PENALIDADE_RISCO_ACIMA = 1.2  # fundo mais arriscado que apetite do cliente
PENALIDADE_RISCO_ABAIXO = 0.5  # fundo mais conservador que apetite (penaliza menos)

# Score retorno por experiência
EXPERIENCIA_INICIANTE = 1
EXPERIENCIA_INTERMEDIARIA = 2

# Bônus por segmento (Fase 3 — substituição da heurística matches.engine).
# Aplicado SOMA direta sobre o match_score final, com cap em 100.
BONUS_SEGMENTO_PRIMARIO = 30  # cliente.segmento == fundo.segmento_predominante
BONUS_SEGMENTO_SECUNDARIO = 15  # cliente.segmento ∈ fundo.segmentos_secundarios

# Campos opcionais no rating/clientes — Fase 3 prepara a engine para consumi-los
# assim que o pipeline Databricks adicionar essas colunas ao Gold.
# Enquanto ausentes, defaults seguros (False / None) mantêm comportamento
# regressivo (ninguém é bloqueado por CVM 555 sem evidência).
COL_RESTRICAO_CVM555 = "restricao_cvm_555"
COL_STATUS_ANBIMA = "status_anbima"
COL_SEGMENTO_PREDOM = "segmento_predominante"
COL_SEGMENTOS_SECUND = "segmentos_secundarios"
COL_CLIENTE_QUALIFICADO = "e_qualificado"
COL_CLIENTE_SEGMENTO = "segmento"
STATUS_ANBIMA_ATIVO = "ativo"


# ─── Score helpers ──────────────────────────────────────────────────────


def score_risco(apetite_cliente: float, risco_fundo: float) -> float:
    diff = risco_fundo - apetite_cliente
    penalidade = diff * PENALIDADE_RISCO_ACIMA if diff > 0 else abs(diff) * PENALIDADE_RISCO_ABAIXO
    return max(0.0, 100.0 - penalidade)


def score_retorno_fit(experiencia: int, retorno_anual: float, volatilidade: float) -> float:
    if pd.isna(retorno_anual) or pd.isna(volatilidade):
        return 50.0
    sharpe_proxy = retorno_anual / (volatilidade + 1.0)
    if experiencia == EXPERIENCIA_INICIANTE:  # prioriza estabilidade
        base = max(0.0, 100.0 - volatilidade * 2.0)
    elif experiencia == EXPERIENCIA_INTERMEDIARIA:  # equilibrio
        base = min(100.0, sharpe_proxy * 10.0 + 40.0)
    else:  # avançado — prioriza retorno
        base = min(100.0, retorno_anual * 1.5)
    return round(base, 1)


def score_historico(meses: int) -> float:
    if pd.isna(meses) or meses < MIN_MESES_HISTORICO:
        return 0.0
    return min(100.0, (meses / HISTORICO_FULL_SCORE) * 100.0)


def _parse_segmentos_secundarios(raw: Any) -> list[str]:
    """Aceita lista, JSON string, CSV string. Retorna lista limpa em maiúsculas."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, list):
        return [str(s).strip().upper() for s in raw if str(s).strip()]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        # JSON list?
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip().upper() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                pass
        # CSV fallback
        return [p.strip().upper() for p in s.split(",") if p.strip()]
    return []


def score_segmento(cliente_segmento: str | None, fundo: pd.Series) -> tuple[float, str]:
    """Calcula o bônus de segmento e devolve (bonus, motivo).

    - +BONUS_SEGMENTO_PRIMARIO se cliente.segmento == fundo.segmento_predominante
    - +BONUS_SEGMENTO_SECUNDARIO se cliente.segmento ∈ fundo.segmentos_secundarios
    - 0 caso contrário (inclusive quando segmento_predominante é ausente no Gold)
    """
    if not cliente_segmento:
        return 0.0, "sem_segmento_cliente"
    cliente_seg = str(cliente_segmento).strip().upper()
    if not cliente_seg:
        return 0.0, "sem_segmento_cliente"

    pred = fundo.get(COL_SEGMENTO_PREDOM)
    pred_presente = pred is not None and not (isinstance(pred, float) and pd.isna(pred))
    if pred_presente and str(pred).strip().upper() == cliente_seg:
        return float(BONUS_SEGMENTO_PRIMARIO), "primario"

    secundarios = _parse_segmentos_secundarios(fundo.get(COL_SEGMENTOS_SECUND))
    if cliente_seg in secundarios:
        return float(BONUS_SEGMENTO_SECUNDARIO), "secundario"

    return 0.0, "nao_alinhado"


def _bool_safe(val: Any, default: bool) -> bool:
    """Casteia val→bool com fallback. Aceita 'true'/'false'/'1'/'0' como string."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    if isinstance(val, (bool,)):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        v = val.strip().lower()
        if v in {"true", "1", "sim", "yes", "y"}:
            return True
        if v in {"false", "0", "nao", "não", "no", "n"}:
            return False
    return default


@dataclass
class Elegibilidade:
    """Resultado dos filtros hard aplicados ANTES do scoring final."""

    cvm_555: bool = True  # passou no filtro CVM 555 (ou filtro não aplicável)
    fundo_ativo: bool = True  # status ANBIMA ativo (ou coluna ausente)
    segmento_alinhado: bool = False  # bate com predominante/secundário do fundo

    def passou_filtros_hard(self) -> bool:
        return self.cvm_555 and self.fundo_ativo


@dataclass
class MatchScores:
    match_score: float
    s_perfil: float
    s_risco: float
    s_retorno: float
    s_historico: float
    s_segmento: float = 0.0
    segmento_motivo: str = "sem_segmento_cliente"
    elegibilidade: Elegibilidade = field(default_factory=Elegibilidade)

    def breakdown(self) -> dict[str, Any]:
        return {
            "perfil": self.s_perfil,
            "risco": self.s_risco,
            "retorno": self.s_retorno,
            "historico": self.s_historico,
            "segmento_bonus": self.s_segmento,
            "segmento_motivo": self.segmento_motivo,
            "pesos": {
                "perfil": PESO_PERFIL,
                "risco": PESO_RISCO,
                "retorno": PESO_RETORNO,
                "historico": PESO_HISTORICO,
            },
        }


def aplicar_filtros_hard(
    cliente: pd.Series,
    fundo: pd.Series,
    cliente_qualificado: bool,
) -> Elegibilidade:
    """Aplica filtros CVM 555 + status ANBIMA. Tolerante a colunas ausentes."""
    elg = Elegibilidade()

    if COL_RESTRICAO_CVM555 in fundo.index:
        restrito = _bool_safe(fundo.get(COL_RESTRICAO_CVM555), default=False)
        if restrito and not cliente_qualificado:
            elg.cvm_555 = False
    # else: coluna ausente → assume não-restrito (default seguro, regressivo).

    if COL_STATUS_ANBIMA in fundo.index:
        status = fundo.get(COL_STATUS_ANBIMA)
        if status is not None and not (isinstance(status, float) and pd.isna(status)):
            elg.fundo_ativo = str(status).strip().lower() == STATUS_ANBIMA_ATIVO
    # else: coluna ausente → assume ativo (default seguro).

    return elg


def calcular_match(cliente: pd.Series, fundo: pd.Series) -> MatchScores | None:
    """Retorna None se o fundo não tiver SCORE_RISCO confiável OU se reprovou nos filtros hard."""
    raw_score = fundo.get("SCORE_RISCO")
    if pd.isna(raw_score):
        return None

    cliente_qualificado = _bool_safe(cliente.get(COL_CLIENTE_QUALIFICADO), default=False)
    elg = aplicar_filtros_hard(cliente, fundo, cliente_qualificado)
    if not elg.passou_filtros_hard():
        return None

    s_perfil = score_perfil(cliente["perfil"], str(fundo.get("PERFIL_SUGERIDO", "")))
    s_risco = score_risco(float(cliente["score_perfil"]), float(raw_score))
    s_retorno = score_retorno_fit(
        int(cliente.get("experiencia", 2)),
        float(fundo.get("RETORNO_ANUAL", 0) or 0),
        float(fundo.get("VOLATILIDADE", 10) or 10),
    )
    s_hist = score_historico(int(fundo.get("MESES_HISTORICO", 0) or 0))

    s_seg, motivo_seg = score_segmento(cliente.get(COL_CLIENTE_SEGMENTO), fundo)
    elg.segmento_alinhado = motivo_seg in {"primario", "secundario"}

    base = s_perfil * PESO_PERFIL + s_risco * PESO_RISCO + s_retorno * PESO_RETORNO + s_hist * PESO_HISTORICO
    # Cap em 100: bônus de segmento NUNCA empurra o score acima do teto.
    match = min(100.0, base + s_seg)

    return MatchScores(
        match_score=round(match, 1),
        s_perfil=round(s_perfil, 1),
        s_risco=round(s_risco, 1),
        s_retorno=round(s_retorno, 1),
        s_historico=round(s_hist, 1),
        s_segmento=round(s_seg, 1),
        segmento_motivo=motivo_seg,
        elegibilidade=elg,
    )


def gerar_motivo(cliente: pd.Series, fundo: pd.Series, scores: MatchScores) -> str:
    partes: list[str] = []
    tipo = str(fundo.get("TIPO_COTA", "")).capitalize()
    risco = str(fundo.get("RISCO", "")).lower()
    ret = fundo.get("RETORNO_ANUAL")
    inad = fundo.get("TAXA_INADIMPLENCIA")  # já em % (vem da Gold)
    perf = str(fundo.get("PERFIL_SUGERIDO", ""))

    if scores.s_perfil >= 90:
        partes.append(f"perfil {perf.lower()} alinhado ao cliente")
    elif scores.s_perfil >= 60:
        partes.append("perfil compatível com o cliente")
    else:
        partes.append("perfil adjacente — maior cautela recomendada")

    if pd.notna(ret):
        partes.append(f"retorno anual de {float(ret):.1f}%")
    if pd.notna(inad):
        nivel = (
            "inadimplência baixa" if inad < 5 else "inadimplência moderada" if inad < 15 else "inadimplência elevada"
        )
        partes.append(nivel)
    partes.append(f"cota {tipo.lower()} com risco {risco}")
    return " | ".join(partes)


# ─── IO ────────────────────────────────────────────────────────────────


def carregar_dados() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not os.path.exists(CLIENTES_PATH):
        raise FileNotFoundError(f"Base de clientes não encontrada: {CLIENTES_PATH}")
    if not os.path.exists(RATING_PATH):
        raise FileNotFoundError(f"Rating não encontrado: {RATING_PATH}")

    clientes = pd.read_csv(CLIENTES_PATH, encoding="utf-8-sig")
    fundos = pd.read_excel(RATING_PATH, sheet_name="GERAL")
    fundos = fundos[fundos["MESES_HISTORICO"] >= MIN_MESES_HISTORICO].copy()

    print(f"  Clientes carregados: {len(clientes)}")
    print(f"  Fundos elegíveis:    {len(fundos)}")
    return clientes, fundos


# ─── Engine ────────────────────────────────────────────────────────────


def rodar_match(
    clientes: pd.DataFrame,
    fundos: pd.DataFrame,
    top_n: int = TOP_N_DEFAULT,
) -> pd.DataFrame:
    print(f"\n  Calculando matches ({len(clientes)} clientes x {len(fundos)} fundos)...")

    # Detecta colunas opcionais presentes no rating (logado para auditoria).
    opcionais_presentes = sorted(
        c
        for c in (COL_RESTRICAO_CVM555, COL_STATUS_ANBIMA, COL_SEGMENTO_PREDOM, COL_SEGMENTOS_SECUND)
        if c in fundos.columns
    )
    if opcionais_presentes:
        print(f"  Colunas opcionais presentes no rating: {opcionais_presentes}")
    else:
        print(
            "  AVISO: nenhuma coluna opcional (CVM 555 / segmento / status_anbima) presente. "
            "Filtros hard ficam permissivos; bônus de segmento = 0. "
            "Ver docs/limitacoes_atuais.md para schema Gold pendente."
        )

    descartados_elg = 0
    descartados_min = 0
    registros: list[dict] = []
    for _, cliente in clientes.iterrows():
        scores_cliente: list[dict] = []
        for _, fundo in fundos.iterrows():
            sc = calcular_match(cliente, fundo)
            if sc is None:
                descartados_elg += 1
                continue
            # Threshold mínimo de elegibilidade: bloqueia entradas fracas no top-N.
            # MIN_MATCH_SCORE é o piso histórico (mantido para regressão de comportamento);
            # MIN_ELEGIBILIDADE é o piso novo da Fase 3 (>=50, empty-state amigável).
            if sc.match_score < MIN_MATCH_SCORE:
                descartados_min += 1
                continue
            if sc.match_score < MIN_ELEGIBILIDADE:
                descartados_min += 1
                continue
            motivo = gerar_motivo(cliente, fundo, sc)
            scores_cliente.append(
                {
                    "CPF": cliente.get("cpf", ""),
                    "CLIENTE": cliente.get("nome", ""),
                    "PERFIL_CLIENTE": cliente.get("perfil", ""),
                    "SCORE_CLIENTE": cliente.get("score_perfil", ""),
                    "FUNDO": fundo.get("FUNDO", ""),
                    "TIPO_COTA": fundo.get("TIPO_COTA", ""),
                    "RISCO_FUNDO": fundo.get("RISCO", ""),
                    "SCORE_RISCO_FUNDO": fundo.get("SCORE_RISCO", ""),
                    "PERFIL_FUNDO": fundo.get("PERFIL_SUGERIDO", ""),
                    "RETORNO_ANUAL": fundo.get("RETORNO_ANUAL", ""),
                    "VOLATILIDADE": fundo.get("VOLATILIDADE", ""),
                    "TAXA_INAD": fundo.get("TAXA_INADIMPLENCIA", ""),
                    "MESES_HISTORICO": fundo.get("MESES_HISTORICO", ""),
                    "MATCH_SCORE": sc.match_score,
                    "S_PERFIL": sc.s_perfil,
                    "S_RISCO": sc.s_risco,
                    "S_RETORNO": sc.s_retorno,
                    "S_HISTORICO": sc.s_historico,
                    "S_SEGMENTO": sc.s_segmento,
                    "SEGMENTO_MOTIVO": sc.segmento_motivo,
                    "MOTIVO": motivo,
                    # Serializa breakdown/elegibilidade como JSON para Excel não perder dict.
                    "MATCH_BREAKDOWN": json.dumps(sc.breakdown(), ensure_ascii=False),
                    "ELEGIBILIDADE": json.dumps(asdict(sc.elegibilidade), ensure_ascii=False),
                }
            )

        top = sorted(scores_cliente, key=lambda x: x["MATCH_SCORE"], reverse=True)[:top_n]
        for rank, item in enumerate(top, 1):
            item["RANK"] = rank
        registros.extend(top)

    df = pd.DataFrame(registros)
    print(
        f"  {len(df)} matches gerados | "
        f"descartados por elegibilidade hard: {descartados_elg} | "
        f"descartados por score<{MIN_ELEGIBILIDADE}: {descartados_min}"
    )
    if df.empty:
        print("  AVISO: zero matches. Empty-state será exibido no frontend.")
    return df


def gerar_resumo(df_matches: pd.DataFrame) -> pd.DataFrame:
    if df_matches.empty:
        return pd.DataFrame()
    resumos = []
    grupos = df_matches.groupby(["CPF", "CLIENTE", "PERFIL_CLIENTE"])
    for (cpf, nome, perfil), grupo in grupos:
        top3 = grupo.nlargest(3, "MATCH_SCORE")
        linha: dict = {
            "CPF": cpf,
            "CLIENTE": nome,
            "PERFIL": perfil,
            "MATCH_MEDIO": round(top3["MATCH_SCORE"].mean(), 1),
        }
        for i, (_, r) in enumerate(top3.iterrows(), 1):
            linha[f"TOP{i}_FUNDO"] = r["FUNDO"]
            linha[f"TOP{i}_COTA"] = r["TIPO_COTA"]
            linha[f"TOP{i}_MATCH"] = r["MATCH_SCORE"]
            linha[f"TOP{i}_RETORNO"] = r["RETORNO_ANUAL"]
            linha[f"TOP{i}_MOTIVO"] = r["MOTIVO"]
        resumos.append(linha)
    return pd.DataFrame(resumos).sort_values("MATCH_MEDIO", ascending=False)


def exportar(df_matches: pd.DataFrame, df_resumo: pd.DataFrame, output_path: str) -> None:
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_matches.to_excel(writer, sheet_name="TODOS_OS_MATCHES", index=False)
        df_resumo.to_excel(writer, sheet_name="RESUMO_CLIENTES", index=False)
        for perfil in ("CONSERVADOR", "MODERADO", "ARROJADO"):
            sub = df_matches[df_matches["PERFIL_CLIENTE"] == perfil]
            if not sub.empty:
                sub.sort_values(["CLIENTE", "RANK"]).to_excel(writer, sheet_name=perfil, index=False)
        # Ranking geral — quantos clientes têm cada fundo como TOP1.
        ranking = (
            df_matches[df_matches["RANK"] == 1]
            .groupby(["FUNDO", "TIPO_COTA", "RISCO_FUNDO", "RETORNO_ANUAL"])
            .agg(
                VEZES_RECOMENDADO=("MATCH_SCORE", "count"),
                MATCH_MEDIO=("MATCH_SCORE", "mean"),
            )
            .reset_index()
            .sort_values("VEZES_RECOMENDADO", ascending=False)
        )
        ranking["MATCH_MEDIO"] = ranking["MATCH_MEDIO"].round(1)
        ranking.to_excel(writer, sheet_name="RANKING_FUNDOS", index=False)
    print(f"\nSalvo: {output_path}")


def main() -> int:
    print("=" * 60)
    print("  MATCH CLIENTE x FIDC")
    print("=" * 60)
    print(f"  Início: {datetime.now().strftime('%H:%M:%S')}\n")

    clientes, fundos = carregar_dados()
    df_matches = rodar_match(clientes, fundos)
    df_resumo = gerar_resumo(df_matches)
    exportar(df_matches, df_resumo, OUTPUT_PATH)

    # Preview
    print("\n  TOP MATCHES POR PERFIL:\n")
    for perfil in ("CONSERVADOR", "MODERADO", "ARROJADO"):
        sub = df_matches[df_matches["PERFIL_CLIENTE"] == perfil].nlargest(3, "MATCH_SCORE")
        if sub.empty:
            continue
        print(f"  --- {perfil} ---")
        for _, r in sub.iterrows():
            print(
                f"  {r['CLIENTE']:<20} → {r['FUNDO'][:45]:<45} | match {r['MATCH_SCORE']:.0f} | retorno {r['RETORNO_ANUAL']:.1f}%"
            )
        print()

    print(f"  Fim: {datetime.now().strftime('%H:%M:%S')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
