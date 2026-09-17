"""Reports for one experiment run: HTML, Markdown and JSON, written to runs/<run-id>/report/.

    uv run python -m experiments.report --run-id 2026-09-17

`experiments.run all` calls this at the end of every run. It reads only files under runs/<run-id>/ (plus the change
patches), shows whichever stages the run contains, and never calls a model.

    report/index.html     everything: every run, check, checkpoint, retry, patch and log line
    report/summary.md     the headline numbers and each stage's outcome
    report/results.json   the same numbers, machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import statistics
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_platform.channels.html_report import (
    AGENT_TONE, CHECKS, chip, code, details, esc, fnum, gantt, hbars, hms, jcompact, kv, lanes, legend, note, ok_chip, page,
    pre, repaired, scrub, section, stat, table, trace_tree, ts, workflow_body,
)

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


def load(p: Path) -> Any:
    return json.loads(p.read_text())


def med(xs: list[float]) -> float:
    return statistics.median(xs) if xs else 0


# ------------------------------------------------------------------ inputs
def stages_of(base: Path) -> list[dict[str, Any]]:
    """runs/<id>/stages.json, written by experiments.run; older runs fall back to the console log."""
    if (base / "stages.json").exists():
        return load(base / "stages.json")
    log = console_log(base)
    out, open_ = [], {}
    for m in re.finditer(r"=== STAGE (\w+) (START|OK|FAILED) (\d\d:\d\d:\d\d)", log):
        t = ts(f"{base.name}T{m.group(3)}+00:00") if re.match(r"\d{4}-\d\d-\d\d$", base.name) else 0
        if m.group(2) == "START":
            open_[m.group(1)] = t
        else:
            out.append({"stage": m.group(1), "start": open_.pop(m.group(1)), "end": t, "ok": m.group(2) == "OK"})
    return out


def console_log(base: Path) -> str:
    p = base / "run.log"
    return scrub(p.read_text()) if p.exists() else ""


def sittings_of(base: Path) -> list[dict[str, Any]]:
    """runs/<id>/tests/sittings.json lists each pytest sitting: a JUnit XML file or a `pytest -rA` log."""
    p = base / "tests" / "sittings.json"
    if not p.exists():
        return []
    out = []
    for s in load(p):
        f = base / "tests" / s["file"]
        results: list[dict[str, Any]] = []
        if s["kind"] == "junit" and f.exists():
            for tc in ET.parse(f).getroot().iter("testcase"):
                bad = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
                skipped = tc.find("skipped") is not None
                results.append({"file": tc.get("classname", "").split(".")[-1], "name": tc.get("name", ""),
                                "outcome": "skipped" if skipped else ("failed" if bad is not None else "passed"),
                                "seconds": float(tc.get("time") or 0), "message": scrub((bad.get("message") or "")[:400]) if bad is not None else ""})
        elif f.exists():
            text = f.read_text()
            for m in re.finditer(r"^(PASSED|FAILED|ERROR|SKIPPED) tests/(\w+)\.py::(\w+)", text, re.M):
                results.append({"file": m.group(2), "name": m.group(3), "outcome": m.group(1).lower(), "seconds": None, "message": ""})
            line = re.search(r"^=*\s*(\d+ (?:passed|failed).*? in [\d.]+s.*?)\s*=*$", text, re.M)
            s = s | {"summary": line.group(1) if line else ""}
            err = re.search(r"^E\s+(\S*(?:Error|Expired|Exception)\b.*)$", text, re.M)
            if err:
                s = s | {"error": scrub(err.group(1))[:400]}
        out.append(s | {"results": results})
    return out


def contracts_of(base: Path) -> list[tuple[str, bool]]:
    """Contract results from the recorded lint-imports output, which wraps long names onto a second line."""
    p = base / "tests" / "lint-imports.log"
    if not p.exists():
        return []
    out, pending = [], ""
    for line in p.read_text().splitlines():
        if not line.strip() or line.startswith(("-", "=", "Contracts:", "Analyzed", "Import Linter")):
            pending = ""
            continue
        pending = f"{pending} {line.strip()}".strip()
        m = re.match(r"^(.+?) (KEPT|BROKEN)(?: \(\d+ ignored imports?\))?$", pending)
        if m:
            out.append((m.group(1), m.group(2) == "KEPT"))
            pending = ""
    return out


def contract_renames(recorded: list[tuple[str, bool]]) -> list[tuple[str, str]]:
    """(recorded name, current name) for contracts renamed in .importlinter since the run, matched by position."""
    current = re.findall(r"^name = (.+)$", (ROOT / ".importlinter").read_text(), re.M)
    if len(current) != len(recorded):
        return []
    return [(old, new) for (old, _), new in zip(recorded, current) if old != new]


def change_scope_of(base: Path) -> dict[str, Any] | None:
    for p in (base / "change-scope.json", RUNS / "change-scope.json"):
        if p.exists():
            return load(p)
    return None


# ------------------------------------------------------------------ numbers (shared by all three outputs)
def collect(base: Path) -> dict[str, Any]:
    d: dict[str, Any] = {"run_id": base.name, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    d["stages"] = stages_of(base)
    if (base / "run.json").exists():
        d["meta"] = load(base / "run.json")
    if (base / "tests.json").exists():
        d["tests"] = load(base / "tests.json")
    if (base / "workflow" / "summary.json").exists():
        wf = load(base / "workflow" / "summary.json")
        d["workflow"] = {m: {"runs": s["runs"], "completed": s["completed"], "all_checks_passed": s["eval_all_pass"],
                             "median_seconds_to_approval": med(s["seconds_to_approval"]),
                             "median_seconds_after_approval": med([t - a for t, a in zip(s["seconds_total"], s["seconds_to_approval"])]),
                             "median_tokens": med(s["tokens"]), "median_model_calls": med(s["model_calls"]),
                             "median_tool_calls": med(s["tool_calls"]), "check_pass": s["check_pass"]} for m, s in wf.items()}
        recs = [load(p) for p in sorted((base / "workflow").glob("*/run*/record.json"))]
        d["remediation_repairs"] = {"repaired": sum(repaired(r) for r in recs), "runs": len(recs)}
    if (base / "faults" / "summary.json").exists():
        f = load(base / "faults" / "summary.json")
        d["faults"] = {"status": f["status"], "evals": f"{f['eval']['passed']}/{f['eval']['total']}", "rollback": f["rollback"],
                       "latency_read_attempts": max((v["attempts"] for v in f["verify_latency_calls"]), default=None),
                       "timeouts_in_audit": f["timeouts_in_audit"]}
    if (base / "crash" / "summary.json").exists():
        c = load(base / "crash" / "summary.json")
        d["crash"] = {k: c[k] for k in ("workflow_id", "processes", "backend_rollbacks", "model_calls_before_crash",
                                        "model_calls_after_resume", "tokens_before_crash", "tokens_after_crash")}
        d["crash"] |= {"status_after_first_kill": c["run"]["status_after"], "final_status": c["resume"]["status"],
                       "remediation_replayed": c["resume"]["remediation_replayed"]}
    if (base / "monolith" / "summary.json").exists():
        m = load(base / "monolith" / "summary.json")
        d["monolith"] = {"runs": len(m["runs"]), "median_seconds": med([r["seconds"] for r in m["runs"]]),
                         "median_tokens": med([r["tokens"] for r in m["runs"]]), "kubernetes_rollbacks": m["kubernetes_rollbacks"],
                         "lost_response_rollbacks": m["lost_response"]["world"]["rollback_executions"],
                         "crash_seconds_to_prompt": m["crash"]["seconds_until_approval_prompt"],
                         "crash_state_left": m["crash"]["state_left_behind"]}
    cs = change_scope_of(base)
    if cs:
        d["change_scope"] = [{"id": c["id"], "title": c["title"],
                              **{side: {k: c[side].get(k) for k in ("files", "added", "removed", "concerns", "applies", "compiles", "imports", "contracts_kept")}
                                 for side in ("monolith", "layered")}} for c in cs["changes"]]
    return d


# ------------------------------------------------------------------ HTML sections
def s_overview(base: Path, d: dict[str, Any]) -> str:
    tiles = []
    t = d.get("tests")
    if t:
        tiles.append(stat("Tests passed", str(t["passed"]), f'{t.get("fast", "?")} fast · {t.get("ollama", 0)} against local models', "green"))
    if d["stages"]:
        span = int(max(s["end"] for s in d["stages"]) - min(s["start"] for s in d["stages"]))
        tiles.append(stat("Stages", f'{sum(s["ok"] for s in d["stages"])}/{len(d["stages"])} OK', f"{span // 60} min wall time", "blue"))
    if "workflow" in d:
        w = d["workflow"]
        tiles.append(stat("Platform runs, all 8 checks", f'{sum(m["all_checks_passed"] for m in w.values())}/{sum(m["runs"] for m in w.values())}',
                          " · ".join(f'{k} {m["all_checks_passed"]}/{m["runs"]}' for k, m in w.items()), "purple"))
    if "monolith" in d and "faults" in d:
        tiles.append(stat("Rollbacks after a lost response", f'{d["monolith"]["lost_response_rollbacks"]} → {d["faults"]["rollback"]["backend_executions"]}',
                          "monolith → platform", "red"))
    if "crash" in d:
        c = d["crash"]
        tiles.append(stat("SIGKILL crashes survived", str(c["processes"] - 1),
                          f'{c["processes"]} processes · {c["backend_rollbacks"]} rollback · replayed {str(c["remediation_replayed"]).lower()}', "orange"))
    if d.get("change_scope") and len(d["change_scope"]) > 1:
        sm = d["change_scope"][1]
        tiles.append(stat("Concerns touched, model swap", f'{len(sm["monolith"]["concerns"])} → {len(sm["layered"]["concerns"])}', "monolith → platform", "teal"))
    log = console_log(base)
    m = d.get("meta") or {}
    about = ""
    if m:
        mode = "live, model traffic recorded" if m.get("recorded") else "live"
        if m.get("mode") == "replay":
            mode = f"replay of runs/{m.get('replay_from')}"
        about = kv([("Run", f'{esc(mode)} · profile {esc(m.get("profile", "custom"))} · models {esc(", ".join(m.get("models", [])))} · '
                            f'{m.get("k")} run(s) per scenario · model tests {"on" if m.get("model_tests") else "off"}'),
                    ("When", f'{esc(m.get("started", ""))} → {esc(m.get("finished", "running"))} · {esc(m.get("host", {}).get("platform", ""))}, '
                             f'Python {esc(m.get("host", {}).get("python", ""))}')]
                   + ([("Re-run", " · ".join(f'{esc(x["what"])}{" (resume)" if x.get("resume") else ""}, {esc(x["mode"])}, {esc(x["at"])}'
                                             for x in m["reruns"]))] if m.get("reruns") else []))
    body = about + f'<div class="stats">{"".join(tiles)}</div>'
    if d["stages"]:
        body += "<h3>How the run unfolded</h3>" + gantt(d["stages"])
        body += table(["Stage", "Started (UTC)", "Duration", "Result"],
                      [[esc(s["stage"]), datetime.fromtimestamp(s["start"], timezone.utc).strftime("%H:%M:%S"),
                        f'{int(s["end"] - s["start"]) // 60}m {int(s["end"] - s["start"]) % 60:02d}s', ok_chip(s["ok"], "OK", "FAILED")] for s in d["stages"]])
    if log:
        body += details("Console log of the whole run (<code>run.log</code>)", pre(log, "log"))
    return body


def s_tests(base: Path, d: dict[str, Any]) -> str:
    parts = []
    for s in sittings_of(base):
        res = s["results"]
        counts = Counter(r["outcome"] for r in res)
        head = f'<h3>{esc(s["label"])}</h3><p>{esc(s.get("date", ""))} · <code>{esc(s["file"])}</code> · ' + " ".join(
            chip(f"{n} {k}", "green" if k == "passed" else "red" if k in ("failed", "error") else "gray") for k, n in counts.items()) + "</p>"
        if s.get("note"):
            head += f'<p>{esc(s["note"])}</p>'
        if s.get("summary"):
            head += f'<p class="small">pytest: <em>{esc(s["summary"])}</em></p>'
        rows = [[code(r["file"], nowrap=True), esc(r["name"].replace("_", " ")),
                 ok_chip(r["outcome"] == "passed", "pass", r["outcome"]) if r["outcome"] != "skipped" else chip("skipped", "gray"),
                 f'<span class="nw">{r["seconds"]:.2f} s</span>' if r["seconds"] is not None else "", esc(r["message"])] for r in res]
        parts.append(head + table(["File", "Test", "Result", "Time", "Message"], rows, "num")
                     + (details("Error reported by pytest", pre(s["error"])) if s.get("error") else ""))
    cs = contracts_of(base)
    if cs:
        parts.append(f"<h3>Layer contracts: {sum(ok for _, ok in cs)} of {len(cs)} kept</h3>"
                     + table(["Contract (import-linter)", "Result"], [[esc(n), ok_chip(ok, "kept", "broken")] for n, ok in cs])
                     + "".join(note(f"Names are as recorded with this run. Renamed since: “{esc(old)}” is now “{esc(new)}”.")
                               for old, new in contract_renames(cs)))
    if not parts:
        parts.append("<p>No test results were recorded with this run. Run <code>experiments.run tests</code> to add them.</p>")
    return "".join(parts)


def s_workflow(base: Path, d: dict[str, Any]) -> str:
    models = list(d["workflow"])
    records = {m: [load(p) for p in sorted((base / "workflow" / m.replace(":", "_")).glob("run*/record.json"))] for m in models}
    all_recs = [r for rs in records.values() for r in rs]
    mono = load(base / "monolith" / "summary.json") if (base / "monolith" / "summary.json").exists() else None
    rows_t, rows_k = [], []
    for m, rs in records.items():
        for i, r in enumerate(rs, 1):
            to, tot = r["seconds_to_approval"], r["seconds_total"]
            rows_t.append((f"{m} · run {i}", [(to, "purple", f"to approval {to:.1f} s"), (max(tot - to, 0), "green", f"after approval {tot - to:.1f} s")], f"{tot:.1f} s"))
            by = Counter()
            for u in r["usage"]:
                by[u["agent"]] += u["input_tokens"] + u["output_tokens"]
            rows_k.append((f"{m} · run {i}", [(by[a], AGENT_TONE[a], f"{a} {by[a]:,}") for a in AGENT_TONE], f'{sum(by.values()):,} tokens · {len(r["usage"])} calls'))
    for i, r in enumerate((mono or {}).get("runs", []), 1):
        rows_t.append((f"monolith · run {i}", [(r["seconds"], "gray", f"whole run {r['seconds']} s")], f'{r["seconds"]:.1f} s'))
        rows_k.append((f"monolith · run {i}", [(r["tokens"], "gray", f"whole run {r['tokens']:,}")], f'{r["tokens"]:,} tokens'))
    summary_rows = [[code(m, nowrap=True), f'{s["completed"]}/{s["runs"]}', f'{s["all_checks_passed"]}/{s["runs"]}', f'{s["median_seconds_to_approval"]:.1f} s',
                     f'{s["median_seconds_after_approval"]:.1f} s', fnum(s["median_tokens"]), f'{s["median_model_calls"]:g}', f'{s["median_tool_calls"]:g}']
                    for m, s in d["workflow"].items()]
    fault = load(base / "faults" / "record.json") if (base / "faults" / "record.json").exists() else None
    cols = all_recs + ([fault] if fault else [])
    head = ["Check", "Kind"] + [f"{m.split(':')[0]} {i}" for m, rs in records.items() for i in range(1, len(rs) + 1)] + (["faults run"] if fault else [])
    matrix = []
    for name, lbl, kind in CHECKS:
        cells = []
        for r in cols:
            c = next((c for c in r["eval"]["checks"] if c["name"] == name), {"passed": False, "detail": "not evaluated"})
            cells.append(f'<span class="dot {"ok" if c["passed"] else "no"}" title="{esc(c["detail"])}">{"✓" if c["passed"] else "✕"}</span>')
        matrix.append([esc(lbl), chip(kind, "purple" if kind == "reasoning" else "blue")] + cells)
    rp = d["remediation_repairs"]
    body = (table(["Model", "Completed", "All 8 checks", "Median to approval", "Median after approval", "Median tokens", "Model calls", "Tool calls"], summary_rows, "num")
            + "<h3>Wall time per run</h3>" + hbars(rows_t, " s")
            + legend([("to the approval request", "purple"), ("after approval", "green"), ("monolith, whole run (auto-approved)", "gray")])
            + "<h3>Tokens per run, by agent</h3>" + hbars(rows_k, "")
            + legend([("diagnosis agent", "purple"), ("remediation agent", "blue"), ("summary agent", "teal"), ("monolith, whole run", "gray")])
            + "<h3>Eval checks, run by run</h3>" + table(head, matrix, "matrix"))
    if rp["repaired"]:
        body += note(f"<strong>Finding.</strong> In {rp['repaired']} of {rp['runs']} runs the remediation agent's first structured answer failed "
                     "validation, and its one bounded repair fixed it. Nothing malformed reached the policy check, but each repair cost an extra model call.")
    sup = sorted((base / "workflow" / "_superseded").glob("*/*/record.json"))
    if sup:
        body += ("<h3>Superseded attempts</h3><p>Earlier attempts at a run that was later repeated. They are kept for the record and "
                 "left out of the numbers above.</p>"
                 + table(["Attempt", "Model", "Status", "Evals", "Time", "Error"],
                         [[code(p.parent.relative_to(base), nowrap=True), code(x["model"], nowrap=True), chip(x["status"], "green" if x["status"] == "COMPLETED" else "red"),
                           f'{x["eval"]["passed"]}/{x["eval"]["total"]}', f'{x["seconds_total"]:.1f} s', esc(x.get("error") or "")]
                          for p in sup for x in [load(p)]]))
    body += "<h3>Every run in full</h3><p>Open a run for its diagnosis, tool and model calls, policy decision, approval, backend result, events, audit log and trace.</p>"
    body += "".join(details(f'<b>{esc(m)}</b> · run {i} · {esc(r["status"])} · {r["eval"]["passed"]}/{r["eval"]["total"]} · {r["seconds_total"]:.1f} s · {esc(r["workflow_id"])}',
                            workflow_body(r), cls="run") for m, rs in records.items() for i, r in enumerate(rs, 1))
    return body


def s_crash(base: Path, d: dict[str, Any]) -> str:
    c = load(base / "crash" / "summary.json")
    db = sqlite3.connect(base / "crash" / "platform.db")
    db.row_factory = sqlite3.Row
    wf = c["workflow_id"]
    events = [dict(r) | json.loads(r["payload"]) for r in db.execute("SELECT id, type, payload, pid, at FROM workflow_events WHERE workflow_id=? ORDER BY id", (wf,))]
    cps = [dict(r) for r in db.execute("SELECT seq, step, next_step, pid, at FROM checkpoints WHERE workflow_id=? ORDER BY seq", (wf,))]
    use = [dict(r) for r in db.execute("SELECT id, agent, model, input_tokens, output_tokens, latency_ms, at FROM model_usage WHERE workflow_id=? ORDER BY id", (wf,))]
    tid = db.execute("SELECT trace_id FROM workflows WHERE id=?", (wf,)).fetchone()[0]
    pid_no = {p: i + 1 for i, p in enumerate(dict.fromkeys(e["pid"] for e in events))}
    t0 = ts(events[0]["at"]) if events else 0
    spans = [json.loads(line) for p in sorted((base / "crash" / "otel" / "traces").glob("*.jsonl")) for line in p.read_text().splitlines() if line.strip()]
    mine = [s for s in spans if s["trace_id"] == tid]
    startup = Counter(s["name"] for s in spans if s["trace_id"] != tid)
    return (
        kv([("Workflow", code(wf)),
            ("Process 1", f'{code("lap run INC-4917")} with {code("LAP_CRASH_ON=after_step:await_approval")} → exit {c["run"]["returncode"]} after {c["run"]["seconds"]} s; status afterwards {chip(c["run"]["status_after"], "orange")}'),
            ("Process 2", f'{code("lap approve")} with {code("LAP_CRASH_ON=executed:source_control.rollback_release")} → exit {c["approve"]["returncode"]} after {c["approve"]["seconds"]} s; '
                          f'backend rollbacks {c["approve"]["backend_rollbacks_after_crash"]}; status {chip(c["approve"]["status_after"], "orange")}'),
            ("Process 3", f'{code("lap resume")} → exit {c["resume"]["returncode"]} after {c["resume"]["seconds"]} s; {chip(c["resume"]["status"], "green" if c["resume"]["status"] == "COMPLETED" else "red")}; '
                          f'remediation replayed {c["resume"]["remediation_replayed"]}'),
            ("Result", f'backend rollbacks <strong>{c["backend_rollbacks"]}</strong> · model calls before the first kill {c["model_calls_before_crash"]} '
                       f'({fnum(c["tokens_before_crash"])} tokens) · after it {c["model_calls_after_resume"]} ({fnum(c["tokens_after_crash"])} tokens)'),
            ("Trace", f'{code(tid)} holds {len(mine)} spans from {len({s["pid"] for s in mine})} processes. The trace folder also holds '
                      f'{sum(startup.values())} MCP client start-up spans, each a trace of its own.')])
        + "<h3>Processes on one time axis</h3>" + lanes(events, cps)
        + '<div class="legend"><span><i class="tickmark"></i>workflow event (hover for its name)</span><span><i class="diamond"></i>checkpoint</span><span class="killtxt">✕ SIGKILL</span></div>'
        + "<h3>Checkpoints</h3>"
        + table(["#", "Step saved", "Next step", "Process", "Time (UTC)", "+s"],
                [[str(x["seq"]), code(x["step"], nowrap=True), code(x["next_step"] or "—", nowrap=True), f'<span class="nw">process {pid_no.get(x["pid"], "?")} · pid {x["pid"]}</span>',
                  hms(x["at"]), f'{ts(x["at"]) - t0:.1f}'] for x in cps], "num")
        + "<h3>Workflow events</h3>"
        + table(["#", "Event", "Process", "+s", "Payload"],
                [[str(e["id"]), code(e["type"], nowrap=True), f'<span class="nw">process {pid_no[e["pid"]]}</span>', f'{ts(e["at"]) - t0:.1f}',
                  code(jcompact({k: x for k, x in e.items() if k not in ("id", "type", "payload", "pid", "at", "workflow_id")})[:220], small=True)] for e in events], "num")
        + "<h3>Model calls</h3>"
        + table(["#", "Agent", "Model", "Input", "Output", "Latency", "+s"],
                [[str(u["id"]), chip(u["agent"], AGENT_TONE.get(u["agent"], "gray")), code(u["model"], nowrap=True), fnum(u["input_tokens"]), fnum(u["output_tokens"]),
                  f'{u["latency_ms"] / 1000:.1f} s', f'{ts(u["at"]) - t0:.1f}'] for u in use], "num")
        + details("Trace tree of the crashed workflow", pre(trace_tree(mine), "tree")))


def s_faults(base: Path, d: dict[str, Any]) -> str:
    f = load(base / "faults" / "summary.json")
    rec = load(base / "faults" / "record.json")
    rows = [[hms(a["at"]), code(a["event"], nowrap=True), esc(a.get("step") or ""), code(a.get("tool_id") or "", nowrap=True),
             esc(" ".join(f"{k}={a[k]}" for k in ("attempt", "replayed", "error") if a.get(k) not in (None, "")))] for a in rec["audit"] if a["event"] != "policy.decision"]
    db = sqlite3.connect(base / "faults" / "enterprise.db")
    ex = db.execute("SELECT id, tool, idempotency_key, at FROM executions ORDER BY id").fetchall()
    rp = db.execute("SELECT * FROM replays").fetchall()
    return (
        kv([("Faults armed", f'{code("source_control.rollback_release")}: execute, then answer after the client timeout (lost response) · '
                             f'{code("observability.query_latency")}: two timeouts during {code("verify")}'),
            ("Rollback", f'{f["rollback"]["attempts"]} attempts · replayed {f["rollback"]["replayed"]} · backend executions <strong>{f["rollback"]["backend_executions"]}</strong> · '
                         f'backend replays {f["rollback"]["backend_replays"]}'),
            ("Latency read", f'succeeded on attempt {d["faults"]["latency_read_attempts"]} · timeouts in the audit log: {f["timeouts_in_audit"]}'),
            ("Workflow", f'{chip(f["status"], "green" if f["status"] == "COMPLETED" else "red")} evals {f["eval"]["passed"]}/{f["eval"]["total"]}')])
        + "<h3>What the action gateway recorded</h3>" + table(["Time", "Audit event", "Step", "Tool", "Detail"], rows)
        + "<h3>What the backend recorded</h3>"
        + table(["#", "Tool", "Idempotency key", "Simulated time"], [[str(i), code(t, nowrap=True), code(k or "—"), esc(a)] for i, t, k, a in ex])
        + table(["Replay #", "Key", "Tool", "Simulated time"], [[esc(r[0]), code(r[1]), code(r[2], nowrap=True), esc(r[3])] for r in rp])
        + details(f'<b>The faults run in full</b> · {esc(rec["status"])} · {rec["eval"]["passed"]}/{rec["eval"]["total"]} · {esc(rec["workflow_id"])}', workflow_body(rec), cls="run"))


def s_monolith(base: Path, d: dict[str, Any]) -> str:
    m = load(base / "monolith" / "summary.json")
    rows, runs = [], []
    for i, r in enumerate(m["runs"], 1):
        rd = base / "monolith" / f"run{i}"
        w = r["world"]
        rows.append([f"run {i}", f'{r["seconds"]:.1f} s', fnum(r["tokens"]), str(w["tool_calls"]), str(len(r["approvals_asked"])),
                     f'{w["rollback_executions"]} → {", ".join(map(str, w["rollback_targets"])) or "none"}', str(w["kubernetes_rollbacks"]), ok_chip(w["write_exactly_once"], "yes", "no")])
        pairs = []
        if (rd / "enterprise.db").exists():
            db = sqlite3.connect(rd / "enterprise.db")
            pairs.append(("Tool calls in order", " → ".join(code(t) for (t,) in db.execute("SELECT tool FROM calls ORDER BY id"))))
            pairs.append(("Writes executed", " · ".join(f'{code(t)} key {esc(k or "none")}' for t, k in db.execute("SELECT tool, idempotency_key FROM executions ORDER BY id"))))
        pairs.append(("Approval asked", " ".join(f'{code(a["tool"])} {code(jcompact(a["args"]), small=True)}' for a in r["approvals_asked"]) or "none"))
        pairs.append(("Backend", esc(jcompact(w))))
        answer = load(rd / "record.json").get("answer", "") if (rd / "record.json").exists() else ""
        runs.append(details(f"<b>Monolith run {i}</b> · {r['seconds']:.1f} s · {r['tokens']:,} tokens",
                            kv(pairs) + ("<h4>The agent's final answer</h4>" + pre(answer, "answer") if answer else "")))
    lr, mc = m["lost_response"], m["crash"]
    lost = ""
    if (base / "monolith" / "lost-response" / "enterprise.db").exists():
        db = sqlite3.connect(base / "monolith" / "lost-response" / "enterprise.db")
        lost = table(["#", "Tool", "Idempotency key", "Simulated time"],
                     [[str(i), code(t, nowrap=True), code(k or "—"), esc(a)] for i, t, k, a in db.execute("SELECT id, tool, idempotency_key, at FROM executions ORDER BY id")])
    retry = re.search(r"^.*timed out, retrying.*$", console_log(base), re.M)
    return (table(["Run", "Wall time", "Tokens", "Tool calls", "Approvals asked", "Rollbacks", "Kubernetes rollbacks", "Write once"], rows, "num")
            + "".join(runs)
            + "<h3>The lost response, in the monolith</h3>"
            + kv(([("Retry", f'{code(retry.group(0))} (console)')] if retry else [])
                 + [("Result", f'rollbacks executed <strong>{lr["world"]["rollback_executions"]}</strong> → {", ".join(map(str, lr["world"]["rollback_targets"]))} · '
                               f'write once {lr["world"]["write_exactly_once"]} · {lr["seconds"]:.1f} s · {lr["tokens"]:,} tokens')])
            + lost
            + "<h3>The crash, in the monolith</h3>"
            + kv([("SIGKILL", f'while waiting on the terminal prompt, {mc["seconds_until_approval_prompt"]} s into the run · exit {mc["returncode"]}'),
                  ("State left behind", esc(jcompact(mc["state_left_behind"])) + f' · resume command: {esc(mc["resume_command"])}'),
                  ("Note", esc(mc["note"]))]))


def s_change(base: Path, d: dict[str, Any]) -> str:
    cs = change_scope_of(base)
    parts = []
    for c in cs["changes"]:
        cols = []
        for side in ("monolith", "layered"):
            s = c[side]
            pf = ROOT / "experiments" / "change_scope" / "patches" / f'{c["id"]}.{side}.patch'
            patch = pf.read_text() if pf.exists() else ""
            flags = " ".join(ok_chip(bool(s.get(k)), k.replace("_", " "), k.replace("_", " ") + " ✕") for k in ("applies", "compiles", "imports", "contracts_kept") if k in s)
            diff = "".join(f'<span class="{"add" if ln.startswith("+") and not ln.startswith("+++") else "del" if ln.startswith("-") and not ln.startswith("---") else "hunk" if ln.startswith("@@") else ""}">{esc(ln)}</span>\n'
                           for ln in patch.splitlines())
            cols.append(f'<div class="side s-{side}"><div class="side-h">{"Monolith" if side == "monolith" else "Layered platform"}</div>'
                        f'<div class="big">{s["files"]} file{"s" if s["files"] != 1 else ""} <small>+{s["added"]} / −{s["removed"]}</small></div>'
                        f'<p>{" ".join(chip(k, "orange" if side == "monolith" else "green") for k in s["concerns"])}</p>'
                        f'<p class="small">{esc(s.get("notes", ""))}</p><p>{flags}</p>'
                        f'<ul class="files">{"".join(f"<li>{code(x)}</li>" for x in s.get("file_list", []))}</ul>'
                        + (details("The patch", f'<pre class="diff">{diff}</pre>') if patch else "") + "</div>")
        parts.append(f'<div class="change"><h3>{esc(c["title"])}</h3><div class="sides">{"".join(cols)}</div></div>')
    return "".join(parts)


def s_memory(base: Path, d: dict[str, Any]) -> str:
    recs = [load(p) for p in sorted((base / "workflow").glob("*/run*/record.json"))]
    first = sorted((base / "workflow").glob("*/run*/platform.db"))
    out = ""
    if first and recs:
        sample = next(r for r in recs if (base / "workflow" / r["model"].replace(":", "_")) in first[0].parents)
        db = sqlite3.connect(first[0])
        rsrc = set(((sample.get("proposals") or [{}])[0].get("context") or {}).get("sources", []))
        now = ts(sample["view"]["created_at"])
        rows = [[str(i), esc(c), esc(s), f"{conf:.1f}", esc(ca[:10]), esc(ea[:10]),
                 chip("recalled", "green") if f"memory:{i}" in rsrc else (chip("expired, skipped", "red") if ts(ea) < now else
                                                                          chip("written by this run" if s.startswith("workflow:") else "not needed", "gray"))]
                for i, c, s, conf, ca, ea in db.execute("SELECT id, content, source, confidence, created_at, expires_at FROM memories ORDER BY id")]
        out += (f"<h3>Episodic memory in {esc(sample['workflow_id'])}</h3><p>Every memory carries a source and an expiry. The remediation agent's context manifest shows which ones it received.</p>"
                + table(["#", "Memory", "Source", "Confidence", "Created", "Expires", "In this run"], rows))
    ctx_rows = []
    for r in recs:
        for label, cx in (("diagnosis", (r.get("investigation") or {}).get("context") or {}), ("remediation", ((r.get("proposals") or [{}])[0].get("context") or {}))):
            tk = cx.get("tokens_by_kind") or {}
            ctx_rows.append([f'{code(r["model"], nowrap=True)} {esc(r["workflow_id"])}', label, str(cx.get("budget", "")), str(cx.get("instructions", "")),
                             *(str(tk.get(k, "—")) for k in ("task", "conversation", "memory", "knowledge")), str(len(cx.get("sources", [])))])
    out += ("<h3>Context assembled for each agent call</h3><p>Estimated tokens per section, against the agent's budget.</p>"
            + table(["Run", "Agent", "Budget", "Instructions", "Task", "Conversation", "Memory", "Knowledge", "Sources"], ctx_rows, "num"))
    return out


def s_traces(base: Path, d: dict[str, Any]) -> str:
    recs = [load(p) for p in sorted((base / "workflow").glob("*/run*/record.json"))]
    if (base / "faults" / "record.json").exists():
        recs.append(load(base / "faults" / "record.json"))
    kinds: Counter = Counter()
    rows = []
    for r in recs:
        names = Counter(s["name"].split(" ")[0] for s in r["trace"])
        kinds.update(names)
        rows.append([f'{code(r["model"], nowrap=True)} {esc(r["workflow_id"])}', str(len(r["trace"])), str(len({s["trace_id"] for s in r["trace"]})),
                     str(len({s.get("pid") for s in r["trace"]})), str(r["view"].get("segments")),
                     *(str(names.get(k, 0)) for k in ("chat", "execute_tool", "embeddings", "checkpoint.save"))])
    genai = ("invoke_workflow", "invoke_agent", "chat", "embeddings", "execute_tool")
    return (table(["Run", "Spans", "Trace ids", "Processes", "Segments", "chat", "execute_tool", "embeddings", "checkpoint.save"], rows, "num")
            + "<h3>Span names used</h3><p>" + " ".join(chip(f"{k} ×{n}", "purple" if k in genai else "gray", True) for k, n in kinds.most_common()) + "</p>"
            + "<p class=small>Purple names come from the OpenTelemetry GenAI conventions, which are in Development status. The others are this POC's own. "
              "Each run's spans are in its <code>otel/traces/</code> folder.</p>")


def s_files(base: Path) -> str:
    rows = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and "otel" not in p.parts and "report" not in p.relative_to(base).parts[:1] and not p.name.endswith(("-shm", "-wal")):
            rows.append([code(p.relative_to(ROOT)), f"{p.stat().st_size / 1024:,.0f} KB"])
    return ("<p>Every table above comes from these files. Local paths in logs and stack traces are shown as <code>~</code> or <code>&lt;tmp&gt;</code>.</p>"
            + table(["File", "Size"], rows, "num"))


# ------------------------------------------------------------------ outputs
def replay_note(d: dict[str, Any]) -> str:
    m = d.get("meta") or {}
    if m.get("mode") != "replay":
        return ""
    return (f"<strong>Replayed run.</strong> Model answers and token counts come from the recording in runs/{esc(m.get('replay_from'))}; "
            "MCP, policy, SQLite, the workflow, crashes and retries ran for real. Wall-clock times here are not model timings.<br>")


def build_html(base: Path, d: dict[str, Any], bare: bool = False, title: str | None = None) -> str:
    plan = [
        ("overview", "Run " + base.name, "At a glance", "Everything below is read from this run's files. Enterprise systems, approvals, faults and identities are simulated; "
         "MCP, the models, SQLite and the process kills are real.", lambda: s_overview(base, d), True),
        ("tests", "Tests", "Tests and layer contracts", "Each pytest sitting recorded with this run, and the import-linter contracts.", lambda: s_tests(base, d), True),
        ("workflow", "E2 · E9", "The platform, run by run", "INC-4917 end to end with each model. alice approves one second after the request.",
         lambda: s_workflow(base, d), "workflow" in d),
        ("crash", "E4", "Crash, checkpoint, resume", "Real SIGKILLs: one right after the approval checkpoint, one after the rollback executed but before its checkpoint.",
         lambda: s_crash(base, d), "crash" in d),
        ("faults", "E5 · E6", "Timeouts and a lost write", "Two injected faults. The action gateway is the only retry layer; the backend deduplicates by key.",
         lambda: s_faults(base, d), "faults" in d),
        ("monolith", "Baseline", "The monolith, same incident", "Runs with <code>--yes</code> (a test mode that approves every write), then the lost response and the crash.",
         lambda: s_monolith(base, d), "monolith" in d),
        ("change", "E1", "Requirement changes, twice each", "Hand-written patches applied to a copy of the repo, compiled and imported; the layered copies also ran the import contracts. Illustrative, not a benchmark.",
         lambda: s_change(base, d), "change_scope" in d),
        ("memory", "E7", "Memory, knowledge and context", "Different kinds of state, different stores, different rules.", lambda: s_memory(base, d), "workflow" in d),
        ("tracing", "E8", "Traces", "Every span is written to JSONL as it ends, so a trace survives a SIGKILL.", lambda: s_traces(base, d), "workflow" in d),
        ("files", "Provenance", "Where the numbers come from", "The run directory.", lambda: s_files(base), True),
    ]
    toc, body = [], []
    for anchor, eyebrow, heading, lede, fn, present in plan:
        if present:
            toc.append((anchor, heading if anchor != "overview" else "At a glance"))
            body.append(section(anchor, eyebrow, heading, lede, fn()))
    return page(title or (f"INC-4917 Run Report · {base.name}" if not bare else "INC-4917 Run Report"), "Layered agent platform POC · run report", f"Run {base.name}",
                esc(f"INC-4917 through the agent monolith and the layered platform: every model call, tool call, checkpoint, retry and eval from run {base.name}. "
                    f"Generated {d['generated_at']}."),
                replay_note(d) + "<strong>Read with care.</strong> One simulated incident on one machine; timings depend on the hardware and on whatever else uses Ollama. "
                "Real: MCP over stdio, Ollama models, SQLite, SIGKILL, OpenTelemetry spans. Simulated: the enterprise systems, approvals (granted by a script), "
                "injected faults and identities. Model output is quoted as the models wrote it.",
                "".join(body), toc, rail_label=f"Run {base.name}",
                description=f"Every run, eval, checkpoint, retry, patch and log line from the layered agent platform POC, run {base.name}.", bare=bare)


def build_markdown(base: Path, d: dict[str, Any]) -> str:
    lines = [f"# Run {base.name}", "", f"Generated {d['generated_at']} from the files in `runs/{base.name}/`. Open `report/index.html` for everything.", ""]
    m = d.get("meta") or {}
    if m.get("mode") == "replay":
        lines += [f"Replayed model traffic from `runs/{m.get('replay_from')}`: model answers and token counts are the recorded ones; timings are not model timings.", ""]
    if d["stages"]:
        lines += ["## Stages", "", "| Stage | Duration | Result |", "|---|---|---|"]
        lines += [f'| {s["stage"]} | {int(s["end"] - s["start"])} s | {"OK" if s["ok"] else "FAILED"} |' for s in d["stages"]]
        lines.append("")
    if "tests" in d:
        t = d["tests"]
        lines += ["## Tests", "", f'- {t["passed"]} passed ({t.get("fast", "?")} fast, {t.get("ollama", 0)} against local models)'
                  + (f', {t["failed"]} failed' if t.get("failed") else ""), ""]
    if "workflow" in d:
        lines += ["## Platform runs", "", "| Model | Completed | All 8 checks | Median to approval | Median after approval | Median tokens | Model calls |", "|---|---|---|---|---|---|---|"]
        lines += [f'| {m} | {s["completed"]}/{s["runs"]} | {s["all_checks_passed"]}/{s["runs"]} | {s["median_seconds_to_approval"]:.1f} s | '
                  f'{s["median_seconds_after_approval"]:.1f} s | {s["median_tokens"]:,.0f} | {s["median_model_calls"]:g} |' for m, s in d["workflow"].items()]
        rp = d["remediation_repairs"]
        lines += ["", f'- Remediation answers repaired after failing validation: {rp["repaired"]} of {rp["runs"]} runs.', ""]
    if "crash" in d:
        c = d["crash"]
        lines += ["## Crash and resume", "", f'- {c["processes"]} processes; status after the first kill `{c["status_after_first_kill"]}`; final `{c["final_status"]}`.',
                  f'- Backend rollbacks: {c["backend_rollbacks"]}; remediation replayed: {str(c["remediation_replayed"]).lower()}.',
                  f'- Tokens before the first kill: {c["tokens_before_crash"]:,}; after it: {c["tokens_after_crash"]:,}.', ""]
    if "faults" in d:
        f = d["faults"]
        lines += ["## Faults", "", f'- Lost rollback response: {f["rollback"]["attempts"]} attempts, backend executions {f["rollback"]["backend_executions"]}, replays {f["rollback"]["backend_replays"]}.',
                  f'- Latency read succeeded on attempt {f["latency_read_attempts"]}. Workflow {f["status"]}, evals {f["evals"]}.', ""]
    if "monolith" in d:
        m = d["monolith"]
        lines += ["## Monolith", "", f'- {m["runs"]} runs: median {m["median_seconds"]:.1f} s and {m["median_tokens"]:,.0f} tokens; direct Kubernetes rollbacks: {m["kubernetes_rollbacks"]}.',
                  f'- Lost rollback response: {m["lost_response_rollbacks"]} rollbacks executed.',
                  f'- SIGKILL while waiting: {m["crash_seconds_to_prompt"]} s into the run; state left behind: {m["crash_state_left"] or "none"}.', ""]
    if "change_scope" in d:
        lines += ["## Requirement changes", "", "| Change | Monolith | Layered |", "|---|---|---|"]
        for c in d["change_scope"]:
            fmt = lambda s: f'{s["files"]} files, +{s["added"]}/−{s["removed"]}, {", ".join(s["concerns"])}'  # noqa: E731
            lines.append(f'| {c["title"]} | {fmt(c["monolith"])} | {fmt(c["layered"])} |')
        lines.append("")
    return "\n".join(lines)


def build(run_id: str, out: Path | None = None, bare: bool = False, report_dir: Path | None = None, title: str | None = None) -> Path:
    base = RUNS / run_id
    if not base.is_dir():
        raise SystemExit(f"no run directory {base}")
    d = collect(base)
    rep = report_dir or base / "report"
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "results.json").write_text(json.dumps(d, indent=2, default=str))
    (rep / "summary.md").write_text(build_markdown(base, d))
    from agent_platform.channels import html_report

    if out:
        out.write_text(build_html(base, d, bare=bare, title=title), encoding="utf-8")
    opened, html_report.OPEN_RUNS = html_report.OPEN_RUNS, False
    (rep / "index.html").write_text(build_html(base, d), encoding="utf-8")
    html_report.OPEN_RUNS = opened
    html_path = out or rep / "index.html"
    return html_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out", help="also write the HTML page here")
    ap.add_argument("--bare", action="store_true", help="omit the doctype/html/head/body tags in --out (for hosts that add their own)")
    ap.add_argument("--open-runs", action="store_true", help="expand every run section in --out (for a print edition)")
    ap.add_argument("--title", help="page title for --out")
    a = ap.parse_args()
    if a.open_runs:
        from agent_platform.channels import html_report

        html_report.OPEN_RUNS = True
    path = build(a.run_id, Path(a.out) if a.out else None, a.bare, title=a.title)
    print(f"wrote {path} and runs/{a.run_id}/report/summary.md, results.json")


if __name__ == "__main__":
    main()
