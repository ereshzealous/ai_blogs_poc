"""Read T1's run directories for the Lab Console: runs, scenarios, recorded events, data lineage.

Every value comes from agent_identity_poc/runs/<run>/scenarios/<scenario>/ (written by aid/experiments.py): scenario.json
(what the scenario was for, what it showed, its checks), audit.jsonl (the platform's hash-chained record), tool-logs.json
(each simulated system's own log) and effects.json (what the systems physically changed).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POC = ROOT / "agent_identity_poc"
RUNS = POC / "runs"

MODEL = {"A": "Shared account", "B": "User token", "C": "Delegation chain"}
OUTCOME = {"held": "HELD", "qualified": "QUALIFIED", "broken": "BROKEN"}
EXPERIMENTS = {
    "I1": ("Attribution", "Can each record say who acted, on whose behalf, with what authority?"),
    "I2": ("Confused deputy", "Can a read-only agent get a rollback done by asking a privileged one?"),
    "I3": ("Revocation", "What does each revocation lever stop, and how fast?"),
    "I4": ("Replay and theft", "Is a copied or stolen token useful to someone else?"),
    "I5": ("Impersonation vs delegation", "Can the agent's action be told apart from the human's own?"),
    "I6": ("Privilege build-up", "What does each identity end up holding? (derived from configuration)"),
    "I7": ("The pause", "If authority is revoked while a rollback waits for approval, does the rollback still run?"),
}
STEP = {"execution.started": "ingress", "execution.delegated": "delegation", "token.refreshed": "exchange", "execution.halted": "exchange",
        "capability.call": "gateway", "capability.denied": "gateway", "capability.rejected": "gateway",
        "approval.requested": "approval", "approval.decided": "approval", "revoked": "revocation"}
STEPS = ["ingress", "delegation", "exchange", "gateway", "approval", "revocation", "tool"]
SHOW = ("invoker", "on_behalf_of", "agent", "act_chain", "credential", "parent", "capability", "arguments", "tool_principal", "status", "rule",
        "authorized_by", "reason", "approval_id", "decided_by", "accepted", "layer", "target", "how", "workload")
TONE = {"capability.call": "ok", "capability.denied": "bad", "capability.rejected": "bad", "execution.halted": "bad",
        "approval.requested": "warn", "revoked": "warn", "token.refreshed": "warn"}


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def discover(primary: str) -> list[dict]:
    """Every run directory with recorded scenarios, the primary first."""
    out = []
    names = [primary] + sorted(p.name for p in RUNS.iterdir() if p.is_dir() and p.name != primary)
    for name in names:
        d = RUNS / name
        if not (d / "scenarios").is_dir() or not any((d / "scenarios").glob("*/scenario.json")):
            continue
        man = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        out.append({"id": name, "dir": d, "scen": d / "scenarios", "kind": "recorded", "manifest": man, "label": f"{name} · recorded run"})
    return out


def scenarios(run: dict) -> list[tuple[Path, dict]]:
    order = {e: i for i, e in enumerate(EXPERIMENTS)}
    sc = [(p, json.loads((p / "scenario.json").read_text())) for p in run["scen"].iterdir() if (p / "scenario.json").exists()]
    return sorted(sc, key=lambda x: (order[x[1]["experiment"]], "ABC".index(x[1]["variant"]), x[1]["id"]))


def _short(v) -> str:
    s = v if isinstance(v, str) else json.dumps(v, sort_keys=True)
    return s if len(s) <= 90 else s[:87] + "…"


def events(sd: Path) -> list[dict]:
    """The platform's audit rows and every tool's own log entries, in time order, each with a step and a tone."""
    ev = []
    for r in jl(sd / "audit.jsonl"):
        rec = r["record"]
        fields = " · ".join(f"{k} `{_short(rec[k])}`" for k in SHOW if k in rec and rec[k] not in (None, [], ""))
        ev.append({"ts": r["t"], "kind": r["kind"], "step": STEP.get(r["kind"], "gateway"), "tone": TONE.get(r["kind"], ""),
                   "text": f"**{r['kind']}**" + (f" · {fields}" if fields else ""), "code": None,
                   "msg": f"row {r['n']} · hash {r['hash'][:12]}… · prev {r['prev'][:12]}…", "src": f"audit.jsonl · {r['platform']} row {r['n']}"})
    logs = json.loads((sd / "tool-logs.json").read_text()) if (sd / "tool-logs.json").exists() else {}
    for label, systems in logs.items():
        for system, entries in systems.items():
            for i, e in enumerate(entries):
                status = e.get("responseStatus", e.get("status", 200))
                body = {k: v for k, v in e.items() if k != "ts"}
                ev.append({"ts": e.get("ts", 0), "kind": "tool", "step": "tool", "tone": "" if status == 200 else "bad",
                           "text": f"**{system}** log · " + " · ".join(f"{k} `{_short(v)}`" for k, v in body.items()), "code": None, "msg": None,
                           "src": f"tool-logs.json · {label} · {system}[{i}]"})
    ev.sort(key=lambda e: (e["ts"], 0 if e["kind"] != "tool" else 1))
    return ev


def mark_where(ev: list[dict], where: str | None) -> int | None:
    """The first event at the step named in scenario.json's `where`, marked as the point the identity property broke."""
    if not where:
        return None
    head = where.split(":")[0].split(" ")[0]
    kind = "tool" if head in ("tool", "Kubernetes") else head
    for i, e in enumerate(ev):
        if e["kind"] == kind:
            e["failed"] = True
            return i
    return None


