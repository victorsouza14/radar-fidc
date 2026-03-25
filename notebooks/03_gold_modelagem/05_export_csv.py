# Notebook: 05_export_csv
# Camada: Gold — Radar FIDC
# Executar via: Databricks Workspace

import os
# Databricks notebook source
# RADAR FIDC — 05: Export CSV para Power BI
import pandas as pd, io
from azure.storage.blob import BlobServiceClient
CONNECTION_STRING = os.environ["AZURE_CONNECTION_STRING"]
blob_svc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
gold = blob_svc.get_container_client("gold")

# COMMAND ----------

def ler(path):
    try:
        d = gold.get_blob_client(path).download_blob().readall()
        return pd.read_parquet(io.BytesIO(d))
    except Exception as e:
        print(f"Erro {path}: {e}")
        return pd.DataFrame()

def salvar_csv(df, path):
    csv = df.to_csv(index=False, encoding="utf-8").encode("utf-8")
    gold.get_blob_client(path).upload_blob(csv, overwrite=True)
    print(f"CSV salvo: {path} ({len(df)} linhas)")

for src, dst in [
    ("score_fidc/score_fidc.parquet",             "powerbi/score_fidc.csv"),
    ("recomendacao_pme/recomendacao.parquet",      "powerbi/recomendacao_pme.csv"),
    ("indicadores_macro/indicadores.parquet",      "powerbi/indicadores_macro.csv"),
    ("dashboard_resumo/ranking_fidcs.parquet",     "powerbi/ranking_fidcs.csv"),
    ("dashboard_resumo/dashboard_master.parquet",  "powerbi/dashboard_master.csv"),
]:
    df = ler(src)
    if len(df) > 0:
        salvar_csv(df, dst)

print("\nCSVs exportados para gold/powerbi/")
print("Acesse via Azure Storage Explorer ou Power BI > Azure Blob Storage")
