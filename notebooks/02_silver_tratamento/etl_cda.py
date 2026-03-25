# Notebook: etl_cda
# Camada: Silver — Tratamento
# Saída: Parquet no ADLS Gen2

# Databricks notebook source
import gc
import io
import os

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from azure.storage.blob import BlobServiceClient
from datetime import datetime
from dateutil.relativedelta import relativedelta

CONNECTION_STRING = dbutils.secrets.get(scope="escopo", key="AZURECONNSTRING")

blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)

# Instanciando os clientes de container apenas uma vez
client_silver = blob_service_client.get_container_client("silver")
client_bronze = blob_service_client.get_container_client("bronze")
pasta_base = 'cda/'

# CORREÇÃO 1: Usar relativedelta para evitar quebra em Janeiro (month - 1 == 0)
data_anterior = datetime.today() - relativedelta(months=1)
ano = str(data_anterior.year)
mes = str(data_anterior.month).zfill(2)

# 1. MAPEAMENTO BRONZE
try:
    print(f"Buscando arquivos em: bronze/{pasta_base}...")
    blobs_bronze = list(client_bronze.list_blobs(name_starts_with=pasta_base))
    arquivos_bronze = {
        x.name[:-10].split('/')[-1]: x
        for x in blobs_bronze
        if x.name.endswith(f'{ano}{mes}.csv')
    }
    print(len(arquivos_bronze))
except Exception as e:
    print(f"Erro ao mapear Bronze: {e}")
    arquivos_bronze = {}


# 2. MAPEAMENTO SILVER
try:
    print(f"Buscando arquivos em: silver/{pasta_base}...")
    blobs_silver = list(client_silver.list_blobs(name_starts_with=pasta_base))
    arquivos_silver = {
        x.name[:-8].split('/')[-1]: x
        for x in blobs_silver
        if x.name.endswith('.parquet')
    }
    print(len(arquivos_silver))
except Exception as e:
    print(f"Erro ao mapear Silver: {e}")
    arquivos_silver = {}


# 3. PROCESSAMENTO
for nome_arquivo_bronze, blob_bronze_prop in arquivos_bronze.items():
    # Declarar variáveis fora do try para o finally conseguir deletar com segurança
    dados_bronze = None
    dados_silver = None
    df_bronze   = None
    df_silver   = None
    df_resultado = None
    df          = None
    buffer      = None

    try:
        print(f"--- Iniciando processamento: {nome_arquivo_bronze} ---")

        # Download Bronze
        dados_bronze = client_bronze.get_blob_client(blob_bronze_prop.name).download_blob().readall()

        # CORREÇÃO 2: Liberar os bytes brutos logo após o parse para não manter 2 cópias na RAM
        df_bronze = pd.read_csv(io.BytesIO(dados_bronze), sep=';', low_memory=False, dtype=str)
        del dados_bronze
        dados_bronze = None

        df_silver = None
        blob_silver_prop = arquivos_silver.get(nome_arquivo_bronze)

        # Download Silver (se existir)
        if blob_silver_prop:
            dados_silver = client_silver.get_blob_client(blob_silver_prop.name).download_blob().readall()

            # CORREÇÃO 3: Liberar os bytes brutos logo após o parse
            df_silver = pd.read_parquet(io.BytesIO(dados_silver))
            del dados_silver
            dados_silver = None

            # Garante que os tipos base batam com o Bronze antes do concat
            df_silver = df_silver.astype(str)

        # Concatenação inteligente
        if df_silver is not None and not df_silver.empty:
            df_resultado = pd.concat([df_bronze, df_silver], axis=0, ignore_index=True)
        else:
            df_resultado = df_bronze.copy()

        # Liberar Bronze e Silver após concat — não são mais necessários
        del df_bronze, df_silver
        df_bronze = None
        df_silver = None

        # --- TIPAGEM DAS COLUNAS ---
        # 1. Colunas numéricas
        colunas_numericas = [
            'QT_VENDA_NEGOC', 'VL_VENDA_NEGOC', 'QT_POS_FINAL',
            'VL_MERC_POS_FINAL', 'VL_AQUIS_NEGOC', 'VL_CUSTO_POS_FINAL'
        ]
        for col in colunas_numericas:
            if col in df_resultado.columns:
                df_resultado[col] = pd.to_numeric(df_resultado[col], errors='coerce').fillna(0.0)

        # 2. Garantir string nas colunas object
        for col in df_resultado.select_dtypes(include=['object']).columns:
            df_resultado[col] = df_resultado[col].astype(str)

        # Remoção de Duplicados
        qtd_antes = len(df_resultado)
        df = df_resultado.drop_duplicates(keep='last').reset_index(drop=True)
        del df_resultado
        df_resultado = None
        print(f"Registros: {qtd_antes} -> Pós-deduplicação: {len(df)}")

        # Criar buffer Parquet e fazer upload
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False, engine='pyarrow', compression='snappy')
        buffer.seek(0)

        nome_arquivo_saida = f"cda/{nome_arquivo_bronze}.parquet"
        blob_client_saida = client_silver.get_blob_client(nome_arquivo_saida)
        blob_client_saida.upload_blob(buffer, overwrite=True)
        print(f"Sucesso! Arquivo {nome_arquivo_saida} gravado na Silver.\n")

    except Exception as e:
        print(f"Erro ao processar {nome_arquivo_bronze}: {e}")

    finally:
        # CORREÇÃO 4: Garante liberação de memória mesmo se ocorrer erro no meio do processamento
        dados_bronze = None
        dados_silver = None
        df_bronze    = None
        df_silver    = None
        df_resultado = None
        df           = None
        buffer       = None
        gc.collect()