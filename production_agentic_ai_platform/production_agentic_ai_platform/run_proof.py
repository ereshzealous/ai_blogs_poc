"""One command, the whole proof.

    uv run python run_proof.py [--run-id ID] [--out DIR]   -> evidence/runs/<ID>/raw/ (or DIR); refuses a directory that holds evidence
    uv run python run_proof.py --source-digest       print the SHA-256 of the proof's source (recorded in every run)

1. runs the unit tests (tests/)
2. for each experiment R1–R13: a fresh directory, INC-4917 seeded, real MCP servers over stdio, the control plane copied and
   signed, the experiment run (real SIGKILLs for R9 and R10), checks recorded as expected vs actual
3. cross-cutting checks over every experiment: canaries in model prompts, key material in evidence, audit chains
4. aggregates the run-level evidence (trace, audit, approvals, policy, capability, events, results, summary)
5. destroys the run's ephemeral keys (the Lab is built from the published run's proof pack: uv run pap lab)
6. exits 1 if any check failed

Nothing here writes a number by hand: every value in results.json is computed from the run.  results.json also records
source_sha256, one digest over every file the proof runs (the SOURCE list below), so a run can be tied to the exact code
and configuration that produced it; --source-digest recomputes it for the tree you have.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import anyio

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from agentic_platform import experiments as X  # noqa: E402
from agentic_platform.harness import new_keys  # noqa: E402
from agentic_platform.observability import verify_chain  # noqa: E402
from agentic_platform.runtime import agent_code_sha256  # noqa: E402

AGG = ("trace", "audit", "approvals", "policy", "capability", "events", "model_io", "context")
SOURCE = ("run_proof.py", "compare_runs.py", "negative_control.py", "pyproject.toml", "uv.lock", "src", "config", "scenarios", "tests")


def source_files() -> list[Path]:
    out: list[Path] = []
    for name in SOURCE:
        p = ROOT / name
        out += [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file() and "__pycache__" not in f.parts and f.name != ".DS_Store")
    return out


def source_sha256() -> str:
    """SHA-256 over (path, SHA-256 of content) of every source file, in path order."""
    h = hashlib.sha256()
    for f in source_files():
        h.update(f.relative_to(ROOT).as_posix().encode() + b"\0" + hashlib.sha256(f.read_bytes()).hexdigest().encode() + b"\n")
    return h.hexdigest()


def unit_tests(run_dir: Path) -> dict:
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={run_dir / 'pytest.junit.xml'}", "tests"],
                       cwd=ROOT, capture_output=True, text=True)
    (run_dir / "pytest.txt").write_text(p.stdout + p.stderr)
    import xml.etree.ElementTree as ET
    ts = ET.parse(run_dir / "pytest.junit.xml").getroot()
    ts = ts if ts.tag == "testsuite" else ts.find("testsuite")
    total, failed = int(ts.get("tests")), int(ts.get("failures")) + int(ts.get("errors"))
    return {"total": total, "passed": total - failed - int(ts.get("skipped")), "failed": failed, "returncode": p.returncode}


async def experiments(run_dir: Path, keys: dict) -> list[dict]:
    """Every experiment runs even if an earlier one fails.  An exception inside an experiment is a harness failure, not a
    finding: it is recorded as a failed check with id <eid>.no_exception and counted in results.json#harness_exceptions."""
    out: list[dict] = []

    async def run(eid: str, title: str, fn, *args) -> dict:
        try:
            r = fn(run_dir, keys, *args)
            r = await r if hasattr(r, "__await__") else r
        except Exception as exc:   # noqa: BLE001 - the proof reports, it does not hide
            import traceback
            r = {"id": eid, "title": title, "question": "", "dir": f"experiments/{eid}", "facts": {}, "status": "FAIL", "passed": 0, "total": 1,
                 "wall_clock_s": None, "harness_exception": True,
                 "checks": [{"id": f"{eid}.no_exception", "claim": "the experiment ran to completion", "expected": "no exception",
                                                   "actual": f"{type(exc).__name__}: {exc}", "passed": False, "traceback": traceback.format_exc()[-2000:]}]}
        out.append(r)
        print(f"  {r['id']:<4} {r['status']}  {r['passed']}/{r['total']}  {r['title']}", flush=True)
        return r

    r1 = await run("R1", "Governed happy path", X.r1)
    for eid, title, fn in (("R2", "Effective authority is an intersection", X.r2), ("R3", "Approval tampering", X.r3), ("R4", "Tool governance", X.r4),
                           ("R5", "Scoped, short-lived capability", X.r5), ("R6", "Budget exhaustion", X.r6)):
        await run(eid, title, fn)
    await run("R7", "Model routing and fallback", X.r7, r1["facts"])
    for eid, title, fn in (("R8", "Context isolation", X.r8), ("R9", "Crash and resume around the approval", X.r9),
                           ("R10", "Lost response and idempotency", X.r10), ("R11", "Control-plane kill switch", X.r11),
                           ("R12", "Prompt injection vs policy", X.r12)):
        await run(eid, title, fn)
    await run("R13", "Trace reconstruction", X.r13, r1["facts"])
    return out


