#!/usr/bin/env python3
"""Gera ``data.json`` e ``data-quality.json`` consumidos pelo dashboard Radar FIDC.

``data.json`` — payload do dashboard (Bronze→Silver→Gold materializado).
``data-quality.json`` — manifesto de auditoria do pipeline. Lado-a-lado, mesmo diretório.

Uso::

    python scripts/generate_dashboard_data.py
    python scripts/generate_dashboard_data.py --output data.json --quality data-quality.json
    python scripts/generate_dashboard_data.py --ge-result /tmp/expectations-result.json
    python scripts/generate_dashboard_data.py --regression-result pass --smoke-result pass

Pré-requisitos:
    - ``AZURE_CONNECTION_STRING`` no ``.env`` (local) ou no GitHub Secret (CI)
    - pandera valida cada DataFrame; se falhar, NÃO escreve ``data.json``
      (fail fast — preferimos zero artefato a um artefato corrompido).

O ``--ge-result`` é defensivo: se não passar ou se o arquivo não existir,
o manifesto marca ``pipeline_quality_check.status: "not_run"``. O blob
``gold/final/_quality/expectations-result.json`` é emitido pelo notebook
Great Expectations no Databricks; até existir, o status fica em
``not_run`` sem quebrar o build.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Permite rodar tanto como ``python scripts/...`` quanto via import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Carrega .env automaticamente (no-op se não existir — no CI as vars vêm dos secrets).
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from lib import io_utils, payload  # noqa: E402
from lib.logger import get_logger  # noqa: E402
from lib.trust_manifest import build_manifest, load_pipeline_quality_result_safely  # noqa: E402

log = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "data.json"
DEFAULT_QUALITY = REPO_ROOT / "data-quality.json"


def now_iso_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_all() -> tuple[dict, dict]:
    """Devolve ``(payload_dict, raw_dataframes_for_manifest)``.

    Os DataFrames brutos são propagados ao caller para que o trust manifest
    possa derivar ``data_freshness`` e ``row_counts`` sem reler do ADLS.
    """
    log.info("pipeline_start", source="adls", filesystem="gold", prefix="final")

    log.info("reading", source="rating_fidc.xlsx")
    geral = io_utils.read_rating()
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

    log.info("reading", source="indicadores_macro/indicadores.parquet (Focus)")
    focus_indicators = io_utils.read_focus_indicators()

    payload_dict: dict = {
        "generated_at": now_iso_utc(),
        "config": {
            "min_meses_historico": payload.MIN_MESES_HISTORICO,
        },
        "macro": payload.build_macro(df_macro, focus_indicators),
        "fidcs": payload.build_fidcs(geral),
        "clientes": payload.build_clientes(df_clientes),
        "matches": payload.build_matches(todos, ranking),
        "credit": payload.build_credit(df_credit),
    }

    raw_dfs = {
        "geral": geral,
        "matches": todos,
        "clientes": df_clientes,
        "credit": df_credit,
        "macro": df_macro,
        "focus_indicators": focus_indicators,
    }

    return payload_dict, raw_dfs


def write_json(out: Path, data: dict) -> None:
    # allow_nan=False: falha o build em vez de emitir ``NaN`` literal (inválido em JSON).
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
        fidcs_detalhe=len(data["fidcs"]["detalhe"]),
        clientes=data["clientes"]["total"],
        matches=data["matches"]["total"],
        credit=len(data["credit"]["empresas"]),
        dist_por_risco=data["fidcs"]["stats"]["distribuicao"]["por_risco"],
        dist_por_perfil=data["fidcs"]["stats"]["distribuicao"]["por_perfil"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None, help="Sobrepõe data.json de saída")
    parser.add_argument("--quality", default=None, help="Sobrepõe data-quality.json de saída")
    parser.add_argument(
        "--ge-result",
        default=None,
        help="Path local para expectations-result.json (opcional; defensivo se ausente)",
    )
    parser.add_argument(
        "--regression-result",
        default="not_run",
        choices=["pass", "fail", "bypassed", "not_run"],
        help="Resultado do regression_check (vem do workflow)",
    )
    parser.add_argument(
        "--smoke-result",
        default="not_run",
        choices=["pass", "fail", "not_run"],
        help="Resultado dos smoke tests Playwright (vem do workflow)",
    )
    args = parser.parse_args()

    out = Path(args.output) if args.output else DEFAULT_OUTPUT
    quality_out = Path(args.quality) if args.quality else DEFAULT_QUALITY

    # ``build_all()`` já valida via pandera; se algum schema falhar ele LEVANTA
    # ``SchemaValidationError`` e a função para aqui (não escreve nada).
    data, raw_dfs = build_all()

    write_json(out, data)
    emit_summary(out, data)

    # Trust manifest (sempre depois do data.json escrito com sucesso).
    pipeline_result = load_pipeline_quality_result_safely(args.ge_result)
    manifest = build_manifest(
        macro_df=raw_dfs["macro"],
        geral_df=raw_dfs["geral"],
        matches_df=raw_dfs["matches"],
        clientes_df=raw_dfs["clientes"],
        credit_df=raw_dfs["credit"],
        pipeline_quality_result=pipeline_result,
        schema_validation_ok=True,  # se chegou aqui, todos os schemas passaram
        regression_check_result=args.regression_result,
        smoke_tests_result=args.smoke_result,
        focus_indicators=raw_dfs.get("focus_indicators"),
    )
    write_json(quality_out, manifest)
    log.info(
        "manifest_written",
        path=str(quality_out),
        size_kb=quality_out.stat().st_size // 1024,
        pipeline_status=manifest["pipeline_quality_check"]["status"],
        schema_validation=manifest["ci_quality_check"]["schema_validation"],
        macro_freshness=manifest["data_freshness"]["macro"]["status"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
