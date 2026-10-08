"""Arm B's prompt-injection classifier. Defense in depth, not the boundary. A keyword heuristic over the untrusted
content; see config/guard.yaml for why its hit/miss split is illustrative, not a measured detection rate.
"""
from __future__ import annotations

from redteam.base import CONFIG
import yaml


class Guard:
    def __init__(self) -> None:
        cfg = yaml.safe_load((CONFIG / "guard.yaml").read_text())
        self.terms = [t.lower() for t in cfg["flag_terms"]]
        self.guard_id = cfg["guard_id"]

    def flags(self, content: str) -> bool:
        low = (content or "").lower()
        return any(t in low for t in self.terms)
