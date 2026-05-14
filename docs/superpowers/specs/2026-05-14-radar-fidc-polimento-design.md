# Radar FIDC — Polimento para Production-Ready

**Data:** 2026-05-14
**Status:** Design aprovado pelo usuário
**Escopo:** Evoluir a plataforma atual (GitHub Pages + Databricks + data.json) para um padrão "production-ready" mantendo a arquitetura estática. Conectar `generate_dashboard_data.py` ao ADLS real, adicionar trust layer (schema validation, GE, manifest), eliminar 4 heurísticas conhecidas, endurecer CI/CD e observabilidade.

**O que NÃO está em escopo:** pivô para SaaS, backend dedicado, multi-tenant, autenticação de usuário, mobile app nativo, microsserviços.

---

## Contexto crítico

O briefing inicial descrevia "evoluir frontend mockado para plataforma integrada". A descoberta na exploração do código:

1. **Pipeline real já existe**: Bronze→Silver→Gold em Databricks/Spark + Azure Data Factory + ADLS Gen2. Não é mockado.
2. **Disconexão arquitetural real**: o `scripts/generate_dashboard_data.py` lê `data_real/` (local), não o ADLS. O README documenta um fluxo que não corresponde ao código. Isso explica a percepção de "dados mockados/incorretos" — o dashboard mostra a foto local, desconectada do estado atual do Gold.
3. **Storage account mudou**: README aponta `stdatatalake2026`; fonte de verdade atual é `dfdatalakesprint/gold/final/`.
4. **Security incident**: Account Key foi exposta no chat. Precisa rotacionar.
5. **4 heurísticas documentadas**: selic_proj/ipca_proj (heurísticos), credit model single-cohort, match engine sem segmento+CVM 555, K-Means "instável" (causa real é feature scaling drift, não o algoritmo).

O usuário escolheu **Abordagem C** (máxima profundidade, mantendo arquitetura estática). Account Key permanece como método de auth (sem migração para Service Principal/OIDC) por restrição de acesso ao tenant AAD.

---

## Seção 1 — Visão arquitetural alvo

```
FONTES PÚBLICAS (ANBIMA · BCB/SGS · CVM CDA · Boletim Focus*)
      │ ingestão diária 6h UTC (Azure Data Factory)
      ▼
ADLS Gen2 — dfdatalakesprint
  ┌──────┐   ┌──────┐   ┌─────────────────────────────┐
  │bronze│ → │silver│ → │ gold/final/                 │
  │ CSV  │   │parquet│  │ ├─ rating_fidc.xlsx         │
  └──────┘   └──────┘   │ ├─ matches.xlsx             │
                        │ ├─ scores_credito.csv       │
                        │ ├─ clientes.csv             │
                        │ ├─ credit_model.pkl         │
                        │ ├─ macroeconomicos/*.csv    │
                        │ ├─ anbima/, cda/, info_mensal/│
                        │ └─ _quality/expectations-result.json (NOVO) │
                        └────────────┬────────────────┘
                                     │ Service Principal indisponível →
                                     │ usa AZURE_CONNECTION_STRING (rotacionado)
                                     ▼
GitHub Actions runner
  ├─ pandera valida schemas dos DataFrames
  ├─ valida GE result do Databricks
  ├─ gera data.json + data-quality.json
  ├─ regression check vs HEAD~1
  ├─ Playwright smoke test (6 páginas)
  └─ commit + push se tudo passou
                                     │
                                     ▼
GitHub Pages
  ├─ index.html
  ├─ data.json
  ├─ data-quality.json (NOVO)
  └─ assets/js/ (lê manifest, mostra trust bar + heuristic markers)
```

**O que muda:**
- `generate_dashboard_data.py` lê ADLS, não `data_real/`
- `data_real/` removido do repo (vai pro `.gitignore`)
- Novo `data-quality.json` como contrato de confiança
- Frontend ganha trust bar + heuristic markers + empty/error states
- 3 workflows no lugar de 1
- Pre-commit hooks + branch protection

**O que NÃO muda:** frontend HTML+JS vanilla, hosting GitHub Pages, cadência batch diária, pipeline Databricks.

