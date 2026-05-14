# Notebook: etl_focus
# Camada: Silver — Tratamento
# Saída: `silver/focus/projecoes_anuais.parquet`
#
# Lê o CSV bruto do Bronze (`bronze/focus/expectativas_top5_anuais.csv`),
# filtra a coluna `Mediana` das top 5 casas para os indicadores `Selic` e
# `IPCA`, e pivota para uma tabela compacta indexada por (Indicador,
# DataReferencia) com mediana e data de referência da pesquisa.
#
# Estrutura esperada do CSV Bronze (campos da API Olinda BCB):
#   Indicador           — "Selic" | "IPCA"
#   Data                — data da pesquisa (ex.: "2026-05-13")
#   DataReferencia      — ano-referência da projeção (ex.: "2026", "2027")
#   Mediana             — projeção mediana dos top 5
#   Media               — média (não usamos)
#   numeroRespondentes  — quantos analistas (info auxiliar)
#
# Estrutura do parquet Silver gerado:
#   Indicador, DataReferencia (int), Mediana (float),
#   DataPesquisa (date), data_processamento (date)
#
# Falha graciosa: se Bronze ausente/vazio, não escreve parquet — Gold
# detecta ausência e cai para heurística com `is_proj_heuristica: true`.

# Databricks notebook source
# MAGIC %pip install azure-storage-blob pyarrow pandas

# COMMAND ----------

import io
import os
import sys
from datetime import date

import pandas as pd
from azure.storage.blob import BlobServiceClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


# COMMAND ----------

CONTAINER_BRONZE = "bronze"
CONTAINER_SILVER = "silver"
BRONZE_LATEST = "focus/expectativas_top5_anuais.csv"
SILVER_OUT = "focus/projecoes_anuais.parquet"

# Ano mínimo a manter no Silver — projeções de anos passados não interessam ao Gold.
# Mantém ano corrente para casos onde a primeira ingestão acontece no início do ano.
ANO_MINIMO = date.today().year


# COMMAND ----------


def ler_bronze(client_bronze, caminho: str) -> pd.DataFrame:
    try:
        dados = client_bronze.get_blob_client(caminho).download_blob().readall()
        df = pd.read_csv(io.BytesIO(dados), sep=";", low_memory=False, dtype=str)
        print(f"Bronze lido: {caminho} ({len(df)} linhas)")
        return df
    except Exception as e:
        print(f"AVISO: não foi possível ler bronze/{caminho} ({e}). Silver abortado.")
        return pd.DataFrame()


def transformar(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Filtra Selic/IPCA, casteia tipos, mantém última pesquisa por (Indicador, DataReferencia)."""
    if df_raw.empty:
        return df_raw
    requeridos = {"Indicador", "Data", "DataReferencia", "Mediana"}
    faltando = requeridos - set(df_raw.columns)
    if faltando:
        print(f"AVISO: colunas ausentes no Bronze {sorted(faltando)}. Silver abortado.")
        return pd.DataFrame()

    df = df_raw[df_raw["Indicador"].isin(["Selic", "IPCA"])].copy()
    df["DataReferencia"] = pd.to_numeric(df["DataReferencia"], errors="coerce")
    df["Mediana"] = pd.to_numeric(df["Mediana"], errors="coerce")
    df["DataPesquisa"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["DataReferencia", "Mediana", "DataPesquisa"])
    df = df[df["DataReferencia"].astype(int) >= ANO_MINIMO]

    if df.empty:
        print("AVISO: nada restou após filtros. Silver abortado.")
        return df

    # Pega a pesquisa MAIS RECENTE por (Indicador, DataReferencia).
    df = df.sort_values("DataPesquisa").groupby(["Indicador", "DataReferencia"], as_index=False).last()
    df["DataReferencia"] = df["DataReferencia"].astype(int)
    df["Mediana"] = df["Mediana"].astype(float).round(4)
    df["DataPesquisa"] = df["DataPesquisa"].dt.date
    df["data_processamento"] = date.today().isoformat()

    cols = ["Indicador", "DataReferencia", "Mediana", "DataPesquisa", "data_processamento"]
    return df[cols].sort_values(["Indicador", "DataReferencia"]).reset_index(drop=True)


def salvar_silver(df: pd.DataFrame, client_silver, caminho: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    client_silver.get_blob_client(caminho).upload_blob(buf.getvalue(), overwrite=True)
    print(f"Salvo: silver/{caminho} ({len(df)} linhas)")


# COMMAND ----------


def main() -> int:
    conn = azure_connection_string()
    blob_svc = BlobServiceClient.from_connection_string(conn)
    client_bronze = blob_svc.get_container_client(CONTAINER_BRONZE)
    client_silver = blob_svc.get_container_client(CONTAINER_SILVER)

    df_raw = ler_bronze(client_bronze, BRONZE_LATEST)
    df_silver = transformar(df_raw)

    if df_silver.empty:
        print("Silver não escrito (sem dados). Gold cai para heurística.")
        return 1

    salvar_silver(df_silver, client_silver, SILVER_OUT)
    print("\nPrévia:")
    print(df_silver.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
