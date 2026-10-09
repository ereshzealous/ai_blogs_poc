"""The gates must not be able to recognise a scenario by its label. Only the scripted model and the corpus loader may
import the corpus; the registry, identity, policy, approval, gateway, egress and oracle modules may not.
"""
import ast
from pathlib import Path

import pytest

GATES = ["registry", "identity", "policy", "approvals", "gateway", "guard", "oracle", "enterprise", "transport"]
SRC = Path(__file__).resolve().parents[1] / "redteam"


def _imports(mod: str) -> set[str]:
    tree = ast.parse((SRC / f"{mod}.py").read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


@pytest.mark.contract
@pytest.mark.parametrize("mod", GATES)
def test_gate_does_not_import_corpus(mod):
    imported = _imports(mod)
    assert "redteam.corpus" not in imported, f"{mod} must not import the corpus (it could cheat off the label)"
    assert "redteam.model" not in imported, f"{mod} must not import the scripted model"


@pytest.mark.contract
def test_only_model_and_loader_touch_corpus():
    touchers = [m.stem for m in SRC.glob("*.py") if "redteam.corpus" in _imports(m.stem)]
    # the runner and the CLI drive the corpus; the model receives a scenario as an argument and never imports it.
    assert set(touchers) <= {"runner", "cli"}, f"unexpected corpus importers: {touchers}"
