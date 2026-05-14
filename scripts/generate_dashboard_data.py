#!/usr/bin/env python3
"""Gera o `data.json` consumido pelo dashboard Radar FIDC.

Lê os outputs do Gold no ADLS (`dfdatalakesprint/gold/final/`),
delega a montagem do payload aos módulos em `scripts/lib/`, e
escreve `data.json` na raiz do repositório.

Uso:
    python scripts/generate_dashboard_data.py
    python scripts/generate_dashboard_data.py --output /tmp/data.json

Pré-requisitos:
    - AZURE_CONNECTION_STRING em .env (local) ou GitHub Secret (CI)
    - Arquivos esperados em gold/final/:
        rating_fidc.xlsx, matches.xlsx, clientes.csv,
        scores_credito.csv, macroeconomicos/consolidade.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permite rodar tanto como `python scripts/...` quanto via import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Carrega .env automaticamente (no-op se não existir — no CI as vars vêm dos secrets).
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from lib import io_utils, payload  # noqa: E402
from lib.logger import get_logger  # noqa: E402

log = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "data.json"


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build() -> dict:
    log.info("pipeline_start", source="adls", filesystem="gold", prefix="final")

    log.info("reading", source="rating_fidc.xlsx")
    geral, resumo = io_utils.read_rating()
    if geral.empty:
        raise SystemExit("ERRO: gold/final/rating_fidc.xlsx ausente ou vazio. Pipeline Databricks deve gerar antes.")

    log.info("reading", source="matches.xlsx")
    todos, ranking = io_utils.read_matches()

    log.info("reading", source="clientes.csv")
    df_clientes = io_utils.read_clientes()

    log.info("reading", source="scores_credito.csv")
    df_credit = io_utils.read_credit_scores()

    log.info("reading", source="macroeconomicos/consolidade.csv")
    df_macro = io_utils.read_macro()

    return {
        "generated_at": now_iso_utc(),
        "config": {
            "min_meses_historico": payload.MIN_MESES_HISTORICO,
            "retorno_outlier_pct": payload.RETORNO_OUTLIER_PCT,
        },
        "macro":    payload.build_macro(df_macro),
        "fidcs":    payload.build_fidcs(geral, resumo),
        "clientes": payload.build_clientes(df_clientes),
        "matches":  payload.build_matches(todos, ranking),
        "credit":   payload.build_credit(df_credit),
    }


def write_json(out: Path, data: dict) -> None:
    # allow_nan=False: falha o build em vez de emitir `NaN` literal (inválido em JSON).
    out.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


def emit_summary(out: Path, data: dict) -> None:
    size_kb = out.stat().st_size // 1024
    log.info(
        "pipeline_end",
        output=str(out),
        size_kb=size_kb,
        fidcs_resumo=len(data["fidcs"]["resumo"]),
        fidcs_detalhe=len(data["fidcs"]["detalhe"]),
        scatter=len(data["fidcs"]["scatter"]),
        clientes=data["clientes"]["total"],
        matches=data["matches"]["total"],
        credit=len(data["credit"]["empresas"]),
        dist_por_risco=data["fidcs"]["stats"]["distribuicao"]["por_risco"],
        dist_por_perfil=data["fidcs"]["stats"]["distribuicao"]["por_perfil"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None, help="Sobrepõe data.json de saída")
    args = parser.parse_args()

    out = Path(args.output) if args.output else DEFAULT_OUTPUT

    data = build()
    write_json(out, data)
    emit_summary(out, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
