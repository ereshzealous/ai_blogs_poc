"""Verify the published results from the public evidence, without a model and without the article tooling.

    uv run sprawl verify          (make verify)       in the public repository
    uv run sprawl verify --public                     the same check in the development workspace

What it checks, each from the committed files:

  frozen inputs        every input hash of the current evidence revision; a public redaction is accepted only where
                       evidence/public-redactions.json declares it, with both hashes
  benchmark            the frozen case set and the catalog manifests the run recorded
  rows                 the published run's row count, per variant and catalog size, and evidence/results.csv
  summary              the preregistered analysis recomputed from rows.jsonl with the frozen code, equal to the
                       committed summary, and the headline numbers the articles print
  hypotheses           the preregistered hypotheses recomputed the same way, and their verdicts
  replay               the recorded replay of every row: rows replayed, effects, outcomes and verdicts, regressions
  request mismatches   the replayed model requests that were not byte-identical, and that they change no result
  featured trace       the ORD-4917 row: its effect, binding, policy decision and hash-chained audit
  negative control     with the policy removed the invariant breaks; with it, nothing reaches a backend
  public manifest      the hash of every public evidence file, the row files the articles name, and the full-evidence archive
  lab console          the Proof Lab and its data name the published run and hold every row the articles link

Post-freeze tooling: it reads files and recomputes; it writes nothing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
ROOT = POC.parent
EXP, EV = ROOT / "experiment", ROOT / "evidence"
sys.path.insert(0, str(POC / "src"))
from sprawl_poc.bench.analyze import summarise  # noqa: E402  (the frozen analysis)
from sprawl_poc.bench.hypotheses import evaluate  # noqa: E402  (the frozen hypothesis evaluator)
from sprawl_poc.control_plane.audit import AuditLog  # noqa: E402

OK, BAD = "PASS", "FAIL"


def jload(p: Path):
    return json.loads(p.read_text())


def jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def norm(x):
    return json.loads(json.dumps(x))


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str, list[str]]] = []

    def add(self, name: str, problems: list[str], detail: str) -> None:
        self.rows.append((name, not problems, detail, problems))

    def print(self) -> bool:
        print("PUBLIC VERIFICATION\n")
        for name, ok, detail, problems in self.rows:
            print(f"{name:<20} {OK if ok else BAD:<6}  {detail if ok else ''}")
            for p in problems[:12]:
                print(f"{'':<28}· {p}")
        ok = all(r[1] for r in self.rows)
        print("\nVERIFIED" if ok else "\nNOT VERIFIED")
        return ok


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--archive", type=Path, help="check a copy of the full-evidence archive elsewhere (default: the one in evidence/full/)")
    ns = ap.parse_args(argv)
    rep = Report()
    pub = jload(EV / "published.json")
    run = pub["run_id"]
    manifest = jload(EV / "public-manifest.json") if (EV / "public-manifest.json").exists() else None
    redactions = jload(EV / "public-redactions.json")["redactions"] if (EV / "public-redactions.json").exists() else []
    raw = EXP / "raw" / run
    an = EXP / "analysis" / run
    E = jload(EV / "evidence.json")
    F = {k: v["value"] for k, v in E["facts"].items()}
    D = {k: v["display"] for k, v in E["facts"].items()}

    # ---- frozen inputs
    import importlib.util
    spec = importlib.util.spec_from_file_location("freeze", POC / "scripts" / "freeze.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)
    fz.ollama_digest = lambda name: None  # model digests are a live-run concern (uv run sprawl doctor)
    rev = fz.current_revision()
    frozen = jload(ROOT / rev["freeze"])["hashes"]
    now = fz.compute()["hashes"]
    red = {r["frozen_key"]: r for r in redactions if r.get("frozen_key")}
    probs, declared = [], []
    for k, want in sorted(frozen.items()):
        have = now.get(k)
        if have == want:
            continue
        r = red.get(k)
        if r and r["original_sha256"] == want and r["public_sha256"] == have:
            declared.append(k)
        else:
            probs.append(f"{k}: {have} (frozen {want})")
    r1 = jload(EXP / "frozen-hashes.json")["hashes"]
    changed = sorted(k for k in set(r1) | set(frozen) if r1.get(k) != frozen.get(k))
    undeclared = sorted(set(changed) - set(rev.get("changed_from_r1", [])))
    probs += [f"revision {rev['id']} differs from the blind-run freeze in an undeclared input: {k}" for k in undeclared]
    rep.add("Frozen inputs", probs, f"{len(frozen) - len(probs) - len(declared)}/{len(frozen)} hashes match evidence revision {rev['id']}"
            + (f"; {len(declared)} public redaction(s) declared with both hashes ({', '.join(declared)})" if declared else "")
            + f"; r{rev['id'][1:]} differs from the blind-run freeze only in its declared {len(changed)} input(s)")

    # ---- benchmark and catalogs
    meta = jload(raw / "run-meta.json")
    bench = jload(EXP / "benchmark" / "cases.json")
    probs = []
    if bench["cases_sha256"] != meta["cases_sha256"]:
        probs.append("cases.json is not the case set the run recorded")
    if (bench["counts"].get("blind"), bench["counts"].get("dev")) != (F["cases.blind"], F["cases.dev"]):
        probs.append(f"case counts {bench['counts']} differ from the published {F['cases.blind']} blind / {F['cases.dev']} development")
    for n in (50, 100, 500):
        m = jload(POC / "data" / "estates" / f"estate-{n}" / "manifest.json")
        tools, servers = m.get("tool_count", m.get("tools")), m.get("server_count", m.get("servers"))
        if isinstance(tools, list):
            tools = len(tools)
        if isinstance(servers, list):
            servers = len(servers)
        if (tools, servers) != (F[f"estate.{n}.tools"], F[f"estate.{n}.servers"]):
            probs.append(f"estate-{n}: {tools} tools on {servers} servers, published {F[f'estate.{n}.tools']} on {F[f'estate.{n}.servers']}")
    rep.add("Benchmark", probs, f"{F['cases.blind']} blind and {F['cases.dev']} development cases, the hash the run recorded; "
            f"catalogs of {F['estate.50.tools']}, {F['estate.100.tools']} and {F['estate.500.tools']} tools as recorded")

    # ---- rows
    rows = jsonl(raw / "rows.jsonl")
    probs = []
    cells = Counter((r["arm_key"], r["estate_size"]) for r in rows)
    if len(rows) != F["run.rows"]:
        probs.append(f"{len(rows)} rows, published {F['run.rows']}")
    per = F["cases.blind"]
    bad_cells = {f"{a}@{z}": n for (a, z), n in cells.items() if n != per}
    if bad_cells or len(cells) != 9:
        probs.append(f"cells not {per} rows each: {bad_cells or dict(cells)}")
    non_ok = sum(r["status"] != "ok" for r in rows)
    if non_ok != F["run.non_ok_rows"]:
        probs.append(f"{non_ok} rows not ok, published {F['run.non_ok_rows']}")
    if (EV / "results.csv").exists():
        with (EV / "results.csv").open() as fh:
            res = {r["row_id"]: r for r in csv.DictReader(fh)}
        if len(res) != len(rows):
            probs.append(f"results.csv has {len(res)} rows, rows.jsonl {len(rows)}")
        diff = [r["row_id"] for r in rows if res.get(r["row_id"], {}).get("correct") != str(bool(r["score"]["correct"])).lower()]
        if diff:
            probs.append(f"results.csv disagrees with rows.jsonl on correctness: {diff[:3]}")
    rep.add("Rows", probs, f"{len(rows)} rows of {run}: {per} per variant and catalog size, {non_ok} invalid"
            + ("; evidence/results.csv equals rows.jsonl" if (EV / "results.csv").exists() else ""))

    # ---- summary: the frozen analysis from rows.jsonl, and the headline numbers
    s = norm(summarise(raw))
    probs = [] if s == jload(an / "summary.json") else [f"recomputed summary differs from {an.relative_to(ROOT)}/summary.json"]
    full = {"A": "A_all_tools", "B": "B_search_only", "C": "C_control_plane"}
    checked = 0
    for a, name in full.items():
        for z in (50, 100, 500):
            c = s["cells"][f"{name}@{z}"]
            for fact, val in ((f"{a}.{z}.correct.kn", f"{c['correct']['k']}/{c['correct']['n']}"),
                              (f"{a}.{z}.unsafe_execution.kn", f"{c['unsafe_execution']['k']}/{c['unsafe_execution']['n']}")):
                checked += 1
                if D.get(fact) != val:
                    probs.append(f"{fact}: published {D.get(fact)}, recomputed {val}")
        tok = s["cells"][f"{name}@500"]["median_tool_definition_tokens"]
        checked += 1
        if F.get(f"{a}.500.median_tool_definition_tokens") != tok:
            probs.append(f"{a}.500.median_tool_definition_tokens: published {F.get(f'{a}.500.median_tool_definition_tokens')}, recomputed {tok}")
        for k in ("unsafe_proposal", "unsafe_execution"):
            n = sum(1 for r in rows if r["arm_key"] == a and r["score"].get(k))
            checked += 1
            if F.get(f"{a}.all.{k}.k") != n:
                probs.append(f"{a}.all.{k}.k: published {F.get(f'{a}.all.{k}.k')}, counted {n}")
    rep.add("Summary", probs, f"the frozen analysis recomputed from rows.jsonl equals the committed summary; {checked} headline numbers equal "
            f"(control plane {D['C.500.correct.kn']}, all tools {D['A.500.correct.kn']}, search only {D['B.500.correct.kn']} at 500 tools; "
            f"{D['C.all.unsafe_proposal.k']} → {D['C.all.unsafe_execution.k']} unsafe in the control plane)")

    # ---- hypotheses
    h = norm(evaluate(raw))
    probs = [] if h == jload(an / "hypotheses.json") else [f"recomputed hypotheses differ from {an.relative_to(ROOT)}/hypotheses.json"]
    verdicts = {k: ("supported" if v["supported"] else "not supported") for k, v in h.items() if k.startswith("H")}
    for k, v in verdicts.items():
        if F.get(f"hyp.{k}") != v:
            probs.append(f"{k}: published {F.get(f'hyp.{k}')}, recomputed {v}")
    rep.add("Hypotheses", probs, f"recomputed with the frozen evaluator, equal to the committed verdicts: "
            f"{sum(v == 'supported' for v in verdicts.values())} of {len(verdicts)} supported "
            f"({', '.join(k for k, v in verdicts.items() if v != 'supported')} not)")

    # ---- replay of every recorded row
    rv = jload(EV / "runs" / run / "replay-verification.json")
    rec_dir = ROOT / rv["record"][0]
    rec = jload(rec_dir / "replay-verification.json")
    cmp = jload(EV / "runs" / run / "replay-comparison.json")
    det = rec["detail"]
    probs = []
    if not (rv["rows_recorded"] == len(rows) == rv["rows_replayed"] == len(det) == rec["rows"]):
        probs.append(f"rows recorded {rv['rows_recorded']}, replayed {rv['rows_replayed']}, in the record {len(det)}, published run {len(rows)}")
    for key, field in (("effects_equivalent", "effects"), ("outcomes_equivalent", "declared_outcome"), ("verdicts_equivalent", "correct"),
                       ("rows_reproduced", "reproduced")):
        n = sum(1 for d in det if d.get(field))
        if n != rv[key]:
            probs.append(f"{key}: {rv[key]} declared, {n} in the record")
    if cmp["classes"].get("REGRESSION") or not cmp["equivalent"] or rv["regressions"]:
        probs.append(f"the replay comparison is not equivalent: {cmp['classes']}")
    if {d["row_id"] for d in det} != {r["row_id"] for r in rows}:
        probs.append("the replay record does not cover exactly the published rows")
    rep.add("Replay", probs, f"{rv['rows_replayed']} of {rv['rows_recorded']} rows replayed without the model: effects {rv['effects_equivalent']}, "
            f"outcomes {rv['outcomes_equivalent']}, verdicts {rv['verdicts_equivalent']} equivalent; {rv['regressions']} regressions; {rv['equivalence']}")

    # ---- request mismatches
    mm_rows = [d for d in det if d.get("replay_request_mismatches")]
    probs = []
    if len(mm_rows) != rv["request_hash_mismatch_rows"] or len(cmp["request_hash_mismatch_rows"]) != len(mm_rows):
        probs.append(f"{len(mm_rows)} rows with mismatches in the record, {rv['request_hash_mismatch_rows']} declared, "
                     f"{len(cmp['request_hash_mismatch_rows'])} in the comparison")
    total = sum(d["replay_request_mismatches"] for d in det)
    if "replay.record.mismatches" in F and F["replay.record.mismatches"] != total:
        probs.append(f"{total} mismatched requests, published {F['replay.record.mismatches']}")
    if any(not d["reproduced"] for d in mm_rows):
        probs.append("a row with a request mismatch did not reproduce")
    rep.add("Request mismatches", probs, f"{total} replayed requests in {len(mm_rows)} rows were not byte-identical (tool-argument key order); "
            "every one of those rows reproduced its effects, outcome and verdict")

    # ---- the featured trace: ORD-4917 through the control plane
    fr = F.get("featured.row", "BL-C03-1__C__500")
    fr = fr if "__" in str(fr) else "BL-C03-1__C__500"
    d = jload(raw / "rows" / f"{fr}.json")
    probs = []
    eff = (d.get("effects") or [{}])[0]
    if not d["score"]["correct"]:
        probs.append(f"{fr} is not scored correct")
    if (eff.get("payload") or {}).get("payment_id") != F.get("featured.effect.payment"):
        probs.append(f"effect payment {(eff.get('payload') or {}).get('payment_id')}, published {F.get('featured.effect.payment')}")
    if eff.get("amount") != F.get("featured.effect.amount"):
        probs.append(f"effect amount {eff.get('amount')}, published {F.get('featured.effect.amount')}")
    if not eff.get("gateway_verified"):
        probs.append("the effect did not arrive with a valid gateway token")
    ex = next((tc for tc in d.get("tool_calls") or [] if (tc.get("gateway") or {}).get("stage_reached") == "executed"), {})
    g = ex.get("gateway") or {}
    pol = g.get("policy") if isinstance(g.get("policy"), dict) else json.loads(g["policy"]) if g.get("policy") else {}
    bind = g.get("binding") if isinstance(g.get("binding"), dict) else json.loads(g["binding"]) if g.get("binding") else {}
    if pol.get("rule") != F.get("featured.policy_rule"):
        probs.append(f"policy rule {pol.get('rule')}, published {F.get('featured.policy_rule')}")
    if "amount" not in (bind.get("bound_fields") or []):
        probs.append("the amount was not bound from the record")
    audit = raw / "audit" / f"{fr}.jsonl"
    ok_chain, why = AuditLog.verify(audit) if audit.exists() else (False, "audit file missing")
    if not ok_chain:
        probs.append(f"audit chain: {why}")
    n_audit = sum(1 for line in audit.read_text().splitlines() if line.strip()) if audit.exists() else 0
    rep.add("Featured trace", probs, f"{fr}: {eff.get('effect_type')} {eff.get('amount')} on {(eff.get('payload') or {}).get('payment_id')}, gateway-verified; "
            f"amount bound from the record; policy {pol.get('rule')}; hash-chained audit of {n_audit} records verified")

    # ---- negative control
    neg = jload(EV / "runs" / run / "negative-control" / "results.json")
    probs = []
    if neg.get("result") != "EXPECTED_FAILURE" or not neg.get("harness_completed"):
        probs.append(f"result {neg.get('result')}, harness completed {neg.get('harness_completed')}")
    if neg["governed"]["reached_backend"] != 0 or neg["mutated"]["reached_backend"] == 0:
        probs.append(f"governed {neg['governed']['reached_backend']}, mutated {neg['mutated']['reached_backend']} reached a backend")
    if neg.get("source_run", run) != run:
        probs.append(f"built from {neg.get('source_run')}, not the published run")
    rep.add("Negative control", probs, f"recorded decisions of {neg.get('source_run', run)}: with the policy {neg['governed']['reached_backend']} of "
            f"{neg['fixture_count']} reached a backend, without it {neg['mutated']['reached_backend']}; the invariant broke as intended")

    # ---- public manifest
    probs, nfiles = [], 0
    if manifest is None:
        rep.add("Public manifest", [], "not a public export (evidence/public-manifest.json absent): skipped")
    else:
        for f in manifest["files"]:
            p = ROOT / f["path"]
            nfiles += 1
            if not p.exists():
                probs.append(f"missing: {f['path']}")
            elif sha(p) != f["sha256"]:
                probs.append(f"changed: {f['path']}")
        for rid in manifest["article_rows"]:
            if not (raw / "rows" / f"{rid}.json").exists():
                probs.append(f"an article names {rid}, its row file is missing")
        arc = manifest["archive"]
        zp = ns.archive or ROOT / arc["path"]
        if not zp.exists():
            probs.append(f"the full-evidence archive is missing: {arc['path']}")
        elif sha(zp) != arc["sha256"] or zp.stat().st_size != arc["size_bytes"]:
            probs.append(f"{zp.name}: sha256 or size differs from the manifest")
        rep.add("Public manifest", probs, f"{nfiles} public evidence files match their sha256; the {len(manifest['article_rows'])} rows the articles name "
                f"are present; the full-evidence archive {arc['path']} ({arc['files']} files, sha256 {arc['sha256'][:12]}…) matches")

    # ---- the Lab Console
    probs = []
    if E["proof"]["run_id"] != run or F.get("published.run_id") != run:
        probs.append(f"evidence.json names {E['proof']['run_id']}, published.json {run}")
    lab_rows = {x["id"]: {r["id"] for r in x["rows"]} if isinstance(x["rows"][0], dict) and "id" in x["rows"][0] else
                {r.get("row_id") or r.get("row") for r in x["rows"]} for x in E["runs"]}
    if run not in lab_rows or len(lab_rows[run]) != len(rows):
        probs.append(f"the Lab holds {len(lab_rows.get(run, []))} rows of {run}, the run has {len(rows)}")
    linked = manifest["article_rows"] if manifest else []
    missing = [r for r in linked if r not in lab_rows.get(run, set())]
    if missing:
        probs.append(f"rows the articles link that the Lab does not hold: {missing[:5]}")
    lab = EV / "lab-console.html"
    if not lab.exists() or run not in lab.read_text():
        probs.append("evidence/lab-console.html is missing or does not name the published run")
    rep.add("Lab console", probs, f"evidence/lab-console.html names {run} and holds all {len(rows)} of its rows"
            + (f", including the {len(linked)} the articles link" if linked else ""))

    sys.exit(0 if rep.print() else 1)


if __name__ == "__main__":
    main()
