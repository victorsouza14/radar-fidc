"""Testes das regras de perfil — ``scripts/lib/perfil_rules.py``.

Cobertura das duas tabelas centrais do match score:

- ``PERFIL_SUGERIDO``: TIPO_COTA x CATEGORIA_RISCO → PERFIL (aplicado após os
  tercis de Tukey definirem a CATEGORIA_RISCO no Databricks).
- ``ALINHAMENTO``: matriz cliente x fundo, 0-100, usada pelo match engine.

Estes testes blindam invariantes documentadas no docstring do módulo —
mudanças de calibragem precisam alterar tabela E teste no mesmo commit.
"""

from __future__ import annotations

import pytest

from lib.perfil_rules import (
    ALINHAMENTO,
    PERFIL_SUGERIDO,
    perfil_sugerido,
    score_perfil,
)

# Domínios locais para os testes — refletem o universo aceito pelas
# tabelas ``PERFIL_SUGERIDO`` e ``ALINHAMENTO`` em ``perfil_rules.py``.
PERFIS = ("CONSERVADOR", "MODERADO", "ARROJADO")
TIPOS_COTA = ("UNICA", "SENIOR", "MEZANINO", "JUNIOR")
CATEGORIAS_RISCO = ("BAIXO", "MEDIO", "ALTO")


# ─── PERFIL_SUGERIDO (TIPO_COTA x RISCO → PERFIL) ────────────────────────
class TestPerfilSugeridoDict:
    """Invariantes da tabela ``PERFIL_SUGERIDO``."""

    def test_unica_baixo_conservador(self) -> None:
        assert PERFIL_SUGERIDO[("UNICA", "BAIXO")] == "CONSERVADOR"

    def test_unica_alto_arrojado(self) -> None:
        assert PERFIL_SUGERIDO[("UNICA", "ALTO")] == "ARROJADO"

    def test_senior_alto_amortece_para_moderado(self) -> None:
        """Invariante documentada: cota sênior amortece risco do fundo."""
        assert PERFIL_SUGERIDO[("SENIOR", "ALTO")] == "MODERADO"

    def test_junior_alto_arrojado(self) -> None:
        assert PERFIL_SUGERIDO[("JUNIOR", "ALTO")] == "ARROJADO"

    def test_junior_baixo_eleva_para_moderado(self) -> None:
        assert PERFIL_SUGERIDO[("JUNIOR", "BAIXO")] == "MODERADO"

    def test_mezanino_baixo_moderado(self) -> None:
        assert PERFIL_SUGERIDO[("MEZANINO", "BAIXO")] == "MODERADO"

    def test_mezanino_alto_arrojado(self) -> None:
        assert PERFIL_SUGERIDO[("MEZANINO", "ALTO")] == "ARROJADO"

    def test_cobre_todas_combinacoes_validas(self) -> None:
        for tipo in TIPOS_COTA:
            for risco in CATEGORIAS_RISCO:
                assert (tipo, risco) in PERFIL_SUGERIDO, f"Faltou mapeamento para ({tipo}, {risco})"

    def test_todos_valores_sao_perfis_validos(self) -> None:
        for chave, perfil in PERFIL_SUGERIDO.items():
            assert perfil in PERFIS, f"{chave} aponta para perfil inválido: {perfil}"

    def test_cada_perfil_eh_atingivel(self) -> None:
        atingiveis = set(PERFIL_SUGERIDO.values())
        for perfil in PERFIS:
            assert perfil in atingiveis, f"Perfil {perfil} não é atingível"

    def test_total_combinacoes_eh_4x3(self) -> None:
        assert len(PERFIL_SUGERIDO) == len(TIPOS_COTA) * len(CATEGORIAS_RISCO) == 12


