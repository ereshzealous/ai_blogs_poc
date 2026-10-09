"""pap: the capstone POC's command line (Production AI Engineering Proof Contract v1). Every make target calls it.

    uv run pap verify [--run R]            PROOF VERIFICATION of the published run (or a candidate): reads the shipped evidence
    uv run pap test                        the unit tests (implementation tests, not proof checks)
    uv run pap proof [--run-id ID]         a fresh proof into a new run: run, replay, negative control, pack, verify (never published)
    uv run pap run --run-id ID             the experiments only, into evidence/runs/<ID>/raw/
    uv run pap replay [--run R]            replay a run: a second run from a fresh start, classified against it
    uv run pap negative-control [--run R]  the approval requirement removed: the invariant must break cleanly
    uv run pap pack [--run R] [--write]    recompute a run's proof pack and compare it byte for byte (or write it)
    uv run pap promote RUN --reason --note the only way evidence/published.json changes run
    uv run pap lab                         the Proof Lab of the published run (lab/index.html)
    uv run pap package                     the publication package: redacted, scanned, hashed
    uv run pap all                         test, verify, replay and negative control into scratch, pack, lab

cli.py decides what runs and in which order; every rule lives in a step under tools/ (or run_proof.py,
negative_control.py), called by name. A recorded run is never overwritten: a replay or a control of a run that already
has one goes to evidence/local/ (scratch, never published) and is compared with the recorded one.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runner"))
from experiment_runner import OK, FAIL, Runner, head, say  # noqa: E402

R = Runner(ROOT, project=".", recorded=("evidence/runs",))
RUNS = ROOT / "evidence" / "runs"
LOCAL = ROOT / "evidence" / "local"


def published() -> str:
    return json.loads((ROOT / "evidence" / "published.json").read_text())["run_id"]


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def recorded(p: Path) -> bool:
    return p.exists() and any(p.iterdir())


def run_into(run_id: str, out: Path | None = None) -> bool:
    """run_proof.py with its terminal output kept beside the run (raw/run-output.txt)."""
    args = ["run_proof.py", "--run-id", run_id] + (["--out", str(out)] if out else [])
    say("$ python " + " ".join(args))
    p = subprocess.run([*R.python(), *args], cwd=ROOT, capture_output=True, text=True)
    print(p.stdout + p.stderr, end="")
    dest = (out or RUNS / run_id / "raw")
    if dest.exists():
        (dest / "run-output.txt").write_text(p.stdout + p.stderr)
    return p.returncode == 0


def verify(o) -> bool:
    head("proof verification")
    return R.py("tools/verify_evidence.py", *(["--run", o.run] if getattr(o, "run", None) else []))


def test(o) -> bool:
    head("unit tests (implementation tests, not proof checks)")
    return R.py("-m", "pytest", "-q", "-p", "no:cacheprovider")


def run(o) -> bool:
    head(f"fresh run {o.run_id}")
    if (RUNS / o.run_id).exists():
        raise SystemExit(f"evidence/runs/{o.run_id} exists: recorded evidence is never overwritten")
    return run_into(o.run_id)


def replay(o) -> bool:
    rid = o.run or published()
    target = RUNS / rid / "replay" / "raw"
    if not recorded(target):
        head(f"replay of {rid}: a second run from a fresh start")
        ok = run_into(f"{rid}-replay", target)
        return R.py("tools/replay_compare.py", rid) and ok
    out = LOCAL / f"replay-{rid}-{stamp()}"
    head(f"replay of {rid} into scratch (its recorded replay stays as it is)")
    ok = run_into(f"{rid}-replay-local", out / "raw")
    return R.py("tools/replay_compare.py", rid, "--replay", str(out / "raw"), "--out", str(out / "replay.json")) and ok


def negative_control(o) -> bool:
    rid = o.run or published()
    if not recorded(RUNS / rid / "negative-control" / "raw"):
        head(f"negative control of {rid}: the approval requirement removed")
        return R.py("negative_control.py", "--run", rid)
    head(f"negative control into scratch ({rid}'s recorded control stays as it is)")
    return R.py("negative_control.py", "--out", str(LOCAL / f"negative-control-{stamp()}"))


def pack(o) -> bool:
    rid = o.run or published()
    head(f"proof pack of {rid}" + (" (write)" if o.write else " (recompute and compare)"))
    return R.py("tools/proof_pack.py", "build", rid, *(["--write"] if o.write else ["--shipped"]))


def proof(o) -> bool:
    rid = o.run_id or f"local-{stamp()}"
    head(f"fresh proof {rid}: run, replay, negative control, pack, verify (never published)")
    if (RUNS / rid).exists():
        raise SystemExit(f"evidence/runs/{rid} exists: recorded evidence is never overwritten")
    steps = [("run", lambda: run_into(rid)),
             ("replay", lambda: replay(argparse.Namespace(run=rid))),
             ("negative-control", lambda: negative_control(argparse.Namespace(run=rid))),
             ("pack", lambda: R.py("tools/proof_pack.py", "build", rid, "--write")),
             ("verify", lambda: R.py("tools/verify_evidence.py", "--run", rid, "--no-write"))]
    return R.pipeline(steps, skip=set(), keep_going=True, stop=set())


def promote(o) -> bool:
    head(f"promote {o.run}")   # the only way evidence/published.json changes run
    return R.py("tools/proof_pack.py", "promote", o.run, "--reason", o.reason, *(["--note", o.note] if o.note else []))


def lab(o) -> bool:
    head("the Proof Lab of the published run")
    return R.py("lab/build_lab.py")


def package(o) -> bool:
    head("publication package")
    return R.py("tools/package_proof.py")


def all_steps(o) -> bool:
    ns = argparse.Namespace(run=None, write=False)
    steps = [("test", lambda: test(o)), ("verify", lambda: verify(ns)), ("replay", lambda: replay(ns)),
             ("negative-control", lambda: negative_control(ns)), ("pack", lambda: pack(ns)), ("lab", lambda: lab(o))]
    return R.pipeline(steps, skip=set(filter(None, (o.skip or "").split(","))), keep_going=o.keep_going, stop={"verify"})


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pap", description="Production Agentic AI Platform POC · Proof Contract v1 commands")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="PROOF VERIFICATION of the published run")
    v.add_argument("--run")
    sub.add_parser("test", help="the unit tests")
    p = sub.add_parser("proof", help="a fresh proof into a new run (never published)")
    p.add_argument("--run-id")
    r = sub.add_parser("run", help="the experiments only")
    r.add_argument("--run-id", required=True)
    for name in ("replay", "negative-control"):
        s = sub.add_parser(name)
        s.add_argument("--run")
    k = sub.add_parser("pack", help="recompute a run's proof pack and compare it (or write it)")
    k.add_argument("--run")
    k.add_argument("--write", action="store_true")
    m = sub.add_parser("promote", help="name the published run")
    m.add_argument("run")
    m.add_argument("--reason", required=True)
    m.add_argument("--note")
    sub.add_parser("lab", help="the Proof Lab")
    sub.add_parser("package", help="the publication package")
    a = sub.add_parser("all", help="the pipeline")
    a.add_argument("--skip")
    a.add_argument("--keep-going", action="store_true")
    return ap


COMMANDS = {"verify": verify, "test": test, "proof": proof, "run": run, "replay": replay, "negative-control": negative_control, "pack": pack,
            "promote": promote, "lab": lab, "package": package, "all": all_steps}


def main(argv: list[str] | None = None) -> None:
    o = parser().parse_args(argv)
    ok = COMMANDS[o.cmd](o)
    say(f"\n{OK if ok else FAIL}  pap {o.cmd}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
