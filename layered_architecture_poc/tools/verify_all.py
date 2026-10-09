"""The final publication gate for F2: verification/final_verification.{json,md}.

    make verify-all          (= uv run --project layered_architecture_poc --with markdown --with pypdf python tools/verify_all.py)

Runs the POC's own evidence verifier on the published run, then checks everything built from it: tests, replay,
facts used by the publications, the three publications and the run report (md/html/pdf), the figures and the
Excalidraw scene check, and the claim/evidence matrix.  Exit code 1 if any check fails.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml  # noqa: E402

import build_docs as bd  # noqa: E402

ROOT = bd.ROOT
BYLINE = "F2 · Production AI Engineering"
results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "ok": bool(ok), "detail": detail})


def main() -> None:
    run = bd.published_run()
    facts = bd.load_facts()
    rel = run.relative_to(ROOT / "layered_architecture_poc")

    p = subprocess.run(["uv", "run", "python", "scripts/verify_evidence.py", str(rel)], cwd=ROOT / "layered_architecture_poc",
                       capture_output=True, text=True, timeout=1800)
    v = json.loads((run / "verification.json").read_text())
    check("run evidence verifier (scripts/verify_evidence.py)", p.returncode == 0 and v["ok"], f"{v['passed']}/{v['total']} checks")

    check("tests: zero failures", facts["tests.failed"]["value"] == 0, f"{facts['tests.passed']['value']}/{facts['tests.total']['value']} passed, "
          f"{facts['tests.skipped']['value']} skipped")
    check("replay identical, no fresh model calls", facts["replay.identical"]["value"] is True and facts["replay.fresh_model_calls"]["value"] == 0,
          f"{facts['replay.model_calls_served_from_tape']['value']} calls from tape")
    check("every preregistered scenario present", facts["integrity.scenarios_present"]["value"] == facts["integrity.scenarios_expected"]["value"],
          f"{facts['integrity.scenarios_present']['value']}/{facts['integrity.scenarios_expected']['value']}")

    uses = json.loads((ROOT / "docs" / "evidence-uses.json").read_text())
    stale = [k for k, u in uses.items() if k not in facts or facts[k]["value"] != u["value"]]
    check("every fact used in the publications matches facts.json", not stale, f"{len(uses)} facts used" + (f"; stale: {stale[:5]}" if stale else ""))

    outs = {t: ROOT / "docs" / "publish" / t / f"{bd.SLUG}-{t}" for t in bd.TRACKS}
    outs["report"] = ROOT / "docs" / "results" / bd.REPORT
    outs["evidence"] = ROOT / "docs" / "results" / bd.EVIDENCE
    post = json.loads((ROOT / "verification" / "post_run_evidence_tests.json").read_text())
    check("post-run evidence tests on the frozen run", post["failed"] == 0 and post["passed"] == post["total"] > 0, f"{post['passed']}/{post['total']} passed")
    bundle = json.loads((ROOT / "dist" / f"{run.name}-evidence.json").read_text())
    bz = ROOT / "dist" / bundle["bundle"]
    import hashlib
    check("evidence bundle verified after extraction", bundle["verified_after_extraction"]["ok"] and bz.exists()
          and hashlib.sha256(bz.read_bytes()).hexdigest() == bundle["sha256"], f"{bundle['files']} files, "
          f"{bundle['verified_after_extraction']['passed']}/{bundle['verified_after_extraction']['total']} checks")
    evv = json.loads((ROOT / "verification" / "evidence_check_validation.json").read_text())
    check("evidence check validation (tools/build_evidence_check.py)", evv["result"] == "PASS" and evv["run"] == run.name,
          f"{sum(c['ok'] for c in evv['checks'])}/{len(evv['checks'])} checks")
    lc = ROOT / "docs" / "results" / "lab-console.evidence.json"
    lce = json.loads(lc.read_text()) if lc.exists() else {"runs": []}
    prim = next((r for r in lce["runs"] if r["id"] == run.name), None)
    scen = sorted(p.name for p in (run / "scenarios").iterdir() if (p / "score.json").exists())
    check("Lab Console: every scenario of the published run is a row", prim is not None and sorted(r["id"] for r in prim["rows"]) == scen
          and (ROOT / "docs" / "results" / "lab-console.html").exists(), f"{len(prim['rows']) if prim else 0}/{len(scen)} rows · runs: {len(lce['runs'])}")
    for name, base in outs.items():
        files = [base.with_suffix(s) for s in (".md", ".html", ".pdf")]
        missing = [f.name for f in files if not f.exists()]
        check(f"{name}: md, html and pdf exist", not missing, ", ".join(missing))
        if missing:
            continue
        text = base.with_suffix(".md").read_text() + re.sub(r"<(style|svg|script)\b.*?</\1>|data:[^\"')\s]+", " ",
                                                             base.with_suffix(".html").read_text(), flags=re.S)
        check(f"{name}: no unresolved placeholder", "{{" not in text and "TBD" not in text and "FILL:" not in text)
        pdf = bd.check_pdf(base.with_suffix(".pdf"))
        check(f"{name}: PDF has pages and no blank page", pdf["pages"] > 0 and not pdf["blank_pages"], f"{pdf['pages']} pages")
        src = ROOT / "docs" / "source" / f"{name}.src.md"
        meta, _ = bd.front_matter(src.read_text())
        check(f"{name}: neutral byline", meta.get("byline") == BYLINE, meta.get("byline", ""))
        html = base.with_suffix(".html").read_text()
        links = [h for h in re.findall(r'href="([^"#][^"]*)"', html) if not h.startswith(("http", "mailto", "data:"))]
        broken = [h for h in links if not (base.parent / h).resolve().exists()]
        check(f"{name}: local links resolve", not broken, f"{len(links)} links" + (f"; broken: {broken[:4]}" if broken else ""))

    man = json.loads((ROOT / "diagrams" / "manifest.json").read_text())["figures"]
    miss = [f"{k}.{ext}" for k in man for ext, d in (("png", "png"), ("svg", "svg"), ("excalidraw", "excalidraw"))
            if not (ROOT / "diagrams" / "premium" / d / f"{k}.{ext}").exists()]
    check("every figure exported as png, svg and .excalidraw", not miss, f"{len(man)} figures" + (f"; missing {miss[:4]}" if miss else ""))
    sc = json.loads((ROOT / "diagrams" / "scene_check.json").read_text())
    check("Excalidraw+ scene check", sc["ok"], f"{sc['elements']} elements, checked {sc['checked_utc']}")

    cm = ROOT / "docs" / "claim_evidence_matrix.md"
    check("claim/evidence matrix present and resolved", cm.exists() and "{{" not in cm.read_text(),
          f"{len(re.findall(r'\*\*C\d+\*\*', cm.read_text()))} claims" if cm.exists() else "")

    # ---- the standardization gate (brief section 55) ----
    def tool(name: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["uv", "run", "--project", "layered_architecture_poc", "--with", "markdown", "--with", "pypdf",
                               "--with", "pyyaml", "python", f"tools/{name}", *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=1800)

    r = tool("build_claim_matrix.py", "--check")
    check("every claim has a facts path, a verification check and raw evidence", r.returncode == 0,
          (r.stdout.strip().splitlines() or [""])[-1])
    r = tool("check_numbers.py")
    check("no measured number is typed by hand in a publication source", r.returncode == 0,
          (r.stdout.strip().splitlines() or [""])[-1])

    pytest_run = subprocess.run(["uv", "run", "pytest", "tests/architecture", "tests/evidence", "-q", "-p", "no:cacheprovider"],
                                cwd=ROOT / "layered_architecture_poc", capture_output=True, text=True, timeout=1800)
    check("architecture and evidence tests pass against the published run", pytest_run.returncode == 0,
          (pytest_run.stdout.strip().splitlines() or [""])[-1][:90])

    inv = yaml.safe_load((ROOT / "layered_architecture_poc" / "docs" / "invariants.yaml").read_text())
    check("fifteen architecture invariants, each enforced somehow",
          set(inv["invariants"]) == {f"L{i}" for i in range(1, 16)}
          and all(any(b.get(k) for k in ("static", "tests", "experiments", "recomputed")) for b in inv["invariants"].values()),
          f"{len(inv['invariants'])} invariants, {len(inv['not_enforced'])} named as not enforced")

    outcomes = json.loads((run / "outcomes.json").read_text())
    check("every scenario carries an outcome class",
          sum(outcomes["counts"].values()) == len(outcomes["scenarios"]) == facts["integrity.scenarios_present"]["value"],
          ", ".join(f"{k} {v}" for k, v in outcomes["counts"].items()))
    check("every fault family publishes its exposure denominator",
          bool(outcomes["exposure"]) and all("planned" in v and "exposed" in v for v in outcomes["exposure"].values()),
          "; ".join(f"{k} {v['exposed']}/{v['planned']}" for k, v in outcomes["exposure"].items()))

    acc = json.loads((ROOT / "verification" / "test_accounting.json").read_text())
    junit_passed = acc["during_the_cited_run"]["passed"]
    check("the cited run's test count is reported separately from the current suite",
          junit_passed == facts["tests.passed"]["value"] and acc["current_repository_suite"]["passed"] >= junit_passed,
          f"cited run {junit_passed}, current {acc['current_repository_suite']['passed']}, "
          f"post-run {acc['post_run_evidence_tests']['passed']}, verifier {acc['run_verifier']['passed']}")

    published_md = {name: base.with_suffix(".md").read_text() for name, base in outs.items()
                    if base.with_suffix(".md").exists()}
    known = {run.name, f"{run.name}-replay", f"{run.name}-evidence"}
    other_runs = sorted({m for text in published_md.values()
                         for m in re.findall(r"\b20\d\d-\d\d-\d\d-[a-z][\w-]*", text)} - known)
    check("no publication cites a run other than the published one", not other_runs, ", ".join(other_runs[:5]))
    check("no publication keeps the old '3 concerns to 1' claim",
          not any(re.search(r"\b3\s*(→|->)\s*1\b", t) for t in published_md.values()), "")
    crash_ok = {n: ("exposed" in t.lower() or "reached the" in t.lower()) for n, t in published_md.items()
                if re.search(r"sigkill|crash", t, re.I)}
    check("every publication that discusses the crash states its exposure", all(crash_ok.values()),
          ", ".join(n for n, ok in crash_ok.items() if not ok))
    e9_ok = {n: ("contradicted" in t.lower() or "more files" in t.lower()) for n, t in published_md.items()
             if "E9" in t or "dry run" in t.lower()}
    check("every publication that discusses E9 keeps the contradiction", all(e9_ok.values()),
          ", ".join(n for n, ok in e9_ok.items() if not ok))
    if outcomes["counts"].get("ERROR"):
        check("execution errors are disclosed in the publications",
              any("error" in t.lower() for t in published_md.values()), "")

    r = tool("build_poc_readme.py", "--check")
    check("the POC README is generated from facts.json and current", r.returncode == 0,
          (r.stdout.strip().splitlines() or [""])[-1])
    r = tool("sync_poc_docs.py", "--check")
    check("the reader documents inside the POC match the bundle", r.returncode == 0,
          (r.stdout.strip().splitlines() or [""])[-1])

    poc_readme = (ROOT / "layered_architecture_poc" / "README.md").read_text()
    links = re.findall(r"\]\(((?!https?:|#)[^)]+)\)", poc_readme)
    broken = sorted({l for l in links if not (ROOT / "layered_architecture_poc" / l.split("#")[0]).exists()})
    check("every path the POC README names exists inside the POC", not broken,
          f"{len(set(links))} path(s)" + (f"; missing {broken[:4]}" if broken else ""))

    r = tool("check_figures.py")
    check("every figure's numbers trace to the run, and every figure is referenced", r.returncode == 0,
          (r.stdout.strip().splitlines() or [""])[0])

    # a replay-equivalence claim needs the artifact that states the equality, even when the replay run is not published
    replay_dir = run.parent / f"{run.name}-replay"
    comparison = run / "replay_comparison.json"
    claims_replay = any(re.search(r"replay|from tape", t, re.I) for t in published_md.values())
    needed = [comparison, replay_dir / "verification.json", replay_dir / "facts.json",
              replay_dir / "manifest.json", replay_dir / "source_hashes.json"]
    missing_replay = [str(x.relative_to(ROOT)) for x in needed if not x.exists()]
    check("replay equivalence is claimed only with the artifacts that state it",
          not claims_replay or not missing_replay,
          "not claimed" if not claims_replay else
          (f"missing {missing_replay}" if missing_replay else
           f"{json.loads(comparison.read_text())['model_calls_served_from_tape']} calls from tape, "
           f"identical={json.loads(comparison.read_text())['identical']}"))

    # the public release bundle, when one has been built: the archive must still be the archive that was hashed
    release = ROOT / "verification" / "release_bundle.json"
    if release.exists():
        import hashlib as _h
        rel = json.loads(release.read_text())
        archive = ROOT / rel["archive"]
        check("the public release bundle matches its recorded hash",
              archive.exists() and _h.sha256(archive.read_bytes()).hexdigest() == rel["archive_sha256"]
              and rel["cited_run"] == run.name,
              f"{rel['archived_files']} files, {rel['archive_bytes']/1e6:.1f} MB, run {rel['cited_run']}, "
              f"revision {rel['evidence_revision']}, {rel['sanitized_files']} sanitized")

    # Links we own: the repository became public on 2026-10-04, so a reader follows these and they must resolve.
    ours = sorted({u for text in published_md.values()
                   for u in re.findall(r"https://github\.com/ereshzealous/[\w./-]+", text)})
    unreachable = []
    for url in ours:
        code = subprocess.run(["curl", "-sL", "-o", "/dev/null", "-m", "25", "-A", "Mozilla/5.0",
                               "-w", "%{http_code}"], capture_output=True, text=True, timeout=60,
                              input="").stdout if False else subprocess.run(
            ["curl", "-sL", "-o", "/dev/null", "-m", "25", "-A", "Mozilla/5.0", "-w", "%{http_code}", url],
            capture_output=True, text=True, timeout=60).stdout.strip()
        if code != "200":
            unreachable.append(f"{url} → {code}")
    check("every repository link in a publication resolves for an anonymous reader", not unreachable,
          "; ".join(unreachable) or f"{len(ours)} link(s) checked" if ours else "no repository link in the publications")

    figs = json.loads((ROOT / "diagrams" / "manifest.json").read_text())["figures"]
    missing_sources = sorted({src for fig in figs.values() for src in fig.get("data_sources", [])
                              if not (ROOT / src).exists() and not list(ROOT.glob(src))})
    check("every figure's data source exists", not missing_sources, f"{len(figs)} figures" +
          (f"; missing {missing_sources[:3]}" if missing_sources else ""))
    unsourced = [k for k, fig in figs.items()
                 if re.match(r"^(measured|recorded)", (fig.get("provenance") or "").strip(), re.I)
                 and not fig.get("data_sources")]
    check("every measured figure names a data source", not unsourced, ", ".join(unsourced))

    out = {"run": run.name, "verified_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "ok": all(r["ok"] for r in results), "passed": sum(r["ok"] for r in results), "total": len(results), "checks": results}
    vd = ROOT / "verification"
    vd.mkdir(exist_ok=True)
    (vd / "final_verification.json").write_text(json.dumps(out, indent=1))
    md = [f"# Final verification · run {run.name}", "", f"{out['passed']}/{out['total']} checks passed · {out['verified_utc']}", "",
          "| Check | Result | Detail |", "|---|---|---|"]
    md += [f"| {r['check']} | {'PASS' if r['ok'] else 'FAIL'} | {r['detail']} |" for r in results]
    (vd / "final_verification.md").write_text("\n".join(md) + "\n")
    for r in results:
        print("PASS" if r["ok"] else "FAIL", r["check"], "·", r["detail"])
    print(f"{out['passed']}/{out['total']}")
    sys.exit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
