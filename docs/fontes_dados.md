# Fontes de Dados — Radar FIDC

## 1. ANBIMA — Associação Brasileira das Entidades dos Mercados Financeiro e de Capitais

**Endpoint**: `https://api.anbima.com.br/feed/fundos/v1/`

| Dataset | Endpoint | Descrição | Frequência |
|---------|----------|-----------|------------|
| `fundos_v2_fidc` | `/fundos/v2` | Cadastro completo dos FIDCs: nome, tipo, gestor, CNPJ | Diária |
| `dados_cadastrais_fidc` | `/dados-cadastrais` | Dados cadastrais detalhados dos fundos | Semanal |
| `serie_historica_fidc` | `/series-historicas` | Série histórica de cotas e retornos por fundo | Diária |

### Campos Principais

```
fundos_v2_fidc:
  codigo_fundo          → identificador interno ANBIMA (ex: F0000123951)
  identificador_fundo   → CNPJ do fundo (ex: 06018364000185)
  razao_social_fundo    → nome completo do fundo
  tipo_fundo            → FIDC, FIDC-NP, etc.
  classes               → lista de classes/subclasses (Senior, Mez., Sub.)

serie_historica_fidc:
  codigo_fundo          → chave de join com fundos_v2
  data                  → data da cota
  valor_cota            → valor da cota no dia
  rentabilidade         → rentabilidade do período
  patrimonio_liquido    → PL em R$
```

### Autenticação
- Client ID + Client Secret via OAuth 2.0
- Token com validade de 1 hora (renovação automática no ETL)

---

## 2. Banco Central do Brasil (BCB) — API Dados Abertos

**Base URL**: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados`

| Indicador | Código SGS | Descrição |
|-----------|-----------|-----------|
| SELIC | 11 | Taxa SELIC diária (% a.a.) |
| IPCA | 433 | IPCA mensal (variação %) |
| CDI | 12 | Taxa CDI diária (% a.a.) |
| SELIC meta | 432 | Meta SELIC definida pelo COPOM |

### Boletim Focus (Expectativas de Mercado)
**Endpoint**: `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/`

| Dado | Descrição |
|------|-----------|
| `ExpectativasMercadoTop5Anuais` | Projeções SELIC e IPCA (mediana das top 5 instituições) para os próximos 12 meses |

---

## 3. CVM — Comissão de Valores Mobiliários

**Portal**: `https://dados.cvm.gov.br/`

| Dataset | Arquivo | Descrição |
|---------|---------|-----------|
| Informe Mensal FIDC | `inf_mensal_fidc_AAAAMM.csv` | PL, captação, resgates mensais |
| CDA — Carteira | `cda_fi_AAAAMM.zip` | Composição da carteira de ativos por fundo |

---

## Arquitetura de Armazenamento

```
ADLS Gen2 — dfdatalakesprint
│
├── bronze/
│   ├── anbima/
│   │   ├── fundos_v2_fidc.csv
│   │   ├── dados_cadastrais_fidc.csv
│   │   └── serie_historica_fidc.csv
│   ├── dados_macroeconomicos/
│   │   ├── selic.csv
│   │   ├── ipca.csv
│   │   ├── cdi.csv
│   │   └── focus_expectativas.csv
│   └── cda/
│       └── cda_mensal_AAAAMM.csv
│
├── silver/
│   ├── anbima/
│   │   ├── fundos_v2_fidc.parquet
│   │   └── serie_historica_fidc.parquet
│   ├── dados_macroeconomicos/
│   │   └── consolidado.parquet
│   └── cda/
│       └── carteira_mensal.parquet
│
└── gold/
    ├── final/                                  # outputs analíticos canônicos
    │   ├── rating_fidc.xlsx                    # abas GERAL, RESUMO_POR_FUNDO
    │   ├── matches.xlsx                        # abas TODOS_OS_MATCHES, RANKING_FUNDOS, etc.
    │   ├── clientes.csv                        # base de clientes (PII em claro, mascarada no payload)
    │   ├── scores_credito.csv                  # output do credit model
    │   ├── _quality/
    │   │   └── expectations-result.json        # resultado Great Expectations (Fase 3)
    │   ├── macroeconomicos/
    │   │   └── consolidade.csv                 # série histórica BCB (SELIC, IPCA, CDI, inad PJ)
    │   ├── anbima/                             # snapshots ANBIMA tratados
    │   │   ├── *.csv
    │   │   └── *.parquet
    │   ├── cda/
    │   │   └── cda_fi_AAAAMM.{csv,parquet}     # composição de carteira mensal
    │   └── info_mensal/
    │       └── inf_mensal_fidc_tab_*.{csv,parquet}
    │
    ├── indicadores_macro/
    │   └── indicadores.parquet                 # consolidado Focus (selic_proj, ipca_proj)
    │
    └── powerbi/                                # legacy — consumo Power BI Desktop
        ├── score_fidc.csv
        ├── ranking_fidcs.csv
        ├── indicadores_macro.csv
        ├── recomendacao_pme.csv
        └── dashboard_master.csv
```

### Mapeamento arquivo → consumidor

| Arquivo | Consumido por | Como entra no `data.json` |
|---------|---------------|---------------------------|
| `gold/final/rating_fidc.xlsx` | `scripts/generate_dashboard_data.py` via `io_utils.read_rating` | `payload.build_fidcs` |
| `gold/final/matches.xlsx` | `scripts/generate_dashboard_data.py` via `io_utils.read_matches` | `payload.build_matches` |
| `gold/final/clientes.csv` | `scripts/generate_dashboard_data.py` via `io_utils.read_clientes` | `payload.build_clientes` (com mascaramento PII) |
| `gold/final/scores_credito.csv` | `scripts/generate_dashboard_data.py` via `io_utils.read_credit_scores` | `payload.build_credit` |
| `gold/final/macroeconomicos/consolidade.csv` | `scripts/generate_dashboard_data.py` via `io_utils.read_macro` | `payload.build_macro` (histórico) |
| `gold/final/_quality/expectations-result.json` | workflow `data-refresh.yml` (step "Validate GE") | `data-quality.json#pipeline_quality_check` |
| `gold/indicadores_macro/indicadores.parquet` | `scripts/generate_dashboard_data.py` via `io_utils.read_focus_indicators` | `payload.build_macro` (projeções Focus) |
| `gold/powerbi/*.csv` | Power BI Desktop (conexão direta ADLS) | — (não entra no `data.json`) |
| `gold/final/anbima/*`, `gold/final/cda/*`, `gold/final/info_mensal/*` | Staging dos notebooks Databricks (insumo Gold→Gold) | — (não entra no `data.json`) |

## Volume de Dados (referência março/2026)

| Camada | Registros | Tamanho |
|--------|-----------|---------|
| Bronze ANBIMA | ~150k cotas históricas | ~45 MB |
| Silver ANBIMA | ~150k registros | ~18 MB |
| Gold `final/rating_fidc.xlsx` | 6.100 FIDCs | ~1.4 MB |
| Gold `powerbi/` | 5 arquivos CSV | ~1.1 MB |
