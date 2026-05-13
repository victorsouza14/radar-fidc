# Notebook: etl_fidc_bcb
# Camada: Bronze — Ingestão
# Fonte: BCB / SGS — indicadores macroeconômicos

# Databricks notebook source
# MAGIC %pip install python-bcb azure-storage-blob pandas

# COMMAND ----------

import os
import sys
from datetime import date, timedelta
from io import StringIO

import pandas as pd
from azure.storage.blob import BlobServiceClient
from bcb import sgs

# Permite importar _common.py mesmo executando este notebook isoladamente.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


# COMMAND ----------

class MacroMetricas:
    def __init__(self, data_referencia: date | None = None):
        self.data_referencia = data_referencia or date.today()

    def gerarTabelaConsolidada(self, dict_metricas):
        print(f"\nGerando tabela consolidada para: {self.data_referencia}")
        linha = {"data_processamento": self.data_referencia}
        for nome, codigo in dict_metricas.items():
            df_temp = self.gerarTabelaMetrica(nome, codigo)
            linha[nome] = df_temp[nome].iloc[-1] if df_temp is not None and not df_temp.empty else None
        return pd.DataFrame([linha])

    def gerarTabelaMetrica(self, nome, numero):
        # Janela de 90 dias para cobrir feriados/fins de semana e indicadores mensais (IPCA, IGP-M).
        try:
            inicio = self.data_referencia - timedelta(days=90)
            df = sgs.get({nome: numero}, start=inicio, end=self.data_referencia)
            return df if not df.empty else None
        except Exception as e:
            print(f"Erro em {nome} (cod {numero}): {e}")
            return None

    def salvarDataLake(self, DF, NOME_CONTAINER, CAMINHO_BLOB):
        conn = azure_connection_string()
        client = BlobServiceClient.from_connection_string(conn)
        output = StringIO()
        DF.to_csv(output, index=False, sep=";")
        client.get_blob_client(container=NOME_CONTAINER, blob=CAMINHO_BLOB).upload_blob(
            output.getvalue(), overwrite=True
        )
        print(f"OK: {NOME_CONTAINER}/{CAMINHO_BLOB} ({len(DF)} linhas)")


# COMMAND ----------

METRICAS = {
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
    "ic_br_energia": 27575,
}


if __name__ == "__main__":
    hoje = date.today()
    metrica = MacroMetricas(hoje)
    df_hoje = metrica.gerarTabelaConsolidada(METRICAS)
    print(df_hoje)

    caminho = (
        f"dados_macroeconomicos/bcb/{hoje:%Y}/{hoje:%m}/{hoje:%d}/"
        f"metricas_macro_{hoje.isoformat()}.csv"
    )
    metrica.salvarDataLake(df_hoje, "bronze", caminho)
