"""sprawl: one command for the Learning 01 POC (Capability Control Plane over real MCP).

    uv run sprawl <command> [options]          the portable form: macOS, Linux, Windows, CI (from the repository root)
    ./sprawl <command> …   sprawl.cmd …        shortcuts for the same command (Unix; Windows cmd or PowerShell)
    make <target>                              the Proof Contract v1 targets (verify, test, proof, replay, …), the same commands
    docker compose run --rm poc <command> …    the same command in a container

This module only decides what runs, in which order and with which options. Each command is a heading and the steps it
runs, printed as they run. What a step means lives in the POC's Python (the frozen poc/src and the post-freeze
poc/scripts), executed in the POC's own locked environment. Nothing here changes an input, a row or a score
(post-freeze tooling, experiment/deviations.md).
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
import time
import tomllib
import webbrowser
from pathlib import Path

from experiment_runner import FAIL, OK, WARN, Runner, head, ollama, say

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiment"
RUNS = EXP / "runs"
RECORDED_RUNS = tomllib.loads((ROOT / "proof" / "runs.toml").read_text())["runs"]  # every recorded run (proof/runs.toml)
PUBLISHED_RUN = os.environ.get("SPRAWL_RUN") or json.loads((ROOT / "evidence" / "published.json").read_text())["run_id"]
R = Runner(ROOT, project="poc", recorded=tuple(r["raw"] for r in RECORDED_RUNS) + tuple(f"experiment/recorded-run/{sub}" for r in RECORDED_RUNS
                                                                                       for sub in r.get("replay", {})),
           container_env="SPRAWL_IN_CONTAINER")
REPLAY_CASES = ["BL-C03-1", "BL-C07-1", "BL-C08-1", "BL-C10-1", "BL-C14-2"]  # one row per failure mode
PRESETS = {  # quick: four dev cases at 50 tools · full: the preregistered blind main pass · protocol: full + the repeat pass
    "quick": {"split": "dev", "arms": ["A", "B", "C"], "sizes": [50], "cases": ["DV-C01", "DV-C03", "DV-C07", "DV-C10"]},
    "full": {"split": "blind", "arms": ["C", "B", "A"], "sizes": [50, 100, 500], "cases": None},
    "protocol": {"split": "blind", "arms": ["C", "B", "A"], "sizes": [50, 100, 500], "cases": None, "repeat": True},
}
BUILD_INPUTS = ["poc/data/estates", "poc/data/world/seed.db", "experiment/benchmark/cases.json"]
BUILD_STEPS = ["sprawl_poc.catalog.build", "sprawl_poc.world.seed", "sprawl_poc.bench.cases", "sprawl_poc.bench.lint"]
ANALYSIS = ["experiment/analysis", "experiment/raw/blind-main/analysis", "evidence/evidence-index.md"]
# The public repository ships the POC, the derived evidence and the public verifier, not the publication framework:
# a verb whose script is absent is not offered, and `verify` checks the public evidence instead of the full proof pack.
HAS = lambda script: (ROOT / "poc" / "scripts" / script).exists()  # noqa: E731
FULL_PROOF = HAS("verify_evidence.py")


# ---------------------------------------------------------------- commands (each returns True when it succeeded)

def doctor(o) -> bool:
    head("doctor")
    return R.py("scripts/doctor.py", "--endpoint", ollama.connect(o.ollama_host, "SPRAWL_OLLAMA_HOST"))


def verify(o) -> bool:
    if getattr(o, "public", False) or not FULL_PROOF:
        head("public verification (no model, no article tooling)")
        return R.py("scripts/public_verify.py", *(["--archive", str(Path(o.archive).resolve())] if getattr(o, "archive", None) else []))
    head("proof verification")
    ollama.connect(o.ollama_host, "SPRAWL_OLLAMA_HOST")
    return R.py("scripts/verify_evidence.py", *(["--strict"] if o.strict else []))


def proof(o) -> bool:
    head("proof pack (recompute from the recorded files)")
    return R.py("scripts/proof_pack.py", "build", *(["--write"] if o.write else []))


def promote(o) -> bool:
    head("promote a run to published")
    return R.py("scripts/proof_pack.py", "promote", o.run, "--reason", o.reason, *(["--note", o.note] if o.note else []))


def negative_control(o) -> bool:
    head("negative control (policy removed; recorded decisions, no model)")
    return R.py("scripts/negative_control.py")


def package(o) -> bool:
    head("publication package")
    return R.py("scripts/package_proof.py")


def test(o) -> bool:
    head("deterministic tests (no model)")
    return R.py("-m", "pytest", *(["-k", o.k] if o.k else []))


def build(o) -> bool:
    head("rebuild deterministic inputs")
    before = R.snapshot(BUILD_INPUTS)
    ok = all(R.py("-m", step) for step in BUILD_STEPS)
    changed = R.changed(before, BUILD_INPUTS)
    if not ok or changed:
        R.restore(before, BUILD_INPUTS)
        say(f"  {FAIL} the rebuild differs from the frozen inputs in {len(changed)} file(s); originals restored:")
        for c in changed[:12]:
            say(f"     {c}")
        return False
    say(f"  {OK} rebuilt {len(before)} files, byte-identical to the frozen inputs")
    return True


def run(o) -> bool:
    head("live benchmark run")
    endpoint = ollama.connect(o.ollama_host, "SPRAWL_OLLAMA_HOST")
    p = PRESETS[o.preset]
    split, arms, sizes, cases = o.split or p["split"], o.arms or p["arms"], o.sizes or p["sizes"], o.cases or p["cases"]
    run_id = o.run_id or f"{split}-{o.preset}-{time.strftime('%Y%m%d-%H%M')}"
    out = (RUNS / run_id).resolve()
    if out.parent != RUNS.resolve() or R.is_recorded(out):
        raise SystemExit(f"--run-id {run_id}: a run is a directory directly under experiment/runs/, never recorded evidence")
    if out.exists() and not o.resume:
        raise SystemExit(f"{R.rel(out)} exists: pass --resume to continue it, or choose another --run-id")
    if not R.py("scripts/doctor.py", "--live", "--split", split, *(["--allow-dirty"] if o.allow_dirty else [])):
        return False
    say(f"  model endpoint  {endpoint}")
    say(f"  run             {R.rel(out)}  ·  split {split}  ·  arms {' '.join(arms)}  ·  sizes {' '.join(map(str, sizes))}"
        f"  ·  cases {'all' if not cases else ' '.join(cases)}")
    if split == "blind":
        say(f"  {WARN} the blind set was scored once for the article; a re-run is a new run, reported as its own")
    t0 = time.time()
    bench = ["-m", "sprawl_poc.bench.runner", "--split", split, "--think", o.think]
    extra = (["--cases", *cases] if cases else []) + (["--allow-dirty"] if o.allow_dirty else [])
    ok = R.py(*bench, "--sizes", *map(str, sizes), "--arms", *arms, *extra, "--out", str(out))
    if ok and p.get("repeat"):  # the preregistered repeat pass: C at every size, then B at 500
        rep = str(out.with_name(out.name + "-repeat"))
        ok = R.py(*bench, "--sizes", *map(str, sizes), "--arms", "C", *extra, "--out", rep)
        if ok and 500 in sizes:
            ok = R.py(*bench, "--sizes", "500", "--arms", "B", *extra, "--out", rep)
    say(f"  {OK if ok else FAIL} finished in {(time.time() - t0) / 60:.1f} min")
    return ok and R.py("scripts/summarize.py", "run", str(out))


def replay(o, source=None, cases=None, sizes=None, arms=None, out=None) -> bool:
    head("replay without the model")
    ollama.connect(o.ollama_host, "SPRAWL_OLLAMA_HOST")  # retrieval re-embeds queries; the committed cache normally answers
    src = Path(source or ROOT / next(r["raw"] for r in RECORDED_RUNS if r["id"] == PUBLISHED_RUN)).resolve()
    out = Path(out or RUNS / "replay-latest").resolve()
    if R.is_recorded(out):
        raise SystemExit("the committed replay check is recorded evidence; choose another --out")
    if out.exists() and out.parent == RUNS.resolve():
        shutil.rmtree(out)
    ok = R.py("scripts/verify_replay.py", str(src), "--out", str(out), "--cases", *(cases or REPLAY_CASES),
              "--sizes", *map(str, sizes or [500]), "--arms", *(arms or ["A", "B", "C"]))
    ok = R.py("scripts/summarize.py", "replay", str(out)) and ok
    if not HAS("compare_runs.py"):
        return ok
    return R.py("scripts/compare_runs.py", str(src), str(out)) and ok  # every replayed row, classified against the run it replays


def analyze(o) -> bool:
    head("recompute the preregistered analysis")
    before = R.snapshot(ANALYSIS)
    ok = R.py("scripts/evidence.py") and R.py("scripts/facts.py")
    changed = R.changed(before, ANALYSIS)
    if ok and o.write:
        say(f"  {OK} written; {len(changed)} file(s) changed")
        return True
    R.restore(before, ANALYSIS)
    if not ok or changed:
        say(f"  {FAIL} recomputed analysis differs from the committed files (originals kept):")
        for c in changed:
            say(f"     {c}")
        return False
    say(f"  {OK} recomputed from the raw rows: byte-identical to the committed analysis ({len(before)} files)")
    return True


def report(o) -> bool:
    head("lab console")
    lab = sorted(RECORDED_RUNS, key=lambda r: r["id"] != PUBLISHED_RUN)  # the recorded runs, the published one first
    captured = [p for p in [(ROOT / r["raw"]).resolve() for r in lab] + sorted(RUNS.glob("*")) if (p / "rows.jsonl").exists()]
    runs = [Path(r).resolve() for r in o.runs] if o.runs else captured
    out = Path(o.out).resolve() if o.out else ROOT / "evidence" / "lab-console.html"
    ok = R.py("scripts/evidence_export.py", "--runs", *map(str, runs), "--out", str(out))
    if ok and o.open and not R.in_container:
        webbrowser.open(out.as_uri())
    return ok


def all_steps(o) -> bool:
    steps = [("doctor", lambda: doctor(o)), ("verify", lambda: verify(o)), ("test", lambda: test(o))]
    if o.live:
        steps.append(("run", lambda: run(o)))
    steps += [s for s in [("analyze", lambda: analyze(o)),
                          ("replay", lambda: replay(o, o.source, o.replay_cases, o.replay_sizes, o.replay_arms, o.replay_out)),
                          ("negative-control", lambda: negative_control(o)), ("proof", lambda: proof(o)), ("report", lambda: report(o))]
              if available(s[0])]
    ok = R.pipeline(steps, skip=set(filter(None, (o.skip or "").split(","))), keep_going=o.keep_going, stop={"verify", "run"})
    console = Path(o.out).resolve() if o.out else ROOT / "evidence" / "lab-console.html"
    if console.exists():
        say(f"\n  Lab Console: {R.rel(console)}  (open it in any browser; it works offline)")
    return ok


# ---------------------------------------------------------------- options

NEEDS = {"proof": ["proof_pack.py"], "promote": ["proof_pack.py"], "negative-control": ["negative_control.py"], "package": ["package_proof.py"],
         "analyze": ["evidence.py", "facts.py"], "report": ["evidence_export.py"], "lab": ["evidence_export.py"], "replay": ["verify_replay.py"]}


def available(cmd: str) -> bool:
    return all(HAS(s) for s in NEEDS.get(cmd, []))


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sprawl", description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="examples:\n"
                                        "  uv run sprawl verify                            the proof verification of the published run (seconds)\n"
                                        "  uv run sprawl all                               evidence mode: no model, a few minutes\n"
                                        "  uv run sprawl all --live --preset quick         plus a 12-row live run (4 dev cases x 3 arms)\n"
                                        "  uv run sprawl run --preset full --run-id rerun-1\n"
                                        "  uv run sprawl replay --cases BL-C03-1 --arms C --sizes 500\n"
                                        "  uv run sprawl report --open")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ollama-host", metavar="URL", help="Ollama server (default $SPRAWL_OLLAMA_HOST or http://127.0.0.1:11434)")
    runp = argparse.ArgumentParser(add_help=False)
    runp.add_argument("--preset", choices=sorted(PRESETS), default="quick", help="quick (12 dev rows), full (504 blind rows), protocol (full + repeat pass)")
    runp.add_argument("--split", choices=["dev", "blind"], help="override the preset's case split")
    runp.add_argument("--arms", nargs="+", choices=["A", "B", "C"], help="A all tools, B search only, C control plane")
    runp.add_argument("--sizes", nargs="+", type=int, choices=[50, 100, 500], help="estate sizes (tools)")
    runp.add_argument("--cases", nargs="+", metavar="ID", help="case ids, e.g. DV-C03 BL-C07-1")
    runp.add_argument("--think", default="low", choices=["low", "medium", "high"], help="gpt-oss reasoning effort (preregistered: low)")
    runp.add_argument("--run-id", help="directory name under experiment/runs/ (default <split>-<preset>-<timestamp>)")
    runp.add_argument("--resume", action="store_true", help="continue an interrupted run; finished rows are kept as final")
    runp.add_argument("--allow-dirty", action="store_true", help="permit a blind run from an uncommitted tree (recorded as dirty)")
    repp = argparse.ArgumentParser(add_help=False)
    repp.add_argument("--source", help="recorded run to replay (default: the published run)")
    repp.add_argument("--replay-cases", nargs="+", metavar="ID", help=f"default: {' '.join(REPLAY_CASES)}")
    repp.add_argument("--replay-sizes", nargs="+", type=int, metavar="N", help="default: 500")
    repp.add_argument("--replay-arms", nargs="+", metavar="ARM", help="default: A B C")
    repp.add_argument("--replay-out", help="output directory (default experiment/runs/replay-latest)")
    repo = argparse.ArgumentParser(add_help=False)
    repo.add_argument("--runs", nargs="+", metavar="DIR", help="run directories (default: every captured run)")
    repo.add_argument("--out", help="output HTML (default evidence/lab-console.html)")
    repo.add_argument("--open", action="store_true", help="open the Lab Console in a browser when done")

    sub = ap.add_subparsers(dest="cmd", required=True, metavar="command")
    _add = sub.add_parser
    sub.add_parser = lambda name, **kw: _add(name, **kw) if available(name) else argparse.ArgumentParser(add_help=False)  # absent: not offered
    sub.add_parser("doctor", parents=[common], help="what this machine has: Python, uv, MCP SDK, Ollama and the models")
    v = sub.add_parser("verify", parents=[common], help=("PROOF VERIFICATION of the published run: manifests, frozen inputs, raw evidence, checks, claims, "
                       "integrity, replay, negative control, publication facts, secret scan") if FULL_PROOF else
                       "PUBLIC VERIFICATION without a model: frozen inputs, benchmark, rows, the recomputed analysis and hypotheses, replay, "
                       "request mismatches, the featured trace, the negative control, the public manifest, the Lab")
    v.add_argument("--strict", action="store_true", help="fail when model digests cannot be checked")
    v.add_argument("--public", action="store_true", help="run the public verification (the default where the full proof pack is absent)")
    v.add_argument("--archive", metavar="ZIP", help="check a copy of the full-evidence archive elsewhere (default: evidence/full/)")
    sub.add_parser("proof", parents=[common], help="recompute the published run's proof pack and compare it with the committed one").add_argument(
        "--write", action="store_true", help="write the pack (evidence/runs/<run>/) instead of only comparing")
    pm = sub.add_parser("promote", parents=[common], help="name the published run (the only way evidence/published.json changes run)")
    pm.add_argument("run", help="run id with a written proof pack")
    pm.add_argument("--reason", required=True)
    pm.add_argument("--note", help="when the run changes: the methodology and the material deltas")
    sub.add_parser("negative-control", parents=[common], help="remove the policy from the gateway and show the invariant break (no model)")
    sub.add_parser("package", parents=[common], help="the publication package: dist/f1-proof-pack-<run>.zip, redacted and scanned")
    sub.add_parser("test", parents=[common], help="deterministic tests: real MCP server processes, no model").add_argument("-k", help="pytest -k expression")
    sub.add_parser("build", parents=[common], help="rebuild estates, world and benchmark; keep them only if byte-identical")
    sub.add_parser("run", parents=[common, runp], help="live benchmark run (Ollama) into experiment/runs/<run-id>/")
    r = sub.add_parser("replay", parents=[common], help="replay recorded rows without the model")
    r.add_argument("--source", help="recorded run to replay (default: the published run)")
    r.add_argument("--cases", nargs="+", metavar="ID", help=f"default: {' '.join(REPLAY_CASES)}")
    r.add_argument("--sizes", nargs="+", type=int, help="default: 500")
    r.add_argument("--arms", nargs="+", help="default: A B C")
    r.add_argument("--out", help="output directory (default experiment/runs/replay-latest)")
    sub.add_parser("analyze", parents=[common], help="recompute the analysis and compare it with the committed files").add_argument(
        "--write", action="store_true", help="keep the recomputed files instead of only comparing")
    sub.add_parser("report", parents=[common, repo], help="build the Proof Lab, the Lab Console (evidence/lab-console.html)")
    sub.add_parser("lab", parents=[common, repo], help="the same as report")
    al = sub.add_parser("all", parents=[common, runp, repp, repo], help="doctor, verify, test, [run with --live], analyze, replay, negative-control, proof, report")
    al.add_argument("--live", action="store_true", help="include a live run (uses --preset and the run options)")
    al.add_argument("--skip", metavar="STEPS", help="comma-separated steps to skip, e.g. test,replay")
    al.add_argument("--keep-going", action="store_true", help="continue after a failed verify or run")
    al.add_argument("--strict", action="store_true", help="fail verify when model digests cannot be checked")
    al.add_argument("--write", action="store_true", help="analyze: keep recomputed files")
    al.set_defaults(k=None, public=False, archive=None)
    return ap


def prepare() -> None:
    """Retrieval caches embedding vectors by text hash. The snapshot from the recorded runs is committed, so replay and
    analysis need no model server."""
    cache, snap = R.project / "data" / "embeddings" / "nomic-embed-text.json", R.project / "data" / "embeddings-cache" / "nomic-embed-text.json.gz"
    if cache.exists():
        state = "present"
    elif snap.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(gzip.decompress(snap.read_bytes()))
        state = "restored from the committed snapshot"
    else:
        state = "missing: retrieval will embed through Ollama"
    os.environ["SPRAWL_EMBED_CACHE"] = state  # doctor reports it


COMMANDS = {"doctor": doctor, "verify": verify, "test": test, "build": build, "run": run, "analyze": analyze, "report": report, "lab": report, "all": all_steps,
            "proof": proof, "promote": promote, "negative-control": negative_control, "package": package,
            "replay": lambda o: replay(o, o.source, o.cases, o.sizes, o.arms, o.out)}


def main(argv: list[str] | None = None) -> None:
    o = parser().parse_args(argv)
    prepare()
    sys.exit(0 if COMMANDS[o.cmd](o) else 1)