class TestPerfilSugeridoFunction:
    """Função wrapper ``perfil_sugerido(tipo_cota, risco)``."""

    @pytest.mark.parametrize(
        ("tipo_cota", "risco", "esperado"),
        [
            ("UNICA", "BAIXO", "CONSERVADOR"),
            ("UNICA", "MEDIO", "MODERADO"),
            ("UNICA", "ALTO", "ARROJADO"),
            ("SENIOR", "ALTO", "MODERADO"),
            ("JUNIOR", "ALTO", "ARROJADO"),
            ("MEZANINO", "MEDIO", "MODERADO"),
        ],
    )
    def test_casos_validos_coincidem_com_dict(
        self,
        tipo_cota: str,
        risco: str,
        esperado: str,
    ) -> None:
        assert perfil_sugerido(tipo_cota, risco) == esperado
        assert PERFIL_SUGERIDO[(tipo_cota, risco)] == esperado

    def test_tipo_cota_invalido_fallback(self) -> None:
        assert perfil_sugerido("QUARTA_CLASSE", "BAIXO") == "SEM DADOS"

    def test_categoria_risco_invalida_fallback(self) -> None:
        assert perfil_sugerido("UNICA", "DESCONHECIDO") == "SEM DADOS"

    def test_ambos_invalidos_fallback(self) -> None:
        assert perfil_sugerido("FOO", "BAR") == "SEM DADOS"


class TestAlinhamentoMatrix:
    """Invariantes da matriz ``ALINHAMENTO`` (cliente x fundo)."""

    def test_diagonal_eh_score_maximo(self) -> None:
        for perfil in PERFIS:
            assert ALINHAMENTO[perfil][perfil] == 100, f"Diagonal de {perfil}x{perfil} deveria ser 100"

    def test_conservador_vs_arrojado_penalidade_maxima(self) -> None:
        assert ALINHAMENTO["CONSERVADOR"]["ARROJADO"] == 0

    def test_arrojado_vs_conservador_nao_eh_zero(self) -> None:
        assert ALINHAMENTO["ARROJADO"]["CONSERVADOR"] > 0

    def test_matriz_nao_eh_simetrica(self) -> None:
        cons_arr = ALINHAMENTO["CONSERVADOR"]["ARROJADO"]
        arr_cons = ALINHAMENTO["ARROJADO"]["CONSERVADOR"]
        assert cons_arr != arr_cons

    def test_cobre_todos_pares_perfil(self) -> None:
        total_pares = 0
        for cliente in PERFIS:
            for fundo in PERFIS:
                assert fundo in ALINHAMENTO[cliente]
                total_pares += 1
        assert total_pares == 9

    def test_todos_valores_em_0_100(self) -> None:
        for cliente, linha in ALINHAMENTO.items():
            for fundo, score in linha.items():
                assert 0 <= score <= 100, f"{cliente}x{fundo}={score} fora do range"

    def test_diagonal_eh_o_maximo_da_linha(self) -> None:
        for cliente in PERFIS:
            linha = ALINHAMENTO[cliente]
            melhor = max(linha, key=lambda k: linha[k])
            assert melhor == cliente


class TestScorePerfilFunction:
    """Função wrapper ``score_perfil(perfil_cliente, perfil_fundo)``."""

    @pytest.mark.parametrize("perfil", PERFIS)
    def test_diagonal_retorna_100(self, perfil: str) -> None:
        assert score_perfil(perfil, perfil) == 100

    def test_conservador_arrojado_retorna_zero(self) -> None:
        assert score_perfil("CONSERVADOR", "ARROJADO") == 0

    def test_perfil_cliente_invalido_retorna_zero(self) -> None:
        assert score_perfil("DESCONHECIDO", "MODERADO") == 0.0

    def test_perfil_fundo_invalido_retorna_zero(self) -> None:
        assert score_perfil("MODERADO", "DESCONHECIDO") == 0.0

    def test_ambos_invalidos_retorna_zero(self) -> None:
        assert score_perfil("FOO", "BAR") == 0.0

    @pytest.mark.parametrize(
        ("cliente", "fundo", "esperado"),
        [
            ("MODERADO", "CONSERVADOR", 70),
            ("MODERADO", "ARROJADO", 40),
            ("ARROJADO", "MODERADO", 80),
            ("CONSERVADOR", "MODERADO", 30),
        ],
    )
    def test_offdiagonal_conhecido(self, cliente: str, fundo: str, esperado: int) -> None:
        assert score_perfil(cliente, fundo) == esperado
