"""Assemble the Medium upload kit from the Medium edition.

    python3 tools/medium_kit.py

Writes medium/images/NN-<figure>.png in order of appearance, and medium/PUBLISHING.md: for each image, where it goes,
its caption and its alt text, ready to paste into Medium's editor (Medium has no tables and no figure import).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "medium" / "authorization-and-policy-for-ai-agents-medium.md"
IMAGES = ROOT / "medium" / "images"


def main() -> None:
    text = SRC.read_text()
    figs = re.finditer(r"!\[(.*?)\]\((?:\.\./)?(assets/png/[^)]+)\)\s*\n(?:\s*\n\*(Figure[^\n]*)\*)?", text)
    if IMAGES.exists():
        shutil.rmtree(IMAGES)
    IMAGES.mkdir(parents=True)
    rows, missing = [], []
    headings = [(m.start(), m.group(1)) for m in re.finditer(r"^## (.+)$", text, re.M)]
    for i, m in enumerate(figs):
        alt, src, cap = m.group(1), ROOT / m.group(2), m.group(3) or "(cover, no caption)"
        if not src.exists():
            missing.append(src.name)
            continue
        name = f"{i:02d}-{src.stem}.png"
        shutil.copy(src, IMAGES / name)
        section = next((h for pos, h in reversed(headings) if pos < m.start()), "Top of the post")
        rows.append((name, section, cap.strip("*"), alt))

    out = ["# Medium publishing kit · Authorization and Policy for AI Agents", "",
           "Upload the images in `images/` in this order (all PNG, 3200 px wide from a 1600-px canvas, above Medium's "
           "1192-px minimum for every placement option). Paste each caption into the image caption field, and each alt "
           "text into the image's alt-text field (… menu → Alt text). Medium doesn't render tables, custom CSS or embeds, "
           "so this edition has no tables: every table became a figure. The standalone HTML is the canonical web edition; "
           "this kit is the Medium edition.", "",
           "- **Title:** Your AI Agent Has an Identity. What Is It Allowed to Do?",
           "- **Subtitle:** A production architecture for fine-grained authorization, delegated authority, contextual "
           "policy, approval gates and auditable tool execution.",
           "- **Kicker / series line (first line of the body, bold):** Authorization & Policy for AI Agents · Production AI Engineering, part 5",
           "- **Tags (max 5):** AI Agents · Authorization · Platform Engineering · Security · LLM",
           "- **Featured image (feed thumbnail):** `images/00-mc0-cover-feed.png` (3200 px wide; set the focal point on the policy gate)", "",
           "Code blocks: paste them as Medium code blocks (``` on a new line). The Medium edition keeps only three short ones.", ""]
    for n, (name, section, cap, alt) in enumerate(rows):
        out += [f"## {n:02d} · `{name}`", "", f"- **Section:** {section}", f"- **Caption:** {cap}", f"- **Alt text:** {alt}", ""]
    if missing:
        out += ["## Missing images", ""] + [f"- {m}" for m in missing]
    (ROOT / "medium" / "PUBLISHING.md").write_text("\n".join(out) + "\n")
    print(f"{len(rows)} images copied to medium/images, {len(missing)} missing: {missing}")


if __name__ == "__main__":
    main()
