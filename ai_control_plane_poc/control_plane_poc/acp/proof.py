"""Render one proof as a card: what was held constant, what changed centrally, what the systems of record show, and
every check with its result. The text is written to runs/<id>/proof.txt exactly as `acp proof` prints it.
"""

from __future__ import annotations

import textwrap

W = 78  # inner width of the box (fits a 680 px article column at 12 px)
LABEL = 19


def card(code: str, title: str, rows: list[tuple[str, str]], checks: list[dict], verdict: str | None = None) -> str:
    top = "╭" + "─" * (W + 2) + "╮"
    mid = "├" + "─" * (W + 2) + "┤"
    bot = "╰" + "─" * (W + 2) + "╯"
    line = lambda s: "│ " + s.ljust(W) + " │"
    out = [top, line(f"{code} — {title}"), mid]
    for label, value in rows:
        wrapped = textwrap.wrap(str(value), W - LABEL) or [""]
        out.append(line(f"{label[: LABEL - 1]:<{LABEL}}{wrapped[0]}"))
        out += [line(" " * LABEL + w) for w in wrapped[1:]]
    out.append(bot)
    for c in checks:
        mark = "✓" if c["passed"] else "✗"
        for i, w in enumerate(textwrap.wrap(c["check"], W)):
            out.append(f"  {mark if i == 0 else ' '} {w}")
    passed = all(c["passed"] for c in checks)
    out.append("")
    out.append(f"  PROOF {code}: " + (verdict or ("PASS" if passed else "FAIL")))
    out.append(f"  Test assertions: {sum(c['passed'] for c in checks)}/{len(checks)} passed")
    return "\n".join(out)
