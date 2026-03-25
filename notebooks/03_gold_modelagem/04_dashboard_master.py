# Notebook: 04_dashboard_master
# Camada: Gold — Radar FIDC
# Executar via: Databricks Workspace

import os
# Databricks notebook source
# RADAR FIDC — 04: Dashboard Master para Power BI
import pandas as pd, io
from azure.storage.blob import BlobServiceClient
from datetime import datetime
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

df_score = ler("score_fidc/score_fidc.parquet")
df_rec   = ler("recomendacao_pme/recomendacao.parquet")
df_macro = ler("indicadores_macro/indicadores.parquet")
print(f"Score: {len(df_score)} | Rec: {len(df_rec)} | Macro: {len(df_macro)}")

# COMMAND ----------

try: gold.create_container()
except: pass

# Ranking FIDCS
if len(df_score) > 0:
    df_rank = df_score.copy()
    df_rank["rank_geral"] = df_rank["score_final"].rank(ascending=False).astype(int)
    if len(df_macro) > 0:
        df_rank["selic_atual"]   = df_macro["selic_atual"].iloc[0]
        df_rank["cenario_macro"] = df_macro["cenario_macro"].iloc[0]
    buf = io.BytesIO(); df_rank.to_parquet(buf, index=False, engine="pyarrow")
    gold.get_blob_client("dashboard_resumo/ranking_fidcs.parquet").upload_blob(buf.getvalue(), overwrite=True)
    print(f"Ranking salvo: {len(df_rank)} FIDCs")

# Master
if len(df_score) > 0 and len(df_rec) > 0:
    merge_cols = [c for c in ["cnpj_fundo","score_retorno","score_risco","score_macro","score_liquidez","retorno_medio","volatilidade"] if c in df_score.columns]
    df_master = df_rec.merge(df_score[merge_cols], on="cnpj_fundo", how="left")
    if len(df_macro) > 0:
        for col in ["selic_atual","ipca_12m","cdi_atual","cenario_macro","descricao_cenario"]:
            if col in df_macro.columns:
                df_master[col] = df_macro[col].iloc[0]
    df_master["data_geracao"] = datetime.today().strftime("%Y-%m-%d")
    buf2 = io.BytesIO(); df_master.to_parquet(buf2, index=False, engine="pyarrow")
    gold.get_blob_client("dashboard_resumo/dashboard_master.parquet").upload_blob(buf2.getvalue(), overwrite=True)
    print(f"Master salvo: {len(df_master)} linhas | {len(df_master.columns)} colunas")
    for col in df_master.columns:
        print(f"  {col}: {df_master[col].dtype}")
