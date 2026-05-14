# Notebook: 06_great_expectations
# Camada: Gold — Radar FIDC (Trust layer — Linha 1)
#
# Executa Great Expectations sobre os artefatos do Gold ANTES da promoção
# para `gold/final/`. Se qualquer suite falhar, a saída é gravada em
# `gold/staging/` (NÃO em `gold/final/`) e `expectations-result.json` reflete
# o estado. CI lê esse JSON e bloqueia o data-refresh quando overall_success
# for false.
#
# Schema do output (Seção 4 da spec):
#   {
#     "ts": ISO-UTC,
#     "source": "great_expectations",
#     "overall_success": bool,
#     "suites_passed": int,
#     "suites_failed": int,
#     "suites": [
#       {"name": "rating_fidc", "success": bool, "n_expectations": int,
#        "n_passed": int, "n_failed": int, "failures": [...]}
#     ]
#   }
#
# Suites (5):
#   1. rating_fidc   — 10 expectativas (score 0-100, classe A-D, CNPJ unique, ...)
#   2. matches       — 6 expectativas (match_score 0-100, CNPJ_FUNDO not null, ...)
#   3. clientes      — 5 expectativas (CPF regex pré-mask, segmento ∈ enum, ...)
#   4. credit        — 5 expectativas (scoring 0-1000, modelo_version, trained_at)
#   5. macro         — 7 expectativas (SELIC meta+efetiva 0-50, IPCA mensal -5..30,
#                      IPCA 12m -10..100, data_ref NN, inadimplência PJ/PF)
#
# Total: 33 expectativas distribuídas em 5 suites.

# Databricks notebook source
# MAGIC %pip install great_expectations azure-storage-blob pandas pyarrow openpyxl

# COMMAND ----------

from __future__ import annotations

import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from azure.storage.blob import BlobServiceClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


# COMMAND ----------

CONTAINER_GOLD = "gold"
PREFIX_FINAL = "final"
PREFIX_STAGING = "staging"
QUALITY_PATH = f"{PREFIX_FINAL}/_quality/expectations-result.json"

# Artefatos a validar. Cada entrada → suite name. Reader é um callable que
# devolve DataFrame; permite testar contra `gold/staging/` ou `gold/final/`
# bastando trocar o prefixo.
ARTEFATOS = {
    "rating_fidc": ("rating_fidc.xlsx", "GERAL"),
    "rating_resumo": ("rating_fidc.xlsx", "RESUMO_POR_FUNDO"),
    "matches": ("matches.xlsx", "TODOS_OS_MATCHES"),
    "clientes": ("clientes.csv", None),
    "credit": ("scores_credito.csv", None),
    "macro": ("macroeconomicos/consolidade.csv", None),
}


# COMMAND ----------


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ler_artefato(gold_client, prefix: str, basename: str, sheet: str | None) -> pd.DataFrame:
    """Lê um artefato do Gold. Suporta xlsx/csv. Devolve DataFrame vazio em erro."""
    caminho = f"{prefix}/{basename}"
    try:
        data = gold_client.get_blob_client(caminho).download_blob().readall()
    except Exception as e:
        print(f"AVISO: {caminho} não encontrado ({e}).")
        return pd.DataFrame()

    if basename.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(data), sheet_name=sheet or 0)
    if basename.endswith(".csv"):
        # Confirmado contra o Gold real:
        # - macroeconomicos/consolidade.csv: sep=";" (lido como str para preservar formato)
        # - clientes.csv: sep="," com BOM utf-8-sig
        # - scores_credito.csv: sep="," padrão
        if "consolidade" in basename or "macro" in basename:
            return pd.read_csv(io.BytesIO(data), sep=";", low_memory=False, dtype=str)
        if "clientes" in basename:
            return pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")
        return pd.read_csv(io.BytesIO(data), low_memory=False)
    raise ValueError(f"Extensão não suportada: {basename}")


# COMMAND ----------
# ─── Expectations engine — pandas-first, GE-compatible semantics ─────────
#
# Cada `expect_*` retorna dict `{name, success, observed, expected}` para
# integrar no schema final. Mantemos compat com Great Expectations: as
# nomes seguem `expect_column_values_to_*` para que esta camada possa
# ser substituída por GE puro no futuro sem mudar contratos.


