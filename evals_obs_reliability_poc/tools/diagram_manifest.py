"""Write diagrams/manifest.json: every R1+R2 figure with its name, size, provenance, badges, data sources, files and Excalidraw+ frame.

    python3 tools/diagram_manifest.py

Provenance is printed under each figure in the articles; badges open its caption.  Excalidraw+ ids come from
diagrams/scenes.json (written as the frames are pushed); a figure not yet pushed is listed without them.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "diagrams"
RUN = (ROOT / "recovery_poc" / "runs" / "PUBLISHED").read_text().strip()
P = f"recovery_poc/runs/{RUN}"
CFG = ["recovery_poc/config/recovery-matrix.toml", "recovery_poc/config/tools.toml"]

PROV = {
    "cover": (f"Concept + measured: the diagnosis is S09's recorded failure event; the counts are S09 in the providers' ledgers · run {RUN}",
              [f"{P}/scenarios/S09/A2/events.jsonl", f"{P}/facts.json"], ["MEASURED"]),
    "legend": ("Architecture: the series' colour grammar, plus the three execution certainties", [], ["ARCHITECTURE"]),
    "three-questions": ("Architecture: our synthesis; the example strings are S09's recorded fields", [f"{P}/scenarios/S09/A2/events.jsonl"], ["ARCHITECTURE"]),
    "operational-loop": (f"Architecture + recorded: each stage's artifact is S09's · run {RUN}", [f"{P}/facts.json"], ["ARCHITECTURE", "RECORDED"]),
    "operational-plane": ("Architecture: the capstone's layers; failure classes from recovery/taxonomy.py", ["recovery_poc/recovery/taxonomy.py"], ["ARCHITECTURE"]),
    "detection-vs-diagnosis": (f"Recorded: S09's failure event, field by field · run {RUN}", [f"{P}/scenarios/S09/A2/events.jsonl"], ["RECORDED"]),
    "failure-taxonomy": ("Implemented: the taxonomy and the frozen matrix's default actions; scenario ids from the oracle",
                         ["recovery_poc/recovery/taxonomy.py"] + CFG + ["recovery_poc/experiments/scenarios.toml"], ["ARCHITECTURE"]),
    "timeout-ambiguity": ("Architecture: certainty rules C1–C11 of the frozen matrix; scenario ids from the oracle", CFG, ["ARCHITECTURE"]),
    "one-timeout-four-answers": ("Implemented + recorded: the four tool contracts and matrix rules; each row is a recorded scenario (S14, S09, S20, S12)",
                                 CFG + [f"{P}/reports/scenarios.json"], ["RECORDED"]),
    "recovery-engine": (f"Implemented: the frozen recovery matrix; usage counts from run {RUN}", CFG + [f"{P}/facts.json"], ["ARCHITECTURE", "MEASURED"]),
    "flagship": (f"Measured: S09 through three runtimes, counted in the credit provider's ledger · run {RUN}",
                 [f"{P}/scenarios/S09/A0/world/ledger.json", f"{P}/scenarios/S09/A1/world/ledger.json", f"{P}/scenarios/S09/A2/world/ledger.json"], ["MEASURED"]),
    "idempotency-limits": (f"Measured: six scenarios × three runtimes, from the providers' ledgers · run {RUN}", [f"{P}/reports/scenarios.json"], ["MEASURED"]),
    "scorecard": (f"Measured: 25 scenarios × 3 runtimes, outcome eval OE1 per cell · run {RUN}", [f"{P}/reports/scenarios.json", f"{P}/facts.json"], ["MEASURED"]),
    "reconciliation": (f"Implemented + measured: reconciliation outcomes and the scenarios that produced them · run {RUN}", CFG + [f"{P}/facts.json"], ["MEASURED"]),
    "checkpoint-semantics": (f"Implemented + recorded: the journal schema (recovery/journal.py); S16 and S23 recorded · run {RUN}",
                             ["recovery_poc/recovery/journal.py", f"{P}/scenarios/S23/A2/events.jsonl"], ["RECORDED"]),
    "trace-anatomy": (f"Recorded: every exported span of S16 under the classified runtime · run {RUN}", [f"{P}/scenarios/S16/A2/telemetry/spans.jsonl"], ["RECORDED"]),
    "eval-families": ("Implemented: the eval suite (recovery/evals.py) and the model-slice evaluators", ["recovery_poc/recovery/evals.py", "recovery_poc/recovery/modelslice.py"],
                      ["ARCHITECTURE"]),
    "mutants": (f"Measured: eight preregistered mutants × 25 scenarios · run {RUN}", [f"{P}/reports/mutants.json"], ["MEASURED"]),
    "release-lifecycle": (f"Architecture + measured: the gate decisions are the run's (scripted change and real-model slice, blind cases) · run {RUN}",
                          [f"{P}/model-change/gate.json", f"{P}/model-slice/gate.json"], ["ARCHITECTURE", "MEASURED"]),
    "model-slice": (f"Measured: two local models, 16 cases × 3 seeds, deterministic evaluators · run {RUN}", [f"{P}/model-slice/scores.json"], ["MEASURED"]),
    "real-model-e2e": ("Measured: the real-model end-to-end run (qwen3:8b deciding, 25 scenarios × 3 runtimes) beside the scripted run · runs 2026-10-07-live and " + RUN,
                       ["recovery_poc/runs/2026-10-07-live/facts.json", f"{P}/facts.json"], ["MEASURED"]),
    "naive-vs-production": (f"Architecture + measured: the bottom counts are A0 and A2 over 25 scenarios · run {RUN}", [f"{P}/facts.json"], ["MEASURED"]),
    "what-ran": (f"Implemented: what is real, simulated, recorded and injected in run {RUN}", [f"{P}/manifest.json"], ["ARCHITECTURE"]),
    "reference-architecture": ("Architecture: the capstone's layers with this article's operational control loop (our synthesis)", [], ["ARCHITECTURE"]),
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
           "reference_scene": {"name": "Capstone · Production Agentic AI Platform · Premium v3", "id": "5jxIKbOR4o3"},
           "icon_collection": {"name": "Architecture Icons", "id": "6xMmyYanRuQ", "note": "editable Lucide shapes (ISC) via diagrams/tools/collection_icons.py"},
           "scene": scenes.get("_scene", {"name": "R1 + R2 · Evals, Observability & Reliability · Premium"}), "run": RUN, "figures": figs}
    (D / "manifest.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(len(figs), "figures")


if __name__ == "__main__":
    main()
