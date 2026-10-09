"""PROOF VERIFICATION of the published run (Proof Contract §7). Reads the shipped evidence; runs no experiment.

    uv run --project ops_poc python tools/verify_evidence.py      (make verify)  -> evidence/verification/verification.{txt,json}

Sections: Manifest · Raw evidence · Facts recompute · Experiment checks · Claim mappings · Integrity · Replay ·
Negative control · Preregistration · Publication facts · Secret scan. A FAIL whose finding is LIMITATION OBSERVED is a
result, not a verification failure: verification asks whether the evidence holds together.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "ops_poc"
sys.path.insert(0, str(ROOT / "vendor" / "kit5"))
sys.path.insert(0, str(ROOT / "tools"))
from evidence_kit import proof  # noqa: E402
from proof_facts import collect  # noqa: E402

CLASSES = {"SUPPORTED": {"supported", "implementation"}, "QUALIFIED": {"supported"}, "NEGATIVE CONTROL": {"control"},
           "NOT SUPPORTED": {"contradicted"}, "ARGUED": {"limitation"}, "NOT TESTED": {"limitation"}}
RUN_DIRS = ("scenarios", "negative-control")
RUN_FILES = ("manifest.json", "facts.json", "summary.md")
SLUG = "operating-ai-agents"


def main() -> int:
    rep = proof.Report()
    pub = json.loads((ROOT / "evidence" / "published.json").read_text())
    run_id = pub["run_id"]
    run = POC / "runs" / run_id
    pack = ROOT / "evidence" / "runs" / run_id

    man = json.loads((pack / "manifest.json").read_text())
    probs = [f"manifest: {p}" for p in proof.validate_schema(man, proof.schema("manifest"))]
    probs += [f"published.json: {p}" for p in proof.validate_schema(pub, proof.schema("published"))]
    if (POC / "runs" / "PUBLISHED").read_text().strip() != run_id:
        probs.append("ops_poc/runs/PUBLISHED and evidence/published.json disagree")
    if proof.sha256_file(pack / "results.json") != pub["results_sha256"]:
        probs.append("results.json differs from the hash recorded at promote")
    rep.add("Manifest", not probs, f"{run_id} · {man['article_id']} · {man['runtime_mode'].split(';')[0]}", probs)

    probs = [f"missing {f}" for f in RUN_FILES if not (run / f).exists()] + [f"missing {d}/" for d in RUN_DIRS if not (run / d).is_dir()]
    rows = sum(1 for p in run.rglob("*.jsonl") for _ in p.open())
    rep.add("Raw evidence", not probs, f"{sum(1 for p in run.rglob('*') if p.is_file())} files, {rows} JSONL records (rows, requests, timelines, decisions)", probs)

    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / run_id
        shutil.copytree(run, dst)
        (dst / "facts.json").unlink()
        (dst / "summary.md").unlink()
        code = f"import sys; sys.path.insert(0, {str(POC)!r}); from pathlib import Path; from agentops.run import aggregate; aggregate(Path({str(dst)!r}))"
        subprocess.run(["uv", "run", "--quiet", "--project", str(POC), "python", "-c", code], cwd=POC, check=True, capture_output=True)
        a = json.loads((run / "facts.json").read_text())
        b = json.loads((dst / "facts.json").read_text())
        diff = sorted(k for k in set(a) | set(b) if (a.get(k) or {}).get("value") != (b.get(k) or {}).get("value"))
    rep.add("Facts recompute", not diff, f"{len(a)} facts rebuilt from the raw run files in a scratch copy", diff[:20])

    facts, _ = collect(run_id)
    spec = tomllib.loads((ROOT / "proof" / "experiments.toml").read_text())
    exps, checks = proof.evaluate(spec, facts)
    res = json.loads((pack / "results.json").read_text())
    probs = []
    if [c["id"] for c in checks] != res["checks"]:
        probs.append("recomputed checks differ from results.json")
    probs += [f"{c['id']} FAIL reads FAIL: a guarantee did not hold" for c in checks if c["status"] == "FAIL" and c["finding"] == "FAIL"]
    c = res["check_counts"]
    found = ", ".join(f"{n} {f}" for f, n in res["finding_counts"].items())
    rep.add("Experiment checks", not probs, f"{c['experiments']} experiments · {c['checks']} checks: {c['pass']} pass, {c['fail']} fail ({found or 'none'}), "
                                            f"{c['expected_failure']} expected failure", probs)

    cspec = tomllib.loads((ROOT / "proof" / "claims.toml").read_text())
    traced, problems = proof.trace(cspec, exps, checks)
    C = {x["id"]: x for x in checks}
    for cl in traced:
        if cl.get("class") not in CLASSES or cl["verdict"] not in CLASSES[cl["class"]]:
            problems.append(f"claim {cl['id']}: class {cl.get('class')!r} does not go with verdict {cl['verdict']!r}")
        if cl.get("class") == "QUALIFIED":
            problems += [f"claim {cl['id']}: bound check {b} is not LIMITATION OBSERVED" for b in cl.get("bound_checks", [])
                         if C.get(b, {}).get("finding") != "LIMITATION OBSERVED"]
        problems += [f"claim {cl['id']}: fact {k} is not a fact of the run" for k in cl.get("facts", []) if k not in facts]
    uses_p = ROOT / "docs" / "evidence-uses.json"
    uses = json.loads(uses_p.read_text()) if uses_p.exists() else {}
    rep.add("Claim mappings", not problems, f"{len(traced)} claims traced to {len(exps)} experiments · {len(uses)} printed facts", problems)

    n, bad = proof.verify_sha256sums(pack / "SHA256SUMS", ROOT)
    listed = {line.split("  ", 1)[1] for line in (pack / "SHA256SUMS").read_text().splitlines() if line.strip()}
    raw = {p.relative_to(ROOT).as_posix() for p in run.rglob("*") if p.is_file() and "volatile" not in p.parts}
    bad += [f"raw file not in SHA256SUMS: {r}" for r in sorted(raw - listed)]
    rep.add("Integrity", not bad, f"{n} files match SHA256SUMS, the raw run included (a checksum list, not a signature)", bad[:20])

    rp = json.loads((pack / "replay.json").read_text())
    ok = rp["equivalent"] and rp["run_id"] == run_id and rp["fresh_model_calls"] == 0
    rep.add("Replay", ok, f"{rp['replay_level']} · {rp['classes']['DETERMINISTIC_EQUIVALENT']} files byte-identical, {rp['classes']['REGRESSION']} different", rp["differences"])

    nc = json.loads((pack / "negative-control" / "results.json").read_text())
    probs = proof.validate_schema(nc, proof.schema("negative-control"))
    if not nc["harness_completed"]:
        probs.append("the negative control did not complete (a crash is not a proof)")
    rep.add("Negative control", not probs and nc["result"] == "EXPECTED_FAILURE", f"{nc['safeguard_removed'].split(':')[0]} removed → {nc['result']}", probs)

    rep.add("Preregistration", facts.value("raw.prereg_changed") == 0, "frozen files unchanged since the freeze (ops_poc/experiments/FROZEN.sha256)")

    shipped = json.loads((run / "facts.json").read_text())
    derived = json.loads((ROOT / "docs" / "derived-facts.json").read_text())
    allf = {**shipped, **derived}
    probs = [f"{k}: printed {u['value']!r}, published {allf[k]['value']!r}" for k, u in uses.items() if k in allf and u["value"] != allf[k]["value"]]
    built = [ROOT / "medium" / f"{SLUG}-medium.md", ROOT / "technical" / f"{SLUG}-technical.md"]
    if not any(p.exists() for p in built):     # a public folder: the editions are published with the articles
        rep.add("Publication facts", None, "the editions are not part of this folder; they are published with the articles")
    else:
        for p in built:
            t = p.read_text() if p.exists() else ""
            if not t:
                probs.append(f"{p.relative_to(ROOT)}: not built")
            elif "{{" in t:
                probs.append(f"{p.relative_to(ROOT)}: unresolved {{{{fact}}}}")
            elif run_id not in t:
                probs.append(f"{p.relative_to(ROOT)}: does not name the published run")
        rep.add("Publication facts", not probs, f"{len(uses)} printed facts equal the published run's; {len(built)} editions name {run_id}", probs)

    paths = [p for p in [*(ROOT / "evidence").rglob("*"), *(ROOT / "proof").glob("*"), *built] if p.is_file() and p.suffix != ".pdf"]
    paths += [p for p in run.rglob("*") if p.is_file() and p.suffix in (".json", ".md")]
    hits = proof.scan(paths, ROOT, allow=[])
    rep.add("Secret scan", not hits, f"{len(paths)} published files scanned (credentials, keys, tokens, private paths, e-mail addresses)",
            [f"{h['file']}:{h['line']}: {h['kind']}" for h in hits[:20]])

    out = ROOT / "evidence" / "verification"
    out.mkdir(parents=True, exist_ok=True)
    (out / "verification.txt").write_text(rep.text())
    (out / "verification.json").write_text(json.dumps(rep.json(run_id=run_id), indent=1) + "\n")
    print(rep.text())
    return 0 if rep.verified else 1


if __name__ == "__main__":
    sys.exit(main())