---

## Seção 2 — Segurança, RBAC e segredos

**Decisão do usuário:** continuar com Account Key (não migrar para Service Principal/OIDC).

**Mitigações compulsórias:**

1. Rotacionar a Account Key vazada antes de qualquer commit
2. Calendário de rotação trimestral documentado no README
3. Pre-commit hook com `gitleaks` bloqueando padrões de Azure connection string
4. GitHub push protection habilitado (Settings → Code security → Secret scanning + push protection)
5. Auditar histórico do Git por leak prévio (`git log -p | grep -E "AccountKey="`); se encontrado, purgar com `git filter-repo`

**Onde a chave vive:**

| Contexto | Storage |
|----|----|
| CI | GitHub Secret `AZURE_CONNECTION_STRING` |
| Pipeline Databricks | Secret Scope `escopo`, key `AZURECONNSTRING` (já existe) |
| Dev local | `.env` (no `.gitignore`) |

**LGPD:** camada de mascaramento `scripts/lib/formatters.py` permanece. Teste regressivo novo: dado payload com PII conhecida, garantir que o `data.json` gerado não contém regex de CPF/email/telefone reais.

**Threat model — defende contra:**
- ✅ PII em commit público (mask + regressão)
- ✅ Schema drift quebrando dashboard silenciosamente
- ✅ Pipeline gravando lixo no Gold (GE barra promoção)
- ✅ Re-leak da Account Key via commit (gitleaks + push protection)

**Threat model — NÃO defende contra:**
- ❌ Vazamento de Account Key por canal não-Git (chat, screen share)
- ❌ Comprometimento de conta GitHub de mantenedor
- ❌ Account Key não tem least-privilege (RW total no storage account)

---

## Seção 3 — Camada de acesso ao Data Lake

### Mapa de origem dos arquivos do `gold/final/`

| Arquivo no ADLS | Lido pelo script | Página do dashboard |
|----|----|----|
| `rating_fidc.xlsx` | `io_utils.read_rating()` | Visão Geral, Score & Risco, FIDCs |
| `matches.xlsx` | `io_utils.read_matches()` | Recomendação PME, Match |
| `clientes.csv` | `io_utils.read_clientes()` | Clientes (PII mascarado) |
| `scores_credito.csv` | `io_utils.read_credit_scores()` | Credit |
| `macroeconomicos/*.csv` | `io_utils.read_macro()` | Cenário Macro |
| `credit_model.pkl` | ❌ não carregar no CI | Treinado no Databricks |
| `anbima/`, `cda/`, `info_mensal/`, `base_*.{csv,xlsx}` | ❌ inputs do Databricks | — |

### Módulos novos

```
scripts/lib/azure_io.py
  get_filesystem_client() → DataLakeServiceClient cacheado
  download_to_bytes(path) → bytes em memória com retry exponencial
  download_to_cache(path) → grava em ./.cache/<path>, valida ETag
  read_csv(path, **kwargs)
  read_excel(path, sheet)
  list_dir(path)
  blob_etag(path)

scripts/lib/gold_paths.py
  GOLD_FILESYSTEM = "gold"
  GOLD_FINAL = "final"
  PATHS = {
      "rating":    f"{GOLD_FINAL}/rating_fidc.xlsx",
      "matches":   f"{GOLD_FINAL}/matches.xlsx",
      "clientes":  f"{GOLD_FINAL}/clientes.csv",
      "credit":    f"{GOLD_FINAL}/scores_credito.csv",
      "macro_dir": f"{GOLD_FINAL}/macroeconomicos/",
  }
```

### Cache de 2 camadas

1. **Byte cache** (`./.cache/gold/final/*.{csv,xlsx}`) — valida via ETag (HEAD blob)
2. **Parse cache** (`./.cache/gold/final/*.parsed.pkl`) — DataFrame serializado, evita re-parse openpyxl

Cache no `.gitignore`. CI tem cache resetado a cada run (proposital). Local persiste.

### Retry & error handling

SDK Azure já tem retry exponencial. Config explícita:
- `retry_total=5`, `retry_backoff_factor=0.5`, status codes 5xx
- Erros 401/403 NÃO sofrem retry (fail fast)

