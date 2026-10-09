"""docs/source/technical/09-references.md from research/sources.md: one line per numbered source, in citation order.

    python3 tools/build_references.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    out = ["## References", "",
           "Every source was fetched on 2026-10-07 and is quoted in `research/sources.md` with the passage it supports and what it does "
           "*not* support. The historical results of F2, T5 and P1 are read from those packages' own recorded facts.", ""]
    for line in (ROOT / "research" / "sources.md").read_text().splitlines():
        m = re.match(r"^\*\*\[(\d+)\]\*\* (.+?) — (.+?) — (https?://\S+)", line)
        if not m:
            continue
        n, title, pub, url = m.groups()
        url = url.rstrip(".,;)")
        out.append(f"**[{n}]** {title} — {pub}. [{re.sub(r'^https?://', '', url)[:90]}]({url})\n")
    (ROOT / "docs" / "source" / "technical" / "09-references.md").write_text("\n".join(out) + "\n")
    print(sum(1 for l in out if l.startswith("**[")), "references")


if __name__ == "__main__":
    main()
