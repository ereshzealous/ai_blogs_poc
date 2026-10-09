"""Build T2's Lab Console: every check the authorization POC ran, its input, its output, the decision behind it, the
audit records it left and where each number came from.

    python3 tools/build_lab_console.py [RUN_ID]          (default: 2026-09-29-recorded)
      -> results/lab-console.html              one self-contained page (evidence-kit 4.1.0, vendor/evidence_kit)
      -> results/lab-console.evidence.json     the canonical evidence it renders

It reads recorded files only (authz_poc/runs/<run>/): decisions.jsonl, timeline.json, sweep.json, expectations.json,
invariants.json, tests.json, facts.json, manifest.json, verification.json. Produce them first:

    cd authz_poc && python3 -m authz.run && python3 -m authz.record_tests && python3 -m authz.verify

The words are in tools/lab_console/learning.toml, where every number is a {{fact}}; the kit refuses hand-typed numbers.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "authz_poc"
sys.path.insert(0, str(ROOT / "vendor"))
import evidence_kit as kit  # noqa: E402  (4.1.0, vendor/evidence_kit)
from evidence_kit import blocks as B  # noqa: E402

SPEC = ROOT / "tools" / "lab_console" / "learning.toml"
OUT = ROOT / "results" / "lab-console.html"

TONE = {"ALLOW": "ok", "ALLOW_WITH_CONSTRAINTS": "info", "ALLOW_WITH_APPROVAL": "warn", "DENY": "bad",
        "approved": "ok", "rejected": "bad", "executed": "ok", "holds": "ok"}
EVT = {"ALLOW": "ok", "ALLOW_WITH_CONSTRAINTS": "info", "ALLOW_WITH_APPROVAL": "warn", "DENY": "bad"}
GROUP = {"l1": "L1 policy unit test", "l3": "L3 gateway integration test", "l4": "L4 recorded replay test",
         "permit": "Role grant, no rule restricted it", "constraint": "Constraint rule (ABAC)", "approval": "Approval rule (ABAC)",
         "forbid": "Forbid rule (ABAC)", "rebac": "Relationship check (ReBAC)", "rbac": "Role check (RBAC)",
         "gate": "Approval gate", "invariant": "Invariant"}


def group_of(rule: str | None) -> str:
    if not rule:
        return "permit"
    if rule.startswith("rebac."):
        return "rebac"
    if rule.startswith(("rbac.", "default.")):
        return "rbac"
    return {"F": "forbid", "A": "approval", "C": "constraint"}.get(rule[0], "permit")


def jload(p: Path):
    return json.loads(p.read_text())


def code(v) -> str:
    return f"`{v}`" if v not in (None, "", []) else "—"


def decision_cards(rec: dict) -> list:
    """The two audiences of one decision: what the agent was told, and what the audit record keeps."""
    av = rec["agent_view"]
    a = rec["attributes"]
    told = B.card(B.kv("Decision", B.chips([(av["decision"], TONE.get(av["decision"], ""))])),
                  B.kv("Returned to the agent", *[B.line(k, code(av[k])) for k in ("code", "reason", "message", "next", "constraints", "approval_id") if av.get(k)]),
                  title="What the agent was told", sub="The agent-facing envelope: decision, code, a short reason and the next step. No rules, attributes or relationships.")
    keys = ["principal.roles", "acting_for", "kind", "risk", "tier", "data_classification", "environment", "severity", "incident_state",
            "change_window", "tenant_in_scope", "evidence_score", "evidence_signals"]
    attrs = B.table(["Attribute", "Value"], [[B.cell(("code", k)), B.cell(("text", json.dumps(a[k]) if isinstance(a[k], (list, bool)) else str(a[k])))]
                                            for k in keys if k in a])
    kept = B.card(B.kv("Reason (audit view)", B.quote(rec["reason"])),
                  B.kv("Evaluation", B.line("Matched rules", ", ".join(f"`{m}`" for m in rec["matched_rules"]) or "none (no rule restricted it)"),
                       B.line("Grants", ", ".join(f"`{g}`" for g in rec["grants"]) or "none"), B.line("Policy version", code(rec["policy_version"])),
                       B.line("Request fingerprint", code(rec["request_fingerprint"])), B.line("Decision id", code(rec["decision_id"])),
                       B.line("Re-check of", code(rec.get("recheck_of")))),
                  B.kv("Attributes the PIP resolved", attrs),
                  title="What the audit record keeps", sub="Enough to rebuild the decision later: rules, grants, attributes and the policy version.")
    return [B.grid(told, kept)]


def audit_tab(recs: list[dict], note: str) -> list:
    rows = [[B.cell(("text", str(r["seq"]))), B.cell(("text", r["time"][11:19])), B.cell(("code", r["kind"])), B.cell(("code", r["prev"])),
             B.cell(("code", r["hash"]))] for r in recs]
    raw = [{"n": r["seq"], "tone": "info", "text": f"`{r['kind']}` · seq {r['seq']} · hash `{r['hash']}`", "code": json.dumps(r["record"], indent=1)} for r in recs]
    return [B.card(B.table([("Seq", "n"), "Time", "Kind", "Prev hash", "Hash"], rows), title="Audit records", sub=note),
            B.transcript(raw, "Records as written", "Each record exactly as it sits in `decisions.jsonl`.")]


def source_tab(items: list[tuple[str, str, str]]) -> list:
    rows = [[B.cell(("text", a)), B.cell(("code", f)), B.cell(("text", d))] for a, f, d in items]
    return [B.card(B.table(["Stage", "File", "Carries"], rows), title="Where this row comes from",
                   sub="From the scenario to this page. Every file is in the repository; paths are relative to `authz_poc/`.")]


def collect(run_id: str) -> tuple[dict, kit.Facts]:
    rd = POC / "runs" / run_id
    rel = f"authz_poc/runs/{run_id}"
    facts_j, timeline, sweep = jload(rd / "facts.json"), jload(rd / "timeline.json"), jload(rd / "sweep.json")
    exp, inv, tests = jload(rd / "expectations.json"), jload(rd / "invariants.json"), jload(rd / "tests.json")
    man, ver = jload(rd / "manifest.json"), jload(rd / "verification.json")
    audit = [json.loads(line) for line in (rd / "decisions.jsonl").read_text().splitlines()]
    scn = tomllib.loads((POC / "scenario.toml").read_text())
    policy = tomllib.loads((POC / "config" / "policy.toml").read_text())
    transcript = (rd / "transcript.txt").read_text().splitlines()
    E = {e["id"]: e for e in exp["results"]}

    rows, traces, cases = [], {}, {}

    def add_row(rid, key, x, passed, group, title, who, cfacts, flags, kv, tabs, note=None, metrics=None):
        cases[rid] = {"group": group, "title": title, "who": who, "facts": cfacts, "chips": []}
        rows.append({"id": rid, "case": rid, "key": key, "x": x, "pass": passed, "sev": "none" if passed else "fail", "note": note,
                     "flags": flags, "metrics": metrics or [], "kv": kv})
        traces[rid] = {"tabs": tabs}

    # ---- R: the incident run (ten proposed calls, two approval attempts, the re-submitted call)
    first = [r for r in audit if r["kind"] == "policy.decision" and not r["record"]["recheck_of"]]
    assert len(first) == len(timeline) == len(scn["step"]), "one first-pass decision per scenario step"
    agent = f"{scn['agent']['principal']} acting for {scn['agent']['acting_for']}"
    for t, st, drec in zip(timeline, scn["step"], first):
        e = E[f"step-{t['n']:02d}"]
        rec = drec["record"]
        related = [r for r in audit if r["record"].get("decision_id") == rec["decision_id"]]
        rid = e["id"]
        out_rec = next((r["record"] for r in related if r["kind"] == "tool.executed"), None)
        inp = B.card(B.kv("Request", B.quote(f"{t['action']} on {t['resource']} in {t['environment']}"), B.small(f"proposed by {agent}")),
                     B.kv("Context", B.line("Time", code(t["at"])), B.line("Why the agent asked", t["why"]),
                          B.line("Arguments", code(json.dumps(st.get("arguments", {})))),
                          B.line("Diagnosis evidence", "not needed below high risk" if t["evidence"] is None else f"{t['evidence']} from {', '.join(t['evidence_signals'] or []) or 'no signals'}")),
                     title="Input", sub="What the agent proposed, from `scenario.toml`.")
        outp = B.card(B.kv("Decision", B.chips([(t["decision"], TONE[t["decision"]])]), B.line("Expected", code(e["expect"])),
                           B.line("Expected rule", code(e["expect_rule"])), B.line("Matched rules", ", ".join(f"`{m}`" for m in t["matched_rules"]) or "none")),
                      B.kv("Enforcement", B.line("Gateway outcome", code(t["status"])),
                           B.line("Constraints applied", ", ".join(f"`{c}`" for c in t["constraints_applied"]) or "none"),
                           B.line("Tool output", code(json.dumps(out_rec["output"])) if out_rec else "the tool was never called")),
                      title="Output", sub="What the gateway decided and did, read from `decisions.jsonl`.")
        checks = B.card(B.kv("Checks (expectations.json)", B.row_flags("Note")), title="Checks",
                        sub="Expected decision and rule come from `scenario.toml`; enforcement means the gateway's outcome matches the decision.")
        add_row(rid, "R", e["expect"], e["passed"], group_of(e["expect_rule"]), f"{t['action']} · {t['resource'].split('/')[1]} · {t['environment']}", agent,
                [["Time", t["at"][11:19]], ["Why", t["why"]]],
                [["Decision as expected", e["decision_ok"]], ["Matched the expected rule", e["rule_ok"] if e["expect_rule"] else None],
                 ["Enforced as decided", e["enforced_ok"]]],
                [["Expected", e["expect"]], ["Actual", e["actual"]], ["Rule", ", ".join(t["matched_rules"]) or "—"], ["Outcome", t["status"]],
                 ["Time", t["at"][11:19]]],
                {"result": [B.grid(inp, outp), checks], "decision": decision_cards(rec),
                 "audit": audit_tab(related, "The decision and, when the call ran, the execution record, chained by hash."),
                 "source": source_tab([("Proposed call", "scenario.toml", f"step {t['n']}: action, resource, arguments, expect"),
                                       ("Policy", "config/policy.toml", f"version {rec['policy_version']}"),
                                       ("Decision", f"runs/{run_id}/decisions.jsonl", f"seq {', '.join(str(r['seq']) for r in related)}"),
                                       ("Timeline row", f"runs/{run_id}/timeline.json", f"n = {t['n']}"),
                                       ("Check", f"runs/{run_id}/expectations.json", f"id = {rid}")])},
                note=None if e["passed"] else f"expected {e['expect']}, got {e['actual']}")

    req = next(r for r in audit if r["kind"] == "approval.requested")
    for i, a in enumerate(exp["approvals"], 1):
        e = E[f"approval-{i}"]
        recs = [req] + [r for r in audit if r["kind"] in ("approval.rejected", "approval.granted") and r["record"]["approver"] == a["approver"]]
        rr = req["record"]
        res_card = B.card(B.kv("Approval attempt", B.quote(f"{a['approver']} approves {rr['approval_id']}"),
                               B.small(f"at {a['at'][11:19]} · requested by {rr['requested_by']} · approver role {rr['approver_role']}")),
                          B.kv("Outcome", B.chips([(a["outcome"], TONE[a["outcome"]])]), B.line("Expected", code(a["expect"])), B.line("Gate said", a["reason"])),
                          title="Input and output", sub="An approval is a separate gate: it binds a human decision to one exact request.")
        bind = B.card(B.kv("Binding", B.line("Request fingerprint", code(rr["request_fingerprint"])), B.line("Decision", code(rr["decision_id"])),
                           B.line("Approver role", code(rr["approver_role"])), B.line("Expires", code(rr["expires_at"]))),
                      title="What the approval is bound to", sub="From the `approval.requested` record.")
        add_row(e["id"], "R", e["expect"], e["passed"], "gate", f"approval by {a['approver']}", "a human (or not) answering the approval request",
                [["Time", a["at"][11:19]], ["Approval", rr["approval_id"]]],
                [["Outcome as expected", e["decision_ok"]]],
                [["Expected", e["expect"]], ["Actual", e["actual"]], ["Rule", "approval gate"], ["Outcome", a["reason"]], ["Time", a["at"][11:19]]],
                {"result": [B.grid(res_card, B.card(B.kv("Checks (expectations.json)", B.row_flags("Note")), title="Checks"))],
                 "decision": [bind], "audit": audit_tab(recs, "The approval request and this attempt."),
                 "source": source_tab([("Approver and time", "scenario.toml", f"[[approval]] {i}"),
                                       ("Records", f"runs/{run_id}/decisions.jsonl", f"seq {', '.join(str(r['seq']) for r in recs)}"),
                                       ("Check", f"runs/{run_id}/expectations.json", f"id = {e['id']}")])})

    e = E["resume"]
    rechk = next(r for r in audit if r["kind"] == "policy.decision" and r["record"]["recheck_of"])
    exe = next(r for r in audit if r["kind"] == "tool.executed" and r["record"]["decision_id"] == rechk["record"]["decision_id"])
    res_card = B.card(B.kv("Request", B.quote("re-submit the approved rollback"), B.small(f"by {agent} at {rechk['time'][11:19]}")),
                      B.kv("Outcome", B.chips([(e["actual"], TONE.get(e["actual"], ""))]), B.line("Expected", code(e["expect"])),
                           B.line("Policy re-check", code(rechk["record"]["decision"])), B.line("Approved by", code(exe["record"]["approved_by"])),
                           B.line("Tool output", code(json.dumps(exe["record"]["output"])))),
                  title="Input and output", sub="The gateway checks the binding, then re-evaluates policy at the time of use.")
    add_row("resume", "R", e["expect"], e["passed"], "gate", "re-submitted approved call", agent,
            [["Time", rechk["time"][11:19]], ["Re-check of", rechk["record"]["recheck_of"]]],
            [["Outcome as expected", e["decision_ok"]]],
            [["Expected", e["expect"]], ["Actual", e["actual"]], ["Rule", ", ".join(rechk["record"]["matched_rules"])], ["Outcome", e["actual"]],
             ["Time", rechk["time"][11:19]]],
            {"result": [B.grid(res_card, B.card(B.kv("Checks (expectations.json)", B.row_flags("Note")), title="Checks"))],
             "decision": decision_cards(rechk["record"]), "audit": audit_tab([rechk, exe], "The re-check decision and the execution, chained by hash."),
             "source": source_tab([("Resume time", "scenario.toml", "[resume]"), ("Records", f"runs/{run_id}/decisions.jsonl", f"seq {rechk['seq']}, {exe['seq']}"),
                                   ("Check", f"runs/{run_id}/expectations.json", "id = resume")])})

    # ---- S: the context sweep (the same production rollback under eight contexts)
    for i, (s, c) in enumerate(zip(sweep, scn["sweep"]["case"]), 1):
        e = E[f"sweep-{i}"]
        varied = [f"{k} = {c[k]!r}" for k in ("environment", "time", "severity", "state", "acting_for", "resource", "evidence") if k in c and not (k == "environment" and c[k] == "production")]
        res_card = B.card(B.kv("Context", B.quote(s["context"]), B.line("What changed", ", ".join(f"`{v}`" for v in varied) or "nothing: the baseline"),
                               B.line("Held constant", "the agent, the tool and the request; full evidence unless stated")),
                          B.kv("Decision", B.chips([(s["decision"], TONE[s["decision"]])]), B.line("Expected", code(e["expect"])),
                               B.line("Rule", code(s["rule"])), B.line("Reason (audit view)", s["reason"]),
                               B.line("Diagnosis evidence", str(s["evidence"]) if s["evidence"] is not None else "—")),
                          title="Input and output", sub="The sweep asks the policy engine directly; nothing is executed.")
        add_row(e["id"], "S", e["expect"], e["passed"], group_of(e["expect_rule"]), s["context"], "the production rollback of payment-service, re-asked",
                [["Varies", ", ".join(varied) or "nothing (baseline)"]],
                [["Decision as expected", e["decision_ok"]], ["Matched the expected rule", e["rule_ok"] if e["expect_rule"] else None]],
                [["Expected", e["expect"]], ["Actual", e["actual"]], ["Rule", s["rule"]], ["Outcome", "evaluated only"], ["Time", "—"]],
                {"result": [B.grid(res_card, B.card(B.kv("Checks (expectations.json)", B.row_flags("Note")), title="Checks"))],
                 "decision": [B.card(B.kv("Reason", B.quote(s["reason"])), B.line("Matched", code(s["rule"])), title="Decision",
                                     sub="The sweep records the decision and its reason; it writes no audit records.")],
                 "audit": [B.chip("evaluated in isolation: the sweep writes nothing to the incident's audit log")],
                 "source": source_tab([("Context", "scenario.toml", f"[[sweep.case]] {i}"), ("Decision", f"runs/{run_id}/sweep.json", f"entry {i}"),
                                       ("Check", f"runs/{run_id}/expectations.json", f"id = {e['id']}")])},
                note=None if e["passed"] else f"expected {e['expect']}, got {e['actual']}")

    # ---- L1 / L3 / L4: every recorded test and subtest (L2, the invariants, follows as one row per invariant)
    LAYER_KEY = {"L1": "T", "L3": "G", "L4": "R"}
    LAYER_FILE = {"L1": "tests/test_l1_policy.py", "L2": "tests/test_l2_invariants.py", "L3": "tests/test_l3_gateway.py",
                  "L4": "tests/test_l4_replay.py"}
    tmap, counters = {}, Counter()
    for t in tests["results"]:
        if t["layer"] == "L2":
            continue
        counters[t["layer"]] += 1
        rid = f"{t['layer']}-{counters[t['layer']]:02d}"
        tmap[f"{t['test']}:{t['case']}"] = rid
        ok = t["status"] == "pass"
        name = t["test"].removeprefix("test_").replace("_", " ")
        title = t["case"] if t["test"] == "test_decision_table" else (f"{name} · {t['case']}" if t["case"] else name)
        rule, x, req_q = t.get("expect_rule"), t.get("expect") or ("PASS"), None
        if t["test"] == "test_decision_table":
            req_q = (f"{t['principal']}{' acting for ' + t['acting_for'] if t['acting_for'] else ''}: "
                     f"{t['action']} on {t['resource']} in {t['environment']}")
        res_card = B.card(B.kv("Test", B.quote(title), *([B.line("Request", req_q)] if req_q else []),
                               B.line("Layer", f"{t['layer']} · {t['layer_name']}"), B.line("Test", code(f"{t['suite']}.{t['test']}"))),
                          B.kv("Result", B.chips([("passed" if ok else t["status"], "ok" if ok else "bad")]),
                               *([B.line("Expected decision", code(t["expect"])), B.line("Expected rule", code(rule))] if t.get("expect") else []),
                               *([B.line("Failure", code(t["message"]))] if t["message"] else [])),
                          title="Input and output", sub="Recorded by `python3 -m authz.verify` from `python3 -m unittest discover -s tests -v`.")
        add_row(rid, LAYER_KEY[t["layer"]], x, ok, group_of(rule) if t["test"] == "test_decision_table" else t["layer"].lower(), title,
                LAYER_FILE[t["layer"]], [["Test", t["test"]]], [["Test passed", ok]],
                [["Expected", x], ["Actual", x if ok else t["message"]], ["Rule", rule or "—"], ["Outcome", t["status"]], ["Time", "—"]],
                {"result": [B.grid(res_card, B.card(B.kv("Checks (tests.json)", B.row_flags("Note")), title="Checks"))],
                 "decision": [B.chip("a test evaluates the policy engine or the gateway directly; see the Input & output tab")],
                 "audit": [B.chip("tests build a fresh world; nothing is written to the incident's audit log")],
                 "source": source_tab([("Test", LAYER_FILE[t["layer"]], f"{t['suite']}.{t['test']}"),
                                       ("Result", f"runs/{run_id}/tests.json", f"{t['test']} · {t['case'] or '(no subtests)'}")])},
                note=None if ok else t["message"])

    # ---- L2: the 14 named invariants (recorded by the run, and asserted case by case by the test suite)
    l2 = [t for t in tests["results"] if t["layer"] == "L2" and t["invariant"]]
    for v in inv:
        ts_ = [t for t in l2 if t["invariant"] == v["id"]]
        t_ok = bool(ts_) and all(t["status"] == "pass" for t in ts_)
        ok = v["passed"] and t_ok
        for t in ts_:
            tmap[f"{t['test']}:{t['case']}"] = v["id"]
        cases_tbl = B.table(["Case", "In the run", "In the tests"],
                            [[B.cell(("text", c["case"])), B.cell(("pill", "pass" if c["passed"] else "fail", "ok" if c["passed"] else "bad")),
                              B.cell(("pill", "pass" if any(t["case"].endswith(c["case"]) and t["status"] == "pass" for t in ts_) else "fail",
                                      "ok" if any(t["case"].endswith(c["case"]) and t["status"] == "pass" for t in ts_) else "bad"))]
                             for c in v["cases"]])
        res_card = B.card(B.kv("Invariant", B.quote(f"{v['id']} · {v['name']}"), B.line("Check", code("authz/invariants.py"))),
                          B.kv("Result", B.chips([("holds" if ok else "broken", "ok" if ok else "bad")]),
                               B.line("Cases", f"{sum(c['passed'] for c in v['cases'])} of {len(v['cases'])} hold")),
                          title="Invariant", sub="Every case builds its own fresh world (or replays the scenario), so no case depends on another.")
        add_row(v["id"], "V", "holds", ok, "invariant", v["name"], "authz/invariants.py", [["Invariant", v["id"]]],
                [["Holds in the run (invariants.json)", v["passed"]], ["Every case passes in the test suite (tests.json)", t_ok]],
                [["Expected", "holds"], ["Actual", "holds" if ok else "broken"], ["Rule", "—"], ["Outcome", "pass" if ok else "fail"],
                 ["Time", "—"], ["Cases", str(len(v["cases"]))]],
                {"result": [res_card, B.card(cases_tbl, title="Cases", sub="The named cases of this invariant, as recorded.")],
                 "decision": [B.chip("an invariant is a property of the policy and the gateway, not one decision")],
                 "audit": [B.chip("invariants build a fresh world; nothing is written to the incident's audit log")],
                 "source": source_tab([("Property", "authz/invariants.py", v["id"]), ("Run result", f"runs/{run_id}/invariants.json", v["id"]),
                                       ("Test result", f"runs/{run_id}/tests.json", f"{LAYER_FILE['L2']} · {v['id']}")])},
                note=None if ok else "invariant broken")

    # ---- facts: every number the page prints
    facts = kit.Facts()
    add = facts.add
    S = f"{rel}/"
    KEYS = ("R", "S", "T", "V", "G")
    by = {k: [r for r in rows if r["key"] == k] for k in KEYS}
    add("run.id", run_id, source=rel)
    add("run.filed", run_id[:10], source=rel)
    add("policy.version", man["policy_version"], source=f"{S}manifest.json")
    add("checks.all", len(rows), unit="checks", source="expectations.json + tests.json + invariants.json",
        derivation="every recorded check: incident run, context sweep, policy tests and invariants")
    add("checks.passed", sum(r["pass"] for r in rows), rows={"run": run_id, "ids": [r["id"] for r in rows if r["pass"]]},
        derivation="checks whose recorded outcome matched the expected one", source=S)
    failed = [r["id"] for r in rows if not r["pass"]]
    add("checks.failed", len(failed), rows={"run": run_id, "ids": failed} if failed else None, derivation="checks that did not match", source=S)
    add("checks.all_pass", not failed, source=S)
    names = {"R": "incident run and replay", "S": "context sweep", "T": "L1 policy tests", "V": "L2 invariants", "G": "L3 gateway tests"}
    for k, rs in by.items():
        ok = [r["id"] for r in rs if r["pass"]]
        add(f"{k}.n", len(rs), source=S, derivation=f"rows of the {names[k]}")
        add(f"{k}.pass", len(ok), rows={"run": run_id, "ids": ok}, derivation=f"{names[k]} checks that passed", source=S)
        add(f"{k}.kn", f"{len(ok)}/{len(rs)}", source=S)
    add("calls.proposed", facts_j["tool_calls_proposed"], source=f"{S}facts.json")
    add("decisions.total", facts_j["decisions_total"], source=f"{S}facts.json", derivation="policy decisions in the audit log, including the re-check")
    add("calls.executed", facts_j["executed"], source=f"{S}facts.json")
    add("calls.blocked", facts_j["blocked"], source=f"{S}facts.json")
    for d, n in facts_j["decisions_by_type"].items():
        add(f"dec.{d}", n, source=f"{S}facts.json", rows={"run": run_id, "ids": [f"step-{t['n']:02d}" for t in timeline if t["decision"] == d]},
            derivation=f"first-pass decisions of type {d}")
    add("audit.records", facts_j["audit_records"], source=f"{S}decisions.jsonl")
    add("audit.valid", facts_j["audit_chain_valid"], source=f"{S}facts.json")
    add("tamper.detected", facts_j["tamper_detected"], source=f"{S}facts.json")
    ev = facts_j["production_rollback_attempts"]
    add("evidence.first", ev[0]["evidence"], source=f"{S}facts.json → production_rollback_attempts")
    add("evidence.final", ev[-1]["evidence"], source=f"{S}facts.json → production_rollback_attempts")
    floor = next(r["when"]["evidence_score.lt"] for r in policy["rule"] if r["id"] == "F2-insufficient-evidence-high-risk-write")
    add("evidence.floor", floor, display=f"{floor:.2f}", source="config/policy.toml → F2")
    add("final.version", facts_j["payment_service_production_version"], source=f"{S}facts.json")
    add("inv.total", facts_j["invariants_total"], source=f"{S}invariants.json")
    add("inv.passed", facts_j["invariants_passed"], source=f"{S}invariants.json")
    add("tests.methods", tests["tests"], source=f"{S}tests.json")
    add("tests.checks", tests["checks"], source=f"{S}tests.json", derivation="tests and subtests")
    add("tests.passed", tests["passed"], source=f"{S}tests.json")
    add("layers.n", len(tests["layers"]), source=f"{S}tests.json")
    add("layers.pass", sum(v["failed"] == 0 for v in tests["layers"].values()), source=f"{S}tests.json")
    add("inv.cases", sum(len(v["cases"]) for v in inv), source=f"{S}invariants.json", derivation="named cases across the 14 invariants")
    add("sweep.n", facts_j["sweep_cases"], source=f"{S}sweep.json")
    for d, n in facts_j["sweep_decisions"].items():
        add(f"sweep.{d}", n, source=f"{S}sweep.json")
    summ = ver["summary"]
    add("verify.ok", summ["ok"], source=f"{S}verification.json")
    add("verify.replay", summ["replay"], source=f"{S}verification.json")
    add("verify.chain", summ["audit_chain"], source=f"{S}verification.json")
    add("verify.deterministic", summ["deterministic"], source=f"{S}verification.json")
    rp_files = ver["replay"]
    add("replay.files", len(rp_files), source=f"{S}verification.json")
    add("replay.same", sum(f["same"] for f in rp_files), source=f"{S}verification.json")
    add("python", man["python"], source=f"{S}manifest.json")
    add("rules.count", len(policy["rule"]), source="config/policy.toml")
    add("inputs.count", len(man["hashes"]), source=f"{S}manifest.json")

    # cross-checks: the page is not built unless the recorded files agree with each other
    xc = []
    assert facts_j["invariants_passed"] == sum(v["passed"] for v in inv), "facts.json vs invariants.json"
    xc.append("facts.json invariant totals equal invariants.json")
    assert facts_j["audit_records"] == len(audit), "facts.json vs decisions.jsonl"
    xc.append("facts.json audit record count equals decisions.jsonl")
    assert Counter(t["decision"] for t in timeline) == Counter(facts_j["decisions_by_type"]), "timeline vs facts decision counts"
    xc.append("facts.json decision counts equal timeline.json")
    assert exp["checks"] == sum(1 for r in by["R"] if not r["id"].startswith("L4-")) + len(by["S"]), "every expectation is a row"
    xc.append("every expectation in expectations.json is a row on this page")
    l2_entries = [t for t in tests["results"] if t["layer"] == "L2"]
    assert tests["checks"] == len(by["T"]) + len(by["G"]) + sum(1 for r in by["R"] if r["id"].startswith("L4-")) + len(l2_entries), \
        "every test result is on this page"
    assert all(t["invariant"] or t["test"] == "test_exactly_14_named_invariants" for t in l2_entries), "every L2 case maps to an invariant"
    xc.append("every test and subtest in tests.json is on this page (L2 cases inside their invariant)")
    assert len(inv) == 14 and [v["id"] for v in inv] == [f"AUTHZ-INV-{n:02d}" for n in range(1, 15)], "exactly 14 named invariants"
    xc.append("exactly 14 named invariants, AUTHZ-INV-01 to AUTHZ-INV-14")

    # ---- datasets
    def dec_md(d):
        return f"**{d}**"
    story = [{"at": audit[0]["time"][11:19], "title": f"Datadog alert for `{audit[0]['record']['service']}`, {audit[0]['record']['severity']}", "tone": "info"},
             {"at": audit[1]["time"][11:19], "title": f"identity established: `{audit[1]['record']['principal']}` acting for `{audit[1]['record']['acting_for']}`", "tone": "info"}]
    for t in timeline:
        story.append({"at": t["at"][11:19], "title": f"`{t['action']}` {t['resource'].split('/')[1]} ({t['environment']}) → {dec_md(t['decision'])} · {t['status']}",
                      "sub": t["why"], "tone": EVT[t["decision"]], "row": f"step-{t['n']:02d}", "run": run_id})
    for i, a in enumerate(exp["approvals"], 1):
        story.append({"at": a["at"][11:19], "title": f"approval by `{a['approver']}` → **{a['outcome']}**", "sub": a["reason"],
                      "tone": "ok" if a["outcome"] == "approved" else "bad", "row": f"approval-{i}", "run": run_id})
    story.append({"at": rechk["time"][11:19], "title": f"re-submitted call: binding ok, policy re-check → **{exe['record']['output']}**".replace("{", "").replace("}", "").replace("'", ""),
                  "tone": "ok", "row": "resume", "run": run_id})
    link = lambda rid, cells: {"row": rid, "run": run_id, "cells": cells}  # noqa: E731
    mark = lambda ok: "✓" if ok else "✕"  # noqa: E731
    datasets = {
        "systems": {"items": [["alert", "Datadog event", audit[0]["record"]["incident_id"]], ["user", "Agent identity", scn["agent"]["principal"]],
                              ["shield", "Gateway (PEP)", "authz/pep.py"], ["target", "Policy engine (PDP)", man["policy_version"]],
                              ["check", "Approval gate", "authz/approvals.py"], ["box", "Simulated tools", "Kubernetes, logs"], ["lock", "Audit log", "hash-chained"]],
                    "label": "What every call touches"},
        "suites": {"head": ["Suite", "Checks", "Passed", "Failed", "What it checks"],
                   "rows": [[names[k].capitalize(), str(len(by[k])), str(sum(r["pass"] for r in by[k])), str(sum(not r["pass"] for r in by[k])), what]
                            for k, what in (("R", "each call's decision, rule and enforcement against `scenario.toml`, both approval attempts, the re-check, "
                                                  "and the L4 replay tests: the run re-created byte for byte and its published facts re-derived"),
                                            ("S", f"the same production rollback under {len(sweep)} contexts, against the expected decision and rule"),
                                            ("T", "L1: the decision table, the freeze case, the combining rule, conditions, evidence, fingerprint, caller view"),
                                            ("V", f"L2: the {len(inv)} named production invariants, {sum(len(v['cases']) for v in inv)} named cases"),
                                            ("G", "L3: the real enforcement path, with tool call counters, credentials and fail-closed policy errors"))]},
        "story": {"events": story},
        "decisions": {"head": ["", "Time", "Agent proposes", "Evidence", "Decision", "Rule", "Outcome"],
                      "rows": [link(f"step-{t['n']:02d}", [mark(E[f"step-{t['n']:02d}"]["passed"]), t["at"][11:19],
                                                           f"`{t['action']}` {t['resource'].split('/')[1]} · {t['environment']}",
                                                           "–" if t["evidence"] is None else str(t["evidence"]), dec_md(t["decision"]),
                                                           " ".join(f"`{m}`" for m in t["matched_rules"]) or "–", t["status"].replace("_", " ")]) for t in timeline]},
        "sweep": {"head": ["", "Context", "Expected", "Decision", "Rule", "Reason (audit view)"],
                  "rows": [link(f"sweep-{i}", [mark(E[f"sweep-{i}"]["passed"]), s["context"], E[f"sweep-{i}"]["expect"], dec_md(s["decision"]), f"`{s['rule']}`", s["reason"]])
                           for i, s in enumerate(sweep, 1)]},
        "tests": {"head": ["", "Row", "Test", "Expected", "Rule"],
                  "rows": [link(r["id"], [mark(r["pass"]), f"`{r['id']}`", cases[r["id"]]["title"], r["kv"][0][1], f"`{r['kv'][2][1]}`"])
                           for r in by["T"] if cases[r["id"]]["group"] != "l1"]},
        "invariants": {"head": ["", "Id", "Invariant", "Cases", "In the run", "In the tests"],
                       "rows": [link(r["id"], [mark(r["pass"]), r["id"], cases[r["id"]]["title"], r["kv"][5][1], mark(r["flags"][0][1]), mark(r["flags"][1][1])])
                                for r in by["V"]]},
        "gateway": {"head": ["", "Row", "Gateway test"],
                    "rows": [link(r["id"], [mark(r["pass"]), f"`{r['id']}`", cases[r["id"]]["title"]]) for r in by["G"]]},
        "replay": {"head": ["", "Row", "Replay test"],
                   "rows": [link(r["id"], [mark(r["pass"]), f"`{r['id']}`", cases[r["id"]]["title"]]) for r in by["R"] if r["id"].startswith("L4-")]},
        "chain": {"head": ["Seq", "Time", "Kind", "Prev", "Hash", "Link ok", "Hash ok"],
                  "rows": [[str(c["seq"]), c["time"][11:19], f"`{c['kind']}`", f"`{c['prev']}`", f"`{c['hash']}`", mark(c["prev_ok"]), mark(c["hash_ok"])] for c in ver["chain"]]},
        "lineage": {"head": ["Stage", "File", "Carries"],
                    "rows": [["Scenario", "`authz_poc/scenario.toml`", f"the incident, {len(timeline)} proposed calls, approvals, sweep contexts, expected outcomes"],
                             ["Policy", "`authz_poc/config/*.toml`", "roles (RBAC), relationships and delegation (ReBAC), guard rules (ABAC), the action catalog"],
                             ["Run", f"`{rel}/decisions.jsonl`", "the hash-chained audit log: every decision, approval and execution"],
                             ["Run", f"`{rel}/timeline.json` · `sweep.json` · `invariants.json`", "each call, each sweep context, each invariant"],
                             ["Checks", f"`{rel}/expectations.json`", "every recorded outcome against the scenario's expected one"],
                             ["Tests", f"`{rel}/tests.json`", "every test and subtest of the four layers in `tests/`"],
                             ["Verification", f"`{rel}/manifest.json` · `verification.json`", "input hashes, the chain re-hashed, the replay"],
                             ["This page", "`results/lab-console.evidence.json`", "every number above, with its source"]]},
    }
    # ---- drill-downs
    metrics = {}
    for k in KEYS:
        groups = sorted({cases[r["id"]]["group"] for r in by[k]})
        metrics[f"pass-{k}"] = {"rows": [r["id"] for r in by[k] if r["pass"]],
                                "breakdown": [{"label": GROUP[g], "count": sum(1 for r in by[k] if r["pass"] and cases[r["id"]]["group"] == g),
                                               "rows": [r["id"] for r in by[k] if r["pass"] and cases[r["id"]]["group"] == g]} for g in groups]}
    metrics["decisions-R"] = {"rows": [f"step-{t['n']:02d}" for t in timeline],
                              "breakdown": [{"label": d, "count": n, "rows": [f"step-{t['n']:02d}" for t in timeline if t["decision"] == d]}
                                            for d, n in facts_j["decisions_by_type"].items()]}
    # ---- artifacts
    frozen = [[f, h[:16], (POC / f).exists() and hashlib.sha256((POC / f).read_bytes()).hexdigest() == h] for f, h in man["hashes"].items()]
    detail = []  # the replay compares files, not rows: the summary carries it
    artifacts = {"frozen": frozen, "models": [],
                 "run_meta": [["Run", run_id], ["Policy version", man["policy_version"]], ["Python", man["python"]], ["Platform", man["platform"]],
                              ["Agent", "scripted (no model): the POC is about the policy boundary"], ["Transcript", f"{len(transcript)} lines, transcript.txt"]],
                 "checks": [f"invariants {summ['invariants']['passed']}/{summ['invariants']['total']} · replay {summ['replay']} · "
                            f"audit chain {summ['audit_chain']} · deterministic {str(summ['deterministic']).lower()}"] + xc,
                 "replay": {"reproduced": sum(f["same"] for f in ver["replay"]), "rows": len(ver["replay"]),
                            "mismatches": sum(not f["same"] for f in ver["replay"]), "detail": detail}}
    x_order = ["ALLOW", "ALLOW_WITH_CONSTRAINTS", "ALLOW_WITH_APPROVAL", "DENY", "rejected", "approved", "executed", "holds", "PASS"]
    xs = [x for x in x_order if any(r["x"] == x for r in rows)] + sorted({r["x"] for r in rows} - set(x_order))
    data = {"factor": {"values": xs, "primary": xs[0]}, "groups": GROUP, "cases": cases,
            "runs": [{"id": run_id, "label": f"Run {run_id}", "kind": "recorded", "path": rel,
                      "note": "scripted agent, simulated tools, real policy engine and gateway", "rows": rows}],
            "traces": {run_id: traces}, "datasets": datasets, "hypotheses": {}, "failures": {}, "metrics": metrics, "failure_classes": [],
            "artifacts": artifacts, "generated": {"runs": [run_id], "primary": run_id}}
    return data, facts


def main() -> None:
    run_id = sys.argv[1] if len(sys.argv) > 1 else "2026-09-29-recorded"
    data, facts = collect(run_id)
    res = kit.build(SPEC, data, facts, OUT, out_json=OUT.with_name("lab-console.evidence.json"), generated_by="tools/build_lab_console.py")
    ev = res["evidence"]
    rows = ev["runs"][0]["rows"]
    print(f"{res['out'].relative_to(ROOT)} ({res['bytes'] // 1024} KB) · {len(rows)} checks · {sum(r['pass'] for r in rows)} passed")


if __name__ == "__main__":
    main()