### Custos & limites

- Volume total Gold lido: ~10 MB/run
- Egress: <R$0,01/run
- Bottleneck real: parse `.xlsx` (~3-5s). Mitigado via parse cache.

---

## Seção 4 — Validação & data quality (3 linhas de defesa)

### Linha 1: Great Expectations no Databricks (pipeline-side)

Suite por DataFrame, **full** (30+ expectativas distribuídas). Exemplos:

| DataFrame | Expectativas |
|----|----|
| rating_fidc | score ∈ [0,100]; classe ∈ {A,B,C,D}; CNPJ unique + regex; row_count ∈ [2000,3000]; CATEGORIA_RISCO ∈ {BAIXO,MEDIO,ALTO} |
| macro | SELIC ∈ [0,50]; IPCA ∈ [-5,30]; data_ref not null; consistência cronológica |
| matches | match_score ∈ [0,100]; CNPJ_FUNDO not null; PME_id referenciado em clientes |
| clientes (pré-mask) | CPF regex `^\d{11}$`; segmento ∈ enum conhecido |
| credit | scoring ∈ [0,1000]; modelo_version present; trained_at not null |

Resultado em `gold/final/_quality/expectations-result.json`. Se `overall_success: false`, pipeline grava em `gold/staging/`, NÃO promove para `gold/final/`.

### Linha 2: Pandera no CI (consumer-side)

`scripts/lib/schemas.py` com `pa.DataFrameModel` por DataFrame. Aplicado dentro de cada `read_*()`. Fail fast se schema drift.

### Linha 3: Regression check entre runs

Compara `data.json` atual com `HEAD~1`:
- `|Δ fidcs.total / fidcs.total_anterior| < 10%`
- `|Δ matches.total / matches.total_anterior| < 20%`
- `macro.data_ref >= macro.data_ref_anterior`

Override: label `data-regression-ok` no PR ou `bypass_regression_check: true` no `workflow_dispatch`.

### Manifesto `data-quality.json`

Schema:

```json
{
  "generated_at": "ISO-8601 UTC",
  "pipeline_quality_check": {
    "ts": "...",
    "source": "great_expectations",
    "overall_success": true,
    "suites_passed": 6,
    "suites_failed": 0
  },
  "ci_quality_check": {
    "schema_validation": "pass|fail",
    "regression_check": "pass|fail|bypassed",
    "smoke_tests": "pass|fail"
  },
  "data_freshness": {
    "<fonte>": {"data_ref": "ISO date", "age_days": N, "status": "fresh|stale_expected|warn|error"}
  },
  "row_counts": {
    "fidcs": N, "matches": N, "clientes": N, "credit_empresas": N, "macro_observations": N
  },
  "heuristic_fields": [
    {"field": "macro.selic_proj", "method": "selic - 0.5", "replaced_in_fase_3": true}
  ],
  "source": {
    "storage_account": "dfdatalakesprint",
    "container": "gold",
    "path": "final/"
  }
}
```

### Thresholds de freshness

| Fonte | Cadência | "warn" | "error" |
|----|----|----|----|
| BCB/SGS (macro) | diário | >2d | >7d |
| ANBIMA | diário | >2d | >7d |
| CVM CDA | mensal | >40d | >60d |
| Credit model retrain | trimestral | >100d | >180d |

---

## Seção 5 — Eliminação das 4 heurísticas

### 5.1 — selic_proj / ipca_proj → Boletim Focus do BCB

- Endpoint: `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoTop5Anuais`
- Mediana das top 5 casas de análise, projeção por ano
- Novo notebook: `01_bronze_ingestao/etl_focus.py` + `02_silver_tratamento/etl_focus.py`
- Output novo no `data.json`:
  ```json
  "macro": {
    "selic_proj_2026": 14.25, "selic_proj_2027": 12.50,
    "ipca_proj_2026": 4.10, "ipca_proj_2027": 3.60,
    "proj_source": "bcb_focus_top5", "is_proj_heuristica": false
  }
  ```
- Fallback: se fetch falhar, mantém heurística antiga com flag `is_proj_heuristica: true`
- **Esforço:** 2 dias

