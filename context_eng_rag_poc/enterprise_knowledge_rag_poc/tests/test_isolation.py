"""The system under test never sees the answers: no import of the evaluation package, no string that names the ground
truth or the verifier pairs (docstrings excepted: they may say so)."""

import ast
import re
from pathlib import Path

SYSTEM = Path(__file__).resolve().parents[1] / "knowledge_rag"


def _strings(tree):
    docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


def test_system_never_imports_the_evaluator_or_reads_labels():
    for p in SYSTEM.glob("*.py"):
        tree = ast.parse(p.read_text())
        mods = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        mods += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not [m for m in mods if m.startswith("s2_eval")], f"{p.name} imports the evaluation package"
        for s in _strings(tree):
            assert not re.search(r"groundtruth|labels\.yaml|verifier-pairs", s), f"{p.name}: {s!r}"


def test_no_case_ids_in_the_system():
    """No case-specific exception table: the system code never mentions a case id."""
    for p in SYSTEM.glob("*.py"):
        assert not re.search(r"\b[HD]-(K\d+|P\d)\b", p.read_text()), f"{p.name} mentions a case id"
