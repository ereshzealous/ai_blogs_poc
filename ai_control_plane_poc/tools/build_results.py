"""Generate docs/source/report.src.md, the T4 run report, from the published run directory.

    python3 tools/build_results.py          (then tools/build_docs.py builds it with the other documents)

Every value in the report is read from control_plane_poc/runs/<PUBLISHED>/; nothing is typed. Headline numbers use {{fact}}
tokens so the builder records where they are used; tables are rendered from the scenario records directly. The build fails
if any check in checks.json did not pass, or if any hash chain in the run (control-plane change logs, runtime audit logs)
does not verify.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "control_plane_poc"
RUN_ID = (POC / "runs" / "PUBLISHED").read_text().strip()
RUN = POC / "runs" / RUN_ID
sys.path.insert(0, str(ROOT / "tools"))
from ledger import rows as ledger_rows  # noqa: E402

GROUP = {"baseline": "CORE", "core": "CORE", "capability": "CAPABILITY", "boundary": "BOUNDARIES", "negative-control": "NEGATIVE CONTROL",
         "governor": "GOVERN THE GOVERNOR"}
LEDGER_ROWS = 40



def outcome_label(outcome: str) -> str:
    """How a document prints a recorded outcome. The run records P11's embedded baseline as `broken` and keeps it; the
    documents add what that break is, so it cannot be read as a failure of the POC."""
    return "BROKEN — expected negative control" if outcome == "broken" else outcome.upper()

def load(p: Path):
    return json.loads(p.read_text())


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def chain_ok(p: Path) -> bool:
    prev = "0" * 64
    for row in jl(p):
        body = {k: v for k, v in row.items() if k != "hash"}
        h = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        if row["prev"] != prev or h != row["hash"]:
            return False
        prev = row["hash"]
    return True


def table(head: list[str], rows: list[list]) -> str:
    esc = lambda c: str(c).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows])


STATUS = {"SUPPORTED": "Supported", "QUALIFIED": "**Qualified**", "NEGATIVE CONTROL": "**Negative control**", "NOT SUPPORTED": "**Not supported**",
          "ARGUED": "*Argued*", "NOT TESTED": "*Not tested*"}


def evidence_claims() -> int:
    """The Evidence Check's claims table, generated between its markers from proof/claims.toml and the proof pack's
    results.json: claim → proof → checks (with their statuses) → raw evidence → status. The observed values are {{facts}}."""
    import tomllib

    claims = tomllib.loads((ROOT / "proof" / "claims.toml").read_text())["claims"]
    res = load(ROOT / "evidence" / "runs" / RUN_ID / "results.json")
    traced = {c["id"]: c for c in res["claims"]}
    checks = {c["id"]: c for c in (json.loads(x) for x in (ROOT / "evidence" / "runs" / RUN_ID / "checks.jsonl").read_text().splitlines())}
    proof_of = lambda x: "P" + x.split("-R")[1] if int(x.split("-R")[1]) <= 12 else "evidence"  # noqa: E731
    rows = []
    for cl in claims:
        st = [checks[k] for k in cl.get("checks", [])]
        summ = Counter(c["finding"] for c in st)
        ck = (" · ".join(f"{n} {f}" for f, n in summ.items()) + f" ({', '.join(cl['checks'][:1])}{'…' if len(st) > 1 else ''})") if st else "—"
        ck += "".join(f"; bound: {b} {checks[b]['finding']}" for b in cl.get("bound_checks", []))
        raw = sorted({e.split(f"runs/{RUN_ID}/")[-1] for e in traced[cl["id"]]["evidence"]})
        ev = ", ".join(f"`{e}`" for e in raw[:2]) + (f" +{len(raw) - 2}" if len(raw) > 2 else "") if raw else cl.get("rests_on", "—")
        status = STATUS[cl["class"]] + (f" ({cl['qualification']})" if cl.get("qualification") else "")
        proofs = ", ".join(dict.fromkeys(proof_of(x) for x in cl.get("experiments", []))) or "—"
        rows.append([f"`{cl['id']}`", cl["statement"], proofs, ck, cl["observed"], ev, status])
    legend = ("Status: **Supported**, the recorded evidence shows it; **Qualified**, shown within a stated bound that a proof check measures; "
              "**Negative control**, the property broke by design when its safeguard was removed; **Not supported**, a stronger claim the evidence "
              "contradicts; *Argued*, reasoned in the editions but not tested; *Not tested*, outside this POC. Every status is tested against its checks "
              "by `make evidence`; prose is never the source of a status.")
    body = "\n".join([legend, "", table(["#", "Claim (either edition)", "Proof", "Proof checks", "Observed", "Raw evidence", "Status"], rows)])
    src = ROOT / "docs" / "source" / "evidence.src.md"
    s = src.read_text()
    a, b = s.index("<!-- claims:begin -->") + len("<!-- claims:begin -->"), s.index("<!-- claims:end -->")
    src.write_text(s[:a] + "\n" + body + "\n" + s[b:])
    return len(rows)


def main() -> None:
    checks, man = load(RUN / "checks.json"), load(RUN / "manifest.json")
    if not all(c["passed"] for c in checks):
        raise SystemExit("build_results: a check failed; the report is not generated for a failing run")
    chains = sorted(RUN.glob("scenarios/*/state/controlplane/changelog.jsonl")) + sorted(RUN.glob("scenarios/*/state/runtime/*/audit.jsonl"))
    bad = [str(p.relative_to(RUN)) for p in chains if not chain_ok(p)]
    if bad:
        raise SystemExit(f"build_results: hash chain broken in {bad}")
    scen = {s["id"]: s for s in (load(p) for p in RUN.glob("scenarios/*/scenario.json"))}
    roles = load(RUN / "scenarios.json")
    led = ledger_rows(RUN)
    pack = ROOT / "evidence" / "runs" / RUN_ID / "results.json"
    pc = load(pack)["check_counts"] if pack.exists() else None
    m2 = dict(scen["P2-C-central-change"]["measures"])
    out = [
        "---",
        "title: T4 Run Report: AI Control Plane",
        "subtitle: Every observed value, every assertion and every recorded step of the published run, generated from the run directory.",
        "byline: T4 · Production AI Engineering",
        "kicker: Production AI Engineering · T4 · Run report",
        f"filed: {RUN_ID[:10]}",
        "run: Recorded run {{run.id}}",
        "tags: Evidence, Run report, AI Control Plane",
        "---",
        "",
        "## Run",
        "",
        table(
            ["Field", "Value"],
            [
                ["Run", "`{{run.id}}`"],
                ["Python", man["python"]],
                ["Agents", man["agents"]],
                ["Agent code sha256", f"`{man['agents_code_sha256']}`"],
                ["Scenarios", "{{run.scenarios}} across {{run.experiments}} proofs"],
                ["Scenario assertions", "{{checks.passed}} of {{checks.total}} passed"],
                ["Proof checks (pae-proof/v1)", f"{pc['checks']}: {pc['pass']} pass, {pc['fail']} fail (LIMITATION OBSERVED), {pc['expected_failure']} expected failure (negative control)" if pc else "not packed"],
                ["Hash chains verified", str(len(chains))],
                ["Ledger rows", f"{len(led)} (every recorded event, `evidence/runs/{RUN_ID}/ledger.jsonl`)"],
                ["Real", "; ".join(man["real"])],
                ["Simulated", "; ".join(man["simulated"])],
            ],
        ),
        "",
        "Three counts, never merged: *scenario assertions* are the checks each scenario makes on its own record; *proof checks* are the "
        "pae-proof/v1 comparisons over facts (`proof/experiments.toml`); unit tests are counted by `make test`.",
        "",
        "### Frozen configuration",
        "",
        table(["File", "sha256"], [[f"`config/{k}`", f"`{v[:16]}…`"] for k, v in man["config_sha256"].items()]),
        "",
        "## P2 · before → after",
        "",
        "The core proof, with the three things it holds fixed. P2 fails if any of them changes (`control_plane_poc/tests/test_cheating.py`).",
        "",
        table(
            ["", "Before", "After"],
            [
                ["Agent source sha256", f"`{m2['agent_sha_before']}`", f"`{m2['agent_sha_after']}`"],
                ["Runtime process", f"`{m2['runtime_pid_before']}`", f"`{m2['runtime_pid_after']}`"],
                ["Request hash", f"`{m2['request_hash_before']}`", f"`{m2['request_hash_after']}`"],
                ["Control plane version", f"`{m2['before_version']}`", f"`{m2['after_version']}`"],
                ["Decision", m2["before_decision"], m2["after_decision"]],
                ["Deploy system: restarts", str(m2["restarts_after_v1"]), str(m2["restarts_after_v2"])],
                ["Agent edits · redeploys", "", f"{m2['agent_edits']} · {m2['redeploys']}"],
            ],
        ),
        "",
        "## Scenarios",
        "",
        table(
            ["Group", "Scenario", "Outcome", "Assertions", "Observed"],
            [[GROUP[r["role"]], f"`{x['id']}`", outcome_label(x["outcome"]), x["checks"], scen[x["id"]]["observed"]] for r in roles for x in r["scenarios"]],
        ),
    ]
    for r in roles:
        for x in r["scenarios"]:
            s = scen[x["id"]]
            out += ["", f"### {s['id']}", "", f"*{GROUP[r['role']]} · {r['property']}*", "", f"**Question.** {s['question']}", "",
                    f"**Expected.** {s['expected']}  ", f"**Observed.** {s['observed']}  ", f"**Outcome.** {outcome_label(s['outcome'])}"
                    + (f" · {s['where']}" if s["where"] else ""), ""]
            rows = [w for w in led if w["scenario_id"] == s["id"]]
            shown = rows[:LEDGER_ROWS]
            out += [f"**Step ledger** ({len(rows)} rows" + (f"; the first {LEDGER_ROWS} shown, all in `ledger.jsonl`" if len(rows) > LEDGER_ROWS else "") + ")", "",
                    table(["Step · tick", "Source · process", "Agent · request", "Version · rule", "Event", "Decision", "Approval · cost", "System of record", "Audit"],
                          [[f"{w['step']} · t{w['logical_time']}", " · ".join(v for v in (w["source"], w["runtime_pid"]) if v),
                            " · ".join(v for v in (w["agent"], w["request_sha256"] and f"req {w['request_sha256']}") if v),
                            " · ".join(v for v in (w["cp_version"], w["rule"]) if v), " · ".join(v for v in (w["audit_event"], w["tool"], w["model"]) if v),
                            w["decision"], " · ".join(str(v) for v in (w["approval"], w["budget"] is not None and f"${w['budget']}") if v),
                            w["system_of_record"], w["audit_hash"] or ""] for w in shown]), ""]
            out += ["**Measures**", "", table(["Measure", "Value"], [[k, f"`{v}`"] for k, v in s["measures"]]), "",
                    f"**Assertions** ({x['checks']})", "", table(["Assertion", "Result"], [[c["check"], "pass" if c["passed"] else "**FAIL**"] for c in s["checks"]]), "",
                    "**Proof card**", "", "```text", s["proof"], "```"]
    out += ["", "## Reproduce", "", "```bash", "make verify       # rerun every proof from source; identical to this run (process ids masked)",
            "make evidence     # PROOF VERIFICATION of the published run", "make verify-all   # the final gate", "make console      # the Lab Console",
            "```", ""]
    (ROOT / "docs" / "source" / "report.src.md").write_text("\n".join(out))
    print(f"report.src.md: {len(scen)} scenarios, {len(checks)} assertions, {len(chains)} chains verified, {len(led)} ledger rows")
    print(f"evidence.src.md: {evidence_claims()} claims")


if __name__ == "__main__":
    main()
