"""Regras de perfil de investidor — fonte única.

Antes a mesma regra existia em 3 lugares: cadastro.py (questionário), match.py (alinhamento)
e rating.py (perfil sugerido por tipo de cota x risco).
"""

from __future__ import annotations

# Perfil sugerido = TIPO_COTA x CATEGORIA_RISCO → PERFIL.
# Aplicado em rating.py após o KMeans definir CATEGORIA_RISCO.
PERFIL_SUGERIDO = {
    ("UNICA", "BAIXO"): "CONSERVADOR",
    ("UNICA", "MEDIO"): "MODERADO",
    ("UNICA", "ALTO"): "ARROJADO",
    ("SENIOR", "BAIXO"): "CONSERVADOR",
    ("SENIOR", "MEDIO"): "MODERADO",
    ("SENIOR", "ALTO"): "MODERADO",  # cota sênior amortece risco do fundo
    ("MEZANINO", "BAIXO"): "MODERADO",
    ("MEZANINO", "MEDIO"): "MODERADO",
    ("MEZANINO", "ALTO"): "ARROJADO",
    ("JUNIOR", "BAIXO"): "MODERADO",
    ("JUNIOR", "MEDIO"): "ARROJADO",
    ("JUNIOR", "ALTO"): "ARROJADO",
}


def perfil_sugerido(tipo_cota: str, categoria_risco: str) -> str:
    """Sugere o perfil de investidor adequado para um par (tipo_cota, categoria_risco)."""
    return PERFIL_SUGERIDO.get((tipo_cota, categoria_risco), "SEM DADOS")


# Matriz de alinhamento cliente x fundo (0-100), usada em match.py.
# Linha = perfil do cliente; coluna = perfil sugerido do fundo.
ALINHAMENTO = {
    "CONSERVADOR": {"CONSERVADOR": 100, "MODERADO": 30, "ARROJADO": 0},
    "MODERADO": {"CONSERVADOR": 70, "MODERADO": 100, "ARROJADO": 40},
    "ARROJADO": {"CONSERVADOR": 60, "MODERADO": 80, "ARROJADO": 100},
}


def score_perfil(perfil_cliente: str, perfil_fundo: str) -> float:
    """Score de alinhamento perfil cliente x perfil fundo (0-100)."""
    return ALINHAMENTO.get(perfil_cliente, {}).get(perfil_fundo, 0.0)
