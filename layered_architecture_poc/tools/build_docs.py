"""Build the three F2 publications (Medium, technical, learning) as Markdown, standalone HTML and PDF.

    python3 tools/build_docs.py                  (all three)    python3 tools/build_docs.py medium

Source: docs/source/<track>.src.md.  Every measured number is a {{fact.key}} token resolved from the published run's
facts.json (layered_architecture_poc/runs/<PUBLISHED>/facts.json).  An unknown key, or a number typed by hand where a token
belongs, is a build failure; every use is recorded in docs/evidence-uses.json.

Directives (one line each)
    ::: figure f06 | Caption | Alt text        an Excalidraw figure (diagrams/premium/svg/f06.svg), numbered, with provenance
    ::: kind MEASURED+RECORDED | basis         the evidence class of a section (evidence-kit label)
    ::: claim Text                             a pull quote
Blocks
    :::: callout kicker | href | link label    a short aside (paragraphs)
    :::: brief kicker | title | caption        problem: / test: / result: / limits: / meta: value | label  lines
    :::: boundary title | caption              supported: / qualified: / contradicted: / not_shown: lines

Outputs: docs/publish/<track>/layered-production-ai-architecture-<track>.{md,html,pdf}.  The .md is plain portable
Markdown (figures as PNG links, numbers resolved); the .html is one self-contained file (inline SVG, inline CSS/JS);
the .pdf is Chrome's print of that HTML.
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
POC = ROOT / "layered_architecture_poc"
sys.path.insert(0, str(ROOT / "vendor"))
from evidence_kit import __version__ as KIT, medium, medium_js, skin_css  # noqa: E402
from evidence_kit.components import md as inline_md  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TRACKS = {"medium": "Medium edition", "technical": "Technical documentation", "learning": "Architecture learning guide"}
SLUG = "layered-production-ai-architecture"
REPORT = "layered-agent-platform-run-report"
EVIDENCE = "layered-agent-platform-evidence-check"
RESULTS = {"report": REPORT, "evidence": EVIDENCE}
LABEL = {**TRACKS, "report": "Run report", "evidence": "Evidence check"}
TOKEN = re.compile(r"\{\{([A-Za-z0-9_.@\-]+)\}\}")
DIRECTIVE = re.compile(r"^::: (\w+)(?: (.*))?$", re.M)
BLOCK = re.compile(r"^:::: (\w+)(?: ([^\n]*))?\n(.*?)\n::::$", re.M | re.S)
medium.KINDS.update({"DERIVED": "Derived", "SETUP": "Setup · no results", "COUNTEREXAMPLE": "Counterexample", "REAL": "Real",
                     "SIMULATED": "Simulated", "POSTRUN": "Post-run verification"})
KIND = {"DERIVED": "Derived", "SETUP": "Setup · no results", "COUNTEREXAMPLE": "Counterexample", "REAL": "Real", "POSTRUN": "Post-run verification",
        "MEASURED": "Measured", "RECORDED": "Recorded", "REASONED": "Reasoned", "ARCHITECTURE": "Architecture", "SIMULATED": "simulated",
        "PROTOCOL": "Protocol", "LIMITATION": "Limitation", "IMPLEMENTED": "Implemented", "VERIFIED": "Verified"}


def published_run() -> Path:
    return POC / "runs" / (POC / "runs" / "PUBLISHED").read_text().strip()


def load_facts() -> dict:
    """The published facts, plus four derived namespaces so no document has to type these numbers either.

    facts.json is built before the run is verified, so the verifier's own counts cannot live in it without a
    circular dependency.  They are resolved here instead, in the same {value, source} shape:

        verify.*      runs/<id>/verification.json      the integrity and recomputation checks
        outcomes.*    runs/<id>/outcomes.json          scenario outcome classes and fault exposure
        accounting.*  verification/test_accounting.json  the four test numbers, reported separately
        bundle.*      dist/<id>-evidence.json          the packaged evidence bundle
    """
    run = published_run()
    facts = json.loads((run / "facts.json").read_text())

    def add(key: str, value, source: str) -> None:
        if value is not None:
            facts[key] = {"value": value, "source": source}

    verification = run / "verification.json"
    if verification.exists():
        v = json.loads(verification.read_text())
        for field in ("passed", "failed", "not_applicable", "total", "recomputed"):
            add(f"verify.{field}", v.get(field), f"runs/{run.name}/verification.json")

    outcomes = run / "outcomes.json"
    if outcomes.exists():
        o = json.loads(outcomes.read_text())
        for name, count in o.get("counts", {}).items():
            add(f"outcomes.{name.lower()}", count, f"runs/{run.name}/outcomes.json")
        add("outcomes.scenarios", len(o.get("scenarios", [])), f"runs/{run.name}/outcomes.json")
        for key, slot in o.get("exposure", {}).items():
            add(f"exposure.{key}.exposed", slot["exposed"], f"runs/{run.name}/outcomes.json")
            add(f"exposure.{key}.planned", slot["planned"], f"runs/{run.name}/outcomes.json")

    accounting = ROOT / "verification" / "test_accounting.json"
    if accounting.exists():
        a = json.loads(accounting.read_text())
        for block, prefix in (("during_the_cited_run", "cited_run"), ("current_repository_suite", "current"),
                              ("post_run_evidence_tests", "post_run"), ("run_verifier", "verifier")):
            for field, value in (a.get(block) or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    add(f"accounting.{prefix}.{field}", value, "verification/test_accounting.json")

    claims_file = POC / "docs" / "claims.yaml"
    if claims_file.exists():
        import yaml as _yaml
        claims = _yaml.safe_load(claims_file.read_text())["claims"]
        for status in ("SUPPORTED", "QUALIFIED", "CONTRADICTED", "UNSUPPORTED"):
            add(f"claims.{status.lower()}", sum(1 for c in claims if c["status"] == status),
                "layered_architecture_poc/docs/claims.yaml")
        add("claims.total", len(claims), "layered_architecture_poc/docs/claims.yaml")

    for bundle in sorted((ROOT / "dist").glob("*-evidence.json")):
        b = json.loads(bundle.read_text())
        for field in ("files", "bytes", "sha256"):
            add(f"bundle.{field}", b.get(field), f"dist/{bundle.name}")
        checked = b.get("verified_after_extraction") or {}
        add("bundle.verified_passed", checked.get("passed"), f"dist/{bundle.name}")
        add("bundle.verified_total", checked.get("total"), f"dist/{bundle.name}")
        break
    return facts


def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.1f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v):,}"
    if isinstance(v, int) and not isinstance(v, bool):
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
    return json.loads((ROOT / "diagrams" / "manifest.json").read_text())["figures"]


ZOOM_CSS = """
.fig svg{cursor:zoom-in}
.zoom{position:fixed;inset:0;background:rgba(15,23,42,.86);display:none;z-index:9999;overflow:auto;padding:24px}
.zoom.on{display:block}.zoom .zin{background:#fff;border-radius:12px;padding:12px;margin:0 auto;max-width:min(2400px,96vw)}
.zoom svg{width:100%;height:auto;cursor:zoom-out}.zoom .zx{position:fixed;top:14px;right:22px;color:#fff;font:600 15px/1 sans-serif;cursor:pointer}
.m-meta-strip{font:400 14px/1.5 sohne,'Helvetica Neue',Helvetica,Arial,sans-serif;color:#6B6B6B;margin:0 0 28px}
.m-kind .k-derived{background:var(--indigo-bg);color:var(--indigo);border-color:rgba(59,59,152,.25)}
.m-kind .k-setup{background:#fff;color:var(--text2);border-style:dashed}
.m-kind .k-counterexample{background:var(--red-bg);color:var(--red);border-color:rgba(190,40,60,.3)}
.m-kind .k-real{background:var(--blue-bg);color:var(--blue);border-color:rgba(28,93,174,.25)}
.m-kind .k-simulated{background:var(--wash);color:var(--text2)}
.m-kind .k-postrun{background:var(--green-bg);color:var(--green);border-color:rgba(43,122,75,.25)}
.ev-strip{display:grid;grid-template-columns:1fr auto 1fr;gap:14px;align-items:stretch;margin:28px 0;font-family:var(--sans)}
.ev-strip .c{border:1px solid var(--line2);border-top:3px solid var(--line2);border-radius:12px;padding:14px 16px;background:#fff}
.ev-strip .c.f1{border-top-color:var(--text2)}.ev-strip .c.f2{border-top-color:var(--blue)}
.ev-strip .c b{display:block;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--text2);margin-bottom:6px}
.ev-strip .c p{margin:0 0 6px!important;font:400 15px/1.45 var(--sans)!important}
.ev-strip .c .sc{font-size:13px!important;color:var(--text2)}
.ev-strip .ar{align-self:center;font:600 13px/1.3 var(--sans);color:var(--text2);text-align:center;max-width:120px}
.ev-two{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:22px 0;font-family:var(--sans)}
.ev-two .c{border:1px solid var(--line2);border-radius:12px;padding:12px 16px;background:#fff}
.ev-two .c b{display:block;font-size:12px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px}
.ev-two .c.real b{color:var(--blue)}.ev-two .c.sim b{color:var(--text2)}.ev-two .c.ctl b{color:var(--red)}.ev-two .c.trt b{color:var(--blue)}
.ev-two ul{margin:0;padding-left:18px}.ev-two li{font:400 14px/1.5 var(--sans)!important;margin:0!important}
.ev-kv{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:var(--line2);border:1px solid var(--line2);border-radius:12px;overflow:hidden;margin:18px 0;font-family:var(--sans)}
.ev-kv>div{background:#fff;padding:10px 14px;min-width:0}.ev-kv>div:last-child:nth-child(odd){grid-column:1/-1}
.ev-kv span{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--text2);margin-bottom:2px}
.ev-kv b{font-weight:600;font-size:14.5px;line-height:1.4;overflow-wrap:anywhere}.ev-kv code{font-size:13px}
.ev-own{font:400 14px/1.45 var(--sans)!important;border-left:3px solid var(--blue);padding:6px 12px!important;background:var(--bg2,#f6f8fb);border-radius:0 8px 8px 0;margin:14px 0!important}
.ev-own span{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--text2)}
.ev-design{margin:24px 0;padding:18px;border:1px dashed var(--line2);border-radius:14px;font-family:var(--sans);background:#fff}
.ev-design .ev-tag{margin:0 0 12px!important;font:700 11px/1 var(--sans)!important;letter-spacing:.1em;color:var(--text2);text-align:center}
.ev-same{border:1px solid var(--line2);border-radius:10px;padding:12px;text-align:center}
.ev-same b{display:block;font-size:16px}.ev-same span{font-size:13.5px;color:var(--text2)}
.ev-fork{display:grid;grid-template-columns:1fr 1fr;height:18px}.ev-fork i{border-right:2px solid var(--line2)}.ev-fork i+i{border-right:0;border-left:2px solid var(--line2)}
.ev-arms{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.ev-arms>div{min-width:0}.ev-arms small{overflow-wrap:anywhere}
.ev-arms>div{border:1px solid var(--line2);border-radius:10px;padding:10px;text-align:center;font-weight:600}
.ev-arms .m{border-top:3px solid var(--red)}.ev-arms .l{border-top:3px solid var(--blue)}
.ev-arms small{display:block;font-weight:400;font-size:12px;color:var(--text2);font-family:var(--mono,monospace)}
.ev-exps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;list-style:none;padding:0!important;margin:14px 0 8px!important}
.ev-exps li{margin:0!important;font:400 13px/1.35 var(--sans)!important;border:1px solid var(--line2);border-radius:8px;padding:6px 8px}
.ev-exps b{margin-right:6px}
.ev-design figcaption{font-size:12.5px;color:var(--text2);text-align:center}
dl.ev-dl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px 14px;margin:8px 0;font:400 14px/1.45 var(--sans)}
dl.ev-dl dt{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--text2);white-space:nowrap;padding-top:2px}
dl.ev-dl dd{margin:0;overflow-wrap:anywhere}
@media (max-width:640px){.ev-kv{grid-template-columns:1fr}.ev-exps{grid-template-columns:1fr 1fr}dl.ev-dl{grid-template-columns:1fr}dl.ev-dl dt{padding-top:6px}}
.ev-scen{font-family:var(--sans);margin:18px 0}
.ev-scen table{width:100%;border-collapse:collapse;font-size:13.5px}
.ev-scen th{font:600 11.5px/1.3 var(--sans);letter-spacing:.07em;text-transform:uppercase;color:var(--text2);text-align:left;padding:6px 8px;border-bottom:1px solid var(--line2)}
.ev-scen td{padding:8px;border-bottom:1px solid var(--line);vertical-align:top;line-height:1.4}
.ev-scen .exp td{background:var(--wash);font-weight:600;border-top:1px solid var(--line2)}
.ev-scen .exp td span{font-weight:400;color:var(--text2);margin-left:8px}
.ev-scen .o{display:flex;gap:8px;align-items:flex-start}
.ev-scen .i{flex:0 0 22px;height:22px;border-radius:6px;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:13px}
.ev-scen .ok .i{background:var(--green-bg);color:var(--green)}.ev-scen .bad .i{background:var(--red-bg);color:var(--red)}.ev-scen .na .i{background:var(--wash);color:var(--text2)}
.ev-scen .o small{display:block;color:var(--text2);font-size:12px}
.ev-scen .sum{display:flex;flex-wrap:wrap;gap:10px 22px;margin:0 0 10px;font-size:14px}
.ev-scen .sum b{font-size:18px;margin-right:4px}
details.ev-d{border:1px solid var(--line2);border-radius:10px;padding:10px 14px;margin:16px 0;font-family:var(--sans);background:#fff}
details.ev-d>summary{cursor:pointer;font:600 14px/1.4 var(--sans)}
details.ev-d table{font-size:13px}
.ev-comp{display:grid;grid-template-columns:1fr 1fr;gap:12px;font-family:var(--sans);margin:18px 0}
.ev-comp .c{border:1px solid var(--line2);border-radius:12px;padding:12px 16px}
.ev-comp .c.m{border-top:3px solid var(--red)}.ev-comp .c.l{border-top:3px solid var(--blue)}
.ev-comp .c b{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--text2)}
.ev-comp dl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 14px;margin:8px 0 0;font-size:14px}.ev-comp dt{white-space:nowrap}.ev-comp dd{margin:0;font-weight:600;text-align:right;overflow-wrap:anywhere}
@media (max-width:720px){.ev-strip,.ev-two,.ev-comp{grid-template-columns:1fr}.ev-strip .ar{max-width:none}.ev-scen table{font-size:12.5px}}
@media print{details.ev-d{break-inside:avoid}details.ev-d:not([open])>*:not(summary){display:none}}
@media print{.zoom{display:none!important}.fig{break-inside:avoid}.fig svg{max-height:235mm}}
"""
ZOOM_JS = """
(function(){var z=document.createElement('div');z.className='zoom';z.innerHTML='<span class="zx">close ✕</span><div class="zin"></div>';
document.body.appendChild(z);function off(){z.classList.remove('on');z.querySelector('.zin').innerHTML='';}
z.addEventListener('click',off);document.addEventListener('keydown',function(e){if(e.key==='Escape')off();});
document.querySelectorAll('.fig svg').forEach(function(s){s.addEventListener('click',function(){var c=s.cloneNode(true);
z.querySelector('.zin').appendChild(c);z.classList.add('on');});});})();
"""


class Doc:
    def __init__(self, track: str, facts: dict, uses: dict):
        self.track = track
        self.src_path = ROOT / "docs" / "source" / f"{track}.src.md"
        self.out = (ROOT / "docs" / "results" / RESULTS[track] if track in RESULTS else ROOT / "docs" / "publish" / track / f"{SLUG}-{track}")
        pj = ROOT / "docs" / "source" / f"{track}.panels.json"
        self.panels = json.loads(render_facts(pj.read_text(), facts, track, uses)) if pj.exists() else {}
        self.meta, src = front_matter(self.src_path.read_text())
        self.src = render_facts(src, facts, track, uses)
        self.meta = {k: render_facts(v, facts, track, uses) for k, v in self.meta.items()}
        self.figs = figure_manifest()
        self.blocks: list[str] = []
        self.nfig = 0
        self.fig_numbers: dict[str, int] = {}
        self.rel_root = "../../" if track in RESULTS else "../../../"

    # ---- Markdown edition --------------------------------------------------------------------------------------------
    def markdown(self) -> str:
        n = 0

        def fig(m: re.Match) -> str:
            nonlocal n
            kind, arg = m.group(1), (m.group(2) or "").strip()
            if kind == "figure":
                n += 1
                fid, cap, alt = [p.strip() for p in arg.split(" | ")][:3]
                prov = self.figs[fid]["provenance"]
                return f"![{alt}]({self.rel_root}diagrams/premium/png/{fid}.png)\n\n*Figure {n}. {cap}* · {prov}"
            if kind == "kind":
                kinds, _, text = arg.partition(" | ")
                return f"*{' · '.join(KIND.get(k, k.title()) for k in kinds.split('+'))}: {text}*"
            if kind == "claim":
                return f"> **{arg}**"
            if kind == "html":
                return self.panels[arg]["md"]
            return m.group(0)

        def blk(m: re.Match) -> str:
            kind, arg, body = m.group(1), (m.group(2) or "").strip(), m.group(3)
            head = arg.split(" | ")[0]
            if kind == "brief":
                lines = [f"**{head}**", ""]
                for line in body.strip().splitlines():
                    k, _, v = line.partition(": ")
                    if k.strip() == "meta":
                        val, _, lbl = v.partition(" | ")
                        lines.append(f"- {lbl.strip()}: **{val.strip()}**")
                    else:
                        lines.append(f"- **{k.strip().title()}.** {v.strip()}")
                return "\n".join(lines)
            if kind == "boundary":
                labels = {"supported": "Supported by the evidence", "qualified": "Qualified",
                          "contradicted": "Contradicted", "not_shown": "Not tested by this POC",
                          "unsupported": "Not tested by this POC"}
                out = [f"**{head}**", ""]
                for line in body.strip().splitlines():
                    k, _, v = line.partition(": ")
                    out.append(f"- *{labels.get(k.strip(), k)}:* {v.strip()}")
                return "\n".join(out)
            return f"> **{head}**\n>\n" + "\n".join(f"> {l}" for l in body.strip().splitlines())

        src = BLOCK.sub(blk, self.src)
        src = DIRECTIVE.sub(fig, src)
        head = f"# {self.meta.get('title', '')}\n\n*{self.meta.get('subtitle', '')}*\n\n{self.meta.get('byline', '')} · {self.meta.get('kicker', '')}\n\n"
        return head + src.strip() + "\n"

    # ---- HTML edition ------------------------------------------------------------------------------------------------
    def figure(self, arg: str, cover: bool = False) -> str:
        fid, cap, alt = [p.strip() for p in arg.split(" | ")][:3]
        svg = (ROOT / "diagrams" / "premium" / "svg" / f"{fid}.svg").read_text()
        svg = own_fonts(re.sub(r"<\?xml[^>]*>", "", svg).strip(), f"{self.track}{fid}")
        svg = svg.replace("<svg ", f'<svg role="img" aria-label="{html.escape(alt, quote=True)}" ', 1)
        if cover:
            return svg
        self.nfig += 1
        self.fig_numbers[fid] = self.nfig
        prov = self.figs[fid]["provenance"]
        return (f'<figure class="fig" id="fig-{fid}">{svg}<figcaption>Figure {self.nfig}. {inline_md(cap)}'
                f'<span class="src">{html.escape(prov)}</span></figcaption></figure>')

    def directive(self, m: re.Match) -> str:
        kind, arg = m.group(1), (m.group(2) or "").strip()
        if kind == "figure":
            out = self.figure(arg)
        elif kind == "kind":
            kinds, _, text = arg.partition(" | ")
            out = medium.kind(kinds.split("+"), text)
        elif kind == "claim":
            out = medium.claim(arg)
        elif kind == "html":
            out = self.panels[arg]["html"]
        else:
            raise SystemExit(f"{self.track}: unknown directive ::: {kind}")
        self.blocks.append(out)
        return f"\n\n@@BLOCK{len(self.blocks) - 1}@@\n\n"

    def block(self, m: re.Match) -> str:
        kind, arg, body = m.group(1), (m.group(2) or "").strip(), m.group(3)
        parts = ([x.strip() for x in arg.split(" | ")] + ["", "", ""])[:3]
        if kind == "callout":
            out = medium.callout(parts[0], body, href=parts[1] or None, link=parts[2] or "Details")
        elif kind == "brief":
            rows, meta = [], []
            for line in body.strip().splitlines():
                k, _, v = line.partition(": ")
                if k.strip() == "meta":
                    val, _, lbl = v.partition(" | ")
                    meta.append((val.strip(), lbl.strip()))
                elif k.strip():
                    rows.append((k.strip().title(), v.strip()))
            out = medium.brief(rows, meta, title=parts[1], kicker=parts[0], caption=parts[2])
        elif kind == "boundary":
            b: dict[str, list[str]] = {}
            for line in body.strip().splitlines():
                k, _, v = line.partition(": ")
                b.setdefault(k.strip(), []).append(v.strip())
            out = medium.boundary_panel(b, title=parts[0] or "Claim boundary", caption=parts[1])
        else:
            raise SystemExit(f"{self.track}: unknown block :::: {kind}")
        self.blocks.append(out)
        return f"\n\n@@BLOCK{len(self.blocks) - 1}@@\n\n"

    def body_html(self) -> str:
        src = BLOCK.sub(self.block, self.src)
        src = DIRECTIVE.sub(self.directive, src)
        body = markdown.markdown(src, extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"])
        body = re.sub(r"<table>.*?</table>", lambda m: f'<div class="table-wrap{" wide" if m.group(0).count("<th") >= 6 else ""}">{m.group(0)}</div>',
                      body, flags=re.S)
        for i, b in enumerate(self.blocks):
            ph = f"<p>@@BLOCK{i}@@</p>"
            if body.count(ph) != 1:
                raise SystemExit(f"{self.track}: block {i} did not survive markdown")
            body = body.replace(ph, b)
        return body

    def nav(self, body: str) -> str:
        items, cur = [], None
        for level, hid, text in re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>', body):
            label = html.unescape(re.sub(r"<[^>]+>", "", text))
            if level == "2":
                cur = [hid, label, []]
                items.append(cur)
            elif cur is not None and self.track != "technical":
                cur[2].append((hid, label))
        li = "".join(f'<li><a href="#{h}">{html.escape(t)}</a>' + (f'<ol>{"".join(f"<li><a href=#{s}>{html.escape(u)}</a></li>" for s, u in subs)}</ol>' if subs else "")
                     + "</li>" for h, t, subs in items)
        return (f'<nav class="m-nav" id="m-nav" aria-label="Sections"><div class="m-nav-h">In this document</div><ol>{li}</ol></nav>'
                '<div class="m-scrim"></div>')

    def html(self) -> str:
        meta = self.meta
        body = self.body_html()
        words = len(re.sub(r"<svg.*?</svg>|<[^>]+>", " ", body, flags=re.S).split())
        mins = max(1, math.ceil((words / 265 * 60 + sum(max(12 - i, 3) for i in range(self.nfig))) / 60))
        by = meta.get("byline", "")
        initials = "".join(w[0] for w in [w for w in by.split() if w[0].isalnum()][:2]).upper()
        kicker = meta.get("kicker", "")
        pub = "../publish/{t}/" if self.track in RESULTS else "../{t}/"
        others = [(t, pub.format(t=t) + f"{SLUG}-{t}.html") for t in TRACKS if t != self.track]
        res = "" if self.track in RESULTS else f"{self.rel_root}docs/results/"
        report = "#top" if self.track == "report" else f"{res}{REPORT}.html"
        evidence = "#top" if self.track == "evidence" else f"{res}{EVIDENCE}.html"
        console = f"{res}lab-console.html"
        links = "".join(f'<a class="opt" href="{h}">{TRACKS[t]}</a>' for t, h in others)
        top = ('<header class="m-top"><a class="pub" href="#top">Production AI Engineering</a><nav>'
               '<button type="button" class="m-toc-btn" aria-expanded="false" aria-controls="m-nav">Contents</button>'
               f'{links}<a href="{console}">Lab Console</a><a href="{evidence}">Evidence check</a><a href="{report}">Run report</a></nav></header>')
        byline = (f'<span class="m-avatar" aria-hidden="true">{html.escape(initials)}</span><div><b>{html.escape(by)}</b>'
                  f'{mins} min read · {html.escape(meta.get("filed", ""))}</div>')
        cover = ""
        if meta.get("cover"):
            art = self.figure(f"{meta['cover']} | cover | {meta.get('cover_alt', meta.get('title', ''))}", cover=True)
            cover = (f'<section class="m-cover" aria-label="Cover"><div class="m-cover-in"><div class="m-cover-top"><span>{html.escape(kicker)}</span>'
                     f'<span>{html.escape(meta.get("run", ""))}</span></div><h1>{html.escape(meta.get("title", ""))}</h1>'
                     f'<p class="m-cover-sub">{html.escape(meta.get("subtitle", ""))}</p><div class="m-cover-by">{byline}</div>'
                     f'<figure class="m-cover-art">{art}</figure>'
                     + (f'<p class="m-cover-cap">{inline_md(meta["cover_caption"])}</p>' if meta.get("cover_caption") else "") + "</div></section>")
        head = ('<header class="m-head">' + (f'<h1>{html.escape(meta.get("title", ""))}</h1><p class="m-sub">{html.escape(meta.get("subtitle", ""))}</p>'
                                              f'<div class="m-author">{byline}</div>' if not cover else "")
                + f'<div class="m-bar"><div><span>{html.escape(kicker)}</span></div><div>{links}<a href="{self.out.name}.pdf">PDF</a>'
                  f'<a href="{self.out.name}.md">Markdown</a></div></div></header>')
        tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
        run = published_run().name
        end = ((f'<div class="m-tags">{"".join(f"<span>{html.escape(t)}</span>" for t in tags)}</div>' if tags else "")
               + f'<footer class="m-end"><h3>Written by {html.escape(by)}</h3><p>{html.escape(kicker)}. Every measured number here is substituted '
               f'from <code>runs/{run}/facts.json</code>, generated from the recorded run\'s <code>summary.json</code>; figures carry their provenance.</p>'
               f'<div class="links"><a href="{console}">Lab Console (every run)</a><a href="{evidence}">Evidence check</a><a href="{report}">Run report</a>{links}'
               f'<a href="{self.rel_root}layered_architecture_poc/runs/{run}/summary.json">summary.json</a></div></footer>')
        title = meta.get("title", self.track)
        footer = f"{title} · {LABEL[self.track]}".replace('"', "'")
        print_css = ("@media print { @page { @bottom-left { content: \"" + footer + "\"; font: 400 7.5pt 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #6B6B6B; }"
                     " @bottom-right { content: counter(page) \" / \" counter(pages); font: 400 7.5pt 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #6B6B6B; } } }")
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>{html.escape(title)} · {LABEL[self.track]}</title><meta name="description" content="{html.escape(meta.get("subtitle", ""), quote=True)}">'
                f'<meta name="author" content="{html.escape(by, quote=True)}"><meta name="generator" content="F2 build_docs · evidence-kit {KIT}">'
                f'<style>{skin_css("medium")}\n{ZOOM_CSS}\n{print_css}</style></head><body>{top}{cover}{self.nav(body)}'
                f'<div class="m-page"><article class="m-article" id="top">{head}<div class="m-body">{body}</div>{end}</article></div>'
                f'<script>{medium_js()}</script><script>{ZOOM_JS}</script></body></html>')


def check_pdf(pdf: Path) -> dict:
    from pypdf import PdfReader

    r = PdfReader(str(pdf))
    blank = [i + 1 for i, p in enumerate(r.pages) if len((p.extract_text() or "").strip()) < 5 and "/XObject" not in str(p.get("/Resources", ""))]
    return {"pages": len(r.pages), "blank_pages": blank}


def build(track: str, facts: dict, uses: dict) -> dict:
    d = Doc(track, facts, uses)
    d.out.parent.mkdir(parents=True, exist_ok=True)
    md = d.markdown()
    d.out.with_suffix(".md").write_text(md)
    page = d.html()
    d.out.with_suffix(".html").write_text(page)
    pdf = d.out.with_suffix(".pdf")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", "--virtual-time-budget=15000",
                    d.out.with_suffix(".html").resolve().as_uri()], capture_output=True, timeout=600)
    words = len(re.sub(r"!\[.*?\]\(.*?\)|[#*>|`-]", " ", md).split())
    info = {"track": track, "words": words, "figures": d.nfig, "html_kb": len(page) // 1024, **check_pdf(pdf)}
    print(info)
    return info


def main() -> None:
    facts = load_facts()
    uses: dict = {}
    tracks = sys.argv[1:] or list(TRACKS)
    report = [build(t, facts, uses) for t in tracks]
    if len(tracks) == len(TRACKS):
        (ROOT / "docs" / "evidence-uses.json").write_text(json.dumps(uses, indent=1, default=str))
        (ROOT / "docs" / "publish" / "build-report.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
