"""Write diagrams/manifest.json: every capstone figure with its name, size, provenance, badges, data sources, files and Excalidraw+ frame.

    python3 tools/diagram_manifest.py

Provenance is printed under each figure in the articles.  Excalidraw+ ids come from diagrams/scenes.json (written when the
frames were pushed with the Excalidraw+ MCP); a figure not pushed yet is listed without them.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "diagrams"
POCDIR = "production_agentic_ai_platform"
PUB = json.loads((ROOT / POCDIR / "evidence" / "published.json").read_text())   # the published run (Proof Contract v1)
RUN = PUB["run_id"]
EV = f"{POCDIR}/evidence/runs/{RUN}"
RES = f"{EV}/results.json"
RAW = f"{EV}/raw/experiments"
FACTS = "docs/facts.json"
_X = {x["id"]: x["checks"] for x in json.loads((ROOT / RES).read_text())["experiments"]}


def measured(*xs: str) -> str:
    """The contract's figure footer: MEASURED · run · experiment · checks · source."""
    ids = {x: sorted(_X["P1-" + x], key=lambda c: int(c.rsplit("-C", 1)[1])) for x in xs}
    parts = [f"P1-{x} · checks {ids[x][0]}…{ids[x][-1].rsplit('-', 1)[1]}" for x in xs]
    return f"run {RUN} · " + " · ".join(parts) + " · results.json"


ARCH, MEAS, IMPL = ["ARCHITECTURE"], ["MEASURED"], ["IMPLEMENTATION"]
NONE = "no run result claimed"
PROV = {  # id: (provenance, badges, data sources)
    "cover": (f"concept; every id and count is from {measured('R1')}", MEAS, [FACTS, RES]),
    "demo-architecture": (f"the demo architecture · {NONE}", ARCH, []),
    "why-it-breaks": (f"the thirteen production questions (our synthesis) · {NONE}", ARCH, []),
    "series-map": (f"the nine earlier notes and what each left in the platform · {NONE}", ARCH, []),
    "platform": (f"the whole platform, end to end (our synthesis) · {NONE}; the proof exercises one agent and one access path", ARCH, []),
    "reference-architecture": (f"the reference architecture (our synthesis, vendor-neutral) · {NONE}", ARCH, []),
    "four-planes": (f"the four planes (our synthesis) · {NONE}", ARCH, []),
    "governed-path": (measured("R1"), MEAS, [FACTS, f"{RAW}/R1"]),
    "effective-authority": (measured("R2"), MEAS, [FACTS, f"{POCDIR}/config/identity/principals.yaml", f"{RAW}/R2"]),
    "context-path": (measured("R8"), MEAS, [FACTS, f"{RAW}/R8"]),
    "model-gateway": (measured("R7") + "; models are recorded fixtures", MEAS, [FACTS, f"{POCDIR}/config/models/models.yaml", f"{RAW}/R7"]),
    "discovery-vs-execution": (measured("R4"), MEAS, [FACTS, f"{RAW}/R4"]),
    "proposal-boundary": (measured("R1"), MEAS, [FACTS, f"{RAW}/R1"]),
    "hitl-digest": (measured("R3"), MEAS, [FACTS, f"{RAW}/R3"]),
    "capability-flow": (measured("R1", "R5"), MEAS, [FACTS, f"{RAW}/R1", f"{RAW}/R5"]),
    "guardrails-vs-policy": (measured("R12"), MEAS, [FACTS, f"{RAW}/R12"]),
    "budget": (measured("R6"), MEAS, [FACTS, f"{RAW}/R6"]),
    "kill-switch": (measured("R11"), MEAS, [FACTS, f"{RAW}/R11"]),
    "crash-idempotency": (measured("R9", "R10") + "; real SIGKILLs", MEAS, [FACTS, f"{RAW}/R9", f"{RAW}/R10"]),
    "evidence-chain": (measured("R13"), MEAS, [FACTS, f"{RAW}/R13"]),
    "poc-architecture": (f"the POC's runtime topology · no benchmark result claimed; library versions from run {RUN}", IMPL, [FACTS, RES, f"{POCDIR}/src/"]),
    "control-tower": (f"the rings are our synthesis ({NONE}); the evidence strip is {measured('R1')}", ARCH + MEAS, [FACTS]),
    "semantics": ("the visual grammar used by every figure; icons are Lucide (ISC)", [], []),
    "proof-chain": (measured("R3") + " · SHA256SUMS · replay.json", MEAS, [FACTS, f"{EV}/checks.jsonl", f"{EV}/SHA256SUMS", f"{EV}/replay.json"]),
    "series-closure": (f"where each earlier note sits in the final platform (our synthesis) · {NONE}", ARCH, []),
    "proof-scorecard": (f"run {RUN} · P1-R1…P1-R14 · every check · results.json", MEAS, [f"{EV}/results.json", f"{EV}/checks.jsonl"]),
    "proof-strip": (f"run {RUN} · results.json · replay.json · negative-control/results.json", MEAS,
                    [FACTS, f"{EV}/results.json", f"{EV}/replay.json", f"{EV}/negative-control/results.json"]),
    "what-ran": (f"the execution profile of run {RUN} (results.json → profile) · {NONE}", IMPL, [f"{EV}/results.json"]),
    "evidence-links": (f"where the evidence of run {RUN} lives in the repository · {NONE}", IMPL, []),
}


def main() -> None:
    scenes = json.loads((D / "scenes.json").read_text())
    figs = {}
    for fid, (prov, badges, sources) in PROV.items():
        s = json.loads((D / "premium" / "skeletons" / f"{fid}.json").read_text())
        files = {k: f"diagrams/premium/{k}/{fid}.{ext}" for k, ext in (("skeletons", "json"), ("excalidraw", "excalidraw"), ("svg", "svg"), ("png", "png"))}
        missing = [p for p in files.values() if not (ROOT / p).exists()]
        if missing:
            raise SystemExit(f"{fid}: missing {missing}")
        for src in sources:
            if not (ROOT / src).exists():
                raise SystemExit(f"{fid}: data source missing {src}")
        figs[fid] = {"name": s["name"], "width": s["width"], "height": s["height"], "provenance": prov, "badges": badges,
                     "data_sources": sources, "files": files}
        if fid in scenes:
            figs[fid]["excalidraw"] = scenes[fid]
        else:
            raise SystemExit(f"{fid}: no Excalidraw+ frame recorded in diagrams/scenes.json")
    out = {"collection": {"name": "AI_BLOGS", "id": "A10UVY9ELvm"}, "scene": scenes["_scene"], "run": RUN,
           "push": "Excalidraw+ MCP (edit_scene_content) only; no forked push; icons are editable shapes from the Architecture Icons collection, no images", "figures": figs}
    (D / "manifest.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(len(figs), "figures ->", D / "manifest.json")


if __name__ == "__main__":
    main()
