"""Build the capstone's two editions as Markdown, standalone HTML and PDF.

    uv run --project production_agentic_ai_platform --with markdown --with pypdf python tools/build_docs.py [technical|medium]

Ported from T4's tools/build_docs.py (same directives, same evidence-kit reading template, same headless-Chrome print).

Sources: docs/source/technical/*.md (concatenated in name order) and docs/source/medium.src.md; both end with
docs/source/references.md.  Every measured number is a {{key}} token resolved from docs/facts.json, which
tools/derive_facts.py computes from the published proof run.  An unknown key is a build failure; every use is recorded in
docs/evidence-uses.json.

Directives (one line each)
    ::: figure id | Caption | Alt [| wide | small]   a figure (diagrams/premium/svg/<id>.svg), numbered, with provenance
    ::: kind RECORDED+IMPLEMENTED | basis            the evidence class of a section
    ::: claim Text                                   a pull quote
    ::: eyebrow Text                                 a small uppercase label announcing the next block
    ::: legend                                       the figures' colour grammar
    ::: result R3 [| collapsed]                      the evidence card of one experiment, from the run's results.json
    ::: scorecard                                    every experiment of the run, from results.json
    ::: evidencebar                                  links to the Lab, run summary, POC README and the other edition
Blocks
    :::: callout kicker | href | link label           a short aside
Citations
    [[@key]] -> [[n]] via research/cite-keys.json;  [[n]] -> a link to reference n (HTML) or "[n]" (Markdown)
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
POCDIR = "production_agentic_ai_platform"
POC = ROOT / POCDIR
sys.path.insert(0, str(ROOT / "vendor"))
from evidence_kit import __version__ as KIT, medium, medium_js, skin_css  # noqa: E402
from evidence_kit.components import md as inline_md  # noqa: E402
from evidence_kit.publication import local_path_findings  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TRACKS = {"technical": "Technical deep dive", "medium": "Medium edition"}
OUT = {"technical": ROOT / "technical" / "production-agentic-ai-platform-final-reference-architecture",
       "medium": ROOT / "medium" / "production-agentic-ai-platform-medium"}
LAB = "../results/production-agentic-ai-platform-lab.html"
SITE = json.loads((ROOT / "docs" / "site.json").read_text())


def public_href(href: str, out: Path) -> str | None:
    """With site.json's site_base set, a repository-relative link becomes its public URL; None if it cannot be resolved."""
    if href.startswith(("#", "http://", "https://", "mailto:", "data:")):
        return href
    path, _, frag = href.partition("#")
    target = (out.parent / path).resolve()
    rel = target.relative_to(WS).as_posix()
    frag = f"#{frag}" if frag else ""
    poc = f"{ROOT.name}/{POCDIR}"
    if rel == poc or rel.startswith(poc + "/"):
        sub = rel[len(poc):].lstrip("/")
        return (SITE["poc_tree"] if target.is_dir() or not sub else SITE["poc_blob"]) + (f"/{sub}" if sub else "") + frag
    if rel.startswith(ROOT.name + "/"):
        return SITE["site_base"] + rel[len(ROOT.name) + 1:] + frag
    url = SITE["series"].get(rel)
    return url + frag if url else None


def publicize(text: str, out: Path, markdown: bool = False) -> str:
    if not SITE.get("site_base"):
        return text
    missing = []

    def sub(m):
        url = public_href(m.group(1), out)
        if url is None:
            missing.append(m.group(1))
            return m.group(0)
        return m.group(0).replace(m.group(1), url)
    text = re.sub(r"\]\(([^)\s]+)\)" if markdown else r'href="([^"]+)"', sub, text)
    if missing:
        raise SystemExit(f"{out.name}: no public URL for {sorted(set(missing))} (set them in docs/site.json)")
    return text
TOKEN = re.compile(r"\{\{([A-Za-z0-9_.@\-]+)(\|p1)?\}\}")   # {{fact}}, or {{fact|p1}}: harness ids R1, R2 shown as P1-R1, P1-R2
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
    ("State", "S1 · Memory, Context & State", "Your agent remembers everything. That's a problem.", "memory_context_state/article/memory-context-state.html"),
    ("Trust", "T1 · Agent Identity", "Who is acting, and on whose authority?", "agent_identity/medium/agent-identity-medium.html"),
    ("Trust", "T2 · Authorization & Policy", "What is this agent actually allowed to do?", "auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html"),
    ("Trust", "T3 · Human-in-the-Loop", "Authorized. Should it still act?", "human_in_loop/medium/hitl-medium.html"),
    ("Governance", "T4 · AI Control Plane", "Your agents shouldn't govern themselves", "ai_control_plane/medium/ai-control-plane-medium.html"),
    ("Governance", "T5 · Observability & Governance", "Can you explain exactly what happened?", "governance_for_ai_agents/medium/observability-governance-medium.html"),
    ("Capstone", "Production Agentic AI Platform", "The final reference architecture", None),
]
START_HERE = "series-start-here/start-here/production-ai-engineering.html"
LEGEND = [("#334155", "experience · request boundary"), ("#D97706", "orchestration · human approval"), ("#4551C9", "probabilistic: agent + models"),
          ("#B5487F", "context · memory"), ("#0E8A9A", "tools · MCP"), ("#2F6FDE", "deterministic enforcement"),
          ("#6D5BD0", "AI control plane (dashed)"), ("#172B4D", "evidence plane"), ("#5B6B82", "enterprise systems"),
          ("#D14D63", "deny · attack · failure"), ("#1F9D74", "executed · verified")]


def run_dir() -> Path:
    pub = POC / "evidence" / "published.json"   # the published run (Proof Contract v1); the plain pointer before it
    rid = json.loads(pub.read_text())["run_id"] if pub.exists() else (POC / "evidence" / "runs" / "PUBLISHED").read_text().strip()
    return POC / "evidence" / "runs" / rid


def run_rel() -> str:
    return f"{POCDIR}/evidence/runs/{run_dir().name}"


