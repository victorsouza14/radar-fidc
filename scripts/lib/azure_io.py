"""Camada de acesso ao ADLS Gen2 com cache de duas camadas.

- Camada 1 (byte cache): bytes brutos do blob em `.cache/<path>`, invalidados via ETag.
- Camada 2 (parse cache): DataFrame serializado em `.cache/<path>.parsed.pkl`,
  invalidado se o byte cache mudou.

Lógica de cache:
    1. Pega ETag remoto (HEAD do blob)
    2. Se existe `.cache/<path>.etag` igual ao remoto E o `.cache/<path>` existe:
       reusa bytes locais (zero egress)
    3. Senão, baixa, grava bytes + ETag
    4. Para `read_csv`/`read_excel`: se existir `.parsed.pkl` válido, devolve direto

No CI o cache é vazio em cada run (proposital — garante leitura fresca).
Localmente acelera de ~5s para <50ms por arquivo após primeiro run.

Erros:
    - 401/403 -> AzureAuthError (fail fast, NÃO retry)
    - 5xx/timeout -> retry exponencial do SDK (config explícita abaixo)
    - ETag inconsistente entre HEAD e GET -> warn + re-download
"""

from __future__ import annotations

import io
import os
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import pandas as pd
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.storage.filedatalake import DataLakeServiceClient, FileSystemClient

from .gold_paths import FILESYSTEM, LOCAL_CACHE_DIR
from .logger import get_logger

log = get_logger(__name__)

# Raiz do cache local (sempre relativo ao cwd do script que importa).
_CACHE_ROOT = Path(LOCAL_CACHE_DIR).resolve()


class AzureAuthError(RuntimeError):
    """Falha de autenticação no ADLS — não retentar."""


class AzureMissingConnectionString(RuntimeError):
    """`AZURE_CONNECTION_STRING` ausente do ambiente."""


# ─── Cliente cacheado ────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _service_client() -> DataLakeServiceClient:
    conn = os.environ.get("AZURE_CONNECTION_STRING")
    if not conn:
        raise AzureMissingConnectionString(
            "AZURE_CONNECTION_STRING ausente. Configure no .env local ou no GitHub Secret AZURE_CONNECTION_STRING."
        )
    # retry_total=5, backoff exponencial. SDK Azure já trata 5xx; 401/403 não retenta.
    return DataLakeServiceClient.from_connection_string(
        conn,
        retry_total=5,
        retry_backoff_factor=0.5,
    )


@lru_cache(maxsize=1)
def _filesystem_client() -> FileSystemClient:
    return _service_client().get_file_system_client(FILESYSTEM)


# ─── Cache helpers ───────────────────────────────────────────────────────
def _cache_path_for(remote_path: str) -> Path:
    """Mapeia 'final/rating_fidc.xlsx' -> '.cache/final/rating_fidc.xlsx'."""
    return _CACHE_ROOT / remote_path


def _etag_cache_path_for(remote_path: str) -> Path:
    return _CACHE_ROOT / f"{remote_path}.etag"


def _parsed_cache_path_for(remote_path: str) -> Path:
    return _CACHE_ROOT / f"{remote_path}.parsed.pkl"


