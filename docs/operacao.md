<!-- AUTO-GENERATED. Não editar a mão entre os marcadores. As seções abaixo são atualizadas por scripts/update_operacao_doc.py ao final de cada run com sucesso do data-refresh.yml. -->

# Operação — Radar FIDC

> Atualizado automaticamente pelo workflow `data-refresh.yml` ao final de cada run com sucesso (via `scripts/update_operacao_doc.py`). Histórico completo de execuções está em [`historico-runs.csv`](historico-runs.csv).

## Último run

<!-- last-update:start -->
- **Timestamp:** 2026-05-28T12:23:49Z
- **Status:** success
- **Duração:** 1m03s
- **Bytes lidos:** 322.9 KB
- **Pipeline ID:** 26574379769
<!-- last-update:end -->

## Últimos 14 runs

A tabela abaixo é truncada para os 14 runs mais recentes (cerca de 2 semanas com cadência diária). Histórico completo em [`historico-runs.csv`](historico-runs.csv).

| Data (UTC) | Status | Duração | Bytes | Pipeline ID |
|------------|--------|---------|-------|-------------|
<!-- runs:start -->
| 2026-05-28T12:23:49Z | success | 1m03s | 322.9 KB | 26574379769 |
| 2026-05-25T12:26:01Z | success | 1m02s | 322.9 KB | 26400369348 |
| 2026-05-24T10:28:57Z | success | 1m03s | 322.9 KB | 26358763870 |
| 2026-05-23T10:25:05Z | success | 1m02s | 322.9 KB | 26330275594 |
| 2026-05-22T11:43:26Z | success | 57s | 322.9 KB | 26285743869 |
| 2026-05-21T12:12:49Z | success | 1m00s | 322.9 KB | 26225125720 |
| 2026-05-20T11:50:18Z | success | 3m23s | 322.9 KB | 26160461993 |
| 2026-05-19T11:59:49Z | success | 1m01s | 322.9 KB | 26095678701 |
| 2026-05-18T12:27:18Z | success | 1m12s | 322.9 KB | 26033358732 |
| 2026-05-17T10:21:08Z | success | 1m04s | 322.9 KB | 25988153801 |
| 2026-05-16T10:11:55Z | success | 1m01s | 322.9 KB | 25959292684 |
| 2026-05-15T11:19:26Z | success | 1m10s | 322.9 KB | 25915010582 |
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
