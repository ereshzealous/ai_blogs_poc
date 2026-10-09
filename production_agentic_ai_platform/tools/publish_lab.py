"""Publish the Lab: one canonical page, results/production-agentic-ai-platform-lab.html.

    python3 tools/publish_lab.py

The POC generates lab/index.html from its run (that file is the POC's own output, documented in its README). This step copies it
to results/ and adds Open Graph / Twitter tags. Once docs/site.json has a site_base, both copies also get the same
<link rel="canonical"> pointing at the published results/ page, so the two files are one page to search engines and to Medium.
"""

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "production_agentic_ai_platform" / "lab" / "index.html"
DST = ROOT / "results" / "production-agentic-ai-platform-lab.html"
SITE = json.loads((ROOT / "docs" / "site.json").read_text())
MARK = "<!-- publish_lab -->"


def tags(page: str) -> str:
    e = lambda v: html.escape(v, quote=True)
    title = re.search(r"<title>(.*?)</title>", page).group(1)
    desc = re.search(r'<meta name="description" content="([^"]*)"', page).group(1)
    t = (f'{MARK}<meta property="og:type" content="website"><meta property="og:title" content="{title}">'
         f'<meta property="og:description" content="{desc}"><meta property="og:site_name" content="Production AI Engineering">'
         f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{title}">'
         f'<meta name="twitter:description" content="{desc}">')
    if SITE.get("site_base"):
        pack = sorted((ROOT / "medium" / "images").glob("*-governed-path.png")) or [ROOT / "medium" / "images" / "00-cover.png"]
        url, img = SITE["site_base"] + "results/" + DST.name, SITE["site_base"] + "medium/images/" + pack[0].name
        t += (f'<link rel="canonical" href="{e(url)}"><meta property="og:url" content="{e(url)}">'
              f'<meta property="og:image" content="{e(img)}"><meta name="twitter:image" content="{e(img)}">')
    return t + MARK


def stamp(page: str) -> str:
    page = re.sub(re.escape(MARK) + ".*?" + re.escape(MARK), "", page, flags=re.S)       # idempotent
    return page.replace("</title>", "</title>" + tags(page), 1)


def relink(page: str) -> str:
    """The POC's Lab links its run files relative to lab/; the copy in results/ points at the same files in the POC folder,
    or, once site_base is set, at the public POC repository."""
    base = SITE["poc_blob"] + "/evidence/" if SITE.get("site_base") else "../production_agentic_ai_platform/evidence/"
    return page.replace('href="../evidence/', f'href="{base}')


def main() -> None:
    page = SRC.read_text()
    DST.write_text(relink(stamp(page)))
    if SITE.get("site_base"):
        SRC.write_text(stamp(page))
    print(DST.relative_to(ROOT), "published" + (" (canonical set on both copies)" if SITE.get("site_base") else " (canonical waits for site_base)"))


if __name__ == "__main__":
    main()
