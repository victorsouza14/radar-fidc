"""Resolução central de paths do projeto.

Toda referência a "onde estão os dados / outputs" passa por aqui.
Permite override via variáveis de ambiente sem mudar código.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default)))


@dataclass(frozen=True)
class Paths:
    repo_root:   Path
    data_real:   Path
    rating:      Path
    matches:     Path
    clientes:    Path
    credit:      Path
    macro:       Path
    bases:       Path
    arquivos:    Path
    dashboard_json: Path

    @classmethod
    def default(cls) -> "Paths":
        data_real = _env_path("RADAR_DATA_DIR", REPO_ROOT / "data_real")
        return cls._build(data_real)

    @classmethod
    def from_data_dir(cls, data_dir: str | Path) -> "Paths":
        """Constrói `Paths` a partir de um diretório custom — sem mutar `os.environ`."""
        return cls._build(Path(data_dir))

    @classmethod
    def _build(cls, data_real: Path) -> "Paths":
        return cls(
            repo_root      = REPO_ROOT,
            data_real      = data_real,
            rating         = data_real / "rating_fidc.xlsx",
            matches        = data_real / "matches.xlsx",
            clientes       = data_real / "clientes.csv",
            credit         = data_real / "scores_credito.csv",
            macro          = data_real / "macroeconomicos" / "consolidade.csv",
            bases          = data_real / "bases",
            arquivos       = data_real / "arquivos",
            dashboard_json = REPO_ROOT / "data.json",
        )