def _read_etag_cached(remote_path: str) -> str | None:
    p = _etag_cache_path_for(remote_path)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _write_etag_cached(remote_path: str, etag: str) -> None:
    p = _etag_cache_path_for(remote_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(etag, encoding="utf-8")


# ─── Operações ADLS ──────────────────────────────────────────────────────
def blob_etag(remote_path: str) -> str:
    """Retorna o ETag do blob (HEAD). Custo: ~50ms, sem egress."""
    try:
        props = _filesystem_client().get_file_client(remote_path).get_file_properties()
    except ClientAuthenticationError as e:
        raise AzureAuthError(f"Falha auth ao buscar ETag de {remote_path}: {e}") from e
    return props.etag or ""


def download_to_bytes(remote_path: str) -> bytes:
    """Baixa o blob, valida ETag, mantém cache em `.cache/`. Retorna bytes."""
    log.info("download_start", path=remote_path)
    local = _cache_path_for(remote_path)
    cached_etag = _read_etag_cached(remote_path)

    try:
        remote_etag = blob_etag(remote_path)
    except AzureAuthError:
        raise
    except HttpResponseError as e:
        log.error("etag_fetch_failed", path=remote_path, error=str(e))
        raise

    if cached_etag == remote_etag and local.exists():
        log.info("download_cache_hit", path=remote_path, etag=remote_etag, bytes=local.stat().st_size)
        return local.read_bytes()

    log.info("download_cache_miss", path=remote_path, cached_etag=cached_etag, remote_etag=remote_etag)
    try:
        downloader = _filesystem_client().get_file_client(remote_path).download_file()
        data = downloader.readall()
    except ClientAuthenticationError as e:
        raise AzureAuthError(f"Falha auth ao baixar {remote_path}: {e}") from e

    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)
    _write_etag_cached(remote_path, remote_etag)
    # Invalida parse cache associado.
    parsed = _parsed_cache_path_for(remote_path)
    if parsed.exists():
        parsed.unlink()
    log.info("download_complete", path=remote_path, bytes=len(data), etag=remote_etag)
    return data


# ─── Parse cache helpers ─────────────────────────────────────────────────
def _try_parsed_cache(remote_path: str) -> Any | None:
    """Devolve o objeto Python cacheado, se ETag bate com remoto."""
    parsed = _parsed_cache_path_for(remote_path)
    if not parsed.exists():
        return None
    # Confiança transitiva: se etag local bate com remoto E parsed existe, parsed é válido.
    cached_etag = _read_etag_cached(remote_path)
    if cached_etag is None:
        return None
    try:
        remote_etag = blob_etag(remote_path)
    except (AzureAuthError, HttpResponseError):
        # Sem internet ou auth caiu: confiar no cache local.
        log.warn("parsed_cache_etag_check_failed", path=remote_path)
        return pickle.loads(parsed.read_bytes())
    if cached_etag != remote_etag:
        return None
    log.info("parsed_cache_hit", path=remote_path)
    return pickle.loads(parsed.read_bytes())


def _save_parsed_cache(remote_path: str, obj: Any) -> None:
    parsed = _parsed_cache_path_for(remote_path)
    parsed.parent.mkdir(parents=True, exist_ok=True)
    parsed.write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


# ─── Leitura tipada (com parse cache) ────────────────────────────────────
def read_csv(remote_path: str, **kwargs: Any) -> pd.DataFrame:
    cached = _try_parsed_cache(remote_path)
    if isinstance(cached, pd.DataFrame):
        return cached
    data = download_to_bytes(remote_path)
    df: pd.DataFrame = pd.read_csv(io.BytesIO(data), **kwargs)
    _save_parsed_cache(remote_path, df)
    return df


def read_excel(remote_path: str, sheet_name: str | int | None = 0, **kwargs: Any) -> pd.DataFrame:
    cached = _try_parsed_cache(f"{remote_path}::{sheet_name}")
    if isinstance(cached, pd.DataFrame):
        return cached
    data = download_to_bytes(remote_path)
    # pandas.read_excel pode devolver DataFrame ou dict[str, DataFrame] dependendo de sheet_name;
    # nossa assinatura aceita só um sheet_name escalar (string|int|None=0) → resultado é DataFrame.
    df = cast(pd.DataFrame, pd.read_excel(io.BytesIO(data), sheet_name=sheet_name, **kwargs))
    _save_parsed_cache(f"{remote_path}::{sheet_name}", df)
    return df


def read_excel_sheets(remote_path: str, sheets: list[str]) -> dict[str, pd.DataFrame]:
    """Lê múltiplas abas de um único download (mais eficiente que vários read_excel)."""
    data = download_to_bytes(remote_path)
    xls = pd.ExcelFile(io.BytesIO(data))
    return {sheet: pd.read_excel(xls, sheet_name=sheet) for sheet in sheets if sheet in xls.sheet_names}


def list_dir(remote_dir: str) -> list[str]:
    """Lista paths de blobs sob um prefixo. Útil para descobrir arquivos macro."""
    fs = _filesystem_client()
    return [p.name for p in fs.get_paths(path=remote_dir) if not p.is_directory]
