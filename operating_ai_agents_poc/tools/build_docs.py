"""Build the two O1 + O2 publications (Medium edition, technical deep dive) and the evidence documents as Markdown,
standalone HTML and PDF.

    uv run --project ops_poc --with markdown --with pypdf python tools/build_docs.py [medium|technical|evidence|report]

Ported unchanged in mechanism from R1 + R2 (evals_obs_reliability/tools/build_docs.py); only the paths, series navigation,
legend and evidence links are this note's.

Ported from F3's tools/build_docs.py, which was ported from F2's (same directives, same evidence-kit reading template, same Chrome print), with
the reader features this note needs: a reading-progress bar, heading deep links, copy-code buttons, light syntax
highlighting, citation links with hover titles, series navigation, and a back-to-top control.

Source: docs/source/<track>.src.md, or docs/source/<track>/*.md concatenated in name order.  Every measured number is a
{{key}} token resolved from the published run's facts.json (ops_poc/runs/<PUBLISHED>/facts.json).  An unknown
key is a build failure; every use is recorded in docs/evidence-uses.json.

Directives (one line each)
    ::: figure t06 | Caption | Alt text        a figure (diagrams/premium/svg/t06.svg), numbered, with provenance
    ::: kind SIMULATED+IMPLEMENTED | basis     the evidence class of a section
    ::: claim Text                             a pull quote
Blocks
    :::: callout kicker | href | link label    a short aside
Citations
    [[12]]                                     -> a link to reference [12] (HTML) or "[12]" (Markdown)

Outputs: medium/operating-ai-agents-medium.{md,html,pdf}, technical/operating-ai-agents-technical.{md,html,pdf} and
results/operating-ai-agents-{evidence,report}.{md,html,pdf}.

Ported from T4 (ai_control_plane/tools/build_docs.py); the proof card is a recorded decision explained by `agentops explain`.

T4 adds (kept here):
    ::: proof E10-canary [| collapsed]         a recorded decision explained, verbatim from docs/explain/E10-canary.txt (agentops explain)
    ::: figure id | Caption | Alt | wide       options after the alt text: small, wide (the Medium hero)
    ::: eyebrow Text                           a small uppercase label announcing the next block
    ::: legend                                 the figures' colour grammar and provenance badges
    ::: evidencebar                            links to the Lab Console, Evidence Check, Real vs simulated, technical edition
Every figure caption starts with the figure's provenance badges (diagrams/manifest.json, drawn on the figure too).
"""

from __future__ import annotations

import html
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT.parent
POC = ROOT / "ops_poc"
sys.path.insert(0, str(ROOT / "vendor"))
from evidence_kit import __version__ as KIT, medium, medium_js, skin_css  # noqa: E402
from evidence_kit.components import md as inline_md  # noqa: E402


def _kit5_publication():
    """The series' local-path check (evidence-kit 5.2.0, vendor/kit5), loaded by file: `evidence_kit` here is the pinned
    3.6.0 reading template, and publication.py is standalone (stdlib only)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("kit5_publication", ROOT / "vendor" / "kit5" / "evidence_kit" / "publication.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.local_path_findings


local_path_findings = _kit5_publication()

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TRACKS = {"medium": "Medium edition", "technical": "Technical deep dive"}
# Evidence documents: built from the same run and the same pipeline, published under results/.
RESULTS = {"evidence": "Evidence Check", "report": "Run report"}
ALL = {**TRACKS, **RESULTS}
SLUG = "operating-ai-agents"
TOKEN = re.compile(r"\{\{([A-Za-z0-9_.@\-]+)\}\}")
DIRECTIVE = re.compile(r"^::: (\w+)(?: (.*))?$", re.M)
BLOCK = re.compile(r"^:::: (\w+)(?: ([^\n]*))?\n(.*?)\n::::$", re.M | re.S)
CITE = re.compile(r"\[\[(\d+)\]\]")
CITEKEY = re.compile(r"\[\[@([\w-]+)\]\]")
KIND = {"MEASURED": "Measured", "RECORDED": "Recorded", "REASONED": "Reasoned", "ARCHITECTURE": "Architecture", "SIMULATED": "Simulated",
        "IMPLEMENTED": "Implemented", "DERIVED": "Derived", "SOURCED": "Sourced", "SYNTHESIS": "Our synthesis", "LIMITATION": "Limitation"}
medium.KINDS.update(KIND)

# Series navigation: real local paths only.  A missing target is a build failure, never a broken link.
SERIES = [
    ("Foundation", "F1 · MCP Tool Sprawl", "Your AI agent has 500 MCP tools. Now what?", "tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html"),
    ("Foundation", "F2 · Layered Architecture", "Your agent works in a demo. Why does it break in production?",
     "f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html"),
    ("Foundation", "F3 · Headless AI", "Your AI shouldn't live inside the UI", "headless_ai/medium/headless-ai-medium.html"),
    ("Trust", "T2 · Authorization & Policy", "What is this agent actually allowed to do?", "auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html"),
    ("Trust", "T3 · Human-in-the-Loop", "Authorized. Should it still act?", "human_in_the_loop/medium/human-in-the-loop-medium.html"),
    ("Trust", "T5 · Observability & Governance", "Your AI agent did something in production. Can you explain exactly what happened?",
     "governance_for_ai_agents/medium/observability-governance-medium.html"),
    ("Trust", "T4 · AI Control Plane", "Your agents shouldn't govern themselves", "ai_control_plane/medium/ai-control-plane-medium.html"),
    ("State", "S1 · Memory, Context & State", "Your agent remembers everything. That's a problem.", "memory_context_state/article/memory-context-state.html"),
    ("Trust", "T1 · Agent Identity", "Who is acting, and on whose authority?", "agent_identity/medium/agent-identity-medium.html"),
    ("Trust", "T6 · Agent, Tool & MCP Security", "Assume the context is hostile.", "securing_tools_mcp/medium/securing-agents-tools-mcp-medium.html"),
    ("Reliability", "R1 + R2 · Evals, Observability & Reliability", "“The agent failed” is not an operational signal.", "evals_obs_reliability/medium/evals-reliability-medium.html"),
    ("Capstone", "P1 · The Agent Is Not the Architecture", "The final reference architecture", "ai_architecture/medium/production-agentic-ai-platform-medium.html"),
    ("Coordination", "C1 · Do You Actually Need Multiple Agents?", "When does one agent become several, and when is that just more complexity?",
     "multi_agent_a2a/medium/multi-agent-a2a-medium.html"),
    ("Current", "O1 + O2 · Operating AI Agents at Scale", "Cost, latency, scale & lifecycle.", None),
]
START_HERE = "series-start-here/start-here/production-ai-engineering.html"
# The evidence bar under the Medium edition's core proof (paths relative to medium/ and technical/).
EVIDENCE_LINKS = [("Evidence Check", "Claim → checks → run", "../results/operating-ai-agents-evidence.html"),
                  ("Run report", "Every scenario, every arm", "../results/operating-ai-agents-report.html"),
                  ("POC README", "Run it yourself", "../ops_poc/README.md"),
                  ("Technical deep dive", "The full architecture", "../technical/operating-ai-agents-technical.html")]


def published_run() -> Path:
    return POC / "runs" / (POC / "runs" / "PUBLISHED").read_text().strip()


def load_facts() -> dict:
    """The run's facts.json, plus docs/derived-facts.json if it exists: both computed from the run, never typed."""
    facts = json.loads((published_run() / "facts.json").read_text())
    dp = ROOT / "docs" / "derived-facts.json"
    derived = json.loads(dp.read_text()) if dp.exists() else {}
    clash = set(facts) & set(derived)
    if clash:
        raise SystemExit(f"fact defined twice: {sorted(clash)}")
    return {**facts, **derived}