def cross_checks(run_dir: Path, keys: dict) -> list[dict]:
    exp = run_dir / "experiments"
    prompts = [json.loads(l).get("prompt", "") for f in exp.rglob("model_io.jsonl") for l in f.read_text().splitlines() if l.strip()]
    canary_hits = sum(1 for p in prompts for c in X.CANARIES if c in p)
    files = [f for f in exp.rglob("*") if f.is_file() and f.name != ".keys.json"]
    def content(f: Path) -> bytes:
        try:
            return f.read_bytes()
        except FileNotFoundError:   # a SQLite -wal/-shm file removed when its last connection closed: transient state, not evidence
            return b""
    key_hits = sorted({str(f.relative_to(run_dir)) for f in files for v in keys.values() if v.encode() in content(f)})
    chains = [(str(f.relative_to(run_dir)), *verify_chain(f)) for f in exp.rglob("audit.jsonl")]
    broken = [c for c in chains if not c[1]]
    return [
        {"id": "X.canary", "claim": "no canary string (other tenant, restricted document) appears in any model prompt of any experiment",
         "expected": 0, "actual": canary_hits, "passed": canary_hits == 0, "detail": f"{len(prompts)} model prompts scanned"},
        {"id": "X.keys", "claim": "no signing or capability key appears in any evidence file, database or log",
         "expected": [], "actual": key_hits, "passed": not key_hits, "detail": f"{len(files)} files scanned for {len(keys)} keys"},
        {"id": "X.chains", "claim": "every experiment's audit hash chain verifies", "expected": [], "actual": [c[0] for c in broken], "passed": not broken,
         "detail": f"{len(chains)} chains, {sum(c[2] for c in chains)} events"},
    ]


