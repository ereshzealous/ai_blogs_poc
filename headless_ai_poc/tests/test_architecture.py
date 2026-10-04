"""Channels render; they never reason.  The dependency rules of the headless boundary, checked on the AST."""
import ast
from pathlib import Path

HAI = Path(__file__).resolve().parents[1] / "hai"


def imports(path: Path) -> set[str]:
    out = set()
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
        elif isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
    return out


def test_head_adapters_import_only_contracts():
    mods = imports(HAI / "ingress" / "adapters.py")
    assert {m for m in mods if m.startswith("hai")} == {"hai.contracts"}


def test_renderers_import_only_contracts():
    mods = imports(HAI / "heads" / "render.py")
    assert {m for m in mods if m.startswith("hai")} == {"hai.contracts"}


def test_runtime_knows_no_channel():
    for f in (HAI / "runtime").glob("*.py"):
        mods = imports(f)
        assert not any(m.startswith(("hai.ingress", "hai.heads")) for m in mods), f.name


def test_only_the_gateway_touches_backends():
    for f in HAI.rglob("*.py"):  # service.py is the composition root; payloads/experiments/cli are fixtures and drivers
        if f.name in ("gateway.py", "world.py", "experiments.py", "cli.py", "service.py", "payloads.py") or "baselines" in f.parts:
            continue
        assert "hai.world" not in imports(f), f"{f.relative_to(HAI)} imports the world"
