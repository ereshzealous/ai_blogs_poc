"""Record a run, or replay one from its tapes.

    uv run python -m s2_eval.run record --run-id 2026-10-08-heldout --split heldout          # live models, records tapes
    uv run python -m s2_eval.run record --run-id dev-smoke --split dev --scripted            # no model: the surrogate
    uv run python -m s2_eval.run replay --from 2026-10-08-heldout --out 2026-10-08-heldout-replay   # no model, no Ollama

A run directory holds: manifest.json (inputs, hashes, models, environment), one JSONL file of rows per experiment
(deterministic given the tapes), invariants.json, timings.jsonl (wall-clock and server timings: never compared), and
tape/ (query embeddings, every model exchange). Replay re-executes every experiment with the tapes in replay mode and
compares each rows file byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
import urllib.request
from pathlib import Path

from knowledge_rag.generate import ModelClient
from knowledge_rag.pipeline import KEEP_ONE, REMOVE_ONE, VARIANTS
from knowledge_rag.util import ROOT, config, load_yaml
from s2_eval import experiments as X
from s2_eval.common import RUNS, load_cases, retriever, world

ROWS = ["a.jsonl", "b.jsonl", "c.jsonl", "d.jsonl", "d_sensitivity.jsonl", "d2.jsonl", "e_evidence.jsonl", "e_live.jsonl", "invariants.json"]
ALL_EXPERIMENTS = ["A", "B", "C", "D", "D2", "E"]


def _write(path: Path, rows) -> None:
    if path.suffix == ".json":
        path.write_text(json.dumps(rows, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    else:
        path.write_text("".join(X.dumps(r) + "\n" for r in rows))


def _ollama_models() -> dict:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as r:
            return {m["name"]: m["digest"] for m in json.loads(r.read())["models"]}
    except Exception:  # noqa: BLE001
        return {}


def input_hashes() -> dict:
    from s2_eval.freeze import frozen_files
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen_files()}


def execute(out: Path, split: str, mode: str, tape: Path, experiments: list[str]) -> None:
    """mode: live | replay | scripted."""
    out.mkdir(parents=True, exist_ok=True)
    models = config("models.yaml")
    w = world()
    retr = retriever(tape / "query_embeddings.jsonl", "replay" if mode == "replay" else "record")
    cases = load_cases(split)
    prim = ModelClient(models["primary"], mode, tape / "model.jsonl")
    timings: list[dict] = []
    if "A" in experiments:
        _write(out / "a.jsonl", X.exp_a(cases, retr, w))
    if "B" in experiments:
        _write(out / "b.jsonl", X.exp_b(cases, retr, w))
    if "C" in experiments:
        _write(out / "c.jsonl", X.exp_c(cases, retr, w))
    if "D" in experiments:
        seeds = models["primary"]["seeds"] if split == "heldout" else [models["ablation_seed"]]
        _write(out / "d.jsonl", X.exp_d(cases, retr, w, prim, seeds, ["naive", "governed"], timings))
        if mode != "scripted":
            sens = ModelClient(models["sensitivity"], mode, tape / "model-sensitivity.jsonl")
            _write(out / "d_sensitivity.jsonl", X.exp_d(cases, retr, w, sens, models["sensitivity"]["seeds"], ["naive", "governed"], timings))
    if "E" in experiments or "Eev" in experiments:
        ev = X.exp_e_evidence(cases, retr, w, list(VARIANTS))
        _write(out / "e_evidence.jsonl", ev)
        _write(out / "invariants.json", {arm: X.invariants(ev, arm) for arm in ("governed", "naive", "nc-minus-recheck")})
        if "E" in experiments:
            # end to end: every remove-one variant, the negative control, and the one keep-only-one variant that needs no new
            # model call (naive + verifier re-verifies the recorded naive answers); every keep-only-one variant is measured at
            # evidence level above
            variants = list(REMOVE_ONE) + ["naive-plus-verify", "nc-minus-recheck"]
            _write(out / "e_live.jsonl", X.exp_d(cases, retr, w, prim, [models["ablation_seed"]], variants, timings))
    if "D2" in experiments:
        judge = ModelClient(models["judge"], mode, tape / "judge.jsonl") if mode != "scripted" else None
        rows = []
        for sp in ([split]):                       # a dev run never scores the held-out pairs
            f = ROOT / "experiments" / f"verifier-pairs-{sp}.yaml"
            if f.exists():
                rows += X.exp_d2(load_yaml(f)["pairs"], sp, w, retr, judge)
        _write(out / "d2.jsonl", rows)
    with (out / "timings.jsonl").open("w") as fh:
        for t in timings:
            fh.write(json.dumps(t, sort_keys=True) + "\n")


def sha256sums(run: Path) -> None:
    lines = []
    for p in sorted(run.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS":
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(run)}")
    (run / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def record(args) -> None:
    run = RUNS / args.run_id
    if run.exists() and any(run.iterdir()) and not args.resume:
        sys.exit(f"{run} exists; refusing to overwrite a recorded run (use --resume to continue an interrupted one)")
    mode = "scripted" if args.scripted else "live"
    exps = args.experiments.split(",") if args.experiments else ALL_EXPERIMENTS
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    manifest = {"run_id": args.run_id, "split": args.split, "mode": mode, "experiments": exps, "started": started,
                "command": " ".join(sys.argv), "python": platform.python_version(), "platform": platform.platform(),
                "models": config("models.yaml"), "ollama_models": _ollama_models() if mode == "live" else {},
                "inputs_sha256": input_hashes(), "frozen": (ROOT / "experiments" / "FROZEN.at").read_text().strip()
                if (ROOT / "experiments" / "FROZEN.at").exists() else None}
    run.mkdir(parents=True, exist_ok=True)
    (run / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    execute(run, args.split, mode, run / "tape", exps)
    manifest["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (run / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    from s2_eval import analysis
    analysis.write(run)
    sha256sums(run)
    print(f"recorded {run}")


def replay(args) -> None:
    src = RUNS / args.src
    out = RUNS / args.out
    m = json.loads((src / "manifest.json").read_text())
    if out.exists():
        for p in out.glob("*.json*"):
            p.unlink()
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps({**m, "replay_of": args.src}, indent=1, sort_keys=True) + "\n")
    execute(out, m["split"], "replay" if m["mode"] == "live" else "scripted", src / "tape", m["experiments"])
    from s2_eval import analysis
    analysis.write(out)
    diffs, same = [], []
    for name in ROWS + ["facts.json"]:
        a, b = src / name, out / name
        if not a.exists() and not b.exists():
            continue
        (same if a.exists() and b.exists() and a.read_bytes() == b.read_bytes() else diffs).append(name)
    verdict = "REPLAY IDENTICAL" if not diffs else "REPLAY DIFFERS"
    report = {"source": args.src, "replay": args.out, "verdict": verdict, "identical": same, "different": diffs,
              "model_calls_from_tape": sum(1 for line in (src / "tape" / "model.jsonl").read_text().splitlines() if line.strip())
              if (src / "tape" / "model.jsonl").exists() else 0}
    (out / "replay-check.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))
    if diffs:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(prog="s2_eval.run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--run-id", required=True)
    r.add_argument("--split", choices=["dev", "heldout"], required=True)
    r.add_argument("--experiments", default="")
    r.add_argument("--scripted", action="store_true")
    r.add_argument("--resume", action="store_true")
    p = sub.add_parser("replay")
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--out", required=True)
    args = ap.parse_args()
    {"record": record, "replay": replay}[args.cmd](args)


if __name__ == "__main__":
    main()