def fmt(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:,.1f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v):,}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def render_facts(src: str, facts: dict, doc: str, uses: dict) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in facts:
            raise SystemExit(f"{doc}: unknown fact {{{{{key}}}}}")
        uses.setdefault(key, {"value": facts[key]["value"], "source": facts[key]["source"], "used_in": []})
        if doc not in uses[key]["used_in"]:
            uses[key]["used_in"].append(doc)
        return fmt(facts[key]["value"])
    out = TOKEN.sub(sub, src)
    if "{{" in out or "TBD" in out or "FILL:" in out:
        raise SystemExit(f"{doc}: unresolved placeholder left in the source")
    return out


def cite_keys(src: str, doc: str) -> str:
    """[[@rfc8693]] -> [[1]], from research/cite-keys.json; an unknown key is a build failure."""
    keys = json.loads((ROOT / "research" / "cite-keys.json").read_text())

    def sub(m: re.Match) -> str:
        if m.group(1) not in keys:
            raise SystemExit(f"{doc}: unknown citation key [[@{m.group(1)}]]")
        return f"[[{keys[m.group(1)]}]]"
    return CITEKEY.sub(sub, src)


def front_matter(src: str) -> tuple[dict, str]:
    meta = {}
    m = re.match(r"^---\n(.*?)\n---\n", src, re.S)
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        src = src[m.end():]
    return meta, src


def own_fonts(svg: str, key: str) -> str:
    """Each inline SVG embeds its own font subsets under shared family names; rename them per figure so they don't collide."""
    for fam in set(re.findall(r'@font-face \{ font-family: "?([^";]+)"?;', svg)):
        svg = re.sub(rf'(@font-face \{{ font-family: )"?{re.escape(fam)}"?;', lambda m: f'{m.group(1)}"{fam} {key}";', svg)
        svg = svg.replace(f'font-family="{fam}, ', f'font-family="{fam} {key}, ')
    return svg


def proof_cards() -> dict[str, str]:
    """Recorded decisions explained, keyed E10-canary ..., verbatim from docs/explain/*.txt (written by `agentops explain --write`)."""
    return {p.stem: p.read_text().rstrip() for p in sorted((ROOT / "docs" / "explain").glob("*.txt"))}


def figure_manifest() -> dict:
    return json.loads((ROOT / "diagrams" / "manifest.json").read_text())["figures"]


def references() -> dict[str, str]:
    """[n] -> title, from research/sources.md, for citation hover titles."""
    out = {}
    for m in re.finditer(r"^\*\*\[(\d+)\]\*\* (.+?) — ", (ROOT / "research" / "sources.md").read_text(), re.M):
        out[m.group(1)] = m.group(2)
    return out


# ---- light syntax highlighting (server side, so the PDF gets it too) ------------------------------------------------
HL_RULES = {
    "json": [(r'"(?:[^"\\]|\\.)*"(?=\s*:)', "k"), (r'"(?:[^"\\]|\\.)*"', "s"), (r"\b(?:true|false|null)\b", "c"), (r"-?\b\d+(?:\.\d+)?\b", "n")],
    "python": [(r"#[^\n]*", "m"), (r'"""[\s\S]*?"""|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', "s"),
               (r"\b(?:def|class|return|if|elif|else|for|while|in|not|and|or|is|None|True|False|import|from|as|with|try|except|raise|yield|lambda|async|await|pass)\b", "c"),
               (r"\b\d+(?:\.\d+)?\b", "n")],
    "yaml": [(r"#[^\n]*", "m"), (r"^\s*-?\s*[\w.\-]+(?=:)", "k"), (r'"(?:[^"\\]|\\.)*"', "s"), (r"\b(?:true|false|null)\b", "c"), (r"\b\d+(?:\.\d+)?\b", "n")],
    "http": [(r"^(?:GET|POST|PUT|PATCH|DELETE)\b", "c"), (r"^[\w-]+(?=:)", "k"), (r"HTTP/\d(?:\.\d)?\s+\d+", "n")],
    "bash": [(r"#[^\n]*", "m"), (r"^\s*(?:uv|make|python3?|cd|curl)\b", "c"), (r'"(?:[^"\\]|\\.)*"', "s")],
}


