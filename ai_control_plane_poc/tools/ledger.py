"""The step ledger of a run: one row per recorded event, joined across the raw files that describe it.

    rows(run_dir) -> list[dict]          used by tools/build_results.py (the Run Report) and tools/proof_pack.py (ledger.jsonl)

A row's fields come from the raw evidence and nothing else:

  runtime audit      state/runtime/<instance>/audit.jsonl   event, tick, agent, config version, decision (effect, reason,
                                                            rule), tool or model, approval, cost, audit hash
  transcript         transcript.jsonl                       runtime process label and request hash of the run
  systems of record  state/systems/log.jsonl, models.jsonl  whether the call reached the system, and its status
  change log         state/controlplane/changelog.jsonl     control-plane events (published, rejected, rollout …)
  scenario record    scenario.json                          agent source hash, assertion count

A scenario with no runtime audit (the embedded baseline, P11a) is ledgered from its transcript.
"""

from __future__ import annotations

import json
from pathlib import Path


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def _sor(e: dict, log: list[dict], models: list[dict]) -> str:
    """What the system of record shows for this event: the call that reached it, or that none did."""
    ev = e["event"]
    if ev in ("tool.executed", "action.executed", "action.failed", "action.denied", "approval.requested"):
        hit = [r for r in log if r["tick"] == e["tick"] and r["tool"] == e.get("action") and r["agent"] == e.get("agent")]
        if hit:
            return f"{hit[0]['server']} {hit[0]['tool']} → {hit[0]['status']}"
        return "no call reached a system"
    if ev in ("model.called", "model.denied"):
        hit = [r for r in models if r["tick"] == e["tick"] and r["agent"] == e.get("agent")]
        return f"model gateway {hit[0]['model']} · {hit[0]['tokens']} tokens" if hit else "no call reached a model"
    return ""


def rows(run_dir: Path) -> list[dict]:
    out = []
    order = json.loads((run_dir / "manifest.json").read_text())["scenarios"]
    for sid in order:
        d = run_dir / "scenarios" / sid
        rec = json.loads((d / "scenario.json").read_text())
        sha = rec["agent_code_sha256"][:12]
        assertions = f"{sum(c['passed'] for c in rec['checks'])}/{len(rec['checks'])}"
        trans = jl(d / "transcript.jsonl")
        runs = {(t["instance"], t["request"].get("run_id")): t for t in trans if t["request"].get("op") == "run"}
        log, models = jl(d / "state" / "systems" / "log.jsonl"), jl(d / "state" / "systems" / "models.jsonl")
        events = [("control plane", r) for r in jl(d / "state" / "controlplane" / "changelog.jsonl")]
        for a in sorted((d / "state" / "runtime").glob("*/audit.jsonl")):
            events += [(a.parent.name, r) for r in jl(a)]
        events.sort(key=lambda x: (x[1]["tick"], x[0] != "control plane", x[0], x[1]["n"]))
        base = {"run_id": run_dir.name, "scenario_id": sid, "assertions": assertions}
        n = 0
        for src, e in events:
            n += 1
            if src == "control plane":
                out.append({**base, "step": n, "logical_time": e["tick"], "source": "control plane", "agent": None, "agent_sha256": None,
                            "runtime_pid": None, "request_sha256": None, "cp_version": e.get("version") or e.get("to"), "rule": None,
                            "decision": e["event"].upper() + (f" · {e['reason']}" if e.get("reason") else ""), "tool": None, "model": None,
                            "approval": None, "budget": None, "system_of_record": "", "audit_event": f"change.{e['event']} {e.get('change', '')}".strip(),
                            "actor": e.get("author"), "audit_hash": e["hash"][:12]})
                continue
            t = runs.get((src, e.get("run_id")))
            dec = e.get("decision") or {}
            budget = e.get("usd") if e["event"] == "model.called" else e.get("cost") if e["event"] == "run.finished" else None
            out.append({**base, "step": n, "logical_time": e["tick"], "source": f"runtime {src}", "agent": e.get("agent"), "agent_sha256": sha,
                        "runtime_pid": t.get("runtime_pid") if t else None, "request_sha256": t["request_sha256"][:12] if t and t.get("request_sha256") else None,
                        "cp_version": e.get("config_version") or e.get("cached_version"), "rule": dec.get("rule"),
                        "decision": (dec["effect"].upper() + f" · {dec['reason']}") if dec else (e.get("reason") or e.get("error") or ""),
                        "tool": e.get("action"), "model": e.get("model"), "approval": e.get("approval_id"), "budget": budget,
                        "system_of_record": _sor(e, log, models), "audit_event": e["event"], "actor": e.get("agent"), "audit_hash": e["hash"][:12]})
        if not events:  # no runtime audit and no control plane: the embedded baseline, ledgered from its transcript
            for t in trans:
                if t["request"].get("op") != "run":
                    continue
                for c in t["response"].get("calls", []):
                    n += 1
                    hit = [r for r in log if r["tool"] == c["name"] and r["agent"] == t["request"]["agent"] and r["tick"] >= t["request"]["tick"]]
                    out.append({**base, "step": n, "logical_time": t["request"]["tick"], "source": f"embedded {t['instance']}", "agent": t["request"]["agent"],
                                "agent_sha256": None, "runtime_pid": t.get("runtime_pid"), "request_sha256": t.get("request_sha256", "")[:12] or None,
                                "cp_version": None, "rule": "embedded in agent code", "decision": c["status"].upper(), "tool": c["name"] if c["kind"] == "tool" else None,
                                "model": c["name"] if c["kind"] == "model" else None, "approval": c.get("approval_id"), "budget": None,
                                "system_of_record": f"{hit[0]['server']} {hit[0]['tool']} → {hit[0]['status']}" if hit and c["kind"] == "tool" and c["status"] == "executed" else "",
                                "audit_event": "none (no runtime audit in the baseline)", "actor": t["request"]["agent"], "audit_hash": None})
    return out
