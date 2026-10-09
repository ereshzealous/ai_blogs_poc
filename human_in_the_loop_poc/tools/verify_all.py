"""The T3 publication gate: the proof verification plus every publication check that can be automated.

    uv run --project hitl_poc --with pypdf python tools/verify_all.py      -> qa/verification.json (+ exit code)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "hitl_poc"
sys.path.insert(0, str(ROOT / "vendor"))
from evidence_kit.publication import expand, local_path_findings  # noqa: E402

# Everything a reader or a reviewer receives: both editions, the results documents, the READMEs, the figures, the evidence.
PUBLISHED = [ROOT / "medium", ROOT / "technical", ROOT / "results", ROOT / "README.md", POC / "README.md", ROOT / "diagrams" / "premium" / "svg",
             ROOT / "diagrams" / "manifest.json", POC / "evidence"]
EDITIONS = [ROOT / "medium" / "human-in-the-loop-medium", ROOT / "technical" / "human-in-the-loop-technical"]
RESULTS = [ROOT / "results" / f"human-in-the-loop-{k}" for k in ("report", "evidence", "real-vs-simulated")]
FILLER = ["in today's rapidly evolving", "revolutionizing", "game-changing", "game changer", "paradigm shift", "imagine a world"]
results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    print("PASS" if ok else "FAIL", name, detail)


def main() -> None:
    # pyproject's addopts already has -q; a second -q would suppress the summary line this check reports
    r = subprocess.run(["uv", "run", "pytest"], cwd=POC, capture_output=True, text=True)
    m = re.search(r"(\d+ passed[^\n]*)", r.stdout)
    check("pytest (conformance suite + implementation tests)", r.returncode == 0 and bool(m), m.group(1).strip("= ") if m else "no pytest summary")
    r = subprocess.run(["uv", "run", "hitl", "verify"], cwd=POC, capture_output=True, text=True)
    check("PROOF VERIFICATION (pae-proof/v1)", r.returncode == 0 and "VERIFIED" in r.stdout and "NOT VERIFIED" not in r.stdout,
          "; ".join(f"{m.group(1)}={m.group(2)}" for m in re.finditer(r"^(\S.*?)\s{2,}(PASS|FAIL|N/A)\b", r.stdout, re.M)))
    run = json.loads((POC / "evidence" / "published.json").read_text())["run_id"]
    rep = json.loads((POC / "evidence" / "runs" / run / "test-report.json").read_text())
    check("conformance suite on the published run", rep["passed"] == rep["total"] == 30, f"{rep['passed']}/{rep['total']}")

    for ed in EDITIONS:
        md = ed.with_suffix(".md").read_text()
        local = [t for t in re.findall(r"!?\[[^\]]*\]\(([^)\s]+)\)", md) if not t.startswith(("http", "#", "mailto:"))]
        missing = [t for t in local if not (ed.parent / t.split("#")[0]).exists()]
        check(f"{ed.name}.md: images and links resolve", not missing, f"{len(local)} local targets" + (f"; missing {missing}" if missing else ""))
        check(f"{ed.name}.md: no raw HTML, no unresolved tokens", not re.search(r"<(div|span|svg|figure|aside|script)\b", md) and "{{" not in md and "[[" not in md, "")
        page = ed.with_suffix(".html").read_text()
        ext = re.findall(r'<(?:script|img|link|iframe)[^>]+(?:src|href)="(https?://[^"]+)"', page) + re.findall(r"url\((https?://[^)]+)\)", page)
        check(f"{ed.name}.html: standalone", not ext, f"{len(page) // 1024} KB")
        low = re.sub(r"<[^>]+>", " ", page).lower()
        check(f"{ed.name}: no marketing filler", not [f for f in FILLER if f in low], "")
        from pypdf import PdfReader
        pdf = PdfReader(str(ed.with_suffix(".pdf")))
        blank = [i + 1 for i, p in enumerate(pdf.pages) if len((p.extract_text() or "").strip()) < 5 and "/XObject" not in str(p.get("/Resources", ""))]
        check(f"{ed.name}.pdf: pages, none blank", len(pdf.pages) > 5 and not blank, f"{len(pdf.pages)} pages")

    # The results documents (Run Report, Evidence, Real vs simulated): present in all three formats and standalone.
    for doc in RESULTS:
        have = [ext for ext in (".md", ".html", ".pdf") if doc.with_suffix(ext).exists()]
        check(f"{doc.name}: md, html and pdf exist", len(have) == 3, ", ".join(have))
        if doc.with_suffix(".html").exists():
            page = doc.with_suffix(".html").read_text()
            ext = re.findall(r'<(?:script|img|link|iframe)[^>]+(?:src|href)="(https?://[^"]+)"', page) + re.findall(r"url\((https?://[^)]+)\)", page)
            check(f"{doc.name}.html: standalone, no unresolved tokens", not ext and "{{" not in page, f"{len(page) // 1024} KB")

    man = json.loads((ROOT / "diagrams" / "manifest.json").read_text())["figures"]
    miss = [f"{fid}.{k}" for fid, m in man.items() for k, p in m["files"].items() if not (ROOT / p).exists()]
    check("every figure exported (skeleton, excalidraw, svg, png)", not miss, f"{len(man)} figures")
    pc = ROOT / "qa" / "page-checks.json"
    rows = json.loads(pc.read_text()) if pc.exists() else []
    bad = [f"{r['page']}/{r['viewport']}" for r in rows if r["errors"] or r["failed"] or r["overflow"] > 0 or r["wide"] or r["badAnchors"] or r["brokenLocal"]]
    check("rendered pages clean at 3 viewports", bool(rows) and not bad, f"{len(rows)} runs" + (f"; problems {bad}" if bad else ""))
    check("reader features and accessibility basics", bool(rows) and all(r["toc"] and r["anchors"] and r["copyButtons"] == r["codeBlocks"] and r["progressAtHalf"] > 20
                                                                    and r["h1"] == 1 and not r["headingSkips"] and not r["svgsNoLabel"] and not r["imgsMissingAlt"] for r in rows), "")
    # The storyboard is one deliverable: every figure pushed as a frame AND the scene check passing (a missing check fails).
    scenes, sc = ROOT / "diagrams" / "scenes.json", ROOT / "diagrams" / "scene_check.json"
    frames = json.loads(scenes.read_text()) if scenes.exists() else {}
    s = json.loads(sc.read_text()) if sc.exists() else {}
    ids = [v["frame_id"] for v in frames.values()]
    check("Excalidraw+ frames == figures (one frame per semantic figure)", sorted(frames) == sorted(man) and len(set(ids)) == len(ids),
          f"{len(frames)} frames, {len(man)} figures" + (f"; unmatched {sorted(set(frames) ^ set(man))}" if set(frames) != set(man) else ""))
    check("Excalidraw+ storyboard pushed and scene check passing", len(frames) == len(man) and s.get("ok", False),
          f"{len(frames)}/{len(man)} frames; " + ("; ".join(f"{c['check']}={'ok' if c['ok'] else 'FAIL'}" for c in s.get("checks", [])) or "diagrams/scene_check.json missing"))
    files = expand(PUBLISHED)
    leaks = local_path_findings(files, ROOT, forbid=[ROOT.parents[2], Path.home()])
    check("no local paths in any publication artifact (md, html, pdf streams, svg, json)", not leaks,
          f"{len(files)} files" + (f"; {[(f['file'], f['kind'], f['match']) for f in leaks[:4]]}" if leaks else ""))
    out = {"ok": all(r["ok"] for r in results), "passed": sum(r["ok"] for r in results), "total": len(results), "checks": results}
    (ROOT / "qa").mkdir(exist_ok=True)
    (ROOT / "qa" / "verification.json").write_text(json.dumps(out, indent=1))
    print(f"\n{out['passed']}/{out['total']} checks passed")
    sys.exit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