def results() -> dict:
    return json.loads((run_dir() / "raw" / "results.json").read_text())   # what run_proof.py recorded (the harness's own record)


def pack() -> dict:
    """The published run's proof pack (pae-proof/v1): results, checks, manifest, replay, negative control, pointer."""
    pub = json.loads((POC / "evidence" / "published.json").read_text())
    d = run_dir()
    return {"pub": pub, "res": json.loads((d / "results.json").read_text()), "man": json.loads((d / "manifest.json").read_text()),
            "checks": {c["id"]: c for c in map(json.loads, (d / "checks.jsonl").read_text().splitlines())},
            "replay": json.loads((d / "replay.json").read_text()), "nc": json.loads((d / "negative-control" / "results.json").read_text())}


def xid(rid: str) -> str:
    """R3 or P1-R3 → the contract id P1-R3."""
    return rid if rid.startswith("P1-") else f"P1-{rid}"


STATUS_WORD = {"PASS": "pass", "EXPECTED_FAILURE": "expected failure", "FAIL": "fail"}


def counts(x: dict) -> str:
    k = x["counts"]
    return " · ".join(f"{k[s]} {STATUS_WORD[s]}" for s in ("PASS", "EXPECTED_FAILURE", "FAIL") if k[s] or s == "PASS")


def load_facts() -> dict:
    return json.loads((ROOT / "docs" / "facts.json").read_text())


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
        v = fmt(facts[key]["value"])
        return re.sub(r"\bR(\d+)\b", r"P1-R\1", v) if m.group(2) else v
    out = TOKEN.sub(sub, src)
    if "{{" in out or "TBD" in out or "FILL:" in out or "TODO" in out:
        raise SystemExit(f"{doc}: unresolved placeholder left in the source")
    return out


def cite_keys(src: str, doc: str) -> str:
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


def expand_includes(src: str, doc: str) -> str:
    """Code shown in the article is copied from the run or the POC at build time, never typed.

    ::: json R1 policy_input | key1,key2   a (subset of a) recorded fact of experiment R1, from results.json
    ::: file config/policies/production.yaml | 1-22   lines of a POC file
    """
    res = {e["id"]: e for e in results()["experiments"]}

    def js(m: re.Match) -> str:
        rid, key, sel = m.group(1), m.group(2), (m.group(3) or "").strip()
        if rid not in res or key not in res[rid]["facts"]:
            raise SystemExit(f"{doc}: no recorded fact {rid}.{key}")
        val = res[rid]["facts"][key]
        if isinstance(val, str) and val.startswith("{"):
            val = json.loads(val)
        if sel:
            val = {k: val[k] for k in [s.strip() for s in sel.split(",")]}
        body = json.dumps(val, indent=2, ensure_ascii=False)
        return f"```json\n{body}\n```\n\n*Recorded: `{rid}` fact `{key}`, copied at build time from `{run_rel()}/raw/results.json`.*"

    def fl(m: re.Match) -> str:
        path, rng = m.group(1), (m.group(2) or "").strip()
        lines = (POC / path).read_text().splitlines()
        if rng:
            a, b = (int(x) for x in rng.split("-"))
            lines = lines[a - 1:b]
        lang = {"yaml": "yaml", "yml": "yaml", "py": "python", "json": "json"}.get(path.rsplit(".", 1)[-1], "text")
        return f"```{lang}\n" + "\n".join(lines) + f"\n```\n\n*From `{POCDIR}/{path}`" + (f", lines {rng}" if rng else "") + ".*"

    src = re.sub(r"^::: json (R\d+) (\w+)(?: \| (.*))?$", js, src, flags=re.M)
    return re.sub(r"^::: file (\S+)(?: \| (.*))?$", fl, src, flags=re.M)


def own_fonts(svg: str, key: str) -> str:
    """Each inline SVG embeds its own font subsets under shared family names; rename them per figure so they don't collide."""
    for fam in set(re.findall(r'@font-face \{ font-family: "?([^";]+)"?;', svg)):
        svg = re.sub(rf'(@font-face \{{ font-family: )"?{re.escape(fam)}"?;', lambda m: f'{m.group(1)}"{fam} {key}";', svg)
        svg = svg.replace(f'font-family="{fam}, ', f'font-family="{fam} {key}, ')
    return svg


def references() -> dict[str, str]:
    out = {}
    for m in re.finditer(r"^\*\*\[(\d+)\]\*\* (.+?) — ", (ROOT / "research" / "sources.md").read_text(), re.M):
        out[m.group(1)] = m.group(2)
    return out


