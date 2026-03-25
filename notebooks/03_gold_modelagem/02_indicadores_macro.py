# Notebook: 02_indicadores_macro
# Camada: Gold — Radar FIDC
# Executar via: Databricks Workspace

import os
# Databricks notebook source
# RADAR FIDC — 02: Indicadores Macro
import pandas as pd, io
from azure.storage.blob import BlobServiceClient
from datetime import datetime
CONNECTION_STRING = os.environ["AZURE_CONNECTION_STRING"]
blob_svc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
silver = blob_svc.get_container_client("silver")
gold   = blob_svc.get_container_client("gold")

# COMMAND ----------

df_macro = pd.DataFrame()
blobs = [b for b in silver.list_blobs(name_starts_with="dados_macroeconomicos/") if b.name.endswith(".parquet")]
print(f"Arquivos macro: {len(blobs)}")
for b in blobs:
    try:
        d = silver.get_blob_client(b.name).download_blob().readall()
        df_tmp = pd.read_parquet(io.BytesIO(d))
        df_macro = pd.concat([df_macro, df_tmp], ignore_index=True)
        print(f"  {b.name}: {len(df_tmp)} linhas | cols: {list(df_tmp.columns)[:10]}")
    except Exception as e:
        print(f"  Erro: {e}")

# COMMAND ----------

ind = {"selic_atual": 14.75, "ipca_12m": 5.06, "cdi_atual": 14.65,
        "selic_projetada_12m": 14.50, "ipca_projetado_12m": 5.50}

if len(df_macro) > 0:
    for col in df_macro.columns:
        if "selic" in col.lower():
            v = pd.to_numeric(df_macro[col], errors="coerce").dropna()
            if len(v): ind["selic_atual"] = round(float(v.iloc[-1]), 4)
        if "ipca" in col.lower():
            v = pd.to_numeric(df_macro[col], errors="coerce").dropna()
            if len(v): ind["ipca_12m"] = round(float(v.tail(12).sum()), 4)

ind["data_ref"] = datetime.today().strftime("%Y-%m-%d")
s = ind["selic_atual"]
if s >= 13:
    ind["cenario_macro"] = "favoravel_posfixado"
    ind["descricao_cenario"] = f"SELIC {s}% favorece FIDCs pos-fixados (CDI+). Alta remuneracao relativa."
elif s >= 10:
    ind["cenario_macro"] = "neutro"
    ind["descricao_cenario"] = f"SELIC {s}% neutro. Diversificacao recomendada."
else:
    ind["cenario_macro"] = "favoravel_prefixado"
    ind["descricao_cenario"] = f"SELIC {s}% baixo. FIDCs prefixados com melhor relacao risco/retorno."

print(f"Indicadores: {ind}")

# COMMAND ----------

try: gold.create_container()
except: pass
buf = io.BytesIO()
pd.DataFrame([ind]).to_parquet(buf, index=False, engine="pyarrow")
gold.get_blob_client("indicadores_macro/indicadores.parquet").upload_blob(buf.getvalue(), overwrite=True)
print("Indicadores salvos: gold/indicadores_macro/indicadores.parquet")

# Atualizar score_macro no score_fidc
try:
    d2 = gold.get_blob_client("score_fidc/score_fidc.parquet").download_blob().readall()
    df_sc = pd.read_parquet(io.BytesIO(d2))
    df_sc["score_macro"] = 80.0 if ind["cenario_macro"]=="favoravel_posfixado" else 60.0 if ind["cenario_macro"]=="neutro" else 70.0
    df_sc["score_final"] = (df_sc["score_retorno"]*0.40 + df_sc["score_risco"]*0.30 +
                            df_sc["score_macro"]*0.20  + df_sc["score_liquidez"]*0.10).round(1)
    df_sc["classificacao"] = df_sc["score_final"].apply(lambda s: "A" if s>=80 else "B" if s>=60 else "C" if s>=40 else "D")
    buf2 = io.BytesIO(); df_sc.to_parquet(buf2, index=False, engine="pyarrow")
    gold.get_blob_client("score_fidc/score_fidc.parquet").upload_blob(buf2.getvalue(), overwrite=True)
    print(f"Score atualizado com macro: {df_sc.groupby('classificacao').size().to_dict()}")
except Exception as e:
    print(f"Aviso: nao foi possivel atualizar score macro: {e}")
