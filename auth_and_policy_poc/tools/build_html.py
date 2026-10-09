"""Build the standalone HTML edition of T2 from the Markdown source.

    uv run --no-project --with markdown python tools/build_html.py            # full edition
    uv run --no-project --with markdown python tools/build_html.py medium     # Medium edition

Everything is embedded: fonts (base64 woff2), figures (inline SVG from assets/svg, PNG fallback), CSS and a few lines
of JS (reading progress, copy buttons, back to top). No network access is needed to read or print the page.
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = {
    "full": (ROOT / "authorization-and-policy-for-ai-agents.md", ROOT / "authorization-and-policy-for-ai-agents.html",
             "Full edition"),
    "medium": (ROOT / "medium" / "authorization-and-policy-for-ai-agents-medium.md",
               ROOT / "medium" / "authorization-and-policy-for-ai-agents-medium.html", "Medium edition"),
}
FONTS = ROOT / "assets" / "fonts"

DECISIONS = {
    "ALLOW": "allow", "ALLOW_WITH_CONSTRAINTS": "constrained", "ALLOW_WITH_APPROVAL": "approval",
    "REQUIRE_APPROVAL": "approval", "CONDITIONAL": "approval", "DENY": "deny", "YES": "allow", "NO": "deny",
}


def font_face(family: str, file: str, weight: str = "400", style: str = "normal") -> str:
    data = base64.b64encode((FONTS / file).read_bytes()).decode()
    return (f"@font-face{{font-family:'{family}';src:url(data:font/woff2;base64,{data}) format('woff2');"
            f"font-weight:{weight};font-style:{style};font-display:swap}}")


# -- code highlighting ----------------------------------------------------------------------------------------------
TOKEN = re.compile(
    r'(?P<str>"(?:[^"\\]|\\.)*")'
    r"|(?P<com>(?:#|//)[^\n]*)"
    r"|(?P<dec>\b(?:ALLOW_WITH_CONSTRAINTS|ALLOW_WITH_APPROVAL|REQUIRE_APPROVAL|CONDITIONAL|ALLOW|DENY|YES|NO)\b)"
    r"|(?P<kw>\b(?:def|return|if|else|for|in|not|and|or|raise|import|from|class|permit|forbid|when|package|default|contains|some|true|false|None)\b)"
    r"|(?P<num>\b\d+(?:\.\d+)?\b)"
)


def highlight(code: str, lang: str) -> str:
    comment_ok = lang not in ("json", "text", "")
    out, pos = [], 0
    for m in TOKEN.finditer(code):
        kind = m.lastgroup
        if kind == "com" and (not comment_ok or (m.group().startswith("#") and lang == "cedar")):
            continue
        if kind == "kw" and lang in ("text", "json", ""):
            continue
        out.append(html.escape(code[pos:m.start()], quote=False))
        tok = html.escape(m.group(), quote=False)
        if kind == "str":
            after = code[m.end():m.end() + 2]
            cls = "k" if after.lstrip().startswith(":") and lang == "json" else "s"
            out.append(f'<span class="tk-{cls}">{tok}</span>')
        elif kind == "dec":
            out.append(f'<span class="tk-dec d-{DECISIONS[m.group()]}">{tok}</span>')
        else:
            out.append(f'<span class="tk-{kind}">{tok}</span>')
        pos = m.end()
    out.append(html.escape(code[pos:], quote=False))
    text = "".join(out)
    if lang == "toml":  # keys and table headers
        text = re.sub(r"(?m)^(\s*)(\[\[?[\w.\-\"]+\]\]?)", r'\1<span class="tk-h">\2</span>', text)
        text = re.sub(r"(?m)^(\s*)([\w.\-]+)(\s*=)", r'\1<span class="tk-k">\2</span>\3', text)
    return text


def code_blocks(body: str) -> str:
    def repl(m: re.Match) -> str:
        lang = m.group(1) or ""
        code = html.unescape(m.group(2))
        label = {"text": "", "": ""}.get(lang, lang)
        head = f'<span class="code-lang">{label}</span>' if label else ""
        return (f'<div class="code">{head}<button class="copy" type="button" aria-label="Copy code">Copy</button>'
                f'<pre><code class="language-{lang or "text"}">{highlight(code, lang)}</code></pre></div>')
    return re.sub(r'<pre><code(?: class="language-([\w-]+)")?>(.*?)</code></pre>', repl, body, flags=re.S)


# -- figures --------------------------------------------------------------------------------------------------------
def svg_for(png_rel: str, alt: str) -> str:
    name = Path(png_rel).stem
    svg = ROOT / "assets" / "svg" / f"{name}.svg"
    if svg.exists():
        s = svg.read_text()
        s = re.sub(r"<\?xml.*?\?>", "", s).strip()
        s = re.sub(r"<svg\b", f'<svg aria-label="{html.escape(alt)}" preserveAspectRatio="xMidYMid meet"', s, count=1)
        s = re.sub(r'(<svg\b[^>]*?)\s(width|height)="[^"]*"', r"\1", s, count=1)
        s = re.sub(r'(<svg\b[^>]*?)\s(width|height)="[^"]*"', r"\1", s, count=1)
        return s
    png = ROOT / png_rel
    if png.exists():
        data = base64.b64encode(png.read_bytes()).decode()
        return f'<img alt="{html.escape(alt)}" src="data:image/png;base64,{data}">'
    return f'<div class="fig-missing">{html.escape(alt)}</div>'


def figures(body: str) -> str:
    pat = re.compile(r'<p><img alt="([^"]*)" src="(?:\.\./)?(assets/png/[^"]+)"\s*/?></p>\s*(?:<p><em>(Figure[^<]*?)</em></p>)?', re.S)

    def repl(m: re.Match) -> str:
        alt, src, cap = html.unescape(m.group(1)), m.group(2), m.group(3)
        if "cover" in Path(src).stem:
            return f'<figure class="fig cover">{svg_for(src, alt)}</figure>'
        num = re.match(r"Figure (\d+)", cap or "")
        fid = f' id="figure-{num.group(1)}"' if num else ""
        caption = ""
        if cap:
            head, _, rest = cap.partition(". ")
            caption = f"<figcaption><b>{head}.</b> {rest}</figcaption>"
        return f'<figure class="fig"{fid}><div class="fig-frame">{svg_for(src, alt)}</div>{caption}</figure>'
    return pat.sub(repl, body)


# -- page -----------------------------------------------------------------------------------------------------------
def build(edition: str = "full") -> None:
    SRC, OUT, label = EDITIONS[edition]
    text = SRC.read_text()
    title = re.search(r"^# (.+)$", text, re.M).group(1).strip()
    text = text.replace(f"# {title}\n", "", 1)
    subtitle_m = re.search(r"^\*(.+?)\*\s*$", text, re.M)
    subtitle = subtitle_m.group(1)
    text = text.replace(subtitle_m.group(0), "", 1)

    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "toc"],
                           extension_configs={"toc": {"permalink": "#", "permalink_class": "anchor", "toc_depth": "2-3"}})
    body = md.convert(text)
    toc = [(t["id"], t["name"]) for t in md.toc_tokens]

    body = figures(body)
    body = code_blocks(body)
    body = re.sub(r"<table>", '<div class="table-wrap"><table>', body)
    body = body.replace("</table>", "</table></div>")
    body = re.sub(r"<strong>(ALLOW_WITH_CONSTRAINTS|ALLOW_WITH_APPROVAL|ALLOW|DENY)</strong>",
                  lambda m: f'<span class="chip d-{DECISIONS[m.group(1)]}">{m.group(1)}</span>', body)
    body = body.replace("<blockquote>", '<blockquote class="callout">')
    # the series line right under the cover
    body = re.sub(r"<p>(Production AI Engineering · .*?)</p>", r'<p class="series-line">\1</p>', body, count=1)
    body = body.replace("<hr />", '<hr class="rule">')

    prose = re.sub(r'<div class="code">.*?</div>\s*(?=<|$)|<pre>.*?</pre>|<figure.*?</figure>', " ", body, flags=re.S)
    words = len(re.sub(r"<[^>]+>", " ", prose).split())
    minutes = round(words / 238)

    toc_html = "".join(f'<li><a href="#{i}">{html.escape(html.unescape(n))}</a></li>' for i, n in toc)
    series = [("F1", "MCP Tool Sprawl", ""), ("F2", "Layered Architecture", ""), ("F3", "Headless AI", ""),
              ("T1", "Agent Identity", ""), ("T2", "Authorization &amp; Policy", "current"), ("T3", "Human-in-the-Loop", "next")]
    series_html = "".join(f'<li class="{c}"><b>{k}</b> {n}</li>' for k, n, c in series)

    fonts = "".join([
        font_face("Cascadia", "CascadiaCode-Regular.woff2"),
        font_face("Lilita One", "LilitaOne-Regular.woff2"),
        font_face("Nunito", "Nunito-Variable-latin.woff2", "200 1000"),
        font_face("Source Serif 4", "SourceSerif4-normal-latin.woff2", "400 700"),
        font_face("Source Serif 4", "SourceSerif4-italic-latin.woff2", "400 700", "italic"),
    ])

    page = TEMPLATE.format(title=html.escape(title), subtitle=subtitle, body=body, toc=toc_html, series=series_html,
                           minutes=minutes, label=label, fonts=fonts, css=CSS, js=JS,
                           description=html.escape(re.sub(r"\*", "", subtitle)))
    OUT.write_text(page)
    print(f"wrote {OUT.name}: {OUT.stat().st_size / 1024:.0f} KiB, {words} words, ~{minutes} min read, "
          f"{body.count('<figure')} figures, {body.count('<svg')} inline svgs")


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="color-scheme" content="light dark">
<style>{fonts}</style>
<style>{css}</style>
</head>
<body>
<div class="progress" aria-hidden="true"><span></span></div>
<nav class="toc" aria-label="Contents"><p class="toc-title">Contents</p><ol>{toc}</ol></nav>
<main class="article">
<header class="hero">
  <p class="kicker"><span class="kicker-rule"></span>Production AI Engineering · T2 · Authorization &amp; Policy</p>
  <h1>{title}</h1>
  <p class="subtitle">{subtitle}</p>
  <div class="meta"><span>Part 5 of the Production AI Engineering series</span><span>·</span><span>{label}</span><span>·</span><span>{minutes} min read</span><span>·</span><span>POC run 2026-09-29-recorded</span></div>
  <ol class="series">{series}</ol>
</header>
{body}
</main>
<a class="to-top" href="#" aria-label="Back to top">↑</a>
<script>{js}</script>
</body>
</html>
"""

