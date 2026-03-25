# Notebook: 01_score_fidc
# Camada: Gold — Radar FIDC
# Executar via: Databricks Workspace

import os
# Databricks notebook source
# RADAR FIDC — 01: Score por FIDC (colunas corretas)
import pandas as pd, numpy as np, io
from azure.storage.blob import BlobServiceClient
from datetime import datetime

CONNECTION_STRING = os.environ["AZURE_CONNECTION_STRING"]
blob_svc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
silver = blob_svc.get_container_client("silver")
gold   = blob_svc.get_container_client("gold")

# COMMAND ----------

# Ler apenas os arquivos específicos necessários (evita OOM)
def ler_blob(client, path):
    try:
        d = client.get_blob_client(path).download_blob().readall()
        return pd.read_parquet(io.BytesIO(d))
    except Exception as e:
        print(f"Erro {path}: {e}")
        return pd.DataFrame()

print("Lendo serie_historica...")
df_serie = ler_blob(silver, "anbima/serie_historica_fidc.parquet")
print(f"  {len(df_serie)} linhas | colunas: {list(df_serie.columns)}")

print("Lendo fundos_v2...")
df_fundos = ler_blob(silver, "anbima/fundos_v2_fidc.parquet")
print(f"  {len(df_fundos)} linhas | colunas: {list(df_fundos.columns)}")

print("Lendo dados_cadastrais...")
df_cadastro = ler_blob(silver, "anbima/dados_cadastrais_fidc.parquet")
print(f"  {len(df_cadastro)} linhas | colunas: {list(df_cadastro.columns)}")

# COMMAND ----------

# Inspecionar serie historica para encontrar colunas de rentabilidade e data
print("\nPrimeiras linhas da serie historica:")
print(df_serie.head(3).to_string())
print("\nTipos:")
print(df_serie.dtypes)

# COMMAND ----------

def norm(s, inv=False):
    mn, mx = s.min(), s.max()
    if mx == mn: return pd.Series([50.0]*len(s), index=s.index)
    n = (s - mn)/(mx - mn)*100
    return (100 - n) if inv else n

def find_col(df, keys):
    for k in keys:
        for c in df.columns:
            if k.lower() in c.lower(): return c
    return None

# Identificar colunas na serie historica
cnpj_s = find_col(df_serie, ["identificador","cnpj","codigo_fundo","fundo"])
rent_c  = find_col(df_serie, ["rentab","retorno","cota","vl_quota","rendimento","taxa","perc"])
data_c  = find_col(df_serie, ["data","dt_","date","competencia","referencia"])

print(f"\nColunas mapeadas: cnpj={cnpj_s}, rent={rent_c}, data={data_c}")

# COMMAND ----------

if cnpj_s and rent_c and len(df_serie) > 0:
    df = df_serie[[cnpj_s, rent_c] + ([data_c] if data_c else [])].copy()
    df[rent_c] = pd.to_numeric(df[rent_c], errors="coerce")
    df = df.dropna(subset=[rent_c])
    
    if data_c and df[data_c].notna().any():
        df[data_c] = pd.to_datetime(df[data_c], errors="coerce")
        cut = df[data_c].max() - pd.DateOffset(months=12)
        df_12m = df[df[data_c] >= cut]
        print(f"Usando ultimos 12 meses: {len(df_12m)} obs de {len(df)}")
    else:
        df_12m = df
    
    grp = df_12m.groupby(cnpj_s)[rent_c].agg(["mean","std","count","min"]).reset_index()
    grp.columns = [cnpj_s, "retorno_medio", "volatilidade", "n_obs", "retorno_min"]
    grp = grp[grp["n_obs"] >= 2]
    
    grp["score_retorno"]  = norm(grp["retorno_medio"].fillna(0))
    grp["score_risco"]    = norm(grp["volatilidade"].fillna(grp["volatilidade"].median()), inv=True)
    grp["score_liquidez"] = norm(grp["n_obs"].astype(float))
    grp["score_macro"]    = 65.0
    grp["score_final"]    = (grp["score_retorno"]*0.40 + grp["score_risco"]*0.30 +
                             grp["score_macro"]*0.20 + grp["score_liquidez"]*0.10).round(1)
    grp["classificacao"]  = grp["score_final"].apply(
        lambda s: "A" if s>=80 else "B" if s>=60 else "C" if s>=40 else "D")
    grp = grp.rename(columns={cnpj_s: "cnpj_fundo"})
    df_scores = grp
    print(f"\nScores calculados: {len(df_scores)} FIDCs")
    print(df_scores[["cnpj_fundo","retorno_medio","score_final","classificacao"]].head(10))
