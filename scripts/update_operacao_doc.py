#!/usr/bin/env python3
"""Atualiza `docs/operacao.md` e `docs/historico-runs.csv` no final de runs do `data-refresh.yml`.

Substitui apenas o conteúdo entre os marcadores delimitadores em `docs/operacao.md`:

    <!-- last-update:start --> ... <!-- last-update:end -->
    <!-- runs:start --> ... <!-- runs:end -->

E faz append idempotente de uma linha em `docs/historico-runs.csv` (criado com cabeçalho se ausente).

Idempotência: rodar duas vezes com o mesmo `--ts` substitui a linha CSV existente em vez de duplicar,
e re-substitui os blocos de marker no Markdown (sem efeito colateral).

Uso (no workflow):
    python scripts/update_operacao_doc.py \\
        --ts "2026-05-14T09:05:30Z" \\
        --duration 142 \\
        --bytes 2456320 \\
        --status success \\
        --pipeline-id 9876543210

Argumentos opcionais úteis para preencher o CSV com row_counts e heuristic_count:
    --quality data-quality.json   (lê row_counts.* e len(heuristic_fields))

Sem dependências externas (apenas stdlib).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERACAO_PATH = REPO_ROOT / "docs" / "operacao.md"
HISTORICO_PATH = REPO_ROOT / "docs" / "historico-runs.csv"

CSV_HEADER = [
    "ts",
    "status",
    "duration_s",
    "bytes_read",
    "row_count_fidcs",
    "row_count_matches",
    "heuristic_count",
    "pipeline_id",
]

MAX_RUNS_IN_TABLE = 14


def _replace_block(content: str, marker: str, replacement: str) -> str:
    """Substitui o conteúdo entre `<!-- {marker}:start -->` e `<!-- {marker}:end -->`.

    Preserva os próprios marcadores. Se o marker não existir, retorna o conteúdo inalterado.
    """
    pattern = re.compile(
        rf"(<!--\s*{re.escape(marker)}:start\s*-->)(.*?)(<!--\s*{re.escape(marker)}:end\s*-->)",
        re.DOTALL,
    )
    return pattern.sub(rf"\1\n{replacement}\n\3", content)


def _format_bytes(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.1f} KB"
    return f"{n} B"


def _format_duration(seconds: int) -> str:
    if seconds >= 60:
        mins, secs = divmod(seconds, 60)
        return f"{mins}m{secs:02d}s"
    return f"{seconds}s"


def _read_quality(path: Path) -> dict[str, Any]:
    """Lê data-quality.json se existir; retorna dict vazio caso contrário."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _ensure_csv_with_header() -> None:
    if HISTORICO_PATH.exists():
        return
    HISTORICO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORICO_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)


def _upsert_csv_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Adiciona/substitui linha por `ts`. Retorna a lista completa atual (ordenada por ts desc)."""
    _ensure_csv_with_header()

    rows: list[dict[str, Any]] = []
    with HISTORICO_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for existing in reader:
            if existing.get("ts") != row["ts"]:
                rows.append(existing)

    rows.append(row)
    # Mais recente primeiro.
    rows.sort(key=lambda r: r.get("ts", ""), reverse=True)

    with HISTORICO_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in CSV_HEADER})

    return rows


def _render_last_update(row: dict[str, Any]) -> str:
    bytes_str = _format_bytes(int(row["bytes_read"])) if row.get("bytes_read") else "—"
    duration_str = _format_duration(int(row["duration_s"])) if row.get("duration_s") else "—"
    pipeline_id = row.get("pipeline_id") or "—"
    return (
        f"- **Timestamp:** {row['ts']}\n"
        f"- **Status:** {row.get('status', '—')}\n"
        f"- **Duração:** {duration_str}\n"
        f"- **Bytes lidos:** {bytes_str}\n"
        f"- **Pipeline ID:** {pipeline_id}"
    )


def _render_runs_table(rows: list[dict[str, Any]]) -> str:
    """Renderiza as últimas linhas em formato Markdown table."""
    if not rows:
        return "| — | — | — | — | — |"
    out_lines = []
    for r in rows[:MAX_RUNS_IN_TABLE]:
        bytes_str = _format_bytes(int(r["bytes_read"])) if r.get("bytes_read") else "—"
        duration_str = _format_duration(int(r["duration_s"])) if r.get("duration_s") else "—"
        out_lines.append(
            f"| {r.get('ts', '—')} | {r.get('status', '—')} | {duration_str} | "
            f"{bytes_str} | {r.get('pipeline_id', '—') or '—'} |"
        )
    return "\n".join(out_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ts", required=True, help="Timestamp ISO-8601 UTC do run.")
    parser.add_argument("--duration", required=True, type=int, help="Duração do run em segundos.")
    parser.add_argument("--bytes", required=True, type=int, help="Bytes lidos do ADLS no run.")
    parser.add_argument(
        "--status",
        required=True,
        choices=("success", "failure", "bypassed"),
        help="Resultado final do run.",
    )
    parser.add_argument("--pipeline-id", default="", help="ID do run no GitHub Actions (opcional).")
    parser.add_argument(
        "--quality",
        type=Path,
        default=None,
        help="Caminho para data-quality.json (preenche row_counts e heuristic_count).",
    )
    args = parser.parse_args()

    if not OPERACAO_PATH.exists():
        print(
            f"::warning::operacao.md não encontrado em {OPERACAO_PATH}; nada a fazer.",
            file=sys.stderr,
        )
        return 0

    quality = _read_quality(args.quality) if args.quality else {}
    row_counts = quality.get("row_counts", {}) if isinstance(quality, dict) else {}
    heuristic_fields = quality.get("heuristic_fields", []) if isinstance(quality, dict) else []

    row = {
        "ts": args.ts,
        "status": args.status,
        "duration_s": args.duration,
        "bytes_read": args.bytes,
        "row_count_fidcs": row_counts.get("fidcs", ""),
        "row_count_matches": row_counts.get("matches", ""),
        "heuristic_count": len(heuristic_fields) if isinstance(heuristic_fields, list) else "",
        "pipeline_id": args.pipeline_id,
    }

    all_rows = _upsert_csv_row(row)

    content = OPERACAO_PATH.read_text(encoding="utf-8")
    new_content = _replace_block(content, "last-update", _render_last_update(row))
    new_content = _replace_block(new_content, "runs", _render_runs_table(all_rows))

    if new_content != content:
        OPERACAO_PATH.write_text(new_content, encoding="utf-8")
        print(f"Atualizado: {OPERACAO_PATH.relative_to(REPO_ROOT)}", file=sys.stderr)
    else:
        print(f"Sem mudanças em {OPERACAO_PATH.relative_to(REPO_ROOT)}.", file=sys.stderr)

    print(
        f"CSV: {HISTORICO_PATH.relative_to(REPO_ROOT)} ({len(all_rows)} linhas).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