### 5.2 — Credit model → multi-cohort + features macro

- Bloqueador: histórico mensal de clientes (confirmar disponibilidade na Gold)
- Features novas: `selic_at_origination`, `ipca_12m_at_origination`, `cohort_month`, `idx_inadimplencia_pj_at_origination`
- Validação out-of-time: train 2024-2025, test 2026 Q1
- A/B no `data.json`: `credit_scoring_v1` (atual) E `credit_scoring_v2` (novo) em paralelo até decisão
- **Esforço:** 1-2 semanas (depende do histórico)

### 5.3 — Match engine → CVM 555 + segmento

- Filtros hard:
  - CVM 555: exclui fundos restritos a investidor qualificado se PME não qualifica
  - Status ANBIMA: só fundos ativos
- Pesos no scoring:
  - segmento exato: +30 pts
  - segmento secundário: +15 pts
- Mínimo de elegibilidade: `match_score >= 50`
- Output novo: `match_breakdown` (score por dimensão) + `elegibilidade` (booleans por filtro)
- **Esforço:** 3-5 dias

### 5.4 — Rating K-Means → quantis (com análise corrigida)

**Diagnóstico real (não está no README):** o K-Means já tem `random_state=42` + `n_init=20`. A instabilidade vem do `fator_macro = inad_pj_atual / inad_pj_median`, que muda diariamente conforme BCB publica nova inadimplência → `f_inad` é reescalado → cluster boundaries deslocam.

**Fix duplo:**

1. Substituir K-Means por quantis do `SCORE_RISCO` (que já é determinístico):
   ```python
   q33, q67 = df_ml["SCORE_RISCO"].quantile([0.33, 0.67])
   df_ml["CATEGORIA_RISCO"] = pd.cut(
       df_ml["SCORE_RISCO"],
       bins=[-np.inf, q33, q67, np.inf],
       labels=["BAIXO", "MEDIO", "ALTO"],
   )
   ```

2. Fixar `INAD_PJ_MEDIANA_HISTORICA` como constante versionada (substitui a mediana móvel diária).

**Side finding:** linha 282-285 do `scripts/rating.py` tem `print()` AVISO sem failure. Vira Great Expectation `expect_table_to_have_at_least_one_match` para CNPJ entre fontes.

- **Esforço:** 2 dias

### Sequenciamento

1. Rating K-Means (1 dia, alto alívio de credibilidade)
2. selic/ipca → Focus (2 dias, baixo risco)
3. Match engine (3-5 dias)
4. Credit model (1-2 semanas, condicional ao histórico mensal)

---

## Seção 6 — Frontend signals & trust indicators

### Componentes novos

- `assets/js/components/trust-bar.js` — sticky no topo, 🟢/🔴
- `assets/js/components/empty-state.js` — reutilizável (sem matches, sem dados)
- `assets/js/components/fetch-error.js` — degradação graciosa
- `assets/js/utils/trust.js` — helper `markHeuristic(fieldKey)` lê manifesto, retorna span com tooltip

### Lógica do trust bar

| Cor | Quando |
|----|----|
| 🟢 Verde | `pipeline_quality_check.overall_success: true` E todas as fontes em `fresh` |
| 🔴 Vermelho | Última pipeline `overall_success: false` OU `data_freshness.*.status === "error"` |

**Decisão do usuário:** heurísticas NÃO afetam cor do trust bar (evita "amarelo crônico"). Heurísticas aparecem só como marker inline na página correspondente (campo a campo).

### Heuristic markers (inline)

Pages chamam `markHeuristic('macro.selic_proj')` que retorna `<span>` com ícone ⚠️ + tooltip se o campo está em `heuristic_fields`. Quando array esvazia (Fase 3), markers somem automaticamente.

### Empty state pós-Seção 5.3

Página de Match pode ter PMEs sem nenhum FIDC compatível após filtro CVM 555 + segmento. Empty state amigável com sugestões de revisão.

### Loading/error

- Skeleton screens (>200ms de delay para evitar piscada)
- Fetch error: mostra última versão conhecida (localStorage cache) + botão recarregar

### Acessibilidade