HL_RULES = {
    "json": [(r'"(?:[^"\\]|\\.)*"(?=\s*:)', "k"), (r'"(?:[^"\\]|\\.)*"', "s"), (r"\b(?:true|false|null)\b", "c"), (r"-?\b\d+(?:\.\d+)?\b", "n")],
    "python": [(r"#[^\n]*", "m"), (r'"""[\s\S]*?"""|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', "s"),
               (r"\b(?:def|class|return|if|elif|else|for|while|in|not|and|or|is|None|True|False|import|from|as|with|try|except|raise|yield|lambda|async|await|pass)\b", "c"),
               (r"\b\d+(?:\.\d+)?\b", "n")],
    "yaml": [(r"#[^\n]*", "m"), (r"^\s*-?\s*[\w.\-]+(?=:)", "k"), (r'"(?:[^"\\]|\\.)*"', "s"), (r"\b(?:true|false|null)\b", "c"), (r"\b\d+(?:\.\d+)?\b", "n")],
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
        out.append(f'<span class="hl-{rules[int(m.lastgroup[1:])][1]}">{html.escape(m.group(0), quote=False)}</span>')
        pos = m.end()
    out.append(html.escape(text[pos:], quote=False))
    return "".join(out)


def _font_faces() -> str:
    """The diagrams' three fonts, embedded (assets/fonts, SIL OFL 1.1): Lilita One, Nunito, Cascadia Code."""
    import base64
    faces = (("Lilita One", "LilitaOne-Regular.woff2", "400"), ("Nunito", "Nunito-Variable-latin.woff2", "200 1000"),
             ("Cascadia", "CascadiaCode-Regular.woff2", "400"))
    return "".join(f"@font-face{{font-family:'{fam}';font-weight:{wt};font-display:swap;src:url(data:font/woff2;base64,"
                   f"{base64.b64encode((ROOT / 'assets' / 'fonts' / fn).read_bytes()).decode()}) format('woff2')}}" for fam, fn, wt in faces)


# One type system for pages and figures: the figures' Lilita One, Nunito and Cascadia replace the skin's sohne / Source Code Pro;
# body text stays Source Serif 4, as in T2.
TYPE_CSS = _font_faces() + """
:root{--sans:Nunito,'Helvetica Neue',Helvetica,Arial,sans-serif;--mono:Cascadia,'SF Mono',Menlo,Consolas,monospace;--display:'Lilita One',Nunito,sans-serif}
.m-cover h1,.m-head h1{font-family:var(--display);font-weight:400;letter-spacing:0}
.m-body h2,.m-body h3,.m-body h4{font-family:var(--sans);font-weight:800}
code,pre{font-variant-ligatures:none;font-feature-settings:'calt' 0,'liga' 0}
"""

EXTRA_CSS = TYPE_CSS + """
.fig svg{cursor:zoom-in;width:100%;height:auto}
.zoom{position:fixed;inset:0;background:rgba(15,23,42,.86);display:none;z-index:9999;overflow:auto;padding:24px}
.zoom.on{display:block}.zoom .zin{background:#fff;border-radius:12px;padding:12px;margin:0 auto;max-width:min(2400px,96vw)}
.zoom svg{width:100%;height:auto;cursor:zoom-out}.zoom .zx{position:fixed;top:14px;right:22px;color:#fff;font:600 15px/1 sans-serif;cursor:pointer;background:none;border:0}
.hai-progress{position:fixed;top:0;left:0;height:3px;width:0;background:#2F6FDE;z-index:10000}
.m-body h2,.m-body h3{position:relative;scroll-margin-top:72px}
.hai-anchor{margin-left:.35em;font:500 .7em/1 var(--sans);color:#8494AA;text-decoration:none;opacity:0;border:0;background:none;cursor:pointer;padding:2px 4px}
.m-body h2:hover .hai-anchor,.m-body h3:hover .hai-anchor,.hai-anchor:focus-visible{opacity:1}
.hai-code{position:relative}.hai-copy{position:absolute;top:8px;right:8px;font:600 12px/1 var(--sans);
  padding:6px 9px;border-radius:7px;border:1px solid #D5DCE6;background:#fff;color:#334155;cursor:pointer}
.hai-copy:hover{background:#F1F5F9}
pre code .hl-k{color:#1D5FB8}pre code .hl-s{color:#0B7A6B}pre code .hl-n{color:#B45309}pre code .hl-c{color:#7C3AED}pre code .hl-m{color:#64748B;font-style:italic}
.hai-cite{font-size:.72em;vertical-align:super;line-height:0;text-decoration:none;padding:0 1px}
.hai-ref{scroll-margin-top:72px;overflow-wrap:anywhere}.hai-ref:target{background:#FFF7E0;border-radius:6px}
.hai-series{margin:48px 0 0;font-family:var(--sans)}
.hai-series h2{font-size:15px;letter-spacing:.08em;text-transform:uppercase;color:#6B6B6B;margin:0 0 12px}
.hai-series ol{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.hai-series li{margin:0;border:1px solid #E3E8EF;border-radius:12px;padding:12px 14px;background:#fff}
.hai-series li.cur{border:2px solid #2F6FDE;background:#F7FAFF}
.hai-series .r{display:block;font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:#6B6B6B;margin-bottom:4px}
.hai-series b{display:block;font-size:15.5px}.hai-series span.q{display:block;font-size:14px;color:#52637A;margin-top:3px}
.hai-series a{color:inherit}
.hai-top{position:fixed;right:18px;bottom:18px;z-index:50;border:1px solid #D5DCE6;background:#fff;border-radius:999px;padding:10px 14px;
  font:600 13px/1 var(--sans);color:#172B4D;cursor:pointer;opacity:0;pointer-events:none;transition:opacity .2s}
.hai-top.on{opacity:1;pointer-events:auto}
a:focus-visible,button:focus-visible,summary:focus-visible{outline:3px solid #0E8A9A;outline-offset:2px;border-radius:4px}
.m-body pre{overflow-x:auto;max-width:100%}.m-body .table-wrap{overflow-x:auto}
.fig{max-width:100%}.m-body img{max-width:100%;height:auto}
.m-body p code,.m-body li code,.m-body td code,.ev-card code,.m-end code,.ev-score code,.m-body figcaption code{overflow-wrap:anywhere;word-break:break-word}
.fig-scroll{max-width:100%}
@media (min-width:729px){.m-body figure.fig.fig-sm{width:min(640px, calc(100vw - var(--navw) - 48px))}}
@media (max-width:640px){.hai-series ol{grid-template-columns:1fr}.hai-copy{padding:5px 7px}
  .fig-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:10px}.fig-scroll svg{min-width:720px}
  .fig figcaption::before{content:"Scroll sideways or tap the figure to enlarge. ";display:block;font-size:12px;color:#8494AA;margin-bottom:4px}}
@media (min-width:729px){.m-body figure.fig.fig-wide{width:min(1240px, calc(100vw - var(--navw) - 48px))}}
.hai-badge{display:inline-block;font:600 10.5px/1 var(--mono);letter-spacing:.06em;padding:4px 7px;border-radius:6px;border:1px solid;margin:0 6px 0 0;vertical-align:1px}
.hai-badge.ARCHITECTURE{color:#334155;border-color:#334155;background:#EEF1F5}.hai-badge.MEASURED{color:#1F9D74;border-color:#1F9D74;background:#E6F6EF}.hai-badge.IMPLEMENTATION{color:#0E8A9A;border-color:#0E8A9A;background:#E4F5F7}
.hai-eyebrow{margin:2.4em 0 -1.4em!important;font:700 12.5px/1.2 var(--sans)!important;letter-spacing:.14em;text-transform:uppercase;color:#2F6FDE;text-align:center}
.hai-legend{margin:2em 0 0;padding:14px 16px;border:1px solid #E3E8EF;border-radius:12px;background:#FBFCFD;font:400 14px/1.5 var(--sans);color:#2E3A4F}
.hai-legend b.h{display:block;font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;color:#6B6B6B;margin:0 0 8px}
.hai-legend ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px 16px}.hai-legend li{margin:0;padding:0;font-size:14px}
.hai-legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.hai-evbar{margin:2.2em 0 0;border:1px solid #B0C8F2;border-radius:14px;background:#F7FAFF;padding:14px 16px;font-family:var(--sans)}
.hai-evbar b.h{display:block;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#2F6FDE;margin:0 0 10px}
.hai-evbar ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.hai-evbar li{margin:0;padding:0}.hai-evbar a{display:block;border:1px solid #E3E8EF;border-radius:10px;background:#fff;padding:10px 12px;text-decoration:none;color:#172B4D;height:100%}
.hai-evbar a b{display:block;font-size:13px;line-height:1.3;letter-spacing:.04em;text-transform:uppercase}.hai-evbar a span{display:block;font-size:13.5px;line-height:1.35;color:#52637A;margin-top:4px}
.hai-evbar a:hover{border-color:#2F6FDE}
.ev-card{margin:1.8em 0;border:1px solid #E3E8EF;border-left:4px solid #1F9D74;border-radius:12px;background:#fff;font-family:var(--sans)}
.ev-card.fail{border-left-color:#D14D63}
.ev-card summary,.ev-card .ev-h{list-style:none;cursor:pointer;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;padding:12px 16px}
.ev-card summary::-webkit-details-marker{display:none}
.ev-card .ev-id{font:700 12.5px/1 var(--mono);color:#fff;background:#172B4D;border-radius:6px;padding:5px 7px}
.ev-card .ev-t{font-weight:600;font-size:15.5px;color:#172B4D;flex:1 1 260px}
.ev-card .ev-s{font:700 12.5px/1 var(--mono);color:#1F9D74}
.ev-card.fail .ev-s{color:#D14D63}
.ev-card .ev-q{padding:0 16px 8px;color:#52637A;font-size:14px}
.ev-card ul{list-style:none;margin:0;padding:4px 16px 14px;display:grid;gap:6px}
.ev-card li{margin:0;padding:0 0 0 22px;position:relative;font-size:14px;line-height:1.45;color:#2E3A4F}
.ev-card li::before{content:"✓";position:absolute;left:0;top:0;color:#1F9D74;font-weight:700}
.ev-card li.x::before{content:"✗";color:#D14D63}
.ev-card li.ctl::before{content:"◇";color:#D97706}.ev-score td.st.ctl{color:#D97706}
.ev-card li code{font-size:12px;color:#52637A;background:none;padding:0}
.ev-card .ev-src{padding:0 16px 12px;font-size:12.5px;color:#8494AA}
.ev-score{margin:1.8em 0}.ev-score table{width:100%;border-collapse:collapse;font-family:var(--sans);font-size:14.5px}
.ev-score th{font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:#6B6B6B;text-align:left;padding:8px 10px;border-bottom:2px solid #E3E8EF}
.ev-score td{padding:9px 10px;border-bottom:1px solid #EEF1F5;vertical-align:top}.ev-score td.id{font:700 12.5px/1.2 var(--mono);color:#172B4D;white-space:nowrap}
.ev-score td.st{font:700 12.5px/1.2 var(--mono);white-space:nowrap}.ev-score td.st.pass{color:#1F9D74}.ev-score td.st.fail{color:#D14D63}
.ev-score td.q{color:#52637A}.ev-score caption{caption-side:bottom;text-align:left;font-size:13px;color:#6B6B6B;padding-top:8px}
@media (max-width:728px){.hai-evbar ul{grid-template-columns:repeat(2,minmax(0,1fr))}.ev-score td.q{display:none}.ev-score th.q{display:none}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
@media print{.m-body figure.fig.fig-wide{width:auto!important}.hai-evbar,.hai-legend,.ev-card,.ev-score{break-inside:avoid}.hai-evbar ul{grid-template-columns:repeat(4,minmax(0,1fr))}
  .m-body figure.fig.fig-sm{width:62%!important;margin-left:auto;margin-right:auto}.zoom,.hai-progress,.hai-top,.hai-copy,.hai-anchor{display:none!important}.fig{break-inside:avoid}.fig svg{max-height:228mm}
  .m-body h2,.m-body h3{break-after:avoid}pre,table,.m-callout,blockquote{break-inside:avoid}.hai-series{break-inside:avoid}
  a.hai-cite{color:inherit}.m-body pre{white-space:pre-wrap;overflow-wrap:anywhere}.m-body .table-wrap,.ev-score{overflow:visible!important}}
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
        src_dir = ROOT / "docs" / "source"
        if (src_dir / track).is_dir():
            raw = "\n\n".join(p.read_text().strip() for p in sorted((src_dir / track).glob("*.md"))) + "\n"
        else:
            raw = (src_dir / f"{track}.src.md").read_text()
        refs = (src_dir / "references.md").read_text()
        if track == "medium":   # the Medium edition lists only the sources it cites, under the same numbers
            cited = {str(k) for k in (json.loads((ROOT / "research" / "cite-keys.json").read_text())[c] for c in CITEKEY.findall(raw))}
            paras = refs.split("\n\n")
            refs = "## Sources\n\n" + "\n\n".join(q for q in paras if re.match(r"\*\*\[(\d+)\]", q) and re.match(r"\*\*\[(\d+)\]", q).group(1) in cited)
            every = [q for q in paras if re.match(r"\*\*\[(\d+)\]", q)]
            series = sum("· SERIES" in q for q in every)
            refs += (f"\n\nThese are the primary references this edition cites. The [technical edition]"
                     f"(../technical/production-agentic-ai-platform-final-reference-architecture.html#references) lists all {len(every)} sources "
                     f"({len(every) - series} external, each with the quotes it supports, and the {series} earlier notes of the series).\n")
        raw = raw.rstrip() + "\n\n" + refs
        self.out = OUT[track]
        self.meta, src = front_matter(raw)
        self.src = expand_includes(cite_keys(render_facts(src, facts, track, uses), track), track)
        self.meta = {k: render_facts(v, facts, track, uses) for k, v in self.meta.items()}
        self.figs = json.loads((ROOT / "diagrams" / "manifest.json").read_text())["figures"]
        self.refs = references()
        self.res = results()
        self.exp = {e["id"]: e for e in self.res["experiments"]}
        self.pk = pack()
        self.X = {x["id"]: x for x in self.pk["res"]["experiments"]}
        self.blocks: list[str] = []
        self.nfig = 0

    def other(self) -> tuple[str, str]:
        t = next(t for t in TRACKS if t != self.track)
        return TRACKS[t], f"../{OUT[t].parent.name}/{OUT[t].name}"

    def links(self) -> list[tuple[str, str, str]]:
        """Evidence bar: (title, description, href relative to this document's folder)."""
        lbl, href = self.other()
        return [("Proof Lab", "Every experiment, check and claim", LAB),
                ("Run summary", f"Run {run_dir().name}", f"../{run_rel()}/summary.md"),
                ("Verification", "PROOF VERIFICATION of the run", f"../{POCDIR}/evidence/verification/verification.txt"),
                ("POC README", "Reproduce and verify it offline", f"../{POCDIR}/README.md"),
                (lbl, "The other edition", f"{href}.html")]

    # ---- the Proof Contract components (evidence-kit 5) -----------------------------------------------------------------
    def strip_rows(self) -> list[tuple[str, str]]:
        r, F, nc = self.pk["res"], self.pk["res"]["facts"], self.pk["nc"]
        c = r["check_counts"]
        d = lambda k: F[k]["display"]  # noqa: E731
        return [("Run", f"`{r['run_id']}`"), ("Experiments", str(c["experiments"])),
                ("Checks", f"{c['checks']}: {c['pass']} pass, {c['expected_failure']} expected failure, {c['fail']} fail"),
                ("MCP", f"stdio, SDK {d('env_mcp_sdk')}"), ("Crash", f"real SIGKILL ×{d('raw.sigkills')}"),
                ("Replay", f"{d('replay.level')}: {d('replay_checks_identical')}/{d('replay_checks_compared')} harness assertions"),
                ("Negative control", f"{nc['result'].replace('_', ' ').lower()}: {d('neg_checks_failed')} of {d('neg_checks')} harness assertions failed"),
                ("Tracing", f"OpenTelemetry {d('env_opentelemetry_sdk')}, one trace")]

    def classes(self, compact: bool) -> list[dict]:
        out = []
        for c in self.pk["res"]["profile"]["classes"]:
            items = [i["text"] for i in c["items"]]
            if compact:
                items = items[:4] if c["class"] in ("REAL", "INJECTED") else items[:2]
                if c["class"] == "GENERATED":
                    continue
            out.append({"class": c["class"], "meaning": None if compact else c.get("meaning"), "items": items})
        return out

    def refresh_text(self) -> tuple[str, str]:
        pub, F = self.pk["pub"], self.pk["res"]["facts"]
        c = self.pk["res"]["check_counts"]
        prev = pub["history"][0]["run_id"]
        body = (f"The proof was standardized under the series' Proof Contract v1 and run again on {pub['promoted_at'][:10]}: the published "
                f"run changed from `{prev}` to `{pub['run_id']}`. The 8 cases the standardization added (two authority layers, three tool-"
                f"governance cases, two capability variants, one human decision) found one gap, now fixed: the release server did not compare "
                f"a capability's operation. Checks are now counted by the contract: {c['checks']} checks, {c['pass']} pass, "
                f"{c['expected_failure']} expected failure (controls), {c['fail']} fail. The "
                f"{F['prev_checks_compared']['display']} harness assertions both runs share are identical.")
        return pub["promoted_at"][:10], body


    # ---- evidence directives ---------------------------------------------------------------------------------------
    def result_md(self, rid: str) -> str:
        x = self.X[xid(rid)]
        C = self.pk["checks"]
        rows = "\n".join(f"- {'✓' if C[i]['status'] == 'PASS' else '◇' if C[i]['status'] == 'EXPECTED_FAILURE' else '✗'} {C[i]['description']} (`{i}`)"
                         for i in x["checks"])
        return (f"**Evidence · {x['id']} · {x['title']}: {x['result'].replace('_', ' ')} ({counts(x)})**\n\n*{x['question']}*\n\n{rows}\n\n"
                f"*From `{run_rel()}/checks.jsonl`: each check compares facts read from `raw/`, evaluated by evidence_kit.proof. "
                f"◇ = a control: the safeguard's invariant breaks as intended.*")

    def result_html(self, rid: str, collapsed: bool) -> str:
        if xid(rid) not in self.X:
            raise SystemExit(f"{self.track}: no experiment {xid(rid)} in the proof pack")
        x = self.X[xid(rid)]
        C = self.pk["checks"]
        cls_of = {"PASS": "", "EXPECTED_FAILURE": "ctl", "FAIL": "x"}
        lis = "".join(f'<li class="{cls_of[C[i]["status"]]}">{html.escape(C[i]["description"])} <code>{html.escape(i)}</code></li>' for i in x["checks"])
        head = (f'<span class="ev-id">{x["id"]}</span><span class="ev-t">{html.escape(x["title"])}</span>'
                f'<span class="ev-s">{counts(x)}</span>')
        body = (f'<div class="ev-q">{html.escape(x["question"])}</div><ul>{lis}</ul>'
                f'<div class="ev-src">From <code>{run_rel()}/checks.jsonl</code> · each check compares facts read from <code>raw/</code> · '
                f'evaluated by <code>evidence_kit.proof</code> · ◇ a control (expected failure)</div>')
        cls = f'ev-card{"" if x["result"] != "FAIL" else " fail"}'
        if collapsed:
            return f'<details class="{cls}" id="ev-{x["id"]}"><summary>{head}</summary>{body}</details>'
        return f'<section class="{cls}" id="ev-{x["id"]}" aria-label="Evidence {x["id"]}"><div class="ev-h">{head}</div>{body}</section>'

    def scorecard_md(self) -> str:
        r = self.pk["res"]
        rows = "\n".join(f"| {x['id']} | {x['title']} | {x['result'].replace('_', ' ')} | {counts(x)} |" for x in r["experiments"])
        c = r["check_counts"]
        return (f"| | Experiment | Result | Checks |\n|---|---|---|---|\n{rows}\n\n*Run `{r['run_id']}` · `pae-proof/v1`: {c['experiments']} experiments, "
                f"{c['checks']} checks: {c['pass']} pass, {c['expected_failure']} expected failure, {c['fail']} fail. From `{run_rel()}/results.json`.*")

    def scorecard_html(self) -> str:
        r = self.pk["res"]
        tone = {"PASS": "pass", "EXPECTED_FAILURE": "ctl", "FAIL": "fail"}
        rows = "".join(
            f'<tr><td class="id">' + (f'<a href="#ev-{x["id"]}">{x["id"]}</a>' if x["id"].removeprefix("P1-") in self.anchored or x["id"] in self.anchored else x["id"])
            + f'</td><td>{html.escape(x["title"])}</td><td class="q">{html.escape(x["question"])}</td>'
            f'<td class="st {tone[x["result"]]}">{counts(x)}</td></tr>' for x in r["experiments"])
        c = r["check_counts"]
        return (f'<div class="ev-score table-wrap"><table><thead><tr><th></th><th>Experiment</th><th class="q">Question</th><th>Checks</th></tr></thead>'
                f'<tbody>{rows}</tbody><caption>Run <code>{r["run_id"]}</code> · <code>pae-proof/v1</code> · {c["experiments"]} experiments · {c["checks"]} checks: '
                f'{c["pass"]} pass, {c["expected_failure"]} expected failure, {c["fail"]} fail · from <code>{run_rel()}/results.json</code></caption></table></div>')

    def claimtrace_md(self) -> str:
        rows = "\n".join(f"| {cl['id']} | {cl['statement']} | {cl['verdict']} | {', '.join(cl.get('experiments', [])) or '—'} | "
                         f"{len(cl.get('checks', [])) or cl.get('rests_on', '')} |" for cl in self.pk["res"]["claims"])
        return f"| Claim | Statement | Verdict | Experiments | Checks |\n|---|---|---|---|---|\n{rows}\n\n*From `{run_rel()}/results.json → claims` (`proof/claims.toml`).*"

    def claimtrace_html(self) -> str:
        rows = "".join(f'<tr><td class="id">{cl["id"]}</td><td>{html.escape(cl["statement"])}</td><td>{cl["verdict"]}</td>'
                       f'<td>{html.escape(", ".join(cl.get("experiments", [])) or "—")}</td><td>{len(cl.get("checks", [])) or "rests on: " + html.escape(cl.get("rests_on", ""))}</td></tr>'
                       for cl in self.pk["res"]["claims"])
        return (f'<div class="ev-score table-wrap"><table><thead><tr><th>Claim</th><th>Statement</th><th>Verdict</th><th>Experiments</th><th>Checks</th></tr></thead>'
                f'<tbody>{rows}</tbody><caption>Each verdict is tested against its checks by <code>evidence_kit.proof.trace</code> · from '
                f'<code>{run_rel()}/results.json</code> (<code>proof/claims.toml</code>)</caption></table></div>')

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
                return "*How to read the figures.* " + " · ".join(t for _, t in LEGEND) + ". Badges: `ARCHITECTURE` our design, no run result claimed · `MEASURED` run · experiment · checks · source · `IMPLEMENTATION` the POC's runtime topology."
            if kind == "evidencebar":
                return "**Inspect the evidence:** " + " · ".join(f"[{t}]({h.replace('.html', '.md') if 'lab' not in h else h}) ({d})" for t, d, h in self.links())
            if kind == "result":
                return self.result_md(arg.split(" | ")[0].strip())
            if kind == "scorecard":
                return self.scorecard_md()
            if kind == "claimtrace":
                return self.claimtrace_md()
            if kind == "proofstrip":
                return "**Published proof** · " + " · ".join(f"{k}: {v}" for k, v in self.strip_rows()) + f" · [Inspect the Proof Lab →]({LAB}#scorecard)"
            if kind == "reality":
                return "\n".join(f"- **{c['class']}**: " + "; ".join(c["items"]) for c in self.classes(arg == "compact"))
            if kind == "refresh":
                date, body = self.refresh_text()
                return f"> **Evidence refresh · {date}.** {body} [The proof-refresh delta](../docs/proof-standardization/proof-refresh-delta.md)"
            return m.group(0)

        def blk(m: re.Match) -> str:
            head, href, label = ([x.strip() for x in (m.group(2) or "").split(" | ")] + ["", "", ""])[:3]
            body = "\n".join(f"> {line}" for line in m.group(3).strip().splitlines())
            link = f"\n>\n> [{label}]({href})" if href else ""
            return f"> **{head}**\n>\n{body}{link}"

        src = BLOCK.sub(blk, self.src)
        src = DIRECTIVE.sub(fig, src)
        src = CITE.sub(lambda m: f"[{m.group(1)}]", src)
        cover = f"![{self.meta.get('cover_alt', '')}](../diagrams/premium/png/{self.meta['cover']}.png)\n\n" if self.meta.get("cover") else ""
        head = (f"# {self.meta.get('title', '')}\n\n*{self.meta.get('subtitle', '')}*\n\n{cover}"
                f"{self.meta.get('kicker', '')} · {TRACKS[self.track]} · "
                f"{('published ' + SITE['published']) if SITE.get('published') else ('proof run ' + self.meta.get('filed', ''))}\n\n")
        lbl, href = self.other()
        series = " · ".join(f"[{name}](../../{path})" for _, name, _, path in SERIES if path)
        tail = (f"\n\n---\n\n**The series.** {series} · Capstone: Production Agentic AI Platform (this note). "
                f"[Start Here](../../{START_HERE}). Companion: [{lbl}]({href}.md). Every measured number is substituted from "
                f"`docs/facts.json`, derived from `{run_rel()}/results.json`.\n")
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
        badges = "".join(f'<span class="hai-badge {b}">{b}</span>' for b in self.figs[fid].get("badges", []))
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
        elif kind == "eyebrow":
            out = f'<p class="hai-eyebrow">{html.escape(arg)}</p>'
        elif kind == "legend":
            out = ('<aside class="hai-legend" aria-label="How to read the figures"><b class="h">How to read the figures</b><ul>'
                   + "".join(f'<li><i style="background:{c}"></i>{html.escape(t)}</li>' for c, t in LEGEND) + '</ul><ul style="margin-top:8px">'
                   + '<li><span class="hai-badge ARCHITECTURE">ARCHITECTURE</span>our design, no measured values</li>'
                   + '<li><span class="hai-badge MEASURED">MEASURED</span>values from the published run: run · experiment · checks · source</li>'
                   + '<li><span class="hai-badge IMPLEMENTATION">IMPLEMENTATION</span>what the POC contains; runtime topology, no benchmark result</li></ul></aside>')
        elif kind == "evidencebar":
            out = ('<nav class="hai-evbar" aria-label="Inspect the evidence"><b class="h">Inspect the evidence</b><ul>'
                   + "".join(f'<li><a href="{h}"><b>{html.escape(t)}</b><span>{html.escape(d)}</span></a></li>' for t, d, h in self.links()) + '</ul></nav>')
        elif kind == "result":
            rid, _, opt = arg.partition(" | ")
            out = self.result_html(rid.strip(), opt.strip() == "collapsed")
        elif kind == "scorecard":
            out = self.scorecard_html()
        elif kind == "claimtrace":
            out = self.claimtrace_html()
        elif kind == "proofstrip":
            out = medium.proof_strip(self.strip_rows(), title="Published proof", href=LAB + "#scorecard", link="Inspect the Proof Lab",
                                     kicker="pae-proof/v1", caption=arg or "")
        elif kind == "reality":
            out = medium.reality(self.classes(arg == "compact"), title="What actually ran", kicker="execution profile",
                                 caption="Classified by what the code does, not by the diagram. Each REAL item names the check that shows it ran (Proof Lab).")
        elif kind == "refresh":
            date, body = self.refresh_text()
            out = medium.refresh(date, body, changed=True, href=f"../docs/proof-standardization/proof-refresh-delta.md")
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
        self.anchored = set(re.findall(r"^::: result (R\d+)", self.src, re.M))
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
                if not (WS / path).exists():
                    raise SystemExit(f"series link target missing: {path}")
                inner = f'<a href="../../{path}"><b>{html.escape(name)}</b></a>'
            else:
                inner = f"<b>{html.escape(name)}</b>"
            cls = "cur" if path is None else ""
            lis.append(f'<li class="{cls}"{" aria-current=page" if path is None else ""}><span class="r">{role}</span>{inner}<span class="q">{html.escape(q)}</span></li>')
        if not (WS / START_HERE).exists():
            raise SystemExit("start-here page missing")
        return (f'<nav class="hai-series" aria-labelledby="series-h"><h2 id="series-h">Production AI Engineering · the whole series</h2><ol>{"".join(lis)}</ol>'
                f'<p style="font-size:14px;margin-top:10px"><a href="../../{START_HERE}">The full learning map (Start Here)</a></p></nav>')

    def social(self, title: str, desc: str) -> str:
        e = lambda v: html.escape(v, quote=True)
        tags = (f'<meta property="og:type" content="article"><meta property="og:title" content="{e(title)}">'
                f'<meta property="og:description" content="{e(desc)}"><meta property="og:site_name" content="Production AI Engineering">'
                f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}">'
                f'<meta name="twitter:description" content="{e(desc)}">')
        if SITE.get("site_base"):
            url = SITE["site_base"] + self.out.relative_to(ROOT).as_posix() + ".html"
            img = SITE["site_base"] + "medium/images/00-cover.png"
            tags += (f'<link rel="canonical" href="{e(url)}"><meta property="og:url" content="{e(url)}">'
                     f'<meta property="og:image" content="{e(img)}"><meta name="twitter:image" content="{e(img)}">')
        if SITE.get("published"):
            tags += f'<meta property="article:published_time" content="{e(SITE["published"])}">'
        return tags

    def html(self) -> str:
        meta = self.meta
        body = self.body_html()
        words = len(re.sub(r"<details.*?</details>|<svg.*?</svg>|<[^>]+>", " ", body, flags=re.S).split())
        mins = max(1, math.ceil((words / 265 * 60 + sum(max(12 - i, 3) for i in range(self.nfig))) / 60))
        by, kicker = meta.get("byline", ""), meta.get("kicker", "")
        lbl, href = self.other()
        other_link = f'<a href="{href}.html">{html.escape(lbl)}</a>'
        poc = f"../{POCDIR}/README.md"
        top = ('<header class="m-top"><a class="pub" href="#top">Production AI Engineering</a><nav aria-label="Edition">'
               '<button type="button" class="m-toc-btn" aria-expanded="false" aria-controls="m-nav">Contents</button>'
               f'{other_link.replace("<a ", "<a class=\"opt\" ", 1)}<a href="{LAB}">Lab</a><a href="{poc}">POC</a><a href="../../{START_HERE}">Start Here</a></nav></header>')
        byline = (f'<span class="m-avatar" aria-hidden="true">PA</span><div><b>{html.escape(by)}</b>'
                  f'{mins} min read · {html.escape(("Published " + SITE["published"]) if SITE.get("published") else ("Proof run " + meta.get("filed", "")))} · {TRACKS[self.track]}</div>')
        art = self.figure(f"{meta['cover']} | cover | {meta.get('cover_alt', meta.get('title', ''))}", cover=True)
        cover = (f'<section class="m-cover" aria-label="Cover"><div class="m-cover-in"><div class="m-cover-top"><span>{html.escape(kicker)}</span>'
                 f'<span>{html.escape(TRACKS[self.track])}</span></div><h1>{html.escape(meta.get("title", ""))}</h1>'
                 f'<p class="m-cover-sub">{html.escape(meta.get("subtitle", ""))}</p><div class="m-cover-by">{byline}</div>'
                 f'<figure class="m-cover-art">{art}</figure>'
                 + (f'<p class="m-cover-cap">{inline_md(meta["cover_caption"])}</p>' if meta.get("cover_caption") else "") + "</div></section>")
        head = (f'<header class="m-head"><div class="m-bar"><div><span>{html.escape(kicker)} · {html.escape(meta.get("run", ""))}</span></div><div>'
                f'{other_link}<a href="{self.out.name}.pdf">PDF</a><a href="{self.out.name}.md">Markdown</a></div></div></header>')
        tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
        rr = run_rel()
        end = ((f'<div class="m-tags">{"".join(f"<span>{html.escape(t)}</span>" for t in tags)}</div>' if tags else "")
               + self.series()
               + f'<footer class="m-end"><h3>{html.escape(by)}</h3><p>{html.escape(kicker)}. Every measured number here is substituted at build time from '
               f'<code>docs/facts.json</code>, derived from <code>{rr}/results.json</code>. The enterprise systems and the models are simulated; the MCP '
               f'servers, OpenTelemetry, SQLite state and process crashes are real. Figures carry their provenance.</p><div class="links">{other_link}'
               f'<a href="{poc}">POC README</a><a href="../{rr}/summary.md">Run summary</a><a href="{LAB}">Lab</a><a href="../QA.md">QA report</a></div></footer>')
        title = meta.get("title", self.track)
        footer = f"{title} · {TRACKS[self.track]}".replace('"', "'")
        print_css = ("@media print { @page { margin: 16mm 15mm 18mm; @bottom-left { content: \"" + footer + "\"; font: 400 7.5pt 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #6B6B6B; }"
                     " @bottom-right { content: counter(page) \" / \" counter(pages); font: 400 7.5pt 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #6B6B6B; } } }")
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>{html.escape(title)} · {TRACKS[self.track]}</title><meta name="description" content="{html.escape(meta.get("subtitle", ""), quote=True)}">'
                f'<meta name="author" content="{html.escape(by, quote=True)}"><meta name="generator" content="capstone build_docs · evidence-kit {KIT}">'
                + self.social(title, meta.get("subtitle", "")) +
                f'<style>{skin_css("medium")}\n{EXTRA_CSS}\n{print_css}</style></head><body>{top}{cover}{self.nav(body)}'
                f'<div class="m-page"><article class="m-article" id="top">{head}<div class="m-body">{body}</div>{end}</article></div>'
                f'<script>{medium_js()}</script><script>{EXTRA_JS}</script></body></html>')


