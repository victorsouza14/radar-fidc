# Modelo de Crédito — Radar FIDC

## Objetivo

Atribuir a cada **empresa pagadora** uma probabilidade de inadimplência (`prob_default`)
e um **score de crédito 0–100** (quanto maior, menor o risco), classificando em
BAIXO / MEDIO / ALTO.

## Algoritmo

- Random Forest (300 árvores, max_depth=6, class_weight="balanced")
- XGBoost (300 estimadores, max_depth=4, lr=0.05, scale_pos_weight ajustado)
- Escolha automática do melhor por **AUC-ROC** em 5-fold CV estratificado

Pipeline final: `SimpleImputer(median) → ModeloEscolhido`. Salva como
`data_real/credit_model.pkl` (inclui imputer e LabelEncoders de UF/CNAE).

## Definição de default (target)

Um boleto é marcado como inadimplido se **qualquer** das condições for verdadeira:

| Condição | Origem |
|---|---|
| `tipo_baixa` ∈ {protestado, decurso de prazo} | base de boletos |
| `dt_pagamento` ausente **E** `dt_vencimento < hoje - 30 dias` | regra com carência |
| `atraso_dias > 30` | calculado |

> **Importante (correção de bug):** antes marcávamos como default *qualquer* boleto
> sem `dt_pagamento`, mesmo os ainda não vencidos. Isso inflava `defaultou` e
> enviesava o modelo. Agora exigimos vencimento + 30 dias de carência.

Um **pagador** é considerado inadimplente se inadimpliu pelo menos uma vez (`max` da flag).

## Features

**Comportamentais (boletos):**
- `total_boletos` — volume
- `vlr_medio` — ticket médio
- `pct_atraso_1_30` — taxa de atrasos pequenos
- `atraso_medio` — média dos atrasos positivos

**Cadastrais (auxiliar):**
- `sacado_indice_liquidez_1m`
- `score_materialidade_evolucao`
- `media_atraso_dias`
- `indicador_liquidez_quantitativo_3m`
- `share_vl_inad_pag_bol_6_a_15d`
- `score_quantidade_v2`, `score_materialidade_v2`
- `uf_enc` (UF codificada)
- `cnae_enc` (CNAE primária codificada)

## Classificação de risco

| Risco | Faixa `prob_default` |
|---|---|
| BAIXO | ≤ 0,15 |
| MEDIO | 0,15 – 0,40 |
| ALTO | > 0,40 |

## Métricas esperadas

- AUC-ROC ~0,85–0,92 (depende do snapshot)
- Acurácia ~88–92%
- F1 ~0,55–0,70 (target desbalanceado)

## Anonimização (LGPD)

O hash do CNPJ na base original é mantido **apenas** em arquivos privados
(`data_real/scores_credito.csv`). No `data.json` público, é exibido como
`EMP-XXXXXXXX` (primeiros 8 caracteres do hash em uppercase).

## Implementação

[`scripts/credit_model.py`](../scripts/credit_model.py) — orquestra preparação, treino,
seleção do melhor modelo, scoring e exporta `credit_model.pkl` + `scores_credito.csv`.

## Limitações conhecidas

1. **Snapshot single-cohort**: o modelo é treinado num único corte temporal.
   Em produção, retreinar mensalmente com janela móvel.
2. **Variáveis macro não entram**: SELIC alta deveria aumentar inadimplência
   prevista — hoje não há essa interação.
3. **Ausência de feedback loop**: empresas que recebem score "BAIXO" e depois
   inadimplem não realimentam o treino automaticamente.
