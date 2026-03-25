# 🎣 Radar FIDC — Data Fishermans

> Plataforma de análise, scoring e recomendação de FIDCs para PMEs

**[🚀 Acessar Dashboard →](https://victorsouza14.github.io/radar-fidc)**

---

## Sobre o Projeto

O **Radar FIDC** é uma plataforma de BI desenvolvida pelo grupo **Data Fishermans** na Sprint Final da FIAP 2026. O objetivo é democratizar o acesso a FIDCs (Fundos de Investimento em Direitos Creditórios) para PMEs, fornecendo análises de risco, scoring e recomendações personalizadas.

## Dashboard

O dashboard interativo possui 4 páginas:

| Página | Conteúdo |
|--------|----------|
| 📊 Visão Geral | KPIs + Top 10 FIDCs por score |
| 🎯 Score & Risco | Scatter plot + distribuição por classificação |
| 📈 Cenário Macro | SELIC, IPCA, CDI + análise de impacto |
| 🏢 Recomendação PME | Top-3 FIDCs por segmento (Varejo, Agronegócio, Serviços, Indústria, Tecnologia) |

## Arquitetura de Dados

```
ANBIMA + BCB/Focus
      ↓
  Azure Data Factory
      ↓
  Bronze (CSV) → Silver (Parquet) → Gold (Parquet/CSV)
      ↓
  Databricks (Score Engine)
      ↓
  Dashboard HTML (GitHub Pages)
```

## Score dos FIDCs

Score ponderado 0–100 com classificação A/B/C/D:

- **40%** Retorno histórico
- **30%** Risco/Volatilidade
- **20%** Cenário Macroeconômico
- **10%** Liquidez

## Stack

- **Ingestão**: Azure Data Factory + Python
- **Storage**: Azure Data Lake Storage Gen2
- **Processamento**: Databricks (Spark 16.4) + Pandas + PyArrow
- **Dados**: ANBIMA API + BCB/Boletim Focus
- **Dashboard**: HTML + Chart.js (GitHub Pages)

## Grupo

**Data Fishermans** | FIAP | Sprint Final 2026
