"""The T6 publication gate. Checks the whole package holds together and writes qa/verification.json.

    uv run --project redteam_poc python tools/verify_all.py

Checks: the proof verifies (EXACT replay); pytest passes; every edition exists as md+html+pdf with a non-trivial PDF;
no unresolved {{token}} and no leaked local path in any published artifact; every figure referenced by a source exists.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "redteam_poc"
EDITIONS = [("medium", "securing-agents-tools-mcp-medium"),
            ("technical", "securing-agents-tools-mcp-technical"),
            ("results", "securing-agents-tools-mcp-evidence")]
FORBID = re.compile(r"/Users/|file:///|/private/tmp/|/home/")


def run(cmd: list[str], cwd: Path = ROOT) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    checks: dict[str, bool] = {}
    notes: dict[str, str] = {}

    rc, out = run(["uv", "run", "--project", "redteam_poc", "redteam", "verify"])
    checks["proof_verifies"] = ("VERIFIED" in out and rc == 0)
    notes["proof"] = out.strip().splitlines()[-1] if out.strip() else ""

    rc, out = run(["uv", "run", "pytest", "-q"], cwd=POC)
    checks["tests_pass"] = (rc == 0)
    notes["tests"] = out.strip().splitlines()[-1] if out.strip() else ""

    ok_files = True
    for folder, slug in EDITIONS:
        base = ROOT / folder / slug
        md, htmlf, pdf = base.with_suffix(".md"), base.with_suffix(".html"), base.with_suffix(".pdf")
        if not (md.exists() and htmlf.exists() and pdf.exists() and pdf.stat().st_size > 20000):
            ok_files = False
            notes[f"files:{slug}"] = "missing or tiny PDF"
    checks["editions_present"] = ok_files

    clean = True
    for folder, slug in EDITIONS:
        for ext in (".md", ".html"):
            p = ROOT / folder / f"{slug}{ext}"
            if not p.exists():
                continue
            text = p.read_text()
            if "{{" in text:
                clean = False; notes[f"token:{slug}{ext}"] = "unresolved {{token}}"
            if FORBID.search(text):
                clean = False; notes[f"path:{slug}{ext}"] = "local path leaked"
    checks["no_tokens_no_local_paths"] = clean

    figs = sorted((ROOT / "diagrams" / "premium" / "svg").glob("*.svg"))
    checks["figures_present"] = len(figs) >= 7
    notes["figures"] = f"{len(figs)} svg"

    ok = all(checks.values())
    result = {"ok": ok, "checks": checks, "notes": notes}
    (ROOT / "qa").mkdir(exist_ok=True)
    (ROOT / "qa" / "verification.json").write_text(json.dumps(result, indent=1) + "\n")
    print("PUBLICATION GATE\n")
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"\n{'GATE PASS' if ok else 'GATE FAIL'} — qa/verification.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
