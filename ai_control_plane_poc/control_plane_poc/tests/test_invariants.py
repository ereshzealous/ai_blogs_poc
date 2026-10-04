"""Architecture invariants the article relies on, checked against the code and against a running runtime.

Runtime executes. Control Plane governs. Enforcement points enforce. Observability proves.  Each test below pins one
side of that split: agents and runtimes cannot change the control plane; a protected action reaches a system of record
only through an enforcement decision; every decision names the version it was made under; a bundle that fails its
signature is never applied.
"""

import ast
import json

import pytest

from acp.common import AGENTS_DIR, POC, read_json, read_jsonl
from acp.controlplane import ControlPlane
from acp.experiments import INC, tree
from acp.runtime.sdk import Context, Runtime
from acp.systems import SystemRefused, Systems

GOVERNED = sorted([*(POC / "acp" / "runtime").glob("*.py"), *AGENTS_DIR.glob("*.py")])


def imported_modules(p):
    out = set()
    for n in ast.walk(ast.parse(p.read_text())):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out.add(n.module or "")
    return out


@pytest.fixture
def world(tmp_path):
    ControlPlane(tmp_path).bootstrap(0)
    return tmp_path


def test_runtime_and_agents_cannot_reach_the_control_plane_mutation_api():
    for p in GOVERNED:
        assert not any(m.startswith("acp.controlplane") for m in imported_modules(p)), f"{p.name} imports the control plane"


def test_the_agent_surface_offers_no_governance_operation():
    public = {n for n in vars(Context) if not n.startswith("_")}
    assert public == {"call", "tools", "model"}, public


def test_running_agents_leaves_the_control_plane_store_untouched(world):
    before = tree(world / "controlplane")
    rt = Runtime(world, "rt-a")
    for i, agent in enumerate(("incident-agent", "support-agent", "finance-agent")):
        rt.run(
            agent, INC if agent == "incident-agent" else {"case_id": "CASE-2231", "refund": True} if agent == "support-agent" else {}, f"run-{i}", 10 * (i + 1)
        )
    rt.status(40)
    assert tree(world / "controlplane") == before


def test_a_system_of_record_refuses_a_call_without_a_brokered_credential(world):
    with pytest.raises(SystemRefused):
        Systems(world).call("deploy", "restart_service", {"service": "payment-service", "environment": "production"}, "incident-agent", None, 1)
    assert read_json(world / "systems" / "effects.json", {"restarts": []})["restarts"] == []


def test_execution_is_reached_only_after_an_enforcement_decision():
    """In the runtime, the one call into a system of record sits in Runtime.execute, and every function that calls
    execute has asked the decision function first (earlier in the same function)."""
    mod = ast.parse((POC / "acp" / "runtime" / "sdk.py").read_text())
    system_calls, callers = [], []
    for fn in (n for n in ast.walk(mod) if isinstance(n, ast.FunctionDef)):
        calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)]
        if any(ast.unparse(c.func) == "self.systems.call" for c in calls):
            system_calls.append(fn.name)
        execs = [c.lineno for c in calls if c.func.attr == "execute"]
        if execs:
            decides = [c.lineno for c in calls if c.func.attr.startswith("decide_")]
            callers.append(fn.name)
            assert decides and min(decides) < min(execs), f"{fn.name} executes without a prior decision"
    assert system_calls == ["execute"]
    assert sorted(callers) == ["call", "resume"]


def test_every_decision_names_the_version_it_was_made_under(world):
    Runtime(world, "rt-a").run("incident-agent", INC, "run-001", 10)
    decided = [e for e in read_jsonl(world / "runtime" / "rt-a" / "audit.jsonl") if e.get("decision")]
    assert decided and all(e["config_version"] == "v1" and e["decision"]["rule"] for e in decided)


def test_a_bundle_that_fails_its_signature_is_never_applied(world):
    b = world / "controlplane" / "bundles" / "v1.json"
    body = json.loads(b.read_text())
    body["desired_state"]["agents"]["incident-agent"]["limits"]["max_tool_calls"] = 99
    b.write_text(json.dumps(body))
    r = Runtime(world, "rt-a").run("incident-agent", INC, "run-001", 10)
    events = [e["event"] for e in read_jsonl(world / "runtime" / "rt-a" / "audit.jsonl")]
    assert r["status"] == "denied" and r["config_version"] is None
    assert "config.rejected" in events and "config.applied" not in events
    assert read_json(world / "systems" / "effects.json", {"restarts": []})["restarts"] == []
