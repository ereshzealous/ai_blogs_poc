"""Aggregate a run: facts, checks, reports, the tamper experiment, telemetry loss, sampling and retention, predictions.

Every number the article cites is a key in runs/<run>/facts.json with the file it was computed from.  Nothing here is typed
by hand; everything is read from the scenario directories the processes left behind.

Outputs (runs/<run>/):
  facts.json, checks.json, summary.md
  reports/comparison.{json,md}   the three layers, question by question, scenario by scenario
  reports/results.{json,md}      each scenario's outcome, side effects, attempts, processes
  reports/tamper.json            three tampering attempts against a copy of e01's evidence, and what verification said
  reports/telemetry.json         spans exported, spans orphaned by SIGKILL, metrics lost, head-sampling survival
  reports/timeline.json          the flagship scenario's reconstruction timeline, read from its evidence
  reports/predictions.json       P1–P7 and the per-scenario expectations, held or missed
  telemetry/  evidence/  state/  model/  commands/     run-level copies and summaries for inspection
"""

from __future__ import annotations

import copy
import json
import shutil
import tomllib
from collections import Counter
from pathlib import Path

from .common import EXPERIMENTS, POC, canon, jl, load
from .evidence import event_hash, verify

PREREG = tomllib.loads((EXPERIMENTS / "preregistration.toml").read_text())
RETENTION = load("retention.toml")
DATA = load("data.toml")
QS = [f"Q{i}" for i in range(1, 14)]
LAYERS = ("L0", "L1", "L2")
LAYER_NAME = {"L0": "Application logs", "L1": "Logs + traces", "L2": "Execution lineage"}
TOKEN = "dpl_live_7Fq2xW9rTt3LmZ"


class Facts:
    def __init__(self) -> None:
        self.f: dict[str, dict] = {}

    def put(self, key: str, value, source: str) -> None:
        if key in self.f:
            raise SystemExit(f"fact defined twice: {key}")
        self.f[key] = {"value": value, "source": source}


def scen(rdir: Path) -> list[Path]:
    order = [c["id"] for c in PREREG["case"]]
    have = {p.name: p for p in (rdir / "scenarios").iterdir() if p.is_dir()}
    return [have[c] for c in order if c in have]


def ev_rows(sdir: Path) -> list[dict]:
    return [dict(r, payload=json.loads(r["payload_json"])) for r in jl(sdir / "evidence" / "audit-events.jsonl")]


def target_exec(rows: list[dict]) -> str | None:
    return next((r["execution_id"] for r in rows if r["event_type"] == "execution.started" and not r["payload"]["background"]), None)


# ---- tamper experiment ---------------------------------------------------------------------------------------------------
def tamper(sdir: Path) -> dict:
    rows = [{k: v for k, v in r.items()} for r in jl(sdir / "evidence" / "audit-events.jsonl")]
    anchors = jl(sdir / "witness" / "anchors.jsonl")
    out = {"source": f"scenarios/{sdir.name}/evidence/audit-events.jsonl", "events": len(rows), "anchors": len(anchors),
           "baseline": verify(rows, anchors)}
    i = next(i for i, r in enumerate(rows) if r["event_type"] == "approval.decided")
    # T1: edit one approval decision in place (the approver's name), leave the hashes alone
    t1 = copy.deepcopy(rows)
    p = json.loads(t1[i]["payload_json"])
    before = p["approver"]
    p["approver"] = "eng.lee"
    t1[i]["payload_json"] = canon(p)
    out["T1_edit_in_place"] = {"what": f"approval.decided seq {t1[i]['seq']}: approver {before} -> eng.lee, hashes untouched", **verify(t1, anchors)}
    # T2: the same edit, then recompute every hash from that event on (an attacker with write access to the store)
    t2 = copy.deepcopy(t1)
    for j in range(i, len(t2)):
        t2[j]["prev_hash"] = t2[j - 1]["event_hash"] if j else "0" * 64
        t2[j]["event_hash"] = event_hash(t2[j])
    out["T2_rewrite_chain"] = {"what": "the same edit, every later hash recomputed so the chain is self-consistent", **verify(t2, anchors)}
    # T3: delete the last execution's final events (truncate the store)
    t3 = copy.deepcopy(rows[:-3])
    out["T3_truncate"] = {"what": "the last three events deleted", **verify(t3, anchors)}
    # T4: T2 again, but the attacker could also rewrite the witness (no independent anchor)
    fake_anchors = [dict(a, head_hash=t2[a["seq"] - 1]["event_hash"]) for a in anchors if a["seq"] <= len(t2)]
    out["T4_rewrite_chain_and_anchor"] = {"what": "T2, and the witness rewritten too: the case an anchor under the same control cannot catch",
                                           **verify(t2, fake_anchors)}
    return out


