# `data_real/` — Bases reais do projeto

Este diretório contém **inputs e outputs** do pipeline Radar FIDC.

## Estrutura

```
data_real/
├── clientes.csv                          # 20 clientes do questionário suitability
├── scores_credito.csv                    # output do scripts/credit_model.py — 3.525 empresas
├── rating_fidc.xlsx                      # output do scripts/rating.py — 6.100 classes
├── matches.xlsx                          # output do scripts/match.py — 100 matches
├── credit_model.pkl                      # XGBoost serializado
│
├── bases/                                # inputs do credit_model
│   ├── base_boletos_fiap.csv             # 7.119 boletos (target)
│   └── base_auxiliar_fiap.csv            # features cadastrais
│
├── macroeconomicos/
│   └── consolidade.csv                   # SELIC, CDI, IPCA, IBC-Br (BCB SGS)
│
└── arquivos/                             # inputs do rating.py
    ├── anbima/                           # ✅ versionado (7 MB)
    │   ├── fundos_v2_fidc.parquet
    │   ├── dados_cadastrais_fidc.parquet
    │   └── serie_historica_fidc.parquet
    │
    ├── info_mensal/                      # ✅ versionado (apenas Tabs usados — 52 MB)
    │   ├── inf_mensal_fidc_tab_I_.parquet   # concentração de cedentes
    │   ├── inf_mensal_fidc_tab_V_.parquet   # inadimplência + aging
    │   └── inf_mensal_fidc_tab_X_.parquet   # SCR devedores
    │
    └── cda/                              # ❌ NÃO versionado (5.1 GB, 2 arquivos > 100 MB)
        └── README.md                     # como obter
```

## O que está versionado

| Função | Está aqui? | Por quê |
|---|---|---|
| Rodar o dashboard | ✅ Tudo | Outputs já calculados são suficientes |
| Reproduzir `scripts/credit_model.py` | ✅ Sim | `bases/` está no repo |
| Reproduzir `scripts/match.py` | ✅ Sim | usa `rating_fidc.xlsx` + `clientes.csv` |
| Reproduzir `scripts/rating.py` (parcial) | ⚠️ Sim sem CDA | requer baixar CDA primeiro |
| Reproduzir notebooks ADF/Databricks completos | ⚠️ Parcial | exige bases CVM completas |

## CDA (Composição da Carteira)

O CDA da CVM tem ~5 GB e dois arquivos individuais excedem o limite de 100 MB do GitHub
(`cda_fi_BLC_1_.parquet` 139 MB e `cda_fi_BLC_7_.parquet` 141 MB).

Para obter:

### Opção A — direto da CVM (gratuito, oficial)

```bash
mkdir -p data_real/arquivos/cda
cd data_real/arquivos/cda

# Snapshot mensal mais recente — substitua AAAAMM
curl -O https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_AAAAMM.zip
unzip cda_fi_AAAAMM.zip
```

Os notebooks `01_bronze_ingestao/etl_cda.py` automatizam esse download.

### Opção B — Git LFS

Se quiser versionar mesmo assim:

```bash
brew install git-lfs        # macOS
git lfs install
git lfs track "data_real/arquivos/cda/*.parquet"
git add .gitattributes data_real/arquivos/cda/
git commit -m "chore: Track CDA via Git LFS"
```

### Opção C — Azure Blob (produção)

O pipeline `notebooks/` lê de `stdatatalake2026/bronze/cda/`. Configure
`AZURE_CONNECTION_STRING` no `.env` e rode os notebooks no Databricks.

## Outros Tabs do `info_mensal` (II, III, IV, IX, VI, VII, X_*)

Não são usados pelo `scripts/rating.py` atual. Total ~110 MB.

Se precisar para análises adicionais, baixe de:
<https://dados.cvm.gov.br/dados/FI/DOC/INF_MENSAL_FIDC/DADOS/>
