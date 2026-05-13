# Notebook: etl_macro
# Camada: Silver — Tratamento
# Saída: Parquet consolidado de indicadores macroeconômicos no ADLS Gen2

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
    client = BlobServiceClient.from_connection_string(conn)
    buf = io.BytesIO()
    DF.to_parquet(buf, index=False, engine="pyarrow")
    caminho = NOME_ARQUIVO if NOME_ARQUIVO.endswith(".parquet") else f"{NOME_ARQUIVO}.parquet"
    client.get_blob_client(container=NOME_CONTAINER, blob=caminho).upload_blob(
        buf.getvalue(), overwrite=True
    )
    print(f"OK: {NOME_CONTAINER}/{caminho} ({len(DF)} linhas)")


# COMMAND ----------

CONNECTION_STRING = azure_connection_string()
blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
client_silver = blob_service_client.get_container_client("silver")
client_bronze = blob_service_client.get_container_client("bronze")

pasta_base = "dados_macroeconomicos/"

# COMMAND ----------

data = datetime.today()
ano = data.strftime("%Y")
mes = data.strftime("%m")
dia = data.strftime("%d")
sufixo_dia_iso = f"{ano}-{mes}-{dia}.csv"
sufixo_dia_compacto = f"{ano}{mes}{dia}.csv"

# 1. MAPEAMENTO BRONZE
df_bronze = pd.DataFrame()
try:
    print(f"Buscando arquivos em: bronze/{pasta_base}...")
    blobs_bronze = list(client_bronze.list_blobs(name_starts_with=pasta_base))
    arquivos_bronze = [
        x for x in blobs_bronze if x.name.endswith((sufixo_dia_iso, sufixo_dia_compacto))
    ]
    if not arquivos_bronze:
        print(f"Nenhum arquivo bronze encontrado para o dia {data:%Y-%m-%d}.")
    else:
        for blob in arquivos_bronze:
            dados = client_bronze.get_blob_client(blob).download_blob().readall()
            df_tmp = pd.read_csv(io.BytesIO(dados), sep=";", low_memory=False, dtype=str)
            df_bronze = pd.concat([df_bronze, df_tmp], ignore_index=True)
            print(f"  Lido {blob.name}: {len(df_tmp)} linhas")
except Exception as e:
    print(f"Erro ao mapear Bronze: {e}")

# COMMAND ----------

# 2. MAPEAMENTO SILVER (snapshot acumulado)
df_silver = pd.DataFrame()
try:
    print(f"Buscando arquivos em: silver/{pasta_base}...")
    blobs_silver = list(client_silver.list_blobs(name_starts_with=pasta_base))
    parquets_silver = [x for x in blobs_silver if x.name.endswith(".parquet")]
    if parquets_silver:
        dados = client_silver.get_blob_client(parquets_silver[0]).download_blob().readall()
        df_silver = pd.read_parquet(io.BytesIO(dados))
        print(f"  Silver acumulada: {len(df_silver)} linhas")
    else:
        print("  Nenhum parquet silver pré-existente (primeira execução).")
except Exception as e:
    print(f"Erro ao mapear Silver: {e}")

# COMMAND ----------

# Concatenação + deduplicação
if df_bronze.empty and df_silver.empty:
    print("Sem dados para processar. Encerrando sem gravar.")
else:
    df_resultado = pd.concat([df_bronze, df_silver], axis=0, ignore_index=True)
    df_resultado = df_resultado.drop_duplicates().reset_index(drop=True)
    print(f"Resultado consolidado: {len(df_resultado)} linhas")
    salvarDataLake(df_resultado, "silver", f"{pasta_base}consolidado.parquet", CONNECTION_STRING)