# ---- telemetry: spans lost to SIGKILL, metrics lost, head sampling ---------------------------------------------------------
def telemetry(sdir: Path) -> dict:
    spans = []
    for p in sorted((sdir / "telemetry").glob("spans-*.jsonl")):
        spans += jl(p)
    ids = {s["span_id"] for s in spans}
    orphans = [s for s in spans if s["parent_span_id"] and s["parent_span_id"] not in ids and not s["parent_is_remote"]]
    remote_missing = [s for s in spans if s["parent_is_remote"] and s["parent_span_id"] not in ids]
    life = json.loads((sdir / "procs" / "supervisor.json").read_text())
    killed = [p for p in life if p["signal"]]
    metric_files = len(list((sdir / "telemetry").glob("metrics-agent-*.json")))
    return {"spans": len(spans), "orphan_spans": len(orphans), "spans_whose_remote_parent_was_never_exported": len(remote_missing),
            "agent_processes": sum(1 for p in life), "agent_processes_killed": len(killed), "agent_metric_dumps": metric_files,
            "agent_metric_dumps_lost": sum(1 for p in life) - metric_files}


def sampled(trace_id_hex: str, rate: float) -> bool:
    from opentelemetry.sdk.trace.sampling import Decision, TraceIdRatioBased
    return TraceIdRatioBased(rate).should_sample(None, int(trace_id_hex, 16), "invoke_agent").decision == Decision.RECORD_AND_SAMPLE


# ---- leaks -----------------------------------------------------------------------------------------------------------------
def leak_scan(sdir: Path) -> dict:
    canary = DATA["datasets"]["payments.customer_transactions"]["canary"]
    hits = {"canary": [], "credential": []}
    files = list((sdir / "logs").glob("*.log")) + list((sdir / "telemetry").glob("*")) + [sdir / "evidence" / "audit-events.jsonl"]
    for tape in (sdir / "tape").glob("*/model_tape.jsonl"):
        files.append(tape)          # the tape holds exactly what was sent to the model
    for f in files:
        text = f.read_text()
        if canary in text:
            hits["canary"].append(str(f.relative_to(sdir)))
        if TOKEN in text:
            hits["credential"].append(str(f.relative_to(sdir)))
    return {"files_scanned": len(files), "canary_hits": hits["canary"], "credential_hits": hits["credential"]}


# ---- predictions -------------------------------------------------------------------------------------------------------------
def expectations(sdir: Path, case: dict) -> list[dict]:
    t = json.loads((sdir / "truth.json").read_text())
    rows = ev_rows(sdir)
    xid = target_exec(rows)
    E = [r for r in rows if r["execution_id"] == xid]
    got = {
        "outcome": "MITIGATED" if t["Q12"]["value"] else "NOT_MITIGATED",
        "mutations": t["Q11"]["value"], "attempts": t["Q9"]["value"], "tool_invoked": t["Q9"]["value"] > 0,
        "policy_decision": next((r["payload"]["decision"] for r in E if r["event_type"] == "policy.evaluated"), None),
        "approvals": sum(1 for r in E if r["event_type"] == "approval.decided" and r["payload"]["decision"] == "APPROVED"),
        "processes": sum(1 for p in json.loads((sdir / "procs" / "supervisor.json").read_text()) if p["role"] == "target"),
        "timeouts": sum(1 for r in E if r["event_type"] == "attempt.finished" and r["payload"]["result"] == "TIMEOUT"),
        "data_denied": any(r["event_type"] == "context.accessed" and r["payload"]["decision"] == "DENY" for r in E),
        "canary_leaks": len(leak_scan(sdir)["canary_hits"]),
        "verified": next((r["payload"]["verified"] for r in E if r["event_type"] == "effect.verified"), None),
        "recorded_config": next((r["payload"]["agent_config"] for r in E if r["event_type"] == "model.invoked"), None),
    }
    return [{"scenario": sdir.name, "field": k, "expected": v, "observed": got[k], "held": got[k] == v} for k, v in case["expect"].items()]


def predictions(comp: dict, res: dict, leaks: dict) -> list[dict]:
    sc = list(comp)
    out = []
    p1 = [s for s in sc if comp[s]["L2"]["correct"] != 13]
    out.append({"id": "P1", "held": not p1, "evidence": f"L2 below 13/13 in: {p1 or 'none'}"})
    p2 = [s for s in sc if comp[s]["L0"]["verdicts"]["Q13"] == "CORRECT"]
    out.append({"id": "P2", "held": not p2, "evidence": f"L0 verified integrity in: {p2 or 'none'}"})
    v = comp.get("e11-false-success", {}).get("L0", {}).get("verdicts", {}).get("Q12")
    out.append({"id": "P3", "held": v == "WRONG", "evidence": f"L0 Q12 verdict in e11-false-success: {v}"})
    p4 = [s for s in sc if not comp[s]["L1"]["heuristic_joins"] < comp[s]["L0"]["heuristic_joins"]]
    out.append({"id": "P4", "held": not p4, "evidence": f"L1 not fewer heuristic joins in: {p4 or 'none'}"})
    p5 = [s for s in sc if comp[s]["L0"]["verdicts"]["Q4"] == "CORRECT"]
    out.append({"id": "P5", "held": not p5, "evidence": f"L0 answered Q4 in: {p5 or 'none'}"})
    m = (res.get("e12a-lost-response", {}).get("mutations"), res.get("e12b-lost-response-no-key", {}).get("mutations"))
    out.append({"id": "P6", "held": m == (1, 2), "evidence": f"mutations e12a={m[0]}, e12b={m[1]}"})
    hits = {s: l["canary_hits"] for s, l in leaks.items() if l["canary_hits"]}
    out.append({"id": "P7", "held": not hits, "evidence": f"canary found in: {hits or 'none'}"})
    for p, pr in zip(out, PREREG["prediction"]):
        p["text"] = pr["text"]
    return out


