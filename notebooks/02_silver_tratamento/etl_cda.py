# Notebook: etl_cda
# Camada: Silver — Tratamento
# Saída: Parquet no ADLS Gen2

# Databricks notebook source
import gc
import io
import os
import sys
from datetime import datetime

import pandas as pd
from azure.storage.blob import BlobServiceClient
from dateutil.relativedelta import relativedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


CONNECTION_STRING = azure_connection_string()
blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
client_silver = blob_service_client.get_container_client("silver")
client_bronze = blob_service_client.get_container_client("bronze")
pasta_base = "cda/"

# A CDA é mensal e fica disponível ~1 mês após a referência. Usar relativedelta evita
# overflow em janeiro (month - 1 == 0).
data_anterior = datetime.today() - relativedelta(months=1)
ano = str(data_anterior.year)
mes = str(data_anterior.month).zfill(2)

# 1. MAPEAMENTO BRONZE
arquivos_bronze: dict = {}
try:
    print(f"Buscando arquivos em: bronze/{pasta_base} (referência {ano}-{mes})...")
    blobs_bronze = list(client_bronze.list_blobs(name_starts_with=pasta_base))
    arquivos_bronze = {
        x.name[:-10].split("/")[-1]: x
        for x in blobs_bronze
        if x.name.endswith(f"{ano}{mes}.csv")
    }
    print(f"  Bronze: {len(arquivos_bronze)} arquivos")
except Exception as e:
    print(f"Erro ao mapear Bronze: {e}")

# 2. MAPEAMENTO SILVER
arquivos_silver: dict = {}
try:
    print(f"Buscando arquivos em: silver/{pasta_base}...")
    blobs_silver = list(client_silver.list_blobs(name_starts_with=pasta_base))
    arquivos_silver = {
        x.name[:-8].split("/")[-1]: x
        for x in blobs_silver
        if x.name.endswith(".parquet")
    }
    print(f"  Silver: {len(arquivos_silver)} arquivos")
except Exception as e:
    print(f"Erro ao mapear Silver: {e}")


# 3. PROCESSAMENTO
for nome_arquivo_bronze, blob_bronze_prop in arquivos_bronze.items():
    df_bronze = df_silver = df_resultado = df = buffer = None

    try:
        print(f"\n--- Processando: {nome_arquivo_bronze} ---")

        dados_bronze = client_bronze.get_blob_client(blob_bronze_prop.name).download_blob().readall()
        df_bronze = pd.read_csv(io.BytesIO(dados_bronze), sep=";", low_memory=False, dtype=str)
        del dados_bronze

        blob_silver_prop = arquivos_silver.get(nome_arquivo_bronze)
        if blob_silver_prop:
            dados_silver = client_silver.get_blob_client(blob_silver_prop.name).download_blob().readall()
            df_silver = pd.read_parquet(io.BytesIO(dados_silver)).astype(str)
            del dados_silver

        if df_silver is not None and not df_silver.empty:
            df_resultado = pd.concat([df_bronze, df_silver], axis=0, ignore_index=True)
        else:
            df_resultado = df_bronze.copy()

        del df_bronze, df_silver
        df_bronze = df_silver = None

        # Tipagem das colunas numéricas conhecidas da CDA
        colunas_numericas = [
            "QT_VENDA_NEGOC", "VL_VENDA_NEGOC", "QT_POS_FINAL",
            "VL_MERC_POS_FINAL", "VL_AQUIS_NEGOC", "VL_CUSTO_POS_FINAL",
        ]
        for col in colunas_numericas:
            if col in df_resultado.columns:
                df_resultado[col] = pd.to_numeric(df_resultado[col], errors="coerce").fillna(0.0)

        for col in df_resultado.select_dtypes(include=["object"]).columns:
            df_resultado[col] = df_resultado[col].astype(str)

        qtd_antes = len(df_resultado)
        df = df_resultado.drop_duplicates(keep="last").reset_index(drop=True)
        del df_resultado
        df_resultado = None
        print(f"  Registros {qtd_antes} -> {len(df)} (após dedup)")

        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False, engine="pyarrow", compression="snappy")
        buffer.seek(0)

        nome_saida = f"cda/{nome_arquivo_bronze}.parquet"
        client_silver.get_blob_client(nome_saida).upload_blob(buffer, overwrite=True)
        print(f"  OK: silver/{nome_saida}")

    except Exception as e:
        print(f"Erro ao processar {nome_arquivo_bronze}: {e}")
    finally:
        df_bronze = df_silver = df_resultado = df = buffer = None
        gc.collect()
