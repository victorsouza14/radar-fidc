#!/usr/bin/env python3
"""Sobe arquivos canônicos para ``gold/final/`` no ADLS Gen2.

Ferramenta de manutenção: usada quando os outputs dos scripts canônicos
(``rating_fidc.xlsx``, ``matches.xlsx``, ``clientes.csv``,
``scores_credito.csv``) divergem da cópia em ADLS Gold. Sobrescreve cada
blob com a versão local e força refresh do cache via novo ETag.

Uso::

    python scripts/upload_to_adls.py --source ~/Downloads/data_fishermans_final

Files uploaded (paths em ``scripts/lib/gold_paths.py``):
    rating, matches, clientes, credit (scores_credito).

``AZURE_CONNECTION_STRING`` precisa estar no ``.env`` ou no ambiente.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from lib.azure_io import _filesystem_client  # noqa: E402
from lib.gold_paths import PATHS  # noqa: E402
from lib.logger import get_logger  # noqa: E402

log = get_logger(__name__)

# Mapeia o nome lógico (em PATHS) para o nome do arquivo na pasta local.
UPLOADS: dict[str, str] = {
    "rating": "rating_fidc.xlsx",
    "matches": "matches.xlsx",
    "clientes": "clientes.csv",
    "credit": "scores_credito.csv",
}


def upload_file(local_path: Path, remote_path: str) -> int:
    fs = _filesystem_client()
    file_client = fs.get_file_client(remote_path)
    data = local_path.read_bytes()
    file_client.upload_data(data, overwrite=True)
    return len(data)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Pasta com rating_fidc.xlsx, matches.xlsx, clientes.csv, scores_credito.csv.",
    )
    args = p.parse_args()

    src = args.source.expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"Source dir not found: {src}")

    for key, filename in UPLOADS.items():
        local = src / filename
        if not local.exists():
            log.warn("upload_skipped_missing", key=key, local=str(local))
            continue
        remote = PATHS[key]
        n_bytes = upload_file(local, remote)
        log.info("uploaded", key=key, remote=remote, size_kb=n_bytes // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
