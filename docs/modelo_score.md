# Modelo de Score — Radar FIDC

## Objetivo

Atribuir uma **pontuação de 0 a 100** para cada FIDC, combinando métricas de retorno histórico, risco, contexto macroeconômico e liquidez. O score permite comparar e ranquear FIDCs de forma objetiva.

## Fórmula

```
Score Final = (Score Retorno × 0,40)
            + (Score Risco   × 0,30)
            + (Score Macro   × 0,20)
            + (Score Liquidez× 0,10)
```

## Componentes

### 1. Score Retorno (40%)

Mede o **retorno histórico médio** de cada FIDC normalizado entre 0 e 100.

```python
retorno_medio = série_histórica["retorno"].mean()
score_retorno = min_max_normalize(retorno_medio) * 100
```

- **Fonte**: `silver/anbima/serie_historica_fidc.parquet`
- **Campo**: retorno diário da cota do fundo
- **Quanto maior o retorno histórico, maior o score**

### 2. Score Risco (30%)

Mede a **estabilidade do fundo** — quanto menor a volatilidade, maior o score.

```python
volatilidade = série_histórica["retorno"].std()
score_risco = (1 - min_max_normalize(volatilidade)) * 100
```

- **Inversamente proporcional**: fundo estável → score alto
- **Complementar ao retorno**: busca o melhor risco-retorno

### 3. Score Macro (20%)

Ajuste baseado no **cenário macroeconômico atual** (SELIC, IPCA).

| Cenário | Score Macro | Critério |
|---------|-------------|----------|
| `favoravel_posfixado` | 80 | SELIC > 10% |
| `neutro` | 50 | 6% ≤ SELIC ≤ 10% |
| `favoravel_prefixado` | 60 | SELIC < 6% |

- **Fonte**: `silver/dados_macroeconomicos/` (BCB + Focus)
- **Cenário atual**: `favoravel_posfixado` (SELIC = 15,0%)

### 4. Score Liquidez (10%)

Mede a **frequência de observações** disponíveis no histórico.

```python
score_liquidez = min(n_observacoes / 12, 1.0) * 100
```

- **Proxy para liquidez**: mais dados históricos = fundo mais ativo
- Fundo com ≥ 12 meses de histórico recebe score máximo

## Classificação Final

| Classificação | Faixa de Score | Interpretação |
|---------------|---------------|----------------|
| **A** | 80 — 100 | Excelente: alto retorno, baixo risco, macro favorável |
| **B** | 60 — 79 | Bom: bom equilíbrio risco-retorno |
| **C** | 40 — 59 | Regular: retorno moderado ou volatilidade elevada |
| **D** | 0 — 39 | Atenção: alto risco ou retorno insuficiente |

## Exemplo de Cálculo

```
FIDC Tramontina:
  retorno_medio  = 0,000352 (série histórica)
  volatilidade   = 0,000368
  n_observacoes  = 12

  score_retorno  = 54,1  (normalizado entre todos os FIDCs)
  score_risco    = 99,9  (volatilidade muito baixa = estável)
  score_macro    = 80,0  (cenário favorável pós-fixado)
  score_liquidez = 8,49  (12 meses / limite normalizado)

  Score Final = (54,1 × 0,40) + (99,9 × 0,30) + (80,0 × 0,20) + (8,49 × 0,10)
             = 21,64 + 29,97 + 16,00 + 0,85
             = 68,46 → Classe B
```

## Limitações e Próximos Passos

- **Score Retorno baixo**: A normalização min-max é sensível a outliers extremos nos dados da série histórica ANBIMA. Versão futura usará percentis.
- **Score Liquidez**: Proxy simplificado. Versão futura incluirá PL (Patrimônio Líquido) e volume médio de resgates.
- **PME Matching**: Atualmente usa 5 perfis simulados. Integração futura com API Núclea para dados reais de PMEs.

## Notebook de Referência

Implementação completa: [`notebooks/03_gold_modelagem/01_score_fidc.py`](../notebooks/03_gold_modelagem/01_score_fidc.py)
