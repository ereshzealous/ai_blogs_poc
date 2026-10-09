"""Build the two T6 editions (Medium, Technical) and the results pages as Markdown, standalone HTML and PDF.

    uv run --project redteam_poc --with markdown --with pygments python tools/build_docs.py [medium|technical|evidence|all]

Every measured number is a {{token}} resolved from the published run's facts
(redteam_poc/evidence/runs/<published>/facts.json). An unknown token is a build failure. The HTML reuses the series'
Medium reading skin from the vendored evidence-kit (Source Serif 4, inlined fonts, print rules), so T6 reads like the
rest of the series. PDFs are printed by headless Chrome.

Directives (one line): ::: figure <key> | Caption | Alt     a numbered SVG figure from diagrams/svg/<key>.svg
                       ::: claim <text>                      a pull quote
Citations: [[12]] -> a link to reference [12].
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "redteam_poc"
SVG = ROOT / "diagrams" / "premium" / "svg"   # the series' Excalidraw-exported premium figures
sys.path.insert(0, str(POC / "vendor"))
from evidence_kit import skin_css, medium_js  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SLUG = "securing-agents-tools-mcp"
TOKEN = re.compile(r"\{\{([A-Za-z0-9_.\-]+)\}\}")
FIG = re.compile(r"^::: figure (\S+) \| ([^|]+?) \| (.+)$", re.M)
CLAIM = re.compile(r"^::: claim (.+)$", re.M)
CITE = re.compile(r"\[\[(\d+)\]\]")

TARGETS = {
    "medium":    ("medium",    f"{SLUG}-medium",    "Securing Agents, Tools & MCP", "Assume the context is hostile — a Production AI Engineering note"),
    "technical": ("technical", f"{SLUG}-technical", "Securing Agents, Tools & MCP — Technical Edition", "Threat model, red-team harness and evidence"),
    "evidence":  ("results",   f"{SLUG}-evidence",  "Securing Agents, Tools & MCP — Evidence", "Claims traced to experiments, checks and the recorded run"),
}

# Premium hero per edition: (kicker, h1, subtitle, byline-read, hero-figure-key, hero-caption).
HERO = {
    "medium": ("Production AI Engineering · T6 · Trust & Security",
               "Securing Agents, Tools & MCP",
               "Assume the context is hostile. A support agent reads a manipulated instruction and believes it — and the "
               "system stays safe anyway. {manip} of {n_attacks} attacks fool the model; deterministic gates contain all {n_attacks}.",
               "T6 · Production AI Engineering · ~14 min read",
               "boundary",
               "One model, five deterministic gates: a manipulated action is denied at the gate that owns it; legitimate work passes every gate."),
    "technical": ("Production AI Engineering · T6 · Technical edition",
                  "Securing Agents, Tools & MCP",
                  "Threat model, trust boundaries, a red-team assurance harness, {n_attacks} attacks across {n_classes} "
                  "classes, the ablation, and the claim boundary — model manipulated ≠ system compromised.",
                  "T6 · Production AI Engineering · ~28 min read",
                  "boundary",
                  "The deterministic gauntlet — five gates, each owning a class of attack; the model is manipulated, the system is not."),
    "evidence": ("Production AI Engineering · T6 · Evidence",
                 "The evidence, traced",
                 "Every claim mapped to an experiment, a check and the recorded run — reproduced byte for byte by "
                 "`redteam verify`.",
                 "T6 · Production AI Engineering · evidence",
                 "headline",
                 "Same manipulated model; the system is compromised {compA}, {compB} or {compC} of {n_attacks} times."),
}

# Cross-edition nav links (relative to each edition's folder).
NAV = {
    "medium": [("Technical edition", f"../technical/{SLUG}-technical.html"),
               ("Evidence", f"../results/{SLUG}-evidence.html"),
               ("Run report (PDF)", f"{SLUG}-medium.pdf")],
    "technical": [("Medium edition", f"../medium/{SLUG}-medium.html"),
                  ("Evidence", f"../results/{SLUG}-evidence.html"),
                  ("Markdown", f"{SLUG}-technical.md")],
    "evidence": [("Medium edition", f"../medium/{SLUG}-medium.html"),
                 ("Technical edition", f"../technical/{SLUG}-technical.html"),
                 ("PDF", f"{SLUG}-evidence.pdf")],
}


def published_run() -> Path:
    pub = POC / "evidence" / "published.json"
    rid = json.loads(pub.read_text())["published"]
    return POC / "evidence" / "runs" / rid


def flat_facts() -> dict[str, str]:
    run = published_run()
    f = json.loads((run / "facts.json").read_text())
    c = f["compromised"]
    ab = f["ablation"]
    t = {
        "n_scenarios": f["n_scenarios"], "n_attacks": f["n_attacks"], "n_controls": f["n_controls"],
        "n_classes": len(f["attack_classes"]), "manip": f["manipulated_attacks"],
        "compA": c["A"]["attacks"], "compB": c["B"]["attacks"], "compC": c["C"]["attacks"],
        "safeC": f["n_attacks"] - c["C"]["attacks"],
        "reg_alone": len(ab["standalone_stops"]["registry"]),
        "policy_alone": len(ab["standalone_stops"]["policy"]),
        "egress_alone": len(ab["standalone_stops"]["egress"]),
        "binding_alone": len(ab["standalone_stops"]["binding"]),
        "identity_alone": len(ab["standalone_stops"]["identity"]),
        "binding_sole": len(ab["per_control"]["binding"]),
        "binding_sole_list": ", ".join(ab["per_control"]["binding"]),
        "n_within": f.get("n_within", 0),
        "within_residual_C": f.get("within_residual", {}).get("C", 0),
        "within_compromised_C": f.get("within_compromised", {}).get("C", 0),
        "run_id": json.loads((POC / "evidence" / "published.json").read_text())["published"],
        "mcp_spec": "2026-07-28",
    }
    return {k: str(v) for k, v in t.items()}


FACTS = flat_facts()
USED: set[str] = set()


def subst(text: str) -> str:
    def repl(m):
        k = m.group(1)
        if k not in FACTS:
            raise SystemExit(f"build error: unknown fact token {{{{{k}}}}}")
        USED.add(k)
        return FACTS[k]
    return TOKEN.sub(repl, text)


KIND = re.compile(r"^::: kind (.+)$", re.M)
KLABEL = {"MEASURED": "k-measured", "RECORDED": "k-recorded", "VERIFIED": "k-verified",
          "IMPLEMENTED": "k-implemented", "ARCHITECTURE": "k-architecture", "REASONED": "k-architecture",
          "LIMITATION": "k-limitation", "CONTROL": "k-control", "SOURCED": "k-recorded", "SYNTHESIS": "k-architecture"}


def _kind(m):
    labels = [x.strip() for x in m.group(1).split("|")[0].split("+")]
    note = m.group(1).split("|", 1)[1].strip() if "|" in m.group(1) else ""
    chips = "".join(f'<span class="k {KLABEL.get(l.upper(), "k-architecture")}">{html.escape(l)}</span>' for l in labels)
    tail = f'<span class="k-note">{html.escape(note)}</span>' if note else ""
    return f'<p class="m-kind">{chips}{tail}</p>'


def preprocess_md(text: str) -> str:
    """Resolve tokens and lower our directives to Markdown/HTML before the markdown pass."""
    text = subst(text)
    figs = {"n": 0}

    def fig(m):
        figs["n"] += 1
        key, cap, alt = m.group(1), m.group(2).strip(), m.group(3).strip()
        svg = SVG / f"{key}.svg"
        inner = svg.read_text() if svg.exists() else f'<div class="fig-missing">[figure {key}]</div>'
        return (f'<figure class="fig" id="fig-{key}" role="img" aria-label="{html.escape(alt)}">'
                f'<div class="fig-scroll">{inner}</div>'
                f'<figcaption><b>Figure {figs["n"]}.</b> {html.escape(cap)}</figcaption></figure>')

    text = FIG.sub(fig, text)
    text = KIND.sub(_kind, text)
    text = CLAIM.sub(lambda m: f'<blockquote class="m-pull">{html.escape(m.group(1).strip())}</blockquote>', text)
    text = CITE.sub(lambda m: f'<a class="cite" href="#ref-{m.group(1)}">[{m.group(1)}]</a>', text)
    return text


def strip_front_matter(md: str) -> str:
    """Remove the leading H1, H2 and the italic byline line — they are rendered in the hero, not the body."""
    lines = md.splitlines()
    out, dropped = [], 0
    for ln in lines:
        if dropped < 3 and (ln.startswith("# ") or ln.startswith("## ") or
                            (ln.startswith("*") and ln.rstrip().endswith("*") and "Production AI Engineering" in ln)):
            dropped += 1
            continue
        out.append(ln)
    return "\n".join(out).lstrip("\n")


def hero_html(name: str) -> str:
    kicker, h1, sub, read, figkey, cap = HERO[name]
    sub = subst_braces(sub)
    cap = subst_braces(cap)
    svg = (SVG / f"{figkey}.svg")
    art = svg.read_text() if svg.exists() else ""
    links = "".join(f'<a class="opt" href="{href}">{html.escape(lab)}</a>' for lab, href in NAV[name])
    return (
        f'<header class="m-top"><a class="pub" href="#top">Production AI Engineering</a>'
        f'<nav>{links}</nav></header>'
        f'<section class="m-cover" aria-label="Cover"><div class="m-cover-in">'
        f'<div class="m-cover-top"><span>{html.escape(kicker)}</span>'
        f'<span>Recorded run {FACTS["run_id"]}</span></div>'
        f'<h1 id="top">{html.escape(h1)}</h1>'
        f'<p class="m-cover-sub">{html.escape(sub)}</p>'
        f'<div class="m-cover-by"><span class="m-avatar" aria-hidden="true">T6</span>'
        f'<div><b>{html.escape(read.split(" · ")[0])} · Production AI Engineering</b>'
        f'{html.escape(" · ".join(read.split(" · ")[1:]))}</div></div>'
        f'<figure class="m-cover-art">{art}'
        f'<figcaption class="m-cover-cap">{html.escape(cap)}</figcaption></figure>'
        f'</div></section>')


def subst_braces(s: str) -> str:
    """Resolve {token} (single-brace) in hero strings from the fact map."""
    def r(m):
        k = m.group(1)
        return FACTS.get(k, m.group(0))
    return re.sub(r"\{([A-Za-z0-9_]+)\}", r, s)


SHELL = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><meta name="description" content="{desc}">
<style>{css}
.m-body figure.fig{{margin:2.6rem 0;text-align:center;background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px 18px;box-shadow:0 6px 22px rgba(31,51,88,.06)}}
.m-body figure.fig svg{{max-width:100%;height:auto}}
.m-body figure.fig figcaption{{font-family:var(--sans);font-size:.8rem;color:#6b7280;margin-top:.8rem;line-height:1.5}}
.fig-scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
@media (max-width:700px){{
 /* keep dense diagrams legible on phones: scroll horizontally at a readable min-width instead of shrinking labels */
 .m-body figure.fig{{padding:14px 10px}}
 .m-body figure.fig .fig-scroll svg{{min-width:720px}}
 .m-body figure.fig figcaption{{font-size:.76rem}}
}}
.m-kind{{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:14px 0 0;font:500 12px/16px var(--sans)}}
.m-kind .k{{padding:3px 9px;border-radius:99px;letter-spacing:.07em;text-transform:uppercase;font-weight:600;border:1px solid var(--line);background:var(--wash)}}
.m-kind .k-measured,.m-kind .k-verified,.m-kind .k-control{{background:var(--green-bg);color:var(--green);border-color:rgba(43,122,75,.25)}}
.m-kind .k-recorded,.m-kind .k-implemented{{background:var(--blue-bg);color:var(--blue);border-color:rgba(28,93,174,.25)}}
.m-kind .k-architecture{{background:var(--indigo-bg);color:var(--indigo);border-color:rgba(59,59,152,.22)}}
.m-kind .k-limitation{{background:var(--amber-bg);color:var(--amber);border-color:rgba(168,116,18,.25)}}
.m-kind .k-note{{color:#6b7280;font-weight:400;text-transform:none;letter-spacing:0}}
.m-body blockquote.m-pull{{box-shadow:none;border-left:3px solid var(--indigo);font:600 clamp(20px,2vw,26px)/1.45 var(--sans);font-style:normal;color:#1f2a44;margin:2.2rem 0;padding:.1rem 0 .1rem 1.2rem}}
.cite{{text-decoration:none;color:var(--blue);font-size:.75em;vertical-align:super;padding:0 1px}}
</style></head><body>{hero}<div class="m-article"><div class="m-body">{body}</div></div><script>{js}</script></body></html>"""


