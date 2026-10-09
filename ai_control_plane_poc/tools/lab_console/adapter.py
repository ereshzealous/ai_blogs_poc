"""Read T4's run directories for the Lab Console: runs, scenarios, recorded events, data lineage.

Every value comes from control_plane_poc/runs/<run>/scenarios/<scenario>/ (written by acp/experiments.py): scenario.json
(what the scenario was for, what it showed, its checks), transcript.jsonl (every request to a runtime process and its
response) and state/ (the whole world at the end: the control plane's bundles and hash-chained change log, each runtime
instance's hash-chained audit and cache, approvals, spend, and the simulated systems of record).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POC = ROOT / "control_plane_poc"
RUNS = POC / "runs"

MODEL = {"E": "Governance embedded in agents", "C": "Control plane"}
OUTCOME = {"held": "HELD", "qualified": "QUALIFIED", "broken": "NEGATIVE CONTROL"}  # P11: broken by design
EXPERIMENTS = {
    "P1": ("Baseline", "Under v1, does the production restart run, attributed to v1?"),
    "P2": ("Central change", "Change only the control plane: does the same process, code and request now stop for approval?"),
    "P3": ("Approval", "Does the held action wait for an eligible human, then run exactly once?"),
    "P4": ("Suspend", "Does a central suspension stop a run in flight and new runs, and only that agent?"),
    "P5": ("Budgets", "Does a quota stop the third call, and an exhausted budget the next run?"),
    "P6": ("Revoke MCP", "Does disabling one server stop every agent that uses it, and no other?"),
    "P7": ("Models", "Can the default model move, and a model be withdrawn, with no model named in agent code?"),
    "P8": ("Rollout", "Does a canary reach only its bucket, and rollback return every run to stable?"),
    "P9": ("Outage", "What happens without the control plane: reads, mutations, staleness, tampering, broker?"),
    "P10": ("Drift", "Can the control plane see a runtime quietly running an old version, and what it did?"),
    "P11": ("Embedded baseline", "Without a control plane, what do the same changes cost, and when do they apply?"),
    "P12": ("Self-governance", "Who may change the control plane, and is every attempt on the record?"),
}
# The proof hierarchy (scenarios.json, written by the run; acp.experiments.ROLE for a run recorded before it existed)
GROUP = {"baseline": "CORE", "core": "CORE", "capability": "CAPABILITY", "boundary": "BOUNDARIES", "negative-control": "NEGATIVE CONTROL",
         "governor": "GOVERN THE GOVERNOR"}
GROUPS = ["CORE", "CAPABILITY", "BOUNDARIES", "NEGATIVE CONTROL", "GOVERN THE GOVERNOR"]


def roles(run: dict) -> dict[str, dict]:
    """experiment -> {role, property, group}."""
    p = run["dir"] / "scenarios.json"
    if p.exists():
        out = {r["experiment"]: {"role": r["role"], "property": r["property"]} for r in json.loads(p.read_text())}
    else:
        from acp.experiments import ROLE

        out = {e: {"role": r, "property": prop} for e, (r, prop) in ROLE.items()}
    return {e: {**v, "group": GROUP[v["role"]]} for e, v in out.items()}


STEP = {"run.requested": "run", "run.decision": "run", "run.finished": "run", "config.applied": "config", "config.unreachable": "config",
        "config.rejected": "config", "tool.executed": "enforce", "action.executed": "enforce", "action.denied": "enforce", "action.failed": "enforce",
        "approval.requested": "approval", "resume.refused": "approval", "model.called": "model", "model.denied": "model",
        "published": "control plane", "rejected": "control plane", "rollout": "control plane", "promoted": "control plane", "rolled_back": "control plane"}
STEPS = ["control plane", "config", "run", "enforce", "approval", "model", "system"]
SHOW = ("agent", "action", "args", "config_version", "config_source", "previous_version", "track", "decision", "approval_id", "model", "usd", "reason", "error",
        "version", "change", "author", "second_approver", "kind", "paths", "percent", "executed", "credential")
TONE = {"action.executed": "ok", "tool.executed": "ok", "model.called": "ok", "action.denied": "bad", "model.denied": "bad", "action.failed": "bad",
        "config.unreachable": "warn", "config.rejected": "bad", "approval.requested": "warn", "resume.refused": "warn", "rejected": "bad", "published": "ok"}


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def discover(primary: str) -> list[dict]:
    """Every run directory with recorded scenarios, the primary first."""
    out = []
    names = [primary] + sorted(p.name for p in RUNS.iterdir() if p.is_dir() and p.name != primary and not p.name.startswith("_"))
    for name in names:
        d = RUNS / name
        if not (d / "scenarios").is_dir() or not any((d / "scenarios").glob("*/scenario.json")):
            continue
        man = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        out.append({"id": name, "dir": d, "scen": d / "scenarios", "kind": "recorded", "manifest": man, "label": f"{name} · recorded run"})
    return out


def scenarios(run: dict) -> list[tuple[Path, dict]]:
    """In the proof hierarchy's order: core, capability, boundaries, negative control, govern the governor."""
    order, grp = {e: i for i, e in enumerate(EXPERIMENTS)}, roles(run)
    sc = [(p, json.loads((p / "scenario.json").read_text())) for p in run["scen"].iterdir() if (p / "scenario.json").exists()]
    return sorted(sc, key=lambda x: (GROUPS.index(grp[x[1]["experiment"]]["group"]), order[x[1]["experiment"]], "EC".index(x[1]["variant"]), x[1]["id"]))


