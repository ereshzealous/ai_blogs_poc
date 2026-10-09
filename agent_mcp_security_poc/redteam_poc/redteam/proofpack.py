"""Record a run as a pae-proof/v1-style package and verify it.

    redteam proof [--run-id ID]   -> evidence/runs/<ID>/{manifest.json, results.json, facts.json, checks.jsonl, summary.md, SHA256SUMS}
    redteam verify [ID]           -> re-run, compare byte for byte (EXACT replay), recompute facts, evaluate checks

The run is fully deterministic (no model, no network, fake clock), so replay is EXACT: a second run reproduces results.json
byte for byte. The checks are the preregistered hypotheses, evaluated against the run's facts.
"""
from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

from redteam import freeze
from redteam.base import POC, canonical
from redteam.runner import run_all

RUNS = POC / "evidence" / "runs"
PUBLISHED = POC / "evidence" / "published.json"
PREREG = POC / "proof" / "preregistration.toml"
OPS = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b, ">": lambda a, b: a > b,
       ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}


def _metric(out, exp: dict, arm: str, metric: str) -> int:
    f = out.facts
    if metric == "system_compromised_attacks":
        return f["compromised"][arm]["attacks"]
    if metric == "controls_contained":
        return f["n_controls"] - f["compromised"][arm]["controls"]
    if metric == "within_residual":
        return f["within_residual"][arm]
    if metric == "system_compromised":
        # summed over the experiment's scenarios for this arm
        ids = exp["scenarios"]
        if ids == ["*"]:
            return f["compromised"][arm]["attacks"]
        return sum(1 for sid in ids if out.matrix[sid][arm])
    raise KeyError(metric)


def build_checks(out) -> list[dict[str, Any]]:
    pre = tomllib.loads(PREREG.read_text())
    checks = []
    for exp in pre["experiments"]:
        for i, h in enumerate(exp["hypotheses"], 1):
            observed = _metric(out, exp, h["arm"], h["metric"])
            ok = OPS[h["op"]](observed, h["value"])
            if h["kind"] == "control":
                status = "EXPECTED_FAILURE" if ok else "FAIL"
                finding = "EXPECTED FAILURE" if ok else "FAIL"
            elif h["kind"] == "hypothesis":
                status, finding = ("PASS", "PASS") if ok else ("FAIL", "NOT SUPPORTED")
            elif h["kind"] == "measurement":
                # a measurement reports what was observed; a declared limitation reads LIMITATION OBSERVED, not a failure
                status, finding = ("PASS", "PASS") if ok else ("FAIL", h.get("finding", "NOT OBSERVED"))
            else:  # invariant
                status, finding = ("PASS", "PASS") if ok else ("FAIL", "FAIL")
            checks.append({"id": f"{exp['id']}-C{i:02d}", "experiment": exp["id"], "arm": h["arm"],
                           "kind": h["kind"], "metric": h["metric"], "op": h["op"], "value": h["value"],
                           "observed": observed, "status": status, "finding": finding, "text": h["text"]})
    return checks


def summary_md(out, checks: list[dict]) -> str:
    f = out.facts
    p = ["# T6 run summary", "",
         f"- attacks: {f['n_attacks']}  ·  controls: {f['n_controls']}  ·  attack classes: {len(f['attack_classes'])}",
         f"- model-manipulated attacks: {f['manipulated_attacks']}/{f['n_attacks']}",
         f"- system compromised — A: {f['compromised']['A']['attacks']}/{f['n_attacks']}, "
         f"B: {f['compromised']['B']['attacks']}/{f['n_attacks']}, C: {f['compromised']['C']['attacks']}/{f['n_attacks']}",
         f"- controls all pass: {f['controls_all_pass']}", "",
         "| check | arm | metric | observed | op/value | finding |", "|---|---|---|---|---|---|"]
    for c in checks:
        p.append(f"| {c['id']} | {c['arm']} | {c['metric']} | {c['observed']} | {c['op']} {c['value']} | {c['finding']} |")
    npass = sum(1 for c in checks if c["status"] == "PASS")
    nef = sum(1 for c in checks if c["status"] == "EXPECTED_FAILURE")
    nfail = sum(1 for c in checks if c["status"] == "FAIL")
    p += ["", f"**{len(checks)} checks: {npass} pass, {nfail} fail, {nef} expected failure.**"]
    return "\n".join(p) + "\n"


