# Limitações atuais — Radar FIDC

> Lista viva. Quando uma heurística é substituída por dado real, mova a entrada para a seção "Histórico" e remova-a de `HEURISTIC_FIELDS` em `scripts/lib/trust_manifest.py` (adicionando ao `REPLACED_HEURISTICS`).

**Referência cruzada:** Seção 5 da spec [`2026-05-14-radar-fidc-polimento-design.md`](superpowers/specs/2026-05-14-radar-fidc-polimento-design.md).

**Última revisão:** 2026-05-14 (pós Fase 3).

---

## Heurísticas ativas

Cada entrada abaixo é um valor calculado por aproximação, não por leitura direta de fonte oficial. O manifesto `data-quality.json` lista todas em `heuristic_fields` e serve como registro de auditoria server-side. O dashboard não exibe marker visual para essas heurísticas — consulte este documento e o manifesto para auditoria de qualidade.

### `credit.scoring`

- **Método atual:** modelo single-cohort em `scripts/credit_model.py`, treinado em uma fotografia única de clientes, sem features macro.
- **Por que é heurística:** ignora variação temporal (cohort_month, selic na origem) e tendências macro que afetam inadimplência PJ. Score envelhece rápido.
- **Substituição planejada:** retrain multi-cohort com features `cohort_month`, `selic_at_origination`, `ipca_12m_at_origination`, `idx_inadimplencia_pj_at_origination`. Validação out-of-time (train 2024-2025, test 2026 Q1). A/B: `credit_scoring_v1` e `credit_scoring_v2` paralelos até decisão.
- **Bloqueador externo:** depende de histórico mensal de clientes no Gold (`gold/final/clientes_mensal/<YYYY>/<MM>/*.parquet`), atualmente não emitido pelo pipeline Databricks. Sem esse dataset, não há cohorts para treinar v2.
- **Esforço estimado:** 1 a 2 semanas após o histórico estar disponível.
- **Status:** pendente — bloqueador externo. Não é resolvível dentro do escopo de polimento da Fase 3.

---

## Bloqueadores resolvíveis na próxima atualização do schema Gold

Estes campos foram desenhados para a Fase 3 mas dependem de evolução do pipeline Databricks. A engine de match já está preparada para consumi-los assim que existirem (defaults seguros enquanto ausentes).

| Campo | Onde | Default atual | Impacto da ausência |
|-------|------|---------------|---------------------|
| `restricao_cvm_555` | `gold/final/rating_fidc.xlsx::GERAL` | `False` (não-restrito) | Filtro CVM 555 não bloqueia ninguém — clientes não qualificados podem ver fundos restritos. Documentar como blocker conhecido até pipeline emitir a coluna. |
| `status_anbima` | `gold/final/rating_fidc.xlsx::GERAL` | `"ativo"` (assume ativo) | Fundos eventualmente cancelados podem aparecer no rating. Mitigação parcial via `cnpjs_encerrados` em `scripts/rating.py`. |
| `segmento_predominante` | `gold/final/rating_fidc.xlsx::GERAL` | `None` | Bônus de segmento primário (+30) sempre = 0. |
| `segmentos_secundarios` | `gold/final/rating_fidc.xlsx::GERAL` | `[]` | Bônus de segmento secundário (+15) sempre = 0. |
| `e_qualificado` | `gold/final/clientes.csv` | `False` (não qualifica) | Conjugado com `restricao_cvm_555: False` (default), o filtro não atua. Assim que `restricao_cvm_555` existir, este precisa existir junto. |
| `segmento` | `gold/final/clientes.csv` | `None` | Sem este, `score_segmento` devolve 0 e o motivo fica `sem_segmento_cliente`. |

A engine de match em `scripts/match.py` detecta presença/ausência por coluna e loga aviso explícito quando trabalha em modo permissivo.

---

## Qualidade de dados — onde olhar

O status de qualidade dos dados é mantido server-side em `data-quality.json` (auditoria), não exibido no dashboard. O manifesto contém:

- `pipeline_quality_check` — resultado agregado das suites Great Expectations (`overall_success`, `suites_passed`, `suites_failed`).
- `ci_quality_check` — flags de schema validation, regression check e smoke tests do workflow `data-refresh.yml`.
- `data_freshness` — idade em dias de cada fonte (`macro`, `focus`) com status `fresh` / `warn` / `error`.
- `heuristic_fields` — lista das heurísticas ativas (cada entrada também documentada aqui).
- `replaced_heuristics` — histórico das substituições já realizadas.

Thresholds de freshness por fonte:

| Fonte | Cadência | `warn` | `error` |
|-------|----------|--------|---------|
| BCB/SGS (macro) | diário | >2d | >7d |
| ANBIMA | diário | >2d | >7d |
| CVM CDA | mensal | >40d | >60d |
| Credit model retrain | trimestral | >100d | >180d |

---

## Histórico de heurísticas substituídas

