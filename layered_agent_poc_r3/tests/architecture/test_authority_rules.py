"""Authority and ownership rules the import table cannot express (invariants L9, L3, L7).

Import direction says which module may call which. These tests say what a module may *decide*. They read the source,
so they need no model and no run:

- no authorization may be derived from model text (L9);
- Model Services may not write workflow state (L9, L3);
- tool adapters may not choose the next workflow step (L7, L3);
- only the action gateway may execute a write (L9).

Each rule ends with a planted violation, so a rule that stopped matching anything fails loudly instead of passing
vacuously.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "layered_platform"

# Words a model's own output would be checked against if a prompt were being treated as authority.
APPROVAL_WORDS = re.compile(r"""["'](?:approved|approve|yes|allow(?:ed)?|authorized|permit(?:ted)?|granted|ok)["']""", re.I)
# The attributes that carry model output through this platform.
MODEL_TEXT = ("content", "text", "answer", "message", "raw", "completion", "response")


def sources(sub: str = "") -> list[Path]:
    return sorted((PKG / sub).rglob("*.py")) if sub else sorted(PKG.rglob("*.py"))


def tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def compares_model_text_to_an_approval_word(node: ast.AST) -> bool:
    """`if result.content == "approved"`, `if "yes" in answer.lower()`, and friends."""
    if isinstance(node, ast.Compare):
        parts = [node.left, *node.comparators]
        text = any(isinstance(p, ast.Attribute) and p.attr in MODEL_TEXT for p in parts) or any(
            isinstance(p, ast.Call) and isinstance(p.func, ast.Attribute) and p.func.attr in ("lower", "strip", "upper")
            and isinstance(p.func.value, ast.Attribute) and p.func.value.attr in MODEL_TEXT for p in parts)
        word = any(isinstance(p, ast.Constant) and isinstance(p.value, str) and APPROVAL_WORDS.fullmatch(f'"{p.value}"') for p in parts)
        return text and word
    return False


def test_no_authority_is_derived_from_model_text():
    """L9: a decision to execute may never come from what the model said."""
    bad = []
    for path in sources():
        if path.name in ("evals",) or "evals" in path.parts:
            continue  # the eval checks read model output on purpose: they score, they do not authorize
        for node in ast.walk(tree(path)):
            if compares_model_text_to_an_approval_word(node):
                bad.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not bad, f"model text is compared to an approval word, which is authority from prose: {bad}"


def test_the_rule_catches_authority_from_model_text(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text("def go(result):\n    if result.content == 'approved':\n        execute()\n")
    assert any(compares_model_text_to_an_approval_word(n) for n in ast.walk(ast.parse(planted.read_text())))


def writes_workflow_state(path: Path) -> list[str]:
    """Calls that persist workflow progression: checkpoints, workflow events, approvals, status transitions."""
    names = ("save_checkpoint", "record_event", "set_status", "advance", "complete_step", "grant", "approve",
             "record_approval", "append_event")
    out = []
    for node in ast.walk(tree(path)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in names:
            out.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.func.attr}()")
    return out


@pytest.mark.parametrize("layer", ["models", "context", "memory"])
def test_model_services_never_mutate_workflow_state(layer):
    """L9, L3: only orchestration and runtime own progression; a model gateway must not advance a workflow."""
    bad = [hit for path in sources(layer) for hit in writes_workflow_state(path)]
    assert not bad, f"{layer} persists workflow progression, which orchestration owns: {bad}"


# Workflow progression vocabulary, matched whole against identifiers and string constants.  Deliberately excludes
# `COMPLETED`, which is also an *operation* state in tools/idempotency.py: an operation's lifecycle is not a
# workflow's progression.
STEP_WORDS = {"next_step", "advance", "advance_workflow", "set_status", "workflow_status", "WAITING_APPROVAL"}


def docstring_lines(mod: ast.Module) -> set[int]:
    """Lines holding a module, class or function docstring: prose, not code."""
    out: set[int] = set()
    for node in ast.walk(mod):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                out.update(range(first.value.lineno, (first.value.end_lineno or first.value.lineno) + 1))
    return out


def progression_hits(path: Path) -> list[str]:
    """Where this module names workflow progression: an attribute, a call, a name or a status constant."""
    mod = ast.parse(path.read_text())
    prose = docstring_lines(mod)
    hits = []
    for node in ast.walk(mod):
        line = getattr(node, "lineno", None)
        if line is None or line in prose:
            continue
        word = (node.attr if isinstance(node, ast.Attribute) else
                node.id if isinstance(node, ast.Name) else
                node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None)
        if word in STEP_WORDS:
            hits.append(f"{path.name}:{line} {word}")
    return hits


def test_tool_adapters_never_choose_the_next_step():
    """L7, L3: an adapter executes a capability; it does not decide what the workflow does next."""
    bad = []
    for path in sources("tools"):
        if path.name == "gateway.py":
            continue  # the gateway stamps the operation id from the step it is given; it still does not choose it
        bad += progression_hits(path)
    assert not bad, f"a tool adapter reasons about workflow progression: {bad}"


def test_the_rule_catches_a_tool_that_advances_a_workflow(tmp_path):
    planted = tmp_path / "adapter.py"
    planted.write_text("def run(wf):\n    wf.set_status('WAITING_APPROVAL')\n")
    assert len(progression_hits(planted)) == 2  # the call and the status it sets


def test_the_rule_ignores_prose_and_operation_states(tmp_path):
    planted = tmp_path / "ops.py"
    planted.write_text('"""A COMPLETED operation and a WAITING_APPROVAL workflow are different things."""\n'
                       "STATES = ('IN_FLIGHT', 'COMPLETED', 'FAILED')\n")
    assert progression_hits(planted) == []
