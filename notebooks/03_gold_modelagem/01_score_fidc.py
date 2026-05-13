# Notebook: 01_score_fidc
# Camada: Gold — Radar FIDC
#
# Calcula score 0-100 por FIDC usando normalização por percentil (rank-based).
# Por que percentil: a normalização min-max anterior centrava a distribuição em ~50,
# fazendo TODOS os FIDCs caírem em classe C. Percentil garante distribuição A/B/C/D
# realista e robusta a outliers.

import io
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from azure.storage.blob import BlobServiceClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


CONNECTION_STRING = azure_connection_string()
blob_svc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
silver = blob_svc.get_container_client("silver")
gold = blob_svc.get_container_client("gold")

# Pesos do score final (devem somar 1.0)
W_RETORNO = 0.40
W_RISCO = 0.30
W_MACRO = 0.20
W_LIQUIDEZ = 0.10

# Mínimo de observações para um FIDC entrar no ranking
MIN_OBS = 6

# Janela de cálculo da rentabilidade
JANELA_MESES = 12

# Cap de volatilidade pelo percentil 99 (evita um único fundo extremo distorcer escala)
VOLATILIDADE_PERCENTIL_CAP = 0.99

# COMMAND ----------


def ler_parquet(client, path):
    try:
        d = client.get_blob_client(path).download_blob().readall()
        return pd.read_parquet(io.BytesIO(d))
    except Exception as e:
        print(f"Erro ao ler {path}: {e}")
        return pd.DataFrame()


def find_col(df, keys):
    """Procura primeira coluna cujo nome contém uma das keys (case-insensitive)."""
    for k in keys:
        for c in df.columns:
            if k.lower() in c.lower():
                return c
    return None


def percentile_score(series: pd.Series, ascending: bool = True) -> pd.Series:
    """Converte uma série em score 0-100 baseado em ranking percentil.

    ascending=True  → valores maiores recebem score maior (retorno, liquidez)
    ascending=False → valores menores recebem score maior (volatilidade)
    """
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() == 0:
        return pd.Series([50.0] * len(series), index=series.index)
    rank = s.rank(method="average", pct=True, ascending=ascending, na_option="bottom")
    return (rank * 100).round(2)


