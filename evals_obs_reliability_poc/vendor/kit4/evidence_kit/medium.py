"""The evidence components in Medium's own idiom (HTML strings for the Medium reading template, assets/medium.css).

Medium has paragraphs, headings, lists, quotes, pull quotes, code and captioned images, and nothing else.  So an
evidence statement is a pull quote with its source as the caption, a hypothesis is a bold lead and a short list, a
failure is a bold lead and a labelled list, and the claim boundary is three labelled lists with the conclusion pulled out.
"""

from __future__ import annotations

import re

from .components import esc, md

STATUS = {"SUPPORTED": "supported", "NOT SUPPORTED": "not supported", "CONTRADICTED": "contradicted", "NOT SHOWN": "not shown"}


def statement(s: dict) -> str:
    """An evidence statement as a pull quote: '15 rows at risk became 0 incidents'."""
    text = " ".join(s["lines"]).rstrip(".") + "."
    title = f' title="source: {esc(s["source"])}"' if s.get("source") else ""
    return (f'<figure class="m-pull"{title}><blockquote><p>{md(text)}</p></blockquote>'
            + (f'<figcaption>{md(s["meta"])}</figcaption>' if s.get("meta") else "") + "</figure>")


def claim(text: str) -> str:
    return f"<blockquote><p>{md(text)}</p></blockquote>"


def _pairs(rows) -> str:
    return "; ".join(f"{md(a)}: {md(b)}" for a, b in rows)


def hypothesis(h: dict) -> str:
    st = STATUS.get(h["status"].upper(), h["status"].lower())
    items = [f"<li><strong>Expected.</strong> {_pairs(h.get('expected', []))}</li>" if h.get("expected") else "",
             f"<li><strong>Observed.</strong> {_pairs(h.get('observed', []))}</li>" if h.get("observed") else "",
             f"<li>{md(h['note'])}</li>" if h.get("note") else ""]
    return (f'<p><strong>{esc(h["id"])}, {st}: {md(h["title"])}.</strong></p><ul>{"".join(items)}</ul>')


def failure(f: dict, why: str | None = None, href: str | None = None) -> str:
    rows = list(f["rows"])
    if why:
        rows.insert(len(rows) - 1, ["Why", why])
    items = "".join(f"<li><strong>{esc(k)}.</strong> {md(v)}</li>" for k, v in rows)
    note = md(f.get("note", "")) + (f' <a href="{esc(href)}">Open the row in the Lab Console.</a>' if href else "")
    return (f'<p><strong>Failure {int(f["n"])}: {md(f["title"])}.</strong></p><ul>{items}</ul>'
            + (f'<p class="m-note">{note}</p>' if note.strip() else ""))


BOUNDARY_GROUPS = [("supported", "What the evidence supports"), ("not_established", "What it does not show"), ("contradicted", "What it contradicted")]
BOUNDARY_PLAIN = [("supported", "Supported"), ("contradicted", "Contradicted"), ("not_established", "Not established")]  # 3.5


def boundary(b: dict, groups: list[tuple[str, str]] | None = None) -> str:
    """The claim boundary as lists; `groups` sets the order and labels (BOUNDARY_PLAIN: Supported · Contradicted · Not established)."""
    groups = groups or BOUNDARY_GROUPS
    out = "".join(f"<p><strong>{label}</strong></p><ul>" + "".join(f"<li>{md(x)}</li>" for x in b[key]) + "</ul>"
                  for key, label in groups if b.get(key))
    if b.get("conclusion"):
        out += f'<figure class="m-pull"><blockquote><p>{md(b["conclusion"])}</p></blockquote></figure>'
    return out


# ---------------------------------------------------------------- 3.4: panels (each is a figure in Medium's idiom; a
# Medium.com export rasterises it) and evidence classes

KINDS = {"REASONED": "Reasoned", "IMPLEMENTED": "Implemented", "VERIFIED": "Verified", "RECORDED": "Recorded",
         "MEASURED": "Measured", "LIMITATION": "Limitation"}
TONES = ("blue", "green", "red", "amber", "orange", "indigo", "grey")


def _tone(x: str | None) -> str:
    return x if x in TONES else "grey"


def _attr_id(pid: str) -> str:
    return f' id="{esc(pid)}"' if pid else ""


def _head(title: str, kicker: str = "") -> str:
    k = f'<span class="mp-k">{esc(kicker)}</span>' if kicker else ""
    return f'<div class="mp-h">{k}<b>{esc(title)}</b></div>'


def _cap(caption: str) -> str:
    return f"<figcaption>{md(caption)}</figcaption>" if caption else ""


def kind(kinds: list[str], text: str = "") -> str:
    """The evidence class of a section, under its heading: 'Measured · Recorded  the ranking of one request'."""
    tags = "".join(f'<span class="k k-{esc(k.lower())}">{esc(KINDS.get(k.upper(), k.title()))}</span>' for k in kinds)
    tail = f'<span class="t">{md(text)}</span>' if text else ""
    return f'<p class="m-kind">{tags}{tail}</p>'


