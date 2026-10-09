"""PROOF VERIFICATION (Proof Contract §7): does the shipped evidence of the published run hold together? Runs no proof.

    uv run python tools/verify_evidence.py [--run RUN] [--no-write]     (uv run pap verify, make verify)
        -> evidence/verification/verification.{txt,json}

Sections: Manifest · Raw evidence · Facts recompute · Experiment checks · Claim mappings · Integrity · Replay ·
Negative control · Published facts · README · Lab · Technical article · Medium article · Secret scan. A FAIL or EXPECTED_FAILURE check is a
result, not a verification failure; verification fails when the evidence does not hold together: a schema, a hash, a
recomputation, a pointer or a printed number disagrees. The articles live in the repository around the POC; in the POC
alone (the published package) their sections are N/A.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "vendor"))
sys.path.insert(0, str(ROOT / "tools"))
from evidence_kit import proof, publication  # noqa: E402  (5.2.0, vendor/)
from proof_facts import RUNS, collect, read, rows  # noqa: E402
import proof_pack  # noqa: E402
import replay_compare  # noqa: E402

# printed facts that describe the run rather than state a result: they need no claim
DESCRIPTIVE = ("run_id", "run_date", "wall_clock_s", "total_", "unit_tests", "env_", "count_", "replay", "prev_", "x_", "proof.", "raw.", "run.",
               "harness.", "R1_", "R2_", "R3_", "R4_", "R5_", "R6_", "R7_", "R8_", "R9_", "R10_", "R11_", "R12_", "R13_")
ARTICLES = {"Technical article": REPO / "technical" / "production-agentic-ai-platform-final-reference-architecture.md",
            "Medium article": REPO / "medium" / "production-agentic-ai-platform-medium.md"}
USES = REPO / "docs" / "evidence-uses.json"
FACTS = REPO / "docs" / "facts.json"
DIAGRAMS = REPO / "diagrams" / "manifest.json"
SCAN_ALLOW = [r"@example\.(?:com|org)", r"spiffe://"]


def headings(md: str) -> set[str]:
    return {re.sub(r"\s+\{#[^}]*\}$", "", h.strip()) for h in re.findall(r"^#{1,4} (.+)$", md, re.M)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="verify this run instead of the published one (a candidate before promotion)")
    ap.add_argument("--no-write", action="store_true")
    o = ap.parse_args()
    rep = proof.Report()
    add = rep.add

    def add_section(name, ok, detail="", problems=None):
        # a failing section reports what it found, not the sentence it failed to establish
        if ok is False:
            detail = f"{len(problems or [])} problem{'' if len(problems or []) == 1 else 's'}" + (" (first 20 listed)" if len(problems or []) > 20 else "")
        return add(name, ok, detail, problems)
    rep.add = add_section
    pub = read(ROOT / "evidence" / "published.json") if (ROOT / "evidence" / "published.json").exists() else None
    run_id = o.run or (pub["run_id"] if pub else None)
    if not run_id:
        raise SystemExit("no published run (evidence/published.json) and no --run")
    candidate = not pub or run_id != pub["run_id"]
    run = RUNS / run_id
    raw = run / "raw"

    # ---- manifest ---------------------------------------------------------------------------------------------------
    probs = []
    man, res = read(run / "manifest.json"), read(run / "results.json")
    probs += [f"manifest.json: {p}" for p in proof.validate_schema(man, proof.schema("manifest"))]
    probs += [f"results.json: {p}" for p in proof.validate_schema(res, proof.schema("results"))]
    jl = [json.loads(x) for x in (run / "checks.jsonl").read_text().splitlines() if x.strip()]
    probs += [f"checks.jsonl {c['id']}: {p}" for c in jl for p in proof.validate_schema(c, proof.schema("check"))]
    for n in ("experiments", "claims"):
        probs += [f"{n}.toml: {p}" for p in proof.validate_schema(tomllib.loads((run / "proof" / f"{n}.toml").read_text()), proof.schema(n))]
    if not candidate:
        probs += [f"published.json: {p}" for p in proof.validate_schema(pub, proof.schema("published"))]
        if proof.sha256_file(run / "results.json") != pub["results_sha256"]:
            probs.append("results.json differs from the hash recorded when it was promoted")
        pointer = (RUNS / "PUBLISHED").read_text().strip() if (RUNS / "PUBLISHED").exists() else None
        if pointer != run_id:
            probs.append(f"evidence/runs/PUBLISHED names {pointer}, evidence/published.json {run_id}")
        drift = [n for n in proof_pack.DEFS if (ROOT / "proof" / n).read_text() != (run / "proof" / n).read_text()]
        probs += [f"proof/{n} differs from the definitions the published pack was built with" for n in drift]
    rep.add("Manifest", not probs, f"{'candidate' if candidate else 'published'} run {run_id} · {man['article_id']} · {man['contract']} "
            f"({man['integrity']['proof_kit']}) · {len(jl)} checks; manifest, results, checks, experiments and claims match pae-proof/v1", probs)

    # ---- raw evidence, and what the files say independently of the harness -------------------------------------------
    facts, data = collect(run_id)
    raw_res = data["res"]
    F = lambda k: facts.value(k)  # noqa: E731
    probs = [f"raw/results.json: missing experiment {e}" for e in [f"R{i}" for i in range(1, 14)] if e not in {x["id"] for x in raw_res["experiments"]}]
    for e in raw_res["experiments"]:
        if not (raw / e["dir"]).is_dir():
            probs.append(f"missing {e['dir']}/")
    W = {e["id"]: e for e in raw_res["experiments"]}
    agree = [("R1 world.db rollbacks = R1.world", F("raw.rollbacks.R1"), W["R1"]["checks"][[c["id"] for c in W["R1"]["checks"]].index("R1.world")]["actual"][0]),
             ("R10 world.db rollbacks = lookup + resend + naive", F("raw.rollbacks.R10"), sum(W["R10"]["facts"][m]["rollbacks"] for m in ("lookup", "resend", "naive"))),
             ("audit chains that verify = audit chains", F("raw.audit_chains_verified"), F("raw.audit_chains")),
             ("distinct trace ids in R1 = 1", F("raw.r1_trace_ids"), 1)]
    probs += [f"{name}: {a} ≠ {b}" for name, a, b in agree if a != b]
    recorded_kills = sum(1 for rc in W["R9"]["facts"]["returncodes"] if rc == -9) + sum(1 for m in ("lookup", "resend", "naive") if W["R10"]["facts"][m]["sigkill"] == -9)
    rep.add("Raw evidence", not probs, f"{len(raw_res['experiments'])} experiment directories; recomputed from the raw files: {F('raw.audit_chains_verified')}/"
            f"{F('raw.audit_chains')} audit chains verify, R1 one trace, rollbacks per experiment equal the harness's; {F('raw.sigkills')} processes "
            f"SIGKILLed ({recorded_kills} recorded in results.json: R9's tampered-checkpoint kill is in its events only)", probs)

    # ---- facts recompute ----------------------------------------------------------------------------------------------
    shipped = res["facts"]
    again = {k: v for k, v in facts.to_json().items()}
    diff = sorted(k for k in again if k not in shipped or (again[k]["value"], again[k]["display"]) != (shipped[k]["value"], shipped[k]["display"]))
    diff += sorted(k for k in shipped if k not in again and not k.startswith("proof."))
    rep.add("Facts recompute", not diff, f"{len(shipped)} facts in results.json; {len(again)} recomputed from the raw files, every value equal", diff)

    # ---- experiment checks ------------------------------------------------------------------------------------------
    files, problems = proof_pack.pack(run_id, source="shipped")
    probs = list(problems)
    probs += [f"{k} differs from the recomputed pack" for k, v in files.items() if not (run / k).exists() or (run / k).read_text() != v]
    if sum(x["counts"][s] for x in res["experiments"] for s in proof.STATUSES) != res["check_counts"]["checks"]:
        probs.append("experiment totals differ from check totals")
    probs += [f"{c['id']}: evidence {e['path']} missing" for c in jl for e in c["evidence"] if not (ROOT / e["path"]).exists()]
    probs += [f"{c['id']} FAIL: a guarantee did not hold" for c in jl if c["status"] == "FAIL" and c["finding"] == "FAIL"]
    c = res["check_counts"]
    rep.add("Experiment checks", not probs, f"{c['experiments']} experiments · {c['checks']} checks: {c['pass']} pass, {c['fail']} fail, "
            f"{c['expected_failure']} expected failure (controls); recomputed from the raw files, byte-identical", probs)

    # ---- claim mappings -----------------------------------------------------------------------------------------------
    cspec = tomllib.loads((run / "proof" / "claims.toml").read_text())
    probs = []
    claimed = {f for cl in cspec["claims"] for f in cl.get("facts", [])}
    probs += [f"claim {cl['id']}: fact {f} is not in the run" for cl in cspec["claims"] for f in cl.get("facts", []) if f not in shipped]
    uses = read(USES) if USES.exists() and not candidate else {}
    probs += [f"printed result fact not mapped to a claim: {k}" for k in sorted(uses) if k not in claimed and not k.startswith(DESCRIPTIVE)]
    built = {n: p.read_text() for n, p in ARTICLES.items() if p.exists()}
    figs = set()
    if built:
        hs = set().union(*(headings(t) for t in built.values()))
        figs = {m for t in built.values() for m in re.findall(r"premium/png/([\w-]+)\.png", t)}
        for cl in cspec["claims"]:
            for a in cl["article"]:
                if a.startswith("fig:"):
                    if a[4:] not in figs:
                        probs.append(f"claim {cl['id']}: figure {a[4:]} is in neither article")
                elif a not in hs:
                    probs.append(f"claim {cl['id']}: section '{a}' is in neither article")
    kinds = {}
    for cl in res["claims"]:
        kinds[cl["verdict"]] = kinds.get(cl["verdict"], 0) + 1
    rep.add("Claim mappings", not probs, f"{len(res['claims'])} claims, each verdict borne out by its checks ({', '.join(f'{v} {k}' for k, v in kinds.items())})"
            + (f"; {len(uses)} printed facts, every result fact mapped" if uses else "") + ("; every article section and figure found" if built else ""), probs)

    # ---- integrity ----------------------------------------------------------------------------------------------------
    n, bad = proof.verify_sha256sums(run / "SHA256SUMS", ROOT)
    listed = {line.split("  ", 1)[1] for line in (run / "SHA256SUMS").read_text().splitlines() if line.strip()}
    present = {p.relative_to(ROOT).as_posix() for p in proof_pack.covered(run_id)}
    bad += [f"not in SHA256SUMS: {r}" for r in sorted(present - listed)][:20]
    if not candidate and pub["results_sha256"] != proof.sha256_file(run / "results.json"):
        bad.append("published.json results_sha256 does not match results.json")
    # earlier published runs are immutable too: their own SHA256SUMS, and the files moved unchanged by the relocation.
    # In the publication package a recorded file may be redacted (REDACTIONS.json, proof/hygiene.toml); it is accepted
    # only as exactly that redaction of exactly the listed original.
    red = {r["file"]: r for r in read(ROOT / "REDACTIONS.json")["redactions"]} if (ROOT / "REDACTIONS.json").exists() else {}

    def redacted_ok(rel_path: str, listed: str) -> bool:
        r = red.get(rel_path)
        return bool(r) and r["original_sha256"] == listed and proof.sha256_file(ROOT / rel_path) == r["redacted_sha256"]

    history = []
    for h in (pub["history"] if pub else []):
        hr = RUNS / h["run_id"]
        if (hr / "SHA256SUMS").exists():
            hn, hbad = proof.verify_sha256sums(hr / "SHA256SUMS", ROOT)
            listing = {ln.split("  ", 1)[1]: ln.split("  ", 1)[0] for ln in (hr / "SHA256SUMS").read_text().splitlines() if ln.strip()}
            hbad = [b for b in hbad if not (b.startswith("changed: ") and redacted_ok(b[9:], listing[b[9:]]))]
            bad += [f"{h['run_id']}: {b}" for b in hbad][:20]
            if h.get("results_sha256") and h["results_sha256"] != proof.sha256_file(hr / "results.json"):
                bad.append(f"{h['run_id']}: results.json differs from the hash in published.json history")
            history.append(f"{h['run_id']} {hn}")
    rel = read(ROOT / "evidence" / "RELOCATION.json") if (ROOT / "evidence" / "RELOCATION.json").exists() else {"map": []}
    moved = [m["to"] for m in rel["map"] if not (ROOT / "evidence" / m["to"]).exists()
             or (proof.sha256_file(ROOT / "evidence" / m["to"]) != m["sha256"] and not redacted_ok(f"evidence/{m['to']}", m["sha256"]))]
    bad += [f"relocated file changed or missing: {m}" for m in moved][:20]
    rep.add("Integrity", not bad, f"{n} files match evidence/runs/{run_id}/SHA256SUMS (the pack, raw run, replay and negative control)"
            + (f"; history unchanged: {', '.join(history)} files match their SHA256SUMS" if history else "")
            + (f", and the {len(rel['map'])} relocated raw files of the runs before the contract match RELOCATION.json" if rel["map"] else "")
            + (f" ({len(red)} redacted in this package, each the recorded redaction of the listed original: REDACTIONS.json)" if red else "")
            + "; a checksum list, not a signature", bad)

    # ---- replay -------------------------------------------------------------------------------------------------------
    rp = read(run / "replay.json")
    again_rp = replay_compare.compare(run_id)
    probs = []
    if json.dumps(again_rp, sort_keys=True) != json.dumps(rp, sort_keys=True):
        probs.append("replay.json differs from a fresh comparison of raw/ and replay/raw/")
    if not rp["equivalent"]:
        probs.append("the replay is not equivalent")
    if rp["replay_level"] != man["replay"]["level"]:
        probs.append(f"replay level {rp['replay_level']} differs from the declared {man['replay']['level']}")
    g = rp["groups"]
    rep.add("Replay", not probs, f"{rp['replay_level']} as declared: harness assertions {g['checks']['deterministic_equivalent']}/{g['checks']['rows']} and ids "
            f"{g['ids']['deterministic_equivalent']}/{g['ids']['rows']} identical; {g['volatile']['rows']} volatile values differ (trace id, timestamps, "
            "pids, wall time); 0 regressions", probs)

    # ---- negative control ---------------------------------------------------------------------------------------------
    nc = read(run / "negative-control" / "results.json")
    probs = proof.validate_schema(nc, proof.schema("negative-control"))
    if not nc["harness_completed"]:
        probs.append("the negative control did not complete cleanly (a crash is not a proof)")
    if nc["result"] != "EXPECTED_FAILURE":
        probs.append(f"result {nc['result']}: the control did not break as intended")
    mu = nc["mutated"]
    rep.add("Negative control", not probs, f"approval requirement removed: policy {nc['governed']['policy_decision']} → {mu['policy_decision']}, "
            f"{mu['checks_failed']} of {mu['checks']} harness assertions failed in {mu['experiments_failed']}, harness exceptions "
            f"{mu['harness_exceptions']}, exit {mu['proof_exit_code']} ({nc['result']})", probs)

    # ---- README, Lab, articles ----------------------------------------------------------------------------------------
    if candidate:
        for s in ("Published facts", "README", "Lab", *ARTICLES):
            rep.add(s, None, "candidate run: publication is checked against the published run only")
    else:
        if not FACTS.exists():
            rep.add("Published facts", None, "not part of the POC package (docs/facts.json is published with the articles)")
        else:
            # the article repository's facts.json (every number the articles and figures print) and every run id it carries
            af = read(FACTS)
            probs = [f"docs/facts.json {k}: {af[k]['value']!r} ≠ published {v['value']!r}" for k, v in shipped.items() if k in af and af[k]["value"] != v["value"]]
            probs += [f"docs/facts.json lacks {k}" for k in shipped if k not in af]
            probs += [f"docs/facts.json {k} is not in the published run" for k in af if k not in shipped and not k.startswith("published.")]
            if af.get("published.run_id", {}).get("value") != run_id:
                probs.append(f"docs/facts.json names published run {af.get('published.run_id', {}).get('value')}")
            known_runs = {run_id} | {h["run_id"] for h in pub["history"]}
            mentions = 0
            for f in (DIAGRAMS, REPO / "docs" / "site.json"):
                if f.exists():
                    found = re.findall(r"\b\d{4}-\d{2}-\d{2}-proof[\w-]*", f.read_text())
                    mentions += len(found)
                    probs += [f"{f.relative_to(REPO)} names {r}, neither published nor in the history" for r in sorted(set(found) - known_runs)]
            if run_id not in (ROOT / "README.md").read_text():
                probs.append(f"README.md does not name the published run {run_id}")
            rep.add("Published facts", not probs, f"docs/facts.json: {len(shipped)} facts equal the published run's; run {run_id} named consistently by "
                    f"published.json, PUBLISHED, facts.json, README, the diagram manifest ({mentions} provenance lines), the Lab and both articles", probs)
        sys.path.insert(0, str(ROOT / "tools"))
        import build_readme  # noqa: E402
        stale = build_readme.stale()
        rep.add("README", not stale, "README.md equals its template rendered with the published run's facts" if not stale else "", stale)
        lab = (ROOT / "lab" / "index.html").read_text() if (ROOT / "lab" / "index.html").exists() else ""
        m = re.search(r'<script type="application/json" id="lab-facts">(.*?)</script>', lab, re.S)
        probs = [] if m else ["lab/index.html carries no lab-facts block"]
        if m:
            lf = json.loads(m.group(1))
            probs += [f"lab fact {k}: {v!r} ≠ published {shipped.get(k, {}).get('display')!r}" for k, v in lf["facts"].items() if shipped.get(k, {}).get("display") != v]
            if lf["run_id"] != run_id:
                probs.append(f"lab/index.html shows run {lf['run_id']}")
        rep.add("Lab", not probs, f"lab/index.html shows run {run_id}; its {len(lf['facts']) if m else 0} printed facts equal the published run's", probs)
        for name, path in ARTICLES.items():
            if not path.exists():
                rep.add(name, None, "not part of the POC package (published with the articles)")
                continue
            t = path.read_text()
            probs = [f"printed {k} = {u['value']!r}, published {shipped[k]['value']!r}" for k, u in uses.items()
                     if name.split()[0].lower() in u["used_in"] and k in shipped and u["value"] != shipped[k]["value"]]
            probs += [f"printed fact {k} is not in the published run" for k, u in uses.items() if name.split()[0].lower() in u["used_in"] and k not in shipped]
            if "{{" in t:
                probs.append("unresolved {{fact}}")
            if run_id not in t:
                probs.append(f"does not name the published run {run_id}")
            other = sorted({r for r in re.findall(r"\b\d{4}-\d{2}-\d{2}-proof[\w-]*", t)} - {run_id} - {h["run_id"] for h in pub["history"]})
            probs += [f"names a run that is neither published nor in the history: {r}" for r in other]
            n_used = sum(name.split()[0].lower() in u["used_in"] for u in uses.values())
            rep.add(name, not probs, f"{path.relative_to(REPO)}: {n_used} printed facts equal the published run's; names {run_id}", probs)

    # ---- secret scan --------------------------------------------------------------------------------------------------
    text_like = {".json", ".jsonl", ".md", ".txt", ".toml", ".yaml", ".html", ".diff", ".py"}
    paths = [p for p in [*run.rglob("*"), *(ROOT / "proof").glob("*"), ROOT / "README.md", ROOT / "lab" / "index.html",
                         *(ROOT / "evidence").glob("*.json")] if p.is_file() and p.suffix in text_like]
    hyg = tomllib.loads((ROOT / "proof" / "hygiene.toml").read_text())
    hits = proof.scan(paths, ROOT, allow=hyg.get("allow", SCAN_ALLOW))
    known = [h for h in hits if any(h["file"] in k["files"] and re.search(k["pattern"], (ROOT / h["file"]).read_text().splitlines()[h["line"] - 1])
                                    for k in hyg.get("known", []))]
    hits = [h for h in hits if h not in known]
    pub_files = [ROOT / "README.md", ROOT / "lab" / "index.html", *[p for p in ARTICLES.values() if p.exists()],
                 *[p.with_suffix(s) for p in ARTICLES.values() for s in (".html", ".pdf") if p.with_suffix(s).exists()]]
    local = publication.local_path_findings(pub_files, ROOT if not built else REPO, forbid=[Path.home()])
    probs = [f"{h['file']}:{h['line']}: {h['kind']}" for h in hits] + [f"{h['file']}:{h['line']}: {h['kind']}" for h in local]
    rep.add("Secret scan", not probs, f"{len(paths)} evidence files: no credential, key, token, e-mail or private path"
            + (f" ({len(known)} known in recorded files, redacted in the package: proof/hygiene.toml)" if known else "")
            + f"; {len(pub_files)} published pages (README, Lab, articles incl. PDFs): no local path", probs)

    txt = rep.text()
    print(txt)
    if not o.no_write:
        out = ROOT / "evidence" / "verification"
        out.mkdir(parents=True, exist_ok=True)
        (out / "verification.txt").write_text(txt)
        (out / "verification.json").write_text(json.dumps(rep.json(run_id=run_id, results_sha256=proof.sha256_file(run / "results.json"),
                                                                   command="uv run pap verify"), indent=1) + "\n")
    return 0 if rep.verified else 1


if __name__ == "__main__":
    sys.exit(main())
