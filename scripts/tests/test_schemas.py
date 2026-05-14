"""Testes dos schemas pandera de ``lib.schemas``.

TDD: cada schema tem (a) DataFrame válido que passa, (b) DataFrame inválido
em pelo menos 2 dimensões que falha com ``SchemaErrors`` (lazy=True).

Para isolar schema drift, esses testes NÃO batem no ADLS — usam fixtures
sintéticas que replicam a forma do Gold mapeada em T05 (vide
``docs/plans/2026-05-14-radar-fidc-fase-2.md``).
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
import pytest


# ─── Rating ──────────────────────────────────────────────────────────────
@pytest.fixture
def rating_geral_valid() -> pd.DataFrame:
    """Replica a forma real da aba GERAL (T05).

    CNPJ vem como int64 no Excel; o schema coage para str. SEGMENTO é 100%
    NaN no Gold atual e por isso entra como ``None``.
    """
    return pd.DataFrame(
        {
            "CNPJ": [12345678000190, 98765432000110],
            "FUNDO": ["FIDC ABC", "FIDC XYZ"],
            "TIPO_COTA": ["UNICA", "JUNIOR"],
            "SEGMENTO": [None, None],
            "RISCO": ["BAIXO", "MEDIO"],
            "SCORE_RISCO": [42.5, 78.0],
            "PERFIL_SUGERIDO": ["CONSERVADOR", "MODERADO"],
            "RETORNO_ANUAL": [12.3, 18.5],
            "VOLATILIDADE": [3.0, 7.0],
            "RETORNO_AJ_RISCO": [4.1, 2.6],
            "TAXA_INADIMPLENCIA": [1.2, 4.5],
            "SCR_NORMALIZADO": [0.5, 0.7],
            "CONC_MAIOR_CEDENTE": [0.0, 0.0],
            "CONC_TOP3": [0.0, 0.0],
            "MESES_HISTORICO": [12, 24],
        }
    )


class TestRatingGeralSchema:
    def test_valid_df_passes(self, rating_geral_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingGeralSchema

        RatingGeralSchema.validate(rating_geral_valid, lazy=True)

    def test_score_above_100_fails(self, rating_geral_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingGeralSchema

        bad = rating_geral_valid.copy()
        bad.loc[0, "SCORE_RISCO"] = 150.0
        with pytest.raises(pa.errors.SchemaErrors):
            RatingGeralSchema.validate(bad, lazy=True)

    def test_invalid_risco_fails(self, rating_geral_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingGeralSchema

        bad = rating_geral_valid.copy()
        bad.loc[0, "RISCO"] = "FOOBAR"
        with pytest.raises(pa.errors.SchemaErrors):
            RatingGeralSchema.validate(bad, lazy=True)

    def test_sem_dados_risco_aceita(self, rating_geral_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingGeralSchema

        df = rating_geral_valid.copy()
        df.loc[0, "RISCO"] = "SEM DADOS"
        RatingGeralSchema.validate(df, lazy=True)

    def test_invalid_tipo_cota_fails(self, rating_geral_valid: pd.DataFrame) -> None:
        from lib.schemas import RatingGeralSchema

        bad = rating_geral_valid.copy()
        bad.loc[0, "TIPO_COTA"] = "QUARTA_CLASSE"
        with pytest.raises(pa.errors.SchemaErrors):
            RatingGeralSchema.validate(bad, lazy=True)

    def test_perfil_arrojado_aceito(self, rating_geral_valid: pd.DataFrame) -> None:
        """O Gold usa ARROJADO (e não AGRESSIVO) — schema deve aceitar."""
        from lib.schemas import RatingGeralSchema

        df = rating_geral_valid.copy()
        df.loc[0, "PERFIL_SUGERIDO"] = "ARROJADO"
        RatingGeralSchema.validate(df, lazy=True)

    def test_taxa_inad_outlier_aceita(self, rating_geral_valid: pd.DataFrame) -> None:
        """TAXA_INADIMPLENCIA real no Gold chega a ~23k. Schema só checa ge=0."""
        from lib.schemas import RatingGeralSchema

        df = rating_geral_valid.copy()
        df.loc[0, "TAXA_INADIMPLENCIA"] = 5000.0
        RatingGeralSchema.validate(df, lazy=True)


# ─── Matches ─────────────────────────────────────────────────────────────
@pytest.fixture
def matches_todos_valid() -> pd.DataFrame:
    """Replica a forma real da aba TODOS_OS_MATCHES (T05).

    Escalas 0-100 para ``MATCH_SCORE``, ``SCORE_CLIENTE`` e ``S_*``.
    """
    return pd.DataFrame(
        {
            "CPF": [12345678901, 98765432100],
            "CLIENTE": ["Ana Lima", "Bruno Souza"],
            "PERFIL_CLIENTE": ["MODERADO", "ARROJADO"],
            "SCORE_CLIENTE": [65.0, 82.0],
            "FUNDO": ["FIDC ABC", "FIDC XYZ"],
            "TIPO_COTA": ["UNICA", "SENIOR"],
            "RISCO_FUNDO": ["BAIXO", "MEDIO"],
            "SCORE_RISCO_FUNDO": [42.5, 78.0],
            "PERFIL_FUNDO": ["CONSERVADOR", "ARROJADO"],
            "RETORNO_ANUAL": [12.3, 18.5],
            "VOLATILIDADE": [3.0, 7.0],
            "TAXA_INAD": [1.2, 4.5],
            "MESES_HISTORICO": [12, 24],
            "MATCH_SCORE": [85.0, 72.0],
            "S_PERFIL": [100, 80],
            "S_RISCO": [80.0, 70.0],
            "S_RETORNO": [60.0, 90.0],
            "S_HISTORICO": [50.0, 80.0],
            "MOTIVO": ["Bom alinhamento", "Histórico curto"],
            "RANK": [1, 2],
        }
    )


@pytest.fixture
def matches_ranking_valid() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "FUNDO": ["FIDC ABC"],
            "TIPO_COTA": ["UNICA"],
            "RISCO_FUNDO": ["BAIXO"],
            "RETORNO_ANUAL": [12.3],
            "VEZES_RECOMENDADO": [42],
            "MATCH_MEDIO": [78.0],
        }
    )


class TestMatchesTodosSchema:
    def test_valid_df_passes(self, matches_todos_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesTodosSchema

        MatchesTodosSchema.validate(matches_todos_valid, lazy=True)

    def test_match_score_above_100_fails(self, matches_todos_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesTodosSchema

        bad = matches_todos_valid.copy()
        bad.loc[0, "MATCH_SCORE"] = 150.0
        with pytest.raises(pa.errors.SchemaErrors):
            MatchesTodosSchema.validate(bad, lazy=True)

    def test_rank_negative_fails(self, matches_todos_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesTodosSchema

        bad = matches_todos_valid.copy()
        bad.loc[0, "RANK"] = -1
        with pytest.raises(pa.errors.SchemaErrors):
            MatchesTodosSchema.validate(bad, lazy=True)

    def test_invalid_risco_fundo_fails(self, matches_todos_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesTodosSchema

        bad = matches_todos_valid.copy()
        bad.loc[0, "RISCO_FUNDO"] = "QUEROZENE"
        with pytest.raises(pa.errors.SchemaErrors):
            MatchesTodosSchema.validate(bad, lazy=True)


class TestMatchesRankingSchema:
    def test_valid_df_passes(self, matches_ranking_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesRankingSchema

        MatchesRankingSchema.validate(matches_ranking_valid, lazy=True)

    def test_vezes_recomendado_negative_fails(self, matches_ranking_valid: pd.DataFrame) -> None:
        from lib.schemas import MatchesRankingSchema

        bad = matches_ranking_valid.copy()
        bad.loc[0, "VEZES_RECOMENDADO"] = -5
        with pytest.raises(pa.errors.SchemaErrors):
            MatchesRankingSchema.validate(bad, lazy=True)


# ─── Clientes ────────────────────────────────────────────────────────────
@pytest.fixture
def clientes_valid() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cpf": ["12345678901", "98765432100"],
            "nome": ["Ana Lima", "Bruno Souza"],
            "email": ["ana@exemplo.com", "bruno@exemplo.com"],
            "telefone": ["11999990000", "21988880000"],
            "idade": [30, 45],
            "renda": [1.0, 2.0],  # gold usa tiers 1..N, não BRL
            "experiencia": [3, 10],
            "horizonte": [5, 10],
            "perfil": ["MODERADO", "ARROJADO"],
            "score_perfil": [65.0, 82.0],
            "data_cadastro": ["2025-01-15", "2024-06-22"],
        }
    )


class TestClientesSchema:
    def test_valid_df_passes(self, clientes_valid: pd.DataFrame) -> None:
        from lib.schemas import ClientesSchema

        ClientesSchema.validate(clientes_valid, lazy=True)

    def test_cpf_already_masked_fails(self, clientes_valid: pd.DataFrame) -> None:
        """Sinaliza regressão de privacidade: pipeline NÃO pode entregar PII mascarada."""
        from lib.schemas import ClientesSchema

        bad = clientes_valid.copy()
        bad.loc[0, "cpf"] = "***.***.***-01"
        with pytest.raises(pa.errors.SchemaErrors):
            ClientesSchema.validate(bad, lazy=True)

    def test_cpf_10_digits_aceito(self, clientes_valid: pd.DataFrame) -> None:
        """CPFs originalmente com leading zero perdem 1 dígito no cast int64→str.

        Aceitar 10 dígitos é necessário pra refletir o pipeline real;
        máscaras com qualquer não-dígito continuam falhando.
        """
        from lib.schemas import ClientesSchema

        df = clientes_valid.copy()
        df.loc[0, "cpf"] = "1234567890"  # 10 dígitos (leading zero perdido)
        ClientesSchema.validate(df, lazy=True)

    def test_invalid_perfil_fails(self, clientes_valid: pd.DataFrame) -> None:
        from lib.schemas import ClientesSchema

        bad = clientes_valid.copy()
        bad.loc[0, "perfil"] = "DESCONHECIDO"
        with pytest.raises(pa.errors.SchemaErrors):
            ClientesSchema.validate(bad, lazy=True)

    def test_idade_below_18_fails(self, clientes_valid: pd.DataFrame) -> None:
        from lib.schemas import ClientesSchema

        bad = clientes_valid.copy()
        bad.loc[0, "idade"] = 12
        with pytest.raises(pa.errors.SchemaErrors):
            ClientesSchema.validate(bad, lazy=True)


# ─── Credit ──────────────────────────────────────────────────────────────
@pytest.fixture
def credit_valid() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id_cnpj": ["a1b2c3", "d4e5f6"],
            "prob_default": [0.12, 0.85],
            "score_credito": [82.5, 23.1],
            "risco_credito": ["BAIXO", "ALTO"],
            "total_boletos": [12, 80],
            "n_default": [0, 60],
            "pct_default": [0.0, 75.0],
            "defaultou": [0, 1],
        }
    )


class TestCreditSchema:
    def test_valid_df_passes(self, credit_valid: pd.DataFrame) -> None:
        from lib.schemas import CreditSchema

        CreditSchema.validate(credit_valid, lazy=True)

    def test_score_above_100_fails(self, credit_valid: pd.DataFrame) -> None:
        from lib.schemas import CreditSchema

        bad = credit_valid.copy()
        bad.loc[0, "score_credito"] = 150.0
        with pytest.raises(pa.errors.SchemaErrors):
            CreditSchema.validate(bad, lazy=True)

    def test_prob_default_above_1_fails(self, credit_valid: pd.DataFrame) -> None:
        from lib.schemas import CreditSchema

        bad = credit_valid.copy()
        bad.loc[0, "prob_default"] = 1.5
        with pytest.raises(pa.errors.SchemaErrors):
            CreditSchema.validate(bad, lazy=True)

    def test_defaultou_invalid_value_fails(self, credit_valid: pd.DataFrame) -> None:
        from lib.schemas import CreditSchema

        bad = credit_valid.copy()
        bad.loc[0, "defaultou"] = 2
        with pytest.raises(pa.errors.SchemaErrors):
            CreditSchema.validate(bad, lazy=True)


# ─── Macro ───────────────────────────────────────────────────────────────
@pytest.fixture
def macro_valid() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "data_processamento": pd.to_datetime(["2026-05-13", "2026-05-14"]),
            "selic_meta": [13.75, 13.75],
            "selic_efetiva": [13.65, 13.65],  # SGS 1178 — taxa efetiva anualizada
            "cdi_diario": [0.05, 0.05],
            "dolar_venda": [5.10, 5.12],
            "ipca_mensal": [0.4, 0.3],
            "ipca_12m_acumulado": [4.20, 4.39],  # SGS 13522 — IPCA 12m oficial
            "inadimplencia_pj": [3.5, 3.6],
            "inadimplencia_pf": [5.5, 5.4],
            "ibc_br": [142.3, 142.7],
        }
    )


class TestMacroSchema:
    def test_valid_df_passes(self, macro_valid: pd.DataFrame) -> None:
        from lib.schemas import MacroSchema

        MacroSchema.validate(macro_valid, lazy=True)

    def test_selic_negative_fails(self, macro_valid: pd.DataFrame) -> None:
        from lib.schemas import MacroSchema

        bad = macro_valid.copy()
        bad.loc[0, "selic_meta"] = -1.0
        with pytest.raises(pa.errors.SchemaErrors):
            MacroSchema.validate(bad, lazy=True)

    def test_ipca_outrageous_fails(self, macro_valid: pd.DataFrame) -> None:
        from lib.schemas import MacroSchema

        bad = macro_valid.copy()
        bad.loc[0, "ipca_mensal"] = 50.0  # > teto 30%
        with pytest.raises(pa.errors.SchemaErrors):
            MacroSchema.validate(bad, lazy=True)