Entradas aparecem aqui quando a heurística é substituída por dado real. Replicado em `data-quality.json#replaced_heuristics` para auditoria.

| Data | Heurística removida | Substituída por | Onde |
|------|---------------------|-----------------|------|
| 2026-05-14 | `rating.algorithm` | Quantis (tercis) do `SCORE_RISCO` + `INAD_PJ_MEDIANA_HISTORICA = 4.20` fixa | `scripts/rating.py` (Fase 3) |
| 2026-05-14 | `macro.selic_proj` | Mediana das top 5 do Boletim Focus do BCB (Olinda OData) | `notebooks/01_bronze_ingestao/etl_focus.py` → `02_silver_tratamento/etl_focus.py` → `03_gold_modelagem/02_indicadores_macro.py` |
| 2026-05-14 | `macro.ipca_proj` | Mesma fonte e fallback de `macro.selic_proj` | idem |
| 2026-05-14 | `matches.engine` | Filtros hard CVM 555 + status ANBIMA, bônus de segmento (+30/+15), mínimo `match_score >= 50` | `scripts/match.py` (Fase 3) |

### Detalhes da substituição — 2026-05-14

#### `rating.algorithm` → tercis de `SCORE_RISCO`

- **Diagnóstico:** o K-Means tinha `random_state=42` + `n_init=20` (não era aleatório), mas `fator_macro = inad_pj_atual / inad_pj_serie.median()` era recalculado a cada execução. Toda vez que o BCB publicava nova inadimplência, a mediana móvel mudava → `f_inad` reescalava → fronteiras de cluster deslocavam → mesmo fundo trocava de classe sem ter mudado.
- **Solução:** congelar `INAD_PJ_MEDIANA_HISTORICA = 4.20` como constante versionada (mediana 2020-2025 do SGS 21084) e substituir `KMeans.fit_predict` por `pd.cut(SCORE_RISCO, bins=[-inf, q33, q67, inf])`. Determinístico, monotônico em relação ao SCORE_RISCO, auditável (basta inspecionar os dois quantis).
- **Quando atualizar `INAD_PJ_MEDIANA_HISTORICA`:** quando dispusermos de pelo menos mais 12 meses de observações (~final de 2027). Atualização documentada aqui no histórico.

#### `macro.selic_proj` / `macro.ipca_proj` → BCB Focus

- **Endpoint:** `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoTop5Anuais` filtrado por `Indicador eq 'Selic' or Indicador eq 'IPCA'`.
- **Cadeia Bronze→Silver→Gold:**
  - `notebooks/01_bronze_ingestao/etl_focus.py`: GET diário, grava `bronze/focus/expectativas_top5_anuais_<YYYY-MM-DD>.csv` + cópia `latest`.
  - `notebooks/02_silver_tratamento/etl_focus.py`: pivot por (Indicador, DataReferencia), última pesquisa por par, salva `silver/focus/projecoes_anuais.parquet`.
  - `notebooks/03_gold_modelagem/02_indicadores_macro.py`: se Silver fresca (<14 dias), substitui `selic_projetada_12m` e `ipca_projetado_12m` + adiciona `proj_source: "bcb_focus_top5"` e `proj_date: <DataReferencia>` + `is_proj_heuristica: false`.
- **Fallback:** se fetch falhar OU Silver indisponível OU pesquisa >14 dias, mantém heurística com `is_proj_heuristica: true` registrado no payload e no manifesto de qualidade.

#### `matches.engine` → CVM 555 + segmento + min elegibilidade

- **Filtros hard:**
  - `restricao_cvm_555 == True` E `cliente.e_qualificado == False` → exclui.
  - `status_anbima != "ativo"` → exclui.
- **Bônus aditivo no `match_score`:**
  - `cliente.segmento == fundo.segmento_predominante` → +30 pts.
  - `cliente.segmento ∈ fundo.segmentos_secundarios` → +15 pts.
  - Cap em 100 (bônus nunca ultrapassa o teto).
- **Mínimo de elegibilidade:** matches com `match_score < 50` são descartados (`MIN_ELEGIBILIDADE = 50` em `scripts/match.py`). Existe ainda a constante `MIN_MATCH_SCORE = 20` como piso histórico interno — é dead branch a remover, sem efeito prático porque `MIN_ELEGIBILIDADE` é o filtro efetivo.
- **Outputs novos:** colunas `S_SEGMENTO`, `SEGMENTO_MOTIVO`, `MATCH_BREAKDOWN` (JSON com componentes), `ELEGIBILIDADE` (JSON com `{cvm_555, fundo_ativo, segmento_alinhado}`).
- **Modo permissivo:** colunas `restricao_cvm_555`, `status_anbima`, `segmento_predominante`, `segmentos_secundarios`, `e_qualificado`, `segmento` ainda não emitidas pelo pipeline Databricks (ver bloqueador acima). Engine detecta ausência por coluna e usa defaults seguros. Loga aviso no início da execução.
