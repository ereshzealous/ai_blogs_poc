"""Assemble the published POC folder (github.com/ereshzealous/ai_blogs_poc/multi_agent_a2a_poc/) from this chapter.

    python3 tools/stage_public.py <out-dir>        -> <out-dir>/ in the chapter's shape, minus the editions

It copies and never moves: public/ (README rendered from its template, Makefile, .gitignore, .publish-frozen, publish
checks, LICENSE), the POC (coordination_poc/, every recorded run included), what `make verify` printed at publication
(verification/, without the JUnit file, which records the machine's hostname), the evidence documents (results/*.md),
the A2A notes and sources (research/), and the figures (diagrams/premium/png/). Keeping the chapter's shape means every
path the POC and its documents name (coordination_poc/runs/…, verification/…) resolves in the published folder.

The documents link to the editions and other chapters, which are not in the published folder: a relative link that
does not resolve there becomes its plain label (an image becomes its alt text). Then scripts/publish-poc.sh copies
<out-dir> into the repository, honouring its .gitignore.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "coordination_poc"
JUNK = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".DS_Store", "._*")
PUBLIC = ["Makefile", ".gitignore", ".publish-frozen", "LICENSE", "scripts/publish-checks.sh"]
POC_SKIP = {"README.template.md"}                      # the rendered README.md ships; its template needs the chapter tools
VERIFICATION = ["frozen-check.txt", "replay-check.txt", "replay-check.json", "pytest.txt", "d3-control.txt"]
RESULTS = ["multi-agent-a2a-report.md", "multi-agent-a2a-real-vs-simulated.md"]
RESEARCH = ["a2a-notes.md", "sources.md"]
LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")


def facts() -> dict:
    run = (POC / "runs" / "PUBLISHED").read_text().strip()
    return {k: v["value"] for k, v in json.loads((POC / "runs" / run / "facts.json").read_text()).items()}


def render(template: str, f: dict) -> str:
    def sub(m: re.Match) -> str:
        if m.group(1) not in f:
            sys.exit(f"stage_public: unknown fact {m.group(1)}")
        return str(f[m.group(1)])
    return re.sub(r"\{\{([\w.@\-]+)\}\}", sub, template)


def unlink_unresolved(md: Path, out: Path) -> int:
    """Relative links that do not resolve inside the published folder become their plain label."""
    n = 0

    def fix(m: re.Match) -> str:
        nonlocal n
        bang, label, target = m.groups()
        if re.match(r"^[a-z]+:|^#", target):
            return m.group(0)
        path = (md.parent / target.split("#")[0]).resolve()
        if path.exists() and out.resolve() in path.parents:
            return m.group(0)
        n += 1
        return label
    text = md.read_text()
    new = LINK.sub(fix, text)
    if new != text:
        md.write_text(new)
    return n


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = Path(sys.argv[1]).resolve()
    if out.exists() and any(out.iterdir()):
        sys.exit(f"stage_public: {out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    f = facts()
    (out / "README.md").write_text(render((ROOT / "public" / "README.template.md").read_text(), f))
    for rel in PUBLIC:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "public" / rel, out / rel)

    def poc_ignore(directory: str, names: list[str]) -> set[str]:
        skip = set(JUNK(directory, names))
        if Path(directory) == POC:
            skip |= POC_SKIP & set(names)
        return skip
    shutil.copytree(POC, out / "coordination_poc", ignore=poc_ignore)
    for sub, names in (("verification", VERIFICATION), ("results", RESULTS), ("research", RESEARCH)):
        (out / sub).mkdir()
        for n in names:
            shutil.copy2(ROOT / sub / n, out / sub / n)
    shutil.copytree(ROOT / "diagrams" / "premium" / "png", out / "diagrams" / "png", ignore=JUNK)
    unlinked = {str(md.relative_to(out)): unlink_unresolved(md, out)
                for md in [out / "README.md", out / "coordination_poc" / "README.md", *(out / "results").glob("*.md"),
                           *(out / "research").glob("*.md")]}
    files = [p for p in out.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files)
    print(f"staged {len(files)} files, {size / 1e6:.1f} MB -> {out}")
    print("links turned into plain labels:", {k: v for k, v in unlinked.items() if v})


if __name__ == "__main__":
    main()
