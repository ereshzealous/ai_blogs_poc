"""Assemble the published POC folder (github.com/ereshzealous/ai_blogs_poc/ai_control_plane_poc/) from this chapter.

    python3 tools/stage_public.py <out-dir>        -> <out-dir>/ with the chapter's shape, minus the editions and figures

It copies and never moves: public/ (README, Makefile, .gitignore, .publish-frozen, publish checks, LICENSE), the POC
(control_plane_poc/), the proof pack (proof/, evidence/), the verifiers the Makefile runs (tools/), the pinned
evidence-kit they import (vendor/kit5/), the evidence documents and the Lab Console (results/), the one figure the
Evidence Check shows, and docs/evidence-uses.json. Keeping the chapter's shape means every path recorded in the proof
pack (control_plane_poc/runs/…, evidence/runs/…) resolves in the published folder exactly as it does here.

The evidence documents link to the editions and to other chapters, which are not in the published folder: such a link
becomes its plain label (the same rule the PDF print uses), and a link to a document's .html points at its shipped .md.
Their Markdown hard line breaks are written as a trailing backslash, so the published copy has no trailing whitespace.
Then scripts/publish-poc.sh copies <out-dir> into the repository, honouring its .gitignore.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JUNK = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".DS_Store", "_scratch")
TOOLS = ["verify_run.py", "verify_evidence.py", "proof_pack.py", "proof_facts.py", "ledger.py"]
RESULTS = ["ai-control-plane-evidence.md", "ai-control-plane-report.md", "ai-control-plane-real-vs-simulated.md",
           "lab-console.html", "lab-console.evidence.json"]
FIGURES = ["diagrams/premium/png/poc-evidence.png"]
LIVE_KEPT = "ollama-2026-09-30T100218Z"
LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")


def poc_ignore(directory: str, names: list[str]) -> set[str]:
    out = set(JUNK(directory, names))
    if Path(directory).name == "live" and Path(directory).parent.name == "runs":
        out |= {n for n in names if n != LIVE_KEPT}
    return out


def localize(md: Path, out: Path) -> int:
    """Rewrite links that would not resolve in the published folder; return how many changed."""
    changed = 0

    def fix(m: re.Match) -> str:
        nonlocal changed
        bang, label, target = m.groups()
        if target.startswith(("http://", "https://", "#", "mailto:")):
            return m.group(0)
        path, _, anchor = target.partition("#")
        dest = (md.parent / path).resolve()
        if dest.is_relative_to(out.resolve()) and dest.exists():
            return m.group(0)
        if dest.suffix == ".html" and dest.with_suffix(".md").exists() and dest.is_relative_to(out.resolve()):
            changed += 1
            return f"{bang}[{label}]({Path(path).with_suffix('.md').as_posix()}{'#' + anchor if anchor else ''})"
        changed += 1
        return label if not bang else f"*({label})*"

    text = md.read_text()
    new = hard_breaks(LINK.sub(fix, text))
    if new != text:
        md.write_text(new)
    return changed


def hard_breaks(text: str) -> str:
    """Markdown hard line breaks written as two trailing spaces become a trailing backslash (CommonMark, as GitHub renders
    it), so the published copy has no trailing whitespace; trailing spaces that break nothing are dropped. Code blocks are
    left as they are. The chapter keeps the two-space form, which its own Markdown-to-HTML build needs."""
    lines, fence, out = text.split("\n"), False, []
    for i, line in enumerate(lines):
        if line.startswith("```"):
            fence = not fence
        if not fence and line != line.rstrip(" "):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            line = line.rstrip(" ") + ("\\" if line.endswith("  ") and nxt.strip() else "")
        out.append(line)
    return "\n".join(out)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1]).resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; give an empty or new directory")
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "public", out, dirs_exist_ok=True)
    shutil.copytree(ROOT / "control_plane_poc", out / "control_plane_poc", ignore=poc_ignore)
    shutil.copytree(ROOT / "proof", out / "proof", ignore=JUNK)
    shutil.copytree(ROOT / "evidence", out / "evidence", ignore=JUNK)
    shutil.copytree(ROOT / "vendor" / "kit5", out / "vendor" / "kit5", ignore=JUNK)
    for sub, names in (("tools", TOOLS), ("results", RESULTS)):
        (out / sub).mkdir(parents=True, exist_ok=True)
        for n in names:
            shutil.copy2(ROOT / sub / n, out / sub / n)
    for f in [*FIGURES, "docs/evidence-uses.json"]:
        (out / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, out / f)
    rewritten = {md.name: localize(md, out) for md in sorted((out / "results").glob("*.md"))}
    files = [p for p in out.rglob("*") if p.is_file()]
    print(f"staged {len(files)} files in {out}; links made local or plain: {rewritten}")


if __name__ == "__main__":
    main()