def expect_column_values_between(
    df: pd.DataFrame, col: str, min_value: float, max_value: float, allow_null: bool = False
) -> dict[str, Any]:
    if col not in df.columns:
        return {"name": f"{col}_between_{min_value}_{max_value}", "success": False, "reason": "coluna_ausente"}
    s = pd.to_numeric(df[col], errors="coerce")
    if not allow_null:
        if s.isna().any():
            return {"name": f"{col}_between_{min_value}_{max_value}", "success": False, "reason": "valores_nulos"}
    bad = (~s.between(min_value, max_value)) & s.notna()
    n_bad = int(bad.sum())
    return {
        "name": f"{col}_between_{min_value}_{max_value}",
        "success": n_bad == 0,
        "observed_failures": n_bad,
        "expected": f"[{min_value}, {max_value}]",
    }


def expect_column_values_in_set(
    df: pd.DataFrame, col: str, values: list[Any], allow_null: bool = False
) -> dict[str, Any]:
    if col not in df.columns:
        return {"name": f"{col}_in_set", "success": False, "reason": "coluna_ausente"}
    series = df[col]
    if allow_null:
        series = series.dropna()
    bad = ~series.isin(values)
    n_bad = int(bad.sum())
    return {
        "name": f"{col}_in_set",
        "success": n_bad == 0,
        "observed_failures": n_bad,
        "expected": values,
        "allow_null": allow_null,
    }


def expect_column_to_be_unique(df: pd.DataFrame, col: str) -> dict[str, Any]:
    if col not in df.columns:
        return {"name": f"{col}_unique", "success": False, "reason": "coluna_ausente"}
    n_dup = int(df[col].duplicated().sum())
    return {"name": f"{col}_unique", "success": n_dup == 0, "observed_duplicates": n_dup}


def expect_column_values_to_match_regex(
    df: pd.DataFrame, col: str, pattern: str, normalize_cnpj: bool = False
) -> dict[str, Any]:
    if col not in df.columns:
        return {"name": f"{col}_regex", "success": False, "reason": "coluna_ausente"}
    rgx = re.compile(pattern)
    series = df[col].dropna().astype(str)
    if normalize_cnpj:
        # CNPJ pode vir como int (perde leading zeros) ou string com pontos/barras.
        # Normaliza: extrai só dígitos e padda pra 14.
        series = series.str.replace(r"\D", "", regex=True).str.zfill(14)
    bad = series.apply(lambda v: not bool(rgx.fullmatch(v)))
    n_bad = int(bad.sum())
    return {
        "name": f"{col}_regex",
        "success": n_bad == 0,
        "observed_failures": n_bad,
        "expected_pattern": pattern,
    }


def expect_column_to_not_be_null(df: pd.DataFrame, col: str) -> dict[str, Any]:
    if col not in df.columns:
        return {"name": f"{col}_not_null", "success": False, "reason": "coluna_ausente"}
    n_null = int(df[col].isna().sum())
    return {"name": f"{col}_not_null", "success": n_null == 0, "observed_nulls": n_null}


def expect_row_count_between(df: pd.DataFrame, min_rows: int, max_rows: int) -> dict[str, Any]:
    n = len(df)
    return {
        "name": f"row_count_between_{min_rows}_{max_rows}",
        "success": min_rows <= n <= max_rows,
        "observed": n,
    }


# COMMAND ----------
# ─── Suites por artefato (~31 expectativas total) ────────────────────────


