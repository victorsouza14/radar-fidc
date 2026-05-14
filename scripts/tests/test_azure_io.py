"""Testes de ``lib.azure_io`` — usa mocks para nunca bater no ADLS real.

Cobertura:
- ``AzureMissingConnectionString`` quando o env var não está setado
- ``blob_etag`` retorna a string vinda das propriedades do blob
- Cache hit: bytes locais + etag local == etag remoto → não baixa
- Cache miss: etag remoto difere → re-download + atualização do etag
- ``read_csv`` parseia o stream corretamente
- ``ResourceNotFoundError`` 404 propaga (tratado por ``io_utils._empty_on_404``)
- ``ClientAuthenticationError`` (auth 403) vira ``AzureAuthError``
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
from azure.core.exceptions import ClientAuthenticationError, ResourceNotFoundError


@pytest.fixture
def fake_props(fake_etag: str) -> MagicMock:
    m = MagicMock()
    m.etag = fake_etag
    return m


def _reset_azure_state() -> None:
    """Limpa caches lru e estado de módulo entre testes."""
    from lib import azure_io

    azure_io._service_client.cache_clear()
    azure_io._filesystem_client.cache_clear()


class TestAzureIO:
    def test_missing_connection_string_raises(self) -> None:
        from lib.azure_io import AzureMissingConnectionString, _service_client

        _reset_azure_state()
        with pytest.raises(AzureMissingConnectionString):
            _service_client()

    def test_blob_etag_returns_string(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_props: MagicMock,
    ) -> None:
        from lib import azure_io

        _reset_azure_state()
        fake_file_client = MagicMock()
        fake_file_client.get_file_properties.return_value = fake_props
        fake_fs = MagicMock()
        fake_fs.get_file_client.return_value = fake_file_client
        monkeypatch.setattr(azure_io, "_filesystem_client", lambda: fake_fs)

        etag = azure_io.blob_etag("final/rating_fidc.xlsx")
        assert etag == fake_props.etag
        fake_fs.get_file_client.assert_called_once_with("final/rating_fidc.xlsx")

    def test_blob_etag_auth_failure_raises_azure_auth_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from lib import azure_io

        _reset_azure_state()
        fake_file_client = MagicMock()
        fake_file_client.get_file_properties.side_effect = ClientAuthenticationError("403 forbidden")
        fake_fs = MagicMock()
        fake_fs.get_file_client.return_value = fake_file_client
        monkeypatch.setattr(azure_io, "_filesystem_client", lambda: fake_fs)

        with pytest.raises(azure_io.AzureAuthError):
            azure_io.blob_etag("final/secret.csv")

    def test_download_uses_cache_when_etag_matches(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_etag: str,
    ) -> None:
        from lib import azure_io

        _reset_azure_state()
        monkeypatch.setattr(azure_io, "_CACHE_ROOT", tmp_path)
        remote_path = "final/sample.csv"
        body = b"a,b\n1,2\n"

        # Planta bytes + etag local válidos.
        (tmp_path / "final").mkdir(parents=True)
        (tmp_path / "final" / "sample.csv").write_bytes(body)
        (tmp_path / "final" / "sample.csv.etag").write_text(fake_etag, encoding="utf-8")

        # Etag remoto == etag local → cache hit; filesystem nem é tocado pra download.
        monkeypatch.setattr(azure_io, "blob_etag", lambda _path: fake_etag)
        # Garante que filesystem_client NÃO é chamado para download.
        fake_fs = MagicMock()
        fake_fs.get_file_client.side_effect = AssertionError("Não deveria baixar em cache hit")
        monkeypatch.setattr(azure_io, "_filesystem_client", lambda: fake_fs)

        data = azure_io.download_to_bytes(remote_path)
        assert data == body

    def test_download_re_downloads_on_etag_mismatch(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_etag: str,
    ) -> None:
        from lib import azure_io

        _reset_azure_state()
        monkeypatch.setattr(azure_io, "_CACHE_ROOT", tmp_path)
        remote_path = "final/sample.csv"
        old_body = b"old\n"
        new_body = b"new\n"
        old_etag = '"0x8DB000000000001"'

        (tmp_path / "final").mkdir(parents=True)
        (tmp_path / "final" / "sample.csv").write_bytes(old_body)
        (tmp_path / "final" / "sample.csv.etag").write_text(old_etag, encoding="utf-8")

        # Etag remoto difere do local → re-download.
        monkeypatch.setattr(azure_io, "blob_etag", lambda _path: fake_etag)

        downloader = MagicMock()
        downloader.readall.return_value = new_body
        fake_file_client = MagicMock()
        fake_file_client.download_file.return_value = downloader
        fake_fs = MagicMock()
        fake_fs.get_file_client.return_value = fake_file_client
        monkeypatch.setattr(azure_io, "_filesystem_client", lambda: fake_fs)

        data = azure_io.download_to_bytes(remote_path)
        assert data == new_body
        # Local foi sobrescrito e etag atualizado.
        assert (tmp_path / "final" / "sample.csv").read_bytes() == new_body
        assert (tmp_path / "final" / "sample.csv.etag").read_text(encoding="utf-8") == fake_etag

    def test_download_404_propagates_resource_not_found(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from lib import azure_io

        _reset_azure_state()
        monkeypatch.setattr(azure_io, "_CACHE_ROOT", tmp_path)
        fake_file_client = MagicMock()
        fake_file_client.get_file_properties.side_effect = ResourceNotFoundError("404 not found")
        fake_fs = MagicMock()
        fake_fs.get_file_client.return_value = fake_file_client
        monkeypatch.setattr(azure_io, "_filesystem_client", lambda: fake_fs)

        with pytest.raises(ResourceNotFoundError):
            azure_io.download_to_bytes("final/missing.csv")

    def test_download_auth_failure_raises_azure_auth_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_etag: str,
    ) -> None:
        from lib import azure_io

        _reset_azure_state()
        monkeypatch.setattr(azure_io, "_CACHE_ROOT", tmp_path)

        # Etag retorna OK mas download lança auth.
        monkeypatch.setattr(azure_io, "blob_etag", lambda _path: fake_etag)
        fake_file_client = MagicMock()
        fake_file_client.download_file.side_effect = ClientAuthenticationError("403")
        fake_fs = MagicMock()
        fake_fs.get_file_client.return_value = fake_file_client
        monkeypatch.setattr(azure_io, "_filesystem_client", lambda: fake_fs)

        with pytest.raises(azure_io.AzureAuthError):
            azure_io.download_to_bytes("final/secret.csv")

    def test_read_csv_parses_dataframe(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fake_etag: str,
    ) -> None:
        from lib import azure_io

        _reset_azure_state()
        monkeypatch.setattr(azure_io, "_CACHE_ROOT", tmp_path)
        path = "final/scores.csv"
        body = b"id_cnpj,score\nA1,500\nA2,750\n"

        (tmp_path / "final").mkdir(parents=True)
        (tmp_path / "final" / "scores.csv").write_bytes(body)
        (tmp_path / "final" / "scores.csv.etag").write_text(fake_etag, encoding="utf-8")
        monkeypatch.setattr(azure_io, "blob_etag", lambda _path: fake_etag)

        df = azure_io.read_csv(path)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["id_cnpj", "score"]
        assert len(df) == 2
        assert df.iloc[0]["score"] == 500
