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

*2.489 FIDCs · ANBIMA + BCB + CVM · Atualização diária via GitHub Action*

</div>

---

## 📋 Índice

- [Problema e Solução](#-problema-e-solução)
- [Dashboard](#-dashboard)
- [Arquitetura](#-arquitetura)
- [Fluxo de Atualização](#-fluxo-de-atualização)
- [Estrutura do Repositório](#-estrutura-do-repositório)
- [Como Executar](#-como-executar)
- [Fontes de Dados](#-fontes-de-dados)
- [Modelo de Score](#-modelo-de-score)
- [Time](#-time)

---

## 💡 Problema e Solução

PMEs enfrentam dificuldades para acessar crédito com condições favoráveis. Os **FIDCs**
(Fundos de Investimento em Direitos Creditórios) são uma alternativa, mas existem
**+2.400 fundos** registrados na ANBIMA, com riscos e retornos muito diferentes.

O **Radar FIDC** automatiza essa análise:

- Calcula um **score 0–100** por FIDC com base em retorno, risco, cenário macro e liquidez.
- Casa o **perfil da PME** (segmento, necessidade, tolerância a risco) com os FIDCs mais aderentes.
- Atualiza diariamente conforme novos dados ANBIMA/BCB/CVM chegam.

---

## 📊 Dashboard

Acesse: **https://victorsouza14.github.io/radar-fidc**

| Página | O que mostra |
|--------|--------------|
| **Visão Geral** | KPIs + Top 10 FIDCs por score + tabela de ranking |
| **Score & Risco** | Distribuição por classe + scatter retorno × score |
| **Cenário Macro** | SELIC, IPCA, CDI + análise de impacto |
| **Recomendação PME** | Top-3 FIDCs por segmento com matching por aderência |

> Conexão Power BI: [docs/powerbi_setup.md](docs/powerbi_setup.md)

---

## 🏗 Arquitetura

```
ANBIMA · BCB · CVM
        ↓
Azure Data Factory (cron 6h UTC)
        ↓
ADLS Gen2 — Bronze (CSV) → Silver (Parquet) → Gold (Parquet + CSV)
        ↓                                         ↓
   Databricks                            gold/powerbi/*.csv
   notebooks Spark                              ↓
                                ┌────────────────┴────────────────┐
                                ↓                                 ↓
                    GitHub Action (cron 9h UTC)          Power BI Desktop
                    gera data.json e commita
                                ↓
                       GitHub Pages serve
                       dashboard atualizado
```

Detalhe: [docs/arquitetura.md](docs/arquitetura.md)

---

## 🔄 Fluxo de Atualização

O dashboard é **estático no GitHub Pages**, mas atualizado automaticamente:

1. **6h UTC** — Azure Data Factory dispara a pipeline Databricks.
2. Notebooks Bronze → Silver → Gold geram parquets e CSVs em `dfdatalakesprint/gold/final/`.
3. **9h UTC** — `.github/workflows/data-refresh.yml` (cron) executa
   `scripts/generate_dashboard_data.py`, que lê os arquivos do ADLS Gen2 (`gold/final/`), gera o `data.json` e
   commita no repositório se houve mudança.
4. GitHub Pages publica a nova versão automaticamente.

Para que o GitHub Action funcione, configure o secret `AZURE_CONNECTION_STRING` em
**Settings → Secrets and variables → Actions**.

---

## ⚙️ Workflows GitHub Actions

O repositório roda 3 workflows independentes em `.github/workflows/`:

| Workflow | Trigger | Função |
|----------|---------|--------|
| [`ci.yml`](.github/workflows/ci.yml) | `pull_request` para `main` + `push` em qualquer branch | Lint (`ruff check`), format check (`ruff format --check`), type check (`mypy`), unit tests (`pytest`) e secret scan (`gitleaks`) — todos em jobs paralelos com cache de pip. Target: ~2 min. Falha bloqueia merge via branch protection (ver [`docs/runbook.md`](docs/runbook.md)). |
| [`data-refresh.yml`](.github/workflows/data-refresh.yml) | `schedule` (cron `0 9 * * *` UTC) + `workflow_dispatch` | Lê o Gold do ADLS Gen2 (`dfdatalakesprint/gold/final/`), valida o secret `AZURE_CONNECTION_STRING`, regenera `data.json` e commita em `main` se houve mudança. Concorrência serializada (`cancel-in-progress: false`) para evitar commits pela metade. |
| [`notify-failures.yml`](.github/workflows/notify-failures.yml) | `workflow_run` (`completed`) sobre `data-refresh.yml` | Em falha: abre (ou comenta em) issue com label `data-refresh-failure` incluindo link do run, step que falhou e últimas 50 linhas do log. Em sucesso: fecha automaticamente as issues abertas com essa label. De-duplica por label para não inundar o repo. |

### Status checks obrigatórios em `main`

Depois do merge do `ci.yml`, ative branch protection com os 5 checks
listados em [`docs/runbook.md`](docs/runbook.md#status-checks-obrigatórios)
(`lint-python`, `lint-python-format`, `type-check`, `unit-tests`,
`secret-scan`). A ativação é manual — o GitHub não expõe a configuração
via REST API simples para `Allow specified actors to bypass`, que é
necessária para o `github-actions[bot]` continuar commitando `data.json`.

---

## 📁 Estrutura do Repositório

```
radar-fidc/
├── index.html                          # Dashboard (carrega data.json via fetch)
├── data.json                           # Dados atuais — gerado pelo pipeline
├── .env.example                        # Template de variáveis de ambiente
├── requirements.txt                    # Dependências Python
│
├── .github/workflows/
│   ├── ci.yml                          # PR/push checks (ruff + mypy + pytest + gitleaks)
│   ├── data-refresh.yml                # GitHub Action de atualização diária (lê ADLS → data.json)
│   └── notify-failures.yml             # Reaction workflow: issues automáticas em falha do data-refresh
│
├── scripts/
│   └── generate_dashboard_data.py      # ADLS gold/final/ → data.json
│
├── notebooks/
│   ├── _common.py                      # Helper compartilhado (secrets)
│   │
│   ├── 01_bronze_ingestao/             # Ingestão das fontes
│   │   ├── etl_anbima.py               #   ANBIMA API → ADLS Bronze
│   │   ├── etl_bcb.py                  #   BCB/SGS → ADLS Bronze
│   │   └── etl_cda.py                  #   CVM CDA → ADLS Bronze
│   │
│   ├── 02_silver_tratamento/           # Limpeza e padronização
│   │   ├── etl_anbima.py
│   │   ├── etl_macro.py
│   │   └── etl_cda.py
│   │
│   └── 03_gold_modelagem/              # Modelagem analítica
│       ├── 00_schema_report.py         #   Validação de schemas Silver
│       ├── 01_score_fidc.py            #   Score por FIDC (percentil)
│       ├── 02_indicadores_macro.py     #   Indicadores macro consolidados
│       ├── 03_recomendacao_pme.py      #   Matching PME × FIDC por segmento
│       ├── 04_dashboard_master.py      #   Tabela mestre
│       ├── 05_export_csv.py            #   Parquet → CSV (Power BI)
│       └── orquestrador_gold.py        #   Roda 00–05 em sequência
│
└── docs/                               # Documentação técnica
    ├── arquitetura.md
    ├── modelo_score.md
    ├── fontes_dados.md
    └── powerbi_setup.md
```

---

## ⚙️ Como Executar

### Pré-requisitos

- Python 3.10+
- Acesso ao ADLS Gen2 (`dfdatalakesprint`) — connection string (rotacionada trimestralmente)
- Credenciais ANBIMA (Client ID / Secret) — se for rodar a ingestão
- Workspace Databricks — para executar os notebooks em produção

### 1. Clonar e instalar

```bash
git clone https://github.com/victorsouza14/radar-fidc.git
cd radar-fidc
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variáveis

```bash
cp .env.example .env
# Preencher AZURE_CONNECTION_STRING, ANBIMA_CLIENT_ID, ANBIMA_CLIENT_SECRET
export $(grep -v '^#' .env | xargs)
```

### 3. Pipeline completa no Databricks

Faça upload da pasta `notebooks/` para o workspace e execute na ordem:

```
01_bronze_ingestao/* → 02_silver_tratamento/* → 03_gold_modelagem/orquestrador_gold.py
```

Os notebooks usam `_common.azure_connection_string()`, que resolve automaticamente
entre Databricks Secret Scope (`scope=escopo`, `key=AZURECONNSTRING`) e `os.environ`.

### 4. Atualizar o dashboard localmente

```bash
# Carrega .env (precisa AZURE_CONNECTION_STRING válida para dfdatalakesprint)
set -a && source .env && set +a

# Gera data.json lendo direto do ADLS
python scripts/generate_dashboard_data.py

# Saída customizada (útil para diff)
python scripts/generate_dashboard_data.py --output /tmp/data.json
```

O cache local em `.cache/` (ignorado pelo Git) acelera execuções subsequentes
via validação de ETag — só re-baixa arquivo que mudou no Gold.

### 5. Servir o dashboard

```bash
# Local
python -m http.server 8000
# abre http://localhost:8000

# Online
# https://victorsouza14.github.io/radar-fidc
```

---

## 📡 Fontes de Dados

| Fonte | Dados | Documentação |
|-------|-------|--------------|
| **ANBIMA API** | Cadastro e histórico de FIDCs | [docs/fontes_dados.md](docs/fontes_dados.md) |
| **BCB — SGS** | SELIC, IPCA, CDI, indicadores macro | [docs/fontes_dados.md](docs/fontes_dados.md) |
| **CVM CDA** | Composição da carteira mensal | [docs/fontes_dados.md](docs/fontes_dados.md) |

---

## 🔒 LGPD e Limitações conhecidas

### Tratamento de PII

O dataset `clientes.csv` (em `gold/final/clientes.csv` no ADLS) contém dados de teste/acadêmicos com nomes
fictícios. Mesmo assim, **todos os campos PII** (CPF, e-mail, telefone, nome
completo) são **mascarados** antes de chegarem ao `data.json` público:

| Campo | Exemplo no JSON | Helper |
|---|---|---|
| CPF | `***.***.***-41` | `mask_cpf` |
| Nome | `Ana L.` | `mask_name` |
| E-mail | `c***@****.com` | `mask_email` |
| Telefone | `(11) ****-8753` | `mask_phone` |
| Hash de empresa (credit) | `EMP-D510A11A` | `_anon_id` |

Helpers em [`scripts/lib/formatters.py`](scripts/lib/formatters.py).

### Limitações dos modelos

- **Rating FIDC**: clusters K-Means podem oscilar entre runs em datasets muito homogêneos; usar `random_state=42`.
- **Projeções macro**: `selic_proj` e `ipca_proj` são heurísticas (`selic - 0.5`, `ipca × 0.9`), sinalizadas via `is_proj_heuristica: true`.
- **Credit model**: snapshot single-cohort, sem variáveis macro nas features.
- **Match**: ignora segmento de atuação do FIDC; sem bloqueio CVM 555.

Detalhes:
- [docs/modelo_score.md](docs/modelo_score.md)
- [docs/credit_model.md](docs/credit_model.md)
- [docs/match_engine.md](docs/match_engine.md)

---

## 🎯 Modelo de Score

Score ponderado de **0 a 100** por FIDC, com **normalização por percentil**
(robusto a outliers e produz distribuição realista A/B/C/D):

| Componente | Peso | Descrição |
|-----------|------|-----------|
| Retorno histórico | **40%** | Percentil do retorno médio 12m |
| Risco / Volatilidade | **30%** | Percentil inverso (cap p99) |
| Cenário Macro | **20%** | Variável por indexador (CDI+/pré/indef.) |
| Liquidez | **10%** | Percentil do número de observações |

Classificação:

| Classe | Score |
|--------|-------|
| 🟢 **A** | 80–100 |
| 🟡 **B** | 60–79 |
| 🟠 **C** | 40–59 |
| 🔴 **D** | 0–39 |

Detalhes: [docs/modelo_score.md](docs/modelo_score.md)

---

## 👥 Time

**Data Fishermans** — FIAP | Sprint Final 2026

| Membro | RM |
|--------|-----|
| Victor de Souza Braga | RM567360 |
| Andre Marques | RM566584 |
| Jony Wesley Sousa Melo | RM567392 |
| Diogo Alves Moitinho | RM566652 |
| Fernando Florence | RM567445 |

---

## 📄 Licença

Projeto desenvolvido para fins acadêmicos — FIAP 2026.
Os dados de FIDCs são públicos e fornecidos pela ANBIMA, BCB e CVM.
