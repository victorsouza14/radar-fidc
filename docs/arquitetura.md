# Arquitetura — Radar FIDC

## Visão Geral

O Radar FIDC segue a **arquitetura Medallion** (Bronze → Silver → Gold), padrão de mercado para pipelines de dados em Data Lakehouse.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FONTES DE DADOS                              │
│                                                                     │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐       │
│   │  ANBIMA  │   │  BCB /   │   │   CVM    │   │  Núclea  │       │
│   │   API    │   │  Focus   │   │ Informe  │   │ (futuro) │       │
│   └────┬─────┘   └────┬─────┘   └────┬─────┘   └──────────┘       │
└────────┼──────────────┼──────────────┼──────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│              AZURE DATA FACTORY (Orquestração)                      │
│              Pipeline diária — trigger 6h UTC                       │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│         AZURE DATA LAKE STORAGE Gen2 (dfdatalakesprint)             │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  🥉 BRONZE — Dados Brutos (CSV)                             │   │
│  │  bronze/anbima/     → fundos_v2_fidc, serie_historica        │   │
│  │  bronze/macroeco/   → SELIC, IPCA, Focus                    │   │
│  │  bronze/cda/        → carteira de ativos mensal              │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
│                            │ ETL Silver (Databricks)                │
│  ┌─────────────────────────▼───────────────────────────────────┐   │
│  │  🥈 SILVER — Dados Tratados (Parquet)                       │   │
│  │  silver/anbima/     → parquet limpo e tipado                 │   │
│  │  silver/dados_macro/→ consolidado BCB + Focus               │   │
│  │  silver/cda/        → carteira padronizada                   │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
│                            │ ETL Gold (Databricks)                  │
│  ┌─────────────────────────▼───────────────────────────────────┐   │
│  │  🥇 GOLD — Dados Analíticos (Parquet + CSV)                 │   │
│  │  gold/score_fidc/          → score ponderado por FIDC       │   │
│  │  gold/indicadores_macro/   → SELIC, IPCA, CDI atual         │   │
│  │  gold/recomendacao_pme/    → matching PME × FIDC            │   │
│  │  gold/dashboard_resumo/    → tabela mestre Power BI         │   │
│  │  gold/powerbi/             → CSVs para consumo direto       │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
└────────────────────────────┼────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
┌─────────────────────┐       ┌─────────────────────────┐
│   Dashboard HTML    │       │     Power BI Desktop     │
│   (GitHub Pages)   │       │   (conexão via CSV/ADLS) │
│                     │       │                          │
│  victorsouza14      │       │  POWERBI_SETUP.md        │
│  .github.io/        │       │  (instruções completas)  │
│  radar-fidc         │       │                          │
└─────────────────────┘       └─────────────────────────┘
```

## Componentes

### Azure Data Factory
- **Pipeline**: `pipeline_radar_fidc`
- **Trigger**: Diário às 6h UTC
- **Atividades**: Copy Data → Databricks Notebook Run

### Azure Databricks
- **Workspace**: `dbw-radar-fidc`
- **Cluster**: StandardD4s_v3 (4 vCores, 16GB RAM), Spark 16.4
- **Notebooks**: 9 notebooks organizados em 3 camadas

### Azure Data Lake Storage Gen2
- **Conta**: `dfdatalakesprint`
- **Containers**: `bronze`, `silver`, `gold`
- **Formato**: CSV (Bronze) → Parquet (Silver/Gold) → CSV (Gold/powerbi)
- **Prefixo de outputs analíticos**: `gold/final/` (consumido pelo `generate_dashboard_data.py`)

## Fluxo de Execução

```
1. ADF trigger (6h UTC)
   └── 2. Bronze: etl_anbima.py    → bronze/anbima/*.csv
   └── 3. Bronze: etl_bcb.py       → bronze/macroeco/*.csv
   └── 4. Bronze: etl_cda.py       → bronze/cda/*.csv
       └── 5. Silver: etl_anbima.py   → silver/anbima/*.parquet
       └── 6. Silver: etl_macro.py    → silver/dados_macro/*.parquet
       └── 7. Silver: etl_cda.py      → silver/cda/*.parquet
           └── 8. Gold: orquestrador_gold.py
               ├── 01_score_fidc.py         → score ponderado
               ├── 02_indicadores_macro.py  → contexto macro
               ├── 03_recomendacao_pme.py   → matching PME
               ├── 04_dashboard_master.py   → tabela consolidada
               └── 05_export_csv.py         → CSVs para dashboard
```

## Tecnologias

| Categoria | Tecnologia | Versão |
|-----------|-----------|--------|
| Orquestração | Azure Data Factory | v2 |
| Processamento | Apache Spark (Databricks) | 16.4 |
| Storage | Azure Data Lake Gen2 | — |
| Linguagem | Python | 3.10+ |
| Serialização | Apache Parquet (PyArrow) | 14.0+ |
| Dashboard | HTML + Chart.js | 4.4 |
| Publicação | GitHub Pages | — |
