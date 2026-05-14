"""Regression check — Linha 3 de defesa.

Compara ``data.json`` candidato contra a versão de HEAD~1. Bloqueia o commit
se qualquer das regras dispara, exceto se ``bypass=True`` (label
``data-regression-ok`` no PR ou input ``bypass_regression_check`` no
``workflow_dispatch``).

Regras:
1. |Δ fidcs.stats.total_classes| < 10%
2. |Δ matches.total| < 20%
3. macro.data_ref >= macro.data_ref anterior

Cada violação vira uma string em ``reasons`` para diagnóstico humano.
Mantemos ``reasons`` populado também no caminho feliz com ``bypass=True``
ou sem baseline, pra dar trilha de auditoria no CI.
"""

from __future__ import annotations

from typing import Any

# Limites inclusivos: variação >= limite é bloqueada.
FIDC_THRESHOLD = 0.10
MATCHES_THRESHOLD = 0.20


def _get(d: dict[str, Any], dotted: str) -> Any:
    """Acessa ``d['a']['b']['c']`` por ``'a.b.c'``.

    Devolve ``None`` se qualquer nível faltar ou não for dict.
    """
    cur: Any = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _abs_delta_ratio(curr: float | int | None, prev: float | int | None) -> float | None:
    """``|curr-prev| / |prev|``. ``None`` se ``prev`` é zero ou faltando."""
    if curr is None or prev is None or prev == 0:
        return None
    return abs(curr - prev) / abs(prev)


def check_regression(
    current_data: dict[str, Any],
    previous_data: dict[str, Any] | None,
    *,
    bypass: bool,
) -> tuple[bool, list[str]]:
    """Compara ``current_data`` contra ``previous_data``.

    Args:
        current_data: payload novo (gerado pelo run atual)
        previous_data: payload de HEAD~1. ``None`` = sem histórico ainda.
        bypass: ignora todas as regras (mantém auditoria nas ``reasons``).

    Returns:
        ``(ok, reasons)``. ``ok=True`` permite seguir. ``reasons`` é a lista
        de mensagens de auditoria, mesmo no caminho feliz quando bypass
        está ligado ou não há baseline.
    """
    if bypass:
        return True, ["regression_check: bypass=True (label/input override aplicado)"]

    if previous_data is None:
        return True, ["regression_check: sem data.json anterior (primeiro run; previous_data=None)"]

    reasons: list[str] = []

    # Regra 1 — FIDCs
    curr_fidcs = _get(current_data, "fidcs.stats.total_classes")
    prev_fidcs = _get(previous_data, "fidcs.stats.total_classes")
    ratio = _abs_delta_ratio(curr_fidcs, prev_fidcs)
    if ratio is not None and ratio >= FIDC_THRESHOLD:
        reasons.append(
            f"fidcs.stats.total_classes mudou {ratio:.1%} "
            f"(anterior={prev_fidcs}, atual={curr_fidcs}, limite={FIDC_THRESHOLD:.0%})"
        )

    # Regra 2 — Matches
    curr_matches = _get(current_data, "matches.total")
    prev_matches = _get(previous_data, "matches.total")
    ratio_m = _abs_delta_ratio(curr_matches, prev_matches)
    if ratio_m is not None and ratio_m >= MATCHES_THRESHOLD:
        reasons.append(
            f"matches.total mudou {ratio_m:.1%} "
            f"(anterior={prev_matches}, atual={curr_matches}, limite={MATCHES_THRESHOLD:.0%})"
        )

    # Regra 3 — macro.data_ref não pode regredir
    curr_ref = _get(current_data, "macro.data_ref")
    prev_ref = _get(previous_data, "macro.data_ref")
    if curr_ref and prev_ref and str(curr_ref) < str(prev_ref):
        reasons.append(f"macro.data_ref regrediu (anterior={prev_ref}, atual={curr_ref})")

    return (len(reasons) == 0, reasons)
