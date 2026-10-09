"""Write diagrams/manifest.json: every T5 figure with its name, size, provenance, data sources, files, article use and Excalidraw+ frame.

    python3 tools/diagram_manifest.py

Provenance is printed under each figure in the articles.  Excalidraw+ ids come from diagrams/scenes.json (written as the
frames are pushed through the Excalidraw MCP); a figure not yet pushed is listed without them.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "diagrams"
RUN = (ROOT / "observability_governance_poc" / "runs" / "PUBLISHED").read_text().strip()
POC = f"observability_governance_poc/runs/{RUN}"
E12 = f"{POC}/scenarios/e12a-lost-response/evidence/audit-events.jsonl"

PROV = {
    "cover": (f"Concept + recorded: the flight-recorder strip is E12's evidence timeline · run {RUN}", [f"{POC}/reports/timeline.json", f"{POC}/facts.json"]),
    "six-hours-later": (f"Concept + recorded: the ids are E12's, from each component's own log · run {RUN}", [f"{POC}/scenarios/e12a-lost-response/logs/"]),
    "fragments-vs-lineage": (f"Measured: joins per scenario from the reconstruction scorer; E12's events · run {RUN}", [f"{POC}/reports/comparison.json", E12]),
    "intent-to-effect": ("Architecture: concept figure; experiment tags name the scenarios that inject each failure", ["observability_governance_poc/experiments/preregistration.toml"]),
    "layered-architecture": ("Architecture: the reference architecture; pins are config/control_plane.toml", ["observability_governance_poc/config/control_plane.toml"]),
    "execution-lineage": (f"Recorded: every id is E12's, from its evidence · run {RUN}", [E12]),
    "telemetry-vs-evidence": (f"Architecture + measured: sampling, orphaned spans and retention from the run and config · run {RUN}", [f"{POC}/reports/telemetry.json", "observability_governance_poc/config/retention.toml"]),
    "identity-lineage": (f"Implemented + measured: the delegation chain the POC records; Q2 scores · run {RUN}", [f"{POC}/reports/comparison.json"]),
    "version-lineage": (f"Recorded + measured: E1, E8a, E8b, E9 pins and digests; Q4 scores · run {RUN}", [f"{POC}/facts.json", f"{POC}/reports/comparison.json"]),
    "lost-response": (f"Recorded: E12a, one fault injected (SIMULATED), real timeout and retry · run {RUN}", [E12, f"{POC}/scenarios/e12a-lost-response/world/external-transactions.json"]),
    "effect-verification": (f"Recorded: E11, fault injected (SIMULATED), real read-back and verdicts · run {RUN}", [f"{POC}/scenarios/e11-false-success/evidence/audit-events.jsonl", f"{POC}/reports/comparison.json"]),
    "evidence-record": (f"Recorded: E12a's evidence events, grouped · run {RUN}", [E12]),
    "poc-architecture": ("Implemented: the POC's processes and stores; labels as in real-vs-simulated", ["observability_governance_poc/lineage/"]),
    "experiment-matrix": (f"Measured: every scenario's recorded outcome and production changes · run {RUN}", [f"{POC}/reports/results.json"]),
    "flagship-proof": (f"Measured: E12a vs E12b, truth from the deployment API's own records · run {RUN}", [f"{POC}/facts.json"]),
    "baseline-vs-lineage": (f"Measured: 15 scenarios × 13 questions × 3 layers · run {RUN}", [f"{POC}/reports/comparison.json"]),
    "reconstruction-timeline": (f"Recorded: E12a's evidence events in order, wall-clock offsets · run {RUN}", [f"{POC}/reports/timeline.json"]),
    "drift": (f"Recorded: D1 drift probe, 10 incidents × 2 configurations, one call each · run {RUN}", [f"{POC}/reports/drift.json"]),
    "blueprint": ("Architecture + series map: principles from the article; no measured values", []),
    "poc-at-a-glance": (f"Implemented: the POC's shared action path, the three readers and the real / simulated / recorded split · run {RUN}",
                        ["observability_governance_poc/lineage/", "results/observability-governance-real-vs-simulated.md"]),
    "scorecard-simple": (f"Measured: 13 questions grouped into operational facts and four governance gaps, 15 scenarios × 3 layers · run {RUN}", [f"{POC}/reports/comparison.json", f"{POC}/facts.json"]),
    "lost-response-hero": (f"Measured: E12a vs E12b, truth from the deployment API's revisions table · run {RUN}", [f"{POC}/facts.json", f"{POC}/scenarios/e12a-lost-response/truth.json"]),
    "telemetry-simple": ("Architecture: the two records and their properties; the measured losses are in the text", ["observability_governance_poc/config/retention.toml"]),
    "architecture-simple": ("Architecture: the reference architecture, simplified for the Medium edition; no measured values", []),
}


def uses() -> dict:
    """figure id -> [{doc, section, caption, alt}] from the figure directives in docs/source (the articles' own text)."""
    import re
    out: dict = {}
    docs = {"medium": [ROOT / "docs/source/medium.src.md"], "technical": sorted((ROOT / "docs/source/technical").glob("*.md")),
            "evidence": [ROOT / "docs/source/evidence.src.md"]}
    for doc, files in docs.items():
        section = ""
        for f in files:
            for line in f.read_text().splitlines():
                if line.startswith("## "):
                    section = line[3:].strip()
                m = re.match(r"^::: figure (\S+) \| (.*?) \| (.*)$", line)
                if m:
                    out.setdefault(m.group(1), []).append({"doc": doc, "section": section, "caption": m.group(2), "alt": m.group(3)})
                if line.startswith("cover: "):
                    out.setdefault(line[7:].strip(), []).append({"doc": doc, "section": "cover", "caption": "cover", "alt": "(front matter cover_alt)"})
    return out


def main() -> None:
    used = uses()
    scenes = json.loads((D / "scenes.json").read_text()) if (D / "scenes.json").exists() else {}
    figs = {}
    for fid, (prov, sources) in PROV.items():
        sk = D / "premium" / "skeletons" / f"{fid}.json"
        if not sk.exists():
            continue
        s = json.loads(sk.read_text())
        figs[fid] = {"name": s["name"], "width": s["width"], "height": s["height"], "provenance": prov, "data_sources": sources,
                     "files": {k: f"diagrams/premium/{k}/{fid}.{ext}" for k, ext in (("skeletons", "json"), ("excalidraw", "excalidraw"), ("svg", "svg"), ("png", "png"))}}
        figs[fid]["used_in"] = used.get(fid, [])
        if fid in scenes:
            figs[fid]["excalidraw"] = {**scenes[fid], "url": scenes.get("_scene", {}).get("url")}
    out = {"collection": {"name": "AI_BLOGS", "id": "A10UVY9ELvm", "url": "https://app.excalidraw.com/o/9sQF7wZvz8d/A10UVY9ELvm"},
           "reference_scene": {"name": "F2 · Layered Production AI Architecture · Premium", "id": "32yE0CHsSJr"},
           "icon_collection": {"name": "Architecture Icons", "id": "6xMmyYanRuQ", "note": "Lucide 1.45 (ISC); SVGs in diagrams/icons"},
           "scene": scenes.get("_scene", {"name": "T5 · Observability & Governance · Premium"}), "run": RUN, "figures": figs}
    (D / "manifest.json").write_text(json.dumps(out, indent=1))
    print(len(figs), "figures")


if __name__ == "__main__":
    main()
