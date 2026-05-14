"""IO defensivo — leitura dos arquivos do pipeline no Gold (ADLS) + validação pandera.

Substitui a leitura de ``data_real/`` local pela leitura direta do ADLS,
mantendo o contrato de retorno (tuplas e DataFrames) idêntico ao código
anterior para preservar ``payload.build_*`` sem mudança.

Cada ``read_*()`` valida o DataFrame contra o schema pandera correspondente
em modo ``lazy=True`` (acumula todos os erros) ANTES de devolver. Schema drift
quebra o pipeline com erro descritivo em vez de produzir ``data.json``
corrompido.

Cache:
- Bytes invalidados via ETag (zero egress quando cache local válido)
- Parse cache em ``.parsed.pkl`` (skip do parse openpyxl que é lento)
Implementado em ``lib.azure_io``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import pandera.pandas as pa

from . import azure_io
from .gold_paths import PATHS
from .logger import get_logger
from .schemas import (
    ClientesSchema,
    CreditSchema,
    MacroSchema,
    MatchesRankingSchema,
    MatchesTodosSchema,
    RatingGeralSchema,
    RatingResumoSchema,
)

log = get_logger(__name__)


class SchemaValidationError(RuntimeError):
    """Falha de schema validation. Não retentável — pipeline precisa intervir."""


def _validate(
    df: pd.DataFrame,
    schema: type[pa.DataFrameModel],
    source: str,
) -> pd.DataFrame:
    """Roda pandera em modo lazy. Devolve o DataFrame coercido ou explode.

    DataFrame vazio (arquivo ausente no Gold) é permitido — quem chama
    decide se quer tratar como `SystemExit` ou seguir com payload parcial.
    """
    if df.empty:
        log.warn("schema_validation_skipped_empty", source=source, schema=schema.__name__)
        return df
    try:
        validated = schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        failure_cases = getattr(exc, "failure_cases", None)
        n_failures = len(failure_cases) if failure_cases is not None else None
        log.error(
            "schema_validation_failed",
            source=source,
            schema=schema.__name__,
            failures=n_failures,
            sample=str(exc)[:2000],
        )
        head = failure_cases.head(5).to_dict("records") if failure_cases is not None else str(exc)
        raise SchemaValidationError(
            f"Schema {schema.__name__} falhou em {source}. Total de causas: {n_failures}. Top 5: {head}"
        ) from exc
    log.info(
        "schema_validation_ok",
        source=source,
        schema=schema.__name__,
        rows=len(validated),
    )
    return validated


def _empty_on_404(
    fn: Callable[..., pd.DataFrame],
    *args: Any,
    **kwargs: Any,
) -> pd.DataFrame:
    """Wrapper: devolve DataFrame vazio se o arquivo não existe no Gold."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        # Import lazy para não pagar import do azure-core se não precisar.
        from azure.core.exceptions import ResourceNotFoundError

        if isinstance(exc, ResourceNotFoundError):
            log.warn("file_not_found", path=str(args[0]) if args else "?")
            return pd.DataFrame()
        raise


def read_clientes() -> pd.DataFrame:
    df = _empty_on_404(
        azure_io.read_csv,
        PATHS["clientes"],
        encoding="utf-8-sig",
    )
    return _validate(df, ClientesSchema, "clientes.csv")


def read_credit_scores() -> pd.DataFrame:
    df = _empty_on_404(azure_io.read_csv, PATHS["credit"])
    if df.empty:
        return df
    for col in ("score_credito", "prob_default", "pct_default", "defaultou"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return _validate(df, CreditSchema, "scores_credito.csv")


def read_macro() -> pd.DataFrame:
    df = _empty_on_404(azure_io.read_csv, PATHS["macro"], sep=";", dtype=str)
    if df.empty:
        return df
    df["data_processamento"] = pd.to_datetime(df["data_processamento"], errors="coerce")
    for col in df.columns:
        if col != "data_processamento":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("data_processamento").reset_index(drop=True)
    return _validate(df, MacroSchema, "macroeconomicos/consolidade.csv")


def read_rating() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        sheets = azure_io.read_excel_sheets(PATHS["rating"], ["GERAL", "RESUMO_POR_FUNDO"])
    except Exception as exc:
        from azure.core.exceptions import ResourceNotFoundError

        if isinstance(exc, ResourceNotFoundError):
            log.warn("file_not_found", path=PATHS["rating"])
            return pd.DataFrame(), pd.DataFrame()
        raise
    geral = _validate(
        sheets.get("GERAL", pd.DataFrame()),
        RatingGeralSchema,
        "rating_fidc.xlsx::GERAL",
    )
    resumo = _validate(
        sheets.get("RESUMO_POR_FUNDO", pd.DataFrame()),
        RatingResumoSchema,
        "rating_fidc.xlsx::RESUMO_POR_FUNDO",
    )
    return geral, resumo


def read_matches() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        sheets = azure_io.read_excel_sheets(PATHS["matches"], ["TODOS_OS_MATCHES", "RANKING_FUNDOS"])
    except Exception as exc:
        from azure.core.exceptions import ResourceNotFoundError

        if isinstance(exc, ResourceNotFoundError):
            log.warn("file_not_found", path=PATHS["matches"])
            return pd.DataFrame(), pd.DataFrame()
        raise
    todos = _validate(
        sheets.get("TODOS_OS_MATCHES", pd.DataFrame()),
        MatchesTodosSchema,
        "matches.xlsx::TODOS_OS_MATCHES",
    )
    ranking = _validate(
        sheets.get("RANKING_FUNDOS", pd.DataFrame()),
        MatchesRankingSchema,
        "matches.xlsx::RANKING_FUNDOS",
    )
    return todos, ranking
