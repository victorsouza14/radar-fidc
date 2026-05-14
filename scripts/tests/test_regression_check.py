"""Testes do regression check entre ``data.json`` candidato e HEAD~1."""

from __future__ import annotations

import copy
from typing import Any

import pytest


@pytest.fixture
def base_data() -> dict[str, Any]:
    return {
        "macro": {"data_ref": "2026-05-13"},
        "fidcs": {"stats": {"total_classes": 2400}},
        "matches": {"total": 12000},
    }


def _patch(d: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Devolve uma cópia profunda de ``d`` com ``path`` ('a.b.c') = ``value``."""
    out: dict[str, Any] = copy.deepcopy(d)
    parts = path.split(".")
    cur: Any = out
    for key in parts[:-1]:
        cur = cur[key]
    cur[parts[-1]] = value
    return out


class TestCheckRegression:
    def test_no_changes_passes(self, base_data: dict[str, Any]) -> None:
        from lib.regression_check import check_regression

        ok, reasons = check_regression(base_data, base_data, bypass=False)
        assert ok is True
        assert reasons == []

    def test_small_fidc_change_passes(self, base_data: dict[str, Any]) -> None:
        from lib.regression_check import check_regression

        current = _patch(base_data, "fidcs.stats.total_classes", 2450)  # +2%
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is True
        assert reasons == []

    def test_large_fidc_drop_fails(self, base_data: dict[str, Any]) -> None:
        from lib.regression_check import check_regression

        current = _patch(base_data, "fidcs.stats.total_classes", 2000)  # -16.7%
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is False
        assert any("fidcs" in r.lower() for r in reasons)

    def test_large_matches_drop_fails(self, base_data: dict[str, Any]) -> None:
        from lib.regression_check import check_regression

        current = _patch(base_data, "matches.total", 8000)  # -33%
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is False
        assert any("matches" in r.lower() for r in reasons)

    def test_macro_date_regression_fails(self, base_data: dict[str, Any]) -> None:
        from lib.regression_check import check_regression

        current = _patch(base_data, "macro.data_ref", "2026-05-10")
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is False
        assert any("macro" in r.lower() or "data_ref" in r.lower() for r in reasons)

    def test_bypass_returns_pass_with_note(self, base_data: dict[str, Any]) -> None:
        from lib.regression_check import check_regression

        current = _patch(base_data, "fidcs.stats.total_classes", 1)  # absurdo
        ok, reasons = check_regression(current, base_data, bypass=True)
        assert ok is True
        assert any("bypass" in r.lower() for r in reasons)

    def test_missing_previous_data_passes_with_note(self, base_data: dict[str, Any]) -> None:
        """Primeiro run da história não tem HEAD~1 → não bloqueia."""
        from lib.regression_check import check_regression

        ok, reasons = check_regression(base_data, None, bypass=False)
        assert ok is True
        assert any("anterior" in r.lower() or "previous" in r.lower() for r in reasons)

    def test_macro_date_advance_passes(self, base_data: dict[str, Any]) -> None:
        from lib.regression_check import check_regression

        current = _patch(base_data, "macro.data_ref", "2026-05-14")
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is True
        assert reasons == []

    def test_missing_keys_in_previous_does_not_crash(self, base_data: dict[str, Any]) -> None:
        """Sem fidcs/matches no anterior, a regra é ignorada (não há baseline)."""
        from lib.regression_check import check_regression

        previous: dict[str, Any] = {"macro": {"data_ref": "2026-05-13"}}
        ok, reasons = check_regression(base_data, previous, bypass=False)
        assert ok is True
        assert reasons == []

    def test_fidc_just_below_threshold_passes(self, base_data: dict[str, Any]) -> None:
        from lib.regression_check import check_regression

        # 9.96% queda (2400 → 2161) — abaixo do limite inclusivo de 10%.
        current = _patch(base_data, "fidcs.stats.total_classes", 2161)
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is True
        assert reasons == []

    def test_fidc_exactly_threshold_fails(self, base_data: dict[str, Any]) -> None:
        from lib.regression_check import check_regression

        # 10% queda — exatamente no limite, falha (limite inclusivo).
        current = _patch(base_data, "fidcs.stats.total_classes", 2160)
        ok, reasons = check_regression(current, base_data, bypass=False)
        assert ok is False
        assert any("fidcs" in r.lower() for r in reasons)
