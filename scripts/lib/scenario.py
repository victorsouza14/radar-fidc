"""Regras de cenário macroeconômico — fonte única para SELIC → cenário/descrição.

Antes essa regra estava replicada em payload.py, 01_score_fidc.py e 02_indicadores_macro.py.
Mudanças de calibragem agora exigem só esta edição.
"""

from __future__ import annotations

from dataclasses import dataclass

SELIC_LIMITE_POSFIXADO = 13.0  # SELIC >= 13% → pós-fixados são favorecidos
SELIC_LIMITE_NEUTRO = 10.0  # 10% <= SELIC < 13% → neutro
# SELIC < 10% → pré-fixados são favorecidos


@dataclass(frozen=True)
class CenarioMacro:
    chave: str
    descricao: str


CENARIO_INDISPONIVEL = CenarioMacro("indisponivel", "Sem dados macro suficientes.")


def classify_selic(selic: float | None) -> CenarioMacro:
    """Classifica o cenário a partir do nível da SELIC.

    Args:
        selic: taxa SELIC anual em %. None se indisponível.

    Returns:
        CenarioMacro(chave, descricao). Chave nunca quebra contrato com o front.
    """
    if selic is None:
        return CENARIO_INDISPONIVEL

    if selic >= SELIC_LIMITE_POSFIXADO:
        return CenarioMacro(
            "favoravel_posfixado",
            f"SELIC {selic:.2f}% favorece FIDCs pós-fixados (CDI+). "
            "Alta remuneração relativa frente à renda fixa tradicional.",
        )
    if selic >= SELIC_LIMITE_NEUTRO:
        return CenarioMacro(
            "neutro",
            f"SELIC {selic:.2f}% em patamar neutro. Diversificação recomendada.",
        )
    return CenarioMacro(
        "favoravel_prefixado",
        f"SELIC {selic:.2f}% baixa favorece FIDCs pré-fixados.",
    )


# Para uso em scoring por indexador inferido (rating.py / payload.py).
SCORE_MACRO_POR_CENARIO = {
    # cenario_chave -> {indexador_inferido: score 0-100}
    "favoravel_posfixado": {"posfixado": 85.0, "prefixado": 45.0, "indefinido": 65.0},
    "neutro": {"posfixado": 60.0, "prefixado": 55.0, "indefinido": 57.5},
    "favoravel_prefixado": {"posfixado": 45.0, "prefixado": 80.0, "indefinido": 62.5},
    "indisponivel": {"posfixado": 50.0, "prefixado": 50.0, "indefinido": 50.0},
}


def score_macro(cenario_chave: str, indexador: str) -> float:
    """Retorna o score macro (0-100) para um indexador num cenário."""
    return SCORE_MACRO_POR_CENARIO.get(cenario_chave, SCORE_MACRO_POR_CENARIO["indisponivel"]).get(indexador, 50.0)