- Trust bar com `role="status"` + `aria-live="polite"`
- Cores não-só-cor: ícones + texto explícito
- Contraste WCAG AA

### O que NÃO entra no frontend

- Auth/login, multi-tenant, real-time, histórico de versões do data.json

---

## Seção 7 — CI/CD & GitHub Actions hardening

### 3 workflows

```
.github/workflows/
├─ ci.yml              ← roda em PR + push (lint + tests + schemas)
├─ data-refresh.yml    ← refatoração do atual
└─ notify-failures.yml ← reaction (cria issue em falha)
```

### `ci.yml`

Jobs em paralelo, target <2min total:
- `lint-python` (ruff)
- `lint-js` (eslint)
- `type-check` (mypy)
- `unit-tests` (pytest)
- `secret-scan` (gitleaks)

Falha qualquer um → PR bloqueado (branch protection).

### `data-refresh.yml`

**Trigger:** cron diário 9h UTC + workflow_dispatch (com inputs de bypass).

**Concurrency:** `cancel-in-progress: false` (era `true`, mudança crítica).

**Pipeline:**
1. Checkout `fetch-depth: 2` (precisa HEAD~1)
2. Setup Python 3.11 + cache pip
3. `pip install -r requirements.txt` (não mais hardcoded)
4. Download `gold/final/_quality/expectations-result.json` do ADLS
5. Falhar se `overall_success: false` (a menos que `bypass_ge_check`)
6. Rodar `generate_dashboard_data.py` (lê ADLS, valida pandera)
7. Regression check vs HEAD~1
8. Playwright smoke test (6 páginas)
9. Diff: se nada mudou, exit 0
10. Commit + push
11. Em falha: dispatch para `notify-failures.yml`

### `notify-failures.yml`

Trigger: `workflow_run` em `data-refresh.yml`, conclusion=failure.

Ação: cria issue com label `data-refresh-failure` (auto-fecha quando próximo run passar).

### Pre-commit (local)

`.pre-commit-config.yaml`:
- gitleaks
- ruff (lint + format)
- eslint
- pandera schema runner (rápido)
- prettier (md/yml/json)

### Branch protection (main)

- Require PR + 1 approval
- Require status checks: lint-python, lint-js, type-check, unit-tests, secret-scan
- Require conversation resolution
- No force push, no deletion
- Exception (bypass list): `github-actions[bot]` para commit do data-refresh

### SLO operacional

| Métrica | Target |
|----|----|
| Sucesso do data-refresh diário | ≥95% rolling 30d |
| Tempo médio de execução | <5min |
| Tempo entre falha e detecção | <1h (issue criada) |
| Tempo de CI de PR | <3min |

---

## Seção 8 — Observabilidade leve

Sem stack enterprise. Suficiente pra responder em <1min: *rodou hoje? rodou bem? se quebrou, onde?*

### Logs estruturados (JSON Lines)

`scripts/lib/logger.py` — helper único. Logs em stdout no CI + arquivo `./.cache/logs/run-*.jsonl` localmente.

Eventos sempre logados: `pipeline_start`, `download`, `schema_validation`, `regression_check`, `manifest_generated`, `pipeline_end`.

### GitHub Step Summaries

Cada step crítico escreve markdown em `$GITHUB_STEP_SUMMARY` (visível na aba Summary do run): tabela de schemas validados, regression deltas, smoke test results.

### `docs/operacao.md`

Página estática auto-atualizada pelo `data-refresh.yml` no fim de cada run com sucesso. Contém:
- Último update (timestamp, duração, bytes)
- Últimos 14 runs (status, duração, notas)
- Issues abertos de `data-refresh-failure`

Gerado por `scripts/update_operacao_doc.py`.

### `docs/historico-runs.csv`

Append-only, uma linha por execução. Permite plotar duração ao longo do tempo, row counts, calcular SLA real.

### Alertas (passivos)

- Workflow run ❌ → e-mail GitHub para mantenedores
- Issue auto-criada
- Banner 🔴 no dashboard

**Opcional (quando houver Slack):** webhook em `notify-failures.yml`.

### O que NÃO entra

