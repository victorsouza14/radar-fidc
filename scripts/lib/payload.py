"""Builders por seção do payload — uma função pura por seção (SRP).

Cada builder recebe seus DataFrames e devolve o dict pronto para serializar.
Sem efeitos colaterais.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from .cnae_setor import setor_from_cnae
from .formatters import (
    cnpj_fmt,
    mask_cpf,
    mask_email,
    mask_name,
    to_float,
    to_int,
    to_str,
)
from .scenario import classify_selic

# ─── limites de saída (evita payload gigante) ─────────────────────────
MAX_FIDC_DETALHE = 1500
MAX_CREDIT = 500

# Filtra fundos com pouco histórico (não confiáveis para ranking).
MIN_MESES_HISTORICO = 6

# Piso de retorno anual (%) para a página de FIDCs (tabela + indicadores).
# Filtro mais frouxo que o do match engine (que usa SELIC 14,75%) — aqui
# o objetivo é mostrar todas as classes com retorno minimamente atrativo,
# eliminando perdas (negativos), zeros e taxas próximas de inflação que
# poluem o painel. Quem entra em recomendação ainda passa o piso SELIC
# no ``match.py`` upstream.
FIDCS_MIN_RETORNO_ANUAL = 8.0

# Piso mínimo de boletos para uma empresa entrar na lista exibida.
# O ``credit_model.py`` canônico não filtra por boletos — gera score para
# todas as empresas. Mas empresas com 1-2 boletos geram score artificialmente
# alto (1 boleto pago = score ~99). Esse piso descarta apenas o ruído mais
# grosseiro mantendo amostra grande (~2.5k empresas elegíveis no dataset FIAP).
CREDIT_MIN_BOLETOS = 5


# ─── MACRO ───────────────────────────────────────────────────────────
# A regra de cenário vive em scripts/lib/scenario.py (fonte única).


def build_macro(
    df: pd.DataFrame,
    focus_indicators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # UTC explícito: o runner do CI roda em UTC, mas a função pode ser chamada
    # localmente em qualquer fuso. Mantemos um único contrato temporal.
    fallback_date = datetime.now(UTC).strftime("%Y-%m-%d")
    if df.empty:
        return {
            "selic": None,
            "cdi": None,
            "ipca": None,
            "selic_proj": None,
            "ipca_proj": None,
            "cenario": "indisponivel",
            "data_ref": fallback_date,
        }
    last = df.iloc[-1]

    # SELIC: preferimos SGS 1178 (taxa efetiva anualizada base 252) — é o valor
    # que o mercado usa em "TAXA SELIC a.a." e que o BCB publica oficialmente.
    # Fallback para SGS 432 (meta Copom) só se a efetiva não estiver disponível.
    selic = to_float(last.get("selic_efetiva"), None, 2)
    if selic is None:
        selic = to_float(last.get("selic_meta"), None, 2)

    # CDI: o BCB devolve a taxa DIÁRIA (~0.055% a.d.). Anualizamos pelos ~252 dias úteis.
    # Guard: valores patológicos (<= -100% a.d.) gerariam NaN/Infinity. Mantém None.
    cdi_diario_pct = to_float(last.get("cdi_diario"), None, 6)
    if cdi_diario_pct is not None and cdi_diario_pct > -100.0:
        cdi = round(((1.0 + cdi_diario_pct / 100.0) ** 252 - 1.0) * 100.0, 2)
    else:
        cdi = None

    # IPCA 12m: preferimos SGS 13522 (IPCA acumulado em 12 meses, série oficial BCB).
    # Fallback para composição interna da série mensal se a oficial não estiver presente.
    ipca_12m = to_float(last.get("ipca_12m_acumulado"), None, 2)
    if ipca_12m is None and "ipca_mensal" in df.columns:
        ipca_serie = pd.to_numeric(df["ipca_mensal"], errors="coerce").dropna().tail(12)
        if not ipca_serie.empty:
            acumulado = 1.0
            for m in ipca_serie:
                acumulado *= 1.0 + float(m) / 100.0
            ipca_12m = round((acumulado - 1.0) * 100.0, 2)

    cenario = classify_selic(selic).chave
    ref = last.get("data_processamento")
    data_ref = ref.strftime("%Y-%m-%d") if pd.notna(ref) else fallback_date

    # Projeções: prioridade para Boletim Focus (BCB) via indicadores.parquet.
    # Fallback para heurística simples se Focus indisponível ou stale.
    if focus_indicators and focus_indicators.get("is_proj_heuristica") is False:
        selic_proj = to_float(focus_indicators.get("selic_projetada_12m"), None, 2)
        ipca_proj = to_float(focus_indicators.get("ipca_projetado_12m"), None, 2)
    else:
        selic_proj = round(selic - 0.5, 2) if selic is not None else None
        ipca_proj = (
            round(ipca_12m * 0.9, 2)
            if ipca_12m is not None and ipca_12m > 0
            else (round(ipca_12m, 2) if ipca_12m is not None else None)
        )

    return {
        "selic": selic,
        "cdi": cdi,
        "ipca": ipca_12m,
        "selic_proj": selic_proj,
        "ipca_proj": ipca_proj,
        "cenario": cenario,
        "data_ref": data_ref,
    }


# ─── FIDCs ───────────────────────────────────────────────────────────
def _fidc_detalhe_row(r: pd.Series) -> dict[str, Any]:
    return {
        "cnpj": cnpj_fmt(r.get("CNPJ")),
        "fundo": to_str(r.get("FUNDO")),
        "tipo_cota": to_str(r.get("TIPO_COTA"), "UNICA"),
        "risco": to_str(r.get("RISCO"), "SEM DADOS"),
        "score_risco": to_float(r.get("SCORE_RISCO"), 0.0, 1),
        "perfil_sugerido": to_str(r.get("PERFIL_SUGERIDO"), "SEM DADOS"),
        "retorno_anual": to_float(r.get("RETORNO_ANUAL"), 0.0, 2),
        "volatilidade": to_float(r.get("VOLATILIDADE"), 0.0, 2),
        "retorno_aj_risco": to_float(r.get("RETORNO_AJ_RISCO"), 0.0, 2),
        "taxa_inad": to_float(r.get("TAXA_INADIMPLENCIA"), 0.0, 2),
        "meses_historico": to_int(r.get("MESES_HISTORICO")),
    }


def _iqr_filter(series: pd.Series) -> pd.Series:
    """Aplica filtro Tukey 1.5x IQR. Amostras < 4 são pequenas demais — devolve cru."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 4:
        return s
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    return s[(s >= q1 - 1.5 * iqr) & (s <= q3 + 1.5 * iqr)]


