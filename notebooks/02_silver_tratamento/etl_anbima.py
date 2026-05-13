# Notebook: etl_anbima
# Camada: Silver — Tratamento
# Saída: Parquet no ADLS Gen2

# Databricks notebook source
import io
import os
import sys
from datetime import datetime

import pandas as pd
from azure.storage.blob import BlobServiceClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


# COMMAND ----------

def salvarDataLake(DF, NOME_CONTAINER, NOME_ARQUIVO, conn):
    print(f"Salvando {NOME_ARQUIVO} em {NOME_CONTAINER}...")
    blob_service_client = BlobServiceClient.from_connection_string(conn)

    output = io.BytesIO()
    DF.to_parquet(output, index=False, engine="pyarrow")

    caminho_blob = NOME_ARQUIVO if NOME_ARQUIVO.endswith(".parquet") else f"{NOME_ARQUIVO}.parquet"
    blob_service_client.get_blob_client(container=NOME_CONTAINER, blob=caminho_blob).upload_blob(
        output.getvalue(), overwrite=True
    )
    print(f"OK: {NOME_CONTAINER}/{caminho_blob} ({len(DF)} linhas)")


# COMMAND ----------

CONNECTION_STRING = azure_connection_string()
blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
client_silver = blob_service_client.get_container_client("silver")
client_bronze = blob_service_client.get_container_client("bronze")

pasta_base = "anbima/"

# COMMAND ----------

data = datetime.today()
ano = data.strftime("%Y")
mes = data.strftime("%m")
dia = data.strftime("%d")
sufixo_dia = f"{ano}{mes}{dia}.csv"

# 1. MAPEAMENTO BRONZE
arquivos_bronze: dict = {}
try:
    print(f"Buscando arquivos em: bronze/{pasta_base} (sufixo {sufixo_dia})...")
    blobs_bronze = list(client_bronze.list_blobs(name_starts_with=pasta_base))
    arquivos_bronze = {
        x.name[: -len(sufixo_dia) - 1].split("/")[-1]: x
        for x in blobs_bronze
        if x.name.endswith(sufixo_dia)
    }
    print(f"  Bronze: {len(arquivos_bronze)} arquivos do dia")
except Exception as e:
    print(f"Erro ao mapear Bronze: {e}")

# COMMAND ----------

# 2. MAPEAMENTO SILVER (snapshot acumulado)
arquivos_silver: dict = {}
try:
    print(f"Buscando arquivos em: silver/{pasta_base}...")
    blobs_silver = list(client_silver.list_blobs(name_starts_with=pasta_base))
    arquivos_silver = {x.name[:-8].split("/")[-1]: x for x in blobs_silver if x.name.endswith(".parquet")}
    print(f"  Silver: {len(arquivos_silver)} arquivos acumulados")
except Exception as e:
    print(f"Erro ao mapear Silver: {e}")

# COMMAND ----------

for nome_arquivo, blob_bronze in arquivos_bronze.items():
    print(f"\nINICIANDO: {nome_arquivo}")

    dados_bronze = client_bronze.get_blob_client(blob_bronze).download_blob().readall()
    df_bronze = pd.read_csv(io.BytesIO(dados_bronze), sep=";", low_memory=False)

    blob_silver = arquivos_silver.get(nome_arquivo)
    if blob_silver is not None:
        dados_silver = client_silver.get_blob_client(blob_silver).download_blob().readall()
        df_silver = pd.read_parquet(io.BytesIO(dados_silver))
        df = pd.concat([df_bronze, df_silver], axis=0).drop_duplicates().reset_index(drop=True)
        print(f"  Bronze ({len(df_bronze)}) + Silver ({len(df_silver)}) = {len(df)} (deduplicado)")
    else:
        df = df_bronze.drop_duplicates().reset_index(drop=True)
        print(f"  Primeira ingestão silver: {len(df)} linhas")

    salvarDataLake(df, "silver", f"{pasta_base}{nome_arquivo}.parquet", CONNECTION_STRING)
