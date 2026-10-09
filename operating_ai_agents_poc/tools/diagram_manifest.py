"""Write diagrams/manifest.json: every O1 + O2 figure with its name, size, provenance, badges, data sources, files and Excalidraw+ frame.

    python3 tools/diagram_manifest.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "diagrams"
RUN = (ROOT / "ops_poc" / "runs" / "PUBLISHED").read_text().strip()
P = f"ops_poc/runs/{RUN}"

PROV = {
    "cover": (f"Architecture + measured: E1 (admission) and E10 (canary, R42-a) from the run's facts · run {RUN}", [f"{P}/facts.json"], ["MEASURED"]),
    "amplification": (f"Measured: 300 Cyber Monday requests replayed under R41 (E8) and the coordinators of E4 · run {RUN}",
                      [f"{P}/scenarios/E8/rows/R41.jsonl", f"{P}/scenarios/E4/none/rows.jsonl"], ["MEASURED"]),
    "pressure-map": ("Architecture: the capstone's layers (P1) with the control each owns; scenario tags point to the experiments", [], ["ARCHITECTURE"]),
    "envelope": (f"Architecture + measured: the refund dispute's calibrated envelope and the runaway outcomes (E4) · run {RUN}",
                 [f"{P}/scenarios/E4/limits.json", f"{P}/scenarios/E4/none/rows.jsonl", f"{P}/scenarios/E4/envelope/rows.jsonl"], ["ARCHITECTURE", "MEASURED"]),
    "runtime-loop": ("Architecture: our synthesis; the stage values are the POC's declared configuration", ["ops_poc/config/platform.toml"], ["ARCHITECTURE"]),
    "controls-compose": (f"Measured: E7's three arms, from the payments API's counters and the requests · run {RUN}", [f"{P}/scenarios/E7/"], ["MEASURED"]),
    "release-unit": (f"Architecture + measured: the release manifest (agentops/release.py) and E8's seven releases · run {RUN}",
                     [f"{P}/scenarios/E8/releases/", f"{P}/scenarios/E8/diffs.json"], ["ARCHITECTURE", "MEASURED"]),
    "release-pipeline": (f"Architecture + measured: E9's gate decisions and E10's canary decisions · run {RUN}",
                         [f"{P}/scenarios/E9/evals/", f"{P}/scenarios/E10/"], ["ARCHITECTURE", "MEASURED"]),
    "canary": (f"Measured + recorded: R42-a's first analysis window and the rollback record; R42-e under both comparisons (E10) · run {RUN}",
               [f"{P}/scenarios/E10/"], ["MEASURED", "RECORDED"]),
    "two-loops": ("Architecture: our synthesis (the two control loops and the shared evidence plane)", [], ["ARCHITECTURE"]),
    "scorecard": (f"Measured: one line per claim, naive and controlled arms; check counts from the proof pack · run {RUN}",
                  [f"{P}/facts.json", f"evidence/runs/{RUN}/results.json"], ["MEASURED"]),
    "series-closure": ("Architecture: the capstone's runtime path with the series' cross-cutting concerns", [], ["ARCHITECTURE"]),
}


def main() -> None:
    scenes = json.loads((D / "scenes.json").read_text()) if (D / "scenes.json").exists() else {}
    figs = {}
    for fid, (prov, sources, badges) in PROV.items():
        sk = D / "premium" / "skeletons" / f"{fid}.json"
        if not sk.exists():
            continue
        s = json.loads(sk.read_text())
        figs[fid] = {"name": s["name"], "width": s["width"], "height": s["height"], "provenance": prov, "badges": badges, "data_sources": sources,
                     "files": {k: f"diagrams/premium/{k}/{fid}.{ext}" for k, ext in (("skeletons", "json"), ("excalidraw", "excalidraw"), ("svg", "svg"), ("png", "png"))}}
        if fid in scenes:
            figs[fid]["excalidraw"] = {**scenes[fid], "url": scenes.get("_scene", {}).get("url")}
    out = {"collection": {"name": "AI_BLOGS", "id": "A10UVY9ELvm", "url": "https://app.excalidraw.com/o/9sQF7wZvz8d/A10UVY9ELvm"},
           "icon_collection": {"name": "Architecture Icons", "id": "6xMmyYanRuQ", "note": "editable Lucide shapes (ISC) via diagrams/tools/collection_icons.py"},
           "scene": scenes.get("_scene", {"name": "O1 + O2 · Operating AI Agents at Scale · Premium"}), "run": RUN, "figures": figs}
    (D / "manifest.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(len(figs), "figures")


if __name__ == "__main__":
    main()
