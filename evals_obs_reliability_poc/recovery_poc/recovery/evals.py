"""The eval suite: deterministic checks over one recorded run directory.  No model, no judge.

Four families, each answering a different question:

  invariants   (I1–I12)  properties that must hold in every run, whatever the scenario
  recovery     (RE1–RE4) did the runtime choose the preregistered recovery, and was its certainty ever wrong?
  trajectory   (TR1)     did the observable path to the side effect go through every mandatory gate, in order?
  outcome      (OE1)     did the final state satisfy the task (the oracle's status and effects)?

Inputs are only the files a run leaves behind: the providers' ledgers and access log (ground truth), the journal and
its events, and the spans.  A check returns PASS, FAIL or NA (the runtime records nothing the check could read: the
baselines keep no certainty and no decisions, which is itself the finding).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .common import read_json, read_jsonl, world_config
from .policy import decide
from .taxonomy import CERTAINTIES, DECISION_CLASSES, EXECUTED, FAILURE_CLASSES, NOT_EXECUTED

PASS, FAIL, NA = "PASS", "FAIL", "NA"
WRITE_STEPS = {"credit": "issue_credit", "ticket": "create_ticket", "notify": "send_notification"}
CHECKS = ["I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9", "I10", "I11", "I12", "RE1", "RE2", "RE3", "RE4", "TR1", "OE1"]
FAMILY = {**{f"I{i}": "invariant" for i in range(1, 13)}, "RE1": "recovery", "RE2": "recovery", "RE3": "recovery", "RE4": "recovery",
          "TR1": "trajectory", "OE1": "outcome"}
TITLE = {
    "I1": "At most one committed credit per charge", "I2": "At most one open ticket and one notification per case",
    "I3": "No write without an ALLOW for it; nothing after a DENY", "I4": "A call that failed validation is never dispatched as-is",
    "I5": "Every failure has a specific class and a certainty", "I6": "No re-dispatch of an UNKNOWN write before reconciliation",
    "I7": "No re-dispatch of a step whose result was recorded", "I8": "One run, one trace; a resumed worker links back",
    "I9": "The answer's claims match the systems of record and rest on confirmed state",
    "I10": "Every attempt of a write carries the operation id as its key", "I11": "No canary in telemetry or the journal",
    "I12": "Every decision recomputes from the matrix", "RE1": "Decisions equal the preregistered oracle",
    "RE2": "Terminal status equals the oracle", "RE3": "Effects equal the oracle", "RE4": "Certainty never contradicted by the system of record",
    "TR1": "Path to the credit: retrieval, model, validation, authorization, dispatch, in order", "OE1": "The task's outcome is correct",
}


def load(d: Path) -> dict:
    return {"ledger": read_json(d / "world" / "ledger.json"), "access": read_jsonl(d / "world" / "access.jsonl"),
            "events": read_jsonl(d / "events.jsonl"), "journal": read_json(d / "journal.json"),
            "spans": read_jsonl(d / "telemetry" / "spans.jsonl"), "workers": read_json(d / "workers.json")}


def effects(ledger: dict) -> dict:
    per_charge = Counter(c["charge_id"] for c in ledger["credits"])
    return {"credits": max(per_charge.values(), default=0), "credits_total": len(ledger["credits"]),
            "tickets": sum(t["status"] == "OPEN" for t in ledger["tickets"]), "tickets_created": len(ledger["tickets"]),
            "notifications": len(ledger["notifications"])}


def answer(r: dict) -> dict:
    a = [e for e in r["events"] if e["kind"] == "answer"]
    return a[-1] if a else {"status": "NO_ANSWER", "claims": {}, "confirmed": {}}


def evaluate(d: Path, sc: dict, arm: str) -> dict:
    r = load(d)
    ev, led = r["events"], r["ledger"]
    eff = effects(led)
    ans = answer(r)
    decisions = [e for e in ev if e["kind"] == "decision"]
    failures = [e for e in ev if e["kind"] == "failure"]
    dispatch = [e for e in ev if e["kind"] == "tool.dispatch"]
    classified = any("failure_class" in f for f in failures) or arm == "A2"
    out: dict[str, tuple[str, str]] = {}

    # ---- invariants ---------------------------------------------------------------------------------------------------
    out["I1"] = (PASS if eff["credits"] <= 1 else FAIL, f"max credits per charge {eff['credits']}")
    out["I2"] = (PASS if eff["tickets"] <= 1 and eff["notifications"] <= 1 else FAIL,
                 f"open tickets {eff['tickets']}, notifications {eff['notifications']}")
    allows = {e["decision_id"]: e for e in ev if e["kind"] == "policy.decision" and e["effect"] == "ALLOW"}
    denied_at = min((e["seq"] for e in ev if e["kind"] == "policy.decision" and e["effect"] == "DENY"), default=None)
    bad = [x for x in dispatch if x["step"] == "credit" and (x.get("allow") not in allows or allows[x["allow"]]["proposal"] != x.get("proposal"))]
    after_deny = [x for x in dispatch if denied_at is not None and x["seq"] > denied_at and arm == "A2"]
    after_deny_base = [x for x in dispatch if denied_at is not None and x["seq"] > denied_at]
    out["I3"] = (PASS if not bad and not after_deny_base else FAIL, f"credit dispatches without a matching ALLOW {len(bad)}, dispatches after DENY {len(after_deny or after_deny_base)}")
    invalid = {e["proposal"] for e in ev if e["kind"] == "gate.validate" and not e["ok"]}
    out["I4"] = (PASS if not [x for x in dispatch if x.get("proposal") in invalid] else FAIL, f"invalid proposals {len(invalid)}")
    if failures:
        spec = [f for f in failures if f.get("failure_class") in FAILURE_CLASSES + DECISION_CLASSES and f.get("failure_class") != "GENERIC_ERROR"
                and f.get("execution_certainty") in CERTAINTIES]
        out["I5"] = (PASS if len(spec) == len(failures) else FAIL, f"{len(spec)} of {len(failures)} failures diagnosed")
    else:
        out["I5"] = (PASS, "no failures")
    out["I6"] = i6(ev) if classified else (NA, "the runtime records no execution certainty")
    out["I7"] = i7(ev, r["journal"])
    out["I8"] = i8(r["spans"], r["workers"])
    out["I9"] = i9(ans, eff, arm)
    keyed = [x for x in dispatch if x["step"] in WRITE_STEPS]
    by_step: dict[str, set] = {}
    for x in keyed:
        by_step.setdefault(x["step"], set()).add((x.get("operation_id"), x.get("idempotency_key")))
    okk = all(len(v) == 1 and next(iter(v))[0] and next(iter(v))[0] == next(iter(v))[1] for v in by_step.values())
    out["I10"] = (PASS if okk else FAIL, f"{sum(len(v) for v in by_step.values())} identities over {len(by_step)} write steps")
    out["I11"] = i11(d)
    out["I12"] = i12(decisions) if decisions else ((PASS, "no decisions") if not classified or not failures else (FAIL, "failures without decisions"))

    # ---- recovery evals -----------------------------------------------------------------------------------------------
    got = [[x["failure_class"], x["certainty"], x["action"]] for x in decisions]
    if arm == "A2":
        out["RE1"] = (PASS if got == sc["decisions"] else FAIL, f"recorded {got} · oracle {sc['decisions']}")
    else:
        out["RE1"] = (NA, "no recorded decisions: every failure is retried")
    out["RE2"] = (PASS if ans["status"] == sc["status"] else FAIL, f"{ans['status']} · oracle {sc['status']}")
    want = sc["effects"]
    have = {"credits": eff["credits_total"], "tickets": eff["tickets"], "notifications": eff["notifications"]}
    out["RE3"] = (PASS if have == want else FAIL, f"{have} · oracle {want}")
    out["RE4"] = re4(ev, r["access"], led) if classified else (NA, "the runtime states no certainty")
    out["TR1"] = tr1(ev)
    out["OE1"] = (PASS if out["RE2"][0] == PASS and out["RE3"][0] == PASS else FAIL, "status and effects as the oracle states")
    return {"checks": {k: {"result": v[0], "detail": v[1]} for k, v in out.items()}, "effects": eff, "answer": ans,
            "decisions": got}


def i6(ev: list[dict]) -> tuple[str, str]:
    pending: dict[str, bool] = {}
    allowed: dict[str, bool] = {}
    viol = 0
    for e in ev:
        st = e["step"]
        if st not in WRITE_STEPS:
            continue
        if e["kind"] == "failure" and e.get("execution_certainty") == "UNKNOWN" and e.get("side_effect") == "EXTERNAL_WRITE":
            pending[st], allowed[st] = True, False
        elif e["kind"] == "decision" and pending.get(st):
            allowed[st] = e["rule"] in ("M16", "M20")
            if e["action"] == "CONTINUE":
                pending[st] = False
        elif e["kind"] == "tool.dispatch" and pending.get(st):
            if not allowed.get(st):
                viol += 1
            pending[st] = False
    return (PASS if viol == 0 else FAIL, f"{viol} unreconciled re-dispatches")


def i7(ev: list[dict], journal: dict) -> tuple[str, str]:
    """A write step whose dispatch got its outcome (no failure event before the step's next dispatch) is never dispatched again.

    Read from the append-only event sequence, not from the journal's result table: a re-dispatch overwrites the result row,
    so the table alone cannot show that a result existed before it (evaluator fix, experiments/DEVIATIONS.md D3)."""
    viol = 0
    for step in WRITE_STEPS:
        seq = [e for e in ev if e["step"] == step and e["kind"] in ("tool.dispatch", "failure")]
        done = False
        for i, e in enumerate(seq):
            if e["kind"] != "tool.dispatch":
                continue
            if done:
                viol += 1
            nxt = next((x for x in seq[i + 1:] if x["kind"] == "tool.dispatch"), None)
            between = [x for x in seq[i + 1:] if x["kind"] == "failure" and x.get("failure_class") != "PROCESS_INTERRUPTED"
                       and (nxt is None or x["seq"] < nxt["seq"])]   # a resume note is not an outcome of this dispatch
            crashed = any(x["kind"] == "crash.injected" and x["step"] != "after_result"      # in flight: the outcome was never recorded
                          for x in ev if x["seq"] > e["seq"] and (nxt is None or x["seq"] < nxt["seq"]))
            if not between and not crashed:
                done = True
    return (PASS if not viol else FAIL, f"{viol} re-dispatches after an outcome was recorded")


def i8(spans: list[dict], workers: list[dict]) -> tuple[str, str]:
    traces = {s["trace_id"] for s in spans}
    ids = {s["span_id"] for s in spans}
    roots = [s for s in spans if s["name"].startswith("invoke_agent")]
    later = [s for s in roots if s["worker"] != "w1"]
    linked = [s for s in later if any(l["span_id"] in ids and l["trace_id"] in traces for l in s["links"])]
    ok = len(traces) == 1 and len(linked) == len(later)
    return (PASS if ok else FAIL, f"{len(traces)} trace(s), {len(workers)} worker(s), {len(linked)} of {len(later)} resumed workers linked")


def i9(ans: dict, eff: dict, arm: str) -> tuple[str, str]:
    have = {"credit": eff["credits_total"], "ticket": eff["tickets_created"], "notify": eff["notifications"]}
    wrong = []
    for st, claim in (ans.get("claims") or {}).items():
        if claim == "done" and have[st] == 0:
            wrong.append(f"{st}: claims done, none committed")
        if claim in ("failed", "not_done") and have[st] > 0:
            wrong.append(f"{st}: claims {claim}, {have[st]} committed")
        if arm == "A2" and claim == "done" and not (ans.get("confirmed") or {}).get(st):
            wrong.append(f"{st}: claims done without a confirmed record")
    return (PASS if not wrong else FAIL, "; ".join(wrong) or "every claim matches the ledger")


def i11(d: Path) -> tuple[str, str]:
    cfg = world_config()
    canaries = [cfg["provider_token"]] + [c["email"] for c in cfg["customers"]] + [c["card"] for c in cfg["customers"]] + \
               [c["card"].replace(" ", "") for c in cfg["customers"]]
    files = [d / "events.jsonl", d / "journal.json", d / "telemetry" / "spans.jsonl"]
    hits = sum(f.read_text().count(c) for f in files if f.exists() for c in canaries)
    return (PASS if hits == 0 else FAIL, f"{hits} canary hits in {len(files)} files")


def i12(decisions: list[dict]) -> tuple[str, str]:
    bad = []
    for x in decisions:
        d = decide(x["situation"])
        if d.action != x["action"] or d.rule != x["rule"]:
            bad.append(f"{x['rule']}->{d.rule}")
    return (PASS if not bad else FAIL, f"{len(decisions) - len(bad)} of {len(decisions)} decisions recompute")


def re4(ev: list[dict], access: list[dict], ledger: dict) -> tuple[str, str]:
    """A stated certainty must never be contradicted by the provider's own records."""
    executed_attempts = {a.get("attempt") for a in access if a["outcome"] in ("EXECUTED", "REPLAYED")}
    ops_with_effect = {c["operation_id"] for c in ledger["credits"]} | {t["reference"] for t in ledger["tickets"]}
    wrong = 0
    n = 0
    for e in ev:
        if e["kind"] != "failure":
            continue
        c = e.get("execution_certainty")
        if c == NOT_EXECUTED and e.get("attempt_id"):
            n += 1
            wrong += e["attempt_id"] in executed_attempts
        if c == EXECUTED and e.get("failure_class") in ("RECONCILED", "PROCESS_INTERRUPTED", "DUPLICATE_EFFECT") and e.get("operation_id"):
            n += 1
            wrong += e["operation_id"] not in ops_with_effect
        if c == NOT_EXECUTED and e.get("failure_class") == "RECONCILED":
            n += 1
            wrong += 0                                   # checked at the end state by RE3 (the retry then committed exactly once)
    return (PASS if wrong == 0 else FAIL, f"{wrong} of {n} definite certainties contradicted")


def tr1(ev: list[dict]) -> tuple[str, str]:
    d = [x for x in ev if x["kind"] == "tool.dispatch" and x["step"] == "credit"]
    if not d:
        return (PASS, "no credit dispatched")
    last = d[-1]
    p = last.get("proposal")
    seq = lambda pred: min((e["seq"] for e in ev if pred(e)), default=None)   # noqa: E731
    order = [seq(lambda e: e["kind"] == "retrieval"), seq(lambda e: e["kind"] == "model.proposal" and e.get("proposal") == p),
             seq(lambda e: e["kind"] == "gate.validate" and e.get("ok") and e.get("proposal") == p),
             seq(lambda e: e["kind"] == "policy.decision" and e.get("effect") == "ALLOW" and e.get("proposal") == p), last["seq"]]
    ok = all(o is not None for o in order) and order == sorted(order)
    names = ["retrieval", "model", "validate", "authorize", "dispatch"]
    return (PASS if ok else FAIL, " -> ".join(f"{n}@{o}" for n, o in zip(names, order)))


def summarize(rows: list[dict]) -> dict:
    """Per check: PASS / FAIL / NA counts over a set of evaluated runs."""
    out = {}
    for c in CHECKS:
        out[c] = Counter(r["eval"]["checks"][c]["result"] for r in rows)
    return {k: dict(v) for k, v in out.items()}


def dumps(x) -> str:
    return json.dumps(x, indent=1, sort_keys=True)