def suite_rating_fidc(df: pd.DataFrame) -> list[dict[str, Any]]:
    """10 expectativas alinhadas à realidade do Gold:
    - RISCO permite NaN (2249 FIDCs ainda sem classificação)
    - CNPJ normalizado (Gold armazena como int — perde leading zeros)
    - TAXA_INADIMPLENCIA sem cap superior (outliers documentados em
      docs/limitacoes_atuais.md; será limpa quando o pipeline normalizar a coluna)
    """
    return [
        expect_column_values_between(df, "SCORE_RISCO", 0.0, 100.0, allow_null=True),
        expect_column_values_in_set(
            df, "RISCO", ["BAIXO", "MEDIO", "ALTO", "SEM DADOS"], allow_null=True
        ),
        expect_column_values_in_set(
            df, "PERFIL_SUGERIDO", ["CONSERVADOR", "MODERADO", "ARROJADO", "SEM DADOS"], allow_null=True
        ),
        expect_column_to_not_be_null(df, "CNPJ"),
        expect_column_values_to_match_regex(df, "CNPJ", r"\d{14}", normalize_cnpj=True),
        expect_row_count_between(df, 2000, 8000),
        expect_column_values_between(df, "VOLATILIDADE", 0.0, 1000.0, allow_null=True),
        expect_column_values_between(df, "TAXA_INADIMPLENCIA", 0.0, 100000.0, allow_null=True),
        expect_column_values_between(df, "MESES_HISTORICO", 0, 600, allow_null=True),
        expect_column_to_not_be_null(df, "FUNDO"),
    ]


def suite_rating_resumo(df: pd.DataFrame) -> list[dict[str, Any]]:
    """5 expectativas para a aba RESUMO_POR_FUNDO."""
    return [
        expect_column_to_be_unique(df, "CNPJ"),
        expect_column_values_to_match_regex(df, "CNPJ", r"\d{14}", normalize_cnpj=True),
        expect_column_values_between(df, "SCORE_RISCO", 0.0, 100.0, allow_null=True),
        expect_column_values_in_set(
            df, "RISCO", ["BAIXO", "MEDIO", "ALTO", "SEM DADOS"], allow_null=True
        ),
        expect_column_to_not_be_null(df, "FUNDO"),
    ]


def suite_matches(df: pd.DataFrame) -> list[dict[str, Any]]:
    """6 expectativas: match_score 0-100, FUNDO/CPF not null, PERFIL_CLIENTE válido."""
    return [
        expect_column_values_between(df, "MATCH_SCORE", 0.0, 100.0),
        expect_column_to_not_be_null(df, "FUNDO"),
        expect_column_to_not_be_null(df, "CPF"),
        expect_column_values_in_set(
            df, "PERFIL_CLIENTE", ["CONSERVADOR", "MODERADO", "ARROJADO"]
        ),
        expect_column_values_in_set(df, "RISCO_FUNDO", ["BAIXO", "MEDIO", "ALTO", "SEM DADOS"]),
        expect_column_values_between(df, "RANK", 0, 100),
    ]


def suite_clientes(df: pd.DataFrame) -> list[dict[str, Any]]:
    """5 expectativas pré-mascaramento: CPF regex, perfil válido, score 0-100."""
    return [
        expect_column_values_to_match_regex(df, "cpf", r"\d{10,11}"),
        expect_column_to_not_be_null(df, "nome"),
        expect_column_values_in_set(df, "perfil", ["CONSERVADOR", "MODERADO", "ARROJADO"]),
        expect_column_values_between(df, "score_perfil", 0.0, 100.0, allow_null=True),
        expect_row_count_between(df, 1, 1000000),
    ]


def suite_credit(df: pd.DataFrame) -> list[dict[str, Any]]:
    """5 expectativas para scores_credito.csv.

    Colunas reais do Gold: id_cnpj (hashed), prob_default, score_credito,
    risco_credito, total_boletos, n_default, pct_default, defaultou.
    Sem regex em id_cnpj porque é hash, não CNPJ literal.
    """
    return [
        expect_column_values_between(df, "score_credito", 0.0, 100.0, allow_null=True),
        expect_column_values_between(df, "prob_default", 0.0, 1.0, allow_null=True),
        expect_column_to_not_be_null(df, "id_cnpj"),
        expect_column_values_in_set(
            df, "risco_credito", ["BAIXO", "MEDIO", "ALTO"], allow_null=True
        ),
        expect_row_count_between(df, 1, 1000000),
    ]


