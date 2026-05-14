"""IO defensivo — leitura dos arquivos do pipeline no Gold (ADLS).

Substitui a leitura de `data_real/` local pela leitura direta do ADLS,
mantendo o contrato de retorno (tuplas e DataFrames) idêntico ao código
anterior para preservar `payload.build_*` sem mudança.

Cache:
- Bytes invalidados via ETag (zero egress quando cache local válido)
- Parse cache em `.parsed.pkl` (skip do parse openpyxl que é lento)
Implementado em `lib.azure_io`.
"""
from __future__ import annotations

import pandas as pd

from . import azure_io
from .gold_paths import PATHS
from .logger import get_logger

log = get_logger(__name__)


def _empty_on_404(fn, *args, **kwargs):
    """Wrapper: devolve DataFrame vazio se o arquivo não existe no Gold."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 — qualquer falha de I/O cai aqui
        # ResourceNotFoundError do SDK Azure herda de HttpResponseError.
        # Imports lazy para evitar carga de azure-core no top-level se não precisar.
        from azure.core.exceptions import ResourceNotFoundError

        if isinstance(e, ResourceNotFoundError):
            log.warn("file_not_found", path=str(args[0]) if args else "?")
            return pd.DataFrame()
        raise


def read_clientes() -> pd.DataFrame:
    return _empty_on_404(azure_io.read_csv, PATHS["clientes"], encoding="utf-8-sig")


def read_credit_scores() -> pd.DataFrame:
    df = _empty_on_404(azure_io.read_csv, PATHS["credit"])
    if df.empty:
        return df
    for col in ("score_credito", "prob_default", "pct_default", "defaultou"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def read_macro() -> pd.DataFrame:
    df = _empty_on_404(azure_io.read_csv, PATHS["macro"], sep=";", dtype=str)
    if df.empty:
        return df
    df["data_processamento"] = pd.to_datetime(df["data_processamento"], errors="coerce")
    for col in df.columns:
        if col != "data_processamento":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("data_processamento").reset_index(drop=True)


def read_rating() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        sheets = azure_io.read_excel_sheets(PATHS["rating"], ["GERAL", "RESUMO_POR_FUNDO"])
    except Exception as e:  # noqa: BLE001
        from azure.core.exceptions import ResourceNotFoundError
        if isinstance(e, ResourceNotFoundError):
            log.warn("file_not_found", path=PATHS["rating"])
            return pd.DataFrame(), pd.DataFrame()
        raise
    return sheets.get("GERAL", pd.DataFrame()), sheets.get("RESUMO_POR_FUNDO", pd.DataFrame())


def read_matches() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        sheets = azure_io.read_excel_sheets(PATHS["matches"], ["TODOS_OS_MATCHES", "RANKING_FUNDOS"])
    except Exception as e:  # noqa: BLE001
        from azure.core.exceptions import ResourceNotFoundError
        if isinstance(e, ResourceNotFoundError):
            log.warn("file_not_found", path=PATHS["matches"])
            return pd.DataFrame(), pd.DataFrame()
        raise
    return sheets.get("TODOS_OS_MATCHES", pd.DataFrame()), sheets.get("RANKING_FUNDOS", pd.DataFrame())