def classificar(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


# COMMAND ----------

print("Lendo Silver...")
df_serie = ler_parquet(silver, "anbima/serie_historica_fidc.parquet")
df_fundos = ler_parquet(silver, "anbima/fundos_v2_fidc.parquet")
df_cadastro = ler_parquet(silver, "anbima/dados_cadastrais_fidc.parquet")
df_macro = ler_parquet(silver, "dados_macroeconomicos/consolidado.parquet")

print(f"  serie_historica: {len(df_serie)} linhas")
print(f"  fundos_v2:       {len(df_fundos)} linhas")
print(f"  cadastrais:      {len(df_cadastro)} linhas")
print(f"  macro:           {len(df_macro)} linhas")

# COMMAND ----------

# Identificar colunas
cnpj_s = find_col(df_serie, ["identificador", "cnpj", "codigo_fundo", "fundo"])
rent_c = find_col(df_serie, ["rentab", "retorno", "cota", "vl_quota", "rendimento"])
data_c = find_col(df_serie, ["data", "dt_", "date", "competencia", "referencia"])
print(f"\nColunas serie_historica: cnpj={cnpj_s}, rent={rent_c}, data={data_c}")

# COMMAND ----------

if cnpj_s and rent_c and len(df_serie) > 0:
    cols = [cnpj_s, rent_c] + ([data_c] if data_c else [])
    df = df_serie[cols].copy()
    df[rent_c] = pd.to_numeric(df[rent_c], errors="coerce")
    df = df.dropna(subset=[rent_c])

    # Filtrar últimos 12 meses se houver coluna de data
    if data_c:
        df[data_c] = pd.to_datetime(df[data_c], errors="coerce")
        valid_dates = df[data_c].notna()
        if valid_dates.any():
            cut = df.loc[valid_dates, data_c].max() - pd.DateOffset(months=JANELA_MESES)
            df = df[df[data_c] >= cut]
            print(f"Filtro {JANELA_MESES}m: {len(df)} observações")

    # Agregação por FIDC: retorno médio, vol, liquidez, retorno mínimo
    grp = df.groupby(cnpj_s)[rent_c].agg(["mean", "std", "count", "min"]).reset_index()
    grp.columns = [cnpj_s, "retorno_medio", "volatilidade", "n_obs", "retorno_min"]
    grp = grp[grp["n_obs"] >= MIN_OBS].copy()
    print(f"FIDCs com >= {MIN_OBS} observações: {len(grp)}")

    # Cap de volatilidade pelo percentil 99 (não pelo absoluto 100)
    if grp["volatilidade"].notna().any():
        cap = grp["volatilidade"].quantile(VOLATILIDADE_PERCENTIL_CAP)
        if pd.notna(cap) and cap > 0:
            grp["volatilidade"] = grp["volatilidade"].clip(upper=cap)

    grp["volatilidade"] = grp["volatilidade"].fillna(grp["volatilidade"].median())

    # Scores por componente
    grp["score_retorno"] = percentile_score(grp["retorno_medio"], ascending=True)
    grp["score_risco"] = percentile_score(grp["volatilidade"], ascending=False)
    grp["score_liquidez"] = percentile_score(grp["n_obs"].astype(float), ascending=True)
    df_scores = grp.rename(columns={cnpj_s: "cnpj_fundo"})

else:
    print("AVISO: sem dados de rentabilidade utilizáveis. Pipeline encerrando sem gravar.")
    raise SystemExit(0)

# COMMAND ----------

# Score Macro variável por tipo de fundo (heurística)
# - Cenário pós-fixado (SELIC alta): fundos CDI+/pós ganham mais
# - Cenário pré-fixado (SELIC baixa): fundos pré ganham mais
# - Sem info de tipo → score macro = 50 (neutro)
def detectar_tipo_indexador(nome: str) -> str:
    if not isinstance(nome, str):
        return "indefinido"
    n = nome.lower()
    if any(k in n for k in ["cdi", "pos-fix", "pós-fix", "posfix", "pósfix"]):
        return "posfixado"
    if any(k in n for k in ["pre-fix", "pré-fix", "prefix", "préfix", "ipca+"]):
        return "prefixado"
    return "indefinido"


# Selic atual (preferência: macro consolidado, depois Focus, depois fallback 13.5)
def selic_atual_from_macro(df_macro) -> float:
    for col in df_macro.columns:
        if "selic" in col.lower():
            v = pd.to_numeric(df_macro[col], errors="coerce").dropna()
            if not v.empty:
                return float(v.iloc[-1])
    return 13.5


selic = selic_atual_from_macro(df_macro) if not df_macro.empty else 13.5

if selic >= 13:
    cenario, score_pos, score_pre = "favoravel_posfixado", 85, 45
elif selic >= 10:
    cenario, score_pos, score_pre = "neutro", 60, 55
else:
    cenario, score_pos, score_pre = "favoravel_prefixado", 45, 80

# COMMAND ----------

# Enriquecer com nome/tipo/gestor a partir do cadastro de fundos
cnpj_f = find_col(df_fundos, ["identificador", "cnpj", "codigo_fundo"])
nome_c = find_col(df_fundos, ["nome_comercial", "razao_social", "denom", "nome"])
tipo_c = find_col(df_fundos, ["tipo_fundo", "tipo", "classe"])
gest_c = find_col(df_fundos, ["gestor", "administr"])

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
    df_result["nome_fundo"] = "FIDC " + df_result["cnpj_fundo"].astype(str).str[-8:]
    df_result["tipo_fundo"] = "Multicedente"
    df_result["gestor"] = "N/A"

# Score Macro variável por indexador inferido a partir do nome
df_result["indexador_inferido"] = df_result["nome_fundo"].apply(detectar_tipo_indexador)
df_result["score_macro"] = df_result["indexador_inferido"].map(
    {"posfixado": score_pos, "prefixado": score_pre, "indefinido": (score_pos + score_pre) / 2}
).astype(float)

# Score final ponderado
df_result["score_final"] = (
    df_result["score_retorno"] * W_RETORNO
    + df_result["score_risco"] * W_RISCO
    + df_result["score_macro"] * W_MACRO
    + df_result["score_liquidez"] * W_LIQUIDEZ
).round(1)

df_result["classificacao"] = df_result["score_final"].apply(classificar)
df_result["cenario_macro"] = cenario
df_result["selic_referencia"] = selic
df_result["data_calculo"] = datetime.today().strftime("%Y-%m-%d")

print(f"\nTotal FIDCs com score: {len(df_result)}")
print("Distribuição:")
print(df_result.groupby("classificacao").size().to_dict())

# COMMAND ----------

try:
    gold.create_container()
except Exception:
    pass

buf = io.BytesIO()
df_result.to_parquet(buf, index=False, engine="pyarrow")
gold.get_blob_client("score_fidc/score_fidc.parquet").upload_blob(buf.getvalue(), overwrite=True)
print("\nSalvo: gold/score_fidc/score_fidc.parquet")
