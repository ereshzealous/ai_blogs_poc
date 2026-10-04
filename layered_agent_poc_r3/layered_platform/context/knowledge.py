"""Knowledge: evidence retrieved from authoritative sources (runbooks), section by section, with its source id."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from layered_platform.config import ROOT


class KnowledgeBase:
    def __init__(self, runbooks_dir: str):
        self.sections: list[dict[str, Any]] = []
        for path in sorted((ROOT / runbooks_dir).glob("*.md")):
            text = path.read_text()
            title = text.splitlines()[0].lstrip("# ").strip()
            for part in re.split(r"\n(?=## )", text)[1:]:
                head, _, body = part.partition("\n")
                self.sections.append({"source": f"{path.stem}#{head.lstrip('# ').strip().lower()}", "doc": title,
                                      "heading": head.lstrip("# ").strip(), "text": body.strip()})

    def search(self, query: str, top_k: int = 3, doc_hint: str | None = None) -> list[dict[str, Any]]:
        words = {w for w in re.findall(r"[a-z0-9-]+", query.lower()) if len(w) > 2}

        def score(s: dict[str, Any]) -> float:
            hay = f"{s['doc']} {s['heading']} {s['text']}".lower()
            return sum(hay.count(w) for w in words) + (5 if doc_hint and doc_hint.lower() in s["doc"].lower() else 0)

        ranked = sorted(self.sections, key=score, reverse=True)
        return [s for s in ranked[:top_k] if score(s) > 0]
