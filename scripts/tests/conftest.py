"""Fixtures compartilhadas entre testes.

- `monkey_env`: limpa env vars sensíveis antes de cada teste
- `disable_azure_real`: garante que nenhum teste bate em ADLS de verdade
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Permite `from lib.* import ...` dentro dos testes sem instalar o pacote.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def _isolate_azure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove credenciais reais do ambiente do teste por segurança."""
    for key in ("AZURE_CONNECTION_STRING", "AZURE_STORAGE_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def fake_etag() -> str:
    return '"0x8DB000000000000"'
