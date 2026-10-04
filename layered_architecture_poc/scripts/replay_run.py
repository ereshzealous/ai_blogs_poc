"""Replay a recorded run from its model tape (no model is called) and compare the published figures.

    uv run python scripts/replay_run.py runs/<id>          -> runs/<id>-replay/ and runs/<id>-replay/replay_comparison.json

Everything below the model runs again for real: MCP servers, the world, faults, SIGKILLs, checkpoints, policy.
A replay is a reproducibility check, not a fresh model execution; the comparison says so.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
VOLATILE = ("wall_s", "median_wall_s", "median_wall_s_after_crash", "run_id", "mode", "replay_of", "tests", "reports")


def strip(node):
    if isinstance(node, dict):
        return {k: strip(v) for k, v in node.items() if k not in VOLATILE and not k.endswith("wall_s")}
    if isinstance(node, list):
        return [strip(x) for x in node]
    return node


def diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += diff(a.get(k), b.get(k), f"{path}.{k}" if path else k)
        return out
    return [] if a == b else [{"path": path, "recorded": a, "replayed": b}]


def main(src: Path) -> int:
    dst_id = f"{src.name}-replay"
    subprocess.run([sys.executable, "scripts/record_run.py", "--run-id", dst_id, "--replay-from", str(src)], cwd=POC, check=True)
    dst = POC / "runs" / dst_id
    a = strip(json.loads((src / "summary.json").read_text()))
    b = strip(json.loads((dst / "summary.json").read_text()))
    d = diff(a.get("experiments"), b.get("experiments"), "experiments") + diff(a.get("headline"), b.get("headline"), "headline")
    served = sum(1 for p in (dst / "scenarios").glob("*/tape/model_calls.jsonl") for l in p.read_text().splitlines() if '"replayed":true' in l.replace(" ", ""))
    fresh = sum(1 for p in (dst / "scenarios").glob("*/tape/model_calls.jsonl") for l in p.read_text().splitlines() if '"replayed":false' in l.replace(" ", ""))
    out = {"recorded_run": src.name, "replay_run": dst_id, "model_calls_served_from_tape": served, "fresh_model_calls": fresh,
           "identical": not d, "differences": d,
           "note": "Replay re-executes MCP servers, the world, faults, SIGKILLs, checkpoints and policy; only model answers come from the tape."}
    (dst / "replay_comparison.json").write_text(json.dumps(out, indent=1, default=str))
    print(f"replay: {'IDENTICAL' if not d else str(len(d)) + ' differences'}; {served} model calls from tape, {fresh} fresh")
    return 0 if not d and fresh == 0 else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve()))
