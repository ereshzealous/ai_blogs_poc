"""Tokenisation shared by lexical retrieval and the intent router."""

from __future__ import annotations

import re

_SPLIT = re.compile(r"[^a-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
STOPWORDS = frozenset(
    "a an and are as at be by for from get has have in into is it its of on or that the this to was what when where which "
    "who why will with you your our we us me my i can could should would please now current currently last recent".split()
)


def stem(token: str) -> str:
    """Very light suffix stripping; enough to match logs/log, deployments/deployment, restarting/restart."""
    for suffix, min_len in (("ies", 5), ("ing", 6), ("ed", 5), ("es", 5), ("s", 4)):
        if token.endswith(suffix) and len(token) >= min_len:
            base = token[: -len(suffix)]
            return base + "y" if suffix == "ies" else base
    return token


def tokenize(text: str) -> list[str]:
    text = _CAMEL.sub(" ", text or "")
    return [stem(t) for t in _SPLIT.split(text.lower()) if t and t not in STOPWORDS]