# ---- the run -------------------------------------------------------------------------------------------------------------------
def aggregate(rdir: Path) -> dict:
    F = Facts()
    S = scen(rdir)
    rep = rdir / "reports"
    rep.mkdir(exist_ok=True)
    res = {s.name: json.loads((s / "result.json").read_text()) for s in S}
    recon = {s.name: json.loads((s / "reconstruction.json").read_text()) for s in S}
    comp = {n: r["score"] for n, r in res.items()}
    cases = {c["id"]: c for c in PREREG["case"]}
    src = lambda s, f: f"scenarios/{s}/{f}"  # noqa: E731

    # headline counts
    F.put("scenarios", len(S), "reports/results.json")
    F.put("experiments", len({n.split("-")[0].rstrip("ab") for n in res}), "experiments/preregistration.toml")
    F.put("questions", 13, "lineage/truth.py")
    F.put("answers_per_layer", 13 * len(S), "reports/comparison.json")
    for L in LAYERS:
        tot = sum(comp[n][L]["correct"] for n in comp)
        F.put(f"{L}_correct_total", tot, "reports/comparison.json")
        F.put(f"{L}_correct_pct", round(100 * tot / (13 * len(S))), "reports/comparison.json")
        F.put(f"{L}_full_scenarios", sum(1 for n in comp if comp[n][L]["correct"] == 13), "reports/comparison.json")
        F.put(f"{L}_min_correct", min(comp[n][L]["correct"] for n in comp), "reports/comparison.json")
        F.put(f"{L}_max_correct", max(comp[n][L]["correct"] for n in comp), "reports/comparison.json")
        F.put(f"{L}_key_joins_total", sum(comp[n][L]["key_joins"] for n in comp), "reports/comparison.json")
        F.put(f"{L}_heuristic_joins_total", sum(comp[n][L]["heuristic_joins"] for n in comp), "reports/comparison.json")
        F.put(f"{L}_sources_max", max(len(comp[n][L]["sources"]) for n in comp), "reports/comparison.json")
        for v in ("WRONG", "INCOMPLETE", "UNANSWERABLE", "AMBIGUOUS"):
            F.put(f"{L}_{v.lower()}_total", sum(1 for n in comp for q in QS if comp[n][L]["verdicts"][q] == v), "reports/comparison.json")
        for q in QS:
            F.put(f"{L}_{q}_correct", sum(1 for n in comp if comp[n][L]["verdicts"][q] == "CORRECT"), "reports/comparison.json")
    for n in comp:
        k = n.split("-")[0]
        for L in LAYERS:
            F.put(f"{k}_{L}_correct", comp[n][L]["correct"], src(n, "reconstruction.json"))
        r = res[n]
        F.put(f"{k}_outcome", r["outcome"], src(n, "result.json"))
        F.put(f"{k}_mutations", r["mutations"], src(n, "truth.json"))
        F.put(f"{k}_attempts", r["attempts"], src(n, "truth.json"))
        F.put(f"{k}_processes", r["processes"], src(n, "procs/supervisor.json"))
        F.put(f"{k}_evidence_events", r["evidence_events"], src(n, "evidence/verification.json"))

    # flagship and friends: read from evidence and the deployment API's records
    def target_events(n: str, t: str) -> list[dict]:
        rows = ev_rows(rdir / "scenarios" / n)
        x = target_exec(rows)
        return [r for r in rows if r["execution_id"] == x and r["event_type"] == t]

    for n in ("e12a-lost-response", "e12b-lost-response-no-key", "e06-duplicate-delivery", "e05b-crash-after-dispatch", "e11-false-success", "e01-success", "e02-tool-failure"):
        if n not in res:
            continue
        k = n.split("-")[0]
        sd = rdir / "scenarios" / n
        t = json.loads((sd / "truth.json").read_text())
        reqs = t["Q9"]["detail"]["requests"]
        fin = target_events(n, "attempt.finished")
        ver = target_events(n, "effect.verified")
        F.put(f"{k}_requests_reaching_api", len(reqs), src(n, "world/external-transactions.json"))
        F.put(f"{k}_timeouts", sum(1 for e in fin if e["payload"]["result"] == "TIMEOUT"), src(n, "evidence/audit-events.jsonl"))
        F.put(f"{k}_replayed", sum(1 for e in fin if e["payload"]["result"] == "REPLAYED"), src(n, "evidence/audit-events.jsonl"))
        F.put(f"{k}_responses_dropped", sum(1 for r in reqs if r["response_delivered"] == 0), src(n, "world/external-transactions.json"))
        if ver:
            v = ver[-1]["payload"]
            F.put(f"{k}_rev_before", v["observed_before"]["revision"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_rev_after", v["observed_after"]["revision"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_ver_before", v["observed_before"]["version"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_ver_after", v["observed_after"]["version"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_verified", v["verified"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_txns_for_key", len(v["transactions_for_key"]), src(n, "evidence/audit-events.jsonl"))
        timeouts = [e for e in fin if e["payload"]["result"] == "TIMEOUT"]
        if timeouts:
            F.put(f"{k}_timeout_ms", round(timeouts[0]["payload"]["latency_ms"]), src(n, "evidence/audit-events.jsonl"))
        txn = next((e["payload"]["external_transaction_id"] for e in fin if e["payload"].get("external_transaction_id")), None)
        if txn:
            F.put(f"{k}_txn", txn, src(n, "evidence/audit-events.jsonl"))
        aid = next((e["action_id"] for e in fin), None)
        if aid:
            F.put(f"{k}_action_id", aid, src(n, "evidence/audit-events.jsonl"))
        claimed = next((e["payload"].get("claimed_status") for e in fin if e["payload"].get("claimed_status")), None)
        if claimed:
            F.put(f"{k}_claimed_status", claimed, src(n, "evidence/audit-events.jsonl"))
        F.put(f"{k}_exec_id", target_exec(ev_rows(sd)), src(n, "evidence/audit-events.jsonl"))
        rec = target_events(n, "attempt.reconciled")
        if rec:
            F.put(f"{k}_reconciled", len(rec), src(n, "evidence/audit-events.jsonl"))
        tr = json.loads((sd / "reconstruction.json").read_text())
        for L in LAYERS:
            for q in ("Q9", "Q11", "Q12"):
                F.put(f"{k}_{L}_{q}", tr[L]["answers"][q]["answer"], src(n, "reconstruction.json"))

    # policy and config lineage (E8, E9)
    for n in ("e08a-policy-v41", "e08b-policy-v42"):
        if n in res:
            k = n.split("-")[0]
            pe = target_events(n, "policy.evaluated")[0]["payload"]
            F.put(f"{k}_policy_version", pe["policy_version"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_policy_digest", pe["policy_digest"][:19], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_quorum", pe["obligations"]["quorum"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_verify_obligation", pe["obligations"]["verify_effect"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_approvers", len(target_events(n, "approval.decided")), src(n, "evidence/audit-events.jsonl"))
    for n in ("e01-success", "e09-config-v9"):
        if n in res:
            k = n.split("-")[0]
            m = target_events(n, "model.invoked")[0]["payload"]
            F.put(f"{k}_prompt_template", m["prompt_template"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_agent_config", m["agent_config"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_model", m["model"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_model_digest", m["model_digest"][:19], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_temperature", m["options"]["temperature"], src(n, "evidence/audit-events.jsonl"))
            so = m["structured_output"]
            F.put(f"{k}_proposal", f"{so['capability']} {so['service']} {so['to_version']}".strip(), src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_input_tokens", m["input_tokens"], src(n, "evidence/audit-events.jsonl"))
            F.put(f"{k}_output_tokens", m["output_tokens"], src(n, "evidence/audit-events.jsonl"))
    if "e10-restricted-data" in res:
        den = [e["payload"] for e in target_events("e10-restricted-data", "context.accessed") if e["payload"]["decision"] == "DENY"]
        F.put("e10_denied_dataset", den[0]["dataset"] if den else None, src("e10-restricted-data", "evidence/audit-events.jsonl"))
        F.put("e10_denied_classification", den[0]["classification"] if den else None, src("e10-restricted-data", "evidence/audit-events.jsonl"))
    if "e07-unexpected-capability" in res:
        g = target_events("e07-unexpected-capability", "gateway.denied")
        F.put("e07_gateway_denials", len(g), src("e07-unexpected-capability", "evidence/audit-events.jsonl"))
        F.put("e07_capability", g[0]["payload"]["capability"] if g else None, src("e07-unexpected-capability", "evidence/audit-events.jsonl"))
    if "e03-policy-denial" in res:
        pe = target_events("e03-policy-denial", "policy.evaluated")[0]["payload"]
        F.put("e03_decision", pe["decision"], src("e03-policy-denial", "evidence/audit-events.jsonl"))
        F.put("e03_severity", pe["attributes"]["severity"], src("e03-policy-denial", "evidence/audit-events.jsonl"))

    # evidence integrity, tamper, leaks
    vers = {n: json.loads((rdir / "scenarios" / n / "evidence" / "verification.json").read_text()) for n in res}
    F.put("evidence_events_total", sum(v["events"] for v in vers.values()), "scenarios/*/evidence/verification.json")
    F.put("evidence_chains_intact", sum(1 for v in vers.values() if v["intact"]), "scenarios/*/evidence/verification.json")
    tam = tamper(rdir / "scenarios" / ("e01-success" if "e01-success" in res else S[0].name))
    (rep / "tamper.json").write_text(json.dumps(tam, indent=1))
    for k in ("T1_edit_in_place", "T2_rewrite_chain", "T3_truncate", "T4_rewrite_chain_and_anchor"):
        F.put(f"tamper_{k.split('_')[0]}_detected", not tam[k]["intact"], "reports/tamper.json")
        F.put(f"tamper_{k.split('_')[0]}_chain_ok", tam[k]["chain_ok"], "reports/tamper.json")
        F.put(f"tamper_{k.split('_')[0]}_anchor_ok", tam[k]["anchors_ok"], "reports/tamper.json")
    F.put("tamper_detected", sum(1 for k in ("T1_edit_in_place", "T2_rewrite_chain", "T3_truncate") if not tam[k]["intact"]), "reports/tamper.json")
    leaks = {n: leak_scan(rdir / "scenarios" / n) for n in res}
    F.put("files_scanned", sum(l["files_scanned"] for l in leaks.values()), "reports/telemetry.json")
    F.put("canary_hits", sum(len(l["canary_hits"]) for l in leaks.values()), "reports/telemetry.json")
    F.put("credential_hits", sum(len(l["credential_hits"]) for l in leaks.values()), "reports/telemetry.json")

    # telemetry loss, sampling
    tel = {n: telemetry(rdir / "scenarios" / n) for n in res}
    F.put("spans_total", sum(t["spans"] for t in tel.values()), "reports/telemetry.json")
    F.put("orphan_spans_total", sum(t["orphan_spans"] + t["spans_whose_remote_parent_was_never_exported"] for t in tel.values()), "reports/telemetry.json")
    F.put("killed_processes", sum(t["agent_processes_killed"] for t in tel.values()), "reports/telemetry.json")
    F.put("metric_dumps_lost", sum(t["agent_metric_dumps_lost"] for t in tel.values()), "reports/telemetry.json")
    for n in ("e05a-crash-awaiting-approval", "e05b-crash-after-dispatch"):
        if n in tel:
            k = n.split("-")[0]
            F.put(f"{k}_orphan_spans", tel[n]["orphan_spans"] + tel[n]["spans_whose_remote_parent_was_never_exported"], "reports/telemetry.json")
            F.put(f"{k}_metric_dumps_lost", tel[n]["agent_metric_dumps_lost"], "reports/telemetry.json")
    trace_ids = {}
    for n in res:
        start = [r for r in ev_rows(rdir / "scenarios" / n) if r["event_type"] == "execution.started" and not r["payload"]["background"]]
        trace_ids[n] = start[0]["trace_id"] if start else None
    samp = {rate: sum(1 for t in trace_ids.values() if t and sampled(t, rate)) for rate in (0.01, 0.1, 0.25)}
    for rate, kept in samp.items():
        F.put(f"sampled_{int(rate * 100)}pct", kept, "reports/telemetry.json")
    (rep / "telemetry.json").write_text(json.dumps({"per_scenario": tel, "leaks": leaks, "head_sampling": {
        "method": "opentelemetry.sdk.trace.sampling.TraceIdRatioBased applied to each target execution's recorded trace id",
        "target_traces": len(trace_ids), "kept": {str(k): v for k, v in samp.items()}}}, indent=1))

    # retention: what each layer still holds N days later, from config/retention.toml
    ret = {"L0": RETENTION["classes"]["debug-logs"]["retention_days"], "L1": min(RETENTION["classes"]["debug-logs"]["retention_days"], RETENTION["classes"]["ops-telemetry"]["retention_days"]),
           "L2": RETENTION["classes"]["audit-evidence"]["retention_days"]}
    for L, d in ret.items():
        F.put(f"{L}_retention_days", d, "config/retention.toml")
    F.put("ops_telemetry_days", RETENTION["classes"]["ops-telemetry"]["retention_days"], "config/retention.toml")

    # metrics from the processes that exited cleanly
    mt = Counter()
    for n in res:
        for p in (rdir / "scenarios" / n / "telemetry").glob("metrics-agent-*.json"):
            for m in json.loads(p.read_text()):
                for pt in m["points"]:
                    key = m["name"] + "{" + ",".join(f"{a}={b}" for a, b in sorted(pt["attributes"].items())) + "}"
                    mt[key] += pt["value"] if isinstance(pt["value"], (int, float)) else pt["value"]["count"]
    (rdir / "telemetry").mkdir(exist_ok=True)
    (rdir / "telemetry" / "metrics.json").write_text(json.dumps(dict(sorted(mt.items())), indent=1))
    F.put("metric_series", len(mt), "telemetry/metrics.json")
    F.put("metric_label_keys", sorted({k.split("{")[1].rstrip("}").split("=")[0] for k in mt if "{" in k and "=" in k}).__len__(), "telemetry/metrics.json")

    # model traffic
    calls = sum(len(jl(t)) for n in res for t in (rdir / "scenarios" / n / "tape").glob("*/model_tape.jsonl"))
    chats = sum(1 for n in res for t in (rdir / "scenarios" / n / "tape").glob("*/model_tape.jsonl") for r in jl(t) if r.get("path") == "/api/chat")
    F.put("model_calls", chats, "scenarios/*/tape/*/model_tape.jsonl")
    F.put("tape_records", calls, "scenarios/*/tape/*/model_tape.jsonl")

    # flagship timeline
    if "e12a-lost-response" in res:
        rows = target_events_all(rdir / "scenarios" / "e12a-lost-response")
        from datetime import datetime
        t0 = datetime.fromisoformat(rows[0]["occurred_at"].replace("Z", "+00:00")).timestamp()
        tl = [{"t_plus_s": round(datetime.fromisoformat(r["occurred_at"].replace("Z", "+00:00")).timestamp() - t0, 3), "event": r["event_type"],
               "attempt": r["attempt_id"], "summary": summarize(r)} for r in rows]
        (rep / "timeline.json").write_text(json.dumps(tl, indent=1))
        F.put("e12a_timeline_events", len(tl), "reports/timeline.json")
        F.put("e12a_total_s", round(tl[-1]["t_plus_s"], 1), "reports/timeline.json")

    # the drift probe, when it has been run into this run directory (lineage.drift)
    dj = rdir / "drift" / "drift.json"
    if dj.exists():
        d = json.loads(dj.read_text())
        shutil.copy(dj, rep / "drift.json")
        F.put("drift_variants", d["variants"], "reports/drift.json")
        F.put("drift_calls", d["calls"], "reports/drift.json")
        F.put("drift_changed", d["variants_whose_action_changed"], "reports/drift.json")
        F.put("drift_denied", d["rollback_proposals_denied_by_policy"], "reports/drift.json")
        for ref, dist in d["distribution"].items():
            v = ref.split("@")[1]
            for cap in ("deployment.rollback", "pods.restart", "diagnostics.run", "noAction"):
                F.put(f"drift_v{v}_{cap.split('.')[-1].lower()}", dist.get(cap, 0), "reports/drift.json")
        d01 = {r["config"].split("@")[1]: r["capability"] for r in d["rows"] if r["variant"] == "D01"}
        F.put("drift_d01_v8", d01.get("8"), "reports/drift.json")
        F.put("drift_d01_v9", d01.get("9"), "reports/drift.json")

    # predictions and expectations
    exp = [e for s in S for e in expectations(s, cases[s.name])]
    preds = predictions(comp, res, leaks)
    (rep / "predictions.json").write_text(json.dumps({"predictions": preds, "expectations": exp}, indent=1))
    F.put("predictions", len(preds), "reports/predictions.json")
    F.put("predictions_held", sum(1 for p in preds if p["held"]), "reports/predictions.json")
    F.put("expectations", len(exp), "reports/predictions.json")
    F.put("expectations_held", sum(1 for e in exp if e["held"]), "reports/predictions.json")
    F.put("expectations_missed", ", ".join(f"{e['scenario']}.{e['field']}" for e in exp if not e["held"]) or "none", "reports/predictions.json")

    # checks: things that must be true for the run to be publishable (a failed check is reported, never hidden)
    checks = [
        {"id": "C1", "check": "every scenario ran to completion (no ERROR outcome, no process that exited abnormally other than SIGKILL)",
         "pass": all(r["outcome"] not in ("NONE", "ERROR") for r in res.values())},
        {"id": "C2", "check": "every scenario's evidence chain and anchors verify", "pass": all(v["intact"] for v in vers.values())},
        {"id": "C3", "check": "tampering T1–T3 is detected", "pass": all(not tam[k]["intact"] for k in ("T1_edit_in_place", "T2_rewrite_chain", "T3_truncate"))},
        {"id": "C4", "check": "the restricted-data canary appears in no model request, log, span or evidence event", "pass": all(not l["canary_hits"] for l in leaks.values())},
        {"id": "C5", "check": "the deploy-api credential appears in no log, span, tape or evidence event", "pass": all(not l["credential_hits"] for l in leaks.values())},
        {"id": "C6", "check": "no metric attribute carries an execution, action, attempt or trace id",
         "pass": not any(x in k for k in mt for x in ("exec-", "act-", "trace", "apr-"))},
        {"id": "C7", "check": "every scenario has exactly one target execution in its evidence", "pass": all(len({r["execution_id"] for r in ev_rows(s) if r["event_type"] == "execution.started" and not r["payload"]["background"]}) == 1 for s in S)},
    ]
    (rdir / "checks.json").write_text(json.dumps(checks, indent=1))
    F.put("checks_total", len(checks), "checks.json")
    F.put("checks_passed", sum(1 for c in checks if c["pass"]), "checks.json")

    (rdir / "facts.json").write_text(json.dumps(F.f, indent=1, default=str))
    write_reports(rdir, res, recon, comp, cases)
    run_level_copies(rdir, S)
    write_summary(rdir, F.f, res, comp, checks, preds, exp, tam)
    return F.f


def target_events_all(sdir: Path) -> list[dict]:
    rows = ev_rows(sdir)
    x = target_exec(rows)
    return [r for r in rows if r["execution_id"] == x]


def summarize(r: dict) -> str:
    p, t = r["payload"], r["event_type"]
    return {
        "execution.started": lambda: f"{p['incident']} {p['severity']} from {p['trigger']['source']} for {p['on_behalf_of']}",
        "context.accessed": lambda: f"{p['dataset']} {p['decision']}",
        "model.invoked": lambda: f"{p['model']} · {p['prompt_template']} · {p['agent_config']}",
        "decision.proposed": lambda: f"{p['capability']} {p['target']} {p['arguments'].get('to_version', '')}",
        "policy.evaluated": lambda: f"{p['policy_id']}@{p['policy_version']} {p['decision']}",
        "approval.requested": lambda: f"{p['approval_id']} quorum {p['quorum']}",
        "approval.decided": lambda: f"{p['approver']} {p['decision']}",
        "action.authorized": lambda: f"{r['action_id']} key={p['idempotency_key']}",
        "attempt.started": lambda: f"attempt {p['attempt']}",
        "attempt.finished": lambda: f"attempt {p['attempt']} {p['result']}" + (f" {p['external_transaction_id']}" if p.get("external_transaction_id") else ""),
        "attempt.reconciled": lambda: f"attempt {p['attempt']} {p['result']}",
        "effect.verified": lambda: f"revision {p['observed_before']['revision']} -> {p['observed_after']['revision']}, {p['observed_after']['version']}, verified={p['verified']}",
        "execution.completed": lambda: f"{p['outcome']}",
        "workflow.resumed": lambda: f"from {p['from_step']}",
        "gateway.denied": lambda: f"{p['capability']} refused",
    }.get(t, lambda: t)()


def write_reports(rdir: Path, res: dict, recon: dict, comp: dict, cases: dict) -> None:
    rep = rdir / "reports"
    (rep / "comparison.json").write_text(json.dumps({"layers": LAYER_NAME, "scenarios": {n: {L: {"correct": comp[n][L]["correct"], "verdicts": comp[n][L]["verdicts"],
                                                     "answers": {q: recon[n][L]["answers"][q]["answer"] for q in QS}, "truth": {q: recon[n][L]["answers"][q]["truth"] for q in QS},
                                                     "sources": comp[n][L]["sources"], "key_joins": comp[n][L]["key_joins"], "heuristic_joins": comp[n][L]["heuristic_joins"],
                                                     "joins": recon[n][L]["joins"]} for L in LAYERS} for n in comp}}, indent=1, default=str))
    ab = {"CORRECT": "✓", "INCOMPLETE": "partial", "UNANSWERABLE": "—", "WRONG": "WRONG", "AMBIGUOUS": "ambiguous"}
    md = ["# Reconstruction comparison", "", "Each cell: the layer's verdict for that question, scored against ground truth from the systems of record "
          "(`lineage/truth.py`). ✓ correct · partial = some parts unrecorded · — = not recorded at all · WRONG = a recorded answer that is false.", ""]
    for L in LAYERS:
        md += [f"## {L} · {LAYER_NAME[L]}", "", "| scenario | " + " | ".join(QS) + " | correct | key joins | heuristic joins |", "|---|" + "---|" * (len(QS) + 3)]
        for n in comp:
            md.append(f"| {n} | " + " | ".join(ab[comp[n][L]["verdicts"][q]] for q in QS) + f" | {comp[n][L]['correct']}/13 | {comp[n][L]['key_joins']} | {comp[n][L]['heuristic_joins']} |")
        md.append("")
    (rep / "comparison.md").write_text("\n".join(md))
    (rep / "results.json").write_text(json.dumps(res, indent=1))
    md = ["# Scenario results", "", "| scenario | group | outcome | production changes | attempts reaching the API | agent processes | evidence events | L0 | L1 | L2 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for n, r in res.items():
        md.append(f"| {n} | {cases[n]['group']} | {r['outcome']} | {r['mutations']} | {r['attempts']} | {r['processes']} | {r['evidence_events']} | "
                  f"{r['score']['L0']['correct']}/13 | {r['score']['L1']['correct']}/13 | {r['score']['L2']['correct']}/13 |")
    (rep / "results.md").write_text("\n".join(md) + "\n")


def run_level_copies(rdir: Path, S: list[Path]) -> None:
    """Run-level views the plan's layout asks for; every file is a concatenation of scenario files, tagged by scenario."""
    for sub in ("telemetry", "evidence", "state", "model", "commands"):
        (rdir / sub).mkdir(exist_ok=True)
    with open(rdir / "telemetry" / "traces.jsonl", "w") as tr, open(rdir / "telemetry" / "logs.jsonl", "w") as lg, \
            open(rdir / "evidence" / "audit-events.jsonl", "w") as ev:
        for s in S:
            for p in sorted((s / "telemetry").glob("spans-*.jsonl")):
                for r in jl(p):
                    tr.write(json.dumps({"scenario": s.name, **r}) + "\n")
            for p in sorted((s / "logs").glob("*.log")):
                for r in jl(p):
                    lg.write(json.dumps({"scenario": s.name, **r}) + "\n")
            for r in jl(s / "evidence" / "audit-events.jsonl"):
                ev.write(json.dumps({"scenario": s.name, **r}) + "\n")
    (rdir / "evidence" / "evidence-verification.json").write_text(json.dumps({s.name: json.loads((s / "evidence" / "verification.json").read_text()) for s in S}, indent=1))
    (rdir / "state" / "before.json").write_text(json.dumps({s.name: json.loads((s / "world" / "before.json").read_text())["deployments"] for s in S}, indent=1))
    (rdir / "state" / "after.json").write_text(json.dumps({s.name: json.loads((s / "world" / "after.json").read_text()) for s in S}, indent=1))
    (rdir / "state" / "external-transactions.json").write_text(json.dumps({s.name: json.loads((s / "world" / "external-transactions.json").read_text()) for s in S}, indent=1))
    calls = []
    for s in S:
        for t in sorted((s / "tape").glob("*/model_tape.jsonl")):
            for r in jl(t):
                if r.get("path") == "/api/chat":
                    resp = json.loads(r["response"])
                    calls.append({"scenario": s.name, "role": t.parent.name, "hash": r["hash"][:16], "model": resp.get("model"),
                                  "input_tokens": resp.get("prompt_eval_count"), "output_tokens": resp.get("eval_count"), "wall_s": r.get("wall_s"),
                                  "tool_calls": [c["function"]["name"] for c in (resp.get("message") or {}).get("tool_calls") or []]})
    (rdir / "model" / "calls.json").write_text(json.dumps(calls, indent=1))
    (rdir / "model" / "README.md").write_text("The model tapes are per scenario and role: `scenarios/<scenario>/tape/<role>/model_tape.jsonl` "
                                              "(request hash -> Ollama response). `calls.json` summarises every chat call.\n")
    (rdir / "commands" / "exact-run-commands.txt").write_text(
        f"# run {rdir.name}\ncd observability_governance_poc\nuv sync --group dev\n"
        + ("uv run python -m lineage.run record --run-id " + rdir.name if "replay" not in rdir.name else f"uv run python -m lineage.run replay {rdir.name.removesuffix('-replay')}")
        + "\nuv run python -m lineage.drift record --run-id " + rdir.name + "   # the drift probe (reports/drift.json)\n"
        + "uv run pytest\n")


def write_summary(rdir: Path, f: dict, res: dict, comp: dict, checks: list, preds: list, exp: list, tam: dict) -> None:
    v = lambda k: f[k]["value"] if k in f else "n/a"  # noqa: E731
    md = [f"# Run {rdir.name}", "",
          f"{v('scenarios')} scenarios ({v('experiments')} experiments), each with a concurrent background execution, observed three ways from the same run.",
          "",
          "## Reconstruction (13 questions per scenario)", "",
          "| layer | correct | scenarios fully answered | wrong | partial | not recorded | key joins | heuristic joins |", "|---|---|---|---|---|---|---|---|"]
    for L in LAYERS:
        md.append(f"| {L} · {LAYER_NAME[L]} | {v(L + '_correct_total')}/{v('answers_per_layer')} | {v(L + '_full_scenarios')}/{v('scenarios')} | "
                  f"{v(L + '_wrong_total')} | {v(L + '_incomplete_total')} | {v(L + '_unanswerable_total')} | {v(L + '_key_joins_total')} | {v(L + '_heuristic_joins_total')} |")
    md += ["", "## Scenarios", ""] + (rdir / "reports" / "results.md").read_text().splitlines()[2:]
    md += ["", "## Checks", ""] + [f"- {'PASS' if c['pass'] else 'FAIL'} {c['id']}: {c['check']}" for c in checks]
    md += ["", "## Predictions", ""] + [f"- {'held' if p['held'] else 'MISSED'} {p['id']}: {p['text']} ({p['evidence']})" for p in preds]
    md += ["", f"Per-scenario expectations: {v('expectations_held')}/{v('expectations')} held; missed: {v('expectations_missed')}."]
    md += ["", "## Tamper experiment (copy of e01's evidence)", ""] + [f"- {k}: {tam[k]['what']} → chain {'ok' if tam[k]['chain_ok'] else 'BROKEN'}, anchors {'ok' if tam[k]['anchors_ok'] else 'MISMATCH'}"
                                                                       for k in ("T1_edit_in_place", "T2_rewrite_chain", "T3_truncate", "T4_rewrite_chain_and_anchor")]
    (rdir / "summary.md").write_text("\n".join(md) + "\n")


# ---- replay comparison ----------------------------------------------------------------------------------------------------------
VOLATILE = {"occurred_at", "latency_ms", "observed_at", "decided_at", "event_hash", "prev_hash", "event_id", "restored_trace", "previous_pid",
            "replayed"}   # "replayed" on model.invoked is True in a replay by definition


def stable(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        p = json.loads(r["payload_json"])
        p = {k: v for k, v in p.items() if k not in VOLATILE}
        out.append({"event_type": r["event_type"], "execution_id": r["execution_id"], "action_id": r["action_id"], "attempt_id": r["attempt_id"], "payload": p})
    return sorted(out, key=lambda x: (x["execution_id"], canon(x)))


def compare_replay(src: Path, rep: Path) -> dict:
    out = {"source": src.name, "replay": rep.name, "scenarios": {}}
    for s in scen(rep):
        a, b = src / "scenarios" / s.name, s
        ra, rb = json.loads((a / "result.json").read_text()), json.loads((b / "result.json").read_text())
        same_result = {k: ra[k] == rb[k] for k in ("outcome", "mutations", "attempts", "processes", "evidence_intact", "evidence_events")}
        same_scores = all(ra["score"][L]["verdicts"] == rb["score"][L]["verdicts"] for L in LAYERS)
        ea, eb = stable(jl(a / "evidence" / "audit-events.jsonl")), stable(jl(b / "evidence" / "audit-events.jsonl"))
        misses = sum(len(jl(t)) for t in (b / "tape").glob("*/model_tape.misses.jsonl"))
        consumed = sum(len(jl(t)) for t in (b / "tape").glob("*/model_tape.consumed.jsonl"))
        out["scenarios"][s.name] = {"result_identical": all(same_result.values()), "differences": [k for k, x in same_result.items() if not x],
                                    "verdicts_identical": same_scores, "evidence_identical": ea == eb, "tape_misses": misses, "answers_served": consumed}
    sc = out["scenarios"].values()
    out["all_identical"] = all(x["result_identical"] and x["verdicts_identical"] and x["evidence_identical"] and x["tape_misses"] == 0 for x in sc)
    out["answers_served"] = sum(x["answers_served"] for x in sc)
    out["tape_misses"] = sum(x["tape_misses"] for x in sc)
    (rep / "replay-comparison.json").write_text(json.dumps(out, indent=1))
    shutil.copy(rep / "replay-comparison.json", src / "reports" / "replay-comparison.json")
    print(f"replay: identical={out['all_identical']} answers served={out['answers_served']} misses={out['tape_misses']}")
    return out
