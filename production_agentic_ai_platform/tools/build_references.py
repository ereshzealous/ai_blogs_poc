"""docs/source/references.md: the numbered reference list, generated from research/sources.md (never typed twice).

    python3 tools/build_references.py

Each entry keeps its number, title, publisher, link, access date and type. Series entries link to the local edition,
relative to technical/ and medium/ (both one level below the package).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = re.compile(r"^\*\*\[(\d+)\]\*\* (.+)$", re.M)
URL = re.compile(r" — (https?://[^\s)]+|`[^`]+`)")


def main() -> None:
    src = (ROOT / "research" / "sources.md").read_text()
    out = ["## References", "",
           "Every external source was fetched and every quote matched against the fetched text; see `research/sources.md` for the quotes each "
           "source is cited for, and for what no source supports (the architecture itself is our synthesis).", ""]
    n = 0
    for m in ENTRY.finditer(src):
        num, line = m.groups()
        u = URL.search(line)
        head = line[:u.start()].split(" — ")
        title, pub = " — ".join(head[:-1]), head[-1]
        url = u.group(1).strip("`")
        date = re.search(r"accessed (\d{4}-\d{2}-\d{2})", line).group(1)
        typ = line.rsplit(" — ", 1)[-1].strip()
        link = f"[{url}]({url})" if url.startswith("http") else f"[{url}](../../{url})"
        out.append(f"**[{num}]** {title} — {pub}. {link} · accessed {date} · {typ}")
        out.append("")
        n += 1
    expected = len(re.findall(r"^\*\*\[\d+\]\*\* ", src, re.M))
    if n != expected:
        raise SystemExit(f"parsed {n} of {expected} entries; fix the pattern or the entry")
    (ROOT / "docs" / "source" / "references.md").write_text("\n".join(out).rstrip() + "\n")
    print(n, "references")


if __name__ == "__main__":
    main()
