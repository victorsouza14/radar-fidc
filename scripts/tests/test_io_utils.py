"""Testes de ``lib.io_utils`` — orquestração + degradação graciosa.

Cobertura:
- ``_validate``: DataFrame vazio passa; válido passa; inválido vira
  ``SchemaValidationError`` com top-5 ``failure_cases`` na mensagem.
- ``_empty_on_404``: ``ResourceNotFoundError`` vira DataFrame vazio,
  outras exceções fazem re-raise.
- ``read_macro()``: coage ``data_processamento`` para datetime.
- ``read_rating()``: lê ambas as abas via ``azure_io.read_excel_sheets``.
- ``read_focus_indicators()``: 404 → ``None`` (degradação graciosa);
  parquet existente → dict.

Todos os testes mockam ``azure_io`` — nenhum bate em ADLS real.
"""

from __future__ import annotations

import io as _io
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest
from azure.core.exceptions import ResourceNotFoundError


# ─── _validate ───────────────────────────────────────────────────────────
class TestValidate:
    def test_empty_df_passa_sem_erro(self) -> None:
        """DataFrame vazio (arquivo ausente) NÃO precisa passar pelo pandera."""
        from lib.io_utils import _validate
        from lib.schemas import ClientesSchema

        out = _validate(pd.DataFrame(), ClientesSchema, "clientes.csv")
        assert out.empty

    def test_df_valido_retorna_coercido(self) -> None:
        from lib.io_utils import _validate
        from lib.schemas import CreditSchema

        df = pd.DataFrame(
            {
                "id_cnpj": ["abc"],
                "score_credito": [80.0],
                "prob_default": [0.1],
                "risco_credito": ["BAIXO"],
                "total_boletos": [10],
                "n_default": [1],
                "pct_default": [10.0],
                "defaultou": [0],
            }
        )
        out = _validate(df, CreditSchema, "scores_credito.csv")
        assert len(out) == 1
        assert out.iloc[0]["risco_credito"] == "BAIXO"

    def test_df_invalido_vira_schema_validation_error(self) -> None:
        """Schema drift → ``SchemaValidationError`` com top-5 failure_cases."""
        from lib.io_utils import SchemaValidationError, _validate
        from lib.schemas import CreditSchema

        df = pd.DataFrame(
            {
                "id_cnpj": ["abc"],
                "score_credito": [9999.0],  # > 100 → fail
                "prob_default": [2.0],  # > 1 → fail
                "risco_credito": ["BAIXO"],
                "total_boletos": [10],
                "n_default": [1],
                "pct_default": [10.0],
                "defaultou": [0],
            }
        )
        with pytest.raises(SchemaValidationError) as exc_info:
            _validate(df, CreditSchema, "scores_credito.csv")
        msg = str(exc_info.value)
        assert "CreditSchema" in msg
        assert "scores_credito.csv" in msg
        # Mensagem inclui top-5 causas para diagnóstico rápido.
        assert "Top 5" in msg


# ─── _empty_on_404 ───────────────────────────────────────────────────────
class TestEmptyOn404:
    def test_resource_not_found_devolve_df_vazio(self) -> None:
        from lib.io_utils import _empty_on_404

        def boom(*_a: Any, **_kw: Any) -> pd.DataFrame:
            raise ResourceNotFoundError("404 not found")

        out = _empty_on_404(boom, "fake/path.csv")
        assert isinstance(out, pd.DataFrame)
        assert out.empty

    def test_outras_excecoes_propagam(self) -> None:
        """Exceção não-404 NÃO deve ser engolida — caso contrário pipeline mascara bugs."""
        from lib.io_utils import _empty_on_404

        def boom(*_a: Any, **_kw: Any) -> pd.DataFrame:
            raise ValueError("bug genuíno")

        with pytest.raises(ValueError, match="bug genuíno"):
            _empty_on_404(boom, "fake/path.csv")

    def test_sucesso_retorna_resultado_da_funcao(self) -> None:
        from lib.io_utils import _empty_on_404

        def ok(path: str) -> pd.DataFrame:
            return pd.DataFrame({"x": [1], "path": [path]})

        out = _empty_on_404(ok, "fake/path.csv")
        assert len(out) == 1
        assert out.iloc[0]["path"] == "fake/path.csv"


