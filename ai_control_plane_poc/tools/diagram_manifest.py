"""Write diagrams/manifest.json: every T4 figure with its name, size, provenance, data sources, files and Excalidraw+ frame.

    python3 tools/diagram_manifest.py

Provenance is printed under each figure in the articles.  Excalidraw+ ids come from diagrams/scenes.json (written when the
frames are pushed); a figure not yet pushed is listed without them.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "diagrams"
sys.path.insert(0, str(ROOT / "diagrams" / "tools"))
from figures_t4 import BADGES  # noqa: E402  (the provenance badges drawn on each figure, repeated in its caption)

RUN = (ROOT / "control_plane_poc" / "runs" / "PUBLISHED").read_text().strip()
POC = f"control_plane_poc/runs/{RUN}"

PROV = {
    "cover": ("Concept: the cover metaphor; version labels are illustrative, no measured values", []),
    "governance-duplicated": (f"Implemented + measured: the embedded baseline's constants (acp/embedded/); the footer counts are P11 · run {RUN}",
                              ["control_plane_poc/acp/embedded/", f"{POC}/facts.json"]),
    "scale-problem": ("Concept: agent counts and questions are illustrative; no measured values", []),
    "four-planes": ("Architecture: concept figure (our synthesis); no measured values", []),
    "desired-observed": (f"Recorded: P10's desired and observed versions; the YAML is the seed desired state · run {RUN}",
                         [f"{POC}/scenarios/P10-C-drift/state/drift.json", "control_plane_poc/config/desired-state.yaml"]),
    "operating-loop": ("Architecture: concept figure (our synthesis); no measured values", []),
    "capability-map": ("Architecture: concept figure (our synthesis); no measured values", []),
    "tool-governance": ("Architecture + implemented: the registry rows are the POC's desired state; the tool names above are illustrative",
                        ["control_plane_poc/config/desired-state.yaml"]),
    "control-distribution": ("Architecture: concept figure; version numbers are illustrative, no measured values", []),
    "poc-architecture": ("Implemented: the POC's components and files; no measured values", ["control_plane_poc/acp/"]),
    "proof-same-code": (f"Recorded: P2 · run {RUN}", [f"{POC}/scenarios/P2-C-central-change/scenario.json", f"{POC}/facts.json"]),
    "poc-evidence": (f"Measured: every proof · run {RUN}", [f"{POC}/facts.json", f"{POC}/checks.json"]),
    "failure-behavior": (f"Architecture + measured: the failure policy; the footer is P9a · run {RUN}", [f"{POC}/facts.json"]),
    "poc-to-production": ("Architecture: mapping (our synthesis); no measured values", []),
    "reference-architecture": ("Architecture: reference (our synthesis); no measured values", []),
    "series-primitives": ("Series map: the series order; no results claimed", []),
    "scale-drift": (f"Concept + measured: the 1/5/50/500 counts are illustrative; the bottom strip is P11 · run {RUN}", [f"{POC}/facts.json"]),
    "control-loop": (f"Architecture + recorded: the loop is our synthesis; the lower panel is P10's desired and observed versions · run {RUN}",
                     [f"{POC}/scenarios/P10-C-drift/state/drift.json", f"{POC}/facts.json"]),
    "guarantee-boundaries": (f"Measured: P9 (outage, tampered bundle) and P10 (drift); the production options are architecture · run {RUN}",
                             [f"{POC}/facts.json"]),
    "production-architecture": ("Architecture: the reference architecture, reduced for the Medium edition (our synthesis); no measured values", []),
}


def main() -> None:
    scenes = json.loads((D / "scenes.json").read_text()) if (D / "scenes.json").exists() else {}
    figs = {}
    for fid, (prov, sources) in PROV.items():
        sk = D / "premium" / "skeletons" / f"{fid}.json"
        if not sk.exists():
            continue
        s = json.loads(sk.read_text())
        figs[fid] = {"name": s["name"], "width": s["width"], "height": s["height"], "provenance": prov, "badges": BADGES.get(fid, []), "data_sources": sources,
                     "files": {k: f"diagrams/premium/{k if k != 'skeletons' else 'skeletons'}/{fid}.{ext}"
                               for k, ext in (("skeletons", "json"), ("excalidraw", "excalidraw"), ("svg", "svg"), ("png", "png"))}}
        if fid in scenes:
            figs[fid]["excalidraw"] = scenes[fid]
    out = {"collection": {"name": "AI_BLOGS", "id": "A10UVY9ELvm"}, "scene": "T4 · AI Control Plane · Premium", "run": RUN, "figures": figs}
    (D / "manifest.json").write_text(json.dumps(out, indent=1))
    print(len(figs), "figures")


if __name__ == "__main__":
    main()