REF = re.compile(r"^\*\*\[(\d+)\]\*\* (.+)$", re.M)   # whole entry line; parse the URL out separately
URL = re.compile(r"(https?://\S+)")
LOCALP = re.compile(r"local: `([^`]+)`")


def references_html(cited: set[str], collapsed: bool = False) -> str:
    """A References section with an #ref-N anchor for EVERY entry (so every [[n]] link resolves), parsed from
    research/sources.md. The first URL is linked; a series entry with only a `local:` path links to that path. Entries
    not cited in this edition are still anchored, so no citation can dangle."""
    src = (ROOT / "research" / "sources.md").read_text()
    items = []
    for m in REF.finditer(src):
        n, rest = m.group(1), m.group(2).strip()
        # the human-readable title is the text up to the first " — accessed" / " — SERIES" / URL / local marker
        title = re.split(r"\s+—\s+(?:accessed|https?://|resource page|PDF|SERIES|STANDARD|local:)", rest)[0].strip()
        um, lm = URL.search(rest), LOCALP.search(rest)
        if um:
            link = f'<a href="{html.escape(um.group(1).rstrip(" ;,"))}">source</a>'
        elif lm:
            link = f'<a href="../../{html.escape(lm.group(1))}">series article</a>'
        else:
            link = ""
        items.append(f'<li id="ref-{n}" value="{n}">{html.escape(title)}{(" · " + link) if link else ""}</li>')
    if not items:
        return ""
    body = ('<ol class="refs" style="font-family:var(--sans);font-size:.82rem;line-height:1.55;color:#4b5563">'
            + "".join(items) + "</ol>")
    note = ('<p style="font-family:var(--sans);font-size:.82rem;color:#6b7280">Each source is cited for the one passage '
            'it supports; verbatim quotes are in <code>research/sources.md</code>.</p>')
    if collapsed:
        return (f'<details class="refs-d"><summary style="font:700 20px/24px var(--sans);cursor:pointer;margin-top:1.9em">'
                f'References ({len(items)})</summary>{note}{body}</details>')
    return '<h2>References</h2>' + note + body


