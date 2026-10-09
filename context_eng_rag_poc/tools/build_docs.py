"""Build the S2 publications (Medium edition, technical deep dive, evidence documents) as Markdown, standalone HTML and PDF.

    uv run --project enterprise_knowledge_rag_poc --with markdown --with pypdf python tools/build_docs.py [all|medium|technical|report|real-vs-simulated] [--strict]

Ported from R1+R2 (evals_obs_reliability/tools/build_docs.py), itself ported from T4, F3 and F2: same directives, same
evidence-kit 3.6.0 reading template (vendor/evidence_kit), same headless-Chrome print, same local-path scan (evidence-kit
5.2.0 publication.py, vendor/kit5), with the reader features of the series: a reading-progress bar, heading deep links,
copy-code buttons, light syntax highlighting, citation links with hover titles, series navigation, a back-to-top control.

Source: docs/source/<doc>.src.md, or docs/source/<doc>/*.md concatenated in name order.  The two editions (medium,
technical) are required; an evidence document (report, real-vs-simulated, and evidence if its source is ever written) is
skipped when its source is absent, and is then never linked.  Every measured number is a {{key}} token resolved from the
published run's facts.json (enterprise_knowledge_rag_poc/runs/<PUBLISHED>/facts.json, {"key": {"value": ..., "source": "..."}}),
plus docs/derived-facts.json when it exists.  An unknown key is a build failure; every use is recorded in
docs/evidence-uses.json.

Directives (one line each)
    ::: figure t06 | Caption | Alt text [| small|wide]   a figure (diagrams/premium/svg/t06.svg), numbered, with the
                                                         provenance and badges of diagrams/manifest.json
    ::: kind SIMULATED+IMPLEMENTED | basis               the evidence class of a section
    ::: claim Text                                       a pull quote
    ::: eyebrow Text                                     a small uppercase label announcing the next block
    ::: legend                                           the figures' colour grammar and provenance badges
    ::: evidencebar                                      links to the evidence documents and the technical edition
Blocks
    :::: callout kicker | href | link label              a short aside
Citations
    [[@a2a-spec]]                                        -> [[n]] from research/cite-keys.json (unknown key: failure)
    [[12]]                                               -> a link to reference [12] (HTML) or "[12]" (Markdown)

Figures not drawn yet: a missing SVG/PNG or manifest entry renders a visible "FIGURE PENDING: <key>" box (numbered like
the figure it stands for) and is listed in docs/build-report.json.  With --strict (publication builds) it is a failure.

Outputs: medium/enterprise-knowledge-rag-medium.{md,html,pdf}, technical/enterprise-knowledge-rag-technical.{md,html,pdf} and
results/enterprise-knowledge-rag-report.{md,html,pdf}.

Dropped from R1+R2: `::: proof` (a scenario explained by `recovery explain`; S2 has `s2_eval.cli explain` instead) and the
Evidence Check as a required document (R1+R2 builds its source from a pae-proof/v1 proof pack; here it is optional).
"""

from __future__ import annotations

import argparse
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
POC = ROOT / "enterprise_knowledge_rag_poc"
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
CODE = "S2"
SLUG = "enterprise-knowledge-rag"
TRACKS = {"medium": "Medium edition", "technical": "Technical deep dive"}
# Evidence documents: built from the same run and the same pipeline, published under results/, skipped without a source.
RESULTS = {"report": "Run report", "real-vs-simulated": "Real vs simulated"}
OPTIONAL = {"evidence": "Evidence Check"}   # R1+R2's claim -> proof page; only if docs/source/evidence.src.md is written
ALL = {**TRACKS, **RESULTS, **OPTIONAL}
STRICT = False   # --strict: a missing figure is a failure, not a placeholder
TOKEN = re.compile(r"\{\{([A-Za-z0-9_.@\-]+)\}\}")
DIRECTIVE = re.compile(r"^::: (\w+)(?: (.*))?$", re.M)
BLOCK = re.compile(r"^:::: (\w+)(?: ([^\n]*))?\n(.*?)\n::::$", re.M | re.S)
CITE = re.compile(r"\[\[(\d+)\]\]")
CITEKEY = re.compile(r"\[\[@([\w.-]+)\]\]")
KIND = {"MEASURED": "Measured", "RECORDED": "Recorded", "REASONED": "Reasoned", "ARCHITECTURE": "Architecture", "SIMULATED": "Simulated",
        "IMPLEMENTED": "Implemented", "DERIVED": "Derived", "SOURCED": "Sourced", "SYNTHESIS": "Our synthesis", "LIMITATION": "Limitation"}
medium.KINDS.update(KIND)

