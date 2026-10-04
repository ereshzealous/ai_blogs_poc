"""The architectural rules the article claims, checked mechanically against the source.

Agents hold business reasoning only: no governance, no model names, no credentials, no control-plane access.
"""

import ast
import re

import yaml

from acp.common import AGENTS_DIR, CONFIG, POC

AGENT_FILES = sorted(p for p in [*AGENTS_DIR.glob("*.py"), *(AGENTS_DIR / "live").glob("*.py")] if p.name != "__init__.py")
STATE = yaml.safe_load((CONFIG / "desired-state.yaml").read_text())


def imports(p):
    tree = ast.parse(p.read_text())
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out.add(n.module or "")
    return out


def test_agents_import_nothing():
    for p in AGENT_FILES:
        assert imports(p) == set(), f"{p.name} imports {imports(p)}: agents reach governance only through ctx"


def test_agents_name_no_model_and_no_credential():
    src = "".join(p.read_text() for p in AGENT_FILES)
    for m in STATE["models"]["catalog"]:
        assert m not in src
    assert "secret://" not in src and "token" not in src.lower()


def code_only(p):
    """The source without docstrings, which may (and do) explain what the agent does not contain."""
    tree = ast.parse(p.read_text())
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
            n.body = n.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_agents_contain_no_policy_branches():
    src = "".join(code_only(p) for p in AGENT_FILES)
    for word in ("approval_required", "allow", "deny", "suspended", "budget", "max_tool_calls", "policy", "role"):
        assert not re.search(rf"\b{word}\b", src), f"agent code mentions {word!r}"


def test_agents_do_not_read_the_control_plane():
    src = "".join(p.read_text() for p in AGENT_FILES)
    assert "desired-state" not in src and "controlplane" not in src and "open(" not in src


def test_embedded_baseline_really_embeds_governance():
    src = (POC / "acp" / "embedded" / "incident_agent.py").read_text()
    assert "MODEL" in src and "ALLOWED_TOOLS" in src and "CREDENTIALS" in src and "needs_approval" in src


def test_runtime_holds_no_policy_literals():
    """The enforcement code must not hard-code any agent, tool or model: every answer comes from the bundle."""
    src = "".join(p.read_text() for p in (POC / "acp" / "runtime").glob("*.py"))
    for name in [*STATE["agents"], *STATE["tools"], *STATE["models"]["catalog"]]:
        assert f'"{name}"' not in src.replace('"incident-agent": "acp.agents.incident_agent"', "").replace(
            '"support-agent": "acp.agents.support_agent"', ""
        ).replace('"finance-agent": "acp.agents.finance_agent"', ""), name
