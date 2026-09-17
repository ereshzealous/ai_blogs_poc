"""The H1–H7 scenarios. Each runs in its own process: `python -m experiments.scenarios <name> <out_dir>`.

The environment (fresh databases, and model answers live, recorded or replayed) is prepared by experiments.run.
Every scenario writes <out_dir>/result.json: {"pass": bool, "checks": {...}, "facts": {...}}.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from headless_ai_platform.contracts import ActionType, Actor, CapabilityError, Status
from headless_ai_platform.renderers import api, cli, slack, web
from headless_ai_platform.runtime import open_gateway

CAP = "incident.remediation"
ALICE = {"slack": "U04ALICE", "web": "oidc|alice-92ab", "cli": "alice@company.example", "rest": "api|alice"}
BOB = {"slack": "U04BOB", "web": "oidc|bob-51cd", "cli": "bob@company.example", "rest": "api|bob"}
WAIT_S = float(os.environ.get("HAI_EXP_WAIT_S", "1200"))


def start(channel: str, subject: str | None = None, **ctx: Any) -> dict[str, Any]:
    return {"capability": CAP, "operation": "start", "input": {"incident_id": "INC-4917"}, "channel_context": ctx,
            "actor": {"channel": channel, "channel_subject": subject or ALICE[channel]}}


def act(wf: str, channel: str, subject: str | None = None, action: str = "approve-remediation",
        binding: str | None = None) -> dict[str, Any]:
    return {"capability": CAP, "operation": "act", "workflow_id": wf, "action_id": action, "binding": binding,
            "actor": {"channel": channel, "channel_subject": subject or ALICE[channel]}}


def get(wf: str, channel: str, subject: str | None = None) -> dict[str, Any]:
    return {"capability": CAP, "operation": "get", "workflow_id": wf,
            "actor": {"channel": channel, "channel_subject": subject or ALICE[channel]}}


def tools_used(record: dict[str, Any]) -> list[str]:
    return [a["tool_id"] for a in record["audit"] if a["event"] == "invocation.executed"]


def summary(record: dict[str, Any]) -> dict[str, Any]:
    ev = record["eval"]
    return {"eval_ok": bool(ev.get("ok")), "eval_checks": f"{ev.get('passed')}/{ev.get('total')}",
            "eval_failed": [c["name"] for c in ev.get("checks", []) if not c.get("passed")],
            "tools": tools_used(record), "model_calls": len(record["usage"]),
            "tokens": sum(u["input_tokens"] + u["output_tokens"] for u in record["usage"]),
            "spans": len(record["trace"])}


# ====================================================================== H1
async def h1(out: Path) -> dict[str, Any]:
    """Same capability via CLI, REST and Slack: same semantics, trajectories may differ.

    Each channel meets the same incident: the simulated enterprise is reset before each start (a completed rollback
    would otherwise leave the next investigation looking at an already-fixed system). Platform memory is kept, as it
    would be in production, so later runs may recall the earlier incident.
    """
    from experiments.harness import reset_enterprise

    rows = {}
    async with open_gateway() as gw:
        for channel in ("cli", "rest", "slack"):
            reset_enterprise(Path(os.environ["LAP_ENTERPRISE_DB"]))
            t0 = time.monotonic()
            r = await gw.handle(start(channel), wait=True)
            a = r.action(ActionType.APPROVE)
            final = await gw.handle(act(r.workflow_id, channel, binding=a.binding if a else None), wait=True) if a else r
            rec = gw.platform.record(r.workflow_id)
            rows[channel] = {"workflow_id": r.workflow_id, "status": final.status.value,
                             "tool": final.state.recommended_action.tool if final.state.recommended_action else None,
                             "target": final.state.recommended_action.target if final.state.recommended_action else None,
                             "policy": final.state.policy_decision, "rule": final.state.policy_rule,
                             "required_role": final.state.approval_required_role, "approval": final.state.approval_status,
                             "verified": final.state.verified, "started_via": final.started_by.channel,
                             "seconds": round(time.monotonic() - t0, 1), **summary(rec)}
    semantic = {c: (v["status"], v["tool"], v["target"], v["policy"], v["rule"], v["required_role"], v["approval"],
                    v["verified"]) for c, v in rows.items()}
    trajectories = {c: v["tools"] for c, v in rows.items()}
    checks = {
        "same_semantics": len(set(semantic.values())) == 1,
        "completed_everywhere": all(v["status"] == "COMPLETED" for v in rows.values()),
        "authoritative_remediation": all(v["tool"] == "source_control.rollback_release" and v["target"] == "v4.16"
                                         for v in rows.values()),
        "same_policy_outcome": len({(v["policy"], v["rule"]) for v in rows.values()}) == 1,
        "platform_evals_pass": all(v["eval_ok"] for v in rows.values()),
        "channel_recorded": all(v["started_via"] == c for c, v in rows.items()),
    }
    facts = {"channels": rows, "identical_trajectories": len({tuple(t) for t in trajectories.values()}) == 1,
             "distinct_trajectories": len({tuple(t) for t in trajectories.values()})}
    return {"checks": checks, "facts": facts}


# ====================================================================== H4
async def h4(out: Path) -> dict[str, Any]:
    """Every channel meets the same governance; a channel cannot forge an approval."""
    rows, forged = {}, []
    async with open_gateway() as gw:
        for channel in ("slack", "rest", "cli", "web"):
            r = await gw.handle(start(channel), wait=True)
            rows[channel] = {"workflow_id": r.workflow_id, "status": r.status.value, "policy": r.state.policy_decision,
                             "rule": r.state.policy_rule, "required_role": r.state.approval_required_role,
                             "executed_before_approval": r.state.remediation_status is not None}
        wf = rows["rest"]["workflow_id"]
        attempts = {"approved: true on the request": {**start("rest"), "approved": True},
                    "approved: true inside input": {**start("rest"), "input": {"incident_id": "INC-4917", "approved": True}},
                    "principal_id asserted by the channel": {**start("rest"), "actor": {"channel": "rest",
                                                             "channel_subject": "api|bob", "principal_id": "alice"}},
                    "approve with an invented binding": act(wf, "rest", binding="0" * 16),
                    "unknown action 'force-execute'": act(wf, "rest", action="force-execute")}
        for label, payload in attempts.items():
            try:
                await gw.handle(payload, wait=True)
                forged.append({"attempt": label, "outcome": "ACCEPTED"})
            except CapabilityError as exc:
                forged.append({"attempt": label, "outcome": exc.code.value})
        after = await gw.handle(get(wf, "rest"))
        audit = gw.platform.record(wf)["audit"]
    decisions = {(v["status"], v["policy"], v["rule"], v["required_role"]) for v in rows.values()}
    checks = {
        "same_decision_every_channel": len(decisions) == 1,
        "decision_is_require_approval": decisions == {("WAITING_APPROVAL", "REQUIRE_APPROVAL", "P4-prod-high-risk-approval",
                                                       "incident-commander")},
        "nothing_executed_before_approval": not any(v["executed_before_approval"] for v in rows.values()),
        "every_forgery_refused": all(f["outcome"] != "ACCEPTED" for f in forged),
        "workflow_still_waiting": after.status is Status.WAITING_APPROVAL and after.state.approval_status == "PENDING",
        "no_write_in_audit": not any(a["event"] == "invocation.executed" and a["tool_id"].endswith("rollback_release")
                                     for a in audit),
    }
    return {"checks": checks, "facts": {"channels": rows, "forgery_attempts": forged}}


# ====================================================================== H5
async def h5(out: Path) -> dict[str, Any]:
    """Same person, same authority, whatever the channel."""
    bob, alice_ids = {}, {}
    async with open_gateway() as gw:
        for channel, subject in ALICE.items():
            alice_ids[channel] = gw.principal_for(Actor(channel=channel, channel_subject=subject))
        r = await gw.handle(start("slack"), wait=True)
        for channel, subject in BOB.items():
            seen = await gw.handle(get(r.workflow_id, channel, subject))
            try:
                await gw.handle(act(r.workflow_id, channel, subject), wait=True)
                outcome = "ALLOWED"
            except CapabilityError as exc:
                outcome = exc.code.value
            bob[channel] = {"subject": subject, "principal": seen.actor.principal_id, "outcome": outcome,
                            "button_enabled": any(a.allowed_for_actor for a in seen.available_actions)}
        waiting = await gw.handle(get(r.workflow_id, "web"))
        done = await gw.handle(act(r.workflow_id, "rest", binding=waiting.action(ActionType.APPROVE).binding), wait=True)
        interactions = gw.store.interactions(r.workflow_id)
    alice = {c: {"subject": ALICE[c], "principal": p.principal_id, "roles": list(p.roles)} for c, p in alice_ids.items()}
    checks = {
        "alice_one_principal": {v["principal"] for v in alice.values()} == {"alice"},
        "alice_same_roles": len({tuple(v["roles"]) for v in alice.values()}) == 1,
        "bob_one_principal": {v["principal"] for v in bob.values()} == {"bob"},
        "bob_denied_everywhere": {v["outcome"] for v in bob.values()} == {"FORBIDDEN"},
        "bob_never_offered_the_button": not any(v["button_enabled"] for v in bob.values()),
        "still_waiting_after_bob": waiting.status is Status.WAITING_APPROVAL,
        "alice_approves_from_another_channel": done.status is Status.COMPLETED and done.state.approved_by == "alice",
    }
    return {"checks": checks, "facts": {"alice": alice, "bob": bob, "interactions": len(interactions)}}


# ====================================================================== H6
async def h6(out: Path) -> dict[str, Any]:
    """Rendering is a pure transformation: no model, tool, policy or workflow activity."""
    async with open_gateway() as gw:
        r = await gw.handle(start("slack"), wait=True)
        before = gw.platform.activity(r.workflow_id)
        n, timings = 250, {}
        samples = {}
        for name, fn in (("slack", slack.render), ("web", web.render), ("cli", cli.render), ("api", api.render)):
            t0 = time.perf_counter()
            for _ in range(n):
                rendered = fn(r)
            timings[name] = round((time.perf_counter() - t0) / n * 1e6, 1)  # microseconds per render
            samples[name] = rendered
        after = gw.platform.activity(r.workflow_id)
        rec = gw.platform.record(r.workflow_id)
        get_ms = []
        for _ in range(100):
            t0 = time.perf_counter()
            await gw.handle(get(r.workflow_id, "web"))
            get_ms.append((time.perf_counter() - t0) * 1000)
        model_ms = [u["latency_ms"] for u in rec["usage"]]
    (out / "renderings").mkdir(parents=True, exist_ok=True)
    (out / "renderings" / "slack.json").write_text(json.dumps(samples["slack"], indent=2, ensure_ascii=False))
    (out / "renderings" / "web.html").write_text(samples["web"])
    (out / "renderings" / "cli.txt").write_text(samples["cli"])
    (out / "renderings" / "api.json").write_text(json.dumps(samples["api"], indent=2, ensure_ascii=False))
    delta = {k: after[k] - before[k] for k in before}
    checks = {"no_activity_while_rendering": all(v == 0 for v in delta.values()),
              "workflow_had_real_activity": before["model_calls"] > 0 and before["tool_calls"] > 0}
    facts = {"renders_per_channel": n, "activity_before": before, "activity_delta": delta,
             "microseconds_per_render": timings, "gateway_get_ms_p50": round(statistics.median(get_ms), 2),
             "model_call_ms_p50": round(statistics.median(model_ms), 0) if model_ms else None}
    return {"checks": checks, "facts": facts}


# ====================================================================== H2 and H7 (separate processes)
def _poll(url: str, headers: dict[str, str], status: str, timeout: float = WAIT_S) -> dict[str, Any]:
    deadline, body = time.monotonic() + timeout, {}
    while time.monotonic() < deadline:
        r = httpx.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            body = r.json()
            if body["response"]["status"] == status:
                return body
            if body["response"]["status"] in ("FAILED", "REJECTED") and status != body["response"]["status"]:
                raise RuntimeError(f"workflow ended {body['response']['status']}")
        time.sleep(0.5)
    raise TimeoutError(f"{url} never reached {status}: {body.get('response', {}).get('status')}")


def _messages(log: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []


def _wait_message(log: Path, status: str, timeout: float = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for m in _messages(log):
            if m.get("text", "").endswith(status):
                return m
        time.sleep(0.2)
    raise TimeoutError(f"no Slack message for {status}")


def _distinct_in_order(statuses: list[str]) -> list[str]:
    """Collapse repeats: ["A", "A", "B"] -> ["A", "B"]. A redelivery is not a new update."""
    return [s for i, s in enumerate(statuses) if i == 0 or statuses[i - 1] != s]


def _handoff(out: Path, kill_slack: bool) -> dict[str, Any]:
    from experiments import procs

    env = {k: v for k, v in os.environ.items() if k.startswith(("LAP_", "HAI_"))}
    logs = out / "processes"
    if logs.exists():  # a re-run starts with empty process logs and an empty Slack workspace
        shutil.rmtree(logs)
    timeline: list[dict[str, Any]] = []
    started = time.monotonic()

    def note(what: str, **kw: Any) -> None:
        timeline.append({"t": round(time.monotonic() - started, 2), "event": what, **kw})

    api_sink = procs.sink(env, logs)
    slack_env = {"HAI_SLACK_URL": f"{api_sink.url}/api/chat.postMessage"}
    slack_proc = procs.server("slack-adapter", "slack", env, logs, slack_env)
    web_proc = procs.server("web-adapter", "web,rest", env, logs)
    note("processes up", slack_pid=slack_proc.pid, web_pid=web_proc.pid)
    alice_web = {"X-OIDC-Subject": ALICE["web"]}
    msg_log = logs / "slack-messages.jsonl"
    slack2 = None
    try:
        mention = {"type": "event_callback", "event_id": "Ev-4917", "team_id": "T1",
                   "event": {"type": "app_mention", "user": "U04ALICE", "channel": "C-INC4917", "ts": "1726560000.1",
                             "team": "T1", "text": "<@UOPS> investigate INC-4917"}}
        reply = httpx.post(f"{slack_proc.url}/slack/events", json=mention, timeout=30).json()
        wf = reply["blocks"][0]["text"]["text"].split("`")[1]
        note("slack: @mention answered", workflow_id=wf, status=reply["text"].split()[-1], pid=slack_proc.pid)
        page = _poll(f"{web_proc.url}/web/api/workflows/{wf}", alice_web, "WAITING_APPROVAL")
        note("web: sees WAITING_APPROVAL", pid=web_proc.pid)
        _wait_message(msg_log, "WAITING_APPROVAL")
        note("slack thread: approval request delivered")
        if kill_slack:
            slack_proc.kill()
            note("slack adapter killed (SIGKILL)", pid=slack_proc.pid)
            try:
                httpx.post(f"{slack_proc.url}/slack/events", json=mention, timeout=3)
                slack_reachable = True
            except httpx.HTTPError:
                slack_reachable = False
            note("slack adapter reachable?", reachable=slack_reachable)
            page = _poll(f"{web_proc.url}/web/api/workflows/{wf}", alice_web, "WAITING_APPROVAL", timeout=10)
            note("web: workflow still WAITING_APPROVAL after slack is gone")
        binding = page["response"]["available_actions"][0]["binding"]
        r = httpx.post(f"{web_proc.url}/web/api/workflows/{wf}/actions", headers=alice_web,
                       json={"action_id": "approve-remediation", "binding": binding}, timeout=30)
        note("web: approve", http=r.status_code, pid=web_proc.pid)
        _poll(f"{web_proc.url}/web/api/workflows/{wf}", alice_web, "COMPLETED")
        note("web: sees COMPLETED")
        status = procs.cli(["--as", ALICE["cli"], "--json", "status", wf], env)
        cli_body = json.loads(status.stdout)
        note("cli: status", exit_code=status.returncode, status=cli_body["status"])
        rest = httpx.get(f"{web_proc.url}/v1/capabilities/{CAP}/workflows/{wf}", headers={"X-Subject": ALICE["rest"]}).json()
        note("rest: status", status=rest["status"])
        outbox_before_restart = _outbox(env, wf)
        if kill_slack:
            slack_msgs_while_down = len(_messages(msg_log))
            slack2 = procs.server("slack-adapter-restarted", "slack", env, logs, slack_env)
            note("slack adapter restarted", pid=slack2.pid)
        done_msg = _wait_message(msg_log, "COMPLETED")
        note("slack thread: completion delivered", thread_ts=done_msg.get("thread_ts"))
        outbox_after = _outbox(env, wf)
    finally:
        for p in (slack2, web_proc, slack_proc, api_sink):
            if p is not None:
                p.stop()
    record = asyncio.run(_record(wf))
    pids = sorted({c["pid"] for c in record["checkpoint_pids"]})
    interactions = record["interactions"]
    checks = {
        "one_workflow_id": {i["workflow_id"] for i in interactions} == {wf},
        "one_trace": len({i["trace_id"] for i in interactions if i["trace_id"]}) == 1,
        "started_in_slack": record["view"]["channel"] == "slack",
        "approved_on_web": record["view"]["approval"]["decided_by"] == "alice"
                           and any(i["channel"] == "web" and i["operation"] == "act" for i in interactions),
        "completed": record["view"]["status"] == "COMPLETED" and cli_body["status"] == "COMPLETED"
                     and rest["status"] == "COMPLETED" and status.returncode == 0,
        "work_spanned_two_processes": len(pids) >= 2,
        # The outbox is at-least-once: a process killed between posting and recording the delivery posts again on
        # restart. What must hold is that the thread saw both statuses, in order, and nothing else.
        "thread_saw_both_updates_in_order": _distinct_in_order([m["text"].split()[-1] for m in _messages(msg_log)])
                                            == ["WAITING_APPROVAL", "COMPLETED"],
        "platform_evals_pass": bool(record["eval"].get("ok")),
    }
    facts: dict[str, Any] = {"workflow_id": wf, "timeline": timeline, "checkpoint_pids": pids,
                             "interactions": [{k: i[k] for k in ("channel", "principal_id", "operation", "action_id",
                                                                 "outcome", "status")} for i in interactions],
                             "slack_messages": [{"text": m["text"], "thread_ts": m.get("thread_ts")} for m in _messages(msg_log)],
                             "redeliveries": len(_messages(msg_log)) - len(_distinct_in_order(
                                 [m["text"].split()[-1] for m in _messages(msg_log)])),
                             "outbox_before_restart": outbox_before_restart, "outbox_after": outbox_after,
                             "spans": len(record["trace"]), "model_calls": len(record["usage"]),
                             "eval_checks": f"{record['eval'].get('passed')}/{record['eval'].get('total')}"}
    if kill_slack:
        completed_t = next(e["t"] for e in timeline if e["event"] == "web: sees COMPLETED")
        killed_t = next(e["t"] for e in timeline if e["event"].startswith("slack adapter killed"))
        restarted_t = next(e["t"] for e in timeline if e["event"] == "slack adapter restarted")
        checks.update({
            "slack_really_down": not next(e for e in timeline if e["event"] == "slack adapter reachable?")["reachable"],
            "completed_while_slack_down": killed_t < completed_t < restarted_t,
            "completion_queued_while_down": any(o["status"] == "COMPLETED" and o["state"] == "PENDING"
                                                for o in outbox_before_restart),
            "no_message_while_down": slack_msgs_while_down == 1,
            "delivered_after_restart": any(o["status"] == "COMPLETED" and o["state"] == "DELIVERED" for o in outbox_after),
        })
        facts["slack_outage_seconds"] = round(restarted_t - killed_t, 1)
    return {"checks": checks, "facts": facts}


def _outbox(env: dict[str, str], wf: str) -> list[dict[str, Any]]:
    db = sqlite3.connect(env["HAI_HEADLESS_DB"])
    db.row_factory = sqlite3.Row
    rows = db.execute("SELECT channel, status, state, attempts, last_error FROM outbox WHERE workflow_id=? ORDER BY id",
                      (wf,)).fetchall()
    db.close()
    return [dict(r) for r in rows]


async def _record(wf: str) -> dict[str, Any]:
    async with open_gateway() as gw:
        rec = gw.platform.record(wf)
        db = sqlite3.connect(os.environ["LAP_PLATFORM_DB"])
        pids = [{"seq": s, "step": st, "pid": p} for s, st, p in
                db.execute("SELECT seq, step, pid FROM checkpoints WHERE workflow_id=? ORDER BY seq", (wf,))]
        db.close()
        return {**rec, "checkpoint_pids": pids, "interactions": gw.store.interactions(wf)}


async def h2(out: Path) -> dict[str, Any]:
    return await asyncio.to_thread(_handoff, out, False)


async def h7(out: Path) -> dict[str, Any]:
    return await asyncio.to_thread(_handoff, out, True)


SCENARIOS = {"h1": h1, "h2": h2, "h4": h4, "h5": h5, "h6": h6, "h7": h7}


def main() -> None:
    name, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        result = asyncio.run(SCENARIOS[name](out))
        result["pass"] = all(result["checks"].values())
    except Exception as exc:  # a scenario that crashes is a failed scenario, with the reason kept
        import traceback

        result = {"pass": False, "checks": {}, "facts": {}, "error": f"{type(exc).__name__}: {exc}",
                  "traceback": traceback.format_exc()[-3000:]}
    result.update(scenario=name, seconds=round(time.monotonic() - t0, 1))
    (out / "result.json").write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps({"scenario": name, "pass": result["pass"], "seconds": result["seconds"],
                      "failed": [k for k, v in result["checks"].items() if not v], "error": result.get("error")}))
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
