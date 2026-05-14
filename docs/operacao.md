<!-- AUTO-GENERATED. Não editar a mão entre os marcadores. As seções abaixo são atualizadas por scripts/update_operacao_doc.py ao final de cada run com sucesso do data-refresh.yml. -->

# Operação — Radar FIDC

> Atualizado automaticamente pelo workflow `data-refresh.yml` ao final de cada run com sucesso (via `scripts/update_operacao_doc.py`). Histórico completo de execuções está em [`historico-runs.csv`](historico-runs.csv).

## Último run

<!-- last-update:start -->
- **Timestamp:** _aguardando primeiro run em produção_
- **Status:** —
- **Duração:** —
- **Bytes lidos:** —
- **Pipeline ID:** —
<!-- last-update:end -->

## Últimos 14 runs

A tabela abaixo é truncada para os 14 runs mais recentes (cerca de 2 semanas com cadência diária). Histórico completo em [`historico-runs.csv`](historico-runs.csv).

| Data (UTC) | Status | Duração | Bytes | Pipeline ID |
|------------|--------|---------|-------|-------------|
<!-- runs:start -->
<!-- runs:end -->

## Issues abertos de `data-refresh-failure`

Lista atualizada manualmente quando há falhas recorrentes. Para a lista corrente, consulte o filtro do GitHub:

[Issues com label `data-refresh-failure`](https://github.com/victorsouza14/radar-fidc/issues?q=is%3Aissue+is%3Aopen+label%3Adata-refresh-failure)

## Histórico de duração

Plote a série temporal a partir de [`historico-runs.csv`](historico-runs.csv) (colunas `ts` × `duration_s`) para acompanhar SLA de execução.

**SLOs operacionais alvo:**

| Métrica | Target |
|---------|--------|
| Sucesso do data-refresh diário | ≥95% rolling 30d |
| Tempo médio de execução | <5min |
| Tempo entre falha e detecção | <1h (issue criada) |
| Tempo de CI de PR | <3min |

## Rotação de Account Key

Trimestralmente — ver procedimento completo em [`runbook.md` Seção 4](runbook.md#4-rotação-de-account-key).

| Data | Quem | Key rotacionada |
|------|------|-----------------|
| 2026-05-13 | victor.braga@brandlovers.ai (Fase 0) | key1 |
