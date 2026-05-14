# Limitações atuais — Radar FIDC

> Lista viva. Quando uma heurística é substituída por dado real, mova a entrada para a seção "Histórico" e remova-a de `HEURISTIC_FIELDS` em `scripts/lib/trust_manifest.py`.

**Referência cruzada:** Seção 5 da spec [`2026-05-14-radar-fidc-polimento-design.md`](superpowers/specs/2026-05-14-radar-fidc-polimento-design.md).

**Última revisão:** 2026-05-14.

---

## Heurísticas ativas

Cada entrada abaixo é um valor calculado por aproximação, não por leitura direta de fonte oficial. O manifesto `data-quality.json` lista todas em `heuristic_fields` e o frontend injeta um marker ⚠ inline ao lado do valor correspondente.

### `macro.selic_proj`

- **Método atual:** `selic_atual - 0.5` em `scripts/lib/payload.py:build_macro`.
- **Por que é heurística:** projeta a Selic do próximo ciclo subtraindo 0,5 ponto da observação mais recente. Ignora expectativa de mercado, ata do Copom e curva DI.
- **Substituição planejada:** mediana das projeções top 5 do Boletim Focus do BCB, endpoint `Expectativas/v1/odata/ExpectativasMercadoTop5Anuais`.
- **Esforço estimado:** 2 dias (novo notebook `etl_focus.py` em Bronze + Silver).
- **Status:** pendente — Fase 3.

### `macro.ipca_proj`

- **Método atual:** `ipca_12m * 0.9` em `scripts/lib/payload.py:build_macro`.
- **Por que é heurística:** assume que o IPCA dos próximos 12 meses cairá 10% sobre o acumulado atual. Ignora expectativa de mercado.
- **Substituição planejada:** mediana das projeções top 5 do Boletim Focus do BCB (mesmo endpoint do `selic_proj`).
- **Esforço estimado:** incluso no esforço de `selic_proj` (notebook único cobre ambos).
- **Status:** pendente — Fase 3.

### `credit.scoring`

- **Método atual:** modelo single-cohort em `scripts/credit_model.py`, treinado em uma fotografia única de clientes, sem features macro.
- **Por que é heurística:** ignora variação temporal (cohort_month, selic na origem) e tendências macro que afetam inadimplência PJ. Score envelhece rápido.
- **Substituição planejada:** retrain multi-cohort com features `cohort_month`, `selic_at_origination`, `ipca_12m_at_origination`, `idx_inadimplencia_pj_at_origination`. Validação out-of-time (train 2024-2025, test 2026 Q1). A/B: `credit_scoring_v1` e `credit_scoring_v2` paralelos até decisão.
- **Esforço estimado:** 1 a 2 semanas (depende de histórico mensal de clientes estar disponível no Gold).
- **Status:** pendente — Fase 3.

### `matches.engine`

- **Método atual:** scoring em `scripts/match.py` que ignora segmento da PME e filtros CVM 555 (investidor qualificado).
- **Por que é heurística:** matches podem sugerir fundos a investidores que não qualificam, e desconsidera afinidade de segmento — um dos sinais mais fortes de fit FIDC ↔ PME.
- **Substituição planejada:** filtros hard de CVM 555 (`exclui restritos a qualificado quando PME não qualifica`) e status ANBIMA (`só fundos ativos`); pesos no scoring (`segmento exato: +30 pts`, `segmento secundário: +15 pts`); mínimo de elegibilidade `match_score >= 50`; novos campos `match_breakdown` e `elegibilidade`.
- **Esforço estimado:** 3 a 5 dias.
- **Status:** pendente — Fase 3.

### `rating.algorithm`

- **Método atual:** K-Means em `scripts/rating.py` com `fator_macro = inad_pj_atual / inad_pj_median` recalculado diariamente.
- **Por que é heurística:** apesar do `random_state=42` e `n_init=20`, o `fator_macro` muda toda vez que o BCB publica nova inadimplência. Isso reescala `f_inad` e desloca as fronteiras de cluster — gera instabilidade na classe (A/B/C/D) de FIDCs entre runs consecutivos sem que o fundo tenha mudado.
- **Substituição planejada:** trocar K-Means por quantis fixos do `SCORE_RISCO` (já determinístico) e congelar `INAD_PJ_MEDIANA_HISTORICA` como constante versionada. Adicionalmente, transformar o `print()` de aviso (linha ~283 de `scripts/rating.py`) em Great Expectation `expect_table_to_have_at_least_one_match`.
- **Esforço estimado:** 2 dias.
- **Status:** pendente — Fase 3 (priorizada como primeira da fila pelo alto ganho de credibilidade).

---

## Como ler o trust bar

O trust bar é um indicador sticky no topo do dashboard que sintetiza qualidade de dados em três cores. **Heurísticas não afetam a cor do trust bar** — essa foi uma decisão consciente de design para evitar "amarelo crônico" enquanto a Fase 3 não conclui. Heurísticas aparecem apenas como markers inline ⚠ ao lado do valor correspondente.

| Cor | Quando aparece |
|-----|----------------|
| 🟢 Verde | `pipeline_quality_check.overall_success: true` E todas as fontes em `data_freshness` com `status: "fresh"`. |
| 🟡 Amarelo | `pipeline_quality_check.status: "not_run"` (Fase 3 ainda não habilitada) OU pelo menos uma fonte em `warn`. |
| 🔴 Vermelho | `pipeline_quality_check.overall_success: false` OU qualquer fonte em `error`. |

Os thresholds de freshness por fonte estão na Seção 4 da spec. Resumo:

| Fonte | Cadência | `warn` | `error` |
|-------|----------|--------|---------|
| BCB/SGS (macro) | diário | >2d | >7d |
| ANBIMA | diário | >2d | >7d |
| CVM CDA | mensal | >40d | >60d |
| Credit model retrain | trimestral | >100d | >180d |

---

## Histórico

Entradas aparecem aqui quando a heurística for substituída por dado real.

| Data | Heurística removida | Substituída por | PR |
|------|---------------------|-----------------|----|
| — | — | — | — |
