"""research/cite-keys.json and docs/source/technical/09-references.md, both from research/sources.md.

    python3 tools/build_references.py              check cite-keys.json against sources.md, then write 09-references.md
    python3 tools/build_references.py --write-keys (re)write cite-keys.json from sources.md first

Ported from C1, itself ported from R1+R2 (evals_obs_reliability/tools/build_references.py).  The sources.md lists its sources as Markdown
table rows (| `key` | Title — URL [more] | supports | does not support |) rather than R1+R2's numbered "**[n]**" lines,
so the numbering lives in research/cite-keys.json:

    {"a2a-spec": {"n": 1, "title": "...", "url": "https://...", "also": ["https://..."], "note": "..."}, ...}

n is the order of first appearance in sources.md; title and url are copied verbatim from the row ("also": further URLs
in the same cell, "note": the cell's remaining text; both only when present).  tools/build_docs.py turns [[@key]] into
[[n]] and uses the title as the citation's hover text.  A cite-keys.json that has drifted from sources.md is a failure.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "research" / "sources.md"
KEYS = ROOT / "research" / "cite-keys.json"
OUT = ROOT / "docs" / "source" / "technical" / "99-references.md"
ROW = re.compile(r"^\|\s*`([\w.@-]+)`\s*\|\s*(.+?)\s*\|")
URL = re.compile(r"https?://[^\s,;)]+")


def parse_sources() -> dict:
    """{key: {n, title, url[, also][, note]}} from the table rows of research/sources.md, in order of appearance."""
    out: dict = {}
    for line in SOURCES.read_text().splitlines():
        m = ROW.match(line)
        if not m:
            continue
        key, cell = m.groups()
        title, sep, rest = cell.partition(" — ")
        urls = URL.findall(rest)
        if not sep or not urls:
            sys.exit(f"sources.md: row `{key}` has no 'Title — URL' source cell")
        if key in out:
            sys.exit(f"sources.md: key `{key}` listed twice")
        entry = {"n": len(out) + 1, "title": title.strip(), "url": urls[0]}
        if urls[1:]:
            entry["also"] = urls[1:]
        note = URL.sub("", rest).strip(" ,;")
        if note:
            entry["note"] = note
        out[key] = entry
    if not out:
        sys.exit("sources.md: no source rows found")
    return out


def main() -> None:
    parsed = parse_sources()
    if "--write-keys" in sys.argv[1:]:
        KEYS.write_text(json.dumps(parsed, indent=1, ensure_ascii=False) + "\n")
        print(f"research/cite-keys.json: {len(parsed)} keys")
    keys = json.loads(KEYS.read_text())
    if keys != parsed:
        drift = sorted(k for k in set(keys) | set(parsed) if keys.get(k) != parsed.get(k))
        sys.exit(f"research/cite-keys.json has drifted from research/sources.md: {drift} (run with --write-keys)")
    out = ["## References", "",
           "Every source is listed in `research/sources.md` with what it supports in this article and what it does *not* "
           "support.", ""]
    for key, s in sorted(keys.items(), key=lambda kv: kv[1]["n"]):
        links = " · ".join(f"[{re.sub(r'^https?://', '', u)[:90]}]({u})" for u in [s["url"], *s.get("also", [])])
        note = s.get("note", "")
        note = (f" {note}" if note.startswith("(") else f"; {note}") if note else ""
        out.append(f"**[{s['n']}]** {s['title']}{note}. {links}\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(out) + "\n")
    print(sum(1 for line in out if line.startswith("**[")), "references")


if __name__ == "__main__":
    main()
