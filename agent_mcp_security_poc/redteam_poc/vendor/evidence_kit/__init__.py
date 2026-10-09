"""evidence-kit 5: the evidence system of the Production AI Engineering learnings, and its Proof Contract v1.

    build(spec, data, facts, out)   a learning's spec (learning.toml: words, layout, claims) + what its adapter read from
                                    the recorded files (facts with provenance, rows, datasets, case tabs) → evidence.json
                                    and the Lab Console.  Copy binds numbers as {{fact}}; hand-typed numbers are refused.
    Facts                           the fact registry (evidence_kit.facts)
    blocks                          constructors for data-driven case tabs (evidence_kit.blocks)
    render_console(evidence, traces, out)   the Lab Console page itself (a learning may call it its Proof Lab: meta.lab)
    proof                           Proof Contract v1 (pae-proof/v1): checks over facts, claims tracing, results, SHA256SUMS,
                                    schema validation, hygiene scans, run comparison, the verification report
                                    (evidence_kit.proof; the contract and its schemas are in proof_contract/)
    skin_css("medium"), medium_js(), medium.*   the article template (Medium's reading system plus a section pane)

The kit knows no experiment: a learning brings an adapter (its row format) and a spec (its words and pages of view
primitives).  Pure standard library.  Learnings copy (vendor) a pinned version; nothing links across repositories.
"""

from __future__ import annotations

import base64
import gzip
import html
import json
import re
from pathlib import Path

from . import blocks, components, medium, proof  # noqa: F401  (re-exported)
from .components import esc, log_bars, md, pair_chart, rate_chart  # noqa: F401
from .facts import Facts, lint  # noqa: F401

__version__ = "5.2.0"
HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
FONTS = ASSETS / "fonts"


def tokens() -> dict:
    return json.loads((HERE / "tokens.json").read_text())


def tokens_css() -> str:
    """The colours that carry meaning (charts use them as var(--blue), var(--green) …)."""
    t = tokens()
    v = {}
    for k, m in t["meaning"].items():
        v[k], v[f"{k}-bg"] = m["hex"], m["bg"]
    return ":root{" + "".join(f"--{k}:{c};" for k, c in v.items()) + "}"


def fonts_css(which: tuple[str, ...] = ("serif", "code")) -> str:
    """@font-face rules with the woff2 files inlined (SIL OFL 1.1; licences in assets/fonts/)."""
    t = tokens()["type"]
    out = []
    for key in which:
        for fn, style, weight in t[key]["files"]:
            b64 = base64.b64encode((FONTS / fn).read_bytes()).decode()
            out.append(f"@font-face{{font-family:'{t[key]['family']}';font-style:{style};font-weight:{weight};font-display:swap;"
                       f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "\n".join(out)


def skin_css(skin: str) -> str:
    """"medium": the Medium reading template (Source Serif 4, sohne → Helvetica Neue, Source Code Pro; print rules inside).
    "console": the Lab Console (Inter, Source Code Pro)."""
    files = {"medium": ("serif", "code"), "console": ("ui", "code")}
    if skin not in files:
        raise ValueError(f"unknown skin {skin!r}: use 'medium' or 'console'")
    return "\n".join([tokens_css(), fonts_css(files[skin]), (ASSETS / f"{skin}.css").read_text()])


def medium_js() -> str:
    """The Medium template's script: section navigator and chart links into the Lab Console."""
    return (ASSETS / "medium.js").read_text()


def build(spec_path, data: dict, facts, out: Path, out_json: Path | None = None, generated_by: str = "") -> dict:
    """See evidence_kit.builder: spec + adapter data → evidence.json and the Lab Console."""
    from .builder import build as _build
    return _build(spec_path, data, facts, out, out_json, kit_version=__version__, generated_by=generated_by)


def render_console(evidence: dict, traces: dict | None, out: Path) -> dict:
    """The Lab Console: one self-contained HTML page (fonts, styles, script, data inline; no network)."""
    meta = evidence.get("meta", {})
    page = (ASSETS / "console.html").read_text()
    subs = {"@@TITLE@@": html.escape(f"{meta.get('id', '')} · {meta.get('lab', 'Lab Console')} · {meta.get('topic', '')}"),
            "@@DESC@@": html.escape(meta.get("question", "")), "@@KIT@@": __version__,
            "/*@@CSS@@*/": skin_css("console"), "/*@@JS@@*/": (ASSETS / "console.js").read_text()}
    for k, v in subs.items():
        page = page.replace(k, v)
    data = json.dumps(evidence, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    blob = base64.b64encode(gzip.compress(json.dumps(traces or {}, ensure_ascii=False, separators=(",", ":")).encode(), 9, mtime=0)).decode()
    page = page.replace("@@DATA@@", data).replace("@@TRACES@@", blob)  # data last: nothing in it can hit a placeholder
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return {"out": out, "bytes": len(page)}


def check_scoped(svg: str, scope: str) -> list[str]:
    """Style rules inside an inline SVG that are not scoped to #scope (inline SVG styles are page-global)."""
    m = re.search(r"<style>(.*?)</style>", svg, re.S)
    if not m:
        return []
    rules = [r.strip() for r in re.sub(r"@font-face\{[^}]*\}", "", m.group(1)).split("}") if r.strip()]
    return [r for r in rules if not r.startswith(f"#{scope}")]
