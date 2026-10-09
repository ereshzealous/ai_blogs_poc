"""Facts the documents quote that are not in the run's facts.json: replay, tests, telemetry detail.

    python3 tools/derive_facts.py          -> docs/derived-facts.json
    python3 tools/derive_facts.py tests    -> run the POC's tests (no model) and record results/tests.json

Same contract as facts.json: every value carries the file it was computed from; nothing is typed.  build_docs.py merges these
with facts.json (a key may not appear in both).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "observability_governance_poc"
RUN = (POC / "runs" / "PUBLISHED").read_text().strip()
R = POC / "runs" / RUN


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def main() -> None:
    F: dict = {}

    def add(k, v, src):
        F[k] = {"value": v, "source": src}

    rc = json.loads((R / "reports" / "replay-comparison.json").read_text())
    src = f"observability_governance_poc/runs/{RUN}/reports/replay-comparison.json"
    add("x.replay.identical", rc["all_identical"], src)
    add("x.replay.answers", rc["answers_served"], src)
    add("x.replay.misses", rc["tape_misses"], src)
    add("x.replay.run", rc["replay"], src)
    add("x.replay.scenarios", len(rc["scenarios"]), src)
    a = json.loads((R / "drift" / "drift.json").read_text())
    b = json.loads((POC / "runs" / f"{RUN}-replay" / "drift" / "drift.json").read_text())
    add("x.drift.replay_identical", [(r["config"], r["variant"], r["capability"]) for r in a["rows"]] == [(r["config"], r["variant"], r["capability"]) for r in b["rows"]],
        f"observability_governance_poc/runs/{RUN}-replay/drift/drift.json")

    t = json.loads((ROOT / "results" / "tests.json").read_text())
    add("x.tests.passed", t["passed"], "results/tests.json")
    add("x.tests.total", t["total"], "results/tests.json")

    walls = [r["wall_s"] for p in (R / "scenarios").glob("*/tape/*/model_tape.jsonl") for r in jl(p) if r.get("path") == "/api/chat"]
    walls.sort()
    add("x.model.median_s", round(walls[len(walls) // 2], 1), f"observability_governance_poc/runs/{RUN}/scenarios/*/tape/*/model_tape.jsonl")
    procs = sum(len(json.loads((d / "procs" / "supervisor.json").read_text())) for d in (R / "scenarios").iterdir())
    add("x.agent_processes", procs, f"observability_governance_poc/runs/{RUN}/scenarios/*/procs/supervisor.json")
    add("x.processes_total", procs + 2 * len(list((R / "scenarios").iterdir())), f"observability_governance_poc/runs/{RUN}/scenarios/*/procs/")
    reqs = sum(len(json.loads((d / "world" / "external-transactions.json").read_text())) for d in (R / "scenarios").iterdir())
    add("x.deploy_requests", reqs, f"observability_governance_poc/runs/{RUN}/scenarios/*/world/external-transactions.json")
    logs = sum(len(jl(p)) for p in (R / "scenarios").glob("*/logs/*.log"))
    add("x.log_lines", logs, f"observability_governance_poc/runs/{RUN}/scenarios/*/logs/*.log")
    e12 = R / "scenarios" / "e12a-lost-response" / "evidence" / "audit-events.jsonl"
    rows = jl(e12)
    x = next(r["execution_id"] for r in rows if r["event_type"] == "execution.started" and not json.loads(r["payload_json"])["background"])
    add("x.e12a.target_events", sum(1 for r in rows if r["execution_id"] == x), str(e12.relative_to(ROOT)))
    tl = json.loads((R / "reports" / "timeline.json").read_text())
    appr = [e for e in tl if e["event"].startswith("approval.")]
    add("x.e12a.approval_wait_s", round(appr[-1]["t_plus_s"] - appr[0]["t_plus_s"], 2), f"observability_governance_poc/runs/{RUN}/reports/timeline.json")
    model = next(e for e in tl if e["event"] == "model.invoked")
    add("x.e12a.model_s", round(model["t_plus_s"], 1), f"observability_governance_poc/runs/{RUN}/reports/timeline.json")
    retry = [e for e in tl if e["event"] == "attempt.started"]
    add("x.e12a.retry_gap_ms", round((retry[1]["t_plus_s"] - [e for e in tl if e["event"] == "attempt.finished"][0]["t_plus_s"]) * 1000), f"observability_governance_poc/runs/{RUN}/reports/timeline.json")
    add("x.run.id", RUN, f"observability_governance_poc/runs/{RUN}/manifest.json")
    m = json.loads((R / "manifest.json").read_text())
    add("x.run.preregistration", m["preregistration_sha256"][:19], f"observability_governance_poc/runs/{RUN}/manifest.json")
    env = json.loads((R / "environment.json").read_text())
    add("x.env.otel", env["opentelemetry-sdk"], f"observability_governance_poc/runs/{RUN}/environment.json")
    add("x.env.ollama", (env.get("ollama") or {}).get("version") if isinstance(env.get("ollama"), dict) else env.get("ollama"), f"observability_governance_poc/runs/{RUN}/environment.json")
    add("x.env.python", env["python"], f"observability_governance_poc/runs/{RUN}/environment.json")
    pr = json.loads((R / "reports" / "predictions.json").read_text())
    src = f"observability_governance_poc/runs/{RUN}/reports/predictions.json"
    for x in pr["predictions"]:
        k = x["id"].lower()
        add(f"x.{k}.text", x["text"], src)
        add(f"x.{k}.held", "held" if x["held"] else "MISSED", src)
        add(f"x.{k}.evidence", x["evidence"], src)
    tel = json.loads((R / "reports" / "telemetry.json").read_text())
    add("x.spans.per_execution_max", max(v["spans"] for v in tel["per_scenario"].values()), f"observability_governance_poc/runs/{RUN}/reports/telemetry.json")
    mt = json.loads((R / "telemetry" / "metrics.json").read_text())
    msrc = f"observability_governance_poc/runs/{RUN}/telemetry/metrics.json"
    for key, name in (("lineage.tool.attempts{capability=deployment.rollback,result=COMMITTED}", "x.m.committed"),
                      ("lineage.tool.attempts{capability=deployment.rollback,result=TIMEOUT}", "x.m.timeout"),
                      ("lineage.tool.attempts{capability=deployment.rollback,result=REPLAYED}", "x.m.replayed"),
                      ("lineage.tool.attempts{capability=deployment.rollback,result=UNAVAILABLE}", "x.m.unavailable"),
                      ("lineage.effects.unverified{capability=deployment.rollback}", "x.m.unverified"),
                      ("lineage.tool.unknown_outcomes{capability=deployment.rollback}", "x.m.unknown")):
        add(name, int(mt.get(key, 0)), msrc)
    out = ROOT / "docs" / "derived-facts.json"
    out.write_text(json.dumps(F, indent=1))
    print(out.relative_to(ROOT), len(F), "facts")


def record_tests() -> None:
    p = subprocess.run(["uv", "run", "pytest"], cwd=POC, capture_output=True, text=True, env={**__import__("os").environ, "OLLAMA_URL": "http://127.0.0.1:1"})
    last = [l for l in p.stdout.splitlines() if " passed" in l or " failed" in l][-1]
    passed = int(re.search(r"(\d+) passed", last).group(1)) if "passed" in last else 0
    failed = int(re.search(r"(\d+) failed", last).group(1)) if "failed" in last else 0
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "tests.json").write_text(json.dumps({"command": "cd observability_governance_poc && OLLAMA_URL=http://127.0.0.1:1 uv run pytest",
                                                             "passed": passed, "failed": failed, "total": passed + failed,
                                                             "summary": last.strip("= ").strip()}, indent=1))
    print("tests:", last.strip("= "))
    subprocess.run(["rm", "-rf", str(POC / "runs" / "_smoke")])


if __name__ == "__main__":
    if sys.argv[1:] == ["tests"]:
        record_tests()
    else:
        main()
