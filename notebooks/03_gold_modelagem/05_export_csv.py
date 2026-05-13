# Notebook: 05_export_csv
# Camada: Gold — Radar FIDC
#
# Exporta os parquets da Gold como CSVs em `gold/powerbi/` para consumo direto
# pelo Power BI Desktop e pelo script de geração do dashboard HTML.

import io
import os
import sys

import pandas as pd
from azure.storage.blob import BlobServiceClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


CONNECTION_STRING = azure_connection_string()
blob_svc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
gold = blob_svc.get_container_client("gold")


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


EXPORTS = [
    ("score_fidc/score_fidc.parquet", "powerbi/score_fidc.csv"),
    ("recomendacao_pme/recomendacao.parquet", "powerbi/recomendacao_pme.csv"),
    ("indicadores_macro/indicadores.parquet", "powerbi/indicadores_macro.csv"),
    ("dashboard_resumo/ranking_fidcs.parquet", "powerbi/ranking_fidcs.csv"),
    ("dashboard_resumo/dashboard_master.parquet", "powerbi/dashboard_master.csv"),
]

for src, dst in EXPORTS:
    df = ler(src)
    if not df.empty:
        salvar_csv(df, dst)

print("\nCSVs exportados para gold/powerbi/")
