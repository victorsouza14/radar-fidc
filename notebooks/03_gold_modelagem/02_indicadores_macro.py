# Notebook: 02_indicadores_macro
# Camada: Gold — Radar FIDC
#
# Consolida indicadores macroeconômicos atuais (SELIC, IPCA, CDI) e projeções 12m
# em uma única tabela `gold/indicadores_macro/indicadores.parquet`.
#
# Não altera o score por FIDC — o ajuste macro é responsabilidade do 01_score_fidc.

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
silver = blob_svc.get_container_client("silver")
gold = blob_svc.get_container_client("gold")

# Fallback usado APENAS se a Silver estiver indisponível (não para mascarar erro).
FALLBACK = {
    "selic_atual": None,
    "ipca_12m": None,
    "cdi_atual": None,
    "selic_projetada_12m": None,
    "ipca_projetado_12m": None,
}

# COMMAND ----------

df_macro = pd.DataFrame()
blobs = [
    b for b in silver.list_blobs(name_starts_with="dados_macroeconomicos/")
    if b.name.endswith(".parquet")
]
print(f"Arquivos macro encontrados: {len(blobs)}")
for b in blobs:
    try:
        d = silver.get_blob_client(b.name).download_blob().readall()
        df_tmp = pd.read_parquet(io.BytesIO(d))
        df_macro = pd.concat([df_macro, df_tmp], ignore_index=True)
        print(f"  {b.name}: {len(df_tmp)} linhas")
    except Exception as e:
        print(f"  Erro lendo {b.name}: {e}")


# COMMAND ----------

def ultimo_valor(df, keywords):
    """Pega último valor numérico não-nulo de qualquer coluna cujo nome bata."""
    for col in df.columns:
        if any(k in col.lower() for k in keywords):
            v = pd.to_numeric(df[col], errors="coerce").dropna()
            if not v.empty:
                return float(v.iloc[-1])
    return None


def soma_ultimos_12(df, keywords):
    """Soma das últimas 12 observações (para acumulado IPCA)."""
    for col in df.columns:
        if any(k in col.lower() for k in keywords):
            v = pd.to_numeric(df[col], errors="coerce").dropna()
            if not v.empty:
                return round(float(v.tail(12).sum()), 4)
    return None


ind = dict(FALLBACK)

if not df_macro.empty:
    ind["selic_atual"] = ultimo_valor(df_macro, ["selic_meta", "selic"])
    ind["cdi_atual"] = ultimo_valor(df_macro, ["cdi"])
    ind["ipca_12m"] = soma_ultimos_12(df_macro, ["ipca"])
    # Sem fonte Focus diretamente: aproximação selic_projetada = selic_atual - 50bps
    if ind["selic_atual"] is not None:
        ind["selic_projetada_12m"] = round(ind["selic_atual"] - 0.5, 2)
    if ind["ipca_12m"] is not None:
        ind["ipca_projetado_12m"] = round(ind["ipca_12m"] * 0.9, 2)


# Cenário macroeconômico
def classificar_cenario(selic):
    if selic is None:
        return "indisponivel", "Sem dados macro suficientes."
    if selic >= 13:
        return (
            "favoravel_posfixado",
            f"SELIC {selic:.2f}% favorece FIDCs pós-fixados (CDI+). "
            "Alta remuneração relativa frente à renda fixa tradicional.",
        )
    if selic >= 10:
        return (
            "neutro",
            f"SELIC {selic:.2f}% em patamar neutro. Diversificação recomendada.",
        )
    return (
        "favoravel_prefixado",
        f"SELIC {selic:.2f}% baixa favorece FIDCs pré-fixados, "
        "que travam taxa antes de novas quedas.",
    )


cenario, descricao = classificar_cenario(ind["selic_atual"])
ind["cenario_macro"] = cenario
ind["descricao_cenario"] = descricao
ind["data_ref"] = datetime.today().strftime("%Y-%m-%d")

print("Indicadores macro:")
for k, v in ind.items():
    print(f"  {k}: {v}")

# COMMAND ----------

try:
    gold.create_container()
except Exception:
    pass

buf = io.BytesIO()
pd.DataFrame([ind]).to_parquet(buf, index=False, engine="pyarrow")
gold.get_blob_client("indicadores_macro/indicadores.parquet").upload_blob(buf.getvalue(), overwrite=True)
print("\nSalvo: gold/indicadores_macro/indicadores.parquet")
