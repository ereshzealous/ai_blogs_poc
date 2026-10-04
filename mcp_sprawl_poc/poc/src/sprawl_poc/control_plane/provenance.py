"""Argument provenance: every argument value must have an owner.

* platform-owned values (ids, charges, amounts on record, regions) are BOUND from systems
  of record by the binder;
* requester-owned values (a new address, a new email, a goodwill amount, a partial refund
  amount, which item was wrong) must be traceable to what the requester actually said.

A requester-owned value that does not appear in the request is treated as invented: the
gateway does not execute it and tells the model to ask.  The check is deterministic
string/number matching — no model.  (Single-turn POC: the request text is the whole
conversation; a multi-turn system would ground against the transcript.)
"""

from __future__ import annotations

import re
from typing import Any

_NUM = re.compile(r"(?<![A-Za-z0-9-])\d+(?:[.,]\d{1,2})?")
_TOK = re.compile(r"[a-z0-9@.]+")


def _norm_tokens(text: str) -> list[str]:
    return [t.strip(".") for t in _TOK.findall(text.lower()) if t.strip(".")]


def request_numbers(text: str) -> list[float]:
    out = []
    for m in _NUM.findall(text):
        try:
            out.append(float(m.replace(",", ".")))
        except ValueError:
            pass
    return out


def grounded(value: Any, request: str) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return any(abs(float(value) - n) < 0.005 for n in request_numbers(request))
    if isinstance(value, str):
        v = value.strip().lower()
        if not v:
            return False
        if v in request.lower():
            return True
        vt = [t for t in _norm_tokens(v) if len(t) >= 2]
        rt = set(_norm_tokens(request))
        return bool(vt) and all(t in rt for t in vt)
    return False


def ungrounded_fields(user_owned: tuple[str, ...], arguments: dict[str, Any], bound: list[str], request: str) -> list[str]:
    return [f for f in user_owned if f in arguments and f not in bound and not grounded(arguments[f], request)]