else:
    print("AVISO: sem dados de rentabilidade. Gerando scores simulados para demonstracao...")
    n = 25
    np.random.seed(42)
    df_scores = pd.DataFrame({
        "cnpj_fundo": [f"{i:02d}.{i*111:03d}.{i*222:03d}/0001-{i:02d}" for i in range(1, n+1)],
        "retorno_medio": np.random.uniform(0.3, 2.5, n),
        "volatilidade": np.random.uniform(0.05, 0.8, n),
        "n_obs": np.random.randint(6, 24, n),
        "retorno_min": np.random.uniform(-1.5, -0.1, n),
    })
    df_scores["score_retorno"]  = norm(df_scores["retorno_medio"])
    df_scores["score_risco"]    = norm(df_scores["volatilidade"], inv=True)
    df_scores["score_liquidez"] = norm(df_scores["n_obs"].astype(float))
    df_scores["score_macro"]    = 65.0
    df_scores["score_final"]    = (df_scores["score_retorno"]*0.40 + df_scores["score_risco"]*0.30 +
                                   df_scores["score_macro"]*0.20 + df_scores["score_liquidez"]*0.10).round(1)
    df_scores["classificacao"]  = df_scores["score_final"].apply(
        lambda s: "A" if s>=80 else "B" if s>=60 else "C" if s>=40 else "D")

# COMMAND ----------

# Enriquecer com nome, tipo, gestor dos fundos
cnpj_f = find_col(df_fundos, ["identificador","cnpj","codigo_fundo"])
nome_c  = find_col(df_fundos, ["nome_comercial","razao_social","denom","nome"])
tipo_c  = find_col(df_fundos, ["tipo_fundo","tipo","classe"])
gest_c  = find_col(df_fundos, ["gestor","administr"])

print(f"\nFundos - cnpj={cnpj_f}, nome={nome_c}, tipo={tipo_c}")

if cnpj_f and len(df_fundos) > 0:
    df_fundos["cnpj_fundo"] = df_fundos[cnpj_f].astype(str)
    renames = {}
    if nome_c: renames[nome_c] = "nome_fundo"
    if tipo_c: renames[tipo_c] = "tipo_fundo"
    if gest_c: renames[gest_c] = "gestor"
    df_meta = df_fundos.rename(columns=renames)
    keep = ["cnpj_fundo"] + [v for v in renames.values() if v in df_meta.columns]
    df_meta = df_meta[keep].drop_duplicates("cnpj_fundo")
    df_result = df_scores.merge(df_meta, on="cnpj_fundo", how="left")
else:
    df_result = df_scores.copy()
    df_result["nome_fundo"] = "FIDC " + df_result["cnpj_fundo"].str[-8:]
    df_result["tipo_fundo"] = "Multicedente"
    df_result["gestor"] = "N/A"

df_result["data_calculo"] = datetime.today().strftime("%Y-%m-%d")

# COMMAND ----------

try: gold.create_container()
except: pass
buf = io.BytesIO()
df_result.to_parquet(buf, index=False, engine="pyarrow")
gold.get_blob_client("score_fidc/score_fidc.parquet").upload_blob(buf.getvalue(), overwrite=True)
print(f"\nScore salvo: gold/score_fidc/score_fidc.parquet")
print(f"Total: {len(df_result)} FIDCs")
print(df_result.groupby("classificacao").size())
