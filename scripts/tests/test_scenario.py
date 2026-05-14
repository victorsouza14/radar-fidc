"""Testes das regras de cenário macro — ``scripts/lib/scenario.py``.

``scenario.py`` é fonte única de verdade para:

- ``classify_selic(selic)`` → cenário/descrição usado no payload macro
- ``score_macro(cenario, indexador)`` → score 0-100 usado no rating

Boundaries críticos: SELIC = 13.0 (pós-fixado), SELIC = 10.0 (neutro).
"""

from __future__ import annotations

import pytest

from lib.scenario import (
    CENARIO_INDISPONIVEL,
    SCORE_MACRO_POR_CENARIO,
    SELIC_LIMITE_NEUTRO,
    SELIC_LIMITE_POSFIXADO,
    CenarioMacro,
    classify_selic,
    score_macro,
)


class TestClassifySelic:
    """Boundaries do classificador de cenário."""

    def test_none_retorna_indisponivel_singleton(self) -> None:
        cen = classify_selic(None)
        assert cen is CENARIO_INDISPONIVEL
        assert cen.chave == "indisponivel"
        assert "Sem dados" in cen.descricao

    def test_acima_do_limite_posfixado_eh_posfixado(self) -> None:
        cen = classify_selic(15.0)
        assert cen.chave == "favoravel_posfixado"
        assert "pós-fixados" in cen.descricao
        assert "15.00" in cen.descricao

    def test_exatamente_no_limite_posfixado_eh_posfixado(self) -> None:
        cen = classify_selic(SELIC_LIMITE_POSFIXADO)
        assert cen.chave == "favoravel_posfixado"

    def test_logo_abaixo_do_limite_posfixado_eh_neutro(self) -> None:
        cen = classify_selic(12.99)
        assert cen.chave == "neutro"

    def test_no_limite_neutro_eh_neutro(self) -> None:
        cen = classify_selic(SELIC_LIMITE_NEUTRO)
        assert cen.chave == "neutro"

    def test_meio_da_faixa_neutra_eh_neutro(self) -> None:
        cen = classify_selic(11.5)
        assert cen.chave == "neutro"
        assert "neutro" in cen.descricao.lower()

    def test_logo_abaixo_do_limite_neutro_eh_prefixado(self) -> None:
        cen = classify_selic(9.99)
        assert cen.chave == "favoravel_prefixado"

    def test_selic_baixa_eh_prefixado(self) -> None:
        cen = classify_selic(5.0)
        assert cen.chave == "favoravel_prefixado"
        assert "pré-fixados" in cen.descricao
        assert "5.00" in cen.descricao

    def test_retorna_dataclass_com_atributos(self) -> None:
        cen = classify_selic(13.5)
        assert isinstance(cen, CenarioMacro)
        assert hasattr(cen, "chave")
        assert hasattr(cen, "descricao")

    @pytest.mark.parametrize(
        ("selic", "chave_esperada"),
        [
            (20.0, "favoravel_posfixado"),
            (13.5, "favoravel_posfixado"),
            (13.0, "favoravel_posfixado"),
            (12.0, "neutro"),
            (10.0, "neutro"),
            (9.5, "favoravel_prefixado"),
            (2.0, "favoravel_prefixado"),
        ],
    )
    def test_tabela_de_casos(self, selic: float, chave_esperada: str) -> None:
        assert classify_selic(selic).chave == chave_esperada


class TestScoreMacro:
    """Tabela ``SCORE_MACRO_POR_CENARIO`` e função wrapper ``score_macro``."""

    @pytest.mark.parametrize(
        ("cenario", "indexador", "esperado"),
        [
            ("favoravel_posfixado", "posfixado", 85.0),
            ("favoravel_posfixado", "prefixado", 45.0),
            ("favoravel_posfixado", "indefinido", 65.0),
            ("neutro", "posfixado", 60.0),
            ("neutro", "prefixado", 55.0),
            ("neutro", "indefinido", 57.5),
            ("favoravel_prefixado", "posfixado", 45.0),
            ("favoravel_prefixado", "prefixado", 80.0),
            ("indisponivel", "posfixado", 50.0),
            ("indisponivel", "prefixado", 50.0),
            ("indisponivel", "indefinido", 50.0),
        ],
    )
    def test_casos_conhecidos(self, cenario: str, indexador: str, esperado: float) -> None:
        assert score_macro(cenario, indexador) == esperado

    def test_cenario_desconhecido_cai_para_indisponivel(self) -> None:
        assert score_macro("ufo", "posfixado") == 50.0

    def test_indexador_desconhecido_retorna_50(self) -> None:
        assert score_macro("favoravel_posfixado", "ufo") == 50.0

    def test_ambos_desconhecidos_retorna_50(self) -> None:
        assert score_macro("ufo", "ufo") == 50.0

    def test_tabela_cobre_quatro_cenarios(self) -> None:
        esperados = {"favoravel_posfixado", "neutro", "favoravel_prefixado", "indisponivel"}
        assert set(SCORE_MACRO_POR_CENARIO.keys()) == esperados

    def test_posfixado_tem_score_maior_em_cenario_posfixado(self) -> None:
        cen = SCORE_MACRO_POR_CENARIO["favoravel_posfixado"]
        assert cen["posfixado"] > cen["prefixado"]
        assert cen["posfixado"] > cen["indefinido"]

    def test_prefixado_tem_score_maior_em_cenario_prefixado(self) -> None:
        cen = SCORE_MACRO_POR_CENARIO["favoravel_prefixado"]
        assert cen["prefixado"] > cen["posfixado"]
        assert cen["prefixado"] > cen["indefinido"]
