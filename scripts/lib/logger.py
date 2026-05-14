"""Logger estruturado em JSON Lines.

Uso:
    from lib.logger import get_logger
    log = get_logger(__name__)
    log.info("pipeline_start", source="dfdatalakesprint", filesystem="gold")
    log.warn("etag_mismatch", path="final/rating_fidc.xlsx", cached_etag="abc", remote_etag="def")

Cada chamada emite UMA linha JSON em stdout, formato:
    {"ts":"2026-05-14T12:00:00Z","level":"info","event":"pipeline_start","logger":"lib.azure_io","source":"...","filesystem":"gold"}

Compatível com agregadores que aceitam stdout JSON Lines (GitHub Actions, Datadog, etc.).
Não usa stdlib logging — keep it simple, fonte única, sem handlers herdados.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class _StructuredLogger:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def _emit(self, level: str, event: str, **fields: Any) -> None:
        record = {
            "ts": _now_iso(),
            "level": level,
            "event": event,
            "logger": self.name,
            **fields,
        }
        # ensure_ascii=False para emojis/acentos serem legíveis em logs locais.
        # default=str para datetimes, Decimals, paths não-serializáveis caírem em str().
        sys.stdout.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()

    def info(self, event: str, **fields: Any) -> None:
        self._emit("info", event, **fields)

    def warn(self, event: str, **fields: Any) -> None:
        self._emit("warn", event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit("error", event, **fields)


def get_logger(name: str) -> _StructuredLogger:
    return _StructuredLogger(name)
