"""Testes do ``data-quality.json`` builder."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def macro_df_today() -> pd.DataFrame:
    today = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    return pd.DataFrame(
        {
            "data_processamento": [today],
            "selic_meta": [13.75],
        }
    )


@pytest.fixture
def macro_df_stale_warn() -> pd.DataFrame:
    """40 dias atrás → entre 35d (warn) e 75d (error) para a fonte 'macro'."""
    old = pd.Timestamp.now("UTC").tz_localize(None).normalize() - pd.Timedelta(days=40)
    return pd.DataFrame({"data_processamento": [old], "selic_meta": [13.75]})


@pytest.fixture
def macro_df_stale_error() -> pd.DataFrame:
    """80 dias atrás → acima do threshold 'error' de 75d para a fonte 'macro'."""
    old = pd.Timestamp.now("UTC").tz_localize(None).normalize() - pd.Timedelta(days=80)
    return pd.DataFrame({"data_processamento": [old], "selic_meta": [13.75]})


@pytest.fixture
def empty_df() -> pd.DataFrame:
    return pd.DataFrame()


class TestBuildManifest:
    def test_minimal_fresh_run(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest

        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=pd.DataFrame({"CNPJ": ["a"]}),
            matches_df=empty_df,
            clientes_df=empty_df,
            credit_df=empty_df,
            pipeline_quality_result=None,
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        assert "generated_at" in manifest
        assert manifest["generated_at"].endswith("Z")
        assert manifest["pipeline_quality_check"]["status"] == "not_run"
        assert manifest["ci_quality_check"]["schema_validation"] == "pass"
        assert manifest["ci_quality_check"]["regression_check"] == "pass"
        assert manifest["ci_quality_check"]["smoke_tests"] == "pass"
        assert manifest["data_freshness"]["macro"]["status"] == "fresh"
        assert manifest["data_freshness"]["macro"]["age_days"] == 0
        assert manifest["row_counts"]["fidcs"] == 1
        assert manifest["row_counts"]["matches"] == 0
        assert manifest["row_counts"]["clientes"] == 0
        assert manifest["row_counts"]["credit_empresas"] == 0
        assert manifest["row_counts"]["macro_observations"] == 1
        assert len(manifest["heuristic_fields"]) >= 1
        assert manifest["source"]["storage_account"] == "dfdatalakesprint"
        assert manifest["source"]["container"] == "gold"
        assert manifest["source"]["path"] == "final/"

    def test_stale_macro_warn_status(self, macro_df_stale_warn: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest

        manifest = build_manifest(
            macro_df=macro_df_stale_warn,
            geral_df=empty_df,
            matches_df=empty_df,
            clientes_df=empty_df,
            credit_df=empty_df,
            pipeline_quality_result=None,
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        assert manifest["data_freshness"]["macro"]["status"] == "warn"

    def test_stale_macro_error_status(self, macro_df_stale_error: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest

        manifest = build_manifest(
            macro_df=macro_df_stale_error,
            geral_df=empty_df,
            matches_df=empty_df,
            clientes_df=empty_df,
            credit_df=empty_df,
            pipeline_quality_result=None,
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        assert manifest["data_freshness"]["macro"]["status"] == "error"

    def test_pipeline_result_passed_through(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest

        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=empty_df,
            matches_df=empty_df,
            clientes_df=empty_df,
            credit_df=empty_df,
            pipeline_quality_result={
                "ts": "2026-05-14T07:00:00Z",
                "overall_success": True,
                "suites_passed": 5,
                "suites_failed": 0,
            },
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        assert manifest["pipeline_quality_check"]["overall_success"] is True
        assert manifest["pipeline_quality_check"]["suites_passed"] == 5
        assert manifest["pipeline_quality_check"]["suites_failed"] == 0
        assert manifest["pipeline_quality_check"]["status"] == "ok"
        assert manifest["pipeline_quality_check"]["ts"] == "2026-05-14T07:00:00Z"

    def test_pipeline_result_failure(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest

        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=empty_df,
            matches_df=empty_df,
            clientes_df=empty_df,
            credit_df=empty_df,
            pipeline_quality_result={
                "ts": "2026-05-14T07:00:00Z",
                "overall_success": False,
                "suites_passed": 3,
                "suites_failed": 2,
            },
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        assert manifest["pipeline_quality_check"]["status"] == "fail"
        assert manifest["pipeline_quality_check"]["overall_success"] is False

    def test_heuristic_fields_present(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest

        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=empty_df,
            matches_df=empty_df,
            clientes_df=empty_df,
            credit_df=empty_df,
            pipeline_quality_result=None,
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        keys = {h["field"] for h in manifest["heuristic_fields"]}
        # Pós-Fase 3 (2026-05-14): apenas credit.scoring permanece como
        # heurística ativa (bloqueador externo: histórico mensal de clientes
        # ainda não disponível no Gold). Ver REPLACED_HEURISTICS para as
        # 4 substituídas.
        assert "credit.scoring" in keys
        assert "macro.selic_proj" not in keys
        assert "macro.ipca_proj" not in keys
        assert "matches.engine" not in keys
        assert "rating.algorithm" not in keys
        for h in manifest["heuristic_fields"]:
            assert h["replaced_in_fase_3"] is True
            assert isinstance(h["method"], str) and h["method"]

    def test_replaced_heuristics_present(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        """Fase 3 — 4 heurísticas movidas para `replaced_heuristics` com data e novo método/fonte."""
        from lib.trust_manifest import build_manifest

        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=empty_df,
            matches_df=empty_df,
            clientes_df=empty_df,
            credit_df=empty_df,
            pipeline_quality_result=None,
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        replaced = manifest["replaced_heuristics"]
        assert isinstance(replaced, list)
        assert len(replaced) == 4
        keys = {h["field"] for h in replaced}
        assert keys == {
            "rating.algorithm",
            "macro.selic_proj",
            "macro.ipca_proj",
            "matches.engine",
        }
        for h in replaced:
            assert h["replaced_at"] == "2026-05-14"
            # Cada entrada documenta OU new_method OU new_source.
            assert "new_method" in h or "new_source" in h
            assert isinstance(h.get("notes", ""), str)

    def test_schema_validation_failed_propagates(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest

        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=empty_df,
            matches_df=empty_df,
            clientes_df=empty_df,
            credit_df=empty_df,
            pipeline_quality_result=None,
            schema_validation_ok=False,
            regression_check_result="fail",
            smoke_tests_result="pass",
        )
        assert manifest["ci_quality_check"]["schema_validation"] == "fail"
        assert manifest["ci_quality_check"]["regression_check"] == "fail"

    def test_manifest_is_json_serializable(self, macro_df_today: pd.DataFrame, empty_df: pd.DataFrame) -> None:
        from lib.trust_manifest import build_manifest

        manifest = build_manifest(
            macro_df=macro_df_today,
            geral_df=empty_df,
            matches_df=empty_df,
            clientes_df=empty_df,
            credit_df=empty_df,
            pipeline_quality_result=None,
            schema_validation_ok=True,
            regression_check_result="pass",
            smoke_tests_result="pass",
        )
        # allow_nan=False captura NaN/Infinity (inválidos em JSON estrito).
        as_str = json.dumps(manifest, ensure_ascii=False, allow_nan=False)
        assert len(as_str) > 0


class TestLoadPipelineQualityResultSafely:
    def test_returns_none_when_path_is_none(self) -> None:
        from lib.trust_manifest import load_pipeline_quality_result_safely

        assert load_pipeline_quality_result_safely(None) is None

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        from lib.trust_manifest import load_pipeline_quality_result_safely

        missing = tmp_path / "nope.json"
        assert load_pipeline_quality_result_safely(str(missing)) is None

    def test_returns_none_when_invalid_json(self, tmp_path: Path) -> None:
        from lib.trust_manifest import load_pipeline_quality_result_safely

        broken = tmp_path / "bad.json"
        broken.write_text("not json {{{", encoding="utf-8")
        assert load_pipeline_quality_result_safely(str(broken)) is None

    def test_returns_none_when_not_dict(self, tmp_path: Path) -> None:
        from lib.trust_manifest import load_pipeline_quality_result_safely

        arr = tmp_path / "arr.json"
        arr.write_text("[1,2,3]", encoding="utf-8")
        assert load_pipeline_quality_result_safely(str(arr)) is None

    def test_returns_dict_when_valid(self, tmp_path: Path) -> None:
        from lib.trust_manifest import load_pipeline_quality_result_safely

        good = tmp_path / "ok.json"
        good.write_text(
            json.dumps({"overall_success": True, "suites_passed": 3, "suites_failed": 0}),
            encoding="utf-8",
        )
        loaded = load_pipeline_quality_result_safely(str(good))
        assert loaded == {"overall_success": True, "suites_passed": 3, "suites_failed": 0}