def check_pdf(pdf: Path) -> dict:
    from pypdf import PdfReader

    r = PdfReader(str(pdf))
    blank = [i + 1 for i, p in enumerate(r.pages) if len((p.extract_text() or "").strip()) < 5 and "/XObject" not in str(p.get("/Resources", ""))]
    links = sum(1 for p in r.pages for a in (p.get("/Annots") or []) if a.get_object().get("/Subtype") == "/Link")
    return {"pages": len(r.pages), "blank_pages": blank, "pdf_links": links}


def build(track: str, facts: dict, uses: dict, pdf: bool = True) -> dict:
    d = Doc(track, facts, uses)
    d.out.parent.mkdir(parents=True, exist_ok=True)
    md = d.markdown()
    md = publicize(md, d.out.with_suffix(".md"), markdown=True)
    d.out.with_suffix(".md").write_text(md)
    page = publicize(d.html(), d.out.with_suffix(".html"))
    d.out.with_suffix(".html").write_text(page)
    words = len(re.sub(r"!\[.*?\]\(.*?\)|```.*?```|\|[^\n]*\||[#*>`-]", " ", md.split("\n## Sources")[0].split("\n## References")[0], flags=re.S).split())
    info = {"track": track, "words_prose": words, "figures": d.nfig, "html_kb": len(page) // 1024}
    if pdf:
        out = d.out.with_suffix(".pdf")
        prn = d.out.with_name(d.out.name + ".print.html")   # Chrome turns relative links into file:// links carrying the local path
        prn.write_text(printable(page))
        try:
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}", "--virtual-time-budget=15000",
                            prn.resolve().as_uri() + "?print=1"], capture_output=True, timeout=600)
        finally:
            prn.unlink(missing_ok=True)
        info.update(check_pdf(out))
    found = local_path_findings([d.out.with_suffix(s) for s in (".md", ".html", ".pdf") if d.out.with_suffix(s).exists()], ROOT, forbid=[Path.home()])
    if found:
        raise SystemExit(f"{track}: a local path reached a published file: " + "; ".join(f"{f['file']}:{f['line']} {f['kind']}" for f in found[:5]))
    print(info)
    return info


def printable(page: str) -> str:
    """The page as the PDF prints it: a relative link would become a file:// link to this machine, so in the PDF it is text.
    Public (https) links and in-page anchors stay links."""
    return re.sub(r'(<a\b[^>]*?)\s+href="(?!https?:|#|mailto:)[^"]*"', r"\1", page)


def main() -> None:
    args = sys.argv[1:]
    pdf = "--no-pdf" not in args
    tracks = [a for a in args if not a.startswith("--")] or list(TRACKS)
    facts, uses = load_facts(), {}
    report = [build(t, facts, uses, pdf) for t in tracks]
    if len(tracks) == len(TRACKS):
        (ROOT / "docs" / "evidence-uses.json").write_text(json.dumps(uses, indent=1, default=str))
        (ROOT / "docs" / "build-report.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
