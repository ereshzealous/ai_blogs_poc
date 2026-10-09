"""Shared helpers and the charts, rendered by machine from recorded data (SVG strings).

Charts are restrained: direct labels, no legends, no decorative grid; an interval is drawn as a line with a dot on it.
A series with `metric` becomes a link into the Lab Console (`data-metric`).  Their text styles live in each skin's CSS.
"""

from __future__ import annotations

import html
import math
import re


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def md(s) -> str:
    """Tiny inline markup: `code`, **bold**, *italic*."""
    t = esc(s)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    return re.sub(r"\*([^*]+)\*", r"<i>\1</i>", t)


# ---------------------------------------------------------------- charts (SVG, direct labels)

def _svg(w: int, h: int, aria: str, body: str) -> str:
    return f'<svg class="ek-chart" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(aria)}">{body}</svg>'


def rate_chart(c: dict) -> str:
    """Rows are variants, columns are factor values; each cell a 0–100% track with the interval and the estimate."""
    xs, series = c["x"], c["series"]
    W, lab, top, rowh, gap = 1000, 190, 36, 58, 28
    colw = (W - lab - gap * (len(xs) - 1)) / len(xs)
    H = top + rowh * len(series) + 8
    b = []
    for j, x in enumerate(xs):
        x0 = lab + j * (colw + gap)
        b.append(f'<text class="ek-ct" x="{x0:.1f}" y="16">{esc(x)} {esc(c.get("x_unit", ""))}</text>')
        b.append(f'<text class="ek-ct" x="{x0 + colw:.1f}" y="16" text-anchor="end">100%</text>')
    for i, s in enumerate(series):
        y = top + i * rowh + 26
        col = f'var(--{s["color"]})'
        if s.get("metric"):  # clickable in the Lab Console
            b.append(f'<g class="ek-hit" data-metric="{esc(s["metric"])}"><rect x="0" y="{y - 26}" width="{W}" height="{rowh}" fill="transparent"/>')
        b.append(f'<text class="ek-cl" x="0" y="{y + 4}" fill="{col}">{esc(s["label"].upper())}</text>')
        for j, x in enumerate(xs):
            p = next((q for q in s["points"] if q["x"] == x), None)
            if not p:
                continue
            x0 = lab + j * (colw + gap)
            px = lambda v: x0 + colw * v
            est = p["k"] / p["n"]
            b.append(f'<line x1="{x0:.1f}" x2="{x0 + colw:.1f}" y1="{y}" y2="{y}" class="ek-track"/>')
            b.append(f'<line x1="{px(p["lo"]):.1f}" x2="{px(p["hi"]):.1f}" y1="{y}" y2="{y}" stroke="{col}" stroke-width="3" stroke-linecap="round" opacity=".45"/>')
            b.append(f'<circle cx="{px(est):.1f}" cy="{y}" r="6" fill="{col}"><title>{esc(s["label"])} at {esc(x)}: {p["k"]}/{p["n"]}, 95% CI {round(100 * p["lo"])}–{round(100 * p["hi"])}%</title></circle>')
            anchor, dx = ("end", -12) if est > 0.5 else ("start", 12)
            b.append(f'<text class="ek-cv" x="{px(est) + dx:.1f}" y="{y - 10}" text-anchor="{anchor}">{round(100 * est)}%</text>')
            b.append(f'<text class="ek-cs" x="{px(est) + dx:.1f}" y="{y + 20}" text-anchor="{anchor}">{p["k"]}/{p["n"]} · {round(100 * p["lo"])}–{round(100 * p["hi"])}</text>')
        if s.get("metric"):
            b.append("</g>")
    return _svg(W, H, c.get("aria", c.get("title", "rates")), "".join(b))


def pair_chart(c: dict) -> str:
    """Per variant, two counts on one scale: `a` outlined (e.g. rows with a risky proposal) and `b` filled inside it
    (e.g. rows where one went through). The words come from the caller: a_word, b_word and a caption with {n}."""
    series, n = c["series"], max(s["n"] for s in c["series"])
    W, lab, rowh = 1000, 190, 62
    bw = W - lab - 250
    H = rowh * len(series) + 8
    b = []
    for i, s in enumerate(series):
        y = i * rowh + 20
        col = f'var(--{s["color"]})'
        if s.get("metric"):
            b.append(f'<g class="ek-hit" data-metric="{esc(s["metric"])}"><rect x="0" y="{y - 14}" width="{W}" height="{rowh}" fill="transparent"/>')
        b.append(f'<text class="ek-cl" x="0" y="{y + 10}" fill="{col}">{esc(s["label"].upper())}</text>')
        wp, we = bw * s["a"] / n, bw * s["b"] / n
        b.append(f'<rect x="{lab}" y="{y}" width="{bw}" height="16" class="ek-well"/>')
        b.append(f'<rect x="{lab}" y="{y}" width="{max(wp, 1):.1f}" height="16" fill="var(--amber-bg)" stroke="var(--amber)" stroke-width="1.2"/>')
        if s["b"]:
            b.append(f'<rect x="{lab}" y="{y}" width="{we:.1f}" height="16" fill="var(--red)"/>')
        tx = lab + wp + 10
        b.append(f'<text class="ek-cv" x="{tx:.1f}" y="{y + 13}">{s["a"]} {esc(c["a_word"])} · <tspan fill="{"var(--red)" if s["b"] else "var(--green)"}">{s["b"]} {esc(c["b_word"])}</tspan></text>')
        b.append(f'<text class="ek-cs" x="{lab}" y="{y + 36}">{esc(c["caption"].replace("{n}", str(s["n"])))}</text>')
        if s.get("metric"):
            b.append("</g>")
    return _svg(W, H, c.get("aria", c.get("title", "")), "".join(b))


def log_bars(c: dict) -> str:
    """Horizontal bars on a log scale, each labelled with its value."""
    rows, lo, hi = c["rows"], math.log10(c.get("min", 100)), math.log10(c.get("max", 40000))
    W, lab, rowh = 1000, 260, 30
    bw = W - lab - 110
    H = rowh * len(rows) + 6
    b = []
    for i, r in enumerate(rows):
        y = i * rowh + 8
        col = f'var(--{r["color"]})'
        w = max(2, bw * (math.log10(max(r["value"], 10 ** lo)) - lo) / (hi - lo))
        b.append(f'<text class="ek-cl2" x="0" y="{y + 11}">{esc(r["label"])}</text>')
        b.append(f'<rect x="{lab}" y="{y}" width="{w:.1f}" height="14" fill="{col}" opacity=".9"/>')
        b.append(f'<text class="ek-cv" x="{lab + w + 8:.1f}" y="{y + 12}">{r["value"]:,}</text>')
    return _svg(W, H, c.get("aria", c.get("title", "")), "".join(b))
