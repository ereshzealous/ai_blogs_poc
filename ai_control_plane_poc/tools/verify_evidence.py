"""PROOF VERIFICATION of the published run (Proof Contract §7). Reads the shipped evidence; runs no proof and no model.

    uv run --project control_plane_poc python tools/verify_evidence.py      (make evidence)
        -> evidence/verification/verification.{txt,json}

Sections: Manifest · Raw evidence · Facts recompute · Experiment checks · Claim mappings · Integrity · Replay ·
Negative control · Publication facts · Secret scan. A FAIL check with finding LIMITATION OBSERVED is a result (the
qualification the articles print), not a verification failure: verification asks whether the evidence holds together.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "control_plane_poc"
sys.path.insert(0, str(ROOT / "vendor" / "kit5"))
sys.path.insert(0, str(ROOT / "tools"))
from evidence_kit import proof  # noqa: E402  (5.2.0, vendor/kit5)
from proof_facts import collect  # noqa: E402

from acp.common import read_json  # noqa: E402
from acp.facts import build_facts  # noqa: E402

# a claim's class (what a reader sees) and the kit verdicts that bear it out (proof/claims.toml)
CLASSES = {
    "SUPPORTED": {"supported", "implementation"},
    "QUALIFIED": {"supported"},
    "NEGATIVE CONTROL": {"control"},
    "NOT SUPPORTED": {"contradicted"},
    "ARGUED": {"limitation"},
    "NOT TESTED": {"limitation"},
}
# printed facts that describe the run rather than state a result: they need no claim
DESCRIPTIVE = ("run.", "checks.", "outcome.", "raw.", "replay.", "proof.")
DESCRIPTIVE_SUFFIX = (".checks", ".outcome", ".assertions_passed", ".assertions_total")
SCENARIO_FILES = ("scenario.json", "transcript.jsonl", "volatile.json")
RUN_FILES = ("manifest.json", "facts.json", "checks.json", "summary.md", "proof.txt", "scenarios.json")


def main() -> int:
    rep = proof.Report()
    pub = json.loads((ROOT / "evidence" / "published.json").read_text())
    run_id = pub["run_id"]
    run = POC / "runs" / run_id
    pack = ROOT / "evidence" / "runs" / run_id

    # ---- manifest ---------------------------------------------------------------------------------------------------
    man = json.loads((pack / "manifest.json").read_text())
    probs = [f"manifest: {p}" for p in proof.validate_schema(man, proof.schema("manifest"))]
    probs += [f"published.json: {p}" for p in proof.validate_schema(pub, proof.schema("published"))]
    pointer = (POC / "runs" / "PUBLISHED").read_text().strip()
    if pointer != run_id:
        probs.append(f"control_plane_poc/runs/PUBLISHED names {pointer}, evidence/published.json {run_id}")
    if proof.sha256_file(pack / "results.json") != pub["results_sha256"]:
        probs.append("results.json differs from the hash recorded at promote")
    if man["agents_code_sha256"] != read_json(run / "manifest.json")["agents_code_sha256"]:
        probs.append("agent source hash differs from the run's manifest")
    rep.add("Manifest", not probs, f"{run_id} · {man['article_id']} · {man['runtime_mode'].split(':')[0]} · agents sha256 {man['agents_code_sha256'][:12]}", probs)

    # ---- raw evidence -----------------------------------------------------------------------------------------------
    roles = read_json(run / "scenarios.json")
    sids = [s["id"] for r in roles for s in r["scenarios"]]
    probs = [f"missing {f}" for f in RUN_FILES if not (run / f).exists()]
    for sid in sids:
        d = run / "scenarios" / sid
        probs += [f"{sid}: missing {f}" for f in SCENARIO_FILES if not (d / f).exists()]
        if not (d / "state").is_dir():
            probs.append(f"{sid}: missing state/ (systems of record, control plane, runtime audit)")
    extra = sorted({p.name for p in (run / "scenarios").iterdir()} - set(sids))
    probs += [f"scenario directory not in scenarios.json: {x}" for x in extra]
    rep.add("Raw evidence", not probs, f"{len(sids)} scenarios across {len(roles)} proofs · each with record, transcript, volatile ids and full state", probs)

    # ---- the run's facts recompute from its scenario records -----------------------------------------------------------
    recs = [read_json(run / "scenarios" / sid / "scenario.json") for sid in sids]
    order = {sid: i for i, sid in enumerate(read_json(run / "manifest.json")["scenarios"])}
    again = build_facts(run, sorted(recs, key=lambda r: order[r["id"]]))
    shipped = read_json(run / "facts.json")
    fd = sorted(k for k in set(again) | set(shipped) if again.get(k) != shipped.get(k))
    rep.add("Facts recompute", not fd, f"{len(shipped)} facts rebuilt from the scenario records and raw state", fd)

    # ---- experiment checks and claims -------------------------------------------------------------------------------
    facts, _ = collect(run_id)
    spec = tomllib.loads((ROOT / "proof" / "experiments.toml").read_text())
    probs = [f"experiments.toml: {p}" for p in proof.validate_schema(spec, proof.schema("experiments"))]
    exps, checks = proof.evaluate(spec, facts)
    res = json.loads((pack / "results.json").read_text())
    if [c["id"] for c in checks] != res["checks"] or [x["result"] for x in exps] != [x["result"] for x in res["experiments"]]:
        probs.append("recomputed checks differ from results.json")
    jl = [json.loads(x) for x in (pack / "checks.jsonl").read_text().splitlines()]
    if [(c["id"], c["status"]) for c in jl] != [(c["id"], c["status"]) for c in checks]:
        probs.append("checks.jsonl differs from the recomputed checks")
    if sum(x["counts"][s] for x in exps for s in proof.STATUSES) != len(checks):
        probs.append("experiment totals differ from check totals")
    fails = [c for c in checks if c["status"] == "FAIL"]
    probs += [f"{c['id']} FAIL reads {c['finding']}: a guarantee did not hold" for c in fails if c["finding"] == "FAIL"]
    c = res["check_counts"]
    found = ", ".join(f"{n} {f}" for f, n in res["finding_counts"].items())
    rep.add(
        "Experiment checks",
        not probs,
        f"{c['experiments']} experiments · {c['checks']} checks: {c['pass']} pass, {c['fail']} fail ({found or 'none'}), {c['expected_failure']} expected failure",
        probs,
    )

    claims_spec = tomllib.loads((ROOT / "proof" / "claims.toml").read_text())
    problems = [f"claims.toml: {p}" for p in proof.validate_schema(claims_spec, proof.schema("claims"))]
    traced, tp = proof.trace(claims_spec, exps, checks)
    problems += tp
    C = {x["id"]: x for x in checks}
    for cl in traced:
        if cl.get("class") not in CLASSES or cl["verdict"] not in CLASSES[cl["class"]]:
            problems.append(f"claim {cl['id']}: class {cl.get('class')!r} does not go with verdict {cl['verdict']!r}")
        if cl.get("class") == "QUALIFIED":
            bound = cl.get("bound_checks", [])
            if not cl.get("qualification") or not bound:
                problems.append(f"claim {cl['id']}: QUALIFIED needs a qualification and the bound_checks that measure it")
            problems += [f"claim {cl['id']}: bound check {b} is not a LIMITATION OBSERVED" for b in bound if C.get(b, {}).get("finding") != "LIMITATION OBSERVED"]
        if cl.get("class") == "NOT SUPPORTED":
            problems += [f"claim {cl['id']}: NOT SUPPORTED rests on {k}, which passed" for k in cl.get("checks", []) if C[k]["status"] != "FAIL"]
    uses = json.loads((ROOT / "docs" / "evidence-uses.json").read_text()) if (ROOT / "docs" / "evidence-uses.json").exists() else {}
    claimed = {f for cl in claims_spec["claims"] for f in cl.get("facts", [])}
    unmapped = sorted(k for k in uses if k not in claimed and not k.startswith(DESCRIPTIVE) and not k.endswith(DESCRIPTIVE_SUFFIX))
    problems += [f"printed fact not mapped to a claim: {k}" for k in unmapped]
    ev = ROOT / "results" / "ai-control-plane-evidence.md"
    if ev.exists():
        text = ev.read_text()
        problems += [f"claim {cl['id']} is not in the Evidence Check" for cl in traced if cl["id"] not in text]
    by_class = {k: sum(cl.get("class") == k for cl in traced) for k in CLASSES}
    rep.add(
        "Claim mappings",
        bool(traced) and not problems,
        f"{len(traced)} claims · " + " · ".join(f"{k.lower()} {n}" for k, n in by_class.items() if n) + f" · {len(uses)} printed facts checked",
        problems,
    )

    # ---- integrity, replay, negative control -------------------------------------------------------------------------
    n, bad = proof.verify_sha256sums(pack / "SHA256SUMS", ROOT)
    listed = {line.split("  ", 1)[1] for line in (pack / "SHA256SUMS").read_text().splitlines() if line.strip()}
    raw = {p.relative_to(ROOT).as_posix() for p in run.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    bad += [f"raw file not in SHA256SUMS: {r}" for r in sorted(raw - listed)]
    rep.add("Integrity", not bad, f"{n} files match SHA256SUMS, the raw run included (a checksum list, not a signature)", bad)

    rp = json.loads((pack / "replay.json").read_text())
    ok = rp["equivalent"] and rp["run_id"] == run_id and rp["fresh_model_calls"] == 0
    rep.add(
        "Replay",
        ok,
        f"{rp['replay_level']} · {rp['classes']['DETERMINISTIC_EQUIVALENT']} files byte-identical, {rp['classes']['NONDETERMINISTIC']} equal with raw process "
        f"ids masked, {sum(rp['classes'][k] for k in ('REGRESSION', 'MODEL_OUTPUT_VARIATION', 'METHODOLOGY_CHANGE'))} different",
        rp["differences"],
    )

    nc = json.loads((pack / "negative-control" / "results.json").read_text())
    probs = proof.validate_schema(nc, proof.schema("negative-control"))
    if not nc["harness_completed"]:
        probs.append("the negative control did not complete (a crash is not a proof)")
    rep.add(
        "Negative control",
        not probs and nc["result"] == "EXPECTED_FAILURE",
        f"{nc['safeguard_removed'].split(':')[0]} removed → property broken by design ({nc['result']}); test assertions {nc['test_assertions']}",
        probs,
    )

    # ---- publication facts --------------------------------------------------------------------------------------------
    # The two editions live in the chapter; the published POC folder (github.com/ereshzealous/ai_blogs_poc) ships the
    # evidence documents and docs/evidence-uses.json (every value the editions print) but not the editions themselves.
    editions = [ROOT / "medium" / "ai-control-plane-medium.md", ROOT / "technical" / "ai-control-plane-technical.md"]
    in_chapter = (ROOT / "medium").is_dir() or (ROOT / "technical").is_dir()
    built = [*(editions if in_chapter else []), *sorted((ROOT / "results").glob("*.md"))]
    probs = [f"{k}: printed {u['value']!r}, published {shipped[k]['value']!r}" for k, u in uses.items() if k in shipped and u["value"] != shipped[k]["value"]]
    for p in built:
        t = p.read_text() if p.exists() else ""
        if not t:
            probs.append(f"{p.relative_to(ROOT)}: not built")
        elif "{{" in t:
            probs.append(f"{p.relative_to(ROOT)}: unresolved {{{{fact}}}}")
        elif run_id not in t:
            probs.append(f"{p.relative_to(ROOT)}: does not name the published run {run_id}")
    lab = ROOT / "results" / "lab-console.evidence.json"
    if lab.exists() and run_id not in lab.read_text():
        probs.append(f"results/lab-console.evidence.json does not name {run_id}")
    rep.add("Publication facts", not probs, f"{len(uses)} printed facts equal the published run's; {len(built)} documents name {run_id}"
            + ("" if in_chapter else " (the editions are not in this folder; docs/evidence-uses.json carries what they print)"), probs)

    # ---- secret scan -------------------------------------------------------------------------------------------------
    paths = [p for p in [*(ROOT / "evidence").rglob("*"), *run.rglob("*"), *built, *(ROOT / "proof").glob("*")] if p.is_file() and p.suffix != ".pdf"]
    hits = proof.scan(paths, ROOT)
    rep.add("Secret scan", not hits, f"{len(paths)} published files scanned (credentials, keys, tokens, private paths, e-mail addresses)", [f"{h['file']}:{h['line']}: {h['kind']}" for h in hits])

    out = ROOT / "evidence" / "verification"
    out.mkdir(parents=True, exist_ok=True)
    (out / "verification.txt").write_text(rep.text())
    (out / "verification.json").write_text(json.dumps(rep.json(run_id=run_id), indent=1) + "\n")
    print(rep.text())
    return 0 if rep.verified else 1


if __name__ == "__main__":
    sys.exit(main())
