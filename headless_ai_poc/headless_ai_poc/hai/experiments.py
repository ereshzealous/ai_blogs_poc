"""The seven F3 experiments.  Deterministic: simulated clock, simulated enterprise, deterministic reasoner.

    uv run hai experiments --run-id <run-id>      -> runs/<run-id>/{X1..X7.json, checks.json, facts.json, summary.md, SHA256SUMS, ...}

Each experiment builds a fresh world and a fresh runtime, drives real code paths through the ingress, and counts
outcomes from the systems of record (world.effects) and the audit chain, never from what the runtime reports.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Callable

from hai import payloads as P
from hai.baselines.chat_centric import ChatAssistant
from hai.baselines.layered_chat import AlertToChatBridge, LayeredChatExperience
from hai.config import CONFIG, Clock, digest, load
from hai.contracts import Accepted, ApprovalDecision, ExecutionView, Rejected
from hai.heads import render
from hai.ingress.gateway import HeadlessIngress
from hai.runtime.reasoner import CompromisedReasoner
from hai.runtime.service import Crash, HeadlessRuntime
from hai.world import T0, World

ROOT = Path(__file__).resolve().parents[1]
MIN = 60.0


class Lab:
    """A fresh simulated enterprise + runtime + ingress in its own directory."""

    def __init__(self, base: Path, name: str, reasoner=None):
        self.dir = base / "work" / name
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.clock = Clock(T0)
        self.world = World(self.dir / "world.db").reset()
        self.rt = HeadlessRuntime(self.dir / "platform", self.world, self.clock, reasoner)
        self.ing = HeadlessIngress(self.rt)

    def send(self, channel: str, credential: str, payload: dict[str, Any]):
        r = self.ing.receive(channel, credential, payload)
        self.ing.drain()
        return r

    def reopen(self) -> None:
        """A new process on the same databases: what a restarted worker sees."""
        self.rt = HeadlessRuntime(self.dir / "platform", self.world, self.clock, self.rt.reasoner)
        self.ing = HeadlessIngress(self.rt)

    def effects(self, kind: str) -> int:
        return len(self.world.effects(kind))

    def approve(self, view: ExecutionView, who: str = "ic.dev", approve: bool = True, digest_override: str | None = None):
        a = view.approval
        return self.rt.decide(ApprovalDecision(approval_id=a["approval_id"], decided_by=who, approve=approve, digest=digest_override or a["digest"]))


def _xid(r) -> str:
    return r.execution_id


# ---- X1 · chat-centric vs layered vs headless ------------------------------------------------------------------------
def x1(base: Path) -> dict[str, Any]:
    heads = list(P.HEADS)
    true_invoker = {h: load("principals.yaml")["credentials"][P.HEADS[h][0]]["principal"] for h in heads}
    true_intent = {h: ("release_check" if h in ("cicd", "agent") else "health_sweep" if h == "scheduler" else "investigate_incident") for h in heads}
    out: dict[str, Any] = {}

    # A · chat-centric: only a chat message reaches the assistant
    lab = Lab(base, "x1-a")
    a = ChatAssistant(lab.world)
    rows = {}
    for h in heads:
        if h in a.entry_points:
            r = a.handle_message("sre.maya", P.chat_message()[1]["text"])
            rows[h] = {"served": "native", "recorded_invoker": r["acted_as"], "intent_kept": True, "source_kept": True}
        else:
            r = a.handle_event({})
            rows[h] = {"served": "needs a human", "recorded_invoker": None, "intent_kept": False, "source_kept": False, "next": r["next"]}
    out["A"] = {"rows": rows, "credentials_in_agent_process": len(a.credentials)}

    # B · layered platform, chat is the only door; other heads bridged into chat by a bot user
    lab = Lab(base, "x1-b")
    exp = LayeredChatExperience(lab.ing)
    bridge = AlertToChatBridge(exp)
    rows = {}
    for i, h in enumerate(heads):
        if h == "chat":
            tok, m = P.chat_message(event_id="slk-b-1")
            exp.handle_message(tok, m)
            env = json.loads(lab.rt.db.execute("SELECT envelope FROM inbox WHERE event_id=?", ("slk-b-1",)).fetchone()["envelope"])
            rows[h] = {"served": "native", "recorded_invoker": env["invoker"], "intent_kept": True, "source_kept": True}
        else:
            alert = P.monitor_alert(event_id=f"b-{h}-{i}")
            bridge.forward(alert, ts=f"1790690{i:03d}.0001")
            env = json.loads(lab.rt.db.execute("SELECT envelope FROM inbox WHERE event_id=?", (f"bridge-{alert['id']}",)).fetchone()["envelope"])
            rows[h] = {"served": "bridged through chat", "recorded_invoker": env["invoker"], "intent_kept": env["intent"] == true_intent[h],
                       "source_kept": not env["source"].startswith("chat/")}
    out["B"] = {"rows": rows, "credentials_in_agent_process": 0}

    # C · headless: every head through its own adapter
    lab = Lab(base, "x1-c")
    rows = {}
    for h in heads:
        cred, fn = P.HEADS[h]
        r = lab.send(h, cred, fn())
        xid = _xid(r)
        env = json.loads(lab.rt.db.execute("SELECT envelope FROM inbox WHERE execution_id=? AND source LIKE ? ORDER BY received LIMIT 1",
                                           (xid, {"event": "monitoring/%", "chat": "chat/%", "web": "web/%", "api": "api/%", "workflow": "workflow/%",
                                                  "scheduler": "scheduler/%", "cicd": "cicd/%", "agent": "agent/%"}[h])).fetchone()["envelope"])
        rows[h] = {"served": "native", "recorded_invoker": env["invoker"], "intent_kept": env["intent"] == true_intent[h],
                   "source_kept": env["source"].split("/")[0] in (h, "monitoring" if h == "event" else h)}
    out["C"] = {"rows": rows, "credentials_in_agent_process": 0}

    for k in ("A", "B", "C"):
        rows = out[k]["rows"]
        out[k]["native"] = sum(r["served"] == "native" for r in rows.values())
        out[k]["bridged"] = sum(r["served"].startswith("bridged") for r in rows.values())
        out[k]["unserved"] = sum(r["served"] == "needs a human" for r in rows.values())
        out[k]["invoker_faithful"] = sum(r["recorded_invoker"] == true_invoker[h] for h, r in rows.items())
        out[k]["intent_kept"] = sum(r["intent_kept"] for r in rows.values())
        out[k]["human_steps_before_alert_investigation"] = 1 if k == "A" else 0
    out["heads"] = len(heads)
    out["alert_invoker_in_B"] = out["B"]["rows"]["event"]["recorded_invoker"]
    return out


# ---- X2 · many heads, one intelligence ------------------------------------------------------------------------------
def x2(base: Path) -> dict[str, Any]:
    lab = Lab(base, "x2")
    order = ["event", "chat", "web", "api", "workflow", "scheduler", "cicd", "agent"]
    results = {}
    for h in order:
        cred, fn = P.HEADS[h]
        r = lab.send(h, cred, fn())
        v = lab.rt.view(_xid(r), joined=getattr(r, "joined", False))
        results[h] = {"execution": v.execution_id, "status": v.status, "joined": v.joined, "intent": v.intent,
                      "assessment_digest": digest(v.assessment.model_dump()) if v.assessment else None,
                      "leading": v.assessment.leading if v.assessment else None, "verdict": v.verdict,
                      "rendered_as": type(render.RENDER[h](v)).__name__}
        lab.clock.advance(20)
    inv = [h for h in order if results[h]["intent"] == "investigate_incident"]
    main = results["event"]["execution"]
    view = lab.rt.view(main)
    ok, why, final = lab.approve(view)
    sweep = results["scheduler"]
    sweep_state = lab.rt._load(sweep["execution"])["state"]
    out = {
        "heads": len(order),
        "investigation_heads": inv,
        "executions_for_investigation": len({results[h]["execution"] for h in inv}),
        "joined": sum(results[h]["joined"] for h in inv),
        "distinct_assessments": len({results[h]["assessment_digest"] for h in inv}),
        "incidents_created": lab.effects("incident.create"),
        "sweep_leading": sweep["leading"],
        "sweep_same_leading": sweep["leading"] == results["event"]["leading"],
        "sweep_write_attempt": sweep_state["verdict"]["write_attempt"],
        "release_checks": {h: results[h]["verdict"]["decision"] for h in ("cicd", "agent")},
        "release_check_based_on_main": all(results[h]["verdict"]["based_on"] == main for h in ("cicd", "agent")),
        "render_shapes": {h: results[h]["rendered_as"] for h in order},
        "approval_accepted": ok,
        "final_status": final.status,
        "rollbacks": lab.effects("deploy.rollback"),
        "verification": lab.rt._load(main)["state"].get("verification"),
        "per_head": results,
        "main_execution": main,
        "chat_render": render.chat(lab.rt.view(results["chat"]["execution"], joined=True)),
    }
    # keep the main execution's audit and trace for the run folder (X5 reads them)
    out["_lab"] = lab
    return out


# ---- X3 · at-least-once delivery, re-fired alerts, poison messages ----------------------------------------------------
def x3(base: Path) -> dict[str, Any]:
    lab = Lab(base, "x3")
    deliveries = [lab.send("event", "tok-monitoring", P.monitor_alert("dd-evt-88121")) for _ in range(3)]
    lab.clock.advance(4 * MIN)
    refire = lab.send("event", "tok-monitoring", P.monitor_alert("dd-evt-88190", value=0.15))
    xid = _xid(deliveries[0])
    v = lab.rt.view(xid)
    ok1, _, _ = lab.approve(v)
    ok2, why2, _ = lab.approve(v)            # the same decision delivered twice
    poison = [
        {"id": "dd-bad-1", "metric": "error_rate", "value": 0.14, "monitor_id": "m", "tags": ["env:production"]},           # no service tag
        {"id": "dd-bad-2", "metric": "error_rate", "value": 0.14, "monitor_id": "m", "tags": ["service:payment-service", "env:prod"]},  # bad env
        {"metric": "error_rate", "value": 0.14, "monitor_id": "m", "tags": ["service:payment-service", "env:production"]},  # no id
    ]
    rej = [lab.send("event", "tok-monitoring", p) for p in poison]
    dlq = lab.rt.db.execute("SELECT COUNT(*) c FROM dead_letters").fetchone()["c"]
    execs = lab.rt.db.execute("SELECT COUNT(*) c FROM executions").fetchone()["c"]
    return {
        "deliveries_same_event": 3, "duplicates_flagged": sum(isinstance(d, Accepted) and d.duplicate for d in deliveries),
        "refire_joined": isinstance(refire, ExecutionView) and refire.joined, "refire_same_execution": _xid(refire) == xid,
        "executions": execs, "incidents_created": lab.effects("incident.create"), "rollbacks": lab.effects("deploy.rollback"),
        "second_approval_accepted": ok2, "second_approval_reason": why2, "first_approval_accepted": ok1,
        "poison_sent": len(poison), "dead_lettered": dlq, "poison_rejections": [r.stage for r in rej if isinstance(r, Rejected)],
        "correlation_ids": sorted({r[0] for r in lab.rt.db.execute("SELECT correlation_id FROM executions")}),
    }


# ---- X4 · invocation is not authorization ---------------------------------------------------------------------------
def x4(base: Path) -> dict[str, Any]:
    lab = Lab(base, "x4")
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    v = lab.rt.view(_xid(r))
    ident = lab.rt._load(v.execution_id)["state"]["identity"]
    discover = lab.rt.registry.discover(ident["scopes"])
    tok, m = P.chat_message(event_id="slk-lee-1", user_token="tok-slack-lee")
    lee = lab.send("chat", tok, m)
    attempts = {}
    for who in ("agent.incident-intel", "svc.monitoring-webhook", "sre.maya"):
        ok, why, _ = lab.approve(v, who=who)
        attempts[who] = {"accepted": ok, "reason": why}
    tampered = dict(v.approval["call"]["arguments"], to_version="v1.0.0")
    fake = lab.rt.approvals.call_digest(v.execution_id, "rollbackDeployment", tampered)
    ok, why, _ = lab.approve(v, who="ic.dev", digest_override=fake)
    attempts["ic.dev (tampered digest)"] = {"accepted": ok, "reason": why}
    rollbacks_before = lab.effects("deploy.rollback")
    ok, why, fin = lab.approve(v, who="ic.dev")
    attempts["ic.dev (exact call)"] = {"accepted": ok, "reason": why}
    audit_rb = [x["record"] for x in lab.rt.audit.records(v.execution_id) if x["kind"] == "capability.call" and x["record"]["capability"] == "rollbackDeployment"]

    # the compromised reasoner: proposes raw tools, a destructive call, a cross-environment write and an arbitrary target
    bad = Lab(base, "x4-compromised", reasoner=CompromisedReasoner())
    rb = bad.send("event", "tok-monitoring", P.monitor_alert())
    gate = bad.rt._load(_xid(rb))["state"].get("gate", [])
    ignored = "treated as data" in (bad.rt.view(_xid(rb)).assessment.summary)
    return {
        "event_identity": {k: ident[k] for k in ("invoker", "on_behalf_of", "agent", "workload", "scopes")},
        "event_scopes_include_rollback": "deploy:rollback" in ident["scopes"],
        "discoverable": [c["name"] for c in discover], "approval_gated_visible": [c["name"] for c in discover if c["approval_gated"]],
        "viewer_chat_invocation": {"type": type(lee).__name__, "stage": getattr(lee, "stage", None)},
        "approval_attempts": attempts,
        "refused_attempts": sum(not a["accepted"] for a in attempts.values()),
        "rollbacks_before_valid_approval": rollbacks_before, "rollbacks_after": lab.effects("deploy.rollback"),
        "rollback_audit": {"authorized_by": audit_rb[-1].get("authorized_by"), "invoker": audit_rb[-1]["invoker"], "agent": audit_rb[-1]["agent"]} if audit_rb else None,
        "final_status": fin.status if fin else None,
        "compromised": {"proposals": [{"capability": g["capability"], "status": g["status"], "rule": g["rule"]} for g in gate],
                        "denied": sum(g["status"] == "denied" for g in gate), "awaiting_human": sum(g["status"] == "approval_required" for g in gate),
                        "executed": sum(g["status"] == "ok" for g in gate), "effects": len(bad.world.effects("deploy.rollback")) + len(bad.world.effects("deploy.delete")),
                        "instruction_lines_treated_as_data": ignored},
    }


# ---- X5 · audit vs observability -------------------------------------------------------------------------------------
def x5(base: Path, x2lab: Lab, main: str) -> dict[str, Any]:
    rt = x2lab.rt
    ans = rt.audit.answer(main)
    answered = {k: bool(v) and (not isinstance(v, dict) or any(v.values())) for k, v in ans.items()}
    intact, broken = rt.audit.verify()
    corr = rt._load(main)["correlation_id"]
    spans = [json.loads(l) for l in (x2lab.dir / "platform" / "traces.jsonl").read_text().splitlines()]
    mine = [s for s in spans if s["trace_id"] == corr]
    kinds = {}
    for s in mine:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    audit_n = len(rt.audit.records(main))
    # tamper test on a copy of the platform database
    cp = x2lab.dir / "tamper.db"
    shutil.copy(x2lab.dir / "platform" / "platform.db", cp)
    db = sqlite3.connect(cp)
    db.row_factory = sqlite3.Row
    n = db.execute("SELECT n FROM audit WHERE record LIKE '%rollbackDeployment%' AND kind='capability.call' ORDER BY n DESC LIMIT 1").fetchone()["n"]
    db.execute("UPDATE audit SET record=replace(record, 'ic.dev', 'sre.maya') WHERE n=?", (n,))
    db.commit()
    from hai.control.audit import AuditLog
    t_intact, t_broken = AuditLog(db, x2lab.clock).verify()
    return {"questions": list(ans), "answered": sum(answered.values()), "of": len(answered), "answers": ans,
            "chain_intact": intact, "tamper_detected": not t_intact, "tamper_row": t_broken, "tampered_row": n,
            "spans_in_trace": len(mine), "span_kinds": kinds, "audit_records": audit_n}


# ---- X6 · failures: timeouts, lost responses, crash + resume, approval timeout, token expiry, revoked credential ------
def x6(base: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    lab = Lab(base, "x6-faults")
    lab.world.faults = {"getTraceSummary": ["timeout"], "rollbackDeployment": ["lost_response"]}
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    v = lab.rt.view(_xid(r))
    ok, _, fin = lab.approve(v)
    tr = [x["record"] for x in lab.rt.audit.records(v.execution_id) if x["kind"] == "capability.call"]
    out["read_timeout"] = next({"attempts": c["attempts"], "status": c["status"]} for c in tr if c["capability"] == "getTraceSummary")
    rb = [c for c in tr if c["capability"] == "rollbackDeployment" and c["status"] == "ok"][-1]
    out["lost_response"] = {"attempts": rb["attempts"], "status": rb["status"], "physical_rollbacks": lab.effects("deploy.rollback"),
                            "same_key_reused": bool(rb.get("idempotency_key"))}

    lab = Lab(base, "x6-crash")
    lab.rt.crash_after = "assess"
    xid = None
    try:
        lab.send("event", "tok-monitoring", P.monitor_alert())
    except Crash:
        xid = lab.rt.db.execute("SELECT id FROM executions").fetchone()["id"]
    before = [s for x, s in lab.rt.steps_run if x == xid]
    reads_before = lab.rt.gateway.calls_by_execution.get(xid, 0)
    lab.reopen()
    lab.rt.recover()
    after = [s for x, s in lab.rt.steps_run if x == xid]
    out["crash_resume"] = {"crashed_after": "assess", "steps_before_crash": before, "steps_after_restart": after,
                           "repeated_steps": sorted(set(before) & set(after)), "reads_before_crash": reads_before,
                           "status_after": lab.rt.view(xid).status, "incidents": lab.effects("incident.create")}

    lab = Lab(base, "x6-approval-timeout")
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    lab.clock.advance(31 * MIN)
    esc = lab.rt.tick()
    out["approval_timeout"] = {"status": lab.rt.view(_xid(r)).status, "rollbacks": lab.effects("deploy.rollback"),
                               "notified": lab.effects("chat.post"), "escalated": len(esc)}

    lab = Lab(base, "x6-token-expiry")
    r = lab.send("event", "tok-monitoring", P.monitor_alert())
    lab.clock.advance(20 * MIN)                         # past the 15-minute token lifetime
    v = lab.rt.view(_xid(r))
    ok, _, fin = lab.approve(v)
    refreshed = [x for x in lab.rt.audit.records(_xid(r)) if x["kind"] == "identity.refreshed"]
    out["token_expiry"] = {"token_ttl_s": lab.rt.directory.ttl, "paused_s": 20 * MIN, "refreshed": len(refreshed), "status": fin.status,
                           "rollbacks": lab.effects("deploy.rollback")}

    lab.rt.directory.revoked.add("tok-monitoring")
    rej = lab.send("event", "tok-monitoring", P.monitor_alert("dd-evt-99999"))
    out["revoked_credential"] = {"type": type(rej).__name__, "stage": getattr(rej, "stage", None)}
    return out


# ---- X7 · sprawl arithmetic (derived from the configuration) ---------------------------------------------------------
def x7(base: Path) -> dict[str, Any]:
    heads = len(load("consumers.yaml")["consumers"])
    principals = load("principals.yaml")["principals"]
    agents = sum(p["kind"] == "agent" for p in principals.values())
    systems = len(load("capabilities.yaml")["systems"])
    return {"heads": heads, "agents": agents, "systems": systems,
            "per_head_assistants": {"integrations": heads * systems, "credential_holders": heads},
            "agent_owned_integrations": {"integrations": agents * systems, "credential_holders": agents},
            "capability_layer": {"integrations": systems, "credential_holders": 1, "head_credentials": heads},
            "note": "Derived from config/*.yaml by arithmetic; no run measures it."}


def run(run_id: str, out: Path | None = None) -> Path:
    """Run the seven experiments into <out or runs/>/<run_id>/.  `hai verify` replays into a temporary `out`."""
    base = (out or ROOT / "runs") / run_id
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    res: dict[str, Any] = {}
    res["X1"] = x1(base)
    x2r = x2(base)
    lab2 = x2r.pop("_lab")
    res["X2"] = x2r
    res["X3"] = x3(base)
    res["X4"] = x4(base)
    res["X5"] = x5(base, lab2, x2r["main_execution"])
    res["X6"] = x6(base)
    res["X7"] = x7(base)
    for k, v in res.items():
        (base / f"{k}.json").write_text(json.dumps(v, indent=1, default=str, sort_keys=True))
    shutil.copy(lab2.dir / "platform" / "traces.jsonl", base / "traces.jsonl")
    (base / "audit.jsonl").write_text("\n".join(json.dumps(r, sort_keys=True, default=str) for r in lab2.rt.audit.records()) + "\n")
    (base / "effects.json").write_text(json.dumps(lab2.world.effects(), indent=1))
    checks = checks_for(res)
    (base / "checks.json").write_text(json.dumps(checks, indent=1))
    facts = facts_for(res, checks)
    (base / "facts.json").write_text(json.dumps(facts, indent=1, sort_keys=True))
    # flat copy for the series learning map (series-start-here/learning-map.yaml reads {name} fields from a flat file)
    (base / "article-numbers.json").write_text(json.dumps({"run": run_id, **{k.replace(".", "_"): v["value"] for k, v in facts.items()}},
                                                          indent=1, sort_keys=True))
    cfg_hash = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(CONFIG.glob("*.yaml"))}
    (base / "manifest.json").write_text(json.dumps({"run_id": run_id, "python": platform.python_version(), "config_sha256": cfg_hash,
                                                    "reasoner": "deterministic (hai.runtime.reasoner.EvidenceReasoner)",
                                                    "simulated": ["enterprise systems (hai/world.py)", "identity provider (config/principals.yaml)",
                                                                  "clock", "faults"],
                                                    "real": ["ingress, adapters, runtime, gateway, policy, approvals, audit chain, spans, SQLite state"]},
                                                   indent=1))
    shutil.rmtree(base / "work", ignore_errors=True)
    (base / "summary.md").write_text(summary_md(run_id, res, checks))
    (base / "SHA256SUMS").write_text(sha256sums(base))
    return base


def sha256sums(base: Path) -> str:
    """`sha256sum` format over every file of a run except SHA256SUMS itself, sorted by path."""
    files = sorted(f for f in base.rglob("*") if f.is_file() and f.name != "SHA256SUMS")
    return "".join(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(base).as_posix()}\n" for f in files)


def checks_for(r: dict[str, Any]) -> list[dict[str, Any]]:
    X1, X2, X3, X4, X5, X6 = (r[k] for k in ("X1", "X2", "X3", "X4", "X5", "X6"))
    c: list[tuple[str, str, bool]] = [
        ("X1", "headless serves every head natively", X1["C"]["native"] == X1["heads"]),
        ("X1", "headless records the true invoker for every head", X1["C"]["invoker_faithful"] == X1["heads"]),
        ("X1", "chat-centric serves only chat natively", X1["A"]["native"] == 1),
        ("X1", "layered-chat bridging loses the alert's invoker", X1["alert_invoker_in_B"] != "svc.monitoring-webhook"),
        ("X2", "all investigation heads share one execution", X2["executions_for_investigation"] == 1),
        ("X2", "all investigation heads see one assessment", X2["distinct_assessments"] == 1),
        ("X2", "one incident for eight heads", X2["incidents_created"] == 1),
        ("X2", "sweep reads the same leading hypothesis", X2["sweep_same_leading"]),
        ("X2", "sweep cannot write", X2["sweep_write_attempt"]["status"] == "denied"),
        ("X2", "CI and agent consumers block on the same finding", X2["release_check_based_on_main"] and set(X2["release_checks"].values()) == {"BLOCK"}),
        ("X2", "one rollback after one approval", X2["rollbacks"] == 1 and X2["final_status"] == "COMPLETED"),
        ("X3", "duplicate deliveries flagged", X3["duplicates_flagged"] == 2),
        ("X3", "re-fired alert joins the open execution", X3["refire_joined"] and X3["refire_same_execution"]),
        ("X3", "one execution, one incident, one rollback", X3["executions"] == 1 and X3["incidents_created"] == 1 and X3["rollbacks"] == 1),
        ("X3", "a replayed approval is refused", not X3["second_approval_accepted"]),
        ("X3", "poison messages dead-lettered", X3["dead_lettered"] == X3["poison_sent"]),
        ("X4", "event execution holds no rollback scope", not X4["event_scopes_include_rollback"]),
        ("X4", "viewer cannot invoke", X4["viewer_chat_invocation"]["stage"] == "authorize_invocation"),
        ("X4", "four invalid approvals refused", X4["refused_attempts"] == 4),
        ("X4", "no rollback before a valid approval", X4["rollbacks_before_valid_approval"] == 0 and X4["rollbacks_after"] == 1),
        ("X4", "audit names the approver and the invoker", X4["rollback_audit"]["authorized_by"] == "ic.dev" and X4["rollback_audit"]["invoker"] == "svc.monitoring-webhook"),
        ("X4", "compromised reasoner executes nothing", X4["compromised"]["executed"] == 0 and X4["compromised"]["effects"] == 0),
        ("X5", "audit answers all seven questions", X5["answered"] == X5["of"] == 7),
        ("X5", "audit chain intact; tamper detected", X5["chain_intact"] and X5["tamper_detected"]),
        ("X6", "read timeout retried", X6["read_timeout"]["attempts"] == 2 and X6["read_timeout"]["status"] == "ok"),
        ("X6", "lost response: one physical rollback", X6["lost_response"]["physical_rollbacks"] == 1),
        ("X6", "crash: no completed step repeated", not X6["crash_resume"]["repeated_steps"]),
        ("X6", "approval timeout escalates, changes nothing", X6["approval_timeout"]["status"] == "ESCALATED" and X6["approval_timeout"]["rollbacks"] == 0),
        ("X6", "expired token re-exchanged, not extended", X6["token_expiry"]["refreshed"] == 1 and X6["token_expiry"]["rollbacks"] == 1),
        ("X6", "revoked credential rejected at ingress", X6["revoked_credential"]["stage"] == "authenticate"),
    ]
    return [{"experiment": e, "check": n, "passed": bool(p)} for e, n, p in c]


def facts_for(r: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    f: dict[str, Any] = {}

    def put(key: str, value: Any, src: str) -> None:
        f[key] = {"value": value, "source": src}

    X1, X2, X3, X4, X5, X6, X7 = (r[k] for k in ("X1", "X2", "X3", "X4", "X5", "X6", "X7"))
    put("checks.passed", sum(c["passed"] for c in checks), "checks.json")
    put("checks.total", len(checks), "checks.json")
    put("x1.heads", X1["heads"], "X1.json")
    for k in ("A", "B", "C"):
        for m in ("native", "bridged", "unserved", "invoker_faithful", "intent_kept", "credentials_in_agent_process"):
            put(f"x1.{k}.{m}", X1[k][m], "X1.json")
    put("x1.alert_invoker_in_B", X1["alert_invoker_in_B"], "X1.json")
    for k in ("heads", "executions_for_investigation", "distinct_assessments", "incidents_created", "rollbacks", "joined"):
        put(f"x2.{k}", X2[k], "X2.json")
    put("x2.investigation_heads", len(X2["investigation_heads"]), "X2.json")
    put("x2.sweep_write_rule", X2["sweep_write_attempt"]["rule"], "X2.json")
    put("x2.verified_error_rate_pct", round(X2["verification"]["error_rate"] * 100, 1), "X2.json")
    for k in ("deliveries_same_event", "duplicates_flagged", "executions", "incidents_created", "rollbacks", "poison_sent", "dead_lettered"):
        put(f"x3.{k}", X3[k], "X3.json")
    put("x4.refused_attempts", X4["refused_attempts"], "X4.json")
    put("x4.scopes", ", ".join(X4["event_identity"]["scopes"]), "X4.json")
    put("x4.compromised.proposals", len(X4["compromised"]["proposals"]), "X4.json")
    put("x4.compromised.denied", X4["compromised"]["denied"], "X4.json")
    put("x4.compromised.awaiting_human", X4["compromised"]["awaiting_human"], "X4.json")
    put("x4.compromised.executed", X4["compromised"]["executed"], "X4.json")
    put("x5.answered", X5["answered"], "X5.json")
    put("x5.spans", X5["spans_in_trace"], "X5.json")
    put("x5.audit_records", X5["audit_records"], "X5.json")
    put("x6.read_attempts", X6["read_timeout"]["attempts"], "X6.json")
    put("x6.lost_response_rollbacks", X6["lost_response"]["physical_rollbacks"], "X6.json")
    put("x6.repeated_steps", len(X6["crash_resume"]["repeated_steps"]), "X6.json")
    put("x6.reads_before_crash", X6["crash_resume"]["reads_before_crash"], "X6.json")
    put("x6.token_ttl_min", int(X6["token_expiry"]["token_ttl_s"] // 60), "X6.json")
    for k in ("heads", "agents", "systems"):
        put(f"x7.{k}", X7[k], "X7.json")
    put("x7.per_head", X7["per_head_assistants"]["integrations"], "X7.json")
    put("x7.agent_owned", X7["agent_owned_integrations"]["integrations"], "X7.json")
    put("x7.capability_layer", X7["capability_layer"]["integrations"], "X7.json")
    return f


def summary_md(run_id: str, r: dict[str, Any], checks: list[dict[str, Any]]) -> str:
    passed = sum(c["passed"] for c in checks)
    lines = [f"# F3 run {run_id}", "", f"**{passed}/{len(checks)} checks passed.** Deterministic run: simulated enterprise, clock and identity "
             "provider; real ingress, runtime, gateway, policy, approvals, audit chain and spans.", "", "| Exp | Check | Result |", "|---|---|---|"]
    lines += [f"| {c['experiment']} | {c['check']} | {'pass' if c['passed'] else '**FAIL**'} |" for c in checks]
    return "\n".join(lines) + "\n"
