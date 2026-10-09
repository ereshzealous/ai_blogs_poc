#!/usr/bin/env python3
"""Build the web edition: a visual-first HTML page.

    python3 tools/build_html.py article/memory-context-state.md article/memory-context-state.html        # one file, figures inlined
    python3 tools/build_html.py article/memory-context-state.md web/index.html --external-assets \
        --canonical https://example.com/post --og-image https://example.com/cover.png         # public web

- **Default output:** a complete HTML document (doctype, charset, viewport, description and Open Graph tags).
- **`--bare`:** drops the doctype, html, head and body tags and uses the short page name, for hosts that add their own skeleton.
- **`--external-assets`:** writes the figures next to the page, in `assets/`, and loads them lazily; otherwise they are inlined as data URIs.

One web-only component comes from the POC's recorded run: a strip of measured results at the `<!-- measured-in-the-poc -->` marker, replacing the quote that follows it in the Markdown (after the facts line when there is no marker). `<!-- eyebrow: X -->` lines become small section labels.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
POC = HERE / "memory-context-state-poc"


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


ASSETS: dict[str, Path | None] = {"dir": None}  # set by --external-assets


def data_uri(path: Path) -> str:
    mime = {".svg": "image/svg+xml", ".png": "image/png"}[path.suffix]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def figure(root: Path, alt: str, src: str, caption: str, idx: int, cover: bool) -> str:
    if ASSETS["dir"]:
        out = ASSETS["dir"] / Path(src).name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes((root / src).read_bytes())
        uri = f"assets/{out.name}"
    else:
        uri = data_uri(root / src)
    cls = "fig cover" if cover else "fig"
    zoom = "" if cover else (f'<button class="zoom" type="button" data-fig="{idx}" aria-label="Open figure full size">'
                             '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>'
                             "Full size</button>")
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return (f'<figure class="{cls}" id="fig-{idx}"><div class="paper"><img alt="{html.escape(alt)}" src="{uri}" '
            f'loading="{"eager" if idx < 3 else "lazy"}" decoding="async">{zoom}</div>{cap}</figure>')


def table(rows: list[list[str]]) -> str:
    head, body = rows[0], rows[1:]
    heat = any("gpt-oss" in h for h in head)
    cls = "tbl heat" if heat else "tbl"

    def cell(c: str) -> str:
        m = re.fullmatch(r"\**(\d+)/(\d+)\**", c.strip())
        if heat and m:
            ratio = int(m.group(1)) / max(1, int(m.group(2)))
            level = "full" if ratio == 1 else "part" if ratio > 0 else "none"
            return f'<td class="hc {level}"><span>{html.escape(c.strip("*"))}</span></td>'
        return f"<td>{inline(c)}</td>"

    return (f'<div class="tbl-wrap"><table class="{cls}"><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in head)
            + "</tr></thead><tbody>" + "".join("<tr>" + "".join(cell(c) for c in r) + "</tr>" for r in body)
            + "</tbody></table></div>")


def convert(md: str, root: Path) -> tuple[str, str, list[tuple[str, str]]]:
    lines = md.split("\n")
    out: list[str] = []
    toc: list[tuple[str, str]] = []
    title = ""
    i = fig = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if not title and not line.startswith("# "):
            # the series kicker above the H1 is the topbar on the web
            i += 1
            continue
        m = re.fullmatch(r"<!--\s*(.*?)\s*-->", line.strip())
        if m:
            # markers invisible in Markdown: section eyebrows and where the results strip goes
            if m.group(1).startswith("eyebrow:"):
                out.append(f'<p class="kicker">{html.escape(m.group(1)[8:].strip())}</p>')
            elif m.group(1) == "measured-in-the-poc":
                # the Markdown carries the headline numbers as a quote; the web shows the results strip instead
                out.append("<!--RESULTS-->")
                i += 1
                while i < len(lines) and lines[i].startswith(">"):
                    i += 1
                continue
            i += 1
            continue
        if line.startswith("```"):
            lang = line[3:].strip()
            j, code = i + 1, []
            while j < len(lines) and not lines[j].startswith("```"):
                code.append(lines[j])
                j += 1
            body = html.escape("\n".join(code))
            term = lang == "" and code and code[0].startswith("$")
            if term:
                body = re.sub(r"^(\$ .*)$", r'<span class="cmd">\1</span>', body, flags=re.M)
            cls = "term" if term else ("code" + (f" lang-{lang}" if lang else ""))
            label = "terminal" if term else (lang or "text")
            out.append(f'<div class="{cls}"><div class="code-bar"><span></span><span></span><span></span><em>{label}</em></div>'
                       f"<pre><code>{body}</code></pre></div>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            level, text = len(m.group(1)), m.group(2)
            if level == 1:
                title = text
            else:
                anchor = slug(text)
                if level == 2:
                    toc.append((anchor, text))
                out.append(f'<h{level} id="{anchor}">{inline(text)}</h{level}>')
            i += 1
            continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", line)
        if m:
            caption = ""
            if i + 2 < len(lines) and re.match(r"^\*[^*].*\*$", lines[i + 2].strip()):
                caption = inline(lines[i + 2].strip()[1:-1])
                i += 2
            out.append(figure(root, m.group(1), m.group(2), caption, fig, fig == 0))
            fig += 1
            i += 1
            continue
        if line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip("> ").rstrip())
                i += 1
            out.append('<blockquote class="lede">' + "".join(f"<p>{inline(q)}</p>" for q in quote if q) + "</blockquote>")
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s:|-]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append(table(rows))
            continue
        if re.match(r"^(\s*)(- |\d+\. )", line):
            ordered = bool(re.match(r"^\d+\. ", line))
            items: list[tuple[int, str]] = []
            while i < len(lines) and re.match(r"^(\s*)(- |\d+\. )", lines[i]):
                ind = len(re.match(r"^(\s*)", lines[i]).group(1))
                items.append((ind, re.sub(r"^\s*(- |\d+\. )", "", lines[i])))
                i += 1
            tag = "ol" if ordered else "ul"
            html_items, depth, open_li = [f"<{tag}>"], 0, [False]
            for ind, text in items:
                d = ind // 2
                if d > depth:  # a nested list opens inside the item that is still open
                    while depth < d:
                        html_items.append("<ul>")
                        depth += 1
                        open_li.append(False)
                else:
                    while depth > d:
                        if open_li.pop():
                            html_items.append("</li>")
                        html_items.append("</ul>")
                        depth -= 1
                    if open_li[-1]:
                        html_items.append("</li>")
                html_items.append(f"<li>{inline(text)}")
                open_li[-1] = True
            while depth > 0:
                if open_li.pop():
                    html_items.append("</li>")
                html_items.append("</ul>")
                depth -= 1
            html_items += ["</li>"] if open_li[-1] else []
            html_items.append(f"</{tag}>")
            out.append("".join(html_items))
            continue
        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|!\[|>|\||```|\s*- |\d+\. )", lines[i]):
            para.append(lines[i])
            i += 1
        text = " ".join(p.strip() for p in para)
        if text.startswith("*") and text.endswith("*") and not text.startswith("**"):
            out.append(f'<p class="tagline">{inline(text[1:-1])}</p>')
        elif text.startswith("**S1 · ") or text.startswith("**Run `"):
            out.append(f'<p class="facts">{"".join(f"<span>{inline(t.strip(" *"))}</span>" for t in text.split("·"))}</p>')
        else:
            out.append(f"<p>{inline(text)}</p>")
    return title, "\n".join(out), toc


# --------------------------------------------------------------------------- web-only components
def results_strip(n: dict, run_id: str) -> str:
    tiles = [
        # the last field separates the pair: → for before-to-after, "vs" for a side-by-side comparison
        ("Invalid evidence admitted to context", n["naive_invalid_total"], n["governed_invalid_total"], "naive", "governed", "red", "→"),
        ("Useful recall, combined scenario (M0)", n["m0_naive_recall"], n["m0_gov_recall"], "naive", "governed", "teal", "→"),
        ("Memory said \"approval done\"; workflow said wait (M9)", f'{n["m9_naive_proceeded"]}/{n["m9_runs"]}', f'{n["m9_gov_waited"]}/{n["m9_runs"]}', "naive proceeded", "governed waited", "orange", "vs"),
        ("Preregistered governed invariants", n["invariants"], n["tests"], "passed", "tests, no model", "green", "·"),
    ]
    cards = "".join(
        f'<div class="tile t-{tone}"><div class="t-title">{html.escape(t)}</div><div class="t-pair"><div><b>{a}</b><span>{la}</span></div>'
        f'<i aria-hidden="true">{sep}</i><div><b>{b}</b><span>{lb}</span></div></div></div>'
        for t, a, b, la, lb, tone, sep in tiles)
    return (f'<section class="results" aria-label="Measured in the POC"><div class="r-head"><span class="eyebrow">Measured in the POC</span>'
            f'<span class="r-note">run {run_id} · local Ollama {n["model"]} · {n["decisions_total"]} recorded decisions · frozen {n["frozen_digest"]}</span></div>'
            f'<div class="tiles">{cards}</div></section>')


CSS = r"""
:root{--ground:#F5F7FB;--surface:#FFFFFF;--ink:#172B4D;--muted:#52637A;--faint:#61738B;--line:#D5DEEA;--wash:#EDF2F8;--paper:#FFFFFF;
--blue:#2F6FDE;--blue-t:#EEF4FF;--purple:#6D5BD0;--purple-t:#F3F0FF;--orange:#B45F06;--orange-s:#D97706;--orange-t:#FFF6E5;
--teal:#0B7585;--teal-s:#0E8FA3;--teal-t:#E5F6F8;--green:#17805E;--green-s:#1F9D74;--green-t:#EAF8F2;--red:#B83A50;--red-s:#D14D63;--red-t:#FFF0F2;
--dark:#334155;--dark-t:#E8ECF1;--gray:#64748B;--gray-t:#F1F5F9;--code-bg:#0F1A2E;--code-ink:#DDE6F3;
--display:"Lilita One","Arial Rounded MT Bold","Trebuchet MS",sans-serif;--sans:"Nunito",ui-sans-serif,-apple-system,"Segoe UI",sans-serif;
--mono:"JetBrains Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ground:#0C1320;--surface:#131D2E;--ink:#E4EAF3;--muted:#A6B2C6;--faint:#7D8BA3;--line:#27354C;--wash:#182338;
--blue:#86ACF4;--blue-t:#1A2946;--purple:#AA9DF3;--purple-t:#241F44;--orange:#F3B05A;--orange-s:#F3B05A;--orange-t:#33260F;--teal:#56CAD9;--teal-s:#56CAD9;--teal-t:#0F2E35;
--green:#5BCDA6;--green-s:#5BCDA6;--green-t:#10302A;--red:#F28B9C;--red-s:#F28B9C;--red-t:#3A1A22;--dark:#B8C3D4;--dark-t:#243149;--gray:#9AA8BC;--gray-t:#1D293E;--code-bg:#080E19;}}
:root[data-theme="dark"]{--ground:#0C1320;--surface:#131D2E;--ink:#E4EAF3;--muted:#A6B2C6;--faint:#7D8BA3;--line:#27354C;--wash:#182338;
--blue:#86ACF4;--blue-t:#1A2946;--purple:#AA9DF3;--purple-t:#241F44;--orange:#F3B05A;--orange-s:#F3B05A;--orange-t:#33260F;--teal:#56CAD9;--teal-s:#56CAD9;--teal-t:#0F2E35;
--green:#5BCDA6;--green-s:#5BCDA6;--green-t:#10302A;--red:#F28B9C;--red-s:#F28B9C;--red-t:#3A1A22;--dark:#B8C3D4;--dark-t:#243149;--gray:#9AA8BC;--gray-t:#1D293E;--code-bg:#080E19;}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);font-family:var(--sans);font-size:18px;line-height:1.7;margin:0}
.shell{display:grid;grid-template-columns:minmax(0,1fr);max-width:1180px;margin:0 auto;padding-inline:20px;padding-block:28px 96px;gap:40px}
@media (min-width:1180px){.shell{grid-template-columns:220px minmax(0,1fr)}}
.rail{display:none}
@media (min-width:1180px){.rail{display:block;position:sticky;top:calc(env(safe-area-inset-top,0px) + 24px);align-self:start;max-height:calc(100vh - 48px);overflow:auto;font-size:13.5px;line-height:1.35;padding-top:8px}}
.rail .rt{font-family:var(--display);letter-spacing:.06em;text-transform:uppercase;color:var(--faint);font-size:12px;margin-bottom:10px}
.rail a{display:block;color:var(--muted);text-decoration:none;padding:5px 0 5px 12px;border-left:2px solid var(--line)}
.rail a:hover{color:var(--ink)}
.rail a.on{color:var(--blue);border-left-color:var(--blue);font-weight:700}
main{min-width:0}
.prose>*{max-width:740px;margin-inline:auto}
.prose>.fig,.prose>.results,.prose>.explorer,.prose>.tbl-wrap,.prose>.term,.prose>.code{max-width:1060px}
h1{font-family:var(--display);font-weight:400;font-size:clamp(34px,5.2vw,58px);line-height:1.04;margin:18px auto 8px;text-wrap:balance;letter-spacing:.005em}
h2{font-family:var(--display);font-weight:400;font-size:clamp(26px,3.2vw,36px);line-height:1.1;margin:76px auto 14px;text-wrap:balance;scroll-margin-top:24px}
h3{font-family:var(--display);font-weight:400;font-size:22px;margin:32px auto 8px}
p{margin:14px auto}
a{color:var(--blue);text-underline-offset:3px}
a:focus-visible,button:focus-visible{outline:3px solid var(--blue);outline-offset:2px;border-radius:6px}
code{font-family:var(--mono);font-size:.84em;background:var(--wash);border:1px solid var(--line);border-radius:6px;padding:1px 6px;white-space:nowrap}
strong{font-weight:800}
.subtitle{font-family:var(--display);color:var(--muted);font-size:clamp(19px,2.2vw,24px);line-height:1.25;margin:4px auto 18px}
.tagline{color:var(--muted);font-style:italic;text-align:center;font-size:15px;margin-top:-6px}
.lede{border:0;margin:26px auto;padding:0 0 0 22px;border-left:5px solid var(--purple);font-family:var(--display);font-size:clamp(21px,2.5vw,27px);line-height:1.3;color:var(--ink)}
.lede p{margin:0}
.facts{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}
.facts span{font-family:var(--display);font-size:13px;letter-spacing:.05em;text-transform:uppercase;padding:5px 12px;border-radius:999px;border:1.5px solid var(--line);background:var(--surface);color:var(--muted)}
.fig{margin:30px auto 34px}
.fig .paper{position:relative;background:var(--paper);border:1.5px solid var(--line);border-radius:18px;overflow:hidden;box-shadow:0 1px 0 rgba(23,43,77,.04),0 12px 32px -18px rgba(23,43,77,.25)}
.fig img{display:block;width:100%;height:auto}
.fig.cover .paper{border:0;border-radius:20px;background:#121212}
.fig figcaption{text-align:center;color:var(--muted);font-size:15px;margin-top:10px;font-style:italic}
.zoom{position:absolute;right:12px;bottom:12px;display:inline-flex;gap:6px;align-items:center;font:700 13px var(--sans);color:#172B4D;background:rgba(255,255,255,.92);border:1.5px solid #D5DEEA;border-radius:999px;padding:5px 11px;cursor:pointer;opacity:.85}
.zoom:hover{opacity:1}
.zoom svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:2.2;stroke-linecap:round}
dialog{border:0;padding:0;max-width:96vw;max-height:94vh;border-radius:14px;background:#fff}
dialog::backdrop{background:rgba(8,14,25,.72)}
dialog .dz{overflow:auto;max-height:94vh}
dialog img{display:block;width:1600px;max-width:none;height:auto}
dialog button{position:sticky;top:10px;float:right;margin:10px;font:700 14px var(--sans);border-radius:999px;border:1.5px solid #D5DEEA;background:#fff;color:#172B4D;padding:6px 14px;cursor:pointer}
ul,ol{padding-left:24px}
li{margin:5px 0}
li>ul{margin:4px 0}
.tbl-wrap{overflow-x:auto;margin:22px auto;border:1.5px solid var(--line);border-radius:14px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:15.5px;line-height:1.45}
th,td{text-align:left;vertical-align:top;padding:10px 14px;border-bottom:1px solid var(--line)}
th{font-family:var(--display);font-weight:400;font-size:13px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);background:var(--wash);white-space:nowrap}
tr:last-child td{border-bottom:0}
td code{white-space:normal}
.heat td:first-child{font-weight:700}
.hc{text-align:center;font-variant-numeric:tabular-nums;font-family:var(--mono);font-weight:700}
.hc span{display:inline-block;min-width:58px;padding:4px 10px;border-radius:8px}
.hc.full span{background:var(--green-t);color:var(--green);border:1.5px solid var(--green-s)}
.hc.part span{background:var(--orange-t);color:var(--orange);border:1.5px solid var(--orange-s)}
.hc.none span{background:var(--red-t);color:var(--red);border:1.5px solid var(--red-s)}
.term,.code{margin:22px auto;border-radius:14px;overflow:hidden;background:var(--code-bg);border:1px solid #1E2B44}
.code-bar{display:flex;gap:7px;align-items:center;padding:10px 14px;background:rgba(255,255,255,.04);border-bottom:1px solid rgba(255,255,255,.06)}
.code-bar span{width:11px;height:11px;border-radius:50%;background:#FF5F57}
.code-bar span:nth-child(2){background:#FEBC2E}.code-bar span:nth-child(3){background:#28C840}
.code-bar em{margin-left:auto;font:600 12px var(--mono);font-style:normal;color:#8494AA;text-transform:lowercase}
pre{margin:0;padding:16px 20px;overflow-x:auto}
pre code{background:none;border:0;padding:0;color:var(--code-ink);font-size:14px;line-height:1.6;white-space:pre}
.term .cmd{color:#8BE9B4}
.kicker{font-family:var(--display);font-size:14px;letter-spacing:.08em;text-transform:uppercase;color:var(--blue);margin:76px auto 0}
.kicker+h2{margin-top:4px}
.eyebrow{font-family:var(--display);font-size:14px;letter-spacing:.07em;text-transform:uppercase;color:var(--blue)}
.results{margin:34px auto 10px}
.r-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 16px;align-items:baseline;margin-bottom:10px}
.r-note{font-size:13px;color:var(--faint)}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
@media (max-width:900px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:520px){.tiles{grid-template-columns:1fr}}
.tile{background:var(--surface);border:1.5px solid var(--line);border-radius:14px;padding:14px 16px;border-top:4px solid var(--c)}
.t-red{--c:var(--red-s)}.t-orange{--c:var(--orange-s)}.t-purple{--c:var(--purple)}.t-teal{--c:var(--teal-s)}.t-blue{--c:var(--blue)}.t-gray{--c:var(--gray)}.t-dark{--c:var(--dark)}
.t-title{font-weight:800;font-size:14.5px;line-height:1.3;min-height:38px}
.t-pair{display:flex;align-items:center;gap:10px;margin-top:8px}
.t-pair>div{display:grid}
.t-pair b{font-family:var(--display);font-weight:400;font-size:30px;line-height:1.05;font-variant-numeric:tabular-nums}
.t-pair>div:last-child b{color:var(--c)}
.t-pair span{font-size:12px;color:var(--muted);line-height:1.2}
.t-pair i{color:var(--faint);font-style:normal;font-size:20px}
.explorer{margin:10px auto 30px;background:var(--surface);border:1.5px solid var(--line);border-radius:18px;padding:18px}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 14px}
.lt{display:inline-flex;align-items:center;gap:8px;font:800 14px var(--sans);color:var(--ink);background:var(--wash);border:1.5px solid var(--line);border-radius:999px;padding:6px 14px 6px 6px;cursor:pointer}
.lt .ln{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--c);color:#fff;font:400 13px var(--display)}
.lt[aria-selected="true"]{border-color:var(--c);background:var(--surface);box-shadow:0 0 0 3px color-mix(in srgb,var(--c) 18%,transparent)}
.lp{border-left:5px solid var(--c);padding:4px 0 4px 18px}
.lp-q{font-family:var(--display);font-size:22px;line-height:1.2;margin-bottom:10px}
.lp-grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:18px}
@media (max-width:720px){.lp-grid{grid-template-columns:1fr}}
.lp-k{font-family:var(--display);font-size:12.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--c);margin-top:6px}
.lp-k.no{color:var(--red)}
.lp ul{margin:6px 0;padding-left:20px;font-size:16px}
.lp p{margin:4px 0 8px;font-size:16px}
.lp-not{display:inline-block;border:1.5px dashed var(--red-s);color:var(--red);border-radius:8px;padding:2px 10px;font-weight:700}
.chip,.exp{display:inline-block;font:700 12.5px var(--mono);border:1.5px solid var(--line);border-radius:999px;padding:2px 9px;margin-right:6px;background:var(--wash);color:var(--muted)}
.exp{border-color:var(--c);color:var(--c);background:transparent}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:13px;color:var(--faint);margin-bottom:6px}
.topbar b{font-family:var(--display);font-weight:400;letter-spacing:.06em;text-transform:uppercase;color:var(--purple)}
.theme{font:700 13px var(--sans);border:1.5px solid var(--line);background:var(--surface);color:var(--muted);border-radius:999px;padding:4px 12px;cursor:pointer}
footer{max-width:740px;margin:60px auto 0;color:var(--faint);font-size:14px;border-top:1px solid var(--line);padding-top:16px}
@media (prefers-reduced-motion:no-preference){.fig .paper{transition:transform .2s ease}.fig:not(.cover) .paper:hover{transform:translateY(-2px)}}
@page{margin:4mm 0}@media print{.rail,.zoom,.theme,.explorer{display:none}.shell{display:block;padding-inline:14mm}html,body{background:#fff;height:auto}.fig,.results,.tbl-wrap,.term,.code,blockquote,tr{break-inside:avoid}h2,h3,.kicker{break-after:avoid}.fig img{max-height:235mm;width:auto;max-width:100%;margin-inline:auto;display:block}pre,pre code{white-space:pre-wrap;overflow-wrap:anywhere;overflow:visible}.tbl-wrap{overflow:visible}h2{padding-top:6mm}.kicker{padding-top:6mm}.kicker+h2{padding-top:0}}
"""

JS = r"""
(function(){
  const imgs=[...document.querySelectorAll('.fig img')];
  const dlg=document.getElementById('zoom');
  document.querySelectorAll('.zoom').forEach(b=>b.addEventListener('click',()=>{
    const i=imgs[+b.dataset.fig]; dlg.querySelector('img').src=i.src; dlg.querySelector('img').alt=i.alt; dlg.showModal();}));
  dlg.querySelector('button').addEventListener('click',()=>dlg.close());
  dlg.addEventListener('click',e=>{if(e.target===dlg)dlg.close();});
  document.querySelectorAll('.tabs').forEach(list=>{
    const tabs=[...list.querySelectorAll('[role=tab]')];
    const pick=t=>{tabs.forEach(x=>{const on=x===t;x.setAttribute('aria-selected',on);x.tabIndex=on?0:-1;
      document.getElementById(x.getAttribute('aria-controls')).hidden=!on;});};
    tabs.forEach((t,k)=>{t.tabIndex=k?-1:0;t.addEventListener('click',()=>pick(t));
      t.addEventListener('keydown',e=>{const last=tabs.length-1;
        const to=e.key==='ArrowRight'?(k+1)%tabs.length:e.key==='ArrowLeft'?(k+last)%tabs.length:e.key==='Home'?0:e.key==='End'?last:-1;
        if(to<0)return; e.preventDefault(); pick(tabs[to]); tabs[to].focus();});});
  });
  const links=[...document.querySelectorAll('.rail a')];
  if('IntersectionObserver' in window&&links.length){
    const map=new Map(links.map(a=>[a.getAttribute('href').slice(1),a]));
    const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){links.forEach(a=>a.classList.remove('on'));const a=map.get(e.target.id);if(a)a.classList.add('on');}});},{rootMargin:'0px 0px -70% 0px'});
    document.querySelectorAll('h2[id]').forEach(h=>io.observe(h));
  }
  // Figures load lazily for a fast first screen. Load them all soon after, and before printing: a page printed from a
  // viewer frame keeps only the figures that were scrolled into view.
  const eager=()=>imgs.forEach(i=>{if(i.loading==='lazy')i.loading='eager';});
  window.addEventListener('beforeprint',eager);
  if(document.readyState==='complete')setTimeout(eager,1200);else window.addEventListener('load',()=>setTimeout(eager,1200));
  const tb=document.querySelector('.theme');
  if(tb){const r=document.documentElement, mq=matchMedia('(prefers-color-scheme: dark)');
    const dark=()=>r.dataset.theme?r.dataset.theme==='dark':mq.matches;
    const label=()=>{tb.textContent=dark()?'Light mode':'Dark mode';};
    label(); mq.addEventListener('change',label);
    tb.addEventListener('click',()=>{r.dataset.theme=dark()?'light':'dark';label();});}
})();
"""


TITLE = "Your Agent Remembers Everything. That's a Problem."
SHORT_TITLE = "Memory Is Not Truth"  # the artifact gallery wants a short name
DESCRIPTION = ("Memory, context and state for production agents: provenance, scope, expiry and authority. A preregistered POC "
               "compares naive vector memory with governed memory under injected stale, expired, wrong-scope, conflicting and poisoned records.")


def head(bare: bool, canonical: str | None, og_image: str | None) -> str:
    q = lambda v: html.escape(v, quote=True)  # noqa: E731
    lines = []
    if not bare:
        lines += ['<meta charset="utf-8">', '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">']
    lines += [f"<title>{q(SHORT_TITLE if bare else TITLE)}</title>", f'<meta name="description" content="{q(DESCRIPTION)}">']
    if not bare:
        lines += ['<meta property="og:type" content="article">', f'<meta property="og:title" content="{q(TITLE)}">',
                  f'<meta property="og:description" content="{q(DESCRIPTION)}">',
                  f'<meta name="twitter:card" content="{"summary_large_image" if og_image else "summary"}">',
                  f'<meta name="twitter:title" content="{q(TITLE)}">', f'<meta name="twitter:description" content="{q(DESCRIPTION)}">']
        if canonical:
            lines += [f'<link rel="canonical" href="{q(canonical)}">', f'<meta property="og:url" content="{q(canonical)}">']
        if og_image:
            lines += [f'<meta property="og:image" content="{q(og_image)}">', f'<meta name="twitter:image" content="{q(og_image)}">']
    lines += ['<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
              '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Lilita+One&family=Nunito:ital,wght@0,400;0,600;0,700;0,800;1,400&family=JetBrains+Mono:wght@400;600;700&display=swap">',
              f"<style>{CSS}</style>"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--run-id", default=__import__("fill_article").ARTICLE_RUN)
    ap.add_argument("--no-strip", action="store_true", help="no results strip (technical edition)")
    ap.add_argument("--bare", action="store_true", help="no doctype/html/head/body; short title (for the artifact host)")
    ap.add_argument("--external-assets", action="store_true", help="write figures to <dst dir>/assets/ instead of inlining them")
    ap.add_argument("--canonical", help="final public URL of the article (canonical and og:url)")
    ap.add_argument("--og-image", help="absolute URL of the social preview image (og:image, twitter:image)")
    a = ap.parse_args()
    dst = Path(a.dst)
    if a.external_assets:
        ASSETS["dir"] = dst.parent / "assets"
    src = Path(a.src)
    title, body, toc = convert(src.read_text(encoding="utf-8"), src.parent)
    numbers = json.loads((HERE / "article" / "article-numbers.flat.json").read_text())
    if numbers["run_id"] != a.run_id:
        raise SystemExit(f"article numbers are from {numbers['run_id']}, not {a.run_id}")
    # subtitle: the first tagline after the H1 becomes the subtitle
    body = body.replace('<p class="tagline">', '<p class="subtitle">', 1)
    # results strip at the measured-in-the-poc marker (after the opening failure), else after the facts line
    if not a.no_strip and "<!--RESULTS-->" in body:
        body = body.replace("<!--RESULTS-->", results_strip(numbers, a.run_id), 1)
    elif not a.no_strip:
        body = re.sub(r'(<p class="facts">.*?</p>)', lambda m: m.group(1) + results_strip(numbers, a.run_id), body, count=1, flags=re.S)
    rail = "".join(f'<a href="#{s}">{html.escape(t)}</a>' for s, t in toc if t != "References")
    page = f"""<div class="shell">
<nav class="rail" aria-label="Contents"><div class="rt">Contents</div>{rail}</nav>
<main>
<div class="topbar prose"><b>Production AI engineering · S1 · State &amp; Knowledge</b><button class="theme" type="button">Dark mode</button></div>
<article class="prose">
<h1>{inline(title)}</h1>
{body}
</article>
<footer>Figures are native Excalidraw drawings from the S1 diagram generator. Every number comes from one recorded run
(<code>runs/{a.run_id}/</code>, frozen digest <code>{numbers["frozen_digest"]}</code>); the tenants, runbooks and incidents are simulated.</footer>
</main>
</div>
<dialog id="zoom" aria-label="Figure"><div class="dz"><button type="button">Close</button><img alt=""></div></dialog>
<script>{JS}</script>"""
    hd = head(a.bare, a.canonical, a.og_image)
    doc = f"{hd}\n{page}\n" if a.bare else f'<!doctype html>\n<html lang="en">\n<head>\n{hd}\n</head>\n<body>\n{page}\n</body>\n</html>\n'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(doc, encoding="utf-8")
    extra = f", figures in {ASSETS['dir']}" if ASSETS["dir"] else ""
    print(f"wrote {dst}: {len(doc) // 1024} KB, {len(toc)} sections{extra}")


if __name__ == "__main__":
    main()
