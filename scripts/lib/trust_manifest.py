"""Builder do ``data-quality.json`` — manifesto de confiança consumido pelo frontend.

Estrutura (Seção 4 da spec ``2026-05-14-radar-fidc-polimento-design.md``)::

    {
      "generated_at": ISO-UTC,
      "pipeline_quality_check": {...} | {"status": "not_run"},
      "ci_quality_check": {schema_validation, regression_check, smoke_tests},
      "data_freshness": {<fonte>: {data_ref, age_days, status}},
      "row_counts": {fidcs, matches, clientes, credit_empresas, macro_observations},
      "heuristic_fields": [{field, method, replaced_in_fase_3}],
      "source": {storage_account, container, path}
    }

``pipeline_quality_check`` é defensivo: se
``gold/final/_quality/expectations-result.json`` não existir (Fase 3 ainda
não rodou Great Expectations pela primeira vez), marca
``status: "not_run"`` em vez de quebrar o build.

Heurísticas: lista fixa atual (Fase 2). Esvazia automaticamente conforme
a Fase 3 elimina cada heurística — basta remover a entrada de
``HEURISTIC_FIELDS``.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Thresholds por fonte (em dias) — Seção 4 da spec.
# (warn_days, error_days). Variação >= threshold acende o flag correspondente.
FRESHNESS_THRESHOLDS: dict[str, tuple[int, int]] = {
    "macro": (2, 7),  # BCB/SGS — diário
    "anbima": (2, 7),  # ANBIMA — diário
    "cda": (40, 60),  # CVM CDA — mensal
    "credit_model": (100, 180),  # retrain trimestral
}


# Heurísticas vivas na Fase 2. Remover entrada conforme Fase 3 substitui.
HEURISTIC_FIELDS: list[dict[str, Any]] = [
    {
        "field": "macro.selic_proj",
        "method": "selic - 0.5 (heurística simples; substituir por Focus/BCB)",
        "replaced_in_fase_3": True,
    },
    {
        "field": "macro.ipca_proj",
        "method": "ipca_12m * 0.9 (heurística simples; substituir por Focus/BCB)",
        "replaced_in_fase_3": True,
    },
    {
        "field": "credit.scoring",
        "method": "single-cohort sem features macro (substituir por multi-cohort)",
        "replaced_in_fase_3": True,
    },
    {
        "field": "matches.engine",
        "method": "scoring sem filtro CVM 555 e sem peso por segmento",
        "replaced_in_fase_3": True,
    },
    {
        "field": "rating.algorithm",
        "method": "K-Means com fator_macro de mediana móvel (substituir por quantis)",
        "replaced_in_fase_3": True,
    },
]


def _now_iso_utc() -> str:
    """ISO 8601 UTC com sufixo ``Z`` (compatível com Date.parse do navegador)."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _classify_age(age_days: int, source_key: str) -> str:
    """Classifica freshness: ``fresh`` / ``warn`` / ``error``.

    Sem threshold configurada (fonte desconhecida) cai para o padrão diário
    (2/7). Limites são inclusivos: idade >= threshold acende o flag.
    """
    warn, err = FRESHNESS_THRESHOLDS.get(source_key, (2, 7))
    if age_days >= err:
        return "error"
    if age_days >= warn:
        return "warn"
    return "fresh"


def _freshness_from_df(
    df: pd.DataFrame,
    source_key: str,
    date_col: str = "data_processamento",
) -> dict[str, Any]:
    """Freshness baseado na última ``data_processamento`` do DataFrame."""
    if df is None or df.empty or date_col not in df.columns:
        return {"data_ref": None, "age_days": None, "status": "error", "reason": "no_data"}
    last = pd.to_datetime(df[date_col], errors="coerce").max()
    if pd.isna(last):
        return {"data_ref": None, "age_days": None, "status": "error", "reason": "invalid_date"}
    today = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    last_norm = last.normalize() if hasattr(last, "normalize") else last
    age = max(0, int((today - last_norm).days))
    return {
        "data_ref": last_norm.date().isoformat(),
        "age_days": age,
        "status": _classify_age(age, source_key),
    }