def highlight(lang: str, code: str) -> str:
    rules = HL_RULES.get(lang)
    if not rules:
        return code
    text = html.unescape(code)
    rx = re.compile("|".join(f"(?P<g{i}>{p})" for i, (p, _) in enumerate(rules)), re.M)
    out, pos = [], 0
    for m in rx.finditer(text):
        out.append(html.escape(text[pos:m.start()], quote=False))
        cls = rules[int(m.lastgroup[1:])][1]
        out.append(f'<span class="hl-{cls}">{html.escape(m.group(0), quote=False)}</span>')
        pos = m.end()
    out.append(html.escape(text[pos:], quote=False))
    return "".join(out)


EXTRA_CSS = """
@media print{.m-body .table-wrap.wide{overflow:visible}.m-body .table-wrap.wide table{font-size:7.4pt;width:100%;table-layout:auto}
  .m-body .table-wrap.wide th,.m-body .table-wrap.wide td{padding:3px 4px;word-break:normal;overflow-wrap:anywhere}
  .m-body .table-wrap.wide code{font-size:6.8pt}}
.fig svg{cursor:zoom-in;width:100%;height:auto}
.zoom{position:fixed;inset:0;background:rgba(15,23,42,.86);display:none;z-index:9999;overflow:auto;padding:24px}
.zoom.on{display:block}.zoom .zin{background:#fff;border-radius:12px;padding:12px;margin:0 auto;max-width:min(2400px,96vw)}
.zoom svg{width:100%;height:auto;cursor:zoom-out}.zoom .zx{position:fixed;top:14px;right:22px;color:#fff;font:600 15px/1 sans-serif;cursor:pointer;background:none;border:0}
.hai-progress{position:fixed;top:0;left:0;height:3px;width:0;background:#6D5BD0;z-index:10000}
.m-body h2,.m-body h3{position:relative;scroll-margin-top:72px}
.hai-anchor{margin-left:.35em;font:500 .7em/1 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#8494AA;text-decoration:none;opacity:0;border:0;background:none;cursor:pointer;padding:2px 4px}
.m-body h2:hover .hai-anchor,.m-body h3:hover .hai-anchor,.hai-anchor:focus-visible{opacity:1}
.hai-code{position:relative}.hai-copy{position:absolute;top:8px;right:8px;font:600 12px/1 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;
  padding:6px 9px;border-radius:7px;border:1px solid #D5DCE6;background:#fff;color:#334155;cursor:pointer}
.hai-copy:hover{background:#F1F5F9}
pre code .hl-k{color:#1D5FB8}pre code .hl-s{color:#0B7A6B}pre code .hl-n{color:#B45309}pre code .hl-c{color:#7C3AED}pre code .hl-m{color:#64748B;font-style:italic}
.hai-cite{font-size:.72em;vertical-align:super;line-height:0;text-decoration:none;padding:0 1px}
.hai-ref{scroll-margin-top:72px}.hai-ref:target{background:#FFF7E0;border-radius:6px}
.hai-series{margin:48px 0 0;font-family:sohne,'Helvetica Neue',Helvetica,Arial,sans-serif}
.hai-series h2{font-size:15px;letter-spacing:.08em;text-transform:uppercase;color:#6B6B6B;margin:0 0 12px}
.hai-series ol{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.hai-series li{margin:0;border:1px solid #E3E8EF;border-radius:12px;padding:12px 14px;background:#fff}
.hai-series li.cur{border:2px solid #6D5BD0;background:#FAF8FF}.hai-series li.plan{border-style:dashed}
.hai-series .r{display:block;font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:#6B6B6B;margin-bottom:4px}
.hai-series b{display:block;font-size:15.5px}.hai-series span.q{display:block;font-size:14px;color:#52637A;margin-top:3px}
.hai-series a{color:inherit}
.hai-top{position:fixed;right:18px;bottom:18px;z-index:50;border:1px solid #D5DCE6;background:#fff;border-radius:999px;padding:10px 14px;
  font:600 13px/1 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#172B4D;cursor:pointer;opacity:0;pointer-events:none;transition:opacity .2s}
.hai-top.on{opacity:1;pointer-events:auto}
a:focus-visible,button:focus-visible,summary:focus-visible{outline:3px solid #0E8A9A;outline-offset:2px;border-radius:4px}
.m-body pre{overflow-x:auto;max-width:100%}.m-body .table-wrap{overflow-x:auto}
.fig{max-width:100%}.m-body img{max-width:100%;height:auto}
.m-body figure.proof{margin:28px 0}.m-body figure.proof pre,.m-body figure.proof pre code{font-size:12px!important;line-height:1.4!important}.m-body figure.proof pre{white-space:pre;overflow-x:auto;background:#0F172A;color:#E2E8F0;border-radius:12px;padding:16px 18px}
.m-body figure.proof pre code{color:inherit;background:none}.m-body figure.proof figcaption{font-size:13px;color:#6B6B6B;margin-top:8px}
.fig-scroll{max-width:100%}
@media (min-width:729px){.m-body figure.fig.fig-sm{width:min(640px, calc(100vw - var(--navw) - 48px))}}
@media (max-width:640px){.hai-series ol{grid-template-columns:1fr}.hai-copy{padding:5px 7px}
  .fig-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:10px}.fig-scroll svg{min-width:720px}
  .fig figcaption::before{content:"Scroll sideways or tap the figure to enlarge. ";display:block;font-size:12px;color:#8494AA;margin-bottom:4px}}
@media (min-width:729px){.m-body figure.fig.fig-wide{width:min(1240px, calc(100vw - var(--navw) - 48px))}}
.hai-badge{display:inline-block;font:600 10.5px/1 ui-monospace,'SF Mono',Menlo,monospace;letter-spacing:.06em;padding:4px 7px;border-radius:6px;border:1px solid;margin:0 6px 0 0;vertical-align:1px}
.hai-badge.ARCHITECTURE{color:#334155;border-color:#334155;background:#EEF1F5}.hai-badge.MEASURED{color:#1F9D74;border-color:#1F9D74;background:#E6F6EF}
.hai-badge.SIMULATED{color:#5B6B82;border-color:#5B6B82;background:#EDF0F4}.hai-badge.QUALIFIED{color:#A16207;border-color:#A16207;background:#FEF6D8}
.hai-badge.NEGATIVE{color:#D14D63;border-color:#D14D63;background:#FFEEF1}
.hai-eyebrow{margin:2.4em 0 -1.4em!important;font:700 12.5px/1.2 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif!important;letter-spacing:.14em;text-transform:uppercase;color:#6D5BD0;text-align:center}
.hai-legend{margin:2em 0 0;padding:14px 16px;border:1px solid #E3E8EF;border-radius:12px;background:#FBFCFD;font:400 14px/1.5 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#2E3A4F}
.hai-legend b.h{display:block;font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;color:#6B6B6B;margin:0 0 8px}
.hai-legend ul{list-style:none;margin:0 0 10px;padding:0;display:flex;flex-wrap:wrap;gap:6px 16px}.hai-legend li{margin:0;padding:0;font-size:14px}
.hai-legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.hai-evbar{margin:2.2em 0 0;border:1px solid #D2CAF5;border-radius:14px;background:#FAF8FF;padding:14px 16px;font-family:sohne,'Helvetica Neue',Helvetica,Arial,sans-serif}
.hai-evbar b.h{display:block;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#6D5BD0;margin:0 0 10px}
.hai-evbar ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.hai-evbar li{margin:0;padding:0}.hai-evbar a{display:block;border:1px solid #E3E8EF;border-radius:10px;background:#fff;padding:10px 12px;text-decoration:none;color:#172B4D;height:100%}
.hai-evbar a b{display:block;font-size:13px;line-height:1.3;letter-spacing:.04em;text-transform:uppercase}.hai-evbar a span{display:block;font-size:13.5px;line-height:1.35;color:#52637A;margin-top:4px}
.hai-evbar a:hover{border-color:#6D5BD0}
details.hai-details{margin:1.6em 0 0;border:1px solid #E3E8EF;border-radius:12px;padding:10px 14px;background:#fff}
details.hai-details summary{cursor:pointer;font:600 14.5px/1.4 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#172B4D}
details.hai-details figure.proof{margin:12px 0 4px}
@media (max-width:728px){.hai-evbar ul{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
@media print{.m-body figure.fig.fig-wide{width:auto!important}.hai-evbar,.hai-legend,details.hai-details{break-inside:avoid}.hai-evbar ul{grid-template-columns:repeat(4,minmax(0,1fr))}
  .m-body figure.fig.fig-sm{width:62%!important;margin-left:auto;margin-right:auto}.zoom,.hai-progress,.hai-top,.hai-copy,.hai-anchor{display:none!important}.fig{break-inside:avoid}.fig svg{max-height:228mm}
  .m-body h2,.m-body h3{break-after:avoid}pre,table,.m-callout,blockquote{break-inside:avoid}.hai-series{break-inside:avoid}
  a.hai-cite{color:inherit}.m-body pre{white-space:pre-wrap;overflow-wrap:anywhere}
  .m-body figure.proof pre,.m-body figure.proof pre code{white-space:pre!important;overflow-wrap:normal!important;font-size:7.4pt!important;break-inside:avoid}}
"""