def inspect(rows: list[tuple[str, str]], summary: str = "Inspect evidence") -> str:
    """A closed drawer under a number: definition, numerator and denominator, source pointer, the rows behind it.
    Values are HTML (the caller escapes)."""
    items = "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in rows)
    return f'<details class="m-inspect"><summary>{esc(summary)}</summary><dl>{items}</dl></details>'


def steps(title: str, items: list[dict], caption: str = "", pid: str = "", closing: str = "", kicker: str = "") -> str:
    """A numbered vertical panel.  Each item is {label, title, html, tone}; an item {divider: text} draws a labelled rule
    between steps (for example the guarantee boundary).  html is trusted (the caller renders it)."""
    lis = []
    for it in items:
        if it.get("divider"):
            lis.append(f'<li class="ms-div"><span>{esc(it["divider"])}</span></li>')
            continue
        h4 = f'<h4>{md(it["title"])}</h4>' if it.get("title") else ""
        lis.append(f'<li class="ms-s t-{_tone(it.get("tone"))}"><span class="ms-n">{esc(it.get("label", ""))}</span>'
                   f'<div class="ms-b">{h4}{it.get("html", "")}</div></li>')
    close = f'<p class="mp-close">{md(closing)}</p>' if closing else ""
    return (f'<figure class="m-panel m-steps"{_attr_id(pid)} role="group" aria-label="{esc(title)}">{_head(title, kicker)}'
            f'<ol>{"".join(lis)}</ol>{close}{_cap(caption)}</figure>')


def _card(c: dict) -> str:
    if c.get("big_to") is not None:  # a containment: 15 rows at risk -> 0 incidents
        big = (f'<div class="mw-flow"><div><b class="mw-big">{esc(c["big"])}</b><span>{md(c.get("from_label", ""))}</span></div>'
               f'<i aria-hidden="true">→</i><div class="to"><b class="mw-big">{esc(c["big_to"])}</b><span>{md(c.get("to_label", ""))}</span></div></div>')
    elif c.get("big") is not None:
        big = f'<b class="mw-big">{esc(c["big"])}</b>'
    else:
        big = ""
    bars = []
    for b in c.get("bars", []):
        label, value, share = b[0], b[1], max(0.0, min(1.0, float(b[2])))
        tone = _tone(b[3] if len(b) > 3 else None)
        bars.append(f'<div class="mw-bar t-{tone}"><span>{md(label)}</span><div class="mw-track"><i style="width:{share * 100:.1f}%"></i></div>'
                    f'<b>{esc(value)}</b></div>')
    cls = f'mw-card t-{_tone(c.get("tone"))}' + (" span2" if c.get("span") == 2 else "")
    metric = f' data-metric="{esc(c["metric"])}"' if c.get("metric") else ""
    parts = [f'<span class="mw-k">{esc(c.get("kicker", ""))}</span>', big]
    if c.get("sub"):
        parts.append(f'<p class="mw-sub">{md(c["sub"])}</p>')
    if bars:
        parts.append(f'<div class="mw-bars">{"".join(bars)}</div>')
    if c.get("note"):
        parts.append(f'<p class="mw-note">{md(c["note"])}</p>')
    parts.append(c.get("inspect", ""))
    return f'<div class="{cls}"{metric}>{"".join(parts)}</div>'


def wall(cards: list[dict], caption: str = "", pid: str = "", title: str = "", kicker: str = "") -> str:
    """An evidence wall: cards {kicker, big, big_to?, from_label?, to_label?, sub, bars[(label, value, share, tone)], note,
    tone, span (1|2), metric, inspect}.  Bars are drawn to the shares given; the values are printed beside them."""
    head = _head(title, kicker) if title else ""
    label = esc(title or re.sub(r"[*`]", "", caption))
    return (f'<figure class="m-panel m-wall"{_attr_id(pid)} role="group" aria-label="{label}">{head}'
            f'<div class="mw-grid">{"".join(_card(c) for c in cards)}</div>{_cap(caption)}</figure>')


def checklist(title: str, rows: list[tuple[str, str, str]], caption: str = "", pid: str = "", kicker: str = "") -> str:
    """Invariants asserted by code: rows (what is attempted, what the platform does, the test that asserts it)."""
    lis = "".join(f'<li><span class="mc-ok" aria-hidden="true">✓</span><div><b>{md(a)}</b><span class="mc-r">{md(r)}</span>'
                  f'<code class="mc-t">{esc(t)}</code></div></li>' for a, r, t in rows)
    return (f'<figure class="m-panel m-check"{_attr_id(pid)} role="group" aria-label="{esc(title)}">{_head(title, kicker)}'
            f'<ul>{lis}</ul>{_cap(caption)}</figure>')


# ---------------------------------------------------------------- 3.5: a reusable legend for the evidence classes, and a
# compact callout (for example a post-run review disclosure)

KIND_MEANING = {"MEASURED": "aggregate blind-run evidence", "RECORDED": "one actual row or trace", "IMPLEMENTED": "exists in the POC",
                "VERIFIED": "a deterministic test", "REASONED": "an architecture conclusion from the evidence",
                "LIMITATION": "not established here"}