APM/tracing, Sentry, Azure Monitor, métricas customizadas.

---

## Seção 9 — Estrutura, riscos, roadmap

### Estrutura alvo do repositório

```
radar-fidc/
├─ index.html
├─ data.json
├─ data-quality.json                     # NOVO
├─ requirements.txt                       # atualizado
├─ .env.example                           # atualizado (dfdatalakesprint)
├─ .gitignore                             # +.cache/, +.env, +data_real/
├─ .pre-commit-config.yaml                # NOVO
├─ pyproject.toml                         # NOVO (ruff, mypy, pytest)
├─ Makefile                               # NOVO
│
├─ .github/workflows/
│   ├─ ci.yml                             # NOVO
│   ├─ data-refresh.yml                   # refatorado
│   └─ notify-failures.yml                # NOVO
│
├─ assets/
│   ├─ css/
│   └─ js/
│       ├─ components/
│       │   ├─ chart-factory.js
│       │   ├─ paginated-table.js
│       │   ├─ select.js
│       │   ├─ table.js
│       │   ├─ trust-bar.js               # NOVO
│       │   ├─ empty-state.js             # NOVO
│       │   └─ fetch-error.js             # NOVO
│       ├─ pages/                         # (sem mudança estrutural)
│       └─ utils/
│           ├─ dom.js, format.js, memo.js, pagination.js
│           └─ trust.js                   # NOVO
│
├─ scripts/
│   ├─ generate_dashboard_data.py         # refatorado (lê ADLS)
│   ├─ update_operacao_doc.py             # NOVO
│   ├─ cadastro.py, credit_model.py, match.py, rating.py
│   ├─ lib/
│   │   ├─ azure_io.py                    # NOVO
│   │   ├─ gold_paths.py                  # NOVO
│   │   ├─ logger.py                      # NOVO
│   │   ├─ schemas.py                     # NOVO (pandera)
│   │   ├─ trust_manifest.py              # NOVO
│   │   ├─ regression_check.py            # NOVO
│   │   ├─ io_utils.py                    # refatorado
│   │   ├─ payload.py, formatters.py, paths.py
│   └─ tests/                             # NOVO
│
├─ notebooks/
│   ├─ 01_bronze_ingestao/
│   │   ├─ etl_anbima.py, etl_bcb.py, etl_cda.py
│   │   └─ etl_focus.py                   # NOVO (Fase 3)
│   ├─ 02_silver_tratamento/
│   │   ├─ etl_anbima.py, etl_macro.py, etl_cda.py
│   │   └─ etl_focus.py                   # NOVO (Fase 3)
│   └─ 03_gold_modelagem/
│       ├─ 00-05 (existentes)
│       ├─ 06_great_expectations.py       # NOVO
│       └─ orquestrador_gold.py
│
├─ docs/
│   ├─ arquitetura.md, modelo_score.md, fontes_dados.md
│   ├─ credit_model.md, match_engine.md, powerbi_setup.md
│   ├─ operacao.md                        # NOVO (auto-gerado)
│   ├─ limitacoes_atuais.md               # NOVO
│   ├─ runbook.md                         # NOVO
│   └─ historico-runs.csv                 # NOVO
│
└─ data_real/                             # REMOVIDO
```

### Regra de ouro da migração

`data.json` permanece **schema-compatível** durante todas as fases. Frontend nunca quebra. Novas features são **adição**, nunca mudança incompatível.

### Roadmap

#### Fase 0 — Segurança & saneamento (~1 dia)

- Rotacionar Account Key
- Atualizar `AZURE_CONNECTION_STRING` no GitHub Secrets
- Configurar pre-commit + gitleaks
- GitHub push protection
- Auditar histórico do git por padrão de Account Key
- Branch protection rules em `main`

**Quick win:** defensável imediatamente como "hardening de segurança".

#### Fase 1 — Conectar ao ADLS (~5 dias)

- `scripts/lib/azure_io.py` + `gold_paths.py` + `logger.py`
- Refatorar `io_utils.py` (lê ADLS, não local)
- Refatorar `generate_dashboard_data.py`
- Atualizar `requirements.txt` (`azure-storage-file-datalake`)
- Atualizar README, `docs/arquitetura.md`, `docs/fontes_dados.md` (stdatatalake2026 → dfdatalakesprint)
- Remover `data_real/` do repo
- Atualizar `data-refresh.yml` (remover path filter, adicionar Azure auth)

