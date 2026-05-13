# Notebook: 03_recomendacao_pme
# Camada: Gold — Radar FIDC
#
# Matching PME × FIDC.
# Antes: filtrava só por risco_tolerado → segmentos diferentes recebiam os mesmos 3 FIDCs.
# Agora: filtra por (a) risco_tolerado e (b) keywords aderentes ao segmento da PME no
# nome/tipo do FIDC. Cada segmento recebe top-3 distintos.

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

# COMMAND ----------

# Perfis de PME com keywords usadas para casar com nome/tipo do FIDC
PERFIS_PME = [
    {
        "perfil_id": "PME001",
        "segmento": "Varejo",
        "necessidade": "Antecipação de recebíveis",
        "prazo_preferido": "curto",
        "risco_tolerado": "baixo",
        "descricao": "Varejista que precisa de capital de giro rápido",
        "keywords": [
            "varejo", "recebiv", "consig", "cartao", "cartão", "boleto",
            "credito privado", "crédito privado", "consignado", "comerc",
        ],
    },
    {
        "perfil_id": "PME002",
        "segmento": "Agronegocio",
        "necessidade": "Capital de giro safra",
        "prazo_preferido": "medio",
        "risco_tolerado": "medio",
        "descricao": "Produtor rural com necessidade sazonal de capital",
        "keywords": [
            "agro", "fiagro", "rural", "agric", "agribusiness", "safra",
            "agropec", "fert", "cooperativa",
        ],
    },
    {
        "perfil_id": "PME003",
        "segmento": "Servicos",
        "necessidade": "Capital de giro operacional",
        "prazo_preferido": "curto",
        "risco_tolerado": "baixo",
        "descricao": "Prestadora de serviços com contratos recorrentes",
        "keywords": [
            "servic", "serviç", "consultor", "contrato", "duplicata",
            "fatura", "multissetor", "multisetor",
        ],
    },
    {
        "perfil_id": "PME004",
        "segmento": "Industria",
        "necessidade": "Financiamento de produção",
        "prazo_preferido": "longo",
        "risco_tolerado": "alto",
        "descricao": "Indústria buscando financiamento de ciclo produtivo",
        "keywords": [
            "industr", "indústr", "manufat", "energia", "infra",
            "estrutur", "produc", "produç", "fornecedor",
        ],
    },
    {
        "perfil_id": "PME005",
        "segmento": "Tecnologia",
        "necessidade": "Expansão e crescimento",
        "prazo_preferido": "medio",
        "risco_tolerado": "alto",
        "descricao": "Startup buscando alternativa ao crédito bancário",
        "keywords": [
            "tech", "tecnolog", "fintech", "credit ", "crédit ", "saas",
            "digital", "venture", "pay", "lift",
        ],
    },
]

TOP_K = 3
# Mínimo de FIDCs que precisam casar com as keywords para considerar matching real.
# Abaixo disso, recorre ao top global filtrado por risco — para evitar segmentos vazios.
MIN_MATCHES = 8


# COMMAND ----------

def filtrar_por_risco(df: pd.DataFrame, risco: str) -> pd.DataFrame:
    if risco == "baixo":
        classes = ["A", "B"]
    elif risco == "medio":
        classes = ["A", "B", "C"]
    else:
        classes = ["A", "B", "C", "D"]
    out = df[df["classificacao"].isin(classes)]
    return out if len(out) > 0 else df


def matching_segmento(df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    """Filtra FIDCs cujo nome_fundo ou tipo_fundo contém alguma keyword."""
    if not keywords:
        return df

    def has_kw(row) -> bool:
        nome = str(row.get("nome_fundo", "")).lower()
        tipo = str(row.get("tipo_fundo", "")).lower()
        texto = f"{nome} {tipo}"
        return any(kw in texto for kw in keywords)

    return df[df.apply(has_kw, axis=1)]


# COMMAND ----------

try:
    data = gold.get_blob_client("score_fidc/score_fidc.parquet").download_blob().readall()
    df_score = pd.read_parquet(io.BytesIO(data))
    print(f"FIDCs com score: {len(df_score)}")
except Exception as e:
    print(f"Erro lendo gold/score_fidc: {e}")
    df_score = pd.DataFrame()

if df_score.empty:
    raise SystemExit("Sem scores para gerar recomendações.")

df_sorted = df_score.sort_values("score_final", ascending=False).reset_index(drop=True)

# COMMAND ----------

recomendacoes = []

for perfil in PERFIS_PME:
    df_risco = filtrar_por_risco(df_sorted, perfil["risco_tolerado"])
    df_match = matching_segmento(df_risco, perfil["keywords"])

    if len(df_match) < MIN_MATCHES:
        print(
            f"  {perfil['segmento']}: somente {len(df_match)} matches por keyword — "
            "fallback para top do risco."
        )
        candidatos = df_risco.head(TOP_K)
        origem_match = "ranking_geral"
    else:
        candidatos = df_match.head(TOP_K)
        origem_match = "segmento_aderente"

    for rank, (_, fidc) in enumerate(candidatos.iterrows(), 1):
        score = round(float(fidc["score_final"]), 1)
        ret_medio = float(fidc.get("retorno_medio", 0) or 0)
        classe = fidc["classificacao"]
        nome = str(fidc.get("nome_fundo", "N/A"))
        tipo_fundo = str(fidc.get("tipo_fundo", "N/A"))

        justificativa = (
            f"Recomendação #{rank} para {perfil['segmento']} ({perfil['necessidade']}): "
            f"{nome} — score {score} (classe {classe}), retorno médio histórico {ret_medio:.4f}. "
            f"Match: {origem_match}. Indexador inferido: {fidc.get('indexador_inferido', 'N/A')}."
        )

        recomendacoes.append({
            "perfil_id": perfil["perfil_id"],
            "segmento": perfil["segmento"],
            "necessidade": perfil["necessidade"],
            "risco_tolerado": perfil["risco_tolerado"],
            "rank_recomendacao": rank,
            "cnpj_fundo": str(fidc.get("cnpj_fundo", "")),
            "nome_fundo": nome,
            "tipo_fundo": tipo_fundo,
            "gestor": str(fidc.get("gestor", "N/A")),
            "score_final": score,
            "classificacao": classe,
            "retorno_esperado_12m": round(ret_medio, 6),
            "origem_match": origem_match,
            "justificativa": justificativa,
            "data_recomendacao": datetime.today().strftime("%Y-%m-%d"),
        })

df_rec = pd.DataFrame(recomendacoes)
print(f"\n{len(df_rec)} recomendações geradas")
print(df_rec[["segmento", "rank_recomendacao", "nome_fundo", "score_final", "classificacao", "origem_match"]].to_string())

# COMMAND ----------

buf = io.BytesIO()
df_rec.to_parquet(buf, index=False, engine="pyarrow")
try:
    gold.create_container()
except Exception:
    pass
gold.get_blob_client("recomendacao_pme/recomendacao.parquet").upload_blob(buf.getvalue(), overwrite=True)
print("\nSalvo: gold/recomendacao_pme/recomendacao.parquet")
