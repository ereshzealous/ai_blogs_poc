"""Dependency direction, enforced on the source (AST), not by convention.

A rule is (source package, forbidden import prefix).  The composition root (layered_platform/service.py) is the only
module allowed to wire implementations of several layers together.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "layered_platform"

RULES = [
    ("experience", ["layered_platform.orchestration", "layered_platform.runtime", "layered_platform.tools", "layered_platform.models",
                    "layered_platform.context", "layered_platform.memory", "layered_platform.policy", "layered_platform.storage", "mcp", "httpx", "sqlite3"]),
    ("orchestration", ["layered_platform.experience", "layered_platform.models", "layered_platform.tools.mcp_client", "mcp", "httpx", "sqlite3"]),
    ("runtime", ["layered_platform.experience", "layered_platform.orchestration", "layered_platform.models", "layered_platform.tools",
                 "layered_platform.policy", "mcp", "httpx"]),
    ("context", ["layered_platform.experience", "layered_platform.orchestration", "layered_platform.runtime", "layered_platform.tools",
                 "layered_platform.models", "mcp", "httpx"]),
    ("memory", ["layered_platform.experience", "layered_platform.orchestration", "layered_platform.runtime", "layered_platform.tools",
                "layered_platform.models", "mcp", "httpx"]),
    ("tools", ["layered_platform.experience", "layered_platform.orchestration", "layered_platform.runtime", "layered_platform.models",
               "layered_platform.context", "layered_platform.memory", "httpx"]),
    ("models", ["layered_platform.experience", "layered_platform.orchestration", "layered_platform.runtime", "layered_platform.tools",
                "layered_platform.context", "layered_platform.memory", "layered_platform.policy", "mcp"]),
    ("policy", ["layered_platform.experience", "layered_platform.orchestration", "layered_platform.runtime", "layered_platform.tools",
                "layered_platform.models", "mcp", "httpx"]),
    ("", ["simulated_enterprise", "mcp_servers", "monolith", "experiments"]),   # the platform never touches the simulated world directly
]


def imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def files(sub: str) -> list[Path]:
    return sorted((PKG / sub).rglob("*.py")) if sub else sorted(PKG.rglob("*.py"))


@pytest.mark.parametrize("layer,forbidden", RULES, ids=[r[0] or "whole-platform" for r in RULES])
def test_layer_does_not_import_forbidden(layer, forbidden):
    bad = [(str(f.relative_to(ROOT)), m) for f in files(layer) for m in imports(f) if any(m == x or m.startswith(x + ".") for x in forbidden)]
    assert not bad, f"{layer or 'platform'} imports what it must not: {bad}"


def test_only_the_mcp_client_speaks_mcp():
    users = sorted(str(f.relative_to(ROOT)) for f in files("") if any(m == "mcp" or m.startswith("mcp.") or m == "mcp_types" for m in imports(f)))
    assert users == ["layered_platform/tools/mcp_client.py"]


def test_only_the_provider_adapter_speaks_http():
    users = sorted(str(f.relative_to(ROOT)) for f in files("") if "httpx" in imports(f))
    assert users == ["layered_platform/models/ollama.py"]


def test_only_the_gateway_reaches_the_mcp_client():
    users = sorted(str(f.relative_to(ROOT)) for f in files("") if "layered_platform.tools.mcp_client" in imports(f))
    assert users == ["layered_platform/service.py", "layered_platform/tools/gateway.py"], "a module other than the gateway could bypass policy"


def test_no_provider_or_model_names_outside_config():
    names = ("gpt-oss", "qwen", "llama", "ollama")
    bad = [str(f.relative_to(ROOT)) for f in files("") if f.parent.name != "models"
           and any(n in f.read_text().lower() for n in names)]
    assert not bad, f"provider/model names leak outside Model Services: {bad}"


def test_provider_options_stay_in_the_adapter():
    bad = [str(f.relative_to(ROOT)) for f in files("") if f.name != "ollama.py" and '"think"' in f.read_text()]
    assert not bad


def test_checker_catches_a_violation(tmp_path):
    """Negative control: the rule checker is not vacuous."""
    bad = tmp_path / "leaky_channel.py"
    bad.write_text("from layered_platform.models.ollama import OllamaProvider\nimport mcp\n")
    found = imports(bad)
    forbidden = dict(RULES)["experience"]
    assert any(m.startswith("layered_platform.models") for m in found) and any(m == x for m in found for x in forbidden)
