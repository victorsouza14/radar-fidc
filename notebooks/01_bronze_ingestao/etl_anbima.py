# Notebook: etl_fidc_anbima
# Camada: Bronze — Ingestão
# Fonte: ANBIMA API (FIDCs)

# Databricks notebook source
# MAGIC %pip install azure-storage-blob xlrd lxml html5lib pendulum

# COMMAND ----------

import base64
import datetime as dt
import io
import os
import time
from io import StringIO

import pandas as pd
import requests
from azure.storage.blob import BlobServiceClient

# COMMAND ----------

# === CONFIG ===
# Credenciais vêm do ambiente (Databricks Secret Scope ou .env local).
# NUNCA commitar valores reais aqui.
BASE = os.environ.get("ANBIMA_BASE", "https://api.anbima.com.br")
CLIENT_ID = os.environ.get("ANBIMA_CLIENT_ID")
CLIENT_SECRET = os.environ.get("ANBIMA_CLIENT_SECRET")
AZURE_CONNECTION_STRING = os.environ.get("AZURE_CONNECTION_STRING")

LIST_MAX_SIZE = 1000   # /feed/fundos/v2/fundos (page/size)
LOTE_MAX_SIZE = 250    # /lote (cursor + size<=250)
TIMEOUT = 60
MAX_RETRIES = 5


def _require_env(name: str, value):
    if not value:
        raise RuntimeError(
            f"Variável obrigatória ausente: {name}. "
            "Configure no .env (local) ou no Databricks Secret Scope 'escopo'."
        )
    return value


# COMMAND ----------

def salvarDataLake(DF, NOME_CONTAINER, NOME_ARQUIVO):
    conn = _require_env("AZURE_CONNECTION_STRING", AZURE_CONNECTION_STRING)
    try:
        print(f"Salvando {NOME_ARQUIVO} em {NOME_CONTAINER}...")
        blob_service_client = BlobServiceClient.from_connection_string(conn)

        output = StringIO()
        DF.to_csv(output, index=False, sep=";")
        dados_csv = output.getvalue()

        blob_client = blob_service_client.get_blob_client(container=NOME_CONTAINER, blob=NOME_ARQUIVO)
        blob_client.upload_blob(dados_csv, overwrite=True)

        print(f"OK: {NOME_CONTAINER}/{NOME_ARQUIVO} ({len(DF)} linhas)")
    except Exception as e:
        print(f"ERRO ao salvar no Azure: {e}")
        raise


def _retry_sleep(attempt):
    time.sleep(min(2 ** attempt, 30))


def get_access_token():
    _require_env("ANBIMA_CLIENT_ID", CLIENT_ID)
    _require_env("ANBIMA_CLIENT_SECRET", CLIENT_SECRET)

    url = f"{BASE}/oauth/access-token"
    raw = f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
    basic = base64.b64encode(raw).decode()

    r = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {basic}",
            "Accept": "application/json",
        },
        json={"grant_type": "client_credentials"},
        timeout=30,
    )

    if r.status_code in (200, 201):
        data = r.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"Resposta sem access_token: {data}")
        print(f"Token ANBIMA OK (expires_in={data.get('expires_in')}s)")
        return token

    msg = r.text[:400]
    if r.status_code == 400 and "Invalid client_id" in msg:
        raise RuntimeError(
            "ANBIMA 400 Invalid client_id. Verifique: "
            "(a) credenciais de produção; (b) Basic = base64(client_id:client_secret); "
            "(c) sem espaços nas envvars."
        )
    if r.status_code == 401:
        raise RuntimeError("ANBIMA 401 — credenciais inválidas ou app não habilitada.")
    if r.status_code in (429, 500, 502, 503, 504):
        raise RuntimeError(f"ANBIMA {r.status_code} intermitência: {msg}")

    raise RuntimeError(f"ANBIMA {r.status_code}: {msg}")


def _feed_headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "client_id": CLIENT_ID,
        "access_token": token,
    }


def get_paginated_list(url, token, params=None, page_size=LIST_MAX_SIZE):
    headers = _feed_headers(token)
    params = dict(params or {})
    params.setdefault("page", 0)
    params.setdefault("size", page_size)

    all_rows = []
    while True:
        r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        if r.status_code != 200:
            raise RuntimeError(f"[LIST {r.status_code}] {r.text[:400]}")
        data = r.json()
        content = data.get("content") or data.get("conteudo") or []
        all_rows.extend(content)
        if len(content) < params["size"]:
            break
        params["page"] += 1
    return pd.json_normalize(all_rows)


def get_cursor_lote(url, token, params=None, size=LOTE_MAX_SIZE):
    headers = _feed_headers(token)
    params = dict(params or {})
    params["size"] = min(size or LOTE_MAX_SIZE, LOTE_MAX_SIZE)

    all_rows, cursor, page = [], None, 0
    while True:
        q = dict(params)
        if cursor:
            q["cursor"] = cursor
        r = requests.get(url, headers=headers, params=q, timeout=TIMEOUT)
        if r.status_code == 204:
            print(f"[LOTE] 204 sem conteúdo. pages={page}, rows={len(all_rows)}")
            break
        if r.status_code != 200:
            raise RuntimeError(f"[LOTE {r.status_code}] {r.text[:400]}")
        data = r.json() or {}
        rows = data.get("content") or data.get("conteudo") or data.get("itens") or []
        all_rows.extend(rows)
        cursor = data.get("next_cursor") or data.get("proximoCursor") or data.get("nextCursor")
        page += 1
        print(f"[LOTE] page={page} batch={len(rows)} next_cursor={'Y' if cursor else 'N'}")
        if not cursor or not rows:
            break
    return pd.json_normalize(all_rows)


def iso_anbima(date_yyyy_mm_dd: str):
    return f"{date_yyyy_mm_dd}T00:00:00.000"


# COMMAND ----------

if __name__ == "__main__":
    token = get_access_token()

    agora = dt.datetime.now()
    ano = agora.strftime("%Y")
    mes = agora.strftime("%m")
    dia = agora.strftime("%d")
    data_hoje = agora.strftime("%Y%m%d")

    container_destino = "bronze"
    caminho_base = f"anbima/{ano}/{mes}/{dia}"

    # 1) Lista de FIDC (paginação page/size)
    df_fundos = get_paginated_list(
        f"{BASE}/feed/fundos/v2/fundos",
        token,
        params={"tipo-fundo": "FIDC", "size": LIST_MAX_SIZE},
    )
    salvarDataLake(df_fundos, container_destino, f"{caminho_base}/fundos_v2_fidc_{data_hoje}.csv")

    # 2) Lote – dados cadastrais (cursor + range de 3 dias)
    start = (dt.datetime.now(dt.UTC) - dt.timedelta(days=3)).date().isoformat()

    df_cad = get_cursor_lote(
        f"{BASE}/feed/fundos/v2/fundos/dados-cadastrais/lote",
        token,
        params={"tipo-fundo": "FIDC", "data-atualizacao": iso_anbima(start)},
        size=LOTE_MAX_SIZE,
    )
    salvarDataLake(df_cad, container_destino, f"{caminho_base}/dados_cadastrais_fidc_{data_hoje}.csv")

    # 3) Lote – série histórica (PL & cota)
    df_hist = get_cursor_lote(
        f"{BASE}/feed/fundos/v2/fundos/serie-historica/lote",
        token,
        params={"tipo-fundo": "FIDC", "data-atualizacao": iso_anbima(start)},
        size=LOTE_MAX_SIZE,
    )
    salvarDataLake(df_hist, container_destino, f"{caminho_base}/serie_historica_fidc_{data_hoje}.csv")
