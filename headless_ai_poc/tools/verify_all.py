"""The F3 publication gate: every check that can be automated, in one place.

    uv run --project headless_ai_poc --with pypdf python tools/verify_all.py      -> qa/verification.json (+ exit code)

Checks: POC tests; EVIDENCE VERIFICATION (`uv run hai verify --check`: manifest, SHA256SUMS, checks, claims, byte-for-byte
replay, credential and local-path scan); all run checks passed; per edition: Markdown targets resolve, no raw HTML, no
unresolved tokens, standalone HTML, no marketing filler, PDF pages with none blank; every figure exported; rendered page
checks (qa/page-checks.json from tools/qa_pages.mjs); every number the articles print matches the published run and
belongs to a claim in proof/claims.toml; the audit excerpt matches the run's audit chain; the hand-off to T3 names the
exact action; GitHub links answer an anonymous reader; no local path in any publication artifact; the Excalidraw+
storyboard pushed with its scene check passing.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "headless_ai_poc"
sys.path.insert(0, str(ROOT / "vendor"))
from evidence_kit.publication import expand, local_path_findings  # noqa: E402

EDITIONS = [ROOT / "medium" / "headless-ai-medium", ROOT / "technical" / "headless-ai-technical"]
FILLER = ["in today's rapidly evolving", "revolutionizing", "revolutionising", "game-changing", "game changer", "paradigm shift", "imagine a world"]
# Everything a reader or a reviewer receives: both editions, the READMEs, the figures and the POC with its evidence.
PUBLISHED = [ROOT / "medium", ROOT / "technical", ROOT / "README.md", POC / "README.md", POC / "architecture.md", POC / "runs",
             POC / "proof", ROOT / "diagrams" / "premium" / "svg", ROOT / "diagrams" / "manifest.json"]
HANDOFF = "rollbackDeployment(payment-service, production, v4.18.0 → v4.17.2)"
results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    print("PASS" if ok else "FAIL", name, detail)


def answers(url: str) -> int:
    """HTTP status an anonymous reader gets (redirects followed); 0 when the request fails."""
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "f3-publication-gate"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError):
        return 0


def main() -> None:
    # pyproject's addopts already has -q; another -q would suppress the summary line this check reports
    r = subprocess.run(["uv", "run", "pytest"], cwd=POC, capture_output=True, text=True)
    m = re.search(r"(\d+ passed[^\n]*)", r.stdout)
    check("POC tests pass", r.returncode == 0 and bool(m), m.group(1).strip("= ") if m else "no pytest summary")

    r = subprocess.run(["uv", "run", "hai", "verify", "--check"], cwd=POC, capture_output=True, text=True)
    check("EVIDENCE VERIFICATION (uv run hai verify)", r.returncode == 0 and "\nVERIFIED" in r.stdout,
          "; ".join(f"{m.group(1)}={m.group(2)}" for m in re.finditer(r"^(\w+)\s+(PASS|FAIL)\b", r.stdout, re.M)))
    run = (POC / "runs" / "PUBLISHED").read_text().strip()
    checks = json.loads((POC / "runs" / run / "checks.json").read_text())
    check("all run checks passed", all(c["passed"] for c in checks), f"{sum(c['passed'] for c in checks)}/{len(checks)} in run {run}")

    md_text = {}
    for ed in EDITIONS:
        md = md_text[ed.name] = ed.with_suffix(".md").read_text()
        targets = re.findall(r"!?\[[^\]]*\]\(([^)\s]+)\)", md)
        local = [t for t in targets if not t.startswith(("http", "#", "mailto:"))]
        missing = [t for t in local if not (ed.parent / t.split("#")[0]).exists()]
        check(f"{ed.name}.md: images and links resolve", not missing, f"{len(local)} local targets" + (f"; missing {missing}" if missing else ""))
        check(f"{ed.name}.md: no raw HTML", not re.search(r"<(div|span|svg|figure|aside|script)\b", md), "")
        check(f"{ed.name}.md: no unresolved tokens", "{{" not in md and "TBD" not in md and "[[" not in md, "")
        page = ed.with_suffix(".html").read_text()
        ext = re.findall(r'<(?:script|img|link|iframe)[^>]+(?:src|href)="(https?://[^"]+)"', page)
        ext += re.findall(r"url\((https?://[^)]+)\)", page)
        check(f"{ed.name}.html: standalone (no external assets)", not ext, f"{len(page) // 1024} KB" + (f"; external {ext[:3]}" if ext else ""))
        low = re.sub(r"<[^>]+>", " ", page).lower()
        check(f"{ed.name}: no marketing filler", not [f for f in FILLER if f in low], "")
        from pypdf import PdfReader
        pdf = PdfReader(str(ed.with_suffix(".pdf")))
        blank = [i + 1 for i, p in enumerate(pdf.pages) if len((p.extract_text() or "").strip()) < 5 and "/XObject" not in str(p.get("/Resources", ""))]
        check(f"{ed.name}.pdf: pages, none blank", len(pdf.pages) > 5 and not blank, f"{len(pdf.pages)} pages")

    man = json.loads((ROOT / "diagrams" / "manifest.json").read_text())["figures"]
    miss = [f"{fid}.{k}" for fid, m in man.items() for k, p in m["files"].items() if not (ROOT / p).exists()]
    check("every figure exported (skeleton, excalidraw, svg, png)", not miss, f"{len(man)} figures" + (f"; missing {miss[:5]}" if miss else ""))

    pc = ROOT / "qa" / "page-checks.json"
    rows = json.loads(pc.read_text()) if pc.exists() else []
    bad = [f"{r['page']}/{r['viewport']}" for r in rows if r["errors"] or r["failed"] or r["overflow"] > 0 or r["wide"] or r["badAnchors"] or r["brokenLocal"]]
    check("rendered pages clean (console, overflow, anchors, links)", bool(rows) and not bad,
          f"{len(rows)} page×viewport runs" + (f"; problems {bad}" if bad else "") if rows else "run node tools/qa_pages.mjs first")
    check("reader features present (TOC, anchors, copy, progress)", bool(rows) and all(
        r["toc"] and r["anchors"] and r["copyButtons"] == r["codeBlocks"] and r["progressAtHalf"] > 20 for r in rows), "")
    check("accessibility basics (one h1, no heading skips, labelled figures)", bool(rows) and all(
        r["h1"] == 1 and not r["headingSkips"] and not r["svgsNoLabel"] and not r["imgsMissingAlt"] for r in rows), "")

    # every printed number: the value the articles were built with is the published run's value, and a claim covers it
    uses = json.loads((ROOT / "docs" / "evidence-uses.json").read_text())
    facts = json.loads((POC / "runs" / run / "facts.json").read_text())
    claimed = {f for c in tomllib.loads((POC / "proof" / "claims.toml").read_text())["claims"] for f in c.get("facts", [])}
    stale = [k for k, u in uses.items() if k not in facts or facts[k]["value"] != u["value"]]
    unclaimed = sorted(set(uses) - claimed)
    check("article numbers match the published run and belong to a claim", bool(uses) and not stale and not unclaimed,
          f"{len(uses)} facts printed" + (f"; stale {stale[:5]}" if stale else "") + (f"; not in proof/claims.toml {unclaimed[:5]}" if unclaimed else ""))

    # the audit record the technical edition quotes is the run's own: its ids and hash prefixes appear in the audit chain
    audit = (POC / "runs" / run / "audit.jsonl").read_text()
    excerpt = md_text["headless-ai-technical"]
    quoted = re.findall(r'"(?:approval_id|idempotency_key|prev|hash|execution_id|correlation_id)": "([0-9a-z-]+)…?"', excerpt)
    absent = [q for q in quoted if q not in audit]
    check("quoted audit record matches the run's audit chain", bool(quoted) and not absent, f"{len(quoted)} quoted values" + (f"; not in the run {absent}" if absent else ""))

    handoff = [n for n, md in md_text.items() if HANDOFF not in md or "APPROVAL_REQUIRED" not in md or "Human-in-the-Loop" not in md]
    old = [n for n, md in md_text.items() if "REQUIRE_APPROVAL" in md]
    check("hand-off to T3 names the exact action and APPROVAL_REQUIRED", not handoff and not old,
          f"{HANDOFF}" + (f"; missing in {handoff}" if handoff else "") + (f"; old label in {old}" if old else ""))

    gh = sorted({u.rstrip(").,") for md in md_text.values() for u in re.findall(r"https://github\.com/ereshzealous/[^\s)\]>\"']+", md)})
    gh_bad = [(u, s) for u in gh if (s := answers(u)) != 200]
    check("GitHub links answer an anonymous reader", bool(gh) and not gh_bad, f"{len(gh)} links" + (f"; {gh_bad}" if gh_bad else ""))

    files = expand(PUBLISHED)
    leaks = local_path_findings(files, ROOT, forbid=[ROOT.parents[2], Path.home()])
    check("no local paths in any publication artifact (md, html, pdf streams, svg, json)", not leaks,
          f"{len(files)} files" + (f"; {[(f['file'], f['kind'], f['match']) for f in leaks[:4]]}" if leaks else ""))

    # the storyboard is one deliverable: every figure a frame AND the scene check passing (a missing check fails)
    scenes, sc = ROOT / "diagrams" / "scenes.json", ROOT / "diagrams" / "scene_check.json"
    frames = json.loads(scenes.read_text()) if scenes.exists() else {}
    s = json.loads(sc.read_text()) if sc.exists() else {}
    check("Excalidraw+ storyboard pushed and scene check passing", len(frames) == len(man) and s.get("ok", False),
          f"{len(frames)}/{len(man)} frames; " + ("; ".join(f"{c['check']}={'ok' if c['ok'] else 'FAIL'}" for c in s.get("checks", []))
                                                  or "diagrams/scene_check.json missing"))

    out = {"ok": all(r["ok"] for r in results), "passed": sum(r["ok"] for r in results), "total": len(results), "checks": results}
    (ROOT / "qa").mkdir(exist_ok=True)
    (ROOT / "qa" / "verification.json").write_text(json.dumps(out, indent=1))
    print(f"\n{out['passed']}/{out['total']} checks passed")
    sys.exit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