def lineage(run: dict, sd: Path, sc: dict) -> list[list]:
    """(stage, file, records, what it carries) from the scenario's inputs to the published number."""
    rel = lambda p: str(p.relative_to(run["dir"]))  # noqa: E731
    audit, logs = jl(sd / "audit.jsonl"), json.loads((sd / "tool-logs.json").read_text())
    effects = json.loads((sd / "effects.json").read_text())
    n_logs = sum(len(v) for s in logs.values() for v in s.values())
    n_eff = sum(len(v) for s in effects.values() for v in s.values())
    return [
        ["Input · identities and grants", "agent_identity_poc/config/*.yaml", str(len(run["manifest"].get("config_sha256", {}))),
         "principals, capabilities, policies, tool identities, the shared account (hashes in manifest.json)"],
        ["Input · scenario", f"agent_identity_poc/aid/experiments.py → {sc['experiment'].lower()}()", "1", "the heads, agents, calls and attack the scenario runs"],
        ["Platform record", rel(sd / "audit.jsonl"), str(len(audit)), "every start, delegation, decision, approval and revocation, hash-chained"],
        ["Tool logs", rel(sd / "tool-logs.json"), str(n_logs), "what each simulated system was shown, in its own log"],
        ["Side effects", rel(sd / "effects.json"), str(n_eff), "what the systems physically changed"],
        ["Scenario record", rel(sd / "scenario.json"), "1", "input, expected, observed, outcome, the checks it answers"],
        ["Experiment aggregate", f"{sc['experiment']}.json", "1", "this scenario rolled up with its siblings"],
        ["Checks", "checks.json", str(len(json.loads((run["dir"] / "checks.json").read_text()))), "every pass/fail check of the run"],
        ["Published numbers", "facts.json", "1", "the values both editions and the evidence documents substitute"],
    ]


def tool_log_transcript(sd: Path) -> list[dict]:
    logs = json.loads((sd / "tool-logs.json").read_text())
    out = []
    for label, systems in logs.items():
        for system, entries in systems.items():
            if not entries:
                continue
            out.append({"n": f"{system} · {label}", "tone": "bad" if any(e.get("responseStatus", e.get("status", 200)) != 200 for e in entries) else "",
                        "text": f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'} in {system}'s own log",
                        "code": "\n".join(json.dumps(e, sort_keys=True) for e in entries[-30:]), "notes": [f"source: `tool-logs.json → {label}.{system}`"]})
    return out