EXTRA_JS = """
(function(){
if(/[?&]print=1/.test(location.search)){document.querySelectorAll('details').forEach(function(d){d.open=true;});}
window.addEventListener('beforeprint',function(){document.querySelectorAll('details').forEach(function(d){d.open=true;});});
var bar=document.createElement('div');bar.className='hai-progress';bar.setAttribute('aria-hidden','true');document.body.appendChild(bar);
var top=document.createElement('button');top.className='hai-top';top.type='button';top.textContent='\\u2191 Top';top.setAttribute('aria-label','Back to top');
document.body.appendChild(top);top.addEventListener('click',function(){window.scrollTo(0,0);});
function onScroll(){var h=document.documentElement;var max=h.scrollHeight-h.clientHeight;bar.style.width=(max>0?(h.scrollTop/max*100):0)+'%';
top.classList.toggle('on',h.scrollTop>1400);}
window.addEventListener('scroll',onScroll,{passive:true});onScroll();
function copy(text,btn,done){function ok(){var o=btn.textContent;btn.textContent=done;setTimeout(function(){btn.textContent=o;},1400);}
try{navigator.clipboard.writeText(text).then(ok,function(){fallback();});}catch(e){fallback();}
function fallback(){var t=document.createElement('textarea');t.value=text;t.style.position='fixed';t.style.opacity='0';document.body.appendChild(t);t.select();
try{document.execCommand('copy');ok();}catch(e){}document.body.removeChild(t);}}
document.querySelectorAll('.m-body pre').forEach(function(pre){var w=document.createElement('div');w.className='hai-code';pre.parentNode.insertBefore(w,pre);w.appendChild(pre);
var b=document.createElement('button');b.type='button';b.className='hai-copy';b.textContent='Copy';b.setAttribute('aria-label','Copy code to clipboard');w.appendChild(b);
b.addEventListener('click',function(){copy(pre.innerText,b,'Copied');});});
document.querySelectorAll('.m-body h2[id], .m-body h3[id]').forEach(function(h){var b=document.createElement('button');b.type='button';b.className='hai-anchor';
b.textContent='#';b.setAttribute('aria-label','Copy link to section: '+h.textContent);h.appendChild(b);
b.addEventListener('click',function(){history.replaceState(null,'','#'+h.id);copy(location.href,b,'\\u2713');});});
var z=document.createElement('div');z.className='zoom';z.setAttribute('role','dialog');z.setAttribute('aria-label','Enlarged figure');
z.innerHTML='<button class="zx" type="button">close \\u2715</button><div class="zin"></div>';document.body.appendChild(z);
function off(){z.classList.remove('on');z.querySelector('.zin').innerHTML='';}
z.addEventListener('click',off);document.addEventListener('keydown',function(e){if(e.key==='Escape')off();});
document.querySelectorAll('.fig svg').forEach(function(s){s.setAttribute('tabindex','0');
function open(){var c=s.cloneNode(true);z.querySelector('.zin').appendChild(c);z.classList.add('on');}
s.addEventListener('click',open);s.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});});
})();
"""