def _fidc_indicadores(elegiveis: pd.DataFrame) -> dict[str, Any]:
    """Estatísticas resumidas da carteira da página — fonte única, server-side.

    Universo já chega filtrado pelo ``build_fidcs`` (histórico >= 6 meses
    e retorno >= ``FIDCS_MIN_RETORNO_ANUAL``). Aqui só formata.

    - retorno_max/min: extremos brutos (sem IQR — não mascarar o melhor/pior).
    - inad_media: aplica Tukey 1.5x IQR (``TAXA_INADIMPLENCIA`` tem outliers
      ~23k no Gold; IQR estabiliza a média).
    """
    if elegiveis.empty:
        return {"retorno_max": None, "retorno_min": None, "inad_media": None}

    def _round_or_none(v: float | None, ndigits: int) -> float | None:
        return round(float(v), ndigits) if v is not None and not pd.isna(v) else None

    retornos = pd.to_numeric(elegiveis["RETORNO_ANUAL"], errors="coerce").dropna()
    inad = _iqr_filter(elegiveis["TAXA_INADIMPLENCIA"])

    return {
        "retorno_max": _round_or_none(retornos.max() if len(retornos) else None, 2),
        "retorno_min": _round_or_none(retornos.min() if len(retornos) else None, 2),
        "inad_media": _round_or_none(inad.mean() if len(inad) else None, 2),
    }


