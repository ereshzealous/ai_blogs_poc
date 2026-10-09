"""Write diagrams/manifest.json: every T3 figure (semantic id, reading order), its frame, files, Excalidraw+ location and
provenance.

    python3 tools/diagram_manifest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "diagrams"
EV = ROOT / "hitl_poc" / "evidence"
sys.path.insert(0, str(D / "tools"))
ARCH = "Architecture: concept figure; no measured values"
SOURCES = {
    "cover": "Concept + measured: digests computed by hitl/contracts.py; footer counts from the run",
    "incident-37-minutes": "Recorded: story.json (scenario H5c under arms A, B and C)",
    "button-not-control": "Recorded + architecture: arm A's message as the run posted it",
    "authz-approval-execution": ARCH,
    "state-machine": "Implemented + measured: TRANSITIONS in hitl/approvals.py; H7 duplicates under C",
    "bound-approval": "Recorded: the approval artifact of H9a under arm C (audit.jsonl)",
    "production-architecture": ARCH,
    "poc-testbed": "Implemented + measured: the testbed of hitl_poc; counts from the run",
    "exp-mutation": "Measured: H1 and H2 under arms A, B and C",
    "exp-replay": "Measured: H3 under arms A, B and C",
    "exp-eligibility": "Measured: H4 under arms A, B and C",
    "exp-stale": "Measured: H5 and H6 under arms A, B and C",
    "exp-duplicate": "Measured: H7 under arms A, B and C",
    "decision-card": "Recorded: the messages arms A and C posted in H9a (channel.posted)",
    "audit-reconstruction": "Measured: H9a reconstruction under arms A, B and C",
    "findings": "Measured + reasoned: global facts of the run and the qualified claims",
    "production-rules": "Reasoned from the scenarios named on each rule",
    "next-control-plane": "Series map: no results claimed",
    "tech-poc-architecture": "Implemented: the modules of hitl_poc; counts from the run",
    "tech-scorecard": "Measured: headline metric per experiment and arm; checks.jsonl",
    "tech-trace": "Recorded: story.json (H5c under arm C)",
    "tech-failure-modes": "Reasoned + measured: each tested row names its scenario",
}


def main() -> None:
    from figures import ORDER, RUN  # the semantic ids in reading order, and the run the figures were drawn from
    assert set(ORDER) == set(SOURCES), set(ORDER) ^ set(SOURCES)
    scenes = json.loads((D / "scenes.json").read_text()) if (D / "scenes.json").exists() else {}
    figs = {}
    for i, fid in enumerate(ORDER):
        prov = SOURCES[fid]
        s = json.loads((D / "premium" / "skeletons" / f"{fid}.json").read_text())
        measured = prov.startswith(("Measured", "Recorded", "Concept + measured", "Implemented + measured", "Reasoned + measured"))
        figs[fid] = {"order": i, "name": s["name"], "width": s["width"], "height": s["height"], "edition": "technical" if fid.startswith("tech-") else "both",
                     "provenance": prov + (f" · run {RUN}" if measured else ""),
                     "files": {k: f"diagrams/premium/{k}/{fid}.{ext}" for k, ext in (("skeletons", "json"), ("excalidraw", "excalidraw"), ("svg", "svg"), ("png", "png"))},
                     "excalidraw": scenes.get(fid, {})}
    (D / "manifest.json").write_text(json.dumps({"collection": {"name": "AI_BLOGS", "id": "A10UVY9ELvm"}, "scene": "6UKrYfW2Ulh", "run": RUN, "figures": figs,
                                                 "screens": {"inbox": "diagrams/screens/inbox.png (recorded: uv run hitl serve)"},
                                                 "icons": {"collection": "Architecture Icons (6xMmyYanRuQ)", "licence": "Lucide (ISC)"}}, indent=1))
    print(len(figs), "figures")


if __name__ == "__main__":
    main()
