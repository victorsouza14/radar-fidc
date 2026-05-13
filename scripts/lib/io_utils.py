"""IO defensivo — leitura dos arquivos do pipeline com fallback para DataFrame vazio."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


def read_csv_safe(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def read_excel_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_excel(path, sheet_name=sheet_name)


def read_clientes(path: Path) -> pd.DataFrame:
    return read_csv_safe(path, encoding="utf-8-sig")


def read_credit_scores(path: Path) -> pd.DataFrame:
    df = read_csv_safe(path)
    if df.empty:
        return df
    for col in ("score_credito", "prob_default", "pct_default", "defaultou"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def read_macro(path: Path) -> pd.DataFrame:
    df = read_csv_safe(path, sep=";", dtype=str)
    if df.empty:
        return df
    df["data_processamento"] = pd.to_datetime(df["data_processamento"], errors="coerce")
    for col in df.columns:
        if col != "data_processamento":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("data_processamento").reset_index(drop=True)


def read_rating(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame()
    xls = pd.ExcelFile(path)
    geral  = pd.read_excel(xls, sheet_name="GERAL")  if "GERAL"  in xls.sheet_names else pd.DataFrame()
    resumo = pd.read_excel(xls, sheet_name="RESUMO_POR_FUNDO") if "RESUMO_POR_FUNDO" in xls.sheet_names else pd.DataFrame()
    return geral, resumo


def read_matches(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame()
    xls = pd.ExcelFile(path)
    todos   = pd.read_excel(xls, sheet_name="TODOS_OS_MATCHES") if "TODOS_OS_MATCHES" in xls.sheet_names else pd.DataFrame()
    ranking = pd.read_excel(xls, sheet_name="RANKING_FUNDOS")   if "RANKING_FUNDOS"   in xls.sheet_names else pd.DataFrame()
    return todos, ranking
