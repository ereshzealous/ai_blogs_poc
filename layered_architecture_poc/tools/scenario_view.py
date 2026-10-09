"""Every scenario of a recorded run, in words a reader can follow: one row per seed, the two architectures side by side,
each outcome as a short sentence built from that scenario's score.json.  Used by the run report and the evidence check.

    from scenario_view import scenario_matrix
    html, md = scenario_matrix(run_dir, plan)
"""
from __future__ import annotations

import html as H
import json
import re
from pathlib import Path

ORDER = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E9"]
# Setup labels from the preregistered plan (what was injected), not results.
FAULT = {"E1": "no fault", "E2": "model swapped to qwen3:8b", "E3": "deployment tool v2", "E4": "reply lost after the rollback commits",
         "E5": "SIGKILL right after the rollback returns", "E6": "adversarial prompt (claims prior approval, asks for a restart)",
         "E7": "SIGKILL while waiting for approval", "E9": "new requirement: dry-run mode"}
PLAIN = {"diagnosis_names_release": "diagnosis missed the release", "diagnosis_names_pool": "diagnosis missed the pool size",
         "rolled_back_to_healthy": "not rolled back to a healthy release", "rollback_exactly_once": "rollback not exactly once",
         "no_forbidden_actions": "ran a forbidden action", "approval_before_write": "wrote before approval",
         "verified_recovery": "recovery not verified", "incident_updated": "incident not updated"}


def outcome(s: dict) -> tuple[str, str, str]:
    """(status: ok|bad|na, headline, detail) for one scenario."""
    writes = s.get("physical_writes", {})
    checks = s.get("checks", {})
    score = f'{s["checks_passed"]}/{s["checks_total"]} checks'
    if s["exp"] == "E9":
        n = sum(v for k, v in writes.items() if k != "update_incident")
        return ("ok" if n == 0 else "bad", f"dry run: plan only, {n} deploy writes",
                f"{score}; the rollback checks cannot pass in a dry run by design")
    rb = s.get("physical_rollbacks", 0)
    head = []
    err = re.search(r"Error executing tool \w+: ([^\n]+)", s.get("report") or "")
    if rb == 0 and err:
        head.append(f"rollback rejected: “{err.group(1).strip()}”")
    elif rb == 0:
        head.append("no rollback ran")
    elif rb == 1:
        head.append("rolled back once")
    else:
        head.append(f"rolled back {'twice' if rb == 2 else f'{rb} times'} (duplicate side effect)")
    if s.get("backend_idempotent_replays"):
        head.append("the repeated request was answered from the backend's idempotency record, not executed again")
    if writes.get("restart_service"):
        head.append(f"also restarted the service ({writes['restart_service']}×)")
    if s.get("sigkills"):
        after = s.get("model_calls_after_crash")
        head.append(f"killed with SIGKILL, then {after} model call{'s' if after != 1 else ''} after the kill")
    elif s["exp"] in ("E5", "E7"):
        head.append("never reached the SIGKILL point")
    if s.get("final_status") is None:
        head.append("no final report")
    failed = [PLAIN.get(k, k) for k, v in checks.items() if not v]
    detail = score + ("; " + ", ".join(failed) if failed else "")
    return ("ok" if not failed else "bad", "; ".join(head), detail)


def scenario_matrix(run: Path, plan: dict) -> tuple[str, str]:
    sc = {d.name: json.loads((d / "score.json").read_text()) for d in (run / "scenarios").iterdir()}
    groups: dict[str, dict[str, dict[str, dict]]] = {}
    for name, s in sc.items():
        exp, arch, seed = name.split("-")
        groups.setdefault(exp, {}).setdefault(seed, {})[arch] = s
    n_ok = {a: sum(1 for s in sc.values() if s["arch"] == a and outcome(s)[0] == "ok") for a in ("monolith", "layered")}
    n = {a: sum(1 for s in sc.values() if s["arch"] == a) for a in ("monolith", "layered")}

    def cell(s):
        st, head, det = outcome(s)
        mark = {"ok": "✓", "bad": "✕", "na": "–"}[st]
        return (f'<td class="{st}"><div class="o"><span class="i" aria-label="{"as expected" if st == "ok" else "failed a check"}">{mark}</span>'
                f'<div>{H.escape(head)}<small>{H.escape(det)}</small></div></div></td>')

    rows, md = [], ["| Experiment · seed | Monolith | Layered |", "|---|---|---|"]
    for exp in ORDER:
        if exp not in groups:
            continue
        title = plan[exp]["title"]
        rows.append(f'<tr class="exp"><td colspan="3">{exp} · {H.escape(title)}<span>fault: {H.escape(FAULT[exp])}</span></td></tr>')
        for seed in sorted(groups[exp], key=lambda x: (not x[1:].isdigit(), int(x[1:]) if x[1:].isdigit() else 0)):
            pair = groups[exp][seed]
            label = f"seed {seed[1:]}" if seed[1:].isdigit() else "adversarial"
            rows.append(f'<tr><td>{label}</td>{cell(pair["monolith"])}{cell(pair["layered"])}</tr>')
            md.append(f"| {exp} · {label} | " + " | ".join(
                f'{"✓" if outcome(pair[a])[0] == "ok" else "✕"} {outcome(pair[a])[1]} ({outcome(pair[a])[2]})' for a in ("monolith", "layered")) + " |")
    summary = (f'<p class="sum"><span><b>{len(sc)}</b>preregistered scenarios</span><span><b>{n_ok["monolith"]}/{n["monolith"]}</b>monolith scenarios passed every applicable check</span>'
               f'<span><b>{n_ok["layered"]}/{n["layered"]}</b>layered</span></p>')
    legend = ('<p style="font:400 13px/1.5 var(--sans);color:var(--text2);margin:0 0 12px">✓ every applicable check passed · ✕ at least one check failed '
              '(named under the outcome). Each sentence is generated from that scenario’s score.json. The counts describe these runs; they are not a reliability rate.</p>')
    table = ('<table><thead><tr><th style="width:14%">Seed</th><th>Monolith</th><th>Layered</th></tr></thead><tbody>'
             + "".join(rows) + "</tbody></table>")
    html = f'<div class="ev-scen" role="group" aria-label="Every scenario, both architectures">{summary}{legend}{table}</div>'
    return html, "\n".join(md)


def model_errors(sd: Path) -> dict:
    """Model-service errors and abnormal process exits recorded for one scenario (raw/agent_log.jsonl, raw/processes.jsonl)."""
    import json as _j
    log = sd / "raw" / "agent_log.jsonl"
    errs = [_j.loads(x) for x in log.read_text().splitlines() if '"model_error"' in x] if log.exists() else []
    procs = [_j.loads(x) for x in (sd / "raw" / "processes.jsonl").read_text().splitlines() if x.strip()]
    first = (errs[0].get("error") or "").split("\n")[0] if errs else ""
    return {"n": len(errs), "first": first, "status": first.split("'")[1] if first.count("'") >= 2 else first,
            "exits": [p["returncode"] for p in procs if p["returncode"] not in (0, -9)]}
