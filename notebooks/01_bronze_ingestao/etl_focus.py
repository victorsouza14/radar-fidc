# Notebook: etl_focus
# Camada: Bronze — Ingestão
# Fonte: BCB Olinda — Expectativas Mercado Top 5 Anuais (Boletim Focus)
#
# Substitui as heurísticas `macro.selic_proj` / `macro.ipca_proj` (anteriormente
# calculadas como `selic - 0.5` / `ipca_12m * 0.9`) pelas projeções oficiais do
# Boletim Focus do BCB, mediana das top 5 casas de análise.
#
# Endpoint OData público (não exige autenticação):
#   https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/
#       ExpectativasMercadoTop5Anuais?$filter=Indicador eq 'IPCA' or Indicador eq 'Selic'&$format=json
#
# Saída: `bronze/focus/expectativas_top5_anuais_<YYYY-MM-DD>.csv` (timestamped),
# colunas brutas da API. Silver consome este artefato e gera o pivot por ano.
#
# Falha graciosa: se o fetch falhar, loga e aborta SEM raise — o Silver detecta
# ausência do dia, mantém parquet anterior, e o Gold cai para heurística com
# `is_proj_heuristica: true`.

# Databricks notebook source
# MAGIC %pip install azure-storage-blob requests pandas

# COMMAND ----------

import io
import os
import sys
from datetime import date

import pandas as pd
import requests
from azure.storage.blob import BlobServiceClient

# Permite importar _common.py mesmo executando este notebook isoladamente.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


# COMMAND ----------

FOCUS_ENDPOINT = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
    "ExpectativasMercadoTop5Anuais"
    "?$filter=Indicador%20eq%20'IPCA'%20or%20Indicador%20eq%20'Selic'"
    "&$format=json"
)

# Timeout generoso — o endpoint OData do BCB às vezes leva ~20s.
REQUEST_TIMEOUT = 60

CONTAINER = "bronze"
PASTA_BASE = "focus"


# COMMAND ----------


def baixar_focus(endpoint: str = FOCUS_ENDPOINT) -> pd.DataFrame | None:
    """Baixa expectativas do Focus. Retorna None em qualquer falha (graceful)."""
    try:
        print(f"Buscando: {endpoint}")
        resp = requests.get(endpoint, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        records = payload.get("value", [])
        if not records:
            print("AVISO: endpoint retornou 0 registros. Abortando ingestão.")
            return None
        df = pd.DataFrame(records)
        print(f"OK: {len(df)} registros recebidos. Colunas: {list(df.columns)}")
        return df
    except requests.RequestException as e:
        print(f"AVISO: falha ao buscar Focus ({e}). Bronze não será atualizado.")
        return None
    except (ValueError, KeyError) as e:
        print(f"AVISO: payload do Focus inválido ({e}). Bronze não será atualizado.")
        return None


def salvar_data_lake(df: pd.DataFrame, container: str, caminho_blob: str, conn: str) -> None:
    print(f"Salvando {caminho_blob} em {container}...")
    client = BlobServiceClient.from_connection_string(conn)
    buf = io.StringIO()
    df.to_csv(buf, index=False, sep=";")
    client.get_blob_client(container=container, blob=caminho_blob).upload_blob(
        buf.getvalue(), overwrite=True
    )
    print(f"OK: {container}/{caminho_blob} ({len(df)} linhas)")


# COMMAND ----------


def main() -> int:
    hoje = date.today()
    df = baixar_focus()
    if df is None or df.empty:
        # Falha graciosa: não levanta exceção para não derrubar a orquestração
        # Bronze; o Silver detecta ausência do dia e o Gold cai para heurística.
        print(f"Ingestão Focus abortada para {hoje.isoformat()} (sem dados).")
        return 1

    # Adiciona coluna de ingestão para auditoria temporal no Silver.
    df["data_ingestao"] = hoje.isoformat()

    caminho_dia = (
        f"{PASTA_BASE}/{hoje:%Y}/{hoje:%m}/{hoje:%d}/"
        f"expectativas_top5_anuais_{hoje.isoformat()}.csv"
    )
    caminho_latest = f"{PASTA_BASE}/expectativas_top5_anuais.csv"

    conn = azure_connection_string()
    salvar_data_lake(df, CONTAINER, caminho_dia, conn)
    # Também grava cópia "latest" para o Silver consumir sem precisar listar diretório por data.
    salvar_data_lake(df, CONTAINER, caminho_latest, conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
