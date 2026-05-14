<div align="center">

# Radar FIDC

Plataforma de análise, scoring e recomendação de FIDCs para PMEs.

[![Dashboard](https://img.shields.io/badge/dashboard-live-brightgreen)](https://victorsouza14.github.io/radar-fidc)
[![Python](https://img.shields.io/badge/python-3.11-blue)](https://python.org)
[![Azure Data Lake Gen2](https://img.shields.io/badge/storage-ADLS%20Gen2-0089D6)](https://azure.microsoft.com)
[![Databricks](https://img.shields.io/badge/compute-Databricks-FF3621)](https://databricks.com)
[![License](https://img.shields.io/badge/license-academic-lightgrey)](#licença)

**[Acessar dashboard →](https://victorsouza14.github.io/radar-fidc)**

</div>

---

## Sumário

- [O que é](#o-que-é)
- [Páginas do dashboard](#páginas-do-dashboard)
- [Arquitetura](#arquitetura)
- [Stack](#stack)
- [Como rodar localmente](#como-rodar-localmente)
- [Pipeline automatizado](#pipeline-automatizado)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Testes](#testes)
- [Privacidade (LGPD)](#privacidade-lgpd)
- [Operação](#operação)
- [Time](#time)
- [Licença](#licença)

---

## O que é

PMEs têm dificuldade de acessar crédito em condições competitivas. Os **FIDCs** (Fundos de Investimento em Direitos Creditórios) são uma alternativa relevante, mas existem mais de 6.000 classes registradas, com perfis de risco e retorno muito heterogêneos.

O Radar FIDC consolida três blocos para apoiar a decisão:

- **Análise comparativa de FIDCs** — score de risco, retorno, volatilidade e perfil sugerido por classe.
- **Engine de match cliente × fundo** — alinha o perfil do investidor (cadastro) aos FIDCs disponíveis e devolve top-3 recomendações.
- **Credit scoring de empresas pagadoras** — score de crédito por CNPJ enriquecido com setor (CNAE) e UF.

Tudo materializado em um `data.json` único, servido como SPA estática no GitHub Pages.

---

## Páginas do dashboard

| Página | O que mostra |
|---|---|
| **Visão geral** | KPIs principais (FIDCs analisados, clientes cadastrados, empresas avaliadas) + cenário macroeconômico (SELIC atual, CDI, IPCA 12m, projeções Focus) + Top 10 FIDCs ajustados por risco. |
| **FIDCs** | Tabela paginada com filtros (busca, risco, tipo de cota, perfil), card de estatísticas com IQR (retorno máx/mín, volatilidade, inadimplência, score) e scatter Risco × Retorno em escala log. |
| **Recomendações** | Match cliente × fundo: seletor de cliente, top-3 fundos por score e ranking agregado dos fundos mais recomendados. |
| **Credit scoring** | Empresas pagadoras com score 0-100, probabilidade de default, setor (CNAE), UF e flag `dados_suficientes` (gating em ≥ 20 boletos). |

---

## Arquitetura

```
ANBIMA · BCB · CVM
        ↓
Azure Data Factory (cron 6h UTC)
        ↓
ADLS Gen2 — Bronze (CSV) → Silver (Parquet) → Gold (Parquet + XLSX)
        ↓
   Databricks (notebooks Spark)
        ↓
ADLS Gen2 — gold/final/  (rating_fidc.xlsx, matches.xlsx, clientes.csv,
                          scores_credito.csv, macroeconomicos/, ...)
        ↓
GitHub Action (cron 9h UTC) ← AZURE_CONNECTION_STRING (secret)
        ↓
generate_dashboard_data.py
  • lê o Gold (Account Key auth)
  • valida cada DataFrame contra pandera (lazy=True)
  • escreve data.json + data-quality.json
        ↓
GitHub Pages serve a SPA (index.html + assets/)
```

Detalhes em [`docs/arquitetura.md`](docs/arquitetura.md).

---

## Stack

**Backend (pipeline)**
- Python 3.11 · pandas · pyarrow · openpyxl
- pandera (DataFrameModels com `lazy=True`, `strict=False`)
- azure-storage-file-datalake (Account Key + ETag cache)
- structlog (JSON logs)

**Frontend (dashboard)**
- HTML + JavaScript ES modules (vanilla — sem framework, sem build step)
- Chart.js 4 (doughnut, horizontal bar, scatter log-Y)
- CSS custom properties (tokens em `assets/css/tokens.css`)

**Infraestrutura**
- Azure Data Lake Storage Gen2 (`dfdatalakesprint/gold/final/`)
- GitHub Actions (CI + data refresh agendado + notifier de falhas)
- GitHub Pages (hospedagem da SPA)

**Qualidade**
- pytest (unit) — 196 testes verdes, cobertura > 90% em `scripts/lib/`
- Playwright (smoke e2e) — 5 cenários cobrindo KPIs, gráficos, tabelas
- ruff (lint + format) · mypy (strict)
- gitleaks (secret scan no CI)

---

## Como rodar localmente

### Pré-requisitos

- Python 3.11+
- Node 20+ (apenas para rodar os e2e)
- Connection string da conta ADLS Gen2 com leitura em `gold/final/`

### Setup

```bash
git clone https://github.com/victorsouza14/radar-fidc.git
cd radar-fidc

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
# Edite .env e preencha AZURE_CONNECTION_STRING.
```

### Gerar `data.json`

```bash
set -a && source .env && set +a
python scripts/generate_dashboard_data.py
```

O parse cache em `.cache/` (gitignored) acelera execuções subsequentes via comparação de ETag — só re-baixa arquivo que mudou no Gold.

Flags úteis:

```bash
python scripts/generate_dashboard_data.py --output /tmp/data.json
python scripts/generate_dashboard_data.py --regression-result pass --smoke-result pass
```

### Servir a SPA

```bash
python -m http.server 8000
# abre http://localhost:8000
```

Tudo é estático: `index.html` carrega `assets/js/main.js`, que busca `data.json?v=<timestamp>` (cache-busting) e hidrata o `Store`.

---

## Pipeline automatizado

Três workflows independentes em `.github/workflows/`:

| Workflow | Trigger | Função |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | PR + push em qualquer branch | Lint (ruff), format check, type check (mypy), unit tests (pytest) e secret scan (gitleaks) em jobs paralelos. ~2 min. |
| [`data-refresh.yml`](.github/workflows/data-refresh.yml) | Cron `0 9 * * *` UTC + dispatch manual | Lê o Gold do ADLS, regenera `data.json` + `data-quality.json`, roda regression check contra HEAD~1 e commita em `main` se houve mudança. |
| [`notify-failures.yml`](.github/workflows/notify-failures.yml) | `workflow_run` sobre o data-refresh | Em falha: abre/comenta issue com label `data-refresh-failure`. Em sucesso: fecha as issues abertas. De-duplica por label. |

Secrets obrigatórios em **Settings → Secrets and variables → Actions**:

- `AZURE_CONNECTION_STRING` — connection string da conta `dfdatalakesprint`.

---

## Estrutura do repositório

```
radar-fidc/
├── index.html                       # SPA shell (carrega data.json)
├── data.json                        # Payload atual (gerado pelo pipeline)
├── data-quality.json                # Manifesto de auditoria server-side
├── .env.example                     # Template de variáveis
├── requirements.txt                 # Runtime Python
├── requirements-dev.txt             # Dev tools (pytest, ruff, mypy, ...)
├── package.json                     # Playwright + servidor estático
│
├── .github/workflows/               # ci · data-refresh · notify-failures
│
├── assets/
│   ├── css/                         # tokens · base · components · layout · main
│   └── js/
│       ├── main.js                  # Bootstrap: carrega data.json e registra rotas
│       ├── router.js                # SPA sem hash routing — toggle .active
│       ├── store.js                 # Estado imutável + isValid()
│       ├── theme.js                 # RISCO_ORDER / PERFIL_ORDER + tokens de cor
│       ├── ui.js                    # Sidebar, theme menu, keyboard shortcuts
│       ├── components/              # chart-factory · paginated-table · empty-state
│       │                            # · fetch-error · select · table
│       ├── pages/                   # overview · fidcs · match · credit
│       └── utils/                   # dom · format · memo · pagination
│
├── scripts/
│   ├── generate_dashboard_data.py   # ADLS Gold → data.json + data-quality.json
│   ├── run_regression_check.py      # Diff sanity vs HEAD~1 (CI)
│   ├── smoke_summary.py             # Resumo dos e2e Playwright (CI)
│   ├── update_operacao_doc.py       # Append em docs/operacao.md + historico-runs.csv
│   ├── lib/
│   │   ├── azure_io.py              # ADLS Gen2 client + ETag + parse cache (.feather)
│   │   ├── cnae_setor.py            # CNAE 2.0 → divisão IBGE (setor humano)
│   │   ├── formatters.py            # Máscaras LGPD + helpers numéricos
│   │   ├── gold_paths.py            # Constantes de paths no Gold
│   │   ├── io_utils.py              # Readers + pandera validation por seção
│   │   ├── logger.py                # structlog JSON
│   │   ├── payload.py               # Builders por seção do data.json (puros)
│   │   ├── perfil_rules.py          # Tabelas TIPO_COTA × CATEGORIA_RISCO
│   │   ├── regression_check.py      # Lógica do diff vs HEAD~1
│   │   ├── scenario.py              # Classificação de cenário macro (SELIC)
│   │   ├── schemas.py               # DataFrameModels pandera
│   │   └── trust_manifest.py        # Builder do data-quality.json
│   └── tests/                       # pytest — ~196 testes cobrindo lib/*
│
├── notebooks/                       # Pipeline Databricks (Bronze · Silver · Gold)
│
├── tests/e2e/dashboard.spec.ts      # Playwright — smoke tests da SPA
├── playwright.config.ts
│
└── docs/
    ├── arquitetura.md               # Visão geral end-to-end
    ├── fontes_dados.md              # ANBIMA + BCB + CVM + shape do Gold
    ├── runbook.md                   # Incidentes, rotação de Account Key, gates
    ├── operacao.md                  # Auto-gerado: últimas runs + SLOs
    └── historico-runs.csv           # Append-only de cada run do data-refresh
```

---

## Testes

```bash
# Unit (Python) — ~196 testes, < 1s
cd scripts && python -m pytest

# Cobertura
cd scripts && python -m pytest --cov=lib --cov-report=term-missing

# Smoke e2e (Playwright)
npm install
npm run test:e2e:install     # baixa Chromium
npm run serve &              # python -m http.server 8000
npm run test:e2e
```

Os testes Python são **herméticos**: nada bate no ADLS. Cada reader é exercitado com fixtures que replicam a forma do Gold (snapshot 2026-05-14) e validadores monkeypatched do `azure_io`.

---

## Privacidade (LGPD)

`clientes.csv` e `matches.xlsx` contêm dados acadêmicos com nomes fictícios. Mesmo assim, **toda PII é mascarada** no builder antes de chegar ao `data.json` público:

| Campo | Exemplo emitido | Helper |
|---|---|---|
| CPF | `***.***.***-41` | `mask_cpf` |
| Nome | `Ana L.` | `mask_name` |
| E-mail | `c***@****.com` | `mask_email` |
| Empresa (credit) | `Empresa A3B5C2D9E5F1` | `_nome_empresa` (12 hex do SHA-256 do CNPJ) |

Telefone, renda, experiência, horizonte e data de cadastro **não são emitidos** no payload — ficam apenas no Gold para uso interno do match engine.

Helpers em [`scripts/lib/formatters.py`](scripts/lib/formatters.py); regressão de PII coberta em [`scripts/tests/test_formatters_mask.py`](scripts/tests/test_formatters_mask.py).

---

## Operação

| Documento | Para que serve |
|---|---|
| [`docs/runbook.md`](docs/runbook.md) | Playbook: gates do CI, rotação de Account Key, modos de falha, gestão de heurísticas. |
| [`docs/operacao.md`](docs/operacao.md) | Estado atual auto-atualizado: último run, últimos 14 runs, SLOs alvo. |
| [`docs/historico-runs.csv`](docs/historico-runs.csv) | Append-only de cada execução do `data-refresh.yml`. |
| `data-quality.json` | Manifesto server-side: schema validation, freshness por fonte, heurísticas ativas, GE result. Consumido pelo `update_operacao_doc.py`. |

---

## Time

**Data Fishermans** — FIAP, Sprint Final 2026.

| Membro | RM |
|---|---|
| Victor de Souza Braga | RM567360 |
| Andre Marques | RM566584 |
| Jony Wesley Sousa Melo | RM567392 |
| Diogo Alves Moitinho | RM566652 |
| Fernando Florence | RM567445 |

---

## Licença

Projeto desenvolvido para fins acadêmicos (FIAP, 2026). Os dados de FIDCs são públicos e fornecidos por ANBIMA, BCB e CVM.