**Validação:** `data.json` gerado do ADLS é byte-igual (ou quase) ao do `data_real/` antigo.

#### Fase 2 — Trust layer (~12 dias)

- `lib/schemas.py` (pandera models)
- Integrar pandera em cada `read_*()`
- `lib/trust_manifest.py` (gera `data-quality.json`)
- `lib/regression_check.py`
- GE no Databricks: `06_great_expectations.py` com 5 suites (30+ expectativas)
- CI lê e valida `expectations-result.json` do ADLS
- Playwright smoke test (6 páginas)
- `notify-failures.yml`
- Frontend: trust-bar, empty-state, fetch-error, utils/trust
- Markers visuais nas heurísticas
- Testes unitários
- Docs: runbook.md, limitacoes_atuais.md, operacao.md template

#### Fase 3 — Eliminação de heurísticas (~3-4 semanas)

| Subtarefa | Ordem | Esforço |
|----|----|----|
| Rating K-Means → quantis | 1 | 2d |
| selic/ipca → BCB Focus | 2 | 2d |
| Match engine (CVM 555 + segmento) | 3 | 3-5d |
| Credit model multi-cohort | 4 | 1-2 sem (bloqueador: histórico mensal) |

**Critério "Fase 3 completa":** `heuristic_fields: []` no `data-quality.json`.

#### Fase 4 — Polimento contínuo

- Migrar `.xlsx` para `.parquet` (negociar com pipeline team)
- Auditoria WCAG AA
- Coverage 80% em `lib/`
- Gráficos de histórico em `operacao.md`
- Rotação trimestral da Account Key (calendário)
- Revisão trimestral de GE expectations

### Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|----|----|----|----|
| Gold muda layout | Média | Alto | pandera + GE pegam |
| Account Key vaza | Média | Crítico | gitleaks + push protection + rotação |
| ANBIMA/BCB/CVM mudam API | Baixa | Alto | bronze guardado; GE alarme |
| `data.json` cresce >10MB | Baixa | Médio | hoje 836KB; split por página se necessário |
| Playwright flaky | Média | Médio | retry x2 + screenshot |
| Credit v2 pior que v1 | Alta | Médio | A/B no payload; só promove se AUC bate v1 |
| FIAP deadline antes de Fase 3 | Alta | Baixo | Fase 2 já entrega "production-ready" |
| Time sem acesso ao Databricks pra GE | Média | Médio | Fallback: GE no CI sobre os mesmos arquivos |

### Anti-patterns a evitar

| ❌ | ✅ |
|----|----|
| Esconder heurísticas | Marker visual claro |
| Falhar silenciosamente | Fail fast + CI vermelho |
| `print()` para tudo | Logger estruturado JSON |
| Manter `data_real/` "por garantia" | Apagar — cache local em `.cache/` |
| Backend "só pra ter API" | Backend só se virar SaaS |
| Substituir tudo de uma vez | Fases, frontend sempre rodando |
| Feature flag sem critério de remoção | Toda flag tem data de remoção |
| Testar mocks elaborados | Pandera sobre DataFrame real |

### O que fica EXPLICITAMENTE de fora

- Backend API dedicado
- Cache distribuído (Redis)
- Filas (RabbitMQ, Service Bus)
- Auth/RBAC de usuário
- Multi-tenant
- Mobile app nativo
- Internacionalização (pt-BR fixo)
- Dark mode (já existe)

---

## Próximos passos

1. Rotacionar a Account Key vazada **hoje** (independente de qualquer decisão de implementação)
2. Aprovar este spec
3. Gerar plano de implementação detalhado (via skill `writing-plans`) — quebra cada fase em tarefas de 2-5 minutos para o ciclo de dev
4. Executar Fase 0 (segurança & saneamento) — 1 dia, sem bloqueador
5. Sequenciar Fases 1 → 2 → 3 → 4 conforme capacidade do time
