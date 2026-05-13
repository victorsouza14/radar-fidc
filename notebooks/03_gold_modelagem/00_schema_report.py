# Notebook: 00_schema_report
# Camada: Gold — Radar FIDC
#
# Valida que todos os parquets esperados estão presentes na Silver e reporta schemas.
# Falha cedo se alguma fonte essencial estiver ausente.

import io
import os
import sys

import pandas as pd
from azure.storage.blob import BlobServiceClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _common import azure_connection_string  # noqa: E402


CONNECTION_STRING = azure_connection_string()
blob_svc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
silver = blob_svc.get_container_client("silver")


FONTES_OBRIGATORIAS = [
    "anbima/serie_historica_fidc.parquet",
    "anbima/fundos_v2_fidc.parquet",
]

FONTES_OPCIONAIS = [
    "anbima/dados_cadastrais_fidc.parquet",
    "dados_macroeconomicos/consolidado.parquet",
]


def schema_de(path: str) -> dict | None:
    try:
        d = silver.get_blob_client(path).download_blob().readall()
        df = pd.read_parquet(io.BytesIO(d))
        return {
            "linhas": len(df),
            "colunas": list(df.columns),
            "tipos": {c: str(t) for c, t in df.dtypes.items()},
        }
    except Exception as e:
        return None if "NotFound" in str(e) or "BlobNotFound" in str(e) else {"erro": str(e)}


print("=" * 60)
print("  Schema Report — Silver")
print("=" * 60)

faltando: list[str] = []
for path in FONTES_OBRIGATORIAS:
    info = schema_de(path)
    if not info:
        print(f"\n[FALTA] {path}")
        faltando.append(path)
    elif "erro" in info:
        print(f"\n[ERRO]  {path}: {info['erro']}")
        faltando.append(path)
    else:
        print(f"\n[OK]    {path}: {info['linhas']} linhas, {len(info['colunas'])} colunas")
        for c, t in info["tipos"].items():
            print(f"           {c}: {t}")

for path in FONTES_OPCIONAIS:
    info = schema_de(path)
    if not info:
        print(f"\n[OPCIONAL FALTA] {path}")
    elif "erro" in info:
        print(f"\n[OPCIONAL ERRO]  {path}: {info['erro']}")
    else:
        print(f"\n[OPCIONAL OK]    {path}: {info['linhas']} linhas")

if faltando:
    raise SystemExit(
        f"\nFontes obrigatórias ausentes: {faltando}. Rode as camadas Bronze e Silver antes do Gold."
    )

print("\nTodas as fontes obrigatórias presentes. Pipeline Gold pode prosseguir.")
