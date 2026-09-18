"""Writes the material the author of held-out set 3 works from (docs/CAPABILITY_RESOLUTION_V5.md, section 4).

    python -m benchmark.dev.holdout3_author_pack <out-dir>

* `tools_list.json`: what `tools/list` publishes for the 500-tool catalog (no generator tags, no registry data);
* `entity_inventory.md`: the entities in the scenario;
* `compute_policy.py`: the expected policy decision for a golden call under policy v2;
* `BRIEF.md`: a copy of `benchmark/prompts/holdout3_brief.md`.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import yaml

from control_plane.paths import CATALOG_DIR, REPO_ROOT, SCENARIO_FILE

BRIEF = REPO_ROOT / "benchmark" / "prompts" / "holdout3_brief.md"
POLICY_HELPER = '''"""Expected policy decision for a golden call under policy v2.

    uv run python <this file> '<golden_tool>' '<json arguments>' [--user oncall-1 --roles sre-oncall]

Run from the repository root. Prints ALLOW, REQUIRE_APPROVAL or DENY.
"""
import argparse, json
from control_plane.policy.engine import Identity, PolicyEngine, PolicyInput
from control_plane.policy.environment import ResourceInventory, resolve_environment
from control_plane.registry.registry import CapabilityRegistry

p = argparse.ArgumentParser()
p.add_argument("tool"); p.add_argument("arguments")
p.add_argument("--user", default="oncall-1"); p.add_argument("--roles", default="sre-oncall")
a = p.parse_args()
args = json.loads(a.arguments)
args = {k: (v[0] if isinstance(v, list) else ("x" if v == "*" else v)) for k, v in args.items()}
reg = CapabilityRegistry.load()
rec = reg.get(a.tool)
env = resolve_environment(args, rec, ResourceInventory.from_scenario()).environment
r = PolicyEngine.load(version="v2").evaluate(PolicyInput(Identity(a.user, tuple(a.roles.split(","))), a.tool, args, rec, env, "req"))
print(r.decision.value)
'''


def tools_list() -> dict:
    manifest = json.loads((CATALOG_DIR / "catalog_500.json").read_text())
    core = {f"{t['server']}.{t['name']}" for t in json.loads((CATALOG_DIR / "catalog_50.json").read_text())["tools"]}
    tools = []
    for t in manifest["tools"]:
        tool_id = f"{t['server']}.{t['name']}"
        hints = {k: t[k] for k in ("read_only_hint", "destructive_hint", "idempotent_hint", "open_world_hint") if t.get(k) is not None}
        tools.append({"tool_id": tool_id, "server": t["server"], "name": t["name"], "title": t.get("title"),
                      "description": t["description"], "input_schema": t["input_schema"], "annotations": hints,
                      "core": tool_id in core})
    return {"note": "What tools/list publishes for the 500-tool catalog. 'core' marks the 50 tools a golden tool must come from.",
            "tools": tools}


def entity_inventory() -> str:
    sc = yaml.safe_load(SCENARIO_FILE.read_text())
    lines = ["# Entity inventory (what the enterprise's systems know about)", "", "## Services", ""]
    lines += [f"- {n}: {s['display_name']}, namespace `{s['namespace']}`, owner {s['owner_team']}, tier {s['tier']}, "
              f"depends on {', '.join(s['dependencies'])}" for n, s in sc["services"].items()]
    lines += ["- search-api (appears in incidents only)", "", "## Kubernetes", ""]
    for svc, envs in sc["kubernetes"].items():
        for env, w in envs.items():
            lines.append(f"- {svc} in {env}: cluster `{w['cluster']}`, namespace `{w['namespace']}`, pods "
                         + ", ".join(f"`{p['name']}`" for p in w["pods"]))
    sections = [
        ("Cloud resources", [f"- `{r['id']}`: {r['type']}, {r['environment']}, region {r['region']}, status {r['status']}"
                             for r in sc["cloud"]["resources"]]),
        ("Feature flags", [f"- `{f['key']}` ({f['environment']}): {f['description']}; enabled={f['enabled']}"
                           for f in sc["feature_flags"]["flags"]]),
        ("Chat channels", [f"- `{c['name']}`: {c['topic']}" for c in sc["collaboration"]["channels"]]),
        ("Incidents", [f"- `{i['id']}`: {i['title']} ({i['severity']}, {i['status']}, {i['service']}, {i['environment']})"
                       for i in sc["incidents"]]),
        ("Release-pipeline deployments", [f"- `{d['id']}`: {d['service']} {d['version']} to {d['environment']} "
                                          f"(previous {d['previous_version']}, commit {d['commit']})" for d in sc["deployments"]]),
        ("Releases", [f"- `{r['id']}`: {r['service']} {r['version']}" for r in sc["releases"]]),
        ("Commits", [f"- `{sha}` in {c['repository']}: {c['message']}" for sha, c in sc["commits"].items()]),
        ("Traces", [f"- `{t['trace_id']}`: {t['service']} {t['environment']} {t['root']} {t['duration_ms']} ms"
                    for t in sc["traces"].values()]),
        ("Alerts", [f"- `{a['id']}` {a['name']}: {a['service']} {a['environment']} {a['severity']} {a['state']}"
                    for a in sc["alerts"]]),
        ("Configuration items", [f"- `{c['ci_id']}`: {c['name']} ({c['type']}), owner {c['owner_team']}"
                                 for c in sc["cmdb"]["configuration_items"]]),
        ("Databases with slow-query data", [f"- `{d}`" for d in sc["database"]["slow_queries"]]),
    ]
    for title, items in sections:
        lines += ["", f"## {title}", ""] + items
    lines += ["", "Runbooks referenced by services: " + ", ".join(sorted({s["runbook"] for s in sc["services"].values()}))]
    return "\n".join(lines) + "\n"


def write_pack(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "tools_list.json").write_text(json.dumps(tools_list(), indent=1) + "\n")
    (out / "entity_inventory.md").write_text(entity_inventory())
    (out / "compute_policy.py").write_text(POLICY_HELPER)
    shutil.copyfile(BRIEF, out / "BRIEF.md")


if __name__ == "__main__":
    write_pack(Path(sys.argv[1]))
    print(f"wrote the author pack to {sys.argv[1]}")
