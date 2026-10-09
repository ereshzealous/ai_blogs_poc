"""Ground truth for the thirteen reconstruction questions, about the target execution (INC-4471's rollback).

Taken only from systems of record and the scenario definition, never from the layers under test:
  * the deployment API's own database: every request that reached it, every revision it created (side effects);
  * the approval service's database: every request and signed decision;
  * the scenario pins (trigger, delegation, agent version, agent configuration, policy version);
  * the model server's reported digest for the pinned model (recorded on the tape from GET /api/tags);
  * the harness's own knowledge that nobody tampered with the evidence in this run.

Q1  What triggered the execution?                 Q8  Which exact capability/action reached production?
Q2  Which principal initiated it?                 Q9  How many attempts reached the production API?
Q3  Which agent/runtime acted?                    Q10 Did the external side effect occur?
Q4  Which model/configuration was used?           Q11 How many times did production change?
Q5  Which policy/version evaluated it?            Q12 Was the incident actually mitigated?
Q6  Was approval required?                        Q13 Can the evidence's integrity be verified?
Q7  Who approved/rejected it?
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .common import jl, load
from .model import config

WORLD = load("world.toml")
CP = load("control_plane.toml")
QUESTIONS = {
    "Q1": "What triggered the execution?", "Q2": "Which principal initiated it?", "Q3": "Which agent and version acted?",
    "Q4": "Which model and configuration produced the proposal?", "Q5": "Which policy and version evaluated it?",
    "Q6": "Was approval required?", "Q7": "Who approved or rejected it?", "Q8": "Which capability and arguments reached production?",
    "Q9": "How many attempts reached the production API?", "Q10": "Did the side effect occur?",
    "Q11": "How many times did production change?", "Q12": "Was the incident actually mitigated?",
    "Q13": "Can the evidence's integrity be verified?",
}


def model_digest_from_tape(sdir: Path, model: str) -> str | None:
    for r in jl(sdir / "tape" / "target" / "model_tape.jsonl"):
        if r.get("path") == "/api/tags" or '"models"' in r["response"][:20]:
            for m in json.loads(r["response"]).get("models", []):
                if m.get("name") == model:
                    return "sha256:" + m["digest"]
    return None


def truth(sdir: Path, spec: dict, after: dict, rows: list[dict]) -> dict:
    inc = WORLD["incident"]
    x = spec["executions"]["target"]
    svc = inc["service"]
    cfg = config(x["agent_config"])
    reqs = [r for r in after["requests"] if r["service"] == svc and r["method"] == "POST"]
    revs = [r for r in after["revisions"] if r["service"] == svc and r["txn_id"]]
    final = next(d for d in after["deployments"] if d["service"] == svc)
    bad = next(d for d in WORLD["deployments"] if d["service"] == svc)["bad_versions"]
    db = sqlite3.connect(sdir / "state" / "approvals.db")
    req = db.execute("SELECT approval_id FROM requests WHERE incident=?", (inc["id"],)).fetchall()
    decs = db.execute("SELECT approver, decision FROM decisions WHERE approval_id IN (SELECT approval_id FROM requests WHERE incident=?) ORDER BY approver",
                      (inc["id"],)).fetchall()
    db.close()
    first = json.loads(reqs[0]["body"]) if reqs else None
    completed = [json.loads(r["payload_json"]) for r in rows if r["event_type"] == "execution.completed" and not json.loads(r["payload_json"]).get("background")
                 and r["execution_id"] == next((e["execution_id"] for e in rows if e["event_type"] == "execution.started" and not json.loads(e["payload_json"])["background"]), None)]
    pid, pver = x["policy"].split("@")
    t = {
        "Q1": {"source": inc["source"], "alert_id": inc["alert_id"]},
        "Q2": {"invoker": inc["source"], "on_behalf_of": inc["on_behalf_of"]},
        "Q3": {"agent": CP["agent"]["id"], "version": CP["agent"]["version"]},
        "Q4": {"model": cfg["model"], "model_digest": model_digest_from_tape(sdir, cfg["model"]), "prompt_template": cfg["prompt_template"],
               "agent_config": x["agent_config"]},
        "Q5": {"policy": pid, "version": int(pver)},
        "Q6": bool(req),
        "Q7": [list(d) for d in decs] or None,
        "Q8": {"capability": "deployment.rollback", "service": svc, "to_version": first["to_version"]} if first else None,
        "Q9": len(reqs),
        "Q10": len(revs) > 0,
        "Q11": len(revs),
        "Q12": final["version"] not in bad,
        "Q13": True,
    }
    out = {q: {"question": QUESTIONS[q], "value": v} for q, v in t.items()}
    out["Q12"]["detail"] = {"final_version": final["version"], "final_revision": final["revision"],
                            "recorded_outcome": completed[0]["outcome"] if completed else "NONE"}
    out["Q11"]["detail"] = {"revisions_created": [{"revision": r["revision"], "version": r["version"], "txn_id": r["txn_id"]} for r in revs]}
    out["Q9"]["detail"] = {"requests": [{"n": r["n"], "request_id": r["request_id"], "idempotency_key": r["idempotency_key"], "outcome": r["outcome"],
                                         "response_delivered": r["response_delivered"], "fault": r["fault"]} for r in reqs]}
    return out