def legend(meanings: dict[str, str] | None = None, title: str = "Evidence labels", collapsed: bool = False) -> str:
    """One small line, once near the top: each evidence class and what it means.  `meanings` overrides the defaults.
    `collapsed` (3.6) folds it into a one-line drawer, so the reader reaches the story first."""
    m = {**KIND_MEANING, **(meanings or {})}
    items = "".join(f'<span class="it"><span class="k k-{esc(k.lower())}">{esc(KINDS.get(k, k.title()))}</span>{esc(v)}</span>'
                    for k, v in m.items())
    if collapsed:
        return (f'<details class="m-legend-d"><summary>{esc(title)}: what each section label means</summary>'
                f'<p class="m-kind m-legend" role="note" aria-label="{esc(title)}">{items}</p></details>')
    return f'<p class="m-kind m-legend" role="note" aria-label="{esc(title)}"><span class="lt">{esc(title)}</span>{items}</p>'


def callout(kicker: str, body: str, href: str | None = None, link: str = "Details") -> str:
    """A compact aside: a kicker, one or more short paragraphs (inline markup; blank lines separate them) and a link."""
    paras = [md(p.strip()) for p in re.split(r"\n\s*\n", body.strip()) if p.strip()]
    if href:
        paras[-1] += f' <a href="{esc(href)}">{esc(link)}</a>'
    return f'<aside class="m-callout" role="note"><span class="ck">{esc(kicker)}</span>' + "".join(f"<p>{p}</p>" for p in paras) + "</aside>"



# ---------------------------------------------------------------- 3.6: a four-line experiment brief with a metadata strip,
# the claim boundary as one visual panel, and compact failure cards

BRIEF_TONES = {"problem": "red", "test": "blue", "result": "green", "limits": "amber"}


def brief(rows: list[tuple[str, str]], meta: list[tuple[str, str]] | None = None, title: str = "", kicker: str = "",
          caption: str = "", pid: str = "panel-brief") -> str:
    """The experiment in four lines, PROBLEM → TEST → RESULT → LIMITS (or any labels), then a small strip of run facts.
    rows: (label, markdown); meta: (value, label)."""
    lis = "".join(f'<li class="mb-r t-{_tone(BRIEF_TONES.get(k.lower()))}"><span class="mb-l">{esc(k)}</span>'
                  f'<span class="mb-t">{md(v)}</span></li>' for k, v in rows)
    strip = ("" if not meta else '<p class="mb-meta">' + "".join(f'<span><b>{esc(v)}</b> {esc(lbl)}</span>' for v, lbl in meta) + "</p>")
    head = _head(title, kicker) if title else ""
    return (f'<figure class="m-panel m-brief"{_attr_id(pid)} role="group" aria-label="{esc(title or "Experiment brief")}">{head}'
            f'<ol class="mb-rows">{lis}</ol>{strip}{_cap(caption)}</figure>')


BOUNDARY_PANEL = [("supported", "Supported", "green", "✓"), ("contradicted", "Contradicted", "red", "✕"),
                  ("not_established", "Not established", "grey", "?")]


def boundary_panel(b: dict, title: str = "Claim boundary", kicker: str = "", caption: str = "", pid: str = "panel-boundary",
                   groups: list[tuple[str, str, str, str]] | None = None) -> str:
    """The claim boundary as one visual: a column per verdict (Supported · Contradicted · Not established), each claim a
    short card.  The facts are the caller's, unchanged."""
    cols = []
    for key, label, tone, mark in groups or BOUNDARY_PANEL:
        if not b.get(key):
            continue
        items = "".join(f"<li>{md(x)}</li>" for x in b[key])
        cols.append(f'<section class="mbd-c t-{_tone(tone)}"><h4><span class="mbd-m" aria-hidden="true">{mark}</span>{esc(label)}'
                    f'<span class="mbd-n">{len(b[key])}</span></h4><ul>{items}</ul></section>')
    head = _head(title, kicker) if title else ""
    return (f'<figure class="m-panel m-bound"{_attr_id(pid)} role="group" aria-label="{esc(title)}">{head}'
            f'<div class="mbd-g">{"".join(cols)}</div>{_cap(caption)}</figure>')


def failure_card(f: dict, why: str, href: str | None = None, link: str = "The model's words and the row, in the Lab Console") -> str:
    """A failure as three short lines: OBSERVED (the recorded summary), WHY IT MATTERS (the author's reading) and NEXT
    CHANGE; the long model quote and the row ids stay behind the link."""
    nxt = dict(f.get("rows", [])).get("Next change", "")
    rows = [("Observed", f.get("summary", "")), ("Why it matters", why), ("Next change", nxt)]
    items = "".join(f"<div><dt>{esc(k)}</dt><dd>{md(v)}</dd></div>" for k, v in rows if v)
    a = f'<a class="fc-a" href="{esc(href)}">{esc(link)} →</a>' if href else ""
    return (f'<div class="m-fcard"><p class="fc-t"><span class="fc-n">Failure {int(f["n"])}</span>{md(f["title"])}</p>'
            f'<dl>{items}</dl>{a}</div>')
