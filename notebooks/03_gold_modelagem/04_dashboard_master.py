# Notebook: 04_dashboard_master
# Camada: Gold — Radar FIDC
#
# Consolida score_fidc + recomendacao_pme + indicadores_macro em uma única tabela
# `gold/dashboard_resumo/dashboard_master.parquet` consumida por Power BI / dashboard HTML.

import io
import os
import sys
from datetime import datetime

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


df_score = ler("score_fidc/score_fidc.parquet")
df_rec = ler("recomendacao_pme/recomendacao.parquet")
df_macro = ler("indicadores_macro/indicadores.parquet")
print(f"Score: {len(df_score)} | Rec: {len(df_rec)} | Macro: {len(df_macro)}")

# COMMAND ----------

try:
    gold.create_container()
except Exception:
    pass

# Ranking FIDCs (todos com rank_geral)
if len(df_score) > 0:
    df_rank = df_score.copy()
    df_rank["rank_geral"] = df_rank["score_final"].rank(ascending=False, method="min").astype(int)
    if len(df_macro) > 0:
        for col in ["selic_atual", "cdi_atual", "ipca_12m", "cenario_macro"]:
            if col in df_macro.columns:
                df_rank[col] = df_macro[col].iloc[0]
    buf = io.BytesIO()
    df_rank.to_parquet(buf, index=False, engine="pyarrow")
    gold.get_blob_client("dashboard_resumo/ranking_fidcs.parquet").upload_blob(buf.getvalue(), overwrite=True)
    print(f"Ranking salvo: {len(df_rank)} FIDCs")

# Master (recomendacao enriquecida)
if len(df_score) > 0 and len(df_rec) > 0:
    cols_score = [
        c for c in [
            "cnpj_fundo", "score_retorno", "score_risco", "score_macro", "score_liquidez",
            "retorno_medio", "volatilidade", "indexador_inferido",
        ] if c in df_score.columns
    ]
    df_master = df_rec.merge(df_score[cols_score], on="cnpj_fundo", how="left")
    if len(df_macro) > 0:
        for col in ["selic_atual", "ipca_12m", "cdi_atual", "cenario_macro", "descricao_cenario"]:
            if col in df_macro.columns:
                df_master[col] = df_macro[col].iloc[0]
    df_master["data_geracao"] = datetime.today().strftime("%Y-%m-%d")

    buf2 = io.BytesIO()
    df_master.to_parquet(buf2, index=False, engine="pyarrow")
    gold.get_blob_client("dashboard_resumo/dashboard_master.parquet").upload_blob(buf2.getvalue(), overwrite=True)
    print(f"Master salvo: {len(df_master)} linhas | {len(df_master.columns)} colunas")
