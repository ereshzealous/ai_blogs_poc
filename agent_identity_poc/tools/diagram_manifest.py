"""Write diagrams/manifest.json: every T1 figure with its name, size, provenance, data sources, files and Excalidraw+ frame.

    python3 tools/diagram_manifest.py

Provenance is printed under each figure in the articles.  Excalidraw+ ids come from diagrams/scenes.json (written when the
frames are pushed); a figure not yet pushed is listed without them.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "diagrams"
RUN = (ROOT / "agent_identity_poc" / "runs" / "PUBLISHED").read_text().strip()
POC = f"agent_identity_poc/runs/{RUN}"
sys.path.insert(0, str(D / "tools"))
from figures_t1 import ORDER  # noqa: E402  (article reading order)

PROV = {
    "cover": ("Concept: the cover metaphor; identifiers only", []),
    "incident": ("Architecture: concept figure; no measured values", []),
    "chat-vs-headless": ("Architecture: concept figure; no measured values", []),
    "five-questions": ("Architecture: concept figure; no measured values", []),
    "five-identities": ("Architecture + implemented: production shapes and the POC's identifiers; no measured values", ["agent_identity_poc/config/principals.yaml"]),
    "credential-not-identity": ("Architecture: concept figure; no measured values", []),
    "trust-boundaries": ("Architecture: the four trust boundaries and the rule at each; no measured values", []),
    "poc-testbed": (f"Implemented: the POC's components and the held-constant fixture; experiment list from the run · run {RUN}", [f"{POC}/manifest.json", f"{POC}/facts.json"]),
    "poc-results": (f"Measured: I1–I7 headline results · run {RUN}", [f"{POC}/facts.json"]),
    "exp-attribution": (f"Measured: I1, attribution under three identity models · run {RUN}", [f"{POC}/I1.json"]),
    "exp-confused-deputy": (f"Measured: I2, the confused deputy · run {RUN}", [f"{POC}/I2.json"]),
    "antipattern-shared-sa": ("Architecture: concept figure; the permission list is illustrative", []),
    "production-pattern": ("Architecture + implemented: the stages of the POC; no measured values", []),
    "exp-revocation": (f"Measured: I3, revocation drill · run {RUN}", [f"{POC}/I3.json"]),
    "exp-pause": (f"Measured: I7, pause and re-exchange; I4, replay · run {RUN}", [f"{POC}/I7.json", f"{POC}/I4.json"]),
    "poc-trace": (f"Recorded: the event-triggered 14:09 rollback, hop by hop · run {RUN}", [f"{POC}/story.json"]),
    "audit-xray": (f"Recorded: the 14:09 event-triggered rollback, platform record and Kubernetes log · run {RUN}", [f"{POC}/story.json"]),
    "findings": (f"Measured: supported and qualified findings, contradicted count from the declared checks · run {RUN}", [f"{POC}/facts.json", f"{POC}/checks.json"]),
    "next-authorization": ("Series map: learning-map.yaml; no results claimed", []),
    "tech-scorecard": (f"Measured: I1–I7 per identity model, declared checks per experiment, G01–G11 · run {RUN}", [f"{POC}/facts.json", f"{POC}/checks.json"]),
    "tech-revocation-matrix": (f"Measured: I3, one revocation lever at a time across five executions · run {RUN}", [f"{POC}/I3.json", f"{POC}/facts.json"]),
    "tech-claim-trace": (f"Measured: claims traced to their declared checks and status · run {RUN}", [f"{POC}/checks.json", "agent_identity_poc/proof/preregistration.toml"]),
}



def main() -> None:
    scenes = json.loads((D / "scenes.json").read_text()) if (D / "scenes.json").exists() else {}
    figs = {}
    for fid in ORDER:
        prov, sources = PROV[fid]
        sk = D / "premium" / "skeletons" / f"{fid}.json"
        if not sk.exists():
            continue
        s = json.loads(sk.read_text())
        figs[fid] = {"name": s["name"], "width": s["width"], "height": s["height"], "provenance": prov, "data_sources": sources,
                     "files": {k: f"diagrams/premium/{k if k != 'skeletons' else 'skeletons'}/{fid}.{ext}"
                               for k, ext in (("skeletons", "json"), ("excalidraw", "excalidraw"), ("svg", "svg"), ("png", "png"))}}
        if fid in scenes:
            figs[fid]["excalidraw"] = scenes[fid]
    out = {"collection": {"name": "AI_BLOGS", "id": "A10UVY9ELvm"}, "scene": "T1 · Agent Identity · Premium", "run": RUN, "figures": figs}
    (D / "manifest.json").write_text(json.dumps(out, indent=1))
    print(len(figs), "figures")


if __name__ == "__main__":
    main()