# ─── read_macro ──────────────────────────────────────────────────────────
class TestReadMacro:
    def test_coage_data_processamento_para_datetime(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``read_macro`` deve coagir a coluna ``data_processamento`` para datetime."""
        from lib import azure_io, io_utils

        raw = pd.DataFrame(
            {
                "data_processamento": ["2026-05-13", "2026-05-14"],
                "selic_meta": ["13.75", "13.75"],
                "selic_efetiva": ["13.65", "13.65"],
                "cdi_diario": ["0.05", "0.05"],
                "dolar_venda": ["5.10", "5.12"],
                "ipca_mensal": ["0.4", "0.3"],
                "ipca_12m_acumulado": ["4.20", "4.39"],
                "inadimplencia_pj": ["3.5", "3.6"],
                "inadimplencia_pf": ["5.5", "5.4"],
                "ibc_br": ["142.3", "142.7"],
            }
        )
        monkeypatch.setattr(azure_io, "read_csv", lambda *_a, **_kw: raw)

        out = io_utils.read_macro()
        assert pd.api.types.is_datetime64_any_dtype(out["data_processamento"])
        # As outras colunas viram numéricas.
        assert pd.api.types.is_numeric_dtype(out["selic_meta"])
        assert len(out) == 2

    def test_404_devolve_df_vazio(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from lib import azure_io, io_utils

        def boom(*_a: Any, **_kw: Any) -> pd.DataFrame:
            raise ResourceNotFoundError("404")

        monkeypatch.setattr(azure_io, "read_csv", boom)
        out = io_utils.read_macro()
        assert out.empty


# ─── read_rating ─────────────────────────────────────────────────────────
class TestReadRating:
    def test_le_apenas_aba_geral(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from lib import azure_io, io_utils

        geral_df = pd.DataFrame(
            {
                "CNPJ": ["12345678000190"],
                "FUNDO": ["FIDC A"],
                "TIPO_COTA": ["UNICA"],
                "SEGMENTO": [None],
                "RISCO": ["BAIXO"],
                "SCORE_RISCO": [42.5],
                "PERFIL_SUGERIDO": ["CONSERVADOR"],
                "RETORNO_ANUAL": [12.3],
                "VOLATILIDADE": [3.0],
                "RETORNO_AJ_RISCO": [4.1],
                "TAXA_INADIMPLENCIA": [1.2],
                "SCR_NORMALIZADO": [0.5],
                "CONC_MAIOR_CEDENTE": [0.0],
                "CONC_TOP3": [0.0],
                "MESES_HISTORICO": [12],
            }
        )
        sheets = {"GERAL": geral_df}
        called: dict[str, Any] = {}

        def fake_read_excel_sheets(path: str, sheet_names: list[str]) -> dict[str, pd.DataFrame]:
            called["path"] = path
            called["sheets"] = sheet_names
            return sheets

        monkeypatch.setattr(azure_io, "read_excel_sheets", fake_read_excel_sheets)

        geral = io_utils.read_rating()
        assert called["sheets"] == ["GERAL"]
        assert len(geral) == 1

    def test_404_devolve_dataframe_vazio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Arquivo de rating ausente → DataFrame vazio."""
        from lib import azure_io, io_utils

        def boom(*_a: Any, **_kw: Any) -> dict[str, pd.DataFrame]:
            raise ResourceNotFoundError("404")

        monkeypatch.setattr(azure_io, "read_excel_sheets", boom)
        assert io_utils.read_rating().empty


# ─── read_focus_indicators ───────────────────────────────────────────────
class TestReadFocusIndicators:
    def test_404_retorna_none_degradacao_graciosa(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Focus indisponível → ``None``; pipeline cai para heurística."""
        from lib import azure_io, io_utils

        def boom(*_a: Any, **_kw: Any) -> bytes:
            raise ResourceNotFoundError("404 no parquet")

        monkeypatch.setattr(azure_io, "download_to_bytes", boom)

        out = io_utils.read_focus_indicators()
        assert out is None

    def test_parquet_existente_retorna_dict_com_proj_date(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from lib import azure_io, io_utils

        df = pd.DataFrame(
            [
                {
                    "selic_projetada_12m": 12.5,
                    "ipca_projetado_12m": 3.5,
                    "proj_source": "bcb_focus_top5",
                    "proj_date": "2026-05-01",
                    "is_proj_heuristica": False,
                    "selic_proj_2026": 12.0,
                    "selic_proj_2027": 10.0,
                    "ipca_proj_2026": 3.5,
                    "ipca_proj_2027": 3.2,
                }
            ]
        )
        buf = _io.BytesIO()
        df.to_parquet(buf)

        monkeypatch.setattr(azure_io, "download_to_bytes", lambda *_a, **_kw: buf.getvalue())

        out = io_utils.read_focus_indicators()
        assert out is not None
        assert out["selic_projetada_12m"] == 12.5
        assert out["proj_date"] == "2026-05-01"
        assert out["is_proj_heuristica"] is False

    def test_parquet_vazio_retorna_none(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Parquet existe mas está vazio → ``None`` (não estoura)."""
        from lib import azure_io, io_utils

        df = pd.DataFrame(
            {
                "selic_projetada_12m": pd.Series([], dtype=float),
                "ipca_projetado_12m": pd.Series([], dtype=float),
                "proj_date": pd.Series([], dtype=str),
            }
        )
        buf = _io.BytesIO()
        df.to_parquet(buf)
        monkeypatch.setattr(azure_io, "download_to_bytes", lambda *_a, **_kw: buf.getvalue())

        out = io_utils.read_focus_indicators()
        assert out is None


# ─── read_clientes (smoke do pipeline completo: read + validate) ─────────
class TestReadClientes:
    def test_404_devolve_df_vazio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from lib import azure_io, io_utils

        def boom(*_a: Any, **_kw: Any) -> pd.DataFrame:
            raise ResourceNotFoundError("404")

        monkeypatch.setattr(azure_io, "read_csv", boom)

        out = io_utils.read_clientes()
        assert out.empty


# ─── Sanity: usa MagicMock para garantir que azure_io NÃO é chamado ──────
def test_io_utils_nao_bate_no_adls_quando_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante que toda a suíte de io_utils é hermetica."""
    from lib import azure_io, io_utils

    # Se algum read_* não respeitar o monkeypatch, o MagicMock estoura.
    sentinel = MagicMock(side_effect=AssertionError("Deveria ter sido mockado"))
    monkeypatch.setattr(azure_io, "_service_client", sentinel)
    monkeypatch.setattr(azure_io, "_filesystem_client", sentinel)

    # Substituições explícitas para read_csv / read_excel_sheets / download_to_bytes.
    monkeypatch.setattr(azure_io, "read_csv", lambda *_a, **_kw: pd.DataFrame())
    monkeypatch.setattr(azure_io, "read_excel_sheets", lambda *_a, **_kw: {})
    monkeypatch.setattr(azure_io, "download_to_bytes", lambda *_a, **_kw: b"")

    # Roda os read_* — todos retornam vazios sem bater no ADLS.
    assert io_utils.read_clientes().empty
    assert io_utils.read_credit_scores().empty
    assert io_utils.read_macro().empty
    assert io_utils.read_rating().empty


# ─── read_credit_scores: coerção numérica ────────────────────────────────
class TestReadCreditScores:
    def test_coage_colunas_numericas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``read_credit_scores`` aplica ``pd.to_numeric`` a colunas que vêm como str."""
        from lib import azure_io, io_utils

        raw = pd.DataFrame(
            {
                "id_cnpj": ["a1", "b2"],
                "score_credito": ["80.5", "30.0"],  # str → float
                "prob_default": ["0.1", "0.4"],
                "risco_credito": ["BAIXO", "ALTO"],
                "total_boletos": [10, 20],
                "n_default": [1, 5],
                "pct_default": ["10.0", "25.0"],
                "defaultou": ["0", "1"],
            }
        )
        monkeypatch.setattr(azure_io, "read_csv", lambda *_a, **_kw: raw)

        out = io_utils.read_credit_scores()
        assert pd.api.types.is_numeric_dtype(out["score_credito"])
        assert out.iloc[0]["score_credito"] == 80.5

    def test_404_retorna_vazio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from lib import azure_io, io_utils

        def boom(*_a: Any, **_kw: Any) -> pd.DataFrame:
            raise ResourceNotFoundError("404")

        monkeypatch.setattr(azure_io, "read_csv", boom)
        assert io_utils.read_credit_scores().empty


# ─── read_matches: paridade com read_rating (duas abas) ──────────────────
class TestReadMatches:
    def test_le_ambas_abas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from lib import azure_io, io_utils

        todos = pd.DataFrame(
            {
                "CPF": ["12345678901"],
                "CLIENTE": ["Ana"],
                "PERFIL_CLIENTE": ["MODERADO"],
                "SCORE_CLIENTE": [65.0],
                "FUNDO": ["FIDC A"],
                "TIPO_COTA": ["UNICA"],
                "RISCO_FUNDO": ["BAIXO"],
                "SCORE_RISCO_FUNDO": [42.5],
                "PERFIL_FUNDO": ["CONSERVADOR"],
                "RETORNO_ANUAL": [12.3],
                "VOLATILIDADE": [3.0],
                "TAXA_INAD": [1.2],
                "MESES_HISTORICO": [12],
                "MATCH_SCORE": [85.0],
                "S_PERFIL": [100],
                "S_RISCO": [80.0],
                "S_RETORNO": [60.0],
                "S_HISTORICO": [50.0],
                "MOTIVO": ["ok"],
                "RANK": [1],
            }
        )
        ranking = pd.DataFrame(
            {
                "FUNDO": ["FIDC A"],
                "TIPO_COTA": ["UNICA"],
                "RISCO_FUNDO": ["BAIXO"],
                "RETORNO_ANUAL": [12.3],
                "VEZES_RECOMENDADO": [42],
                "MATCH_MEDIO": [78.0],
            }
        )
        monkeypatch.setattr(
            azure_io,
            "read_excel_sheets",
            lambda *_a, **_kw: {"TODOS_OS_MATCHES": todos, "RANKING_FUNDOS": ranking},
        )

        t, r = io_utils.read_matches()
        assert len(t) == 1
        assert len(r) == 1

    def test_404_devolve_par_vazio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from lib import azure_io, io_utils

        def boom(*_a: Any, **_kw: Any) -> dict[str, pd.DataFrame]:
            raise ResourceNotFoundError("404")

        monkeypatch.setattr(azure_io, "read_excel_sheets", boom)
        todos, ranking = io_utils.read_matches()
        assert todos.empty
        assert ranking.empty


# ─── Exceções não-404 propagam ───────────────────────────────────────────
class TestReadRaisesNon404:
    def test_read_rating_propaga_outras_excecoes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Exceção que NÃO é ``ResourceNotFoundError`` deve subir — bug genuíno."""
        from lib import azure_io, io_utils

        def boom(*_a: Any, **_kw: Any) -> dict[str, pd.DataFrame]:
            raise RuntimeError("network blew up")

        monkeypatch.setattr(azure_io, "read_excel_sheets", boom)
        with pytest.raises(RuntimeError, match="network blew up"):
            io_utils.read_rating()

    def test_read_matches_propaga_outras_excecoes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from lib import azure_io, io_utils

        def boom(*_a: Any, **_kw: Any) -> dict[str, pd.DataFrame]:
            raise RuntimeError("network blew up")

        monkeypatch.setattr(azure_io, "read_excel_sheets", boom)
        with pytest.raises(RuntimeError, match="network blew up"):
            io_utils.read_matches()

    def test_read_focus_indicators_propaga_outras_excecoes(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from lib import azure_io, io_utils

        def boom(*_a: Any, **_kw: Any) -> bytes:
            raise RuntimeError("blob storage down")

        monkeypatch.setattr(azure_io, "download_to_bytes", boom)
        with pytest.raises(RuntimeError, match="blob storage down"):
            io_utils.read_focus_indicators()