CSS = r"""
:root{
  --bg:#ffffff; --ink:#1f2430; --ink-2:#3b4252; --muted:#6b7280; --line:#e6e8ee; --wash:#f7f8fb; --code-bg:#f6f7fb;
  --violet:#6D5BD0; --violet-t:#F1EEFF; --indigo:#4551C9; --blue:#2F6FDE; --teal:#0E8A9A;
  --green:#1F9D74; --green-t:#E6F6EF; --orange:#D97706; --orange-t:#FFF4E0; --red:#D14D63; --red-t:#FFEEF1;
  --serif:'Source Serif 4', Charter, Georgia, 'Times New Roman', serif;
  --sans:Nunito, 'Helvetica Neue', Helvetica, Arial, sans-serif;
  --display:'Lilita One', Nunito, sans-serif;
  --mono:Cascadia, 'SF Mono', Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#12151c; --ink:#e7e9ee; --ink-2:#c9ced8; --muted:#9aa3b2; --line:#2a303c; --wash:#191d26; --code-bg:#171b24;
  --violet-t:#241f45; --green-t:#12302a; --orange-t:#33260f; --red-t:#3a1b22;
}}
:root[data-theme="dark"]{
  --bg:#12151c; --ink:#e7e9ee; --ink-2:#c9ced8; --muted:#9aa3b2; --line:#2a303c; --wash:#191d26; --code-bg:#171b24;
  --violet-t:#241f45; --green-t:#12302a; --orange-t:#33260f; --red-t:#3a1b22;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--serif);font-size:20px;line-height:1.72;
  font-feature-settings:"kern","liga";text-rendering:optimizeLegibility}
.article{max-width:728px;margin:0 auto;padding:56px 24px 120px}
.progress{position:fixed;top:0;left:0;right:0;height:3px;z-index:20}
.progress span{display:block;height:100%;width:0;background:var(--violet)}

/* hero */
.hero{margin-bottom:28px}
.kicker{font-family:var(--mono);font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--violet);
  display:flex;align-items:center;gap:12px;margin:0 0 18px}
.kicker-rule{display:inline-block;width:32px;height:2px;background:var(--violet)}
h1{font-family:var(--sans);font-weight:900;font-size:50px;line-height:1.08;letter-spacing:-.02em;margin:0 0 18px}
.subtitle{font-family:var(--serif);font-size:23px;line-height:1.5;color:var(--ink-2);margin:0 0 22px}
.meta{font-family:var(--sans);font-size:14px;color:var(--muted);display:flex;flex-wrap:wrap;gap:8px}
.series{list-style:none;padding:0;margin:22px 0 0;display:flex;flex-wrap:wrap;gap:8px;font-family:var(--sans);font-size:13px}
.series li{border:1px solid var(--line);border-radius:999px;padding:4px 12px;color:var(--muted)}
.series li b{font-family:var(--display);font-weight:400;margin-right:4px}
.series li.current{border-color:var(--violet);background:var(--violet-t);color:var(--ink)}
.series li.current b{color:var(--violet)}
.series li.next{border-style:dashed}
.series-line{font-family:var(--sans);font-size:14px;color:var(--muted);text-align:center;margin-top:-6px}

/* text */
h2{font-family:var(--sans);font-weight:850;font-size:32px;line-height:1.22;letter-spacing:-.01em;margin:64px 0 14px;scroll-margin-top:24px}
h3{font-family:var(--sans);font-weight:800;font-size:23px;line-height:1.3;margin:40px 0 8px;scroll-margin-top:24px}
p{margin:0 0 24px}
a{color:var(--violet);text-decoration-thickness:1px;text-underline-offset:3px}
h2 .anchor,h3 .anchor{opacity:0;margin-left:8px;color:var(--muted);text-decoration:none;font-weight:400}
h2:hover .anchor,h3:hover .anchor{opacity:1}
strong{font-weight:700}
ul,ol{padding-left:28px;margin:0 0 24px}
li{margin:6px 0}
li::marker{color:var(--violet)}
code{font-variant-ligatures:none;font-feature-settings:'calt' 0,'liga' 0;font-family:var(--mono);font-size:.8em;background:var(--code-bg);border:1px solid var(--line);border-radius:5px;padding:.08em .35em}
hr.rule{border:0;height:1px;background:var(--line);margin:48px 0}

/* callouts */
blockquote.callout{margin:32px 0;padding:18px 22px 18px 24px;border-left:4px solid var(--violet);background:var(--violet-t);
  border-radius:0 12px 12px 0;font-family:var(--sans);font-size:21px;line-height:1.5;color:var(--ink)}
blockquote.callout p{margin:0}
blockquote.callout p + p{margin-top:12px}
blockquote.callout strong{font-weight:800}

/* chips */
.chip{display:inline-block;font-family:var(--mono);font-size:.68em;font-weight:400;letter-spacing:.02em;border-radius:999px;
  padding:.18em .7em;border:1.5px solid;white-space:nowrap;vertical-align:.1em}
.chip.d-allow{color:var(--green);background:var(--green-t);border-color:var(--green)}
.chip.d-constrained{color:var(--green);background:var(--green-t);border-color:var(--green);border-style:dashed}
.chip.d-approval{color:var(--orange);background:var(--orange-t);border-color:var(--orange)}
.chip.d-deny{color:var(--red);background:var(--red-t);border-color:var(--red)}

/* code */
.code{position:relative;margin:28px 0 30px}
.code pre{font-variant-ligatures:none;font-feature-settings:'calt' 0,'liga' 0;margin:0;background:var(--code-bg);border:1px solid var(--line);border-radius:12px;padding:18px 20px;overflow-x:auto;
  font-family:var(--mono);font-size:14.5px;line-height:1.6;color:var(--ink)}
.code pre code{background:none;border:0;padding:0;font-size:inherit}
.code-lang{position:absolute;top:-10px;left:16px;font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.06em;
  background:var(--bg);color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:1px 9px}
.copy{position:absolute;top:8px;right:8px;font-family:var(--sans);font-size:12px;border:1px solid var(--line);background:var(--bg);
  color:var(--muted);border-radius:8px;padding:3px 9px;cursor:pointer;opacity:0;transition:opacity .15s}
.code:hover .copy,.copy:focus{opacity:1}
.tk-s{color:#1b7f5f}.tk-k{color:#4551C9}.tk-com{color:#8a93a6;font-style:italic}.tk-kw{color:#6D5BD0}.tk-num{color:#b45309}.tk-h{color:#0E8A9A}
.tk-dec{font-weight:400;border-radius:4px;padding:0 3px}
.tk-dec.d-allow,.tk-dec.d-constrained{color:var(--green);background:var(--green-t)}
.tk-dec.d-approval{color:var(--orange);background:var(--orange-t)}
.tk-dec.d-deny{color:var(--red);background:var(--red-t)}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]) .tk-s{color:#6fd3ad} :root:not([data-theme="light"]) .tk-k{color:#9aa4ff}
  :root:not([data-theme="light"]) .tk-kw{color:#b3a8ff} :root:not([data-theme="light"]) .tk-num{color:#f0b35a} }

/* tables */
.table-wrap{overflow-x:auto;margin:28px -24px 32px;padding:0 24px}
table{border-collapse:collapse;width:100%;font-family:var(--sans);font-size:15.5px;line-height:1.5}
th{text-align:left;font-weight:800;color:var(--ink);border-bottom:2px solid var(--ink);padding:9px 12px 9px 0;vertical-align:bottom}
td{border-bottom:1px solid var(--line);padding:10px 12px 10px 0;vertical-align:top;color:var(--ink-2)}
td code,th code{font-size:.82em}
tr:last-child td{border-bottom:0}

/* figures */
.fig{margin:40px -120px 44px}
.fig .fig-frame{border-radius:16px;overflow:hidden;background:#fff}
.fig svg,.fig img{display:block;width:100%;height:auto}
.fig figcaption{font-family:var(--sans);font-size:15px;line-height:1.5;color:var(--muted);text-align:center;max-width:728px;margin:14px auto 0;padding:0 24px}
.fig figcaption b{color:var(--ink-2)}
.fig.cover{margin:8px -120px 20px}
.fig-missing{padding:40px;border:2px dashed var(--line);font-family:var(--sans);font-size:14px;color:var(--muted)}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]) .fig .fig-frame{box-shadow:0 0 0 1px var(--line)} }

/* contents rail */
.toc{position:fixed;top:96px;left:max(16px, calc(50% - 364px - 300px));width:230px;max-height:calc(100vh - 140px);overflow:auto;
  font-family:var(--sans);font-size:13.5px;line-height:1.4;display:none}
.toc-title{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 10px}
.toc ol{list-style:none;padding:0;margin:0;border-left:1px solid var(--line)}
.toc li{margin:0}
.toc a{display:block;padding:5px 0 5px 14px;color:var(--muted);text-decoration:none;border-left:2px solid transparent;margin-left:-1px}
.toc a:hover{color:var(--ink)}
.toc a.active{color:var(--violet);border-left-color:var(--violet);font-weight:700}
@media (min-width:1360px){.toc{display:block}}
.to-top{position:fixed;right:20px;bottom:20px;width:40px;height:40px;border-radius:50%;background:var(--bg);border:1px solid var(--line);
  color:var(--muted);display:grid;place-items:center;text-decoration:none;font-family:var(--sans);opacity:0;transition:opacity .2s}
.to-top.show{opacity:1}

@media (max-width:1000px){ .fig,.fig.cover{margin-left:-24px;margin-right:-24px} .fig .fig-frame{border-radius:0} }
@media (max-width:640px){
  body{font-size:18px}
  .article{padding:32px 16px 80px}
  h1{font-size:36px} h2{font-size:26px} h3{font-size:20px} .subtitle{font-size:19px}
  blockquote.callout{font-size:18px}
  .table-wrap{margin-left:-16px;margin-right:-16px;padding:0 16px}
  .fig,.fig.cover{margin-left:-16px;margin-right:-16px}
  .fig .fig-frame{overflow-x:auto} .fig .fig-frame svg{min-width:720px}
}

/* print / PDF */
@page{size:A4;margin:16mm 15mm 18mm}
@media print{
  :root{--bg:#fff;--ink:#1f2430;--ink-2:#3b4252;--muted:#6b7280;--line:#e2e5ec;--wash:#f7f8fb;--code-bg:#f6f7fb;
    --violet-t:#F1EEFF;--green-t:#E6F6EF;--orange-t:#FFF4E0;--red-t:#FFEEF1}
  body{font-size:10.6pt;line-height:1.55;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .progress,.toc,.to-top,.copy,.anchor{display:none!important}
  .article{max-width:none;padding:0}
  h1{font-size:30pt} h2{font-size:18pt;margin-top:26pt;break-after:avoid} h3{font-size:13pt;break-after:avoid}
  .subtitle{font-size:13pt}
  p,li{orphans:3;widows:3}
  .fig,.fig.cover{margin:14pt 0 16pt;break-inside:avoid}
  .fig figcaption{font-size:9pt}
  .code-lang{top:8px;left:auto;right:12px;border:0;background:transparent;padding:0}
  .code{break-inside:avoid} .code pre{white-space:pre-wrap;word-break:break-word;font-size:8.2pt;overflow:visible}
  .table-wrap{margin:14pt 0;padding:0;overflow:visible} table{font-size:8.6pt} tr{break-inside:avoid}
  blockquote.callout{font-size:11.5pt;break-inside:avoid}
  a{color:inherit;text-decoration:none}
  .hero{break-after:avoid}
}
"""

JS = r"""
(function(){
  var bar=document.querySelector('.progress span'), top=document.querySelector('.to-top');
  var links=[].slice.call(document.querySelectorAll('.toc a'));
  var heads=links.map(function(a){return document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1)));});
  function onScroll(){
    var h=document.documentElement, max=h.scrollHeight-h.clientHeight;
    bar.style.width=(max>0?(h.scrollTop/max*100):0)+'%';
    top.classList.toggle('show', h.scrollTop>900);
    var cur=-1; heads.forEach(function(el,i){ if(el && el.getBoundingClientRect().top<120) cur=i; });
    links.forEach(function(a,i){ a.classList.toggle('active', i===cur); });
  }
  document.addEventListener('scroll', onScroll, {passive:true}); onScroll();
  [].forEach.call(document.querySelectorAll('.copy'), function(b){
    b.addEventListener('click', function(){
      var t=b.parentNode.querySelector('pre').innerText;
      try{ navigator.clipboard.writeText(t).then(function(){ b.textContent='Copied'; setTimeout(function(){b.textContent='Copy';},1400); }); }catch(e){}
    });
  });
})();
"""

if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else "full")
