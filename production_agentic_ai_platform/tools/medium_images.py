"""Medium image pack: every figure the Medium story shows, in article order, as a 1600 px wide PNG with the text that goes with it.

    python3 tools/medium_images.py          -> medium/images/NN-<figure>.png + medium/images/CAPTIONS.md

Medium's editor takes JPG/PNG/GIF (not the inline SVG the standalone page uses); 1192 px or wider unlocks every layout option.
For each image CAPTIONS.md gives the figure number, its badge (ARCHITECTURE / MEASURED), the caption, the provenance line and the
alt text, all read from the built Medium Markdown, so they are exactly what the standalone page says.

docs/site.json "medium_omit_figures" (figure ids, default none) leaves figures out of the Medium story only; the standalone
page keeps them. The story's figures are then renumbered in order, which is safe because the prose never cites a figure number.
"""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "medium" / "images"
SITE = json.loads((ROOT / "docs" / "site.json").read_text())
IMG = re.compile(r"!\[(.*?)\]\(\.\./diagrams/premium/png/([\w-]+)\.png\)\n+([^\n]*)")
CAP = re.compile(r"^((?:`[A-Z ]+`\s*)*)\*Figure (\d+)\.\s*(.*?)\*(?: · (.*))?$")


def main() -> None:
    md = (ROOT / "medium" / "production-agentic-ai-platform-medium.md").read_text()
    omit = set(SITE.get("medium_omit_figures") or [])
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("[0-9][0-9]-*.png"):   # generated files only; rebuilt below
        old.unlink()
    rows, n = [], 0
    for i, m in enumerate(IMG.finditer(md)):
        alt, fig, line = m.groups()
        c = CAP.match(line.strip())
        if i == 0:
            if c:
                raise SystemExit("the Medium Markdown did not start with the cover figure")
            badges, std, cap, prov = [], None, "", ""
        else:
            if not c:
                raise SystemExit(f"no caption line under {fig}: {line[:80]!r}")
            badges, std, cap, prov = re.findall(r"`([A-Z ]+)`", c.group(1)), int(c.group(2)), c.group(3), c.group(4) or ""
            if fig in omit:
                continue
            n += 1
        name = f"{n:02d}-{'cover' if i == 0 else fig}.png"
        subprocess.run(["sips", "--resampleWidth", "1600", str(ROOT / "diagrams" / "premium" / "png" / f"{fig}.png"), "--out", str(OUT / name)],
                       capture_output=True, check=True)
        dims = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(OUT / name)], capture_output=True, text=True).stdout
        w, h = (int(x) for x in re.findall(r"pixel(?:Width|Height): (\d+)", dims))
        rows.append({"name": name, "w": w, "h": h, "n": n if i else None, "std": std, "badges": badges, "cap": cap, "prov": prov, "alt": alt})
    missing = omit - {m.group(2) for m in IMG.finditer(md)}
    if missing:
        raise SystemExit(f"medium_omit_figures names figures the Medium edition does not have: {sorted(missing)}")
    out = ["# Medium image pack", "",
           "Every figure of the Medium story, in article order, as PNG at 1600 px wide (Medium accepts JPG/PNG/GIF, not SVG; 1192 px or",
           "wider unlocks every layout). Upload each image where the article places it, paste its caption line under it, and paste the",
           "alt text into Medium's alt-text field. Regenerate with `make medium-images` after any figure change.", ""]
    if omit:
        out += [f"Left out of the Medium story (kept in the standalone page): {', '.join(sorted(omit))}. The story's figures are renumbered;",
                "each entry also gives the figure's number in the standalone page.", ""]
    for r in rows:
        out += [f"## {r['name']}", "", f"*{r['w']} × {r['h']} px*", ""]
        if r["n"] is None:
            out += ["**Caption:** none (the cover image)", ""]
        else:
            badge = " · ".join(r["badges"])
            out += [f"**Figure {r['n']}**" + (f" (standalone page: Figure {r['std']})" if r["std"] != r["n"] else "") + f" · `{badge}`", "",
                    "**Caption line (paste under the image):**", "",
                    f"> Figure {r['n']} · {badge}. {r['cap']}" + (f" Provenance: {r['prov']}" if r["prov"] else ""), ""]
        out += [f"**Alt text:** {r['alt']}", ""]
    (OUT / "CAPTIONS.md").write_text("\n".join(out))
    print(len(rows), "images ->", OUT, f"(omitted: {sorted(omit)})" if omit else "")


if __name__ == "__main__":
    main()