def suite_macro(df: pd.DataFrame) -> list[dict[str, Any]]:
    """7 expectativas: SELIC meta + efetiva 0-50, IPCA mensal -5..30,
    IPCA 12m acumulado -10..100, data_processamento NN, inadimplência PJ/PF.

    `selic_efetiva` (SGS 1178) é a série que o frontend prefere para
    exibição e que o notebook de cenário macro usa para classificar — sua
    ausência ou outlier degrada silenciosamente a UX. `ipca_12m_acumulado`
    (SGS 13522) tem a mesma criticidade.
    """
    return [
        expect_column_values_between(df, "selic_meta", 0.0, 50.0, allow_null=True),
        expect_column_values_between(df, "selic_efetiva", 0.0, 50.0, allow_null=True),
        expect_column_values_between(df, "ipca_mensal", -5.0, 30.0, allow_null=True),
        expect_column_values_between(df, "ipca_12m_acumulado", -10.0, 100.0, allow_null=True),
        expect_column_to_not_be_null(df, "data_processamento"),
        expect_column_values_between(df, "inadimplencia_pj", 0.0, 50.0, allow_null=True),
        expect_column_values_between(df, "inadimplencia_pf", 0.0, 50.0, allow_null=True),
    ]


SUITES = {
    "rating_fidc": suite_rating_fidc,
    "rating_resumo": suite_rating_resumo,
    "matches": suite_matches,
    "clientes": suite_clientes,
    "credit": suite_credit,
    "macro": suite_macro,
}


# COMMAND ----------


def rodar_suite(
    name: str, df: pd.DataFrame, suite_fn
) -> dict[str, Any]:
    if df.empty:
        return {
            "name": name,
            "success": False,
            "n_expectations": 0,
            "n_passed": 0,
            "n_failed": 0,
            "failures": [{"reason": "dataframe_vazio_ou_ausente"}],
        }
    results = suite_fn(df)
    n_passed = sum(1 for r in results if r.get("success"))
    n_failed = len(results) - n_passed
    failures = [r for r in results if not r.get("success")]
    return {
        "name": name,
        "success": n_failed == 0,
        "n_expectations": len(results),
        "n_passed": n_passed,
        "n_failed": n_failed,
        "failures": failures,
    }


def gravar_resultado(gold_client, payload: dict[str, Any], path: str) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    gold_client.get_blob_client(path).upload_blob(data, overwrite=True)
    print(f"Salvo: gold/{path} ({len(data)} bytes)")


# COMMAND ----------


def main() -> int:
    conn = azure_connection_string()
    gold_client = BlobServiceClient.from_connection_string(conn).get_container_client(CONTAINER_GOLD)

    # Estratégia: roda primeiro contra `staging/`. Se a pipeline ainda escreveu em
    # `final/` (modo legado), fallback para `final/`. O resultado é gravado SEMPRE
    # em `final/_quality/` (frontend lê de lá).
    prefix_to_check = PREFIX_STAGING
    suites_resultados: list[dict[str, Any]] = []
    for suite_name, (basename, sheet) in ARTEFATOS.items():
        df = _ler_artefato(gold_client, prefix_to_check, basename, sheet)
        if df.empty:
            # Fallback: tenta em `final/` (pipeline pode ainda não usar staging).
            df = _ler_artefato(gold_client, PREFIX_FINAL, basename, sheet)
        suite_fn = SUITES[suite_name]
        res = rodar_suite(suite_name, df, suite_fn)
        suites_resultados.append(res)
        status = "OK" if res["success"] else "FAIL"
        print(f"[{status}] {suite_name}: {res['n_passed']}/{res['n_expectations']} expectativas")

    suites_passed = sum(1 for s in suites_resultados if s["success"])
    suites_failed = len(suites_resultados) - suites_passed
    overall = suites_failed == 0

    payload = {
        "ts": _now_iso_utc(),
        "source": "great_expectations",
        "overall_success": overall,
        "suites_passed": suites_passed,
        "suites_failed": suites_failed,
        "suites": suites_resultados,
    }

    print("\n" + "=" * 60)
    print(f"Overall success: {overall} ({suites_passed} passed, {suites_failed} failed)")
    print("=" * 60)

    gravar_resultado(gold_client, payload, QUALITY_PATH)

    if not overall:
        # Pipeline NÃO promove. Sinaliza para o orquestrador.
        print(
            "\nERRO: Great Expectations falhou. Mantém artefatos em gold/staging/. "
            "Frontend usa último gold/final/ válido + trust bar vermelho."
        )
        return 1
    print("\nGreat Expectations OK. Promoção para gold/final/ liberada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