def aggregate(run_dir: Path) -> dict:
    counts = {}
    for name in AGG:
        n = 0
        with (run_dir / f"{name}.jsonl").open("w") as out:
            for f in sorted((run_dir / "experiments").rglob(f"{name}.jsonl")):
                rel = str(f.parent.relative_to(run_dir / "experiments"))
                for line in f.read_text().splitlines():
                    if line.strip():
                        out.write(json.dumps({"experiment_dir": rel, **json.loads(line)}) + "\n")
                        n += 1
        counts[name] = n
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y-%m-%d-proof-%H%M%S"))
    ap.add_argument("--out", type=Path, help="write the run here instead of evidence/runs/<run-id>/raw/")
    ap.add_argument("--no-lab", action="store_true", help="accepted for compatibility: a run no longer rebuilds the Lab (pap lab builds it from the published run)")
    ap.add_argument("--source-digest", action="store_true", help="print the source digest and exit")
    a = ap.parse_args()
    if a.source_digest:
        print(f"{source_sha256()}  ({len(source_files())} files)")
        return 0
    run_dir = a.out.resolve() if a.out else ROOT / "evidence" / "runs" / a.run_id / "raw"
    if run_dir.exists() and any(run_dir.iterdir()):
        raise SystemExit(f"refusing to write into {run_dir.name}/: it already holds a run (recorded evidence is never overwritten); choose another --run-id or --out")
    run_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"proof run {a.run_id}")
    tests = unit_tests(run_dir)
    print(f"  unit tests: {tests['passed']} passed, {tests['failed']} failed")
    keys = new_keys()
    exps = anyio.run(experiments, run_dir, keys)
    xc = cross_checks(run_dir, keys)
    for f in (run_dir / "experiments").rglob(".keys.json"):
        f.unlink()   # keys are ephemeral: destroyed with the run; the hash chains verify without them
    counts = aggregate(run_dir)
    checks = [c for e in exps for c in e["checks"]] + xc
    passed = sum(c["passed"] for c in checks)
    results = {
        "run_id": a.run_id, "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wall_clock_s": round(time.time() - t0, 1),
        "environment": {"python": platform.python_version(), "platform": f"{platform.system()} {platform.machine()}", "mcp_sdk": version("mcp"),
                        "opentelemetry_sdk": version("opentelemetry-sdk"), "mcp_transport": "stdio (real subprocesses, official Python SDK)",
                        "checkpoint_store": "SQLite (WAL)", "model_mode": "deterministic recorded providers (RecordedModelA/B tapes), offline",
                        "tracing": "OpenTelemetry SDK -> JSONL exporter", "policy_engine": "deterministic in-process engine (policies/production.yaml)",
                        "crash_injection": "POSIX SIGKILL of a separate runtime process", "agent_code_sha256": agent_code_sha256(),
                        "source_sha256": source_sha256(), "source_files": len(source_files())},
        "unit_tests": tests,
        "experiments": exps,
        "cross_checks": xc,
        "totals": {"experiments": len(exps), "experiments_passed": sum(e["status"] == "PASS" for e in exps), "checks": len(checks),
                   "passed": passed, "failed": len(checks) - passed},
        "harness_exceptions": [e["id"] for e in exps if e.get("harness_exception")],
        "evidence_counts": counts,
    }
    (run_dir / "results.json").write_text(json.dumps(results, indent=1, default=str))
    summary = {k: results[k] for k in ("run_id", "started_at", "finished_at", "wall_clock_s", "totals", "harness_exceptions", "unit_tests",
                                        "evidence_counts")} | {
        "experiments": [{k: e[k] for k in ("id", "title", "status", "passed", "total")} for e in exps],
        "failed_checks": [c for c in checks if not c["passed"]]}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    md = [f"# Proof run {a.run_id}", "", f"{results['totals']['experiments_passed']}/{len(exps)} experiments passed · "
          f"{passed}/{len(checks)} checks passed · unit tests {tests['passed']} passed, {tests['failed']} failed · "
          f"harness exceptions {len(results['harness_exceptions'])} · {results['wall_clock_s']} s", "",
          "| Experiment | Status | Checks |", "|---|---|---|"]
    md += [f"| {e['id']} · {e['title']} | {e['status']} | {e['passed']}/{e['total']} |" for e in exps]
    md += [f"| Cross-cutting | {'PASS' if all(c['passed'] for c in xc) else 'FAIL'} | {sum(c['passed'] for c in xc)}/{len(xc)} |", ""]
    if summary["failed_checks"]:
        md += ["## Failed checks", ""] + [f"- `{c['id']}` {c['claim']}: expected `{c['expected']}`, got `{c['actual']}`" for c in summary["failed_checks"]]
    (run_dir / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    ok = results["totals"]["failed"] == 0 and tests["failed"] == 0 and tests["returncode"] == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
