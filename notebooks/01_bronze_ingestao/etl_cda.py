# Notebook: etl_fidc_cda_mensal
# Camada: Bronze — Ingestão
# Fonte: ANBIMA/BCB/CVM

# Databricks notebook source
# MAGIC %pip install azure-storage-blob xlrd lxml html5lib

# COMMAND ----------

import requests
import os
import pandas as pd
from io import StringIO
from azure.storage.blob import BlobServiceClient
import shutil
from datetime import datetime 
import zipfile

# COMMAND ----------

def salvarDataLake(DF, NOME_CONTAINER, CAMINHO_BLOB, CONEXAO):
    try:
        blob_service_client = BlobServiceClient.from_connection_string(CONEXAO)
        output = StringIO()
        DF.to_csv(output, index=False, sep=";")
        dados_csv = output.getvalue()
        
        blob_client = blob_service_client.get_blob_client(container=NOME_CONTAINER, blob=CAMINHO_BLOB)
        blob_client.upload_blob(dados_csv, overwrite=True)
        print(f"Upload OK: {CAMINHO_BLOB}")
    except Exception as e:
        print(f"Erro no upload: {e}")
        raise e

# COMMAND ----------

ano = dbutils.widgets.get("ano")
mes = dbutils.widgets.get("mes")

dia = datetime.today().strftime("%d")

CONNECTION_STRING = dbutils.secrets.get(scope="escopo", key="AZURECONNSTRING")

print(f"Processando CDA referência: {ano}/{mes} (Data de ingestão: dia {dia})")

try:

    url = f"https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_{ano}{mes}.zip"
    nome_zip = f'cda_fi_{ano}_{mes}.zip'
    
    # Criando uma pasta temporária com nome único para não dar conflito
    pasta_destino = f"{os.getcwd()}/temp_cda_{ano}_{mes}"

    print(f"Baixando: {url}")
    response = requests.get(url)
    response.raise_for_status()

    with open(nome_zip, 'wb') as f:
        f.write(response.content)

    # Extraindo com Python nativo
    os.makedirs(pasta_destino, exist_ok=True)
    with zipfile.ZipFile(nome_zip, 'r') as zip_ref:
        zip_ref.extractall(pasta_destino)
        
    os.remove(nome_zip)

    arquivos_encontrados = False
    
    for arquivo in os.listdir(pasta_destino):
        if arquivo.endswith(".csv") or arquivo.endswith(".txt"):
            arquivos_encontrados = True
            caminho_local = os.path.join(pasta_destino, arquivo)
            
            print(f"Lendo arquivo: {arquivo}")
            # low_memory=False evita que o Pandas trave ao ler as tabelas gigantes da CDA
            df_temp = pd.read_csv(caminho_local, sep=";", encoding="latin1", low_memory=False, quoting=3)            
            
            # Remove a extensão original (.txt ou .csv) para garantir que salvaremos limpo
            nome_sem_extensao = os.path.splitext(arquivo)[0]
            
            # 2. Montando a hierarquia perfeita: cda/YYYY/MM/DD/arquivo.csv
            caminho_blob = f"cda/{ano}/{mes}/{nome_sem_extensao}.csv"
            
            # Chamando a função de salvamento
            salvarDataLake(df_temp, 'bronze', caminho_blob, CONNECTION_STRING)

    if not arquivos_encontrados:
        print("Nenhum CSV/TXT encontrado no ZIP da CDA.")

    # Limpando o ambiente do Databricks para não lotar o disco
    shutil.rmtree(pasta_destino)
    print("Processo concluído e arquivos temporários apagados com sucesso!")

except Exception as e:
    print(f"FALHA GERAL: {e}")
    raise e

# COMMAND ----------

