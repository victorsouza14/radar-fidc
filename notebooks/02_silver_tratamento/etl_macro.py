# Notebook: etil_macro
# Camada: Silver — Tratamento
# Saída: Parquet no ADLS Gen2

# Databricks notebook source
import pandas as pd
import requests
import io
from azure.storage.blob import BlobServiceClient
from io import StringIO
import os
import time
import  base64
import datetime as dt
from datetime import datetime
import shutil

# COMMAND ----------

def salvarDataLake(DF, NOME_CONTAINER, NOME_ARQUIVO):     
    # Puxa a string de conexão do cofre do Databricks
    CONNECTION_STRING = dbutils.secrets.get(scope="escopo", key="AZURECONNSTRING")

    try:
        print(f"Conectando ao Azure para salvar {NOME_ARQUIVO}...")
        blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
        
        # Salvar como Parquet em memória
        output = io.BytesIO()
        DF.to_parquet(output, index=False, engine='pyarrow')
        dados_parquet = output.getvalue()
        
        # Garantir extensão .parquet no nome
        caminho_blob = f"{NOME_ARQUIVO}.parquet" if not NOME_ARQUIVO.endswith('.parquet') else NOME_ARQUIVO
        blob_client = blob_service_client.get_blob_client(container=NOME_CONTAINER, blob=caminho_blob)
        blob_client.upload_blob(dados_parquet, overwrite=True)
        
        print(f"✅ Sucesso! Arquivo salvo em: {NOME_CONTAINER}/{caminho_blob}")
    except Exception as e:
        print(f"❌ Erro ao salvar no Azure: {e}")

# COMMAND ----------

CONNECTION_STRING = dbutils.secrets.get(scope="escopo", key="AZURECONNSTRING")

blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)

client_silver = blob_service_client.get_container_client("silver")
client_bronze = blob_service_client.get_container_client("bronze")

pasta_base = 'dados_macroeconomicos/'

# COMMAND ----------

data = datetime.today()

# 1. MAPEAMENTO BRONZE
try:
    ano = '2026'
    mes = ('0' + str(data.month))[-2:]
    dia =  data.day
    print(f"Buscando arquivos em: bronze/{pasta_base}...")
    blobs_bronze = list(client_bronze.list_blobs(name_starts_with=pasta_base))
    arquivos_bronze = [(x.name[:-4].split('/')[-1], x) for x in blobs_bronze if x.name.endswith(f'{ano}-{mes}-{dia}.csv')]
    blob_br = arquivos_bronze[0][1]
    nome_br = arquivos_bronze[0][0]

    #Criar Tabela Bronze
    dados_bronze = client_bronze.get_blob_client(blob_br).download_blob().readall()
    df_bronze = pd.read_csv(io.BytesIO(dados_bronze), sep=';', low_memory=False, dtype=str)
except Exception as e:
    print(f"Erro ao mapear Bronze: {e}")
    arquivos_bronze = {}

# COMMAND ----------

# 2. MAPEAMENTO SILVER
try:
    print(f"Buscando arquivos em: silver/{pasta_base}...")
    blobs_silver = list(client_silver.list_blobs(name_starts_with=pasta_base))
    arquivos_silver = [(x.name[:-8].split('/')[-1], x) for x in blobs_silver]

    dados_silver = client_silver.get_blob_client(arquivos_silver[0][1]).download_blob().readall()
    df_silver = pd.read_parquet(io.BytesIO(dados_silver))
except Exception as e:
    print(f"Erro ao mapear Silver: {e}")
    arquivos_silver = {}

# COMMAND ----------

# Juntar Tabelas 
df_resultado = None
try:
    if df_silver is not None and not df_silver.empty:
        df_resultado = pd.concat([df_bronze, df_silver], axis=0, ignore_index=True)
    else:
        df_resultado = df_bronze.copy()
except Exception as e:
    print(f"❌ Erro ao concatenar tabelas: {e}")

if df_resultado is not None:
    salvarDataLake(
        df_resultado,
        'silver/dados_macroeconomicos',
        'consolidade'
    )
else:
    print("⚠️ df_resultado está vazio, nada foi salvo.")

# COMMAND ----------



# COMMAND ----------

