"""Builders por seção do payload — uma função pura por seção (SRP).

Cada builder recebe seus DataFrames e devolve o dict pronto para serializar.
Sem efeitos colaterais.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from .formatters import (
    cnpj_fmt,
    mask_cpf,
    mask_email,
    mask_name,
    mask_phone,
    to_float,
    to_int,
    to_str,
    truncate,
)
from .scenario import classify_selic

# ─── limites de saída (evita payload gigante) ─────────────────────────
MAX_FIDC_RESUMO = 400
MAX_FIDC_DETALHE = 1500
MAX_SCATTER = 600
MAX_CREDIT = 500

# Filtra fundos com pouco histórico (não confiáveis para ranking).
MIN_MESES_HISTORICO = 6

# Limite máximo de retorno anual a ser plotado (acima disso é provavelmente artefato).
RETORNO_OUTLIER_PCT = 200.0


# ─── MACRO ───────────────────────────────────────────────────────────
# A regra de cenário vive em scripts/lib/scenario.py (fonte única).


def build_macro(
    df: pd.DataFrame,
    focus_indicators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback_date = datetime.today().strftime("%Y-%m-%d")
    if df.empty:
        return {
            "selic": None,
            "cdi": None,
            "ipca": None,
            "selic_proj": None,
            "ipca_proj": None,
            "cenario": "indisponivel",
            "descricao": "Sem dados macro disponíveis.",
            "data_ref": fallback_date,
            "inadimplencia_pj": None,
            "inadimplencia_pf": None,
            "ibc_br": None,
            "dolar_venda": None,
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
    if ipca_12m is None:
        ipca_col = df.get("ipca_mensal")
        if ipca_col is None:
            ipca_col = pd.Series([], dtype=float)
        ipca_serie = pd.to_numeric(ipca_col, errors="coerce").dropna().tail(12)
        if not ipca_serie.empty:
            acumulado = 1.0
            for m in ipca_serie:
                acumulado *= 1.0 + float(m) / 100.0
            ipca_12m = round((acumulado - 1.0) * 100.0, 2)

    cen = classify_selic(selic)
    cenario, descricao = cen.chave, cen.descricao
    ref = last.get("data_processamento")
    data_ref = ref.strftime("%Y-%m-%d") if pd.notna(ref) else fallback_date

    # Projeções: prioridade para Boletim Focus (BCB) via indicadores.parquet.
    # Fallback para heurística simples se Focus indisponível ou stale.
    proj_source: str | None = None
    proj_date: str | None = None
    selic_proj_2026: float | None = None
    selic_proj_2027: float | None = None
    ipca_proj_2026: float | None = None
    ipca_proj_2027: float | None = None
    if focus_indicators and focus_indicators.get("is_proj_heuristica") is False:
        selic_proj = to_float(focus_indicators.get("selic_projetada_12m"), None, 2)
        ipca_proj = to_float(focus_indicators.get("ipca_projetado_12m"), None, 2)
        is_heuristica = False
        proj_source = str(focus_indicators.get("proj_source") or "bcb_focus_top5")
        proj_date_raw = focus_indicators.get("proj_date")
        proj_date = str(proj_date_raw) if proj_date_raw is not None else None
        selic_proj_2026 = to_float(focus_indicators.get("selic_proj_2026"), None, 2)
        selic_proj_2027 = to_float(focus_indicators.get("selic_proj_2027"), None, 2)
        ipca_proj_2026 = to_float(focus_indicators.get("ipca_proj_2026"), None, 2)
        ipca_proj_2027 = to_float(focus_indicators.get("ipca_proj_2027"), None, 2)
    else:
        # Fallback heurístico (sinalizado com is_proj_heuristica=True).
        selic_proj = round(selic - 0.5, 2) if selic is not None else None
        ipca_proj = (
            round(ipca_12m * 0.9, 2)
            if ipca_12m is not None and ipca_12m > 0
            else (round(ipca_12m, 2) if ipca_12m is not None else None)
        )
        is_heuristica = True

    return {
        "selic": selic,
        "cdi": cdi,
        "ipca": ipca_12m,
        "selic_proj": selic_proj,
        "ipca_proj": ipca_proj,
        "is_proj_heuristica": is_heuristica,
        "proj_source": proj_source,
        "proj_date": proj_date,
        "selic_proj_2026": selic_proj_2026,
        "selic_proj_2027": selic_proj_2027,
        "ipca_proj_2026": ipca_proj_2026,
        "ipca_proj_2027": ipca_proj_2027,
        "cenario": cenario,
        "descricao": descricao,
        "data_ref": data_ref,
        "inadimplencia_pj": to_float(last.get("inadimplencia_pj"), None, 2),
        "inadimplencia_pf": to_float(last.get("inadimplencia_pf"), None, 2),
        "ibc_br": to_float(last.get("ibc_br"), None, 2),
        "dolar_venda": to_float(last.get("dolar_venda"), None, 4),
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
        "scr": to_float(r.get("SCR_NORMALIZADO"), None, 4),
        "conc_maior": to_float(r.get("CONC_MAIOR_CEDENTE"), 0.0, 2),
        "conc_top3": to_float(r.get("CONC_TOP3"), 0.0, 2),
        "meses_historico": to_int(r.get("MESES_HISTORICO")),
    }


def _fidc_resumo_row(r: pd.Series) -> dict[str, Any]:
    return {
        "cnpj": cnpj_fmt(r.get("CNPJ")),
        "fundo": to_str(r.get("FUNDO")),
        "score_risco": to_float(r.get("SCORE_RISCO"), 0.0, 1),
        "risco": to_str(r.get("RISCO"), "SEM DADOS"),
        "retorno_medio": to_float(r.get("RETORNO_MEDIO"), 0.0, 2),
        "melhor_cota": to_str(r.get("MELHOR_COTA"), "UNICA"),
        "perfil_predominante": to_str(r.get("PERFIL_PREDOMINANTE"), "SEM DADOS"),
    }


def _scatter_row(r: pd.Series) -> dict[str, Any]:
    return {
        "nome": truncate(r.get("FUNDO"), 60),
        "score_risco": to_float(r.get("SCORE_RISCO"), 0.0, 1),
        "retorno": to_float(r.get("RETORNO_ANUAL"), 0.0, 2),
        "volatilidade": to_float(r.get("VOLATILIDADE"), 0.0, 2),
        "risco": to_str(r.get("RISCO"), "SEM DADOS"),
        "tipo_cota": to_str(r.get("TIPO_COTA"), "UNICA"),
        "perfil": to_str(r.get("PERFIL_SUGERIDO"), "SEM DADOS"),
    }


def build_fidcs(geral: pd.DataFrame, resumo: pd.DataFrame) -> dict[str, Any]:
    if geral.empty:
        return {
            "stats": {
                "total_classes": 0,
                "total_fundos": 0,
                "distribuicao": {"por_risco": {}, "por_perfil": {}, "por_cota": {}},
            },
            "resumo": [],
            "detalhe": [],
            "scatter": [],
        }

    # Fundos com pouco histórico não são confiáveis para ranking.
    # Eles continuam contando nas estatísticas globais, mas saem das listagens ordenadas.
    confiaveis = geral[geral["MESES_HISTORICO"].fillna(0) >= MIN_MESES_HISTORICO]

    deduped = confiaveis.drop_duplicates(subset=["CNPJ", "FUNDO", "TIPO_COTA"]).sort_values(
        "SCORE_RISCO", ascending=True
    )

    if not resumo.empty:
        # Resumo usa CNPJs presentes no conjunto confiável
        cnpjs_ok = set(confiaveis["CNPJ"].astype(str))
        resumo_filtrado = resumo[resumo["CNPJ"].astype(str).isin(cnpjs_ok)]
        resumo_deduped = resumo_filtrado.drop_duplicates(subset=["CNPJ"]).sort_values("SCORE_RISCO", ascending=True)
    else:
        resumo_deduped = pd.DataFrame()

    scatter_pool = confiaveis.dropna(subset=["SCORE_RISCO", "RETORNO_ANUAL"])
    scatter_pool = scatter_pool[scatter_pool["RETORNO_ANUAL"].abs() <= 200]
    scatter_sample = (
        scatter_pool.sample(min(MAX_SCATTER, len(scatter_pool)), random_state=42)
        if len(scatter_pool) > MAX_SCATTER
        else scatter_pool
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
        },
        "resumo": [_fidc_resumo_row(r) for _, r in resumo_deduped.head(MAX_FIDC_RESUMO).iterrows()],
        "detalhe": [_fidc_detalhe_row(r) for _, r in deduped.head(MAX_FIDC_DETALHE).iterrows()],
        "scatter": [_scatter_row(r) for _, r in scatter_sample.iterrows()],
    }


# ─── CLIENTES ────────────────────────────────────────────────────────
# Todos os campos PII são mascarados antes de virem para data.json (LGPD).
def _cliente_row(r: pd.Series) -> dict[str, Any]:
    return {
        "cpf": mask_cpf(r.get("cpf")),
        "nome": mask_name(r.get("nome")),
        "email": mask_email(r.get("email")),
        "telefone": mask_phone(r.get("telefone")),
        "idade": to_int(r.get("idade")),
        "renda": to_int(r.get("renda")),
        "experiencia": to_int(r.get("experiencia")),
        "horizonte": to_int(r.get("horizonte")),
        "perfil": to_str(r.get("perfil"), "MODERADO"),
        "score_perfil": to_float(r.get("score_perfil"), 0.0, 1),
        "data_cadastro": to_str(r.get("data_cadastro")),
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
        "score_cliente": to_float(r.get("SCORE_CLIENTE"), 0.0, 1),
        "fundo": to_str(r.get("FUNDO")),
        "tipo_cota": to_str(r.get("TIPO_COTA"), "UNICA"),
        "risco_fundo": to_str(r.get("RISCO_FUNDO"), "SEM DADOS"),
        "score_risco_fundo": to_float(r.get("SCORE_RISCO_FUNDO"), 0.0, 1),
        "perfil_fundo": to_str(r.get("PERFIL_FUNDO"), "SEM DADOS"),
        "retorno_anual": to_float(r.get("RETORNO_ANUAL"), 0.0, 2),
        "volatilidade": to_float(r.get("VOLATILIDADE"), 0.0, 2),
        "taxa_inad": to_float(r.get("TAXA_INAD"), 0.0, 2),
        "meses_historico": to_int(r.get("MESES_HISTORICO")),
        "match_score": to_float(r.get("MATCH_SCORE"), 0.0, 1),
        "s_perfil": to_float(r.get("S_PERFIL"), 0.0, 1),
        "s_risco": to_float(r.get("S_RISCO"), 0.0, 1),
        "s_retorno": to_float(r.get("S_RETORNO"), 0.0, 1),
        "s_historico": to_float(r.get("S_HISTORICO"), 0.0, 1),
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
# Mínimo de boletos para que o score seja considerado confiável. Empresas
# abaixo desse threshold são marcadas `dados_suficientes=False` e o
# frontend renderiza "Dados insuficientes" no lugar dos valores numéricos.
MIN_BOLETOS_SCORE_CONFIAVEL = 20


def _nome_empresa(raw: Any) -> str:
    """Deriva um nome anônimo legível a partir do hash do CNPJ.

    O ``id_cnpj`` no Gold já é SHA-256 anonimizado (LGPD). Usamos os
    primeiros 8 caracteres em CAIXA ALTA para obter um identificador
    determinístico e fácil de comunicar (ex.: ``Empresa A3B5C2D9``).
    """
    s = to_str(raw)
    return f"Empresa {s[:8].upper()}" if s else "Empresa —"


def _credit_row(r: pd.Series) -> dict[str, Any]:
    total_boletos = to_int(r.get("total_boletos"))
    dados_suficientes = total_boletos >= MIN_BOLETOS_SCORE_CONFIAVEL
    return {
        "nome": _nome_empresa(r.get("id_cnpj")),
        "score": to_float(r.get("score_credito"), 0.0, 1),
        "prob_default": to_float(r.get("prob_default"), 0.0, 4),
        "risco": to_str(r.get("risco_credito"), "SEM DADOS"),
        "total_boletos": total_boletos,
        "n_default": to_int(r.get("n_default")),
        "pct_default": to_float(r.get("pct_default"), 0.0, 2),
        "dados_suficientes": dados_suficientes,
    }


def build_credit(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {
            "empresas": [],
            "stats": {
                "total": 0,
                "total_confiaveis": 0,
                "por_risco": {},
                "media_score": 0.0,
                "min_boletos_score_confiavel": MIN_BOLETOS_SCORE_CONFIAVEL,
            },
        }

    sample_size_each = MAX_CREDIT // 3
    df_sorted = df.sort_values("score_credito", ascending=False)
    sample = (
        pd.concat(
            [
                df_sorted.head(sample_size_each),
                df_sorted.tail(sample_size_each),
                df_sorted.sample(min(sample_size_each, len(df_sorted)), random_state=42),
            ]
        )
        .drop_duplicates(subset=["id_cnpj"])
        .head(MAX_CREDIT)
    )

    confiaveis_mask = df["total_boletos"] >= MIN_BOLETOS_SCORE_CONFIAVEL
    df_confiaveis = df[confiaveis_mask]

    # Estatísticas agregadas usam apenas empresas com dados suficientes —
    # caso contrário a média é dominada por scores ruidosos de empresas com
    # 1-2 boletos. Por_risco mantém o universo total para auditoria.
    stats_media_score = to_float(df_confiaveis["score_credito"].mean(), 0.0, 1) if len(df_confiaveis) else 0.0
    stats_media_prob = (
        to_float(df_confiaveis["prob_default"].mean(), 0.0, 4)
        if len(df_confiaveis) and "prob_default" in df_confiaveis
        else 0.0
    )

    return {
        "empresas": [_credit_row(r) for _, r in sample.iterrows()],
        "stats": {
            "total": len(df),
            "total_confiaveis": int(confiaveis_mask.sum()),
            "por_risco": df["risco_credito"].fillna("SEM DADOS").value_counts().to_dict(),
            "media_score": stats_media_score,
            "media_prob_default": stats_media_prob,
            "taxa_default_observada": to_float(df["defaultou"].mean(), 0.0, 4) if "defaultou" in df else 0.0,
            "min_boletos_score_confiavel": MIN_BOLETOS_SCORE_CONFIAVEL,
        },
    }
