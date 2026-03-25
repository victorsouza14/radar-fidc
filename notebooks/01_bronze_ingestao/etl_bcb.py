# Notebook: etl_fidc_bcb
# Camada: Bronze — Ingestão
# Fonte: ANBIMA/BCB/CVM

# Databricks notebook source
# MAGIC %pip install python-bcb azure-storage-blob pandas

# COMMAND ----------

from bcb import sgs
import pandas as pd
from datetime import date
from datetime import timedelta
from azure.storage.blob import BlobServiceClient
from io import StringIO
import os
import shutil


class macroMetricas:
    def __init__(self):
        self.tabela = None
        self.data_atual = date.today()

    def gerarTabelaConsolidada(self, dict_metricas):
        """
        Gera a linha horizontal. Se data_referencia for None, usa HOJE.
        """
        data = date.today()            
        print(f"\n--- Gerando Tabela Consolidada para: {data} ---")
        linha_dados = {"data_processamento": data}
        for nome, codigo in dict_metricas.items():
            df_temp = self.gerarTabelaMetrica(nome, codigo)
            if df_temp is not None:
                linha_dados[nome] = df_temp[nome].iloc[0]
            else:
                linha_dados[nome] = None
        df_final = pd.DataFrame([linha_dados])
        return df_final


    def gerarTabelaMetrica(self, nome, numero):
        try:
            # COMPORTAMENTO HISTÓRICO: Pega o dado vigente na data passada
            # Truque: Buscamos 40 dias atrás até a data alvo e pegamos o último (.tail(1))
            # Isso resolve problemas de feriado, fim de semana e dados mensais (IPCA)
            inicio_janela = self.data_atual - timedelta(days=90)
            df = sgs.get({nome: numero}, start=inicio_janela, end=self.data_atual)
            if df.empty:
                return None
            return  df
        except Exception as e:
            print(f" Erro em {nome}: {e}")
            return None


    def salvarDataLake(self, DF, NOME_CONTAINER, NOME_ARQUIVO):     
        CONNECTION_STRING = dbutils.secrets.get(scope="escopo", key="AZURECONNSTRING")

        try:
            print(f"Conectando ao Azure para salvar {NOME_ARQUIVO}...")
            blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
            output = StringIO()
            DF.to_csv(output, index=False, sep=";")
            dados_csv = output.getvalue()
            caminho_blob = f"{NOME_ARQUIVO}"
            blob_client = blob_service_client.get_blob_client(container=NOME_CONTAINER, blob=caminho_blob)
            blob_client.upload_blob(dados_csv, overwrite=True)
            print(f"Sucesso! Arquivo salvo em: {NOME_CONTAINER}/{caminho_blob}")
        except Exception as e:
             print(f"Erro ao salvar no Azure: {e}")


from datetime import date 

metrica = macroMetricas() 

metricas_avancadas = {
    "selic_meta": 432,
    "cdi_diario": 12,
    "dolar_venda": 1,
    "ipca_mensal": 433,
    "igpm_mensal": 189,
    "incc_m": 192,
    "ibc_br": 24364,
    "inadimplencia_total": 21082,
    "inadimplencia_pj": 21084,
    "inadimplencia_pf": 21083,
    "utilizacao_capacidade": 24352,
    "ic_br_agro": 27574,
    "ic_br_energia": 27575
}


print("\n--- Processando HOJE ---")
df_hoje = metrica.gerarTabelaConsolidada(metricas_avancadas)
print(df_hoje)

data = date.today()
ano = data.strftime('%Y')
mes = data.strftime('%m')
dia = data.strftime('%d')

nome_arquivo_hoje = f"metricas_macro_{data}.csv"
metrica.salvarDataLake(
    df_hoje, 
    "bronze", 
    f"dados_macroeconomicos/bcb/{ano}/{mes}/{dia}/{nome_arquivo_hoje}"
)


# COMMAND ----------

