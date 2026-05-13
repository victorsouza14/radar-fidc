# Notebook: etl_fidc_cda_mensal
# Camada: Bronze — Ingestão
# Fonte: CVM — CDA (Composição da carteira) mensal

# Databricks notebook source
# MAGIC %pip install azure-storage-blob xlrd lxml html5lib

# COMMAND ----------

import os
import shutil
import sys
import zipfile
from datetime import datetime
from io import StringIO

import pandas as pd
import requests
from azure.storage.blob import BlobServiceClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


# COMMAND ----------

def salvarDataLake(DF, NOME_CONTAINER, CAMINHO_BLOB, conn):
    client = BlobServiceClient.from_connection_string(conn)
    output = StringIO()
    DF.to_csv(output, index=False, sep=";")
    client.get_blob_client(container=NOME_CONTAINER, blob=CAMINHO_BLOB).upload_blob(
        output.getvalue(), overwrite=True
    )
    print(f"Upload OK: {CAMINHO_BLOB} ({len(DF)} linhas)")


# COMMAND ----------

def _get_widget(name: str, default: str | None = None) -> str:
    """Lê widget no Databricks ou env var local (CDA_ANO / CDA_MES)."""
    try:
        from pyspark.dbutils import DBUtils  # type: ignore
        from pyspark.sql import SparkSession  # type: ignore

        dbutils = DBUtils(SparkSession.builder.getOrCreate())
        return dbutils.widgets.get(name)
    except Exception:
        env_key = f"CDA_{name.upper()}"
        val = os.environ.get(env_key, default)
        if not val:
            raise RuntimeError(f"Parâmetro '{name}' não fornecido. Defina {env_key}=...")
        return val


if __name__ == "__main__":
    ano = _get_widget("ano")
    mes = _get_widget("mes").zfill(2)
    dia = datetime.today().strftime("%d")

    conn = azure_connection_string()
    print(f"Processando CDA referência: {ano}/{mes} (ingestão: dia {dia})")

    url = f"https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_{ano}{mes}.zip"
    nome_zip = f"cda_fi_{ano}_{mes}.zip"
    pasta_destino = f"{os.getcwd()}/temp_cda_{ano}_{mes}"

    print(f"Baixando: {url}")
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    try:
        with open(nome_zip, "wb") as f:
            f.write(response.content)

        os.makedirs(pasta_destino, exist_ok=True)
        with zipfile.ZipFile(nome_zip, "r") as zip_ref:
            zip_ref.extractall(pasta_destino)
        os.remove(nome_zip)

        encontrou_arquivo = False
        for arquivo in os.listdir(pasta_destino):
            if not (arquivo.endswith(".csv") or arquivo.endswith(".txt")):
                continue
            encontrou_arquivo = True
            caminho_local = os.path.join(pasta_destino, arquivo)
            print(f"Lendo: {arquivo}")
            # quoting=3 (QUOTE_NONE) é necessário porque alguns arquivos CDA misturam aspas.
            df_temp = pd.read_csv(
                caminho_local, sep=";", encoding="latin1", low_memory=False, quoting=3
            )
            nome_sem_extensao = os.path.splitext(arquivo)[0]
            caminho_blob = f"cda/{ano}/{mes}/{nome_sem_extensao}.csv"
            salvarDataLake(df_temp, "bronze", caminho_blob, conn)

        if not encontrou_arquivo:
            print("Nenhum CSV/TXT encontrado no ZIP da CDA.")
    finally:
        if os.path.exists(pasta_destino):
            shutil.rmtree(pasta_destino, ignore_errors=True)
        if os.path.exists(nome_zip):
            os.remove(nome_zip)
        print("Limpeza concluída.")
