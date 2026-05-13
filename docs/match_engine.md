# Engine de Match Cliente × FIDC

## Objetivo

Para cada cliente, ranquear os FIDCs elegíveis combinando 4 dimensões e produzir
um **match score 0–100** + **motivo** explicável.

## Score combinado

```
match_score = s_perfil  × 0,40
            + s_risco   × 0,30
            + s_retorno × 0,20
            + s_hist    × 0,10
```

Pesos definidos no topo de `scripts/match.py`.

### `s_perfil` — alinhamento de perfis

Matriz definida em [`scripts/lib/perfil_rules.py`](../scripts/lib/perfil_rules.py).
Linha = cliente; coluna = perfil sugerido do fundo.

|  | CONSERVADOR | MODERADO | ARROJADO |
|---|---|---|---|
| **CONSERVADOR** | 100 | 30 | 0 |
| **MODERADO** | 70 | 100 | 40 |
| **ARROJADO** | 60 | 80 | 100 |

### `s_risco` — distância entre apetite × risco

```python
diff = score_risco_fundo - score_perfil_cliente
if diff > 0:    # fundo mais arriscado
    penalidade = diff * 1.2
else:           # fundo mais conservador (penaliza menos)
    penalidade = abs(diff) * 0.5
s_risco = max(0, 100 - penalidade)
```

### `s_retorno` — adequado à experiência

- **Iniciante (1)**: prioriza estabilidade → `100 - 2·vol`
- **Intermediário (2)**: equilíbrio → `min(100, sharpe·10 + 40)`
- **Avançado (3)**: prioriza retorno → `min(100, retorno·1,5)`

### `s_hist` — histórico

```python
s_hist = min(100, meses / 24 * 100)   # 24 meses → score 100
       = 0 se meses < 6
```

## Filtros de elegibilidade

Antes mesmo de calcular o score:

| Condição | Bloqueia |
|---|---|
| `MESES_HISTORICO < 6` | Sim (excluído antes do loop) |
| `SCORE_RISCO` é NaN | Sim (correção de bug — antes virava 50 sintético) |
| `match_score < 20` | Sim (descarta matches ruins) |

## Saída

Excel `data_real/matches.xlsx` com 5 abas:

| Aba | Conteúdo |
|---|---|
| `TODOS_OS_MATCHES` | Top-5 por cliente, detalhe completo |
| `RESUMO_CLIENTES` | 1 linha por cliente, top-3 inline |
| `CONSERVADOR/MODERADO/ARROJADO` | Filtrados por perfil do cliente |
| `RANKING_FUNDOS` | Fundos que aparecem como TOP1 com frequência |

## Motivo (texto)

Gerado por `gerar_motivo(cliente, fundo, scores)`:

- "perfil X alinhado ao cliente" / "compatível" / "adjacente — maior cautela"
- "retorno anual de X%"
- "inadimplência baixa / moderada / elevada"
- "cota X com risco Y"

## Implementação

[`scripts/match.py`](../scripts/match.py) — funções nomeadas (`score_perfil`, `score_risco`,
`score_retorno_fit`, `score_historico`, `calcular_match`) + `main()`.

## Limitações conhecidas

1. **CPF como chave**: `gerar_resumo` faz groupby `(CPF, CLIENTE, PERFIL)`.
   Se o nome diferir minimamente (acento, espaço), o cliente vira 2 resumos.
2. **Sem matriz de produto**: o match ignora o segmento de atuação do FIDC
   (recebíveis, agro, multissetorial). Adicionar features por segmento seria evolutivo.
3. **Sem regulatório**: a CVM 555 sugere bloqueio de produtos incompatíveis. Hoje
   apenas penalizamos no score; não bloqueamos a recomendação.
