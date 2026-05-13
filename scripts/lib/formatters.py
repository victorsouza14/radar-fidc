"""Coerções defensivas para a fronteira (input -> JSON).

Pandas devolve `NaN` / `NaT` que viram inválido em JSON. Esses helpers garantem
que tudo que vai pro payload seja tipo nativo serializável.
"""
from __future__ import annotations

import math
from typing import Any, Optional


def is_nullish(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return True
    return False


def to_float(v: Any, default: Optional[float] = 0.0, digits: Optional[int] = None) -> Optional[float]:
    if is_nullish(v):
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return round(f, digits) if digits is not None else f
    except (TypeError, ValueError):
        return default


def to_int(v: Any, default: int = 0) -> int:
    if is_nullish(v):
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def to_str(v: Any, default: str = "") -> str:
    if is_nullish(v):
        return default
    return str(v).strip()


def cnpj_fmt(raw: Any) -> str:
    """Formata CNPJ no padrão `00.000.000/0000-00` zero-padding 14 dígitos."""
    digits = "".join(ch for ch in str(raw) if ch.isdigit()).zfill(14)
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"


def truncate(s: Any, max_len: int, suffix: str = "…") -> str:
    if is_nullish(s):
        return ""
    txt = str(s)
    return txt[:max_len] + suffix if len(txt) > max_len else txt


# ─── PII masking — LGPD ────────────────────────────────────────────────
# Esses helpers são a fronteira de saída pública (data.json) para PII de clientes.
# Nunca emitem o dado original; mantêm pista mínima para identificação cruzada
# pelo dono do dado, não pelo público.

def mask_cpf(raw: Any) -> str:
    """`***.***.***-XX` — preserva últimos 2 dígitos para o cliente reconhecer o próprio."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) < 2:
        return "***.***.***-**"
    return f"***.***.***-{digits[-2:]}"


def mask_email(raw: Any) -> str:
    """`c***@****.com` — preserva 1ª letra do local e TLD."""
    s = str(raw or "").strip()
    if "@" not in s:
        return "***@***"
    local, domain = s.split("@", 1)
    dom_parts = domain.rsplit(".", 1)
    tld = dom_parts[-1] if len(dom_parts) > 1 else "***"
    first = local[0] if local else "*"
    return f"{first}***@****.{tld}"


def mask_phone(raw: Any) -> str:
    """`(DD) ****-XXXX` — preserva DDD e últimos 4 dígitos."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) < 6:
        return "(**) ****-****"
    ddd = digits[:2] if len(digits) >= 10 else "**"
    last4 = digits[-4:]
    return f"({ddd}) ****-{last4}"


def mask_name(raw: Any) -> str:
    """`Ana L.` — primeiro nome + inicial do sobrenome, suficiente para o front."""
    s = str(raw or "").strip()
    if not s:
        return "—"
    parts = s.split()
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][:1]}."
