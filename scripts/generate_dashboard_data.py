#!/usr/bin/env python3
"""Gera o `data.json` consumido pelo dashboard Radar FIDC.

Orquestra leitura dos outputs do pipeline (data_real/) e produção do payload
delegando trabalho aos módulos em scripts/lib/.

Uso:
    python scripts/generate_dashboard_data.py
    python scripts/generate_dashboard_data.py --output /tmp/data.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permite rodar tanto como `python scripts/...` quanto via import
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import io_utils, payload  # noqa: E402
from lib.paths import Paths  # noqa: E402


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build(paths: Paths) -> dict:
    print(f"Lendo dados de: {paths.data_real}")

    if not paths.rating.exists():
        raise SystemExit(f"ERRO: {paths.rating} não encontrado. Rode scripts/rating.py primeiro.")

    print("  → rating_fidc.xlsx");          geral, resumo  = io_utils.read_rating(paths.rating)
    print("  → matches.xlsx");              todos, ranking = io_utils.read_matches(paths.matches)
    print("  → clientes.csv");              df_clientes    = io_utils.read_clientes(paths.clientes)
    print("  → scores_credito.csv");        df_credit      = io_utils.read_credit_scores(paths.credit)
    print("  → macroeconomicos/...csv");    df_macro       = io_utils.read_macro(paths.macro)

    return {
        "generated_at": now_iso_utc(),
        "config": {
            # Constantes compartilhadas com o front (única fonte de verdade).
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


def print_summary(out: Path, data: dict) -> None:
    size_kb = out.stat().st_size // 1024
    print(f"\nOK: {out} ({size_kb} KB)")
    print(f"  FIDCs (resumo)   : {len(data['fidcs']['resumo'])}")
    print(f"  FIDCs (detalhe)  : {len(data['fidcs']['detalhe'])}")
    print(f"  Scatter          : {len(data['fidcs']['scatter'])}")
    print(f"  Clientes         : {data['clientes']['total']}")
    print(f"  Matches          : {data['matches']['total']}")
    print(f"  Credit empresas  : {len(data['credit']['empresas'])}")
    print(f"  Distribuição risco FIDCs: {data['fidcs']['stats']['distribuicao']['por_risco']}")
    print(f"  Distribuição perfis FIDCs: {data['fidcs']['stats']['distribuicao']['por_perfil']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=None, help="Sobrepõe RADAR_DATA_DIR")
    parser.add_argument("--output",   default=None, help="Sobrepõe data.json de saída")
    args = parser.parse_args()

    paths = Paths.from_data_dir(args.data_dir) if args.data_dir else Paths.default()
    out = Path(args.output) if args.output else paths.dashboard_json

    data = build(paths)
    write_json(out, data)
    print_summary(out, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
