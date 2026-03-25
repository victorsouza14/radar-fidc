# Notebook: 03_recomendacao_pme
# Camada: Gold — Radar FIDC
# Executar via: Databricks Workspace

import os
# Databricks notebook source
# RADAR FIDC — 03: Matching PME x FIDC
import pandas as pd, numpy as np, io
from azure.storage.blob import BlobServiceClient
from datetime import datetime

CONNECTION_STRING = os.environ["AZURE_CONNECTION_STRING"]
blob_svc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
gold = blob_svc.get_container_client("gold")

# COMMAND ----------

# Ler score FIDCs
try:
    data = gold.get_blob_client("score_fidc/score_fidc.parquet").download_blob().readall()
    df_score = pd.read_parquet(io.BytesIO(data))
    print(f"FIDCs carregados: {len(df_score)}")
    print(f"Colunas: {list(df_score.columns)}")
except Exception as e:
    print(f"Erro ao ler score: {e}")
    df_score = pd.DataFrame()

# COMMAND ----------

perfis_pme = [
    {"perfil_id": "PME001", "segmento": "Varejo", "necessidade": "Antecipacao de recebiveis", "prazo_preferido": "curto", "risco_tolerado": "baixo", "descricao": "Varejista que precisa de capital de giro rapido"},
    {"perfil_id": "PME002", "segmento": "Agronegocio", "necessidade": "Capital de giro safra", "prazo_preferido": "medio", "risco_tolerado": "medio", "descricao": "Produtor rural com necessidade sazonal de capital"},
    {"perfil_id": "PME003", "segmento": "Servicos", "necessidade": "Capital de giro operacional", "prazo_preferido": "curto", "risco_tolerado": "baixo", "descricao": "Prestadora de servicos com contratos recorrentes"},
    {"perfil_id": "PME004", "segmento": "Industria", "necessidade": "Financiamento de producao", "prazo_preferido": "longo", "risco_tolerado": "alto", "descricao": "Industria buscando financiamento de ciclo produtivo"},
    {"perfil_id": "PME005", "segmento": "Tecnologia", "necessidade": "Expansao e crescimento", "prazo_preferido": "medio", "risco_tolerado": "alto", "descricao": "Startup buscando alternativa ao credito bancario"},
]

print(f"Perfis PME definidos: {len(perfis_pme)}")

# COMMAND ----------

recomendacoes = []

if len(df_score) > 0:
    df_sorted = df_score.sort_values("score_final", ascending=False).reset_index(drop=True)
    
    for perfil in perfis_pme:
        risco = perfil["risco_tolerado"]
        if risco == "baixo":
            df_filtrado = df_sorted[df_sorted["classificacao"].isin(["A", "B"])]
        elif risco == "medio":
            df_filtrado = df_sorted[df_sorted["classificacao"].isin(["A", "B", "C"])]
        else:
            df_filtrado = df_sorted
        
        if len(df_filtrado) == 0:
            df_filtrado = df_sorted
        
        top3 = df_filtrado.head(3)
        
        for rank, (_, fidc) in enumerate(top3.iterrows(), 1):
            score = round(float(fidc["score_final"]), 1)
            ret = round(float(fidc.get("retorno_medio", 0)), 4)
            classe = fidc["classificacao"]
            nome = str(fidc.get("nome_fundo", "N/A"))
            
            justificativa = (
                f"Recomendacao #{rank} para {perfil['segmento']}: "
                f"FIDC {nome} com score {score} (classe {classe}), "
                f"retorno medio {ret:.2%}. Adequado para {perfil['necessidade']}."
            )
            
            recomendacoes.append({
                "perfil_id": perfil["perfil_id"],
                "segmento": perfil["segmento"],
                "necessidade": perfil["necessidade"],
                "risco_tolerado": risco,
                "rank_recomendacao": rank,
                "cnpj_fundo": str(fidc.get("cnpj_fundo", "")),
                "nome_fundo": nome,
                "tipo_fundo": str(fidc.get("tipo_fundo", "N/A")),
                "gestor": str(fidc.get("gestor", "N/A")),
                "score_final": score,
                "classificacao": classe,
                "retorno_esperado_12m": ret,
                "justificativa": justificativa,
                "data_recomendacao": datetime.today().strftime("%Y-%m-%d"),
            })
    
    df_rec = pd.DataFrame(recomendacoes)
    print(f"\n{len(df_rec)} recomendacoes geradas")
    print(df_rec[["segmento","rank_recomendacao","nome_fundo","score_final","classificacao"]].to_string())
else:
    print("Sem dados de score. Usando exemplos...")
    df_rec = pd.DataFrame([{
        "perfil_id": f"PME{(i//3)+1:03d}",
        "segmento": ["Varejo","Agronegocio","Servicos","Industria","Tecnologia"][i//3],
        "necessidade": "Capital de giro",
        "risco_tolerado": "medio",
        "rank_recomendacao": (i % 3) + 1,
        "cnpj_fundo": f"00.000.{(i%3)+1:03d}/0001-00",
        "nome_fundo": f"FIDC Exemplo {(i%3)+1}",
        "tipo_fundo": "Multicedente",
        "gestor": "Gestora Exemplo",
        "score_final": round(85 - (i%3)*8.0, 1),
        "classificacao": "A" if (i%3)==0 else "B",
        "retorno_esperado_12m": 0.015 - (i%3)*0.001,
        "justificativa": f"FIDC recomendado por score elevado.",
        "data_recomendacao": datetime.today().strftime("%Y-%m-%d"),
    } for i in range(15)])

# COMMAND ----------

buf = io.BytesIO()
df_rec.to_parquet(buf, index=False, engine="pyarrow")
try: gold.create_container()
except: pass
gold.get_blob_client("recomendacao_pme/recomendacao.parquet").upload_blob(buf.getvalue(), overwrite=True)
print("\nRecomendacoes salvas em gold/recomendacao_pme/recomendacao.parquet")