# Series navigation: real local paths only.  A missing target is a build failure, never a broken link.  The "Current"
# entry is this article: it is not linked from itself, and its path must be this build's Medium edition.
SERIES = [
    ("Foundation", "F1 · MCP Tool Sprawl", "Your AI agent has 500 MCP tools. Now what?", "tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html"),
    ("Foundation", "F2 · Layered Architecture", "Your agent works in a demo. Why does it break in production?",
     "f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html"),
    ("Foundation", "F3 · Headless AI", "Your AI shouldn't live inside the UI", "headless_ai/medium/headless-ai-medium.html"),
    ("State", "S1 · Memory, Context & State", "Your agent remembers everything. That's a problem.", "memory_context_state/article/memory-context-state.html"),
    ("Trust", "T2 · Authorization & Policy", "What is this agent actually allowed to do?", "auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html"),
    ("Trust", "T3 · Human-in-the-Loop", "Authorized. Should it still act?", "human_in_the_loop/medium/human-in-the-loop-medium.html"),
    ("Trust", "T5 · Observability & Governance", "Your AI agent did something in production. Can you explain exactly what happened?",
     "governance_for_ai_agents/medium/observability-governance-medium.html"),
    ("Trust", "T4 · AI Control Plane", "Your agents shouldn't govern themselves", "ai_control_plane/medium/ai-control-plane-medium.html"),
    ("Trust", "T1 · Agent Identity", "Who is acting, and on whose authority?", "agent_identity/medium/agent-identity-medium.html"),
    ("Trust", "T6 · Agent, Tool & MCP Security", "Assume the context is hostile.", "securing_tools_mcp/medium/securing-agents-tools-mcp-medium.html"),
    ("Reliability", "R1 + R2 · Evals, Observability & Reliability", "“The agent failed” is not an operational signal.",
     "evals_obs_reliability/medium/evals-reliability-medium.html"),
    ("Capstone", "P1 · The Agent Is Not the Architecture", "The final reference architecture", "ai_architecture/medium/production-agentic-ai-platform-medium.html"),
    ("Coordination", "C1 · Multi-Agent & A2A", "Do you actually need multiple agents?", "multi_agent_a2a/medium/multi-agent-a2a-medium.html"),
    ("Operations", "O1 + O2 · Operating AI Agents at Scale", "Cost, latency, scale and lifecycle", "operating_ai_agents/medium/operating-ai-agents-medium.html"),
    ("Current", "S2 · Enterprise Knowledge & RAG", "Your agent found the right document. Why did it give the wrong answer?",
     "context_eng_rag/medium/enterprise-knowledge-rag-medium.html"),
]
START_HERE = "series-start-here/start-here/production-ai-engineering.html"
# The learning map's ready-to-paste Medium blocks for this note (series-start-here tools/build_map.py), used when present.
MAP_MEDIUM = "series-start-here/components/generated/S2-knowledge-medium.md"
# The figures' colour grammar (the series' eleven colours) and provenance badges, for ::: legend.  Revise the meanings
# with the S2 figures (the legend frame).
LEGEND_SWATCHES = [("#334155", "slate", "the request and its identity"), ("#D97706", "orange", "workflow, owners, escalation"),
                   ("#4551C9", "indigo", "the model: probabilistic"), ("#B5487F", "magenta", "retrieval, candidates, the packet"),
                   ("#5B6B82", "grey", "source systems (simulated)"), ("#2F6FDE", "blue", "deterministic gates"),
                   ("#6D5BD0", "purple", "verification"), ("#172B4D", "navy", "evidence"), ("#D14D63", "red", "invalid, excluded, wrong"),
                   ("#1F9D74", "green", "admitted, supported")]
LEGEND_BADGES = [("ARCHITECTURE", "conceptual design"), ("MEASURED", "a recorded POC result"), ("RECORDED", "one recorded run"),
                 ("PROPOSED", "not built")]


def source_files(doc: str) -> list[Path]:
    """docs/source/<doc>/*.md in name order, else [docs/source/<doc>.src.md], else [] (no source)."""
    folder = ROOT / "docs" / "source" / doc
    parts = sorted(folder.glob("*.md")) if folder.is_dir() else []
    single = ROOT / "docs" / "source" / f"{doc}.src.md"
    return parts or ([single] if single.exists() else [])


def available(doc: str) -> bool:
    return bool(source_files(doc))


def companion(track: str) -> list[tuple[str, str]]:
    """(label, path without extension, relative to any output folder) of the evidence document shown next to the editions:
    the Evidence Check if written, else Real vs simulated, else the Run report."""
    for r in ("evidence", "real-vs-simulated", "report"):
        if r != track and available(r):
            return [(ALL[r], f"../results/{SLUG}-{r}")]
    return []


def evidence_links() -> list[tuple[str, str, str]]:
    """The evidence bar (paths relative to medium/ and technical/): only documents that exist or are built from a source."""
    out = []
    if (ROOT / "results" / "lab-console.html").exists():
        out.append(("Lab Console", "Explore every run", "../results/lab-console.html"))
    for r, d in (("evidence", "Claim → proof"), ("report", "Every case, every experiment"), ("real-vs-simulated", "What was actually run")):
        if available(r):
            out.append((ALL[r], d, f"../results/{SLUG}-{r}.html"))
    return out + [("Technical deep dive", "The full architecture", f"../technical/{SLUG}-technical.html")]


def published_run() -> Path:
    pointer = POC / "runs" / "PUBLISHED"
    if not pointer.exists():
        raise SystemExit("no published run: enterprise_knowledge_rag_poc/runs/PUBLISHED (a file holding a run id) is missing")
    run = POC / "runs" / pointer.read_text().strip()
    if not (run / "facts.json").exists():
        raise SystemExit(f"published run {run.name} has no facts.json")
    return run


def load_facts() -> dict:
    """The run's facts.json, plus docs/derived-facts.json if it exists: both computed from the run, never typed."""
    facts = json.loads((published_run() / "facts.json").read_text())
    dp = ROOT / "docs" / "derived-facts.json"
    derived = json.loads(dp.read_text()) if dp.exists() else {}
    clash = set(facts) & set(derived)
    if clash:
        raise SystemExit(f"fact defined twice: {sorted(clash)}")
    out = {**facts, **derived}
    bad = [k for k, v in out.items() if not (isinstance(v, dict) and "value" in v and "source" in v)]
    if bad:
        raise SystemExit(f"facts without {{value, source}}: {sorted(bad)[:10]}")
    return out


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


def cite_table() -> dict[str, dict]:
    """research/cite-keys.json (written by tools/build_references.py): key -> {n, title, url, ...}.  The R1+R2 shape,
    key -> n, is accepted too."""
    raw = json.loads((ROOT / "research" / "cite-keys.json").read_text())
    return {k: (v if isinstance(v, dict) else {"n": v, "title": ""}) for k, v in raw.items()}


def cite_keys(src: str, doc: str) -> str:
    """[[@rfc8693]] -> [[9]], from research/cite-keys.json; an unknown key is a build failure."""
    keys = cite_table()

    def sub(m: re.Match) -> str:
        if m.group(1) not in keys:
            raise SystemExit(f"{doc}: unknown citation key [[@{m.group(1)}]]")
        return f"[[{keys[m.group(1)]['n']}]]"
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


