"""Agents propose; the platform carries identity.  The dependency rules, checked on the AST."""
import ast
from pathlib import Path

AID = Path(__file__).resolve().parents[1] / "aid"


def imports(path: Path) -> set[str]:
    out = set()
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
        elif isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
    return out


def test_agents_import_only_contracts():
    assert {m for m in imports(AID / "agents.py") if m.startswith("aid")} == {"aid.contracts"}


def test_agents_hold_no_credentials_or_tokens():
    names = set()
    for n in ast.walk(ast.parse((AID / "agents.py").read_text())):
        names.update({n.id} if isinstance(n, ast.Name) else {n.attr} if isinstance(n, ast.Attribute) else
                     {n.arg} if isinstance(n, ast.arg) else {a.name for a in n.names} if isinstance(n, ast.ImportFrom) else set())
    assert not {x for x in names if any(w in x.lower() for w in ("credential", "token", "svid", "secret"))}


def test_only_the_gateway_and_baselines_reach_tools():
    allowed = {"gateway.py", "platform.py", "tools.py", "baselines.py", "experiments.py"}   # platform is the composition root
    for f in AID.glob("*.py"):
        if f.name not in allowed:
            assert "aid.tools" not in imports(f), f.name


def test_gateway_does_not_import_baselines():
    assert "aid.baselines" not in imports(AID / "gateway.py")


def test_trust_layer_knows_no_tool():
    assert not any(m in imports(AID / "trust.py") for m in ("aid.tools", "aid.broker", "aid.gateway"))