def build_fidcs(geral: pd.DataFrame) -> dict[str, Any]:
    if geral.empty:
        return {
            "stats": {
                "total_classes": 0,
                "total_fundos": 0,
                "distribuicao": {"por_risco": {}, "por_perfil": {}, "por_cota": {}},
                "indicadores": {"retorno_max": None, "retorno_min": None, "inad_media": None},
            },
            "detalhe": [],
        }

    # Universo da página = histórico mínimo + retorno minimamente atrativo
    # (>= FIDCS_MIN_RETORNO_ANUAL, 8% a.a.). Mais frouxo que o piso do
    # match engine (14,75%) — aqui o objetivo é mostrar todas as classes
    # que não são perdas/quase-zero, sem se prender ao filtro de
    # recomendação. Universo bruto (geral) continua alimentando
    # stats.distribuicao/total_classes (auditoria).
    retornos = pd.to_numeric(geral["RETORNO_ANUAL"], errors="coerce")
    elegiveis = geral[
        (geral["MESES_HISTORICO"].fillna(0) >= MIN_MESES_HISTORICO) & (retornos >= FIDCS_MIN_RETORNO_ANUAL)
    ]
    deduped = elegiveis.drop_duplicates(subset=["CNPJ", "FUNDO", "TIPO_COTA"]).sort_values(
        "SCORE_RISCO", ascending=True
    )

    return {
        "stats": {
            "total_classes": len(geral),
            "total_fundos": int(geral["CNPJ"].nunique()),
            "distribuicao": {
                "por_risco": geral["RISCO"].fillna("SEM DADOS").value_counts().to_dict(),
                "por_perfil": geral["PERFIL_SUGERIDO"].fillna("SEM DADOS").value_counts().to_dict(),
                "por_cota": geral["TIPO_COTA"].fillna("UNICA").value_counts().to_dict(),
            },
            "indicadores": _fidc_indicadores(elegiveis),
        },
        "detalhe": [_fidc_detalhe_row(r) for _, r in deduped.head(MAX_FIDC_DETALHE).iterrows()],
    }


# ─── CLIENTES ────────────────────────────────────────────────────────
# Todos os campos PII são mascarados antes de virem para data.json (LGPD).
def _cliente_row(r: pd.Series) -> dict[str, Any]:
    return {
        "cpf": mask_cpf(r.get("cpf")),
        "nome": mask_name(r.get("nome")),
        "email": mask_email(r.get("email")),
        "idade": to_int(r.get("idade")),
        "perfil": to_str(r.get("perfil"), "MODERADO"),
        "score_perfil": to_float(r.get("score_perfil"), 0.0, 1),
    }


def build_clientes(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"total": 0, "distribuicao_perfil": {}, "lista": []}
    perfil_series = df["perfil"].fillna("SEM DADOS") if "perfil" in df else pd.Series(dtype=str)
    return {
        "total": len(df),
        "distribuicao_perfil": perfil_series.value_counts().to_dict(),
        "lista": [_cliente_row(r) for _, r in df.iterrows()],
    }


# ─── MATCHES ─────────────────────────────────────────────────────────
def _match_row(r: pd.Series) -> dict[str, Any]:
    return {
        "cpf": mask_cpf(r.get("CPF")),
        "cliente": mask_name(r.get("CLIENTE")),
        "perfil_cliente": to_str(r.get("PERFIL_CLIENTE"), "MODERADO"),
        "fundo": to_str(r.get("FUNDO")),
        "tipo_cota": to_str(r.get("TIPO_COTA"), "UNICA"),
        "risco_fundo": to_str(r.get("RISCO_FUNDO"), "SEM DADOS"),
        "retorno_anual": to_float(r.get("RETORNO_ANUAL"), 0.0, 2),
        "volatilidade": to_float(r.get("VOLATILIDADE"), 0.0, 2),
        "taxa_inad": to_float(r.get("TAXA_INAD"), 0.0, 2),
        "meses_historico": to_int(r.get("MESES_HISTORICO")),
        "match_score": to_float(r.get("MATCH_SCORE"), 0.0, 1),
        "motivo": to_str(r.get("MOTIVO")),
        "rank": to_int(r.get("RANK")),
    }