def figure_manifest() -> dict:
    """diagrams/manifest.json's figures; {} until the manifest exists (every figure is then pending, or --strict fails)."""
    p = ROOT / "diagrams" / "manifest.json"
    return json.loads(p.read_text()).get("figures", {}) if p.exists() else {}


def references() -> dict[str, str]:
    """[n] -> title, from research/cite-keys.json, for citation hover titles."""
    return {str(v["n"]): v.get("title", "").replace("`", "") for v in cite_table().values()}


def map_medium_blocks() -> tuple[str, str]:
    """(TOP, END) of the learning map's generated Medium blocks for S2, or ("", "") until series-start-here generates them."""
    p = WS / MAP_MEDIUM
    if not p.exists():
        return "", ""
    text = p.read_text()
    top, _, end = text.partition("<!-- TOP -->")[2].partition("<!-- END -->")
    return top.strip(), end.strip()


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
.fig svg,.m-cover-art svg{cursor:zoom-in;width:100%;height:auto}
.fig-scroll{position:relative}
.fig-zoom{position:absolute;top:10px;right:10px;z-index:2;display:inline-flex;align-items:center;gap:6px;border:1px solid #D5DCE6;background:rgba(255,255,255,.94);
  color:#172B4D;border-radius:999px;padding:6px 11px;font:600 12.5px/1 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;cursor:pointer;opacity:0;transition:opacity .15s}
.fig-scroll:hover .fig-zoom,.fig-zoom:focus-visible{opacity:1}
.zoom{position:fixed;inset:0;background:rgba(10,16,30,.92);display:none;z-index:9999;overscroll-behavior:contain}
.zoom.on{display:block}
.zoom .zbar{position:absolute;top:0;left:0;right:0;height:52px;display:flex;align-items:center;gap:8px;padding:0 12px;color:#E6ECF5;
  font:500 13px/1.3 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;background:rgba(10,16,30,.6)}
.zoom .zt{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.85}
.zoom .zb{min-width:40px;height:36px;border-radius:9px;border:1px solid rgba(255,255,255,.22);background:rgba(255,255,255,.08);color:#fff;
  font:600 15px/1 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;cursor:pointer;padding:0 10px}
.zoom .zb:hover{background:rgba(255,255,255,.16)}
.zoom .zin{position:absolute;top:52px;left:0;right:0;bottom:30px;overflow:auto;-webkit-overflow-scrolling:touch;touch-action:pan-x pan-y;cursor:grab}
.zoom .zin.drag{cursor:grabbing}
.zoom .zc{margin:12px auto;background:#fff;border-radius:10px;padding:8px;box-sizing:content-box}
.zoom .zc svg{display:block;width:100%;height:auto;cursor:inherit}
.zoom .zhint{position:absolute;left:0;right:0;bottom:6px;margin:0;text-align:center;color:#9AA8BD;font:400 12px/1.3 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif}
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
.hai-pending{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;min-height:220px;padding:24px;box-sizing:border-box;
  border:3px dashed #D97706;border-radius:12px;background:#FFF7E0;color:#92400E;text-align:center;font-family:ui-monospace,'SF Mono',Menlo,monospace}
.hai-pending b{font-size:18px;letter-spacing:.06em}.hai-pending span{font:400 13.5px/1.45 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#7C5A1A;max-width:60ch}
.hai-badge.PENDING{color:#A16207;border-color:#A16207;background:#FEF6D8}
.fig-scroll{max-width:100%}
@media (min-width:729px){.m-body figure.fig.fig-sm{width:min(640px, calc(100vw - var(--navw) - 48px))}}
@media (max-width:640px){.hai-series ol{grid-template-columns:1fr}.hai-copy{padding:5px 7px}
  .fig-zoom{opacity:1;top:6px;right:6px;padding:5px 9px;font-size:12px}
  .fig figcaption::before{content:"Tap the figure to zoom: pinch and drag to read it at full size.";display:block;font-size:12px;color:#8494AA;margin-bottom:4px}}
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
@media (max-width:728px){.hai-evbar ul{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
.hai-score{margin:2.4em 0 0;padding:18px 18px 16px;border:1px solid #E3E8EF;border-radius:16px;background:linear-gradient(180deg,#F8FAFD 0,#fff 70%);
  font-family:sohne,'Helvetica Neue',Helvetica,Arial,sans-serif}
.hai-score .sc-h{margin:0 0 14px!important;font:700 12px/1.4 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif!important;letter-spacing:.12em;text-transform:uppercase;color:#6D5BD0}
.hai-score ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.hai-score li{position:relative;margin:0;padding:14px 16px 13px 18px;border:1px solid #E3E8EF;border-radius:12px;background:#fff;--tone:#334155;--tbg:#EEF1F5}
.hai-score li::before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:4px;border-radius:0 4px 4px 0;background:var(--tone)}
.hai-score li.sc-good{--tone:#1F9D74;--tbg:#E6F6EF}.hai-score li.sc-cost{--tone:#C2410C;--tbg:#FFF1E6}
.hai-score .sc-lab{display:block;font:600 14.5px/1.3 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#172B4D}
.hai-score .sc-nums{display:flex;align-items:flex-end;gap:12px;margin-top:10px}
.hai-score .sc-n,.hai-score .sc-g{display:flex;flex-direction:column;gap:3px;font-variant-numeric:tabular-nums}
.hai-score i{font:500 10.5px/1 ui-monospace,'SF Mono',Menlo,monospace;letter-spacing:.08em;text-transform:uppercase;font-style:normal;color:#8494AA}
.hai-score .sc-n{font:600 22px/1 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#64748B}
.hai-score .sc-g{font:800 34px/1 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;color:var(--tone);letter-spacing:-.02em}
.hai-score .sc-arr{color:#A3AFC2;font-size:20px;padding-bottom:6px}
.hai-score .sc-note{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:10px;font:400 12.5px/1.35 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#64748B}
.hai-score .sc-note b{flex:none;font:700 10.5px/1 ui-monospace,'SF Mono',Menlo,monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--tone);
  background:var(--tbg);border-radius:999px;padding:5px 8px}
@media (max-width:560px){.hai-score ul{grid-template-columns:1fr}.hai-score{padding:14px 12px}}
.m-callout.t-amber{border-left-color:#D97706;background:#FFF8EB}.m-callout.t-amber .ck{color:#B45309}
.m-callout.t-purple{border-left-color:#6D5BD0;background:#F6F4FF}.m-callout.t-purple .ck{color:#5B4BC4}
.m-callout.t-red{border-left-color:#D14D63;background:#FFF3F5}.m-callout.t-red .ck{color:#B83A50}
.m-callout.t-slate{border-left-color:#334155;background:#F4F6F9}.m-callout.t-slate .ck{color:#334155}
.trk-medium .m-callout{border-left-width:4px;border-radius:0 12px 12px 0;padding:18px 22px 8px}
.trk-medium .m-callout .ck{font-size:11.5px;letter-spacing:.12em}
.trk-medium .m-body h2{font-size:27px;line-height:1.22;letter-spacing:-.022em;margin-top:2.3em}
.trk-medium .m-body h2::before{content:"";display:block;width:34px;height:3px;border-radius:2px;background:#B5487F;margin:0 0 16px}
.trk-medium .m-pull blockquote{box-shadow:none;border-left:4px solid #B5487F;padding:2px 0 2px 22px;margin:0;color:#172B4D;
  font:500 25px/1.42 var(--serif);letter-spacing:-.012em}
.trk-medium .m-body ol{list-style:none;padding-left:0;counter-reset:rule}
.trk-medium .m-body ol>li{counter-increment:rule;position:relative;margin-top:12px;padding:14px 18px 14px 62px;border:1px solid #E3E8EF;border-radius:12px;background:#fff}
.trk-medium .m-body ol>li::before{content:counter(rule);position:absolute;left:16px;top:14px;width:30px;height:30px;border-radius:50%;background:#172B4D;color:#fff;
  font:700 14px/30px sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;text-align:center}
.trk-medium figcaption{font-size:14.5px;line-height:1.5;color:#52637A}
@media (max-width:640px){.trk-medium .m-body h2{font-size:23px}.trk-medium .m-pull blockquote{font-size:21px;padding-left:16px}
  .trk-medium .m-body ol>li{padding:12px 14px 12px 54px}.trk-medium .m-body ol>li::before{left:12px}}
@media print{.hai-score,.trk-medium .m-body ol>li{break-inside:avoid;-webkit-print-color-adjust:exact;print-color-adjust:exact}.fig-zoom{display:none!important}}
@media print{.m-body figure.fig.fig-wide{width:auto!important}.hai-evbar,.hai-legend,details.hai-details{break-inside:avoid}.hai-evbar ul{grid-template-columns:repeat(4,minmax(0,1fr))}
  .m-body figure.fig.fig-sm{width:62%!important;margin-left:auto;margin-right:auto}.zoom,.hai-progress,.hai-top,.hai-copy,.hai-anchor{display:none!important}.fig{break-inside:avoid}.fig svg{max-height:228mm}
  .m-body h2,.m-body h3{break-after:avoid}pre,table,.m-callout,blockquote{break-inside:avoid}.hai-series{break-inside:avoid}
  a.hai-cite{color:inherit}.m-body pre{white-space:pre-wrap;overflow-wrap:anywhere}
  .hai-pending{break-inside:avoid;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
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
var z=document.createElement('div');z.className='zoom';z.setAttribute('role','dialog');z.setAttribute('aria-modal','true');z.setAttribute('aria-label','Enlarged figure');
z.innerHTML='<div class="zbar"><span class="zt"></span><button class="zb" type="button" data-z="out" aria-label="Zoom out">−</button><button class="zb" type="button" data-z="fit">Fit</button><button class="zb" type="button" data-z="one">1:1</button><button class="zb" type="button" data-z="in" aria-label="Zoom in">+</button><button class="zb" type="button" data-z="close" aria-label="Close">✕</button></div><div class="zin"><div class="zc"></div></div><p class="zhint">Drag to pan · pinch, + or − to zoom · Esc to close</p>';
document.body.appendChild(z);
var zin=z.querySelector('.zin'),zc=z.querySelector('.zc'),zt=z.querySelector('.zt'),native=1600,scale=1,last=null;
function fit(){return Math.min(1,(zin.clientWidth-40)/native);}
function setScale(k,cx,cy){var old=scale;scale=Math.max(fit()*0.9,Math.min(2.5,k));if(cx===undefined){cx=zin.clientWidth/2;cy=zin.clientHeight/2;}
var px=(zin.scrollLeft+cx)/old,py=(zin.scrollTop+cy)/old;zc.style.width=Math.round(native*scale)+'px';zin.scrollLeft=px*scale-cx;zin.scrollTop=py*scale-cy;}
function off(){if(!z.classList.contains('on'))return;z.classList.remove('on');zc.innerHTML='';document.documentElement.style.overflow='';if(last)last.focus();}
function open(s){last=s;var vb=s.viewBox&&s.viewBox.baseVal;native=(vb&&vb.width)||s.getBoundingClientRect().width||1600;
zc.innerHTML='';var c=s.cloneNode(true);c.removeAttribute('tabindex');zc.appendChild(c);
var fig=s.closest('figure');var cap=fig&&fig.querySelector('figcaption');var tx=cap?cap.textContent.replace(/\\s+/g,' '):'Figure';var fi=tx.indexOf('Figure ');zt.textContent=(fi>=0?tx.slice(fi):tx).slice(0,140);
z.classList.add('on');document.documentElement.style.overflow='hidden';
scale=window.innerWidth<760?Math.max(fit(),0.8):fit();zc.style.width=Math.round(native*scale)+'px';zin.scrollLeft=0;zin.scrollTop=0;
z.querySelector('[data-z="close"]').focus();}
z.querySelector('.zbar').addEventListener('click',function(e){var b=e.target.closest('[data-z]');if(!b)return;var k=b.getAttribute('data-z');
if(k==='close')off();else if(k==='in')setScale(scale*1.25);else if(k==='out')setScale(scale/1.25);else if(k==='fit')setScale(fit());else if(k==='one')setScale(1);});
zin.addEventListener('click',function(e){if(e.target===zin)off();});
document.addEventListener('keydown',function(e){if(!z.classList.contains('on'))return;if(e.key==='Escape')off();else if(e.key==='+'||e.key==='=')setScale(scale*1.25);else if(e.key==='-')setScale(scale/1.25);
else if(e.key==='Tab'){var f=[].slice.call(z.querySelectorAll('button'));var i=f.indexOf(document.activeElement);if(e.shiftKey&&i<=0){e.preventDefault();f[f.length-1].focus();}else if(!e.shiftKey&&i===f.length-1){e.preventDefault();f[0].focus();}}});
zin.addEventListener('wheel',function(e){if(!e.ctrlKey&&!e.metaKey)return;e.preventDefault();var r=zin.getBoundingClientRect();setScale(scale*(e.deltaY<0?1.12:1/1.12),e.clientX-r.left,e.clientY-r.top);},{passive:false});
var drag=null;zin.addEventListener('pointerdown',function(e){if(e.pointerType!=='mouse'||e.button!==0)return;drag={x:e.clientX,y:e.clientY,l:zin.scrollLeft,t:zin.scrollTop,moved:false};zin.classList.add('drag');});
window.addEventListener('pointermove',function(e){if(!drag)return;var dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3)drag.moved=true;zin.scrollLeft=drag.l-dx;zin.scrollTop=drag.t-dy;});
window.addEventListener('pointerup',function(){if(drag){zin.classList.remove('drag');drag=null;}});
var pinch=null;function dist(t){var a=t[0],b=t[1];return Math.hypot(a.clientX-b.clientX,a.clientY-b.clientY);}
zin.addEventListener('touchstart',function(e){if(e.touches.length===2){var r=zin.getBoundingClientRect();pinch={d:dist(e.touches),k:scale,
cx:(e.touches[0].clientX+e.touches[1].clientX)/2-r.left,cy:(e.touches[0].clientY+e.touches[1].clientY)/2-r.top};}},{passive:true});
zin.addEventListener('touchmove',function(e){if(pinch&&e.touches.length===2){e.preventDefault();setScale(pinch.k*dist(e.touches)/pinch.d,pinch.cx,pinch.cy);}},{passive:false});
zin.addEventListener('touchend',function(e){if(e.touches.length<2)pinch=null;});
var taps=0;zin.addEventListener('touchend',function(e){if(e.touches.length)return;taps++;setTimeout(function(){taps=0;},300);if(taps===2)setScale(Math.abs(scale-fit())<0.02?1:fit());});
document.querySelectorAll('.fig svg, .m-cover-art svg').forEach(function(s,i){s.setAttribute('tabindex','0');
s.addEventListener('click',function(){open(s);});s.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();open(s);}});
var host=s.closest('.fig-scroll');if(host){var b=document.createElement('button');b.type='button';b.className='fig-zoom';b.textContent='⤢ Zoom';
b.setAttribute('aria-label','Enlarge figure '+(i+1));b.addEventListener('click',function(e){e.stopPropagation();open(s);});host.appendChild(b);}});
})();
"""


def scorecard_row(line: str) -> dict:
    """`label | naive | governed | lower|higher | note` (numbers already substituted from facts)."""
    p = [x.strip() for x in line.split(" | ")]
    if len(p) != 5 or p[3] not in ("lower", "higher"):
        raise SystemExit(f"scorecard row needs 'label | naive | governed | lower|higher | note': {line!r}")
    first = lambda v: float(re.match(r"-?[\d.]+", v.replace(",", "")).group(0))
    a, b = first(p[1]), first(p[2])
    good = (b < a) if p[3] == "lower" else (b > a)
    return {"label": p[0], "naive": p[1], "governed": p[2], "note": p[4], "tone": "good" if good else ("same" if a == b else "cost")}


def scorecard_html(title: str, rows: list[dict]) -> str:
    """The Medium headline: one card per outcome, naive → governed, coloured by whether governance helped."""
    verdict = {"good": "better", "cost": "the cost", "same": "no change"}
    cards = "".join(
        f'<li class="sc-{r["tone"]}"><span class="sc-lab">{html.escape(r["label"])}</span>'
        f'<span class="sc-nums"><span class="sc-n"><i>naive</i>{html.escape(r["naive"])}</span><span class="sc-arr" aria-hidden="true">→</span>'
        f'<span class="sc-g"><i>governed</i>{html.escape(r["governed"])}</span></span>'
        f'<span class="sc-note">{html.escape(r["note"])}<b>{verdict[r["tone"]]}</b></span></li>' for r in rows)
    return f'<section class="hai-score" aria-label="{html.escape(title, quote=True)}"><p class="sc-h">{html.escape(title)}</p><ul>{cards}</ul></section>'


def callout_tone(kicker: str) -> str:
    """A callout's colour follows what it reports: a failure (amber), a limit of the checks (purple), a contract lesson (red)."""
    k = kicker.lower()
    if "fail" in k or "didn" in k:
        return "amber"
    if "verifier" in k:
        return "purple"
    if "contract" in k:
        return "red"
    return "slate"


class Doc:
    def __init__(self, track: str, facts: dict, uses: dict):
        self.track = track
        raw = "\n\n".join(p.read_text().strip() for p in source_files(track)) + "\n"
        refs_md = ROOT / "docs" / "source" / "technical" / "99-references.md"
        if track == "medium" and refs_md.exists():   # the Medium edition cites the same numbered sources as the technical edition
            raw = raw.rstrip() + "\n\n" + refs_md.read_text().replace("## References", "## Sources", 1)
        self.out = ROOT / (track if track in TRACKS else "results") / f"{SLUG}-{track}"
        self.meta, src = front_matter(raw)
        self.src = cite_keys(render_facts(src, facts, track, uses), track)
        self.meta = {k: render_facts(v, facts, track, uses) for k, v in self.meta.items()}
        self.figs = figure_manifest()
        self.refs = references()
        self.blocks: list[str] = []
        self.nfig = 0
        self.pending: set[str] = set()

    def others(self) -> list[tuple[str, str]]:
        """(label, path without extension) of the companion documents, relative to this document's folder."""
        eds = [(TRACKS[t], f"../{t}/{SLUG}-{t}") for t in TRACKS if t != self.track]
        return eds + companion(self.track)

    def figure_gaps(self, fid: str, need: str, manifest: bool = True) -> list[str]:
        """What figure `fid` lacks for this rendering (need: "svg" for HTML, "png" for Markdown).  --strict checks both files
        and fails; otherwise the figure is recorded as pending and drawn as a placeholder."""
        gaps = [f"diagrams/manifest.json entry {fid!r}"] if manifest and fid not in self.figs else []
        for ext in (("svg", "png") if STRICT else (need,)):
            if not (ROOT / "diagrams" / "premium" / ext / f"{fid}.{ext}").exists():
                gaps.append(f"diagrams/premium/{ext}/{fid}.{ext}")
        if gaps and STRICT:
            raise SystemExit(f"{self.track}: figure {fid!r} is missing {', '.join(gaps)} (--strict)")
        if gaps:
            self.pending.add(fid)
        return gaps

    # ---- Markdown edition --------------------------------------------------------------------------------------------
    def markdown(self) -> str:
        n = 0

        def fig(m: re.Match) -> str:
            nonlocal n
            kind, arg = m.group(1), (m.group(2) or "").strip()
            if kind == "figure":
                n += 1
                fid, cap, alt = [p.strip() for p in arg.split(" | ")][:3]
                if self.figure_gaps(fid, "png"):
                    return f"> **FIGURE PENDING: {fid}**\n>\n> *Figure {n}. {cap}*"
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
                return ("*How to read the figures.* " + " · ".join(f"{name}: {t}" for _, name, t in LEGEND_SWATCHES) + ". "
                        "Badges: " + " · ".join(f"`{b}` {t}" for b, t in LEGEND_BADGES) + ".")
            if kind == "evidencebar":
                return ("**Want to inspect the evidence?** " + " · ".join(f"[{t}]({h.replace('.html', '.md') if 'console' not in h else h}) ({d})"
                                                                          for t, d, h in evidence_links()))
            return m.group(0)

        def blk(m: re.Match) -> str:
            if m.group(1) == "scorecard":
                rows = [scorecard_row(l) for l in m.group(3).strip().splitlines() if l.strip()]
                return (f"**{(m.group(2) or '').strip().upper()}**\n\n"
                        + "\n".join(f"- **{r['label']}:** naive {r['naive']} → governed {r['governed']} ({r['note']})" for r in rows))
            head, href, label = ([x.strip() for x in (m.group(2) or "").split(" | ")] + ["", "", ""])[:3]
            body = "\n".join(f"> {l}" for l in m.group(3).strip().splitlines())
            link = f"\n>\n> [{label}]({href})" if href else ""
            return f"> **{head}**\n>\n{body}{link}"

        src = BLOCK.sub(blk, self.src)
        src = DIRECTIVE.sub(fig, src)
        src = CITE.sub(lambda m: f"[{m.group(1)}]", src)
        cover = ""
        if self.meta.get("cover"):
            cid = self.meta["cover"]
            cover = (f"> **FIGURE PENDING: {cid}**\n\n" if self.figure_gaps(cid, "png", manifest=False)
                     else f"![{self.meta.get('cover_alt', '')}](../diagrams/premium/png/{cid}.png)\n\n")
        top, end = map_medium_blocks() if self.track == "medium" else ("", "")
        head = (f"# {self.meta.get('title', '')}\n\n*{self.meta.get('subtitle', '')}*\n\n" + (f"{top}\n\n" if top else "") + cover +
                f"{self.meta.get('kicker', '')} · {ALL[self.track]} · {self.meta.get('filed', '')}\n\n")
        others = " · ".join(f"[{l}]({h}.md)" for l, h in self.others())
        series = " · ".join(f"[{name}](../../{pth})" for role, name, _, pth in SERIES if pth and role != "Current")
        current = next(name for role, name, _, _ in SERIES if role == "Current")
        tail = (f"\n\n---\n\n**Series.** {series} · Current: {current}. "
                f"Companions: {others}. Every measured number is substituted from "
                f"`enterprise_knowledge_rag_poc/runs/{published_run().name}/facts.json`.\n")
        return head + src.strip() + (f"\n\n{end}" if end else "") + tail

    # ---- HTML edition ------------------------------------------------------------------------------------------------
    def pending_box(self, fid: str, alt: str) -> str:
        return (f'<div class="hai-pending" role="img" aria-label="Figure pending: {html.escape(fid, quote=True)}">'
                f'<b>FIGURE PENDING: {html.escape(fid)}</b><span>{html.escape(alt)}</span></div>')

    def figure(self, arg: str, cover: bool = False) -> str:
        parts = [p.strip() for p in arg.split(" | ")]
        fid, cap, alt = parts[:3]
        opts = set(parts[3:])
        if self.figure_gaps(fid, "svg", manifest=not cover):
            if cover:
                return self.pending_box(fid, alt)
            self.nfig += 1
            return (f'<figure class="fig fig-pending" id="fig-{fid}">{self.pending_box(fid, alt)}<figcaption>'
                    f'<span class="hai-badge PENDING">PENDING</span>Figure {self.nfig}. {inline_md(cap)}</figcaption></figure>')
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
        elif kind == "eyebrow":
            out = f'<p class="hai-eyebrow">{html.escape(arg)}</p>'
        elif kind == "legend":
            out = ('<aside class="hai-legend" aria-label="How to read the figures"><b class="h">How to read the figures</b><ul>'
                   + "".join(f'<li><i style="background:{c}"></i>{html.escape(t)}</li>' for c, _, t in LEGEND_SWATCHES) + '</ul><ul>'
                   + "".join(f'<li><span class="hai-badge {b.split()[0]}">{b}</span>{html.escape(t)}</li>' for b, t in LEGEND_BADGES) + '</ul></aside>')
        elif kind == "evidencebar":
            out = ('<nav class="hai-evbar" aria-label="Inspect the evidence"><b class="h">Want to inspect the evidence?</b><ul>'
                   + "".join(f'<li><a href="{h}"><b>{html.escape(t)}</b><span>{html.escape(d)}</span></a></li>' for t, d, h in evidence_links())
                   + '</ul></nav>')
        else:
            raise SystemExit(f"{self.track}: unknown directive ::: {kind}")
        self.blocks.append(out)
        return f"\n\n@@BLOCK{len(self.blocks) - 1}@@\n\n"

    def block(self, m: re.Match) -> str:
        kind, arg, body = m.group(1), (m.group(2) or "").strip(), m.group(3)
        if kind == "scorecard":
            self.blocks.append(scorecard_html(arg, [scorecard_row(l) for l in body.strip().splitlines() if l.strip()]))
            return f"\n\n@@BLOCK{len(self.blocks) - 1}@@\n\n"
        parts = ([x.strip() for x in arg.split(" | ")] + ["", "", "", ""])[:4]
        if kind != "callout":
            raise SystemExit(f"{self.track}: unknown block :::: {kind}")
        out = medium.callout(parts[0], body, href=parts[1] or None, link=parts[2] or "Details")
        tone = parts[3] or callout_tone(parts[0])
        self.blocks.append(out.replace('class="m-callout"', f'class="m-callout t-{tone}"', 1))
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
        # A citation links to its reference entry on this page; a document without a reference list (an evidence document)
        # links to the technical edition's.  A cited number with no entry is a failure, never a dead anchor.
        has_refs = 'class="hai-ref"' in body
        base = "" if has_refs or self.track == "technical" else f"../technical/{SLUG}-technical.html"
        cited = set(CITE.findall(body))
        if base:   # the technical edition lists every key of cite-keys.json once 09-references.md is written
            refs_md = (ROOT / "docs" / "source" / "technical" / "99-references.md").exists()
            missing = sorted((n for n in cited if not refs_md or n not in self.refs), key=int)
        else:
            missing = sorted((n for n in cited if f'id="ref-{n}"' not in body), key=int)
        if missing:
            raise SystemExit(f"{self.track}: cited [{', '.join(missing)}] has no reference entry (run tools/build_references.py)")
        return CITE.sub(lambda m: (f'<a class="hai-cite" href="{base}#ref-{m.group(1)}" title="{html.escape(self.refs.get(m.group(1), ""), quote=True)}">'
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
            if role == "Current":
                if path != f"{ROOT.name}/medium/{SLUG}-medium.html":
                    raise SystemExit(f"series: the current entry's path {path} is not this build's Medium edition")
                inner = f"<b>{html.escape(name)}</b>"
            elif path:
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
        # reading time: what a reader sees by default, so a collapsed block is not counted
        words = len(re.sub(r"<details.*?</details>|<svg.*?</svg>|<[^>]+>", " ", body, flags=re.S).split())
        mins = max(1, math.ceil((words / 265 * 60 + sum(max(12 - i, 3) for i in range(self.nfig))) / 60))
        by = meta.get("byline", "")
        kicker = meta.get("kicker", "")
        others = self.others()
        other_links = "".join(f'<a href="{h}.html">{html.escape(l)}</a>' for l, h in others)
        run = published_run().name
        # Local links only to files that exist: the POC README is rendered by tools/build_readme.py once its template exists.
        poc = "../enterprise_knowledge_rag_poc/README.md" if (POC / "README.md").exists() else ""
        local = [(label, href) for label, href, f in
                 (("POC README", poc, POC / "README.md"), ("Run summary", f"../enterprise_knowledge_rag_poc/runs/{run}/summary.md", POC / "runs" / run / "summary.md"),
                  ("Lab Console", "../results/lab-console.html", ROOT / "results" / "lab-console.html"), ("QA report", "../QA.md", ROOT / "QA.md"))
                 if f.exists()]
        top = ('<header class="m-top"><a class="pub" href="#top">Production AI Engineering</a><nav aria-label="Edition">'
               '<button type="button" class="m-toc-btn" aria-expanded="false" aria-controls="m-nav">Contents</button>'
               f'{other_links.replace("<a ", '<a class="opt" ', 1)}' + (f'<a href="{poc}">POC</a>' if poc else "")
               + f'<a href="../../{START_HERE}">Start Here</a></nav></header>')
        byline = (f'<span class="m-avatar" aria-hidden="true">{CODE}</span><div><b>{html.escape(by)}</b>'
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
        # footer_note (optional front matter): what in the run is real and what is simulated, in the author's words.
        note = f" {inline_md(meta['footer_note'])}" if meta.get("footer_note") else ""
        end = ((f'<div class="m-tags">{"".join(f"<span>{html.escape(t)}</span>" for t in tags)}</div>' if tags else "")
               + self.series()
               + f'<footer class="m-end"><h3>{html.escape(by)}</h3><p>{html.escape(kicker)}. Every measured number here is substituted at build time from '
               f'<code>enterprise_knowledge_rag_poc/runs/{run}/facts.json</code>.{note} Figures carry their provenance.</p><div class="links">{other_links}'
               + "".join(f'<a href="{h}">{html.escape(l)}</a>' for l, h in local) + '</div></footer>')
        title = meta.get("title", self.track)
        footer = f"{title} · {ALL[self.track]}".replace('"', "'")
        print_css = ("@media print { @page { margin: 16mm 15mm 18mm; @bottom-left { content: \"" + footer + "\"; font: 400 7.5pt 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #6B6B6B; }"
                     " @bottom-right { content: counter(page) \" / \" counter(pages); font: 400 7.5pt 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #6B6B6B; } } }")
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>{html.escape(title)} · {ALL[self.track]}</title><meta name="description" content="{html.escape(meta.get("subtitle", ""), quote=True)}">'
                f'<meta name="author" content="{html.escape(by, quote=True)}"><meta name="generator" content="{CODE} build_docs · evidence-kit {KIT}">'
                f'<style>{skin_css("medium")}\n{EXTRA_CSS}\n{print_css}</style></head><body class="trk-{self.track}">{top}{cover}{self.nav(body)}'
                f'<div class="m-page"><article class="m-article" id="top">{head}<div class="m-body">{body}</div>{end}</article></div>'
                f'<script>{medium_js()}</script><script>{EXTRA_JS}</script></body></html>')


def check_pdf(pdf: Path) -> dict:
    from pypdf import PdfReader

    r = PdfReader(str(pdf))
    blank = [i + 1 for i, p in enumerate(r.pages) if len((p.extract_text() or "").strip()) < 5 and "/XObject" not in str(p.get("/Resources", ""))]
    links = sum(1 for p in r.pages for a in (p.get("/Annots") or []) if a.get_object().get("/Subtype") == "/Link")
    return {"pages": len(r.pages), "blank_pages": blank, "pdf_links": links}


def upload_list(d: "Doc") -> None:
    """medium/figures-for-medium.md: the PNG@2x of every figure in article order with its caption and alt text, for the
    manual Medium upload (Medium does not keep inline SVG, styles or scripts; the standalone HTML stays the richer edition)."""
    rows = ["# Figures for the Medium upload", "",
            "Upload in this order, in place, from `diagrams/premium/png/` (2x PNG). Paste each caption under its figure and the alt text into Medium's alt field.", ""]
    if d.meta.get("cover"):
        rows += [f"**Cover** · `diagrams/premium/png/{d.meta['cover']}.png`", "", f"Alt: {d.meta.get('cover_alt', '')}", ""]
    for i, m in enumerate(re.finditer(r"^::: figure (.+)$", d.src, re.M), 1):
        fid, cap, alt = [p.strip() for p in m.group(1).split(" | ")][:3]
        rows += [f"**Figure {i}** · `diagrams/premium/png/{fid}.png`", "", f"Caption: Figure {i}. {cap}", "", f"Alt: {alt}", ""]
    (ROOT / "medium" / "figures-for-medium.md").write_text("\n".join(rows))


def build(track: str, facts: dict, uses: dict) -> dict:
    d = Doc(track, facts, uses)
    d.out.parent.mkdir(parents=True, exist_ok=True)
    md = d.markdown()
    d.out.with_suffix(".md").write_text(md)
    page = d.html()
    d.out.with_suffix(".html").write_text(page)
    if track == "medium":
        upload_list(d)
    pdf = d.out.with_suffix(".pdf")
    # Chrome prints relative links as absolute file:// URLs, which would publish a local path.  Print a copy whose local
    # links are plain text (in-page anchors and web links stay live), as F3 and T3 do.
    printable = d.out.with_name(d.out.name + ".print.html")
    printable.write_text(re.sub(r'<a ([^>]*?)href="(?!https?:|#|mailto:)[^"]*"', r'<a \1', page))
    if not Path(CHROME).exists():
        raise SystemExit(f"Google Chrome not found at {CHROME}: it prints the PDF")
    pdf.unlink(missing_ok=True)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", "--virtual-time-budget=15000",
                    printable.resolve().as_uri() + "?print=1"], capture_output=True, timeout=600)
    printable.unlink()
    if not pdf.exists():
        raise SystemExit(f"{d.out.name}: Chrome wrote no PDF")
    leaks = local_path_findings([d.out.with_suffix(x) for x in (".md", ".html", ".pdf")], ROOT, forbid=[ROOT.parents[2], Path.home()])
    if leaks:
        raise SystemExit(f"{d.out.name}: local paths in the publication: {leaks[:5]}")
    words = len(re.sub(r"!\[.*?\]\(.*?\)|```.*?```|[#*>|`-]", " ", md, flags=re.S).split())
    info = {"track": track, "words_prose": words, "figures": d.nfig, "figures_pending": sorted(d.pending), "html_kb": len(page) // 1024, **check_pdf(pdf)}
    print(info)
    return info


def main() -> None:
    global STRICT
    ap = argparse.ArgumentParser(description="Build the S2 editions and evidence documents (Markdown, HTML, PDF).")
    ap.add_argument("docs", nargs="*", metavar="DOC", help=f"all (the default) or any of: {', '.join(ALL)}")
    ap.add_argument("--strict", action="store_true", help="a missing figure file or manifest entry fails the build (use for publication)")
    a = ap.parse_args()
    STRICT = a.strict
    unknown = [x for x in a.docs if x != "all" and x not in ALL]
    if unknown:
        ap.error(f"unknown document(s) {unknown}: use all or {', '.join(ALL)}")
    every = not a.docs or "all" in a.docs
    docs = []
    for t in (list(ALL) if every else a.docs):
        if available(t):
            docs.append(t)
        elif t in TRACKS or not every:   # an edition, or a document asked for by name, must have a source
            raise SystemExit(f"{t}: no source (docs/source/{t}.src.md or docs/source/{t}/*.md)")
        elif t not in OPTIONAL:
            print(f"{t}: skipped, no source (docs/source/{t}.src.md)")
    facts = load_facts()
    uses: dict = {}
    report = [build(t, facts, uses) for t in docs]
    if every:
        (ROOT / "docs" / "evidence-uses.json").write_text(json.dumps(uses, indent=1, default=str))
        (ROOT / "docs" / "build-report.json").write_text(json.dumps(report, indent=1))
    pending = sorted({f for r in report for f in r["figures_pending"]})
    if pending:
        print(f"FIGURES PENDING ({len(pending)}): {', '.join(pending)}: drawn as placeholders; --strict fails on them")


if __name__ == "__main__":
    main()