def _short(v) -> str:
    if isinstance(v, dict) and "effect" in v:
        v = f"{v['effect']} · {v['reason']} · {v['rule']}"
    s = v if isinstance(v, str) else json.dumps(v, sort_keys=True)
    return s if len(s) <= 90 else s[:87] + "…"


def events(sd: Path) -> list[dict]:
    """Control-plane changes, every runtime instance's audit rows and every system call, in tick order."""
    st, ev = sd / "state", []
    for r in jl(st / "controlplane" / "changelog.jsonl"):
        fields = " · ".join(f"{k} `{_short(r[k])}`" for k in SHOW if k in r and r[k] not in (None, [], ""))
        ev.append({"ts": r["tick"], "kind": r["event"], "step": "control plane", "tone": TONE.get(r["event"], ""), "text": f"**control plane · {r['event']}** · {fields}",
                   "code": None, "msg": f"change log row {r['n']} · hash {r['hash'][:12]}…", "src": f"state/controlplane/changelog.jsonl · row {r['n']}"})
    for p in sorted((st / "runtime").glob("*/audit.jsonl")):
        inst = p.parent.name
        for r in jl(p):
            fields = " · ".join(f"{k} `{_short(r[k])}`" for k in SHOW if k in r and r[k] not in (None, [], ""))
            ev.append({"ts": r["tick"], "kind": r["event"], "step": STEP.get(r["event"], "enforce"), "tone": TONE.get(r["event"], ""),
                       "text": f"**{inst} · {r['event']}**" + (f" · {fields}" if fields else ""), "code": None,
                       "msg": f"row {r['n']} · hash {r['hash'][:12]}… · prev {r['prev'][:12]}…", "src": f"state/runtime/{inst}/audit.jsonl · row {r['n']}"})
    for i, r in enumerate(jl(st / "systems" / "log.jsonl")):
        ev.append({"ts": r["tick"], "kind": "system", "step": "system", "tone": "" if r["status"] == 200 else "bad",
                   "text": f"**{r['server']}** saw `{r['tool']}` from `{r['agent']}` · credential `{r['credential']}` · status {r['status']}", "code": None, "msg": None,
                   "src": f"state/systems/log.jsonl[{i}]"})
    ev.sort(key=lambda e: (e["ts"], 0 if e["step"] == "control plane" else (2 if e["step"] == "system" else 1)))
    return ev