def _normalize_pipeline_result(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Lida com o blob ``expectations-result.json`` ausente ou presente.

    Quando o blob não existe (Fase 3 ainda não rodou GE), devolve um stub
    com ``status: "not_run"``. Quando existe, normaliza chaves para o
    contrato do frontend.
    """
    if raw is None:
        return {
            "status": "not_run",
            "source": "great_expectations",
            "overall_success": None,
            "suites_passed": None,
            "suites_failed": None,
        }
    return {
        "status": "ok" if raw.get("overall_success") else "fail",
        "source": "great_expectations",
        "ts": raw.get("ts"),
        "overall_success": bool(raw.get("overall_success", False)),
        "suites_passed": int(raw.get("suites_passed", 0)),
        "suites_failed": int(raw.get("suites_failed", 0)),
    }


def build_manifest(
    *,
    macro_df: pd.DataFrame,
    geral_df: pd.DataFrame,
    matches_df: pd.DataFrame,
    clientes_df: pd.DataFrame,
    credit_df: pd.DataFrame,
    pipeline_quality_result: dict[str, Any] | None,
    schema_validation_ok: bool,
    regression_check_result: str,
    smoke_tests_result: str,
) -> dict[str, Any]:
    """Monta o dict do ``data-quality.json``.

    Args:
        macro_df: DataFrame macro (usado para ``data_freshness.macro``).
        geral_df: DataFrame ``rating.GERAL`` (usado para ``row_counts.fidcs``).
        matches_df: DataFrame ``matches.TODOS_OS_MATCHES``.
        clientes_df: DataFrame ``clientes``.
        credit_df: DataFrame ``scores_credito``.
        pipeline_quality_result: Conteúdo de ``expectations-result.json`` ou
            ``None`` se o blob não existe (status ``not_run``).
        schema_validation_ok: True se todos os schemas pandera passaram.
        regression_check_result: ``pass`` / ``fail`` / ``bypassed`` / ``not_run``.
        smoke_tests_result: ``pass`` / ``fail`` / ``not_run``.
    """
    return {
        "generated_at": _now_iso_utc(),
        "pipeline_quality_check": _normalize_pipeline_result(pipeline_quality_result),
        "ci_quality_check": {
            "schema_validation": "pass" if schema_validation_ok else "fail",
            "regression_check": regression_check_result,
            "smoke_tests": smoke_tests_result,
        },
        "data_freshness": {
            "macro": _freshness_from_df(macro_df, "macro"),
        },
        "row_counts": {
            "fidcs": len(geral_df),
            "matches": len(matches_df),
            "clientes": len(clientes_df),
            "credit_empresas": len(credit_df),
            "macro_observations": len(macro_df),
        },
        "heuristic_fields": [dict(h) for h in HEURISTIC_FIELDS],
        "source": {
            "storage_account": os.environ.get("AZURE_STORAGE_ACCOUNT", "dfdatalakesprint"),
            "container": os.environ.get("AZURE_FILESYSTEM", "gold"),
            "path": f"{os.environ.get('AZURE_GOLD_PREFIX', 'final')}/",
        },
    }


def load_pipeline_quality_result_safely(local_path: str | None) -> dict[str, Any] | None:
    """Lê ``expectations-result.json`` se baixado; ``None`` se ausente ou inválido.

    Defensivo: blob criado pela Fase 3 do Databricks. Enquanto não existe,
    devolvemos ``None`` e o manifesto marca ``pipeline_quality_check.status:
    "not_run"``. Também devolve ``None`` se o conteúdo é JSON inválido ou
    se a raiz não é um dict — não queremos pré-validar o schema completo
    aqui, mas garantimos que o consumidor recebe um dict ou ``None``.
    """
    if not local_path:
        return None
    p = Path(local_path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data
