#!/usr/bin/env python3
"""Parse Playwright's JSON reporter output and emit a smoke-test summary.

Consumed by `.github/workflows/data-refresh.yml` to populate the
`smoke_tests` field of the trust manifest. Returns exit code 0 when every
non-skipped test passed and 1 otherwise. Tests marked `test.fixme` (skipped
on purpose) are counted as skipped and do NOT fail the run.

Usage:
    python3 scripts/smoke_summary.py [results-json-path]

    # Defaults to playwright-report/results.json (matches playwright.config.ts).
    python3 scripts/smoke_summary.py

Exit codes:
    0  → every executed test passed (skipped tests allowed).
    1  → at least one test failed, timed out, was interrupted, or the
         results file is missing/malformed.

Output (stdout, in order):
    1. Per-test "PASS|FAIL|SKIP <duration>ms <title>" lines.
    2. Blank line.
    3. Summary "Smoke summary: N passed, N failed, N skipped (Xs total)".
    4. "Result: ok" or "Result: fail".
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections.abc import Iterable
from typing import Any

DEFAULT_RESULTS_PATH = pathlib.Path("playwright-report/results.json")

# Playwright's JSON reporter writes the outcome of each attempt; we look at
# the *final* status because retries can flip a flaky run to "passed".
TERMINAL_OK = {"passed", "expected"}
TERMINAL_SKIP = {"skipped"}
TERMINAL_FAIL = {"failed", "timedOut", "interrupted", "unexpected"}


def _iter_specs(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Walk the Playwright JSON tree yielding every spec entry."""
    yield from node.get("specs", []) or []
    for child in node.get("suites", []) or []:
        yield from _iter_specs(child)


def _classify_spec(spec: dict[str, Any]) -> tuple[str, int]:
    """Return (status, duration_ms) for the spec.

    status ∈ {"passed", "failed", "skipped"}.
    """
    duration_ms = 0
    result_status = "skipped"
    for test in spec.get("tests", []) or []:
        outcome = (test.get("status") or "").lower()
        for run in test.get("results", []) or []:
            duration_ms += int(run.get("duration") or 0)
        if outcome in TERMINAL_FAIL:
            result_status = "failed"
            break
        if outcome in TERMINAL_OK:
            result_status = "passed"
        elif outcome in TERMINAL_SKIP and result_status != "passed":
            result_status = "skipped"
    return result_status, duration_ms


def _load_results(path: pathlib.Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        print(f"smoke_summary: results file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"smoke_summary: malformed JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str]) -> int:
    path = pathlib.Path(argv[1]) if len(argv) > 1 else DEFAULT_RESULTS_PATH
    report = _load_results(path)

    passed = failed = skipped = 0
    total_ms = 0
    lines: list[str] = []

    for suite in report.get("suites", []) or []:
        for spec in _iter_specs(suite):
            status, ms = _classify_spec(spec)
            total_ms += ms
            title = spec.get("title") or "<untitled>"
            tag = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[status]
            lines.append(f"{tag}  {ms:>5d}ms  {title}")
            if status == "passed":
                passed += 1
            elif status == "failed":
                failed += 1
            else:
                skipped += 1

    for line in lines:
        print(line)
    print()
    print(f"Smoke summary: {passed} passed, {failed} failed, {skipped} skipped ({total_ms / 1000:.1f}s total)")

    if failed > 0 or (passed == 0 and skipped == 0):
        print("Result: fail")
        return 1
    print("Result: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