def _ranking_row(r: pd.Series) -> dict[str, Any]:
    return {
        "fundo": to_str(r.get("FUNDO")),
        "tipo_cota": to_str(r.get("TIPO_COTA"), "UNICA"),
        "risco": to_str(r.get("RISCO_FUNDO"), "SEM DADOS"),
        "retorno_anual": to_float(r.get("RETORNO_ANUAL"), 0.0, 2),
        "vezes_recomendado": to_int(r.get("VEZES_RECOMENDADO")),
        "match_medio": to_float(r.get("MATCH_MEDIO"), 0.0, 1),
    }


def build_matches(todos: pd.DataFrame, ranking: pd.DataFrame) -> dict[str, Any]:
    return {
        "total": len(todos),
        "lista": [_match_row(r) for _, r in todos.iterrows()] if not todos.empty else [],
        "ranking_fundos": [_ranking_row(r) for _, r in ranking.iterrows()] if not ranking.empty else [],
    }


# ─── CREDIT ──────────────────────────────────────────────────────────
def _nome_empresa(raw: Any) -> str:
    """Deriva um nome anônimo legível a partir do hash do CNPJ.

    O ``id_cnpj`` no Gold já é SHA-256 anonimizado (LGPD). Usamos os
    primeiros 12 caracteres em CAIXA ALTA — colisão sobre 500 empresas
    fica em <1/10^9 por build (era ~1/34k com 8 chars).
    """
    s = to_str(raw)
    return f"Empresa {s[:12].upper()}" if s else "Empresa —"


def _credit_row(r: pd.Series) -> dict[str, Any]:
    return {
        "nome": _nome_empresa(r.get("id_cnpj")),
        "setor": setor_from_cnae(r.get("cd_cnae_prin")),
        "uf": to_str(r.get("uf"), "—"),
        "score": to_float(r.get("score_credito"), 0.0, 1),
        "prob_default": to_float(r.get("prob_default"), 0.0, 4),
        "risco": to_str(r.get("risco_credito"), "SEM DADOS"),
        "total_boletos": to_int(r.get("total_boletos")),
        "n_default": to_int(r.get("n_default")),
        "pct_default": to_float(r.get("pct_default"), 0.0, 2),
    }


def build_credit(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {
            "empresas": [],
            "stats": {
                "total": 0,
                "total_elegiveis": 0,
                "por_risco": {},
                "media_score": 0.0,
                "credit_min_boletos": CREDIT_MIN_BOLETOS,
            },
        }

    # Empresas exibidas: histórico mínimo de ``CREDIT_MIN_BOLETOS`` boletos
    # (filtra o ruído de 1-boleto que gera score artificial ~99). Ordenadas
    # por score descendente para que as melhores apareçam primeiro.
    elegiveis_mask = df["total_boletos"] >= CREDIT_MIN_BOLETOS
    elegiveis = df[elegiveis_mask]
    top = elegiveis.sort_values("score_credito", ascending=False).head(MAX_CREDIT)

    stats_media_score = to_float(elegiveis["score_credito"].mean(), 0.0, 1) if len(elegiveis) else 0.0
    stats_media_prob = (
        to_float(elegiveis["prob_default"].mean(), 0.0, 4) if len(elegiveis) and "prob_default" in elegiveis else 0.0
    )

    return {
        "empresas": [_credit_row(r) for _, r in top.iterrows()],
        "stats": {
            "total": len(df),
            "total_elegiveis": int(elegiveis_mask.sum()),
            "por_risco": elegiveis["risco_credito"].fillna("SEM DADOS").value_counts().to_dict(),
            "media_score": stats_media_score,
            "media_prob_default": stats_media_prob,
            "taxa_default_observada": (
                to_float(elegiveis["defaultou"].mean(), 0.0, 4) if "defaultou" in elegiveis else 0.0
            ),
            "credit_min_boletos": CREDIT_MIN_BOLETOS,
        },
    }
