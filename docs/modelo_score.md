# Modelo de Score — Radar FIDC

## Objetivo

Atribuir um **score de risco 0–100** e uma **categoria** (BAIXO / MEDIO / ALTO)
para cada FIDC, combinando inadimplência ajustada pelo cenário macro, aging,
qualidade do SCR dos devedores e concentração de cedentes.

A partir desse rating, calculamos também:

- **Perfil sugerido** do investidor (CONSERVADOR / MODERADO / ARROJADO)
- **Retorno ajustado ao risco** (retorno por ponto de risco)

## Pipeline (scripts/rating.py)

```
Tab V (inadimplência + aging) ┐
Tab X (SCR dos devedores)     │
Tab I (concentração cedentes) ├──► features 4D ──► PCA (1º componente) ──► SCORE_RISCO 0–100
Tab IV/Macro (fator macro)    │                ──► KMeans (3 clusters) ──► CATEGORIA_RISCO
ANBIMA Série Histórica        ┘
```

### Features (após StandardScaler)

| Feature | Origem | Interpretação |
|---|---|---|
| `f_inad` | Tab V | Inadimplência / Direitos creditórios no prazo × fator_macro |
| `f_aging` | Tab V | Aging ponderado (inadimplência mais antiga → pior) |
| `f_scr` | Tab X | Score SCR (0=AA→1=H, ponderado) |
| `f_conc` | Tab I | % do maior cedente no PL |

**Fator macro** = inadimplência PJ atual / mediana histórica.
Quando o ciclo de crédito está pior, a feature de inadimplência ganha peso.

### Score contínuo (PCA)

PCA com 4 componentes; usa o **PC1** (que captura ~50–60% da variância) como
score linear. O sinal é alinhado para que score baixo = risco baixo.

Normalização min–max → 0..100.

### Categoria (KMeans)

3 clusters sobre as features padronizadas. Os clusters são rotulados pela média
do `SCORE_RISCO` interno → BAIXO / MEDIO / ALTO.

## Filtros de elegibilidade

Não entram no rating (são marcados como "SEM DADOS"):

- Fundos com `TAXA_INAD > 100%` (artefato de liquidação)
- Fundos com SCR ausente (não preenchemos com valor sintético)
- Fundos sem concentração de cedente reportada
- Fundos com `data_encerramento_fundo` na ANBIMA

Para a listagem do dashboard, também exigimos `MESES_HISTORICO >= 6`
(configurável em `scripts/lib/payload.py`).

## Perfil sugerido por (tipo_cota × categoria_risco)

Tabela em `scripts/lib/perfil_rules.py` (fonte única consumida por rating + match).

| Tipo cota \ Risco | BAIXO | MEDIO | ALTO |
|---|---|---|---|
| ÚNICA | CONSERVADOR | MODERADO | ARROJADO |
| SENIOR | CONSERVADOR | MODERADO | MODERADO* |
| MEZANINO | MODERADO | MODERADO | ARROJADO |
| JUNIOR | MODERADO | ARROJADO | ARROJADO |

\* Cota sênior amortece o risco do fundo subjacente.

## Cenário macroeconômico

Em `scripts/lib/scenario.py`:

| SELIC | Cenário | Indexador preferido |
|---|---|---|
| ≥ 13% | `favoravel_posfixado` | CDI+ / pós |
| 10–13% | `neutro` | diversificar |
| < 10% | `favoravel_prefixado` | pré-fixado |

## Retorno e volatilidade (ANBIMA Série Histórica)

- Janela: 24 meses
- Retornos mensais **winsorizados** em ±50% (não descartados)
- Retorno anual: $(1 + \bar{r}_m)^{12} - 1$, clipped em [-100%, +1000%]
- Volatilidade anual: $\sigma_m \cdot \sqrt{12}$
- Mínimo 3 observações para entrar no agregado

## Retorno ajustado ao risco

`RETORNO_AJ_RISCO = RETORNO_ANUAL / (SCORE_RISCO/100 + 0.01)`

Calculado **após** o retorno virar percentual (correção do bug de escala).
Maior = melhor relação retorno/risco.

## Implementação

- Pipeline: [`scripts/rating.py`](../scripts/rating.py)
- Regras de cenário: [`scripts/lib/scenario.py`](../scripts/lib/scenario.py)
- Regras de perfil: [`scripts/lib/perfil_rules.py`](../scripts/lib/perfil_rules.py)
- Builder do payload: [`scripts/lib/payload.py`](../scripts/lib/payload.py)

## Limitações conhecidas

1. **Fundos novos (< 6 meses)** ficam de fora das listagens ordenadas mesmo que tenham score.
2. **PCA + KMeans** não-supervisionado: os rótulos BAIXO/MEDIO/ALTO podem mudar entre runs em datasets muito homogêneos. Usar sempre `random_state=42`.
3. **Fator macro** afeta só `TAXA_INAD`; o ajuste poderia ser estendido para SCR e concentração.
4. **Projeções macro** (`selic_proj`, `ipca_proj`) são heurísticas (não são as projeções oficiais do Focus). Flag `is_proj_heuristica` no payload sinaliza isso.
