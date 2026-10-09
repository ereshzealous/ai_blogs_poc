"""PROOF VERIFICATION for T3 (pae-proof/v1 §7): one command that checks the shipped evidence holds together.

    uv run hitl verify [run-id]      (default: the published run, else the newest run)
"""

from __future__ import annotations

import filecmp
import json
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

from hitl import freeze as FZ
from hitl.proofpack import EVIDENCE, POC, ROOT, _toml
from hitl.scenarios import SCENARIOS, run_all
from hitl.suite import run_suite

sys.path.insert(0, str(ROOT / "vendor"))
from evidence_kit import proof  # noqa: E402
from evidence_kit.facts import Facts  # noqa: E402


def _run_id(arg: str | None) -> str:
    if arg:
        return arg
    pub = EVIDENCE / "published.json"
    if pub.exists():
        return json.loads(pub.read_text())["run_id"]
    return sorted(p.name for p in (EVIDENCE / "runs").iterdir())[-1]


def verify(run_id: str | None = None) -> proof.Report:
    rid = _run_id(run_id)
    run = EVIDENCE / "runs" / rid
    R = proof.Report()
    man = json.loads((run / "manifest.json").read_text())
    res = json.loads((run / "results.json").read_text())
    probs = proof.validate_schema(man, proof.schema("manifest")) + proof.validate_schema(res, proof.schema("results"))
    probs += [p for line in (run / "checks.jsonl").read_text().splitlines() for p in proof.validate_schema(json.loads(line), proof.schema("check"))]
    probs += proof.validate_schema(_toml("experiments.toml"), proof.schema("experiments")) + proof.validate_schema(_toml("claims.toml"), proof.schema("claims"))
    R.add("Manifest", not probs, f"run {rid}; schemas: manifest, results, check, experiments, claims", probs)

    raw = sorted((run / "raw" / "tests").glob("HITL-T*.json"))
    broken = [p.name for p in raw if not json.loads(p.read_text())["audit_chain_intact"]]
    scen = sorted((run / "raw" / "scenarios").rglob("scenario.json"))
    sbroken = [str(p.parent.relative_to(run)) for p in scen if not json.loads(p.read_text())["metrics"].get("audit_chain_intact")]
    errors = [str(p.parent.relative_to(run)) for p in scen if json.loads(p.read_text())["error"]]
    want = len(SCENARIOS) * 3
    R.add("Raw evidence", len(raw) == 30 and not broken and len(scen) == want and not sbroken and not errors,
          f"{len(scen)}/{want} scenario runs and {len(raw)} conformance traces; audit chains intact; no scenario crashed", broken + sbroken + errors)

    fz = FZ.check()
    frozen = json.loads((run / "prereg" / "FREEZE.json").read_text())
    same = all((run / "prereg" / f).read_bytes() == (POC / "proof" / f).read_bytes() for f in ("preregistration.toml", "experiments.toml"))
    before = frozen["frozen_at"] <= man["started_at"]
    R.add("Preregistration", fz["ok"] and same and before and frozen["guarded"] == man["preregistration"]["guarded_sha256"],
          f"frozen {frozen['frozen_at']}, run started {man['started_at']}; guarded files unchanged; code changed since freeze: "
          f"{', '.join(man['preregistration']['code_changed_since_freeze']) or 'none'} (see prereg/DEVIATIONS.md)",
          fz["changed_guarded"] + ([] if same else ["the run's prereg copy differs from proof/"]) + ([] if before else ["frozen after the run started"]))

    F = Facts()
    for fid, f in res["facts"].items():
        F.add(fid, f["value"], f.get("display"), **{k: v for k, v in f.items() if k not in ("value", "display")})
    exps, checks = proof.evaluate(_toml("experiments.toml"), F)
    rec = [json.loads(l) for l in (run / "checks.jsonl").read_text().splitlines()]
    same = [c["status"] for c in checks] == [c["status"] for c in rec]
    st = [c["status"] for c in checks]
    broken = [c["id"] for c in checks if c["status"] == "FAIL" and c["kind"] not in ("hypothesis", "confirmatory", "measurement")]
    R.add("Experiment checks", same and not broken,
          f"{len(checks)} checks: {st.count('PASS')} pass, {st.count('FAIL')} fail ({sum(c['finding'] == 'NOT SUPPORTED' for c in checks)} hypotheses not supported, "
          f"reported), {st.count('EXPECTED_FAILURE')} expected failure", broken)

    claims, cprobs = proof.trace(_toml("claims.toml"), exps, checks)
    med = (ROOT / "medium" / "human-in-the-loop-medium.md")
    if med.exists():
        heads = set(re.findall(r"^#+ (.+)$", med.read_text(), re.M))
        cprobs += [f"claim {c['id']}: article section '{a}' not found" for c in claims for a in c.get("article", []) if not a.startswith("fig:") and a not in heads]
    R.add("Claim mappings", not cprobs, f"{len(claims)} claims traced to checks and article sections", cprobs)

    n, bad = proof.verify_sha256sums(run / "SHA256SUMS", run)
    R.add("Integrity", not bad, f"{n} files match SHA256SUMS", bad)

    with tempfile.TemporaryDirectory() as tmp:
        again = Path(tmp) / "raw"
        outs = run_suite(Path(tmp) / "work", raw=again / "tests")
        run_all(Path(tmp) / "scen", raw=again / "scenarios")
        diff = [p.name for p in raw if not filecmp.cmp(p, again / "tests" / p.name, shallow=False)]
        mine = sorted(p.relative_to(run / "raw" / "scenarios") for p in (run / "raw" / "scenarios").rglob("*") if p.is_file())
        theirs = sorted(p.relative_to(again / "scenarios") for p in (again / "scenarios").rglob("*") if p.is_file())
        diff += [str(p) for p in mine if p not in theirs or not filecmp.cmp(run / "raw" / "scenarios" / p, again / "scenarios" / p, shallow=False)]
        diff += [f"extra {p}" for p in theirs if p not in mine]
        rep = json.loads((run / "test-report.json").read_text())
        changed = [o.id for o, t in zip(outs, rep["tests"]) if ("pass" if o.passed else "fail") != t["result"]]
    R.add("Replay", not diff and not changed, f"EXACT: re-running reproduces {len(raw)} conformance traces and {len(mine)} scenario files byte for byte",
          diff[:10] + changed)

    nc = json.loads((EVIDENCE / "negative-control" / "results.json").read_text())
    nprob = proof.validate_schema(nc, proof.schema("negative-control"))
    R.add("Negative control", not nprob and nc["result"] == "EXPECTED_FAILURE" and nc["harness_completed"],
          f"{nc['result']}; harness completed: {nc['harness_completed']}", nprob)

    uses = ROOT / "docs" / "evidence-uses.json"
    if uses.exists():
        u = json.loads(uses.read_text())
        wrong = [k for k, v in u.items() if k not in res["facts"] or res["facts"][k]["value"] != v["value"]]
        claimed = {f for c in _toml("claims.toml")["claims"] for f in c.get("facts", [])}
        roots = {"global", "all", "story", "tests", "api"} | {x[:2] for x in SCENARIOS} | set(SCENARIOS)
        unmapped = [k for k in u if k.split(".")[0] in roots and k not in claimed and not k.endswith((".held", ".assertions"))]
        R.add("Publication facts", not wrong and not unmapped, f"{len(u)} facts printed by the articles match the run; result facts belong to a claim",
              wrong + [f"unmapped: {x}" for x in unmapped])
    else:
        R.add("Publication facts", None, "articles not built yet")

    hits = proof.scan([p for p in list(run.rglob("*")) + list((ROOT / "medium").glob("*")) + list((ROOT / "technical").glob("*")) if p.is_file()],
                      ROOT, allow=[r"tok-[a-z]+"])
    R.add("Secret scan", not hits, "no credentials or private paths in the evidence or the articles (demo tokens allowed)", [str(h) for h in hits[:5]])
    out = EVIDENCE / "verification"
    out.mkdir(exist_ok=True)
    (out / "verification.txt").write_text(R.text())
    (out / "verification.json").write_text(json.dumps(R.json(run_id=rid), indent=1))
    return R
