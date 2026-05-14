#!/usr/bin/env python3
"""Wrapper CLI para ``lib.regression_check.check_regression``.

Uso (em ``.github/workflows/data-refresh.yml``)::

    python scripts/run_regression_check.py \\
        --current data.json \\
        --previous /tmp/data-previous.json \\
        --bypass "${{ github.event.inputs.bypass_regression_check }}"

Exit codes:
    0 = OK
    1 = Regressão detectada
    2 = Erro de I/O do arquivo ``--current`` (arquivo ausente/inválido)

Ausência do ``--previous`` é tratada como "primeiro run da história" e não
gera erro: ``check_regression`` devolve ``ok=True`` com uma ``reason`` de
auditoria. Mesma tolerância vale se o arquivo existe mas é JSON inválido —
preferimos não bloquear o primeiro pipeline de uma branch nova por causa
disso (decisão consciente: HEAD~1 pode ser de antes da existência do
``data.json``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.logger import get_logger
from lib.regression_check import check_regression

log = get_logger(__name__)


def _load(path: Path) -> dict | None:
    """Carrega JSON de ``path``. ``None`` se arquivo não existe ou é inválido."""
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("regression_load_failed", path=str(path), error=str(exc))
        return None
    if not isinstance(loaded, dict):
        log.error("regression_load_not_dict", path=str(path), type=type(loaded).__name__)
        return None
    return loaded


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True, type=Path, help="Path para data.json atual (recém-gerado)")
    parser.add_argument(
        "--previous", required=True, type=Path, help="Path para data.json anterior (HEAD~1, pode não existir)"
    )
    parser.add_argument("--bypass", default="false", help="'true'/'1' ignora todas as regras (label override)")
    args = parser.parse_args(argv)

    current = _load(args.current)
    if current is None:
        log.error("regression_current_missing", path=str(args.current))
        return 2

    previous = _load(args.previous)
    bypass = _truthy(args.bypass)

    ok, reasons = check_regression(current, previous, bypass=bypass)
    for reason in reasons:
        log.info("regression_reason", reason=reason)
    if ok:
        log.info("regression_ok", bypass=bypass, n_notes=len(reasons))
        return 0
    log.error("regression_failed", n_reasons=len(reasons))
    return 1


if __name__ == "__main__":
    sys.exit(main())