def to_html(name: str, title: str, desc: str, body_md: str) -> str:
    resolved = preprocess_md(strip_front_matter(body_md))
    cited = set(m.group(1) for m in re.finditer(r'href="#ref-(\d+)"', resolved))
    body = markdown.markdown(resolved, extensions=["tables", "fenced_code", "toc", "attr_list", "sane_lists"])
    body += references_html(cited, collapsed=(name == "medium"))   # Medium keeps the long list collapsed
    return SHELL.format(title=html.escape(title), desc=html.escape(desc), hero=hero_html(name),
                        css=skin_css("medium"), js=medium_js(), body=body)


def md_clean(name: str, text: str) -> str:
    """A portable Markdown deliverable: resolve tokens, turn directives into Markdown images/quotes, [[n]] into [n]."""
    text = subst(text)
    rel = "../diagrams/premium/svg"
    n = {"i": 0}

    def fig(m):
        n["i"] += 1
        key, cap, alt = m.group(1), m.group(2).strip(), m.group(3).strip()
        return f"![{alt}]({rel}/{key}.svg)\n\n*Figure {n['i']}. {cap}*"

    text = FIG.sub(fig, text)
    text = CLAIM.sub(lambda m: f"> **{m.group(1).strip()}**", text)
    text = CITE.sub(lambda m: f"[{m.group(1)}]", text)
    return text


def build(name: str) -> None:
    folder, slug, title, desc = TARGETS[name]
    src = (ROOT / "docs" / "source" / f"{name}.md").read_text()
    outdir = ROOT / folder
    outdir.mkdir(exist_ok=True)
    (outdir / f"{slug}.md").write_text(md_clean(name, src))
    htmlpath = outdir / f"{slug}.html"
    htmlpath.write_text(to_html(name, title, desc, src))
    pdf = outdir / f"{slug}.pdf"
    r = subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", htmlpath.as_uri()], capture_output=True, text=True)
    ok = pdf.exists() and pdf.stat().st_size > 20000
    print(f"  {name:<10} md+html{'+pdf' if ok else ' (PDF FAILED)'} -> {folder}/{slug}.*")


def main() -> int:
    which = sys.argv[1:] or ["all"]
    names = list(TARGETS) if which == ["all"] else which
    for n in names:
        build(n)
    print(f"facts used: {len(USED)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
