# Notebook: etl_anbima
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
import shutil
from datetime import datetime

# COMMAND ----------

def salvarDataLake(DF, NOME_CONTAINER, NOME_ARQUIVO):     
    CONNECTION_STRING = os.environ["AZURE_CONNECTION_STRING"]
    
    try:
        print(f"Conectando ao Azure para salvar {NOME_ARQUIVO}...")
        blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
        
        # Salvar como Parquet em memória
        output = io.BytesIO()
        DF.to_parquet(output, index=False, engine='pyarrow')
        dados_parquet = output.getvalue()
        
        # Garantir extensão .parquet no nome
        caminho_blob = f"{NOME_ARQUIVO}.parquet" if not NOME_ARQUIVO.endswith('.parquet') else NOME_ARQUIVO
        
        # Conectar ao container e fazer o upload
        blob_client = blob_service_client.get_blob_client(container=NOME_CONTAINER, blob=caminho_blob)
        blob_client.upload_blob(dados_parquet, overwrite=True)
        
        print(f"✅ Sucesso! Arquivo salvo em: {NOME_CONTAINER}/{caminho_blob}")
        
    except Exception as e:
        print(f"❌ Erro ao salvar no Azure: {e}")

# COMMAND ----------

CONNECTION_STRING = os.environ["AZURE_CONNECTION_STRING"]

blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)

client_silver = blob_service_client.get_container_client("silver")
client_bronze = blob_service_client.get_container_client("bronze")

pasta_base = 'anbima/'

# COMMAND ----------

data = datetime.today()

# 1. MAPEAMENTO BRONZE
try:
    ano = '2026'
    mes = ('0' + str(data.month))[-2:]
    dia =  data.day
    print(f"Buscando arquivos em: bronze/{pasta_base}...")
    blobs_bronze = list(client_bronze.list_blobs(name_starts_with=pasta_base))
    arquivos_bronze = {x.name[:-13].split('/')[-1]: x for x in blobs_bronze if x.name.endswith(f'{ano}{mes}{dia}.csv')}
except Exception as e:
    print(f"Erro ao mapear Bronze: {e}")
    arquivos_bronze = {}

# COMMAND ----------

# 1. MAPEAMENTO SILVER
try:
    print(f"Buscando arquivos em: silver/...")
    blobs_silver = list(client_silver.list_blobs(name_starts_with=pasta_base))
    arquivos_silver = {x.name[:-8].split('/')[-1]: x for x in blobs_silver}
except Exception as e:
    print(f"Erro ao mapear Bronze: {e}")
    arquivos_bronze = {}

# COMMAND ----------

for nome_arquivo, blob_bronze in arquivos_bronze.items():

    print('INICIIANDO: ', nome_arquivo)
    
    df_bronze = df_silver = df = None

    # - DEFINIR A TABELA BRONZE
    dados_bronze = client_bronze.get_blob_client(blob_bronze).download_blob().readall()
    df_bronze = pd.read_csv(io.BytesIO(dados_bronze), sep=';', low_memory=False)

    # - DEFINIR A TABELA SILVER
    blob_silver = arquivos_silver[nome_arquivo]
    dados_silver = client_silver.get_blob_client(blob_silver).download_blob().readall()
    df_silver = pd.read_parquet(io.BytesIO(dados_silver))


    # - JUNTAS AS TABELAS
    if df_bronze is not None and df_silver is not None:
        resultado = pd.concat([df_bronze, df_silver], axis=0).reset_index(drop=True)
        df = resultado.drop_duplicates()
        print("Datasets combinados com sucesso!")
        
        salvarDataLake(
            df,
            'silver/anbima',
            nome_arquivo
        )
    else:
        print("Pulo: Um ou ambos os arquivos não puderam ser processados.")