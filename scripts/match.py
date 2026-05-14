#!/usr/bin/env python3
"""Engine de matching cliente x FIDC.

Para cada cliente, calcula um score 0-100 contra cada fundo elegível, retorna
o top-N e exporta planilha Excel com abas por perfil.

Funções:
    score_perfil:     alinhamento de perfil clientexfundo (matriz em perfil_rules)
    score_risco:      penaliza distância entre apetite do cliente e risco do fundo
    score_retorno_fit: balanceia retorno vs. volatilidade conforme experiência
    score_historico:  bonifica fundos com histórico mais longo
    calcular_match:   combina os 4 scores num único valor 0-100
"""

from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass
from datetime import datetime

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
MIN_MATCH_SCORE = 20  # abaixo disso, descarta
HISTORICO_FULL_SCORE = 24  # 24 meses → score 100
TOP_N_DEFAULT = 5

# Penalidades risco
PENALIDADE_RISCO_ACIMA = 1.2  # fundo mais arriscado que apetite do cliente
PENALIDADE_RISCO_ABAIXO = 0.5  # fundo mais conservador que apetite (penaliza menos)

# Score retorno por experiência
EXPERIENCIA_INICIANTE = 1
EXPERIENCIA_INTERMEDIARIA = 2


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


@dataclass
class MatchScores:
    match_score: float
    s_perfil: float
    s_risco: float
    s_retorno: float
    s_historico: float


def calcular_match(cliente: pd.Series, fundo: pd.Series) -> MatchScores | None:
    """Retorna None se o fundo não tiver SCORE_RISCO confiável."""
    raw_score = fundo.get("SCORE_RISCO")
    if pd.isna(raw_score):
        return None

    s_perfil = score_perfil(cliente["perfil"], str(fundo.get("PERFIL_SUGERIDO", "")))
    s_risco = score_risco(float(cliente["score_perfil"]), float(raw_score))
    s_retorno = score_retorno_fit(
        int(cliente.get("experiencia", 2)),
        float(fundo.get("RETORNO_ANUAL", 0) or 0),
        float(fundo.get("VOLATILIDADE", 10) or 10),
    )
    s_hist = score_historico(int(fundo.get("MESES_HISTORICO", 0) or 0))

    match = s_perfil * PESO_PERFIL + s_risco * PESO_RISCO + s_retorno * PESO_RETORNO + s_hist * PESO_HISTORICO
    return MatchScores(
        match_score=round(match, 1),
        s_perfil=round(s_perfil, 1),
        s_risco=round(s_risco, 1),
        s_retorno=round(s_retorno, 1),
        s_historico=round(s_hist, 1),
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

    registros: list[dict] = []
    for _, cliente in clientes.iterrows():
        scores_cliente: list[dict] = []
        for _, fundo in fundos.iterrows():
            sc = calcular_match(cliente, fundo)
            if sc is None or sc.match_score < MIN_MATCH_SCORE:
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
                    "MOTIVO": motivo,
                }
            )

        top = sorted(scores_cliente, key=lambda x: x["MATCH_SCORE"], reverse=True)[:top_n]
        for rank, item in enumerate(top, 1):
            item["RANK"] = rank
        registros.extend(top)

    df = pd.DataFrame(registros)
    print(f"  {len(df)} matches gerados")
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