def record(run_id: str = "2026-10-07-recorded") -> Path:
    chk = freeze.check()
    if not chk["ok"]:
        raise SystemExit(f"refusing to record: guarded files changed since the freeze: {chk['changed_guarded']}\n"
                         f"log them in proof/DEVIATIONS.md and run `redteam freeze` again.")
    out = run_all()
    checks = build_checks(out)
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"schema": "pae-proof/v1", "series": "Production AI Engineering", "article_id": "T6",
                "poc": "t6-redteam-poc", "run_id": run_id, "scenario": "agent-mcp-security",
                "runtime_mode": "deterministic-scripted-model", "clock": "2026-11-30T09:20:00Z",
                "environment": {"model": "scripted-worst-case-compliant", "network": "disabled", "randomness": "none"},
                "frozen_at": chk["frozen_at"], "replay_level": "EXACT"}
    results = {"run_id": run_id, "facts": out.facts, "matrix": out.matrix, "scenarios": out.scenarios}
    facts = out.facts

    _write(run_dir / "manifest.json", manifest)
    _write(run_dir / "results.json", results)
    _write(run_dir / "facts.json", facts)
    (run_dir / "checks.jsonl").write_text("\n".join(canonical(c) for c in checks) + "\n")
    (run_dir / "summary.md").write_text(summary_md(out, checks))
    _sha256sums(run_dir)
    PUBLISHED.write_text(json.dumps({"published": run_id}, indent=1) + "\n")
    return run_dir


def _write(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def _sha256sums(run_dir: Path) -> None:
    lines = []
    for p in sorted(run_dir.glob("*")):
        if p.name == "SHA256SUMS":
            continue
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (run_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def published_id() -> str:
    return json.loads(PUBLISHED.read_text())["published"] if PUBLISHED.exists() else "2026-10-07-recorded"


def verify(run_id: str | None = None) -> bool:
    run_id = run_id or published_id()
    run_dir = RUNS / run_id
    if not run_dir.exists():
        print(f"PROOF VERIFICATION\n\nRun directory       FAIL  ({run_dir} missing)")
        return False
    # 1. integrity: SHA256SUMS
    integrity = _check_sums(run_dir)
    # 2. replay: re-run and compare results.json byte for byte (EXACT)
    out = run_all()
    live_results = json.dumps({"run_id": run_id, "facts": out.facts, "matrix": out.matrix, "scenarios": out.scenarios},
                              indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    stored_results = (run_dir / "results.json").read_text()
    replay = (live_results == stored_results)
    # 3. checks recompute and match
    live_checks = build_checks(out)
    stored_checks = [json.loads(l) for l in (run_dir / "checks.jsonl").read_text().splitlines() if l.strip()]
    checks_match = (canonical(live_checks) == canonical(stored_checks))
    npass = sum(1 for c in live_checks if c["status"] == "PASS")
    nef = sum(1 for c in live_checks if c["status"] == "EXPECTED_FAILURE")
    nfail = sum(1 for c in live_checks if c["status"] == "FAIL")
    # a FAIL of an invariant check is a real failure; control EXPECTED_FAILUREs are fine
    # Per pae-proof/v1: a FAIL of a hypothesis or measurement check is a reported finding (NOT SUPPORTED / LIMITATION
    # OBSERVED), not a verification failure. Only invariant/replay/control/implementation FAILs break verification.
    bad_invariants = [c["id"] for c in live_checks
                      if c["status"] == "FAIL" and c["kind"] in ("invariant", "replay", "control", "implementation")]

    print("PROOF VERIFICATION\n")
    print(f"Integrity (SHA256)   {'PASS' if integrity else 'FAIL'}")
    print(f"Replay (EXACT)       {'PASS' if replay else 'FAIL'}")
    print(f"Checks recompute     {'PASS' if checks_match else 'FAIL'}")
    print(f"Experiment checks    {'PASS' if not bad_invariants else 'FAIL'}   "
          f"{len(live_checks)} checks: {npass} pass, {nfail} fail, {nef} expected failure")
    ok = integrity and replay and checks_match and not bad_invariants
    print(f"\n{'VERIFIED' if ok else 'NOT VERIFIED: ' + ', '.join(bad_invariants)}")
    return ok


def _check_sums(run_dir: Path) -> bool:
    sums = run_dir / "SHA256SUMS"
    if not sums.exists():
        return False
    for line in sums.read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        p = run_dir / name
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            return False
    return True
