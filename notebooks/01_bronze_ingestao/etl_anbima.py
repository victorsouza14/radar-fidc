# Notebook: etl_fidc_anbima
# Camada: Bronze — Ingestão
# Fonte: ANBIMA/BCB/CVM

# Databricks notebook source
# MAGIC %pip install azure-storage-blob xlrd lxml html5lib
# MAGIC %pip install pendulum

# COMMAND ----------

import pandas as pd
import requests
import pendulum
import io
from azure.storage.blob import BlobServiceClient
from io import StringIO
import os
import time
import  base64
import datetime as dt
import shutil

# COMMAND ----------

# === CONFIG ===
BASE = os.getenv("ANBIMA_BASE", "https://api.anbima.com.br")  # ou https://api-sandbox.anbima.com.br
CLIENT_ID = os.getenv("ANBIMA_CLIENT_ID", "sqmKHanwC9za")
CLIENT_SECRET = os.getenv("ANBIMA_CLIENT_SECRET", "4aQqzp3bIV7k")

LIST_MAX_SIZE = 1000   # /feed/fundos/v2/fundos (page/size)
LOTE_MAX_SIZE = 250    # /lote (cursor + size<=250)
TIMEOUT = 60
MAX_RETRIES = 5

# COMMAND ----------

def salvarDataLake(DF, NOME_CONTAINER, NOME_ARQUIVO):     
    # Puxa a string de conexão do cofre do Databricks
    CONNECTION_STRING = dbutils.secrets.get(scope="escopo", key="AZURECONNSTRING")

    try:
        print(f"Conectando ao Azure para salvar {NOME_ARQUIVO}...")
        blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
        
        output = StringIO()
        DF.to_csv(output, index=False, sep=";") # Salvando com separador ponto e vírgula
        dados_csv = output.getvalue()
        
        caminho_blob = f"{NOME_ARQUIVO}"
        blob_client = blob_service_client.get_blob_client(container=NOME_CONTAINER, blob=caminho_blob)
        blob_client.upload_blob(dados_csv, overwrite=True)
        
        print(f"✅ Sucesso! Arquivo salvo em: {NOME_CONTAINER}/{caminho_blob}")
    except Exception as e:
         print(f"❌ Erro ao salvar no Azure: {e}")

def _retry_sleep(attempt):
    time.sleep(min(2 ** attempt, 30))

def get_access_token():
    url = f"{BASE}/oauth/access-token"

    # DEBUG: remova depois
    raw = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64 = base64.b64encode(raw.encode()).decode()
    print("[DEBUG] BASE =", BASE)
    print("[DEBUG] CLIENT_ID len =", len(CLIENT_ID), "| SECRET len =", len(CLIENT_SECRET))
    print("[DEBUG] BASIC (first 16) =", b64[:16], "...")

    r = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {b64}",
            "Accept": "application/json",
        },
        json={"grant_type": "client_credentials"},
        timeout=30,
    )

    if r.status_code in (200, 201):
        data = r.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"[TOKEN OK MAS SEM access_token] payload={data}")
        print(f"✅ Token OK (expires_in={data.get('expires_in')}s)")
        return token

    msg = r.text[:400]
    if r.status_code == 400 and "Invalid client_id" in msg:
        raise RuntimeError(
            "[TOKEN 400] Invalid client_id — confira se:\n"
            "- Você está usando o client_id/secret da APP de PRODUÇÃO;\n"
            "- Não há espaços/quebras de linha no client_id/secret;\n"
            "- O Authorization Basic é base64(client_id:client_secret).\n"
            f"Resposta: {msg}"
        )
    if r.status_code == 401:
        raise RuntimeError("[TOKEN 401] Credenciais inválidas ou app não habilitada em produção.")
    if r.status_code in (429, 500, 502, 503, 504):
        raise RuntimeError(f"[TOKEN {r.status_code}] Intermitência — tente novamente. Resp: {msg}")

    raise RuntimeError(f"[TOKEN {r.status_code}] {msg}")

def _feed_headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "client_id": CLIENT_ID,  # exigido pelo gateway
        "access_token": token,   # idem
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
    return f"{date_yyyy_mm_dd}T00:00:00.000"   # <-- sem 'Z'


# COMMAND ----------

if __name__ == "__main__":
    token = get_access_token()
    
    # Pegando a data atual
    agora = dt.datetime.now()
    
    # Extraindo as partes para montar a hierarquia de pastas
    ano = agora.strftime("%Y")
    mes = agora.strftime("%m")
    dia = agora.strftime("%d")
    data_hoje = agora.strftime("%Y%m%d") # mantido para o sufixo do arquivo
    
    container_destino = "bronze" 
    
    # Criando a estrutura de pastas: anbima/YYYY/MM/DD
    caminho_base = f"anbima/{ano}/{mes}/{dia}"

    # ==========================================
    # 1) Lista de FIDC (paginação page/size)
    # ==========================================
    df_fundos = get_paginated_list(
        f"{BASE}/feed/fundos/v2/fundos",
        token,
        params={"tipo-fundo": "FIDC", "size": LIST_MAX_SIZE}
    )
    # Salvando com a hierarquia: anbima/ano/mes/dia/arquivo.csv
    salvarDataLake(df_fundos, container_destino, f"{caminho_base}/fundos_v2_fidc_{data_hoje}.csv")


    # ==========================================
    # 2) Lote – dados cadastrais (cursor + range)
    # ==========================================
    # Usando 3 dias temos uma margem segura que não quebra a regra de 1 mês da API
    start = (dt.datetime.now(dt.UTC) - dt.timedelta(days=3)).date().isoformat()
    
    df_cad = get_cursor_lote(
        f"{BASE}/feed/fundos/v2/fundos/dados-cadastrais/lote",
        token,
        params={
            "tipo-fundo": "FIDC",
            "data-atualizacao": iso_anbima(start),
        },
        size=LOTE_MAX_SIZE
    )
    salvarDataLake(df_cad, container_destino, f"{caminho_base}/dados_cadastrais_fidc_{data_hoje}.csv")


    # ==========================================
    # 3) Lote – série histórica (PL & cota)
    # ==========================================
    df_hist = get_cursor_lote(
        f"{BASE}/feed/fundos/v2/fundos/serie-historica/lote",
        token,
        params={
            "tipo-fundo": "FIDC",
            "data-atualizacao": iso_anbima(start),
        },
        size=LOTE_MAX_SIZE
    )
    salvarDataLake(df_hist, container_destino, f"{caminho_base}/serie_historica_fidc_{data_hoje}.csv")

# COMMAND ----------