class Doc:
    def __init__(self, track: str, facts: dict, uses: dict):
        self.track = track
        single = ROOT / "docs" / "source" / f"{track}.src.md"
        parts = sorted((ROOT / "docs" / "source" / track).glob("*.md")) if (ROOT / "docs" / "source" / track).is_dir() else []
        raw = "\n\n".join(p.read_text().strip() for p in parts) + "\n" if parts else single.read_text()
        if track == "medium":   # the Medium edition lists only the numbered sources its body cites (same numbers as the technical edition)
            keys = json.loads((ROOT / "research" / "cite-keys.json").read_text())
            cited = {str(keys[k]) for k in CITEKEY.findall(raw) if k in keys} | set(CITE.findall(raw))
            refs = (ROOT / "docs" / "source" / "technical" / "99-references.md").read_text().replace("## References", "## Sources", 1)
            refs = "\n".join(l for l in refs.splitlines() if not l.startswith("**[") or re.match(r"\*\*\[(\d+)\]\*\*", l).group(1) in cited)
            raw = raw.rstrip() + "\n\n" + refs
        self.cards = proof_cards()
        self.out = ROOT / (track if track in TRACKS else "results") / f"{SLUG}-{track}"
        self.meta, src = front_matter(raw)
        self.src = cite_keys(render_facts(src, facts, track, uses), track)
        self.meta = {k: render_facts(v, facts, track, uses) for k, v in self.meta.items()}
        self.figs = figure_manifest()
        self.refs = references()
        self.blocks: list[str] = []
        self.nfig = 0

    def others(self) -> list[tuple[str, str]]:
        """(label, path without extension) of the companion documents, relative to this document's folder."""
        eds = [(TRACKS[t], f"../{t}/{SLUG}-{t}") for t in TRACKS if t != self.track]
        ev = [] if self.track == "evidence" else [(RESULTS["evidence"], f"../results/{SLUG}-evidence")]
        return eds + ev

    # ---- Markdown edition --------------------------------------------------------------------------------------------
    def markdown(self) -> str:
        n = 0

        def fig(m: re.Match) -> str:
            nonlocal n
            kind, arg = m.group(1), (m.group(2) or "").strip()
            if kind == "figure":
                n += 1
                fid, cap, alt = [p.strip() for p in arg.split(" | ")][:3]
                badges = " ".join(f"`{b}`" for b in self.figs[fid].get("badges", []))
                return f"![{alt}](../diagrams/premium/png/{fid}.png)\n\n{badges} *Figure {n}. {cap}* · {self.figs[fid]['provenance']}"
            if kind == "kind":
                kinds, _, text = arg.partition(" | ")
                return f"*{' · '.join(KIND.get(k, k.title()) for k in kinds.split('+'))}: {text}*"
            if kind == "claim":
                return f"> **{arg}**"
            if kind == "eyebrow":
                return f"**{arg.upper()}**"
            if kind == "legend":
                return ("*How to read the figures.* Slate: requests, demand, operations · orange: orchestration and the runtime loop · "
                        "indigo: the agent and its models (probabilistic) · magenta: context and retrieval · teal: tools and downstream APIs · "
                        "blue: deterministic controls (admission, bounds, gates) · purple: the control plane, releases and the change loop · "
                        "navy: evidence · grey: enterprise systems (simulated) · red: the naive arm, a breach, a rollback · green: the controlled arm, held, promoted. "
                        "Badges: `ARCHITECTURE` conceptual design · `MEASURED` a recorded POC result (simulation units) · `RECORDED` one recorded decision.")
            if kind == "evidencebar":
                return ("**Want to inspect the evidence?** " + " · ".join(f"[{t}]({h.replace('.html', '.md') if 'console' not in h else h}) ({d})" for t, d, h in EVIDENCE_LINKS))
            if kind == "proof":
                arg = arg.split(" | ")[0].strip()
                return (f"```text\n{self.cards[arg]}\n```\n\n*{arg.replace('-', ' · ')} in run `{published_run().name}`, "
                        f"as `agentops explain {arg}` prints it from the recorded files.*")
            return m.group(0)

        def blk(m: re.Match) -> str:
            head, href, label = ([x.strip() for x in (m.group(2) or "").split(" | ")] + ["", "", ""])[:3]
            body = "\n".join(f"> {l}" for l in m.group(3).strip().splitlines())
            link = f"\n>\n> [{label}]({href})" if href else ""
            return f"> **{head}**\n>\n{body}{link}"

        src = BLOCK.sub(blk, self.src)
        src = DIRECTIVE.sub(fig, src)
        src = CITE.sub(lambda m: f"[{m.group(1)}]", src)
        cover = f"![{self.meta.get('cover_alt', '')}](../diagrams/premium/png/{self.meta['cover']}.png)\n\n" if self.meta.get("cover") else ""
        head = (f"# {self.meta.get('title', '')}\n\n*{self.meta.get('subtitle', '')}*\n\n{cover}"
                f"{self.meta.get('kicker', '')} · {ALL[self.track]} · {self.meta.get('filed', '')}\n\n")
        others = " · ".join(f"[{l}]({h}.md)" for l, h in self.others())
        series = " · ".join(f"[{n}](../../{pth})" for _, n, _, pth in SERIES if pth)
        tail = (f"\n\n---\n\n**Series.** {series} · Current: O1 + O2 · Operating AI Agents at Scale. "
                f"Companions: {others}. Every measured number is substituted from "
                f"`ops_poc/runs/{published_run().name}/facts.json`.\n")
        return head + src.strip() + tail

    # ---- HTML edition ------------------------------------------------------------------------------------------------
    def figure(self, arg: str, cover: bool = False) -> str:
        parts = [p.strip() for p in arg.split(" | ")]
        fid, cap, alt = parts[:3]
        opts = set(parts[3:])
        svg = (ROOT / "diagrams" / "premium" / "svg" / f"{fid}.svg").read_text()
        svg = own_fonts(re.sub(r"<\?xml[^>]*>", "", svg).strip(), f"{self.track}{fid}")
        svg = svg.replace("<svg ", f'<svg role="img" aria-label="{html.escape(alt, quote=True)}" ', 1)
        if cover:
            return svg
        self.nfig += 1
        prov = self.figs[fid]["provenance"]
        badges = "".join(f'<span class="hai-badge {b.split()[0]}">{b}</span>' for b in self.figs[fid].get("badges", []))
        cls = "".join(f" fig-{o}" for o in ("small", "wide") if o in opts).replace("fig-small", "fig-sm")
        return (f'<figure class="fig{cls}" id="fig-{fid}"><div class="fig-scroll">{svg}</div><figcaption>{badges}Figure {self.nfig}. {inline_md(cap)}'
                f'<span class="src">{html.escape(prov)}</span></figcaption></figure>')

    def directive(self, m: re.Match) -> str:
        kind, arg = m.group(1), (m.group(2) or "").strip()
        if kind == "figure":
            out = self.figure(arg)
        elif kind == "kind":
            kinds, _, text = arg.partition(" | ")
            out = medium.kind(kinds.split("+"), text)
        elif kind == "claim":
            out = f'<div class="m-pull">{medium.claim(arg)}</div>'
        elif kind == "proof":
            code, _, opt = arg.partition(" | ")
            code = code.strip()
            if code not in self.cards:
                raise SystemExit(f"{self.track}: no explained run {code} in docs/explain/")
            out = (f'<figure class="proof" id="proof-{code}"><pre><code class="language-text">{html.escape(self.cards[code])}</code></pre>'
                   f'<figcaption>{code.replace("-", " · ")} in run <code>{published_run().name}</code>, as <code>agentops explain {code}</code> prints it '
                   f'from the recorded files.</figcaption></figure>')
            if opt.strip() == "collapsed":
                out = f'<details class="hai-details"><summary>The recorded run, explained ({code})</summary>{out}</details>'
        elif kind == "eyebrow":
            out = f'<p class="hai-eyebrow">{html.escape(arg)}</p>'
        elif kind == "legend":
            sw = [("#334155", "requests, demand, operations"), ("#D97706", "orchestration, the runtime loop"),
                  ("#4551C9", "the agent and its models: probabilistic"), ("#B5487F", "context and retrieval"), ("#0E8A9A", "tools and downstream APIs"),
                  ("#2F6FDE", "deterministic controls: admission, bounds, gates"), ("#6D5BD0", "control plane, releases, the change loop"),
                  ("#172B4D", "evidence"), ("#5B6B82", "enterprise systems (simulated)"), ("#D14D63", "the naive arm, a breach, a rollback"),
                  ("#1F9D74", "the controlled arm, held, promoted")]
            bd = [("ARCHITECTURE", "conceptual design"), ("MEASURED", "a recorded POC result, in simulation units"), ("RECORDED", "one recorded decision")]
            out = ('<aside class="hai-legend" aria-label="How to read the figures"><b class="h">How to read the figures</b><ul>'
                   + "".join(f'<li><i style="background:{c}"></i>{html.escape(t)}</li>' for c, t in sw) + '</ul><ul>'
                   + "".join(f'<li><span class="hai-badge {b.split()[0]}">{b}</span>{html.escape(t)}</li>' for b, t in bd) + '</ul></aside>')
        elif kind == "evidencebar":
            out = ('<nav class="hai-evbar" aria-label="Inspect the evidence"><b class="h">Want to inspect the evidence?</b><ul>'
                   + "".join(f'<li><a href="{h}"><b>{html.escape(t)}</b><span>{html.escape(d)}</span></a></li>' for t, d, h in EVIDENCE_LINKS)
                   + '</ul></nav>')
        else:
            raise SystemExit(f"{self.track}: unknown directive ::: {kind}")
        self.blocks.append(out)
        return f"\n\n@@BLOCK{len(self.blocks) - 1}@@\n\n"

    def block(self, m: re.Match) -> str:
        kind, arg, body = m.group(1), (m.group(2) or "").strip(), m.group(3)
        parts = ([x.strip() for x in arg.split(" | ")] + ["", "", ""])[:3]
        if kind != "callout":
            raise SystemExit(f"{self.track}: unknown block :::: {kind}")
        self.blocks.append(medium.callout(parts[0], body, href=parts[1] or None, link=parts[2] or "Details"))
        return f"\n\n@@BLOCK{len(self.blocks) - 1}@@\n\n"

    def body_html(self) -> str:
        src = BLOCK.sub(self.block, self.src)
        src = DIRECTIVE.sub(self.directive, src)
        body = markdown.markdown(src, extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"])
        body = re.sub(r'<code class="language-(\w+)">(.*?)</code>', lambda m: f'<code class="language-{m.group(1)}">{highlight(m.group(1), m.group(2))}</code>',
                      body, flags=re.S)
        body = re.sub(r"<table>.*?</table>", lambda m: f'<div class="table-wrap{" wide" if m.group(0).count("<th") >= 6 else ""}">{m.group(0)}</div>',
                      body, flags=re.S)
        body = re.sub(r"<p><strong>\[(\d+)\]</strong>", lambda m: f'<p class="hai-ref" id="ref-{m.group(1)}"><strong>[{m.group(1)}]</strong>', body)
        body = re.sub(r'(<a href="https?://[^"]+")', r'\1 rel="noopener"', body)
        for i, b in enumerate(self.blocks):
            ph = f"<p>@@BLOCK{i}@@</p>"
            if body.count(ph) != 1:
                raise SystemExit(f"{self.track}: block {i} did not survive markdown")
            body = body.replace(ph, b)
        return CITE.sub(lambda m: (f'<a class="hai-cite" href="#ref-{m.group(1)}" title="{html.escape(self.refs.get(m.group(1), ""), quote=True)}">'
                                   f'[{m.group(1)}]</a>'), body)

    def nav(self, body: str) -> str:
        items, cur = [], None
        for level, hid, text in re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>', body):
            label = html.unescape(re.sub(r"<[^>]+>", "", text))
            if level == "2":
                cur = [hid, label, []]
                items.append(cur)
            elif cur is not None and self.track == "medium":
                cur[2].append((hid, label))
        li = "".join(f'<li><a href="#{h}">{html.escape(t)}</a>'
                     + (f'<ol>{"".join(f"<li><a href=#{s}>{html.escape(u)}</a></li>" for s, u in subs)}</ol>' if subs else "")
                     + "</li>" for h, t, subs in items)
        return (f'<nav class="m-nav" id="m-nav" aria-label="Sections"><div class="m-nav-h">In this article</div><ol>{li}</ol></nav>'
                '<div class="m-scrim"></div>')

    def series(self) -> str:
        lis = []
        for role, name, q, path in SERIES:
            if path:
                target = WS / path
                if not target.exists():
                    raise SystemExit(f"series link target missing: {path}")
                inner = f'<a href="../../{path}"><b>{html.escape(name)}</b></a>'
            else:
                inner = f"<b>{html.escape(name)}</b>"
            cls = "cur" if role == "Current" else ("plan" if role == "Next" and not path else "")
            lis.append(f'<li class="{cls}"{" aria-current=page" if role == "Current" else ""}><span class="r">{role}</span>{inner}<span class="q">{html.escape(q)}</span></li>')
        if not (WS / START_HERE).exists():
            raise SystemExit("start-here page missing")
        return (f'<nav class="hai-series" aria-labelledby="series-h"><h2 id="series-h">Production AI Engineering · the series so far</h2><ol>{"".join(lis)}</ol>'
                f'<p style="font-size:14px;margin-top:10px"><a href="../../{START_HERE}">The full learning map (Start Here)</a></p></nav>')

    def html(self) -> str:
        meta = self.meta
        body = self.body_html()
        # reading time: what a reader sees by default, so a collapsed block (the P2 proof card) is not counted
        words = len(re.sub(r"<details.*?</details>|<svg.*?</svg>|<[^>]+>", " ", body, flags=re.S).split())
        mins = max(1, math.ceil((words / 265 * 60 + sum(max(12 - i, 3) for i in range(self.nfig))) / 60))
        by = meta.get("byline", "")
        kicker = meta.get("kicker", "")
        others = self.others()
        other_links = "".join(f'<a href="{h}.html">{html.escape(l)}</a>' for l, h in others)
        poc = "../ops_poc/README.md"
        top = ('<header class="m-top"><a class="pub" href="#top">Production AI Engineering</a><nav aria-label="Edition">'
               '<button type="button" class="m-toc-btn" aria-expanded="false" aria-controls="m-nav">Contents</button>'
               f'{other_links.replace("<a ", '<a class="opt" ', 1)}<a href="{poc}">POC</a><a href="../../{START_HERE}">Start Here</a></nav></header>')
        byline = (f'<span class="m-avatar" aria-hidden="true">O</span><div><b>{html.escape(by)}</b>'
                  f'{mins} min read · Published {html.escape(meta.get("filed", ""))} · {ALL[self.track]}</div>')
        cover = ""
        if meta.get("cover"):
            art = self.figure(f"{meta['cover']} | cover | {meta.get('cover_alt', meta.get('title', ''))}", cover=True)
            cover = (f'<section class="m-cover" aria-label="Cover"><div class="m-cover-in"><div class="m-cover-top"><span>{html.escape(kicker)}</span>'
                     f'<span>{html.escape(ALL[self.track])}</span></div><h1>{html.escape(meta.get("title", ""))}</h1>'
                     f'<p class="m-cover-sub">{html.escape(meta.get("subtitle", ""))}</p><div class="m-cover-by">{byline}</div>'
                     f'<figure class="m-cover-art">{art}</figure>'
                     + (f'<p class="m-cover-cap">{inline_md(meta["cover_caption"])}</p>' if meta.get("cover_caption") else "") + "</div></section>")
        else:   # evidence documents have no cover art: a plain title block carries the h1
            cover = (f'<section class="m-cover" aria-label="Title"><div class="m-cover-in"><div class="m-cover-top"><span>{html.escape(kicker)}</span>'
                     f'<span>{html.escape(ALL[self.track])}</span></div><h1>{html.escape(meta.get("title", ""))}</h1>'
                     f'<p class="m-cover-sub">{html.escape(meta.get("subtitle", ""))}</p><div class="m-cover-by">{byline}</div></div></section>')
        head = (f'<header class="m-head"><div class="m-bar"><div><span>{html.escape(kicker)} · {html.escape(meta.get("run", ""))}</span></div><div>'
                f'{other_links}<a href="{self.out.name}.pdf">PDF</a><a href="{self.out.name}.md">Markdown</a></div></div></header>')
        tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
        run = published_run().name
        end = ((f'<div class="m-tags">{"".join(f"<span>{html.escape(t)}</span>" for t in tags)}</div>' if tags else "")
               + self.series()
               + f'<footer class="m-end"><h3>{html.escape(by)}</h3><p>{html.escape(kicker)}. Every measured number here is substituted at build time from '
               f'<code>ops_poc/runs/{run}/facts.json</code>. The platform controls are real code; the clock, providers, tools, clients and agents are a deterministic simulation in '
               f'simulated milliseconds and cost units, and the whole run replays byte for byte. Figures carry their provenance.</p><div class="links">{other_links}<a href="{poc}">POC README</a>'
               f'<a href="../ops_poc/runs/{run}/summary.md">Run summary</a><a href="../results/claim-evidence.json">Claim evidence (JSON)</a><a href="../QA.md">QA report</a></div></footer>')
        title = meta.get("title", self.track)
        footer = f"{title} · {ALL[self.track]}".replace('"', "'")
        print_css = ("@media print { @page { margin: 16mm 15mm 18mm; @bottom-left { content: \"" + footer + "\"; font: 400 7.5pt 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #6B6B6B; }"
                     " @bottom-right { content: counter(page) \" / \" counter(pages); font: 400 7.5pt 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #6B6B6B; } } }")
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>{html.escape(title)} · {ALL[self.track]}</title><meta name="description" content="{html.escape(meta.get("subtitle", ""), quote=True)}">'
                f'<meta name="author" content="{html.escape(by, quote=True)}"><meta name="generator" content="O1+O2 build_docs · evidence-kit {KIT}">'
                f'<style>{skin_css("medium")}\n{EXTRA_CSS}\n{print_css}</style></head><body>{top}{cover}{self.nav(body)}'
                f'<div class="m-page"><article class="m-article" id="top">{head}<div class="m-body">{body}</div>{end}</article></div>'
                f'<script>{medium_js()}</script><script>{EXTRA_JS}</script></body></html>')


