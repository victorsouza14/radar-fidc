<div align="center">

# 🎣 Radar FIDC

**Plataforma de análise, scoring e recomendação de FIDCs para PMEs**

[![Dashboard](https://img.shields.io/badge/Dashboard-Live-brightgreen?style=for-the-badge&logo=github)](https://victorsouza14.github.io/radar-fidc)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)](https://python.org)
[![Azure](https://img.shields.io/badge/Azure-Data%20Lake%20Gen2-0089D6?style=for-the-badge&logo=microsoft-azure)](https://azure.microsoft.com)
[![Databricks](https://img.shields.io/badge/Databricks-Spark%2016.4-FF3621?style=for-the-badge&logo=databricks)](https://databricks.com)
[![FIAP](https://img.shields.io/badge/FIAP-Sprint%20Final%202026-red?style=for-the-badge)](https://fiap.com.br)

---

### 🚀 [Acessar Dashboard →](https://victorsouza14.github.io/radar-fidc)

*2.489 FIDCs reais · Dados ANBIMA + BCB · Atualizado diariamente*

</div>

---

## 📋 Índice

- [Problema e Solução](#-problema-e-solução)
- [Dashboard](#-dashboard)
- [Arquitetura](#-arquitetura)
- [Estrutura do Repositório](#-estrutura-do-repositório)
- [Como Executar](#-como-executar)
- [Fontes de Dados](#-fontes-de-dados)
- [Modelo de Score](#-modelo-de-score)
- [Time](#-time)

---

## 💡 Problema e Solução

### O Problema

PMEs (Pequenas e Médias Empresas) enfrentam dificuldades para acessar crédito com condições favoráveis. Os **FIDCs** (Fundos de Investimento em Direitos Creditórios) são uma alternativa viável, mas:

- Existem **+2.400 FIDCs** registrados na ANBIMA — escolher é complexo
- Cada fundo tem risco, retorno e perfil diferentes
- PMEs não têm assessoria financeira especializada

### A Solução

O **Radar FIDC** automatiza a análise de todos os FIDCs disponíveis e recomenda os mais adequados para cada perfil de PME, considerando:

- Histórico de retorno e volatilidade
- Cenário macroeconômico atual (SELIC, IPCA, CDI)
- Compatibilidade com o segmento e necessidade da PME

---

## 📊 Dashboard

Acesse o dashboard interativo em: **https://victorsouza14.github.io/radar-fidc**

| Página | O que mostra |
|--------|-------------|
| **Visão Geral** | KPIs + Top 10 FIDCs por score + tabela de ranking |
| **Score & Risco** | Scatter plot retorno × risco + distribuição por classe |
| **Cenário Macro** | SELIC 15%, IPCA 3,15%, CDI 14,65% + análise de impacto |
| **Recomendação PME** | Filtro por segmento → top-3 FIDCs recomendados |

> Para conectar ao Power BI, veja: [docs/powerbi_setup.md](docs/powerbi_setup.md)

---

## 🏗 Arquitetura

```
┌──────────────────────────────────────────────────────────────┐
│  FONTES: ANBIMA API · BCB/Focus · CVM                        │
└─────────────────────┬────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────┐
│  AZURE DATA FACTORY — pipeline diária (6h UTC)               │
└─────────────────────┬────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────┐
│  AZURE DATA LAKE STORAGE Gen2 (stdatatalake2026)             │
│                                                              │
│  🥉 Bronze → 🥈 Silver → 🥇 Gold                            │
│   CSV bruto   Parquet limpo  Parquet analítico + CSV         │
└─────────────────────┬────────────────────────────────────────┘
                      │ Databricks (Spark)
                      ▼
┌──────────────────────────────────────────────────────────────┐
│  DASHBOARD HTML (GitHub Pages) · Power BI Desktop            │
└──────────────────────────────────────────────────────────────┘
```

> Diagrama detalhado: [docs/arquitetura.md](docs/arquitetura.md)

---

## 📁 Estrutura do Repositório

```
radar-fidc/
│
├── 📄 index.html                    # Dashboard interativo (GitHub Pages)
├── 📄 .env.example                  # Variáveis de ambiente necessárias
├── 📄 requirements.txt              # Dependências Python
│
├── 📁 notebooks/                    # Pipeline de dados completa
│   ├── 📁 01_bronze_ingestao/       # Ingestão das fontes de dados
│   │   ├── etl_anbima.py            #   → ANBIMA API → ADLS Bronze
│   │   ├── etl_bcb.py               #   → BCB/Focus → ADLS Bronze
│   │   └── etl_cda.py               #   → CVM CDA → ADLS Bronze
│   │
│   ├── 📁 02_silver_tratamento/     # Limpeza e padronização
│   │   ├── etl_anbima.py            #   → Bronze → Silver (Parquet tipado)
│   │   ├── etl_macro.py             #   → Bronze → Silver (SELIC, IPCA, CDI)
│   │   └── etl_cda.py               #   → Bronze → Silver (carteira)
│   │
│   └── 📁 03_gold_modelagem/        # Modelo de score e recomendações
│       ├── 01_score_fidc.py         #   → Score ponderado por FIDC (0-100)
│       ├── 02_indicadores_macro.py  #   → Contexto macro atual
│       ├── 03_recomendacao_pme.py   #   → Matching PME × FIDC
│       ├── 04_dashboard_master.py   #   → Tabela consolidada Power BI
│       ├── 05_export_csv.py         #   → Export CSV para dashboard
│       └── orquestrador_gold.py     #   → Orquestra notebooks 01-05
│
└── 📁 docs/                         # Documentação técnica
    ├── arquitetura.md               #   Diagrama completo da pipeline
    ├── modelo_score.md              #   Como o score é calculado
    ├── fontes_dados.md              #   ANBIMA, BCB, CVM — schemas
    └── powerbi_setup.md             #   Guia de conexão Power BI
```

---

## ⚙️ Como Executar

### Pré-requisitos

- Python 3.10+
- Conta Azure com acesso ao ADLS Gen2
- Workspace Databricks configurado
- Credenciais ANBIMA API

### 1. Clonar o repositório

```bash
git clone https://github.com/victorsouza14/radar-fidc.git
cd radar-fidc
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com suas credenciais
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Executar a pipeline no Databricks

```bash
# Fazer upload dos notebooks para o Databricks e executar via API
# Veja documentação completa em docs/arquitetura.md
```

### 5. Abrir o dashboard

```bash
# Local
open index.html

# Online
# https://victorsouza14.github.io/radar-fidc
```

---

## 📡 Fontes de Dados

| Fonte | Dados | Documentação |
|-------|-------|-------------|
| **ANBIMA API** | Cadastro e histórico de FIDCs | [docs/fontes_dados.md](docs/fontes_dados.md) |
| **BCB — API SGS** | SELIC, IPCA, CDI | [docs/fontes_dados.md](docs/fontes_dados.md) |
| **BCB — Focus** | Projeções de mercado 12m | [docs/fontes_dados.md](docs/fontes_dados.md) |
| **CVM** | Informe mensal + carteira CDA | [docs/fontes_dados.md](docs/fontes_dados.md) |

---

## 🎯 Modelo de Score

Score ponderado de **0 a 100** por FIDC:

| Componente | Peso | Descrição |
|-----------|------|-----------|
| Retorno histórico | **40%** | Retorno médio normalizado |
| Risco / Volatilidade | **30%** | Inverso do desvio padrão |
| Cenário Macroeconômico | **20%** | SELIC, IPCA, projeções Focus |
| Liquidez | **10%** | Frequência de dados históricos |

**Classificação:**

| Classe | Score | Perfil |
|--------|-------|--------|
| 🟢 **A** | 80–100 | Excelente |
| 🟡 **B** | 60–79 | Bom |
| 🟠 **C** | 40–59 | Regular |
| 🔴 **D** | 0–39 | Atenção |

> Detalhes completos: [docs/modelo_score.md](docs/modelo_score.md)

---

## 👥 Time

**Data Fishermans** — FIAP | Sprint Final 2026

| Membro | RM |
|--------|-----|
| Victor de Souza Braga | RM567360 |

---

## 📄 Licença

Este projeto foi desenvolvido para fins acadêmicos — FIAP 2026.
Os dados de FIDCs são públicos e fornecidos pela ANBIMA e CVM.