def mark_where(ev: list[dict], where: str | None) -> int | None:
    """The first event of the kind named at the head of scenario.json's `where`, marked as the point the property was qualified or broke."""
    if not where:
        return None
    head = where.split(":")[0].strip()
    for i, e in enumerate(ev):
        if e["kind"] == head:
            e["failed"] = True
            return i
    return None


def lineage(run: dict, sd: Path, sc: dict) -> list[list]:
    """(stage, file, records, what it carries) from the scenario's inputs to the published number."""
    rel = lambda p: str(p.relative_to(run["dir"]))  # noqa: E731
    st = sd / "state"
    audits = sorted((st / "runtime").glob("*/audit.jsonl"))
    bundles = sorted((st / "controlplane" / "bundles").glob("v*.json"))
    return [
        ["Input · desired state and changes", "control_plane_poc/config/*.yaml", str(len(run["manifest"].get("config_sha256", {}))),
         "seed desired state, named central changes, administrators, the embedded baseline's edits (hashes in manifest.json)"],
        ["Input · the proof", f"control_plane_poc/acp/experiments.py → {sc['experiment'].lower()}()", "1", "the runs, changes and faults the proof applies"],
        ["Control plane · versions", rel(st / "controlplane" / "bundles"), str(len(bundles)), "every signed bundle version this scenario published"],
        ["Control plane · change log", rel(st / "controlplane" / "changelog.jsonl"), str(len(jl(st / "controlplane" / "changelog.jsonl"))),
         "every accepted and rejected change, hash-chained"],
        ["Runtime · audit", ", ".join(rel(p) for p in audits) or "—", str(sum(len(jl(p)) for p in audits)), "every decision, with its config version, source and rule"],
        ["Runtime · requests", rel(sd / "transcript.jsonl"), str(len(jl(sd / "transcript.jsonl"))), "each request to a runtime process and its response"],
        ["Systems of record", rel(st / "systems"), str(len(jl(st / "systems" / "log.jsonl")) + len(jl(st / "systems" / "models.jsonl"))),
         "what each simulated system and model endpoint saw; side effects in effects.json"],
        ["Scenario record", rel(sd / "scenario.json"), "1", "input, expected, observed, outcome, measures, checks, proof card"],
        ["Proof aggregate", f"{sc['experiment']}.json", "1", "this scenario rolled up with its siblings"],
        ["Checks", "checks.json", str(len(json.loads((run["dir"] / "checks.json").read_text()))), "every pass/fail check of the run"],
        ["Published numbers", "facts.json", "1", "the values both editions and the evidence documents substitute"],
    ]


def tool_log_transcript(sd: Path) -> list[dict]:
    st = sd / "state" / "systems"
    out = []
    by: dict[str, list] = {}
    for r in jl(st / "log.jsonl"):
        by.setdefault(r["server"], []).append(r)
    for server, entries in by.items():
        out.append({"n": server, "tone": "bad" if any(e["status"] != 200 for e in entries) else "",
                    "text": f"{len(entries)} call{'s' if len(entries) != 1 else ''} in {server}'s own log",
                    "code": "\n".join(json.dumps(e, sort_keys=True) for e in entries[-30:]), "notes": ["source: `state/systems/log.jsonl`"]})
    models = jl(st / "models.jsonl")
    if models:
        out.append({"n": "model gateway", "tone": "", "text": f"{len(models)} model call{'s' if len(models) != 1 else ''}: which model served which agent, at what cost",
                    "code": "\n".join(json.dumps(e, sort_keys=True) for e in models[-30:]), "notes": ["source: `state/systems/models.jsonl`"]})
    eff = st / "effects.json"
    if eff.exists():
        out.append({"n": "side effects", "tone": "", "text": "what the systems physically changed", "code": eff.read_text(), "notes": ["source: `state/systems/effects.json`"]})
    return out
