"""Run one scenario through one runtime: a fresh simulated enterprise, real worker processes, real SIGKILLs, resume.

    run_one(out_dir, scenario, arm, mutant=None, model_change=None) -> row

The harness is the only place that knows the oracle's fault plan for the process (crash points, provider-time
advance); the runtime knows its fault plan only as an injected crash flag for its first worker.  After the run the
harness collects the providers' ledgers (ground truth), the journal, the telemetry, and per-worker exit codes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .common import POC, write_json, write_jsonl
from .journal import Journal
from .world import World

MAX_WORKERS = 4


def crash_point(sc: dict) -> str | None:
    for f in sc["faults"]:
        if f.startswith("process:"):
            _, point, tool, _ = f.split(":")
            return f"{point}:{tool}"
    return None


def clock_advance(sc: dict) -> int:
    for f in sc["faults"]:
        if f.startswith("clock:advance_before_resume:"):
            return int(f.rsplit(":", 1)[1])
    return 0


def run_one(out: Path, sc: dict, arm: str, mutant: str | None = None, model_change: str | None = None, live: str | None = None) -> dict:
    """live: None | "record" (a real model decides, every answer taped to model-tape.jsonl) | "replay" (answers from the tape)."""
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for p in (out / "journal.db", out / "telemetry" / "spans.jsonl"):
        if p.exists():
            p.unlink()
    tape = out / "model-tape.jsonl"
    if live == "record" and tape.exists():
        tape.unlink()
    lv = None
    if live:
        from .runtime import LIVE_FALLBACK, LIVE_PRIMARY
        lv = {"primary": LIVE_PRIMARY, "fallback": LIVE_FALLBACK, "mode": live, "tape": tape, "run_key": f"{sc['id']}/{arm}"}
    world = World(sc["faults"], model_change=model_change, live=lv)
    port = world.start()
    exits, offset = [], 0
    try:
        for w in range(1, MAX_WORKERS + 1):
            cmd = [sys.executable, "-m", "recovery.runtime", "--run-dir", str(out), "--scenario", sc["id"], "--arm", arm,
                   "--port", str(port), "--worker", str(w)]
            if w == 1 and crash_point(sc):
                cmd += ["--crash", crash_point(sc)]
            if mutant:
                cmd += ["--mutant", mutant]
            if model_change:
                cmd += ["--model-change", model_change]
            if offset:
                cmd += ["--clock-offset-s", str(offset)]
            if live:
                cmd += ["--live"]
            p = subprocess.run(cmd, cwd=POC, capture_output=True, text=True, timeout=120)
            exits.append({"worker": f"w{w}", "exit": p.returncode, "signal": "SIGKILL" if p.returncode == -9 else None,
                          "stderr_tail": p.stderr.strip().splitlines()[-1][:200] if p.returncode not in (0, -9, 75) and p.stderr.strip() else None})
            if p.returncode == 0:
                break
            if p.returncode not in (-9, 75):
                break                                    # a harness anomaly: recorded, never retried silently
            adv = clock_advance(sc)
            if adv and not offset:                       # an outage longer than the provider's idempotency window
                import json
                import urllib.request
                urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/admin/clock", data=json.dumps({"advance_s": adv}).encode(),
                                                              headers={"Content-Type": "application/json"}, method="POST"), timeout=5).read()
                offset = adv
    finally:
        world.stop()
    ledger = world.ledger()
    j = Journal(out / "journal.db")
    dump = j.dump()
    j.close()
    (out / "journal.db").unlink()
    for row in dump["intent"]:
        row.pop("deadline_ms", None)                     # wall-clock: volatile, never part of the compared evidence
    write_json(out / "world" / "ledger.json", {k: v for k, v in ledger.items() if k != "access"})
    write_jsonl(out / "world" / "access.jsonl", ledger["access"])
    write_json(out / "journal.json", {k: v for k, v in dump.items() if k != "event"})
    import json as _j
    write_jsonl(out / "events.jsonl", [{"seq": e["seq"], "worker": e["worker"], "kind": e["kind"], "step": e["step"], **_j.loads(e["data"])}
                                     for e in dump["event"]])
    write_json(out / "workers.json", exits)
    if live == "record" and world.volatile_ms:
        write_json(out / "volatile" / "model-ms.json", world.volatile_ms)
    return {"dir": str(out), "exits": exits}
