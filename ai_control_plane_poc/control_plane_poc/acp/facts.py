"""facts.json and summary.md for a run: every number the articles use, each with the file it came from.

Keys: run.* and checks.* for the run; <prefix>.<measure> for every scenario measure, where the prefix is the
experiment (p2.after_decision) or, for experiments with several scenarios, experiment.scenario (p9.outage.stale_run).
"""

from __future__ import annotations

from pathlib import Path

from acp.common import read_jsonl

PREFIX = {
    "P9-C-outage": "p9.outage",
    "P9-C-tampered-bundle": "p9.tamper",
    "P9-C-broker-down": "p9.broker",
    "P11-E-embedded": "p11.embedded",
    "P11-C-control-plane": "p11.cp",
}


def prefix(sid: str) -> str:
    return PREFIX.get(sid, sid.split("-")[0].lower())


def build_facts(run_dir: Path, scenarios: list[dict]) -> dict:
    rid = run_dir.name
    base = f"control_plane_poc/runs/{rid}"
    f: dict = {}

    def add(key, value, source):
        assert key not in f, key
        f[key] = {"value": value, "source": source}

    checks = [c for s in scenarios for c in s["checks"]]
    add("run.id", rid, f"{base}/manifest.json")
    add("run.filed", rid[:10], "the run id")
    add("run.experiments", len({s["experiment"] for s in scenarios}), f"{base}/P*.json")
    add("run.scenarios", len(scenarios), f"{base}/scenarios/*/scenario.json")
    add("checks.passed", sum(c["passed"] for c in checks), f"{base}/checks.json")
    add("checks.total", len(checks), f"{base}/checks.json")
    add("run.agent_code_sha256", scenarios[0]["agent_code_sha256"][:12], f"{base}/manifest.json → agents_code_sha256")
    procs = sum(len({t["instance"] for t in read_jsonl(run_dir / "scenarios" / s["id"] / "transcript.jsonl")}) for s in scenarios)
    add("run.runtime_processes", procs, f"{base}/scenarios/*/transcript.jsonl (distinct runtime instances)")
    versions = sum(
        len(list((run_dir / "scenarios" / s["id"] / "state" / "controlplane" / "bundles").glob("v*.json")))
        for s in scenarios
        if (run_dir / "scenarios" / s["id"] / "state" / "controlplane" / "bundles").exists()
    )
    add("run.bundle_versions", versions, f"{base}/scenarios/*/state/controlplane/bundles/")
    events = sum(len(read_jsonl(p)) for p in (run_dir / "scenarios").glob("*/state/runtime/*/audit.jsonl"))
    add("run.audit_events", events, f"{base}/scenarios/*/state/runtime/*/audit.jsonl")
    for o in ("held", "qualified", "broken"):
        add(f"outcome.{o}", sum(1 for s in scenarios if s["outcome"] == o), f"{base}/scenarios/*/scenario.json → outcome")
    for s in scenarios:
        p = prefix(s["id"])
        src = f"{base}/scenarios/{s['id']}/scenario.json → measures"
        n = sum(c["passed"] for c in s["checks"])
        add(f"{p}.checks", f"{n}/{len(s['checks'])}", f"{base}/scenarios/{s['id']}/scenario.json → checks")
        add(f"{p}.outcome", s["outcome"].upper(), f"{base}/scenarios/{s['id']}/scenario.json → outcome")
        for k, v in s["measures"]:
            add(f"{p}.{k}", v, src)
    return dict(sorted(f.items()))


def summary_md(run_dir: Path, scenarios: list[dict], checks: list[dict]) -> str:
    out = [
        f"# T4 · AI Control Plane · run `{run_dir.name}`",
        "",
        f"{sum(c['passed'] for c in checks)} of {len(checks)} checks passed across {len(scenarios)} scenarios. "
        "Agents follow fixed plans; enterprise systems and models are simulated; every runtime is a real, separate, long-lived process. "
        "Proof cards: `proof.txt`.",
        "",
        "| Scenario | Outcome | Checks | Observed |",
        "|---|---|---|---|",
    ]
    for s in scenarios:
        n = sum(c["passed"] for c in s["checks"])
        out.append(f"| `{s['id']}` | {s['outcome'].upper()} | {n}/{len(s['checks'])} | {s['observed']} |")
    out += [
        "",
        "Outcomes: HELD = the governed property held; QUALIFIED = it held within a stated bound (see `where`); "
        "BROKEN = the baseline lost it, which is what the baseline is there to show.",
        "",
    ]
    return "\n".join(out)
