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
Tab IV/Macro (fator macro)    │                                                │
ANBIMA Série Histórica        ┘                                                ▼
                                                          Tercis (q33, q67) ──► CATEGORIA_RISCO
                                                          BAIXO / MEDIO / ALTO
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

### Categoria (tercis do SCORE_RISCO)

A categoria de risco vem dos **tercis** do `SCORE_RISCO` contínuo:

```
q33, q67 = SCORE_RISCO.quantile([0.33, 0.67])
CATEGORIA_RISCO = pd.cut(SCORE_RISCO, bins=[-inf, q33, q67, inf],
                         labels=["BAIXO", "MEDIO", "ALTO"])
```

Substituiu o K-Means original na Fase 3. Vantagens: determinístico (não depende
de `random_state`), monotônico em relação ao `SCORE_RISCO` (fundo com score
maior nunca cai em categoria mais conservadora que outro com score menor),
auditável (basta inspecionar `q33` e `q67`) e estável entre runs — não havia
re-clusterização sobre features rescaled pelo fator macro.

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
2. **PCA não-supervisionado:** o sinal do PC1 pode inverter entre execuções; o pipeline corrige forçando o alinhamento (`pca.components_[0, 0] < 0` → inverte). A categoria é estável porque vem dos tercis do `SCORE_RISCO`, não dos componentes brutos.
3. **Fator macro** afeta só `TAXA_INAD`; o ajuste poderia ser estendido para SCR e concentração.
4. **Projeções macro** vêm do Boletim Focus (BCB) quando a Silver está fresca (≤14 dias). Em fallback, o pipeline cai para heurística com `is_proj_heuristica: true` registrado no payload — ver `docs/limitacoes_atuais.md` para detalhes.
