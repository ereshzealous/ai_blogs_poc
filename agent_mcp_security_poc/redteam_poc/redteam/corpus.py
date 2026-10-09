"""Load and validate the synthetic assurance corpus. Only redteam/model.py and the runner import this; the gates must
not (enforced by tests/test_import_contract.py), so no gate can recognise a scenario by its label or ingress.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from redteam.base import POC

CORPUS = POC / "corpus" / "scenarios.yaml"
CLASSES = {"CONTROL", "PI", "RAG", "TOOL", "MCP", "EXFIL", "BYPASS", "PEER", "MEM", "WITHIN"}
INGRESS = {"none", "email", "attachment", "web", "kb", "tool_result", "mcp_metadata", "peer", "memory"}


def load(path: Path = CORPUS) -> dict[str, Any]:
    doc = yaml.safe_load(path.read_text())
    assert doc.get("schema") == "t6-corpus/v1", "unexpected corpus schema"
    legit = doc["legit_task"]["actions"]
    out = []
    for s in doc["scenarios"]:
        assert s["class"] in CLASSES, f"{s['id']}: bad class {s['class']}"
        assert s["ingress"] in INGRESS, f"{s['id']}: bad ingress {s['ingress']}"
        assert s["set"] in ("dev", "blind"), f"{s['id']}: bad set"
        out.append({**s, "legit_task_actions": legit})
    return {"legit_task": doc["legit_task"], "scenarios": out}


def scenarios(path: Path = CORPUS) -> list[dict[str, Any]]:
    return load(path)["scenarios"]
