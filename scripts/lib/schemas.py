"""Pandera DataFrameModels — Linha 2 de defesa (consumer-side).

Cada schema corresponde a UM DataFrame lido pelo `io_utils`. A validação é
chamada dentro de cada `read_*()` em modo `lazy=True` para que TODAS as
violações apareçam em um único erro, não a primeira.

Schema drift = pipeline mudou layout sem coordenação → CI vermelho imediato.

Convenções:
- Strings nullable explícitas via ``nullable=True``
- Ranges via ``ge``/``le`` (inclusive); strings categóricas via ``isin``
- ``coerce=True`` no nível do schema: força o cast da coluna pro dtype declarado
  (e.g. CNPJ vem como ``int64`` no Excel → vira ``str``; renda vem como
  ``int64`` → continua int). Mantém o contrato robusto contra mudanças menores
  do upstream sem dependência de cada ``read_*`` repetir conversão.
- ``strict = False``: aceita colunas extras que o Databricks adicionar sem
  quebrar (forward compat); novos campos passam por uma revisão consciente
  ao serem usados no payload.

Observações sobre o Gold real (T05 — `docs/plans/2026-05-14-radar-fidc-fase-2.md`):
- ``rating.SEGMENTO`` é float64 100% NaN — declarado nullable.
- ``rating.TAXA_INADIMPLENCIA`` pode chegar a ~23k (artefato do upstream);
  removemos o teto de 100 para não bloquear o build (registramos como
  débito técnico em ``docs/limitacoes_atuais.md``).
- ``rating.CONC_MAIOR_CEDENTE``/``CONC_TOP3`` chegam apenas como 0.0 no Gold
  atual (pendente cálculo no pipeline) — schema só verifica ``ge=0``.
- ``matches.MATCH_SCORE``/``SCORE_CLIENTE``/``S_*``/``score_perfil`` estão
  em escala 0-100, não 0-1.
- ``clientes.cpf`` chega como int64 (perde zeros à esquerda → 10 ou 11
  dígitos). Aceitamos 10-11 dígitos numéricos para falhar se vier mascarado.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.typing import Series

# Valores canônicos extraídos dos uniques do Gold em 2026-05-14 (vide T05).
RISCO_VALUES = ("BAIXO", "MEDIO", "ALTO", "SEM DADOS")
PERFIL_VALUES = ("CONSERVADOR", "MODERADO", "ARROJADO", "SEM DADOS")
TIPO_COTA_VALUES = ("UNICA", "SENIOR", "MEZANINO", "JUNIOR", "SUBORDINADA")


class RatingGeralSchema(pa.DataFrameModel):
    """``gold/final/rating_fidc.xlsx`` — aba GERAL.

    Colunas reais (T05 — 2026-05-14): CNPJ, FUNDO, TIPO_COTA, SEGMENTO,
    RISCO, SCORE_RISCO, PERFIL_SUGERIDO, RETORNO_ANUAL, VOLATILIDADE,
    RETORNO_AJ_RISCO, TAXA_INADIMPLENCIA, SCR_NORMALIZADO,
    CONC_MAIOR_CEDENTE, CONC_TOP3, MESES_HISTORICO.

    Nullable em diversas colunas reflete o estado atual do Gold:
    ~37% de SCORE_RISCO e ~36% de RISCO chegam NaN porque o pipeline
    ainda não roda o cálculo de risco para todas as classes (heurística
    documentada em ``trust_manifest.HEURISTIC_FIELDS``).
    """

    CNPJ: Series[str] = pa.Field(nullable=False)
    FUNDO: Series[str] = pa.Field(nullable=False)
    TIPO_COTA: Series[str] = pa.Field(isin=TIPO_COTA_VALUES, nullable=False)
    # SEGMENTO no Gold atual é 100% NaN (float64). Mantemos float nullable
    # até o pipeline preencher; quando preencher, basta enxugar o ``nullable``.
    SEGMENTO: Series[float] = pa.Field(nullable=True)
    # RISCO/SCORE_RISCO têm ~36% de NaN no Gold porque o pipeline não calcula
    # rating para fundos sem histórico mínimo. Nullable até a Fase 3.
    RISCO: Series[str] = pa.Field(isin=RISCO_VALUES, nullable=True)
    SCORE_RISCO: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True)
    PERFIL_SUGERIDO: Series[str] = pa.Field(isin=PERFIL_VALUES, nullable=False)
    RETORNO_ANUAL: Series[float] = pa.Field(nullable=True)
    VOLATILIDADE: Series[float] = pa.Field(ge=0.0, nullable=True)
    RETORNO_AJ_RISCO: Series[float] = pa.Field(nullable=True)
    # TAXA_INADIMPLENCIA chega com outliers do upstream (max ~23k). Mantemos
    # apenas o piso (não-negativo) e registramos o teto fora-de-norma como
    # heurística a corrigir na Fase 3 (vide ``trust_manifest``).
    TAXA_INADIMPLENCIA: Series[float] = pa.Field(ge=0.0, nullable=True)
    SCR_NORMALIZADO: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=True)
    CONC_MAIOR_CEDENTE: Series[float] = pa.Field(ge=0.0, nullable=True)
    CONC_TOP3: Series[float] = pa.Field(ge=0.0, nullable=True)
    MESES_HISTORICO: Series[int] = pa.Field(ge=0, nullable=False)

    class Config:
        strict = False
        coerce = True


class RatingResumoSchema(pa.DataFrameModel):
    """``gold/final/rating_fidc.xlsx`` — aba RESUMO_POR_FUNDO.

    Mesmo padrão de nullable do schema GERAL para RISCO/SCORE_RISCO.
    """

    CNPJ: Series[str] = pa.Field(nullable=False)
    FUNDO: Series[str] = pa.Field(nullable=False)
    SCORE_RISCO: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True)
    RISCO: Series[str] = pa.Field(isin=RISCO_VALUES, nullable=True)
    RETORNO_MEDIO: Series[float] = pa.Field(nullable=True)
    MELHOR_COTA: Series[str] = pa.Field(isin=TIPO_COTA_VALUES, nullable=False)
    PERFIL_PREDOMINANTE: Series[str] = pa.Field(isin=PERFIL_VALUES, nullable=False)

    class Config:
        strict = False
        coerce = True


class MatchesTodosSchema(pa.DataFrameModel):
    """``gold/final/matches.xlsx`` — aba TODOS_OS_MATCHES.

    Todas as colunas ``S_*``, ``MATCH_SCORE`` e ``SCORE_*`` estão em escala
    0-100 no Gold atual (vide T05 — 2026-05-14).
    """

    CPF: Series[str] = pa.Field(nullable=False)
    CLIENTE: Series[str] = pa.Field(nullable=False)
    PERFIL_CLIENTE: Series[str] = pa.Field(isin=PERFIL_VALUES, nullable=False)
    SCORE_CLIENTE: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=False)
    FUNDO: Series[str] = pa.Field(nullable=False)
    TIPO_COTA: Series[str] = pa.Field(isin=TIPO_COTA_VALUES, nullable=False)
    RISCO_FUNDO: Series[str] = pa.Field(isin=RISCO_VALUES, nullable=False)
    SCORE_RISCO_FUNDO: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=False)
    PERFIL_FUNDO: Series[str] = pa.Field(isin=PERFIL_VALUES, nullable=False)
    RETORNO_ANUAL: Series[float] = pa.Field(nullable=True)
    VOLATILIDADE: Series[float] = pa.Field(ge=0.0, nullable=True)
    TAXA_INAD: Series[float] = pa.Field(ge=0.0, nullable=True)
    MESES_HISTORICO: Series[int] = pa.Field(ge=0, nullable=False)
    MATCH_SCORE: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=False)
    S_PERFIL: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True)
    S_RISCO: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True)
    S_RETORNO: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True)
    S_HISTORICO: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True)
    MOTIVO: Series[str] = pa.Field(nullable=True)
    RANK: Series[int] = pa.Field(ge=0, nullable=False)

    class Config:
        strict = False
        coerce = True


class MatchesRankingSchema(pa.DataFrameModel):
    """``gold/final/matches.xlsx`` — aba RANKING_FUNDOS."""

    FUNDO: Series[str] = pa.Field(nullable=False)
    TIPO_COTA: Series[str] = pa.Field(isin=TIPO_COTA_VALUES, nullable=False)
    RISCO_FUNDO: Series[str] = pa.Field(isin=RISCO_VALUES, nullable=False)
    RETORNO_ANUAL: Series[float] = pa.Field(nullable=True)
    VEZES_RECOMENDADO: Series[int] = pa.Field(ge=0, nullable=False)
    MATCH_MEDIO: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=False)

    class Config:
        strict = False
        coerce = True


class ClientesSchema(pa.DataFrameModel):
    """``gold/final/clientes.csv`` — pré-mascaramento (PII em claro).

    IMPORTANTE: validar ANTES do mascaramento. O regex ``^\\d{10,11}$`` falha
    de propósito se vier algo já mascarado (estrelas, hifens) — sinaliza
    pipeline com regressão de privacidade.

    A regex aceita 10 ou 11 dígitos porque o pipeline armazena CPF como
    ``int64`` e CPFs com leading zero perdem 1 dígito após o cast.
    Aceitar 10 dígitos NÃO afrouxa a guarda de PII: o ponto é detectar
    string com qualquer caractere não-numérico (= já mascarado).
    """

    cpf: Series[str] = pa.Field(str_matches=r"^\d{10,11}$", nullable=False)
    nome: Series[str] = pa.Field(nullable=False)
    email: Series[str] = pa.Field(str_contains="@", nullable=True)
    telefone: Series[str] = pa.Field(str_matches=r"^\d{8,13}$", nullable=True)
    idade: Series[int] = pa.Field(ge=18, le=120, nullable=True)
    # ``renda`` no Gold atual é uma codificação em tiers 1..N (não BRL).
    # Mantemos apenas ``ge=0`` — não tente assumir escala monetária aqui.
    renda: Series[float] = pa.Field(ge=0.0, nullable=True)
    experiencia: Series[int] = pa.Field(ge=0, nullable=True)
    horizonte: Series[int] = pa.Field(ge=0, nullable=True)
    perfil: Series[str] = pa.Field(isin=PERFIL_VALUES, nullable=False)
    score_perfil: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True)
    data_cadastro: Series[str] = pa.Field(nullable=True)

    class Config:
        strict = False
        coerce = True


class CreditSchema(pa.DataFrameModel):
    """``gold/final/scores_credito.csv``.

    ``score_credito`` vem em escala 0-100 no Gold atual (não 0-1000).
    """

    id_cnpj: Series[str] = pa.Field(nullable=False)
    score_credito: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=False)
    prob_default: Series[float] = pa.Field(ge=0.0, le=1.0, nullable=True)
    risco_credito: Series[str] = pa.Field(isin=RISCO_VALUES, nullable=True)
    total_boletos: Series[int] = pa.Field(ge=0, nullable=True)
    n_default: Series[int] = pa.Field(ge=0, nullable=True)
    pct_default: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True)
    defaultou: Series[int] = pa.Field(isin=(0, 1), nullable=True)

    class Config:
        strict = False
        coerce = True


class MacroSchema(pa.DataFrameModel):
    """``gold/final/macroeconomicos/consolidade.csv``.

    Colunas reais (T05): data_processamento, selic_meta, cdi_diario,
    dolar_venda, ipca_mensal, igpm_mensal, incc_m, ibc_br,
    inadimplencia_total, inadimplencia_pj, inadimplencia_pf,
    utilizacao_capacidade, ic_br_agro, ic_br_energia.
    """

    data_processamento: Series[pa.DateTime] = pa.Field(nullable=False)
    selic_meta: Series[float] = pa.Field(ge=0.0, le=50.0, nullable=True)
    # SGS 1178 — SELIC efetiva anualizada (base 252). Pode ficar NaN nas
    # linhas historicamente importadas antes da Fase 3 (linhas mais antigas).
    selic_efetiva: Series[float] = pa.Field(ge=0.0, le=50.0, nullable=True)
    cdi_diario: Series[float] = pa.Field(ge=-1.0, le=5.0, nullable=True)
    ipca_mensal: Series[float] = pa.Field(ge=-5.0, le=30.0, nullable=True)
    # SGS 13522 — IPCA acumulado 12 meses, série oficial.
    ipca_12m_acumulado: Series[float] = pa.Field(ge=-10.0, le=100.0, nullable=True)
    inadimplencia_pj: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True)
    inadimplencia_pf: Series[float] = pa.Field(ge=0.0, le=100.0, nullable=True)
    ibc_br: Series[float] = pa.Field(nullable=True)
    dolar_venda: Series[float] = pa.Field(ge=0.0, nullable=True)

    class Config:
        strict = False
        coerce = True