def check_pdf(pdf: Path) -> dict:
    from pypdf import PdfReader

    r = PdfReader(str(pdf))
    blank = [i + 1 for i, p in enumerate(r.pages) if len((p.extract_text() or "").strip()) < 5 and "/XObject" not in str(p.get("/Resources", ""))]
    links = sum(1 for p in r.pages for a in (p.get("/Annots") or []) if a.get_object().get("/Subtype") == "/Link")
    return {"pages": len(r.pages), "blank_pages": blank, "pdf_links": links}


def build(track: str, facts: dict, uses: dict) -> dict:
    d = Doc(track, facts, uses)
    d.out.parent.mkdir(parents=True, exist_ok=True)
    md = d.markdown()
    d.out.with_suffix(".md").write_text(md)
    page = d.html()
    d.out.with_suffix(".html").write_text(page)
    pdf = d.out.with_suffix(".pdf")
    # Chrome prints relative links as absolute file:// URLs, which would publish a local path.  Print a copy whose local
    # links are plain text (in-page anchors and web links stay live), as F3 and T3 do.
    printable = d.out.with_name(d.out.name + ".print.html")
    printable.write_text(re.sub(r'<a ([^>]*?)href="(?!https?:|#|mailto:)[^"]*"', r'<a \1', page))
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", "--virtual-time-budget=15000",
                    printable.resolve().as_uri() + "?print=1"], capture_output=True, timeout=600)
    printable.unlink()
    leaks = local_path_findings([d.out.with_suffix(x) for x in (".md", ".html", ".pdf")], ROOT, forbid=[ROOT.parents[2], Path.home()])
    if leaks:
        raise SystemExit(f"{d.out.name}: local paths in the publication: {leaks[:5]}")
    words = len(re.sub(r"!\[.*?\]\(.*?\)|```.*?```|[#*>|`-]", " ", md, flags=re.S).split())
    info = {"track": track, "words_prose": words, "figures": d.nfig, "html_kb": len(page) // 1024, **check_pdf(pdf)}
    print(info)
    return info


def main() -> None:
    facts = load_facts()
    uses: dict = {}
    tracks = sys.argv[1:] or list(ALL)
    report = [build(t, facts, uses) for t in tracks]
    if len(tracks) == len(ALL):
        (ROOT / "docs" / "evidence-uses.json").write_text(json.dumps(uses, indent=1, default=str))
        (ROOT / "docs" / "build-report.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
