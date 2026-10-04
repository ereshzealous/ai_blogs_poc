"""P1–P12: the proofs. Each one changes the control plane, never the agents, and measures what the runtime then did.

    acp experiments --run-id 2026-09-30-recorded    -> runs/<id>/  (summary, facts, checks, proof.txt, P1–P12.json, scenarios/)

Every scenario runs in its own fresh world (a temporary state directory standing in for the control plane's store,
the approval service, the credential broker, the budget meter and the simulated enterprise systems), with the agent
runtime started ONCE as a separate long-lived process. The experiment process plays the control plane's operators:
it publishes changes while that runtime process keeps running.

Side effects are always counted from the systems of record (systems/effects.json, systems/log.jsonl, models.jsonl),
never from what the agent or the runtime reports. Everything is deterministic: logical ticks, no clock, no randomness,
so a rerun is byte-identical (make verify).
"""

from __future__ import annotations

import difflib
import os
import platform
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import yaml

from acp.common import AGENTS_DIR, CONFIG, POC, canon, code_sha256, digest, read_json, read_jsonl, sha256, verify_chain, write_json
from acp.controlplane import ChangeRejected, ControlPlane
from acp.harness import Worker
from acp.proof import card
from acp.runtime import pdp
from acp.runtime.sdk import bucket
from acp.runtime.services import ApprovalService

RUNS = POC / "runs"
INC = {"service": "payment-service", "environment": "production"}
SUP = {"case_id": "CASE-2231", "refund": True}
FIN = {}
EXPERIMENTS = {
    "P1": ("Baseline: the control plane allows", "Under v1, does the incident agent's production restart run, and is it attributed to v1?"),
    "P2": ("One central change, same agent", "Change only the control plane. Does the same process, with the same code and request, now stop for approval?"),
    "P3": ("Approval, then exactly one execution", "Does the held action stay unexecuted until an eligible human approves, and then run exactly once?"),
    "P4": ("Suspend: the kill switch", "Does a central suspension stop new runs and a run already in flight, and only that agent?"),
    "P5": ("Budgets and quotas", "Does a central quota stop the third tool call, and an exhausted budget stop the next run?"),
    "P6": ("Revoke one MCP server for every agent", "Does disabling one server centrally stop every agent that uses it, and no other?"),
    "P7": ("Model governance", "Can the control plane move the default model and withdraw a model without an agent naming one?"),
    "P8": ("Staged rollout and rollback", "Does a canary reach only its bucket of runs, and does rollback return every run to the stable version?"),
    "P9": (
        "When the control plane is unreachable",
        "What does the runtime do without its control plane: for reads, mutations, stale policy, tampered bundles?",
    ),
    "P10": ("Desired vs observed state", "Can the control plane see a runtime that is quietly running an old version, and what it did meanwhile?"),
    "P11": (
        "Baseline: governance inside every agent",
        "Without a control plane, what does the same set of governance changes cost, and when do they take effect?",
    ),
    "P12": ("Governing the control plane itself", "Who may change the control plane, and is every change, accepted or rejected, on the record?"),
}

# The proof hierarchy: what each experiment is for, and the one property it isolates.
ROLE = {
    "P1": ("baseline", "under v1 the protected action is allowed, executed once and attributed to v1"),
    "P2": ("core", "behaviour changes centrally with agent code, runtime process and request held fixed"),
    "P3": ("capability", "a held action stays unexecuted until an eligible approver approves, then runs exactly once"),
    "P4": ("capability", "a central suspension stops new and in-flight runs of one agent, and only that agent"),
    "P5": ("capability", "a central quota and budget stop the run at the configured limit"),
    "P6": ("capability", "disabling one MCP server centrally stops every agent that uses it, and no other"),
    "P7": ("capability", "the model is chosen by the control plane, by data class, never named by the agent"),
    "P8": ("capability", "a canary reaches only its bucket; rollback returns every run to stable"),
    "P9": ("boundary", "without the control plane, reads continue within a staleness bound and mutations fail closed"),
    "P10": ("boundary", "the control plane observes a runtime that has drifted from desired state, and what it did meanwhile"),
    "P11": ("negative-control", "governance embedded in agents: the property is broken by design"),
    "P12": ("governor", "the control plane's own changes are authorized, validated and on a tamper-evident log"),
}


def tree(d: Path) -> dict[str, str]:
    return {str(p.relative_to(d)): sha256(p.read_bytes()) for p in sorted(d.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def changed(before: dict, after: dict) -> list[str]:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


class Scenario:
    """One scenario's world, its long-lived worker processes and its record."""

    def __init__(self, sid: str, variant: str, use_case: str):
        self.sid, self.exp, self.variant, self.use_case = sid, sid.split("-")[0], variant, use_case
        self.dir = Path(tempfile.mkdtemp(prefix=f"acp-{sid}-"))
        self.cp = ControlPlane(self.dir)
        self.workers: dict[str, Worker] = {}
        self.steps: list[dict] = []
        self.checks: list[dict] = []
        self.measures: list[list] = []
        self.transcript: list[dict] = []
        self.pid_labels: dict[tuple[str, int], str] = {}
        self.code_before = code_sha256()

    # ---- world ---------------------------------------------------------------------------------------------------------
    def worker(self, instance: str = "rt-a") -> Worker:
        if instance not in self.workers:
            self.workers[instance] = Worker(self.dir, instance)
        return self.workers[instance]

    def pid_label(self, instance: str, raw: int) -> str:
        """Process ids are volatile, so the record carries a normalized label (rt-a/pid-1, rt-a/pid-2 after a restart);
        the raw ids go to volatile.json, which `make verify` compares with the ids masked (an explicit rule)."""
        if (instance, raw) not in self.pid_labels:
            n = sum(1 for i, _ in self.pid_labels if i == instance) + 1
            self.pid_labels[(instance, raw)] = f"{instance}/pid-{n}"
        return self.pid_labels[(instance, raw)]

    def record(self, instance: str, worker: Worker, req: dict, out: dict, **extra) -> None:
        entry = {"instance": instance, "runtime_pid": self.pid_label(instance, worker.last_pid), "request": req, "response": out, **extra}
        if req.get("op") == "run":
            entry["request_sha256"] = digest({k: req[k] for k in ("agent", "task")})
        self.transcript.append(entry)

    def ask(self, req: dict, instance: str = "rt-a") -> dict:
        w = self.worker(instance)
        out = w.request(req)
        self.record(instance, w, req, out)
        return out

    def run(self, agent: str, task: dict, run_id: str, tick: int, instance: str = "rt-a", checkpoint=None, at=None) -> dict:
        req = {"op": "run", "agent": agent, "task": task, "run_id": run_id, "tick": tick}
        if checkpoint is None:
            return self.ask(req, instance)
        req["checkpoint_after"] = checkpoint
        w = self.worker(instance)
        out = w.run_with_checkpoint(req, at)
        self.record(instance, w, req, out, paused_after_tool_calls=checkpoint)
        return out

    def net(self, instance: str, **kw) -> None:
        write_json(self.dir / "network" / f"{instance}.json", kw)

    def broker(self, available: bool) -> None:
        write_json(self.dir / "broker" / "status.json", {"available": available})

    def effects(self) -> dict:
        return read_json(self.dir / "systems" / "effects.json", {"restarts": [], "deletions": [], "refunds": [], "flags": []})

    def syslog(self) -> list[dict]:
        return read_jsonl(self.dir / "systems" / "log.jsonl")

    def modellog(self) -> list[dict]:
        return read_jsonl(self.dir / "systems" / "models.jsonl")

    def audit(self, instance: str = "rt-a") -> list[dict]:
        return read_jsonl(self.dir / "runtime" / instance / "audit.jsonl")

    def publish(self, change: str, tick: int, **kw) -> str:
        v = self.cp.publish_change(change, tick, **kw)
        c = self.cp.bundle(v)["change"]
        self.step(tick, c["author"], f"publish {change}", f"{v} ({c['kind']})", version=v)
        return v

    # ---- record ------------------------------------------------------------------------------------------------------
    def step(self, tick: int, actor: str, what: str, result: str, **data) -> None:
        self.steps.append({"tick": tick, "actor": actor, "what": what, "result": result, **data})

    def check(self, name: str, passed: bool) -> bool:
        self.checks.append({"experiment": self.exp, "scenario": self.sid, "check": name, "passed": bool(passed)})
        return passed

    def measure(self, key: str, value) -> None:
        self.measures.append([key, value])

    @property
    def same_process(self) -> bool:
        return all(w.same_process for w in self.workers.values())

    def code_unchanged(self) -> bool:
        return all(w.loaded_code_sha256 == self.code_before for w in self.workers.values()) and code_sha256() == self.code_before

    def close(self, run_dir: Path, question: str, inp: dict, expected: str, observed: str, outcome: str, where: str | None, proof: str) -> dict:
        for w in self.workers.values():
            w.close()
        out = run_dir / "scenarios" / self.sid
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(self.dir, out / "state", ignore=shutil.ignore_patterns("__pycache__"))  # bytecode caches are not evidence
        shutil.rmtree(self.dir)
        (out / "transcript.jsonl").write_text("".join(canon(t) + "\n" for t in self.transcript))
        write_json(
            out / "volatile.json",
            {
                "rule": "raw process ids; `make verify` compares this file with the ids masked",
                "runtime_pids": {lab: raw for (_, raw), lab in sorted(self.pid_labels.items(), key=lambda x: x[1])},
            },
        )
        rec = {
            "id": self.sid,
            "experiment": self.exp,
            "variant": self.variant,
            "use_case": self.use_case,
            "question": question,
            "input": inp,
            "expected": expected,
            "observed": observed,
            "outcome": outcome,
            "where": where,
            "measures": self.measures,
            "checks": self.checks,
            "steps": self.steps,
            "agent_code_sha256": self.code_before,
            "proof": proof,
        }
        write_json(out / "scenario.json", rec)
        return rec


def outcome_of(s: Scenario) -> str:
    return "held" if all(c["passed"] for c in s.checks) else "broken"


def last_run_calls(resp: dict) -> list[str]:
    return [f"{c['name']}:{c['status']}" + (f"({c['reason']})" if c.get("reason") else "") for c in resp.get("calls", [])]


def decision_for(resp: dict, name: str) -> dict | None:
    return next((c for c in resp.get("calls", []) if c["name"] == name), None)


# ---- P1 ---------------------------------------------------------------------------------------------------------------
def p1(run_dir: Path) -> list[dict]:
    s = Scenario("P1-C-baseline", "C", "incident-agent restarts payment-service in production under v1")
    s.cp.bootstrap(0)
    s.step(0, "platform.admin", "bootstrap desired state", "v1")
    r = s.run("incident-agent", INC, "run-001", 10)
    rs = decision_for(r, "restart_service")
    ev = [e for e in s.audit() if e["event"] == "action.executed"]
    restarts = s.effects()["restarts"]
    s.step(10, "incident-agent", "restart_service payment-service production", f"{rs['status']} under {rs['config_version']}")
    s.check("restart_service decided under v1", rs["config_version"] == "v1")
    s.check("restart_service executed (decision allow)", rs["status"] == "executed")
    s.check("deploy system of record shows exactly 1 restart", len(restarts) == 1)
    s.check(
        "audit event names the config version and the rule",
        bool(ev) and ev[0]["config_version"] == "v1" and ev[0]["decision"]["rule"].startswith("agents.incident-agent.tools.restart_service"),
    )
    s.check(
        "the system saw a short-lived, tool-scoped credential, not a static secret",
        any(x["tool"] == "restart_service" and str(x["credential"]).startswith("cred-") for x in s.syslog()),
    )
    s.check("agent code unchanged, one runtime process", s.code_unchanged() and s.same_process)
    s.measure("config_version", rs["config_version"])
    s.measure("decision", "ALLOW")
    s.measure("restarts", len(restarts))
    s.measure("rule", ev[0]["decision"]["rule"])
    proof = card(
        "P1",
        "BASELINE: THE CONTROL PLANE ALLOWS",
        [
            ("Agent", "incident-agent"),
            ("Agent code", f"sha256 {s.code_before[:12]}…"),
            ("Request", "restart_service payment-service production"),
            ("Policy version", "v1"),
            ("Rule", ev[0]["decision"]["rule"]),
            ("Decision", "ALLOW"),
            ("Executed", "YES · 1 restart in the deploy system"),
            ("Credential", "minted for restart_service only, 5-tick TTL"),
        ],
        s.checks,
    )
    return [
        s.close(
            run_dir,
            EXPERIMENTS["P1"][1],
            {"agent": "incident-agent", "task": INC, "config": "v1"},
            "ALLOW, executed once, attributed to v1",
            f"{rs['status']} under {rs['config_version']}; restarts={len(restarts)}",
            outcome_of(s),
            None,
            proof,
        )
    ]


# ---- P2 ---------------------------------------------------------------------------------------------------------------
CHEATS = ("code", "process", "request")


def p2(run_dir: Path, cheat: str | None = None) -> list[dict]:
    """The core proof.  `cheat` exists only for tests/test_cheating.py: it breaks one of the three things P2 holds fixed
    (agent code, runtime process, request) between the two requests, and P2 must then fail.  "code" edits an agent file,
    so it refuses to run outside a scratch copy of the POC."""
    assert cheat in (None, *CHEATS), cheat
    assert cheat != "code" or os.environ.get("ACP_SCRATCH_COPY") == str(POC), "cheat=code edits agent source: scratch copies only"
    s = Scenario("P2-C-central-change", "C", "the same restart request, before and after one central policy change")
    s.cp.bootstrap(0)
    before = s.run("incident-agent", INC, "run-001", 10)
    b = decision_for(before, "restart_service")
    restarts_v1 = len(s.effects()["restarts"])
    s.step(10, "incident-agent", "restart_service payment-service production", f"{b['status']} under {b['config_version']}")
    code_tree, cp_tree = tree(POC / "acp"), tree(s.dir / "controlplane")
    v2 = s.publish("restart-requires-approval", 20)
    code_changed, cp_changed = changed(code_tree, tree(POC / "acp")), changed(cp_tree, tree(s.dir / "controlplane"))
    task = INC
    if cheat == "code":
        with (AGENTS_DIR / "incident_agent.py").open("a") as f:
            f.write("# edited between the two requests\n")
    elif cheat == "process":
        s.workers.pop("rt-a").close()  # the next request starts a new runtime process
    elif cheat == "request":
        task = {**INC, "ticket": "INC-2"}  # one extra field: the agent ignores it, the request hash does not
    after = s.run("incident-agent", task, "run-002", 30)
    a = decision_for(after, "restart_service")
    s.step(30, "incident-agent", "restart_service payment-service production (same request)", f"{a['status']} under {a['config_version']} ({a['approval_id']})")
    restarts = s.effects()["restarts"]
    approvals = ApprovalService(s.dir).all()
    runs_ = [t for t in s.transcript if t["request"]["op"] == "run"]
    pid_b, pid_a = runs_[0]["runtime_pid"], runs_[1]["runtime_pid"]
    hash_b, hash_a = runs_[0]["request_sha256"], runs_[1]["request_sha256"]
    sha_b, sha_a = s.code_before, code_sha256()
    redeploys = len(s.pid_labels) - len({i for i, _ in s.pid_labels})  # runtime processes started beyond one per instance
    s.check(f"same request: request hash {hash_b[:12]} before and after", hash_b == hash_a)
    s.check(f"same runtime process: {pid_b} answered both requests, never restarted", pid_b == pid_a and s.same_process)
    s.check(f"same agent code: sha256 {sha_b[:12]} before, at import and after", s.code_unchanged() and sha_b == sha_a)
    s.check("files changed under acp/ by the policy change: 0", code_changed == [])
    s.check(
        "control plane store changed (new bundle, signature, pointer, changelog)",
        {"bundles/v2.json", "bundles/v2.sig", "current.json", "changelog.jsonl"} <= set(cp_changed),
    )
    s.check("before: v1 ALLOW, executed", b["config_version"] == "v1" and b["status"] == "executed")
    s.check("after: v2 APPROVAL_REQUIRED, not executed", a["config_version"] == v2 and a["status"] == "pending_approval")
    s.check("deploy system still shows 1 restart (the side effect did not happen)", len(restarts) == 1)
    s.check("approval request emitted and pending", approvals.get(a["approval_id"], {}).get("status") == "pending")
    ev = [e for e in s.audit() if e["event"] in ("action.executed", "approval.requested")]
    for k, v in (
        ("before_version", "v1"),
        ("before_decision", "ALLOW"),
        ("before_executed", "yes"),
        ("after_version", v2),
        ("after_decision", "APPROVAL_REQUIRED"),
        ("after_executed", "no"),
        ("approval_id", a["approval_id"]),
        ("acp_files_changed", len(code_changed)),
        ("control_plane_files_changed", len(cp_changed)),
        ("restarts", len(restarts)),
        ("agent_code_sha256", s.code_before[:12]),
        ("agent_sha_before", sha_b[:12]),
        ("agent_sha_after", sha_a[:12]),
        ("runtime_pid_before", pid_b),
        ("runtime_pid_after", pid_a),
        ("request_hash_before", hash_b[:12]),
        ("request_hash_after", hash_a[:12]),
        ("restarts_after_v1", restarts_v1),
        ("restarts_after_v2", len(restarts)),
        ("side_effect_delta", len(restarts) - restarts_v1),
        ("agent_edits", len(code_changed)),
        ("redeploys", redeploys),
    ):
        s.measure(k, v)
    proof = card(
        "P2",
        "CENTRAL POLICY CHANGE",
        [
            ("Agent", "incident-agent"),
            ("Agent code", f"sha256 {s.code_before[:12]}…  UNCHANGED"),
            ("Runtime process", "started once · SAME process for both requests"),
            ("Request", "restart_service payment-service production (identical)"),
            ("Before", "v1 → ALLOW → executed"),
            ("Central change", f"{v2} · restart-requires-approval · platform.admin"),
            ("After", f"{v2} → APPROVAL_REQUIRED → NOT executed"),
            ("Approval", f"{a['approval_id']} (pending)"),
            ("Files changed", f"acp/: {len(code_changed)} · control plane store: {len(cp_changed)}"),
            ("BEFORE → AFTER", ""),
            ("  agent SHA", f"{sha_b[:12]} → {sha_a[:12]}  ({'same' if sha_b == sha_a else 'CHANGED'})"),
            ("  runtime PID", f"{pid_b} → {pid_a}  ({'same process' if pid_b == pid_a else 'RESTARTED'})"),
            ("  request hash", f"{hash_b[:12]} → {hash_a[:12]}  ({'same' if hash_b == hash_a else 'CHANGED'})"),
            ("  control plane", f"v1 → {v2}"),
            ("  decision", "ALLOW → APPROVAL_REQUIRED"),
            ("  restarts", f"{restarts_v1} → {len(restarts)}  (no new side effect)"),
            ("  agent edits", f"{len(code_changed)} · redeploys {redeploys}"),
            ("Audit", " → ".join(f"{e['event']} ({e['config_version']})" for e in ev)),
        ],
        s.checks,
    )
    return [
        s.close(
            run_dir,
            EXPERIMENTS["P2"][1],
            {"agent": "incident-agent", "task": INC, "change": "restart-requires-approval"},
            "same process, same code, same request: v1 executes, v2 holds for approval",
            f"v1 {b['status']} → {v2} {a['status']}; restarts={len(restarts)}",
            outcome_of(s),
            None,
            proof,
        )
    ]


# ---- P3 ---------------------------------------------------------------------------------------------------------------
def p3(run_dir: Path) -> list[dict]:
    s = Scenario("P3-C-approval", "C", "an approval-required restart: refused approvers, one approval, one execution")
    s.cp.bootstrap(0)
    s.publish("restart-requires-approval", 5)
    r = s.run("incident-agent", INC, "run-001", 10)
    aid = decision_for(r, "restart_service")["approval_id"]
    s.step(14, "incident-agent", "restart_service payment-service production", f"pending_approval {aid}")
    appr = ApprovalService(s.dir)
    early = s.ask({"op": "resume", "approval_id": aid, "tick": 16})
    s.step(16, "runtime", "resume before any decision", early["reason"])
    after_early = len(s.effects()["restarts"])
    tries = []
    for tick, who in ((18, "incident-agent"), (19, "support.lead"), (20, "ic.dev")):
        ok, why = appr.decide(aid, who, True, tick)
        tries.append((who, ok, why))
        s.step(tick, who, f"approve {aid}", why)
    first = s.ask({"op": "resume", "approval_id": aid, "tick": 22})
    s.step(22, "runtime", "resume after approval", first["reason"])
    second = s.ask({"op": "resume", "approval_id": aid, "tick": 24})
    s.step(24, "runtime", "resume again (duplicate delivery)", second["reason"])
    restarts = s.effects()["restarts"]
    ev = [e for e in s.audit() if e["event"] == "action.executed"]
    s.check("held action not executed before approval (resume refused, 0 restarts)", early["executed"] is False and after_early == 0)
    s.check("the agent cannot approve its own action", tries[0][1] is False)
    s.check("an ineligible principal cannot approve", tries[1][1] is False)
    s.check("the eligible incident commander's approval is accepted", tries[2][1] is True)
    s.check("resume after approval executes under the current policy", first["executed"] is True and first["config_version"] == "v2")
    s.check("a second resume does not execute again (ALREADY_EXECUTED)", second["executed"] is False and second["reason"] == "ALREADY_EXECUTED")
    s.check("deploy system shows exactly 1 restart", len(restarts) == 1)
    s.check("the executed event carries the approval id", bool(ev) and ev[0]["approval_id"] == aid)
    s.check("agent code unchanged, one runtime process", s.code_unchanged() and s.same_process)
    for k, v in (
        ("approval_id", aid),
        ("restarts_before_approval", after_early),
        ("refused_approvers", sum(1 for t in tries if not t[1])),
        ("approved_by", "ic.dev"),
        ("restarts_after", len(restarts)),
        ("duplicate_resume", second["reason"]),
    ):
        s.measure(k, v)
    proof = card(
        "P3",
        "APPROVAL, THEN EXACTLY ONE EXECUTION",
        [
            ("Agent", "incident-agent"),
            ("Policy version", "v2 (restart requires approval)"),
            ("Held action", f"{aid} · restart_service payment-service production"),
            ("Before approval", f"resume → {early['reason']} · restarts 0"),
            ("incident-agent", f"approve → {tries[0][2]}"),
            ("support.lead", f"approve → {tries[1][2]}"),
            ("ic.dev", f"approve → {tries[2][2]}"),
            ("Resume", f"{first['reason']} · restarts 1"),
            ("Resume again", f"{second['reason']} · restarts still 1"),
        ],
        s.checks,
    )
    return [
        s.close(
            run_dir,
            EXPERIMENTS["P3"][1],
            {"agent": "incident-agent", "task": INC, "config": "v2"},
            "0 restarts until ic.dev approves; then exactly 1",
            f"before approval {after_early}; after {len(restarts)}; duplicate resume {second['reason']}",
            outcome_of(s),
            None,
            proof,
        )
    ]


# ---- P4 ---------------------------------------------------------------------------------------------------------------
def p4(run_dir: Path) -> list[dict]:
    s = Scenario("P4-C-suspend", "C", "suspend incident-agent centrally: mid-run, new runs, other agents, restore")
    s.cp.bootstrap(0)
    box = {}

    def suspend(cp):
        box["v"] = s.publish("suspend-incident-agent", cp["tick"])

    inflight = s.run("incident-agent", INC, "run-001", 10, checkpoint=1, at=suspend)
    s.step(11, "incident-agent", "query_logs (before suspension)", decision_for(inflight, "query_logs")["status"])
    after_calls = inflight["calls"][1:]
    s.step(12, "incident-agent", "rest of run-001 after suspension", ", ".join(last_run_calls({"calls": after_calls})))
    mcalls_before = len(s.modellog())
    new = s.run("incident-agent", INC, "run-002", 20)
    mcalls_after_new = len(s.modellog())
    s.step(20, "incident-agent", "new run run-002", f"{new['status']} ({new.get('reason')})")
    other = s.run("support-agent", SUP, "run-003", 30)
    s.step(30, "support-agent", "run-003 (not suspended)", ", ".join(last_run_calls(other)))
    restore_alone = None
    try:
        s.cp.publish_change("restore-incident-agent", 40)
    except ChangeRejected as e:
        restore_alone = str(e)
    s.step(40, "oncall.ic", "restore incident-agent alone", f"rejected: {restore_alone}")
    v_restore = s.publish("restore-incident-agent", 41, second_approver="sre.lead")
    back = s.run("incident-agent", {**INC, "environment": "staging"}, "run-004", 50)
    s.step(50, "incident-agent", "run-004 after restore (staging)", ", ".join(last_run_calls(back)))
    restarts = s.effects()["restarts"]
    executed_after = [c for c in after_calls if c["status"] == "executed"]
    s.check("in-flight run: every call after the suspension was denied (0 executed)", len(executed_after) == 0 and len(after_calls) > 0)
    s.check(
        "in-flight run: denial reason is AGENT_SUSPENDED under the new version",
        all(c["reason"] == "AGENT_SUSPENDED" and c["config_version"] == box["v"] for c in after_calls),
    )
    s.check(
        "new run denied at start: 0 tool calls, 0 model calls",
        new["status"] == "denied" and new["reason"] == "AGENT_SUSPENDED" and not new["calls"] and mcalls_after_new == mcalls_before,
    )
    s.check("no production restart happened", not any(x["environment"] == "production" for x in restarts))
    s.check("support-agent unaffected (every call executed)", all(c["status"] == "executed" for c in other["calls"]))
    s.check("restoring needs a second person: oncall.ic alone rejected", restore_alone is not None)
    s.check("restore with sre.lead as second approver works at the next run", all(c["status"] == "executed" for c in back["calls"]))
    s.check("agent code unchanged, one runtime process", s.code_unchanged() and s.same_process)
    for k, v in (
        ("suspend_version", box["v"]),
        ("inflight_calls_after_suspension", len(after_calls)),
        ("inflight_executed_after_suspension", len(executed_after)),
        ("new_run", f"{new['status']} {new['reason']}"),
        ("other_agent_calls_executed", sum(c["status"] == "executed" for c in other["calls"])),
        ("restore_alone", "rejected"),
        ("restore_version", v_restore),
    ):
        s.measure(k, v)
    proof = card(
        "P4",
        "SUSPEND: THE KILL SWITCH",
        [
            ("Agent", "incident-agent · status active → suspended"),
            ("Central change", f"{box['v']} · suspend-incident-agent · oncall.ic (break-glass)"),
            ("Run in flight", f"run-001 paused after query_logs; {len(after_calls)} later calls → {len(executed_after)} executed"),
            ("New run", f"run-002 → DENIED {new['reason']} · 0 tool calls · 0 model calls"),
            ("Other agents", "support-agent run-003 → every call executed"),
            ("Restore alone", "oncall.ic → REJECTED (widening needs a second approver)"),
            ("Restore", f"{v_restore} · oncall.ic + sre.lead → run-004 executes"),
        ],
        s.checks,
    )
    return [
        s.close(
            run_dir,
            EXPERIMENTS["P4"][1],
            {"agent": "incident-agent", "change": "suspend-incident-agent", "checkpoint_after": 1},
            "every later call of the in-flight run denied; new runs denied; other agents untouched; restore needs two people",
            f"{len(executed_after)} of {len(after_calls)} in-flight calls executed after suspension; new run {new['reason']}",
            outcome_of(s),
            None,
            proof,
        )
    ]


# ---- P5 ---------------------------------------------------------------------------------------------------------------
def p5(run_dir: Path) -> list[dict]:
    s = Scenario("P5-C-budgets", "C", "a central tool-call quota and an exhausted daily budget for support-agent")
    s.cp.bootstrap(0)
    before = s.run("support-agent", SUP, "run-001", 10)
    s.step(10, "support-agent", "run-001 under v1", ", ".join(last_run_calls(before)))
    v2 = s.publish("support-tool-call-budget", 20)
    capped = s.run("support-agent", SUP, "run-002", 30)
    tools_seq = [c for c in capped["calls"] if c["kind"] == "tool"]
    s.step(30, "support-agent", f"run-002 under {v2}", ", ".join(last_run_calls({"calls": tools_seq})))
    v3 = s.publish("support-daily-budget-exhausted", 40)
    spent = read_json(s.dir / "budget" / "spend.json")["support-agent"]
    broke = s.run("support-agent", SUP, "run-003", 50)
    s.step(50, "support-agent", f"run-003 under {v3}", f"{broke['status']} {broke.get('reason')}")
    refunds = s.effects()["refunds"]
    s.check("before the quota: 3 tool calls executed, 1 refund", sum(c["status"] == "executed" for c in before["calls"] if c["kind"] == "tool") == 3)
    s.check("call 1 ALLOW, call 2 ALLOW", [c["status"] for c in tools_seq[:2]] == ["executed", "executed"])
    s.check("call 3 DENY TOOL_CALL_BUDGET_EXCEEDED", tools_seq[2]["status"] == "denied" and tools_seq[2]["reason"] == "TOOL_CALL_BUDGET_EXCEEDED")
    s.check("billing system shows 1 refund (the capped run refunded nothing)", len(refunds) == 1)
    s.check("exhausted daily budget: next run denied at start", broke["status"] == "denied" and broke["reason"] == "DAILY_BUDGET_EXHAUSTED")
    s.check("the budget is metered centrally (shared spend meter), not per process", spent > 0)
    s.check("agent code unchanged, one runtime process", s.code_unchanged() and s.same_process)
    for k, v in (
        ("quota_version", v2),
        ("max_tool_calls", 2),
        ("call_3", f"{tools_seq[2]['status']} {tools_seq[2]['reason']}"),
        ("refunds", len(refunds)),
        ("budget_version", v3),
        ("spent_usd", spent),
        ("run_after_budget", f"{broke['status']} {broke['reason']}"),
    ):
        s.measure(k, v)
    proof = card(
        "P5",
        "BUDGETS AND QUOTAS",
        [
            ("Agent", "support-agent"),
            ("Central change", f"{v2} · max_tool_calls = 2 · support.lead"),
            ("CALL 1", f"read_case → {tools_seq[0]['status'].upper()}"),
            ("CALL 2", f"query_logs → {tools_seq[1]['status'].upper()}"),
            ("CALL 3", f"refund_customer → DENY · {tools_seq[2]['reason']}"),
            ("Refunds", f"{len(refunds)} (from run-001, before the quota)"),
            ("Central change", f"{v3} · daily budget below today's spend (${spent})"),
            ("Next run", f"run-003 → DENIED {broke['reason']}"),
        ],
        s.checks,
    )
    return [
        s.close(
            run_dir,
            EXPERIMENTS["P5"][1],
            {"agent": "support-agent", "task": SUP, "changes": ["support-tool-call-budget", "support-daily-budget-exhausted"]},
            "call 3 denied with TOOL_CALL_BUDGET_EXCEEDED; next run denied with DAILY_BUDGET_EXHAUSTED",
            f"call 3 {tools_seq[2]['reason']}; run-003 {broke['reason']}",
            outcome_of(s),
            None,
            proof,
        )
    ]


# ---- P6 ---------------------------------------------------------------------------------------------------------------
def p6(run_dir: Path) -> list[dict]:
    s = Scenario("P6-C-revoke-mcp", "C", "disable observability-mcp once: incident-agent and support-agent lose it, finance-agent does not")
    s.cp.bootstrap(0)
    sup = {"case_id": "CASE-2231", "refund": False}
    rows = {}
    for i, (agent, task) in enumerate((("incident-agent", {**INC, "environment": "staging"}), ("support-agent", sup), ("finance-agent", FIN))):
        r = s.run(agent, task, f"run-00{i + 1}", 10 + i * 5)
        rows[(agent, "before")] = r
        s.step(10 + i * 5, agent, "before revocation", ", ".join(last_run_calls(r)))
    v2 = s.publish("revoke-observability-mcp", 30)
    n_obs_before = sum(1 for x in s.syslog() if x["server"] == "observability-mcp")
    for i, (agent, task) in enumerate((("incident-agent", {**INC, "environment": "staging"}), ("support-agent", sup), ("finance-agent", FIN))):
        r = s.run(agent, task, f"run-00{i + 4}", 40 + i * 5)
        rows[(agent, "after")] = r
        s.step(40 + i * 5, agent, "after revocation", ", ".join(last_run_calls(r)))
    obs_after = [x for x in s.syslog() if x["server"] == "observability-mcp" and x["tick"] > 30]
    ql = lambda a, w: decision_for(rows[(a, w)], "query_logs")
    s.check("before: incident-agent query_logs ALLOW", ql("incident-agent", "before")["status"] == "executed")
    s.check("before: support-agent query_logs ALLOW", ql("support-agent", "before")["status"] == "executed")
    s.check("after: incident-agent query_logs DENY MCP_SERVER_DISABLED", ql("incident-agent", "after")["reason"] == "MCP_SERVER_DISABLED")
    s.check("after: support-agent query_logs DENY MCP_SERVER_DISABLED", ql("support-agent", "after")["reason"] == "MCP_SERVER_DISABLED")
    s.check("observability-mcp received 0 calls after the revocation", len(obs_after) == 0)
    s.check("finance-agent (no observability tools) unaffected", all(c["status"] == "executed" for c in rows[("finance-agent", "after")]["calls"]))
    s.check("one central change, 0 agent files changed", s.code_unchanged() and s.same_process)
    denied_after = sum(1 for a in ("incident-agent", "support-agent") for c in rows[(a, "after")]["calls"] if c.get("reason") == "MCP_SERVER_DISABLED")
    for k, v in (
        ("revoke_version", v2),
        ("observability_calls_before", n_obs_before),
        ("observability_calls_after", len(obs_after)),
        ("calls_denied_mcp_disabled", denied_after),
        ("agents_affected", 2),
        ("agents_unaffected", 1),
    ):
        s.measure(k, v)
    proof = card(
        "P6",
        "REVOKE ONE MCP SERVER FOR EVERY AGENT",
        [
            ("Shared tool", "query_logs (observability-mcp)"),
            ("Before", "incident-agent → ALLOW · support-agent → ALLOW"),
            ("Central change", f"{v2} · observability-mcp = disabled · platform.admin (break-glass)"),
            ("After", "incident-agent → DENY · support-agent → DENY  (MCP_SERVER_DISABLED)"),
            ("Unaffected", "finance-agent → every call executed"),
            ("observability-mcp", f"{n_obs_before} calls before · {len(obs_after)} after"),
            ("Agent code", "UNCHANGED · 0 files edited · 0 redeploys"),
        ],
        s.checks,
    )
    return [
        s.close(
            run_dir,
            EXPERIMENTS["P6"][1],
            {"agents": ["incident-agent", "support-agent", "finance-agent"], "change": "revoke-observability-mcp"},
            "both dependent agents denied, finance untouched, 0 calls reach the server",
            f"{len(obs_after)} observability calls after revoke; {denied_after} calls denied",
            outcome_of(s),
            None,
            proof,
        )
    ]


# ---- P7 ---------------------------------------------------------------------------------------------------------------
def p7(run_dir: Path) -> list[dict]:
    s = Scenario("P7-C-models", "C", "move the default model, then withdraw the only model allowed for confidential data")
    s.cp.bootstrap(0)
    sup = {"case_id": "CASE-2231", "refund": False}
    stg = {**INC, "environment": "staging"}
    seen = []
    for tick, label in ((10, "v1"),):
        seen.append((label, s.run("incident-agent", stg, "run-001", tick), s.run("support-agent", sup, "run-002", tick + 5)))
    v2 = s.publish("migrate-default-model", 20)
    seen.append((v2, s.run("incident-agent", stg, "run-003", 30), s.run("support-agent", sup, "run-004", 35)))
    v3 = s.publish("withdraw-private-model", 40)
    seen.append((v3, s.run("incident-agent", stg, "run-005", 50), s.run("support-agent", sup, "run-006", 55)))
    model = lambda r: next((c["name"] if c["status"] == "executed" else f"DENIED {c['reason']}" for c in r["calls"] if c["kind"] == "model"), None)
    for label, inc, sp in seen:
        s.step(0, "runtime", f"model calls under {label}", f"incident-agent → {model(inc)} · support-agent (confidential) → {model(sp)}")
    names = set(yaml.safe_load((CONFIG / "desired-state.yaml").read_text())["models"]["catalog"])
    src = "".join(p.read_text() for p in AGENTS_DIR.glob("*.py"))
    conf = [m for m in s.modellog() if m["data_class"] == "confidential"]
    cat = yaml.safe_load((CONFIG / "desired-state.yaml").read_text())["models"]["catalog"]
    s.check("agent source names no model (0 catalog names in acp/agents/)", not any(n in src for n in names))
    s.check("v1: incident-agent served by fast-model", model(seen[0][1]) == "fast-model")
    s.check(f"{v2}: incident-agent served by large-model, agent unchanged", model(seen[1][1]) == "large-model")
    s.check(
        "confidential data always served by private-model while it is allowed", model(seen[0][2]) == "private-model" and model(seen[1][2]) == "private-model"
    )
    s.check(
        f"{v3}: private-model withdrawn → confidential call DENIED, no fallback to a public model",
        model(seen[2][2]) == "DENIED NO_ALLOWED_MODEL_FOR_DATA_CLASS",
    )
    s.check("no confidential prompt ever reached a model without confidential clearance", all("confidential" in cat[m["model"]]["data_classes"] for m in conf))
    s.check("agent code unchanged, one runtime process", s.code_unchanged() and s.same_process)
    for k, v in (
        ("v1_incident_model", model(seen[0][1])),
        ("v2_incident_model", model(seen[1][1])),
        ("v3_support_model", model(seen[2][2])),
        ("confidential_calls", len(conf)),
        ("model_names_in_agent_code", sum(src.count(n) for n in names)),
    ):
        s.measure(k, v)
    proof = card(
        "P7",
        "MODEL GOVERNANCE",
        [
            ("Agents", "incident-agent (internal data) · support-agent (confidential case)"),
            ("Agent code", "names no model: 0 catalog names in acp/agents/"),
            ("v1", f"incident → {model(seen[0][1])} · support → {model(seen[0][2])}"),
            ("Central change", f"{v2} · default model → large-model (platform.admin + ml.lead)"),
            (v2, f"incident → {model(seen[1][1])} · support → {model(seen[1][2])}"),
            ("Central change", f"{v3} · private-model withdrawn (break-glass)"),
            (v3, f"incident → {model(seen[2][1])} · support → DENIED (no fallback to a public model)"),
        ],
        s.checks,
    )
    return [
        s.close(
            run_dir,
            EXPERIMENTS["P7"][1],
            {"agents": ["incident-agent", "support-agent"], "changes": ["migrate-default-model", "withdraw-private-model"]},
            "default moves with no agent change; confidential data never falls back to an uncleared model",
            f"{model(seen[0][1])} → {model(seen[1][1])}; confidential under {v3}: {model(seen[2][2])}",
            outcome_of(s),
            None,
            proof,
        )
    ]


# ---- P8 ---------------------------------------------------------------------------------------------------------------
def p8(run_dir: Path) -> list[dict]:
    s = Scenario("P8-C-canary", "C", "roll a new default model out to 25% of finance-agent runs, roll back, then promote")
    s.cp.bootstrap(0)
    v2 = s.publish("migrate-default-model", 5, activate=False)
    s.cp.rollout(v2, 25, "platform.admin", 6)
    s.step(6, "platform.admin", f"rollout {v2} to 25% of runs", "canary")
    phases, tick = {}, 10
    for phase, n in (("canary", 20), ("rollback", 20), ("promoted", 10)):
        if phase == "rollback":
            s.cp.rollback("platform.admin", tick)
            s.step(tick, "platform.admin", "rollback", "stable v1 only")
        if phase == "promoted":
            s.cp.rollout(v2, 25, "platform.admin", tick)
            s.cp.promote("platform.admin", tick + 1)
            s.step(tick + 1, "platform.admin", f"promote {v2}", f"stable {v2}")
        rows = []
        for i in range(n):
            tick += 5
            rid = f"{phase}-{i + 1:02d}"
            r = s.run("finance-agent", FIN, rid, tick)
            m = next(c for c in r["calls"] if c["kind"] == "model")
            rows.append({"run_id": rid, "bucket": bucket(rid), "versions": r["versions"], "model": m["name"]})
        phases[phase] = rows
        cnt = Counter(tuple(x["versions"]) for x in rows)
        s.step(tick, "finance-agent", f"{n} runs ({phase})", ", ".join(f"{'+'.join(k)}: {v}" for k, v in sorted(cnt.items())))
    can = phases["canary"]
    on_v2 = [x for x in can if x["versions"] == [v2]]
    s.check("canary reached some but not all runs", 0 < len(on_v2) < len(can))
    s.check("canary membership = deterministic bucket < 25", all((x["versions"] == [v2]) == (x["bucket"] < 25) for x in can))
    s.check(
        "every run used exactly one version, and its model matches it",
        all(len(x["versions"]) == 1 and x["model"] == ("large-model" if x["versions"] == [v2] else "fast-model") for p in phases.values() for x in p),
    )
    s.check("after rollback: 0 runs on the canary version", all(x["versions"] == ["v1"] for x in phases["rollback"]))
    s.check("after promote: every run on the new version", all(x["versions"] == [v2] for x in phases["promoted"]))
    s.check("agent code unchanged, one runtime process", s.code_unchanged() and s.same_process)
    for k, v in (
        ("canary_version", v2),
        ("canary_percent", 25),
        ("canary_runs", len(can)),
        ("canary_runs_on_new", len(on_v2)),
        ("rollback_runs_on_new", sum(x["versions"] == [v2] for x in phases["rollback"])),
        ("promoted_runs_on_new", sum(x["versions"] == [v2] for x in phases["promoted"])),
    ):
        s.measure(k, v)
    write_json(run_dir / "scenarios" / "_p8_runs.json", phases)
    proof = card(
        "P8",
        "STAGED ROLLOUT AND ROLLBACK",
        [
            ("Agent", "finance-agent (20 + 20 + 10 runs)"),
            ("Change", f"{v2} · default model → large-model, published inactive"),
            ("Canary 25%", f"{len(on_v2)} of {len(can)} runs on {v2} (large-model) · rest on v1"),
            ("Rollback", f"{sum(x['versions'] == [v2] for x in phases['rollback'])} of 20 runs on {v2}"),
            ("Promote", f"{sum(x['versions'] == [v2] for x in phases['promoted'])} of 10 runs on {v2}"),
            ("Agent code", "UNCHANGED · no redeploy at any step"),
        ],
        s.checks,
    )
    rec = s.close(
        run_dir,
        EXPERIMENTS["P8"][1],
        {"agent": "finance-agent", "rollout": {"version": v2, "percent": 25}},
        "a deterministic ~quarter of runs on the canary; none after rollback; all after promotion",
        f"canary {len(on_v2)}/{len(can)}; rollback 0/20; promoted 10/10",
        outcome_of(s),
        None,
        proof,
    )
    shutil.move(str(run_dir / "scenarios" / "_p8_runs.json"), str(run_dir / "scenarios" / s.sid / "runs.json"))
    return [rec]


# ---- P9 ---------------------------------------------------------------------------------------------------------------
def p9(run_dir: Path) -> list[dict]:
    out = []
    # (a) outage: last-known-good for reads, fail closed for mutations, stale bound, a kill switch that cannot land
    s = Scenario("P9-C-outage", "C", "the control plane becomes unreachable from the runtime, and a suspension is published during the outage")
    s.cp.bootstrap(0)
    warm = s.run("incident-agent", INC, "run-001", 10)
    s.step(10, "incident-agent", "warm run (control plane reachable)", ", ".join(last_run_calls(warm)))
    s.net("rt-a", unreachable=True)
    s.step(20, "network", "control plane unreachable from rt-a", "partition")
    down = s.run("incident-agent", INC, "run-002", 20)
    s.step(20, "incident-agent", "run during outage", ", ".join(last_run_calls(down)))
    v2 = s.publish("suspend-incident-agent", 25)
    during = s.run("incident-agent", INC, "run-003", 30)
    s.step(30, "incident-agent", f"run after {v2} (suspension) was published, still partitioned", ", ".join(last_run_calls(during)))
    stale = s.run("incident-agent", INC, "run-004", 60)
    s.step(60, "incident-agent", "run beyond max_staleness (30 ticks)", f"{stale['status']} {stale.get('reason')}")
    s.net("rt-a")
    s.step(70, "network", "partition heals", "reachable")
    healed = s.run("incident-agent", INC, "run-005", 70)
    s.step(70, "incident-agent", "run after recovery", f"{healed['status']} {healed.get('reason')}")
    ev = s.audit()
    restarts = s.effects()["restarts"]
    lkg_reads = [e for e in ev if e.get("config_source") == "last_known_good" and e["event"] == "tool.executed"]
    rs_down = decision_for(down, "restart_service")
    s.check(
        "reads during the outage ran on the last-known-good bundle (v1)",
        decision_for(down, "query_logs")["status"] == "executed" and all(e["config_version"] == "v1" for e in lkg_reads) and len(lkg_reads) > 0,
    )
    s.check(
        "production mutation during the outage failed closed (CONTROL_PLANE_UNREACHABLE)",
        rs_down["status"] == "denied" and rs_down["reason"] == "CONTROL_PLANE_UNREACHABLE",
    )
    s.check("deploy system: only the warm run's restart (1)", len(restarts) == 1)
    s.check(
        "QUALIFIED: the suspension could not reach a partitioned runtime; reads continued under v1", decision_for(during, "query_logs")["status"] == "executed"
    )
    s.check("beyond max_staleness every run is denied (POLICY_STALE)", stale["status"] == "denied" and stale["reason"] == "POLICY_STALE")
    s.check("after recovery the suspension lands at the next enforcement point", healed["status"] == "denied" and healed["reason"] == "AGENT_SUSPENDED")
    reads_after_suspend = sum(1 for c in during["calls"] if c["status"] == "executed")
    for k, v in (
        ("lkg_version", "v1"),
        ("reads_on_lkg", len(lkg_reads)),
        ("mutation_during_outage", rs_down["reason"]),
        ("calls_executed_after_suspension_published", reads_after_suspend),
        ("max_staleness_ticks", 30),
        ("stale_run", stale["reason"]),
        ("recovered_run", healed["reason"]),
    ):
        s.measure(k, v)
    proof = card(
        "P9a",
        "CONTROL PLANE UNREACHABLE",
        [
            ("Runtime", "rt-a · last-known-good v1 cached"),
            ("Read (query_logs)", "ALLOW from last-known-good v1"),
            ("Mutation (restart)", f"DENY · {rs_down['reason']} (fail closed)"),
            ("Suspension", f"{v2} published during the partition"),
            ("…after it", f"{reads_after_suspend} read/model calls still executed on v1  ← QUALIFIED"),
            ("Past staleness", f"DENY · {stale['reason']} for everything"),
            ("Partition heals", f"next run → DENY · {healed['reason']}"),
        ],
        s.checks,
        verdict="QUALIFIED · held within the stated bound (max staleness, fail-closed mutations)",
    )
    out.append(
        s.close(
            run_dir,
            EXPERIMENTS["P9"][1],
            {"agent": "incident-agent", "failure": "control plane unreachable", "max_staleness_ticks": 30},
            "reads on last-known-good, mutations fail closed, everything denied past the staleness bound",
            f"mutation {rs_down['reason']}; {reads_after_suspend} calls ran after the suspension was published",
            "qualified",
            "config.unreachable: a suspension cannot reach a partitioned runtime; exposure bounded by max_staleness and fail-closed mutations",
            proof,
        )
    )

    # (b) a tampered bundle in transit
    t = Scenario("P9-C-tampered-bundle", "C", "a bundle altered in transit to grant delete_resource")
    t.cp.bootstrap(0)
    t.run("incident-agent", {**INC, "environment": "staging"}, "run-001", 10)
    v2 = t.publish("restart-requires-approval", 20)
    evil = t.cp.state(v2)
    evil["agents"]["incident-agent"]["tools"]["delete_resource"] = "allow"
    evil["agents"]["incident-agent"]["tools"]["restart_service"] = "allow"
    t.net("rt-a", tamper_in_transit={"version": v2, "overlay": {"agents": evil["agents"]}})
    r = t.run("incident-agent", INC, "run-002", 30)
    t.step(30, "incident-agent", f"run while {v2} arrives altered", ", ".join(last_run_calls(r)))
    rejected = [e for e in t.audit() if e["event"] == "config.rejected"]
    t.check("the altered bundle failed signature verification and was not applied", len(rejected) > 0 and all(c["config_version"] == "v1" for c in r["calls"]))
    t.check(
        "the mutation failed closed while no verified current bundle was available (BUNDLE_REJECTED)",
        decision_for(r, "restart_service")["reason"] == "BUNDLE_REJECTED",
    )
    t.check(
        "deploy system: no production restart, no deletion",
        not any(x["environment"] == "production" for x in t.effects()["restarts"]) and not t.effects()["deletions"],
    )
    for k, v in (("rejected_events", len(rejected)), ("applied_version", "v1"), ("restart_decision", decision_for(r, "restart_service")["reason"])):
        t.measure(k, v)
    proof_t = card(
        "P9b",
        "TAMPERED BUNDLE IN TRANSIT",
        [
            ("Attack", f"{v2} altered to allow delete_resource and production restarts"),
            ("Runtime", f"signature check FAILED → {len(rejected)} config.rejected events"),
            ("Applied", "v1 (last-known-good); the altered bundle never applied"),
            ("Mutation", "restart_service → DENY · BUNDLE_REJECTED (fail closed)"),
        ],
        t.checks,
    )
    out.append(
        t.close(
            run_dir,
            EXPERIMENTS["P9"][1],
            {"agent": "incident-agent", "attack": "bundle altered in transit"},
            "rejected; last-known-good kept; mutation fails closed",
            f"{len(rejected)} rejections; applied v1",
            outcome_of(t),
            None,
            proof_t,
        )
    )

    # (c) the credential broker is down: policy says allow, but no credential can be minted
    b = Scenario("P9-C-broker-down", "C", "the control plane is reachable but the credential broker is not")
    b.cp.bootstrap(0)
    b.broker(False)
    r = b.run("incident-agent", INC, "run-001", 10)
    b.step(10, "incident-agent", "run with the broker down", ", ".join(last_run_calls(r)))
    b.check(
        "every tool call denied CREDENTIAL_UNAVAILABLE (policy allowed them)",
        all(c["reason"] == "CREDENTIAL_UNAVAILABLE" for c in r["calls"] if c["kind"] == "tool"),
    )
    b.check("no system received a call without a credential", len(b.syslog()) == 0)
    b.check("deploy system: 0 restarts", len(b.effects()["restarts"]) == 0)
    b.measure("tool_calls_denied", sum(1 for c in r["calls"] if c.get("reason") == "CREDENTIAL_UNAVAILABLE"))
    proof_b = card(
        "P9c",
        "CREDENTIAL BROKER DOWN",
        [
            ("Policy", "v1 · query_logs, query_metrics ALLOW"),
            ("Broker", "unavailable"),
            ("Result", "every tool call → DENY · CREDENTIAL_UNAVAILABLE"),
            ("Systems", "0 calls received · 0 restarts"),
        ],
        b.checks,
    )
    out.append(
        b.close(
            run_dir,
            EXPERIMENTS["P9"][1],
            {"agent": "incident-agent", "failure": "credential broker unavailable"},
            "no credential, no call",
            "all tool calls denied CREDENTIAL_UNAVAILABLE",
            outcome_of(b),
            None,
            proof_b,
        )
    )
    return out


# ---- P10 --------------------------------------------------------------------------------------------------------------
def p10(run_dir: Path) -> list[dict]:
    s = Scenario("P10-C-drift", "C", "two runtime instances; one sits behind a lagging replica that still serves v1")
    s.cp.bootstrap(0)
    for inst, t in (("rt-a", 10), ("rt-b", 12)):
        s.run("incident-agent", {**INC, "environment": "staging"}, f"warm-{inst}", t, instance=inst)
    v2 = s.publish("restart-requires-approval", 20)
    s.net("rt-b", serve_pointer={"stable": "v1", "canary": None})
    s.step(20, "network", "rt-b's replica lags: still serves pointer v1, without error", "silent staleness")
    ra = s.run("incident-agent", INC, "run-a", 30, instance="rt-a")
    rb = s.run("incident-agent", INC, "run-b", 32, instance="rt-b")
    s.step(30, "incident-agent@rt-a", "restart production", f"{decision_for(ra, 'restart_service')['status']} under {ra['config_version']}")
    s.step(32, "incident-agent@rt-b", "restart production", f"{decision_for(rb, 'restart_service')['status']} under {rb['config_version']}")
    observed = [
        {"instance": i, "agent": "incident-agent", "config_version": s.ask({"op": "status", "tick": 40}, i)["config_version"]} for i in ("rt-a", "rt-b")
    ]
    audit = s.audit("rt-a") + s.audit("rt-b")
    drift = s.cp.drift(observed, audit)
    exec_drift = [d for d in drift if d["kind"] == "executed_under_superseded_config"]
    would = [
        pdp.decide_tool(s.cp.state(d["superseded_by"]), d["agent"], "spiffe://acp.example/ns/agents/sa/agent-runtime", d["action"], INC, 0).effect
        for d in exec_drift
    ]
    s.step(40, "control plane", "compare desired vs observed", f"{len(drift)} drift findings: " + ", ".join(sorted({d["kind"] for d in drift})))
    s.net("rt-b")
    s.run("incident-agent", {**INC, "environment": "staging"}, "reconcile-b", 50, instance="rt-b")
    observed2 = [
        {"instance": i, "agent": "incident-agent", "config_version": s.ask({"op": "status", "tick": 55}, i)["config_version"]} for i in ("rt-a", "rt-b")
    ]
    stale_after = [d for d in s.cp.drift(observed2, []) if d["kind"] == "stale_config"]
    s.step(55, "control plane", "reconcile: replica fixed, rt-b re-syncs", f"stale instances: {len(stale_after)}")
    write_json(
        s.dir / "drift.json", {"desired": s.cp.pointer(), "observed": observed, "findings": drift, "would_have_decided": would, "after_reconcile": observed2}
    )
    s.check("rt-a applied v2 and held the restart for approval", decision_for(ra, "restart_service")["status"] == "pending_approval")
    s.check(
        "rt-b, behind the lagging replica, executed the restart under v1",
        decision_for(rb, "restart_service")["status"] == "executed" and rb["config_version"] == "v1",
    )
    s.check("drift detected: rt-b observed v1 while desired is v2", any(d["kind"] == "stale_config" and d["instance"] == "rt-b" for d in drift))
    s.check("drift detected: a mutation executed under a superseded version", len(exec_drift) == 1)
    s.check("re-evaluated under the desired version, that action required approval", would == ["approval_required"])
    s.check("after reconcile: no instance on a stale version", len(stale_after) == 0)
    s.check("agent code unchanged; both runtime processes never restarted", s.code_unchanged() and s.same_process)
    for k, v in (
        ("desired", v2),
        ("observed_rt_a", observed[0]["config_version"]),
        ("observed_rt_b", observed[1]["config_version"]),
        ("drift_findings", len(drift)),
        ("executed_under_superseded", len(exec_drift)),
        ("stale_after_reconcile", len(stale_after)),
    ):
        s.measure(k, v)
    proof = card(
        "P10",
        "DESIRED VS OBSERVED STATE",
        [
            ("Desired", f"{v2} (restart requires approval)"),
            ("rt-a observed", f"{observed[0]['config_version']} → restart held for approval"),
            ("rt-b observed", f"{observed[1]['config_version']} → restart EXECUTED (lagging replica, no error)"),
            ("Drift", f"{len(drift)} findings · stale_config rt-b · executed_under_superseded_config"),
            ("Under desired", f"that restart → {would[0].upper() if would else '-'}"),
            ("Reconcile", f"replica fixed · stale instances {len(stale_after)}"),
        ],
        s.checks,
        verdict="QUALIFIED · drift detected, not prevented",
    )
    return [
        s.close(
            run_dir,
            EXPERIMENTS["P10"][1],
            {"instances": ["rt-a", "rt-b"], "change": "restart-requires-approval", "fault": "lagging replica serves v1"},
            "the control plane detects rt-b's stale version and the action it executed under it",
            f"{len(drift)} drift findings; {len(exec_drift)} mutation under a superseded version",
            "qualified",
            "distribution: a lagging replica served v1 without error; policy did not prevent the restart, observation caught it",
            proof,
        )
    ]


# ---- P11 --------------------------------------------------------------------------------------------------------------
def apply_edits(d: Path, edits: list[dict]) -> tuple[list[str], int]:
    files, lines = set(), 0
    for e in edits:
        p = d / e["file"]
        old = p.read_text()
        assert e["old"] in old, f"{e['file']}: edit anchor not found"
        new = old.replace(e["old"], e["new"], 1)
        p.write_text(new)
        files.add(e["file"])
        lines += sum(
            1 for x in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0) if x[:1] in "+-" and not x.startswith(("+++", "---"))
        )
    return sorted(files), lines


def p11(run_dir: Path) -> list[dict]:
    edits = yaml.safe_load((CONFIG / "embedded-changes.yaml").read_text())
    order = ["restart-requires-approval", "revoke-observability-mcp", "suspend-incident-agent", "migrate-default-model"]
    # (E) governance embedded in every agent
    e = Scenario("P11-E-embedded", "E", "the same four governance changes, when governance lives inside each agent")
    src = POC / "acp" / "embedded"
    work = e.dir / "deploy"
    work.mkdir()
    for f in ("incident_agent.py", "support_agent.py", "finance_agent.py"):
        shutil.copy(src / f, work / f)
    old = Worker(e.dir, "embedded-old", module="acp.embedded.worker", extra=[str(work)])
    e.workers["embedded-old"] = old
    ask = lambda w, name, req: (e.record(name, w, req, resp := w.request(req)), resp)[1]
    r0 = ask(old, "embedded-old", {"op": "run", "agent": "incident-agent", "task": INC, "tick": 10})
    e.step(10, "incident-agent (embedded)", "restart production", decision_for(r0, "restart_service")["status"])
    footprint, hashes = {}, {}
    for ch in order:
        h0 = {f: sha256((work / f).read_bytes()) for f in ("incident_agent.py", "support_agent.py", "finance_agent.py")}
        files, lines = apply_edits(work, edits[ch])
        h1 = {f: sha256((work / f).read_bytes()) for f in h0}
        footprint[ch] = {"files": files, "lines": lines, "agents_to_redeploy": sum(h0[f] != h1[f] for f in h0)}
        e.step(20, "platform team", f"edit agents for {ch}", f"{len(files)} files · {lines} lines · {footprint[ch]['agents_to_redeploy']} redeploys")
        if ch == "restart-requires-approval":
            r1 = ask(old, "embedded-old", {"op": "run", "agent": "incident-agent", "task": INC, "tick": 30})
            e.step(30, "incident-agent (old process)", "restart production after the edit, before redeploy", decision_for(r1, "restart_service")["status"])
            new = Worker(e.dir, "embedded-new", module="acp.embedded.worker", extra=[str(work)])
            e.workers["embedded-new"] = new
            r2 = ask(new, "embedded-new", {"op": "run", "agent": "incident-agent", "task": INC, "tick": 40})
            e.step(40, "incident-agent (redeployed)", "restart production", decision_for(r2, "restart_service")["status"])
            hashes = {"before": h0["incident_agent.py"], "after": h1["incident_agent.py"]}
    creds = sum((src / f).read_text().count("static-") for f in ("incident_agent.py", "support_agent.py", "finance_agent.py"))
    tot_files = sum(len(v["files"]) for v in footprint.values())
    tot_lines = sum(v["lines"] for v in footprint.values())
    tot_redeploy = sum(v["agents_to_redeploy"] for v in footprint.values())
    e.check("before the edit the embedded agent restarts production", decision_for(r0, "restart_service")["status"] == "executed")
    e.check(
        "BROKEN: after the edit, the running process still restarts production (no central change is possible)",
        decision_for(r1, "restart_service")["status"] == "executed",
    )
    e.check(
        "only a redeployed process (new code hash) holds the restart",
        decision_for(r2, "restart_service")["status"] == "pending_approval" and hashes["before"] != hashes["after"],
    )
    e.check("the embedded agents hold long-lived static credentials in code", creds > 0)
    for k, v in (
        ("files_edited", tot_files),
        ("lines_changed", tot_lines),
        ("redeploys", tot_redeploy),
        ("static_credential_literals", creds),
        ("restart_before_redeploy", decision_for(r1, "restart_service")["status"]),
        ("restart_after_redeploy", decision_for(r2, "restart_service")["status"]),
    ):
        e.measure(k, v)
    for ch in order:
        e.measure(f"{ch}.files", len(footprint[ch]["files"]))
    write_json(e.dir / "footprint.json", footprint)
    e.code_before = e.code_before  # the control-plane agents are not what changed here
    proof_e = card(
        "P11a",
        "NEGATIVE CONTROL: GOVERNANCE INSIDE EVERY AGENT",
        [
            ("Change", "production restarts need approval"),
            ("Edit", f"incident_agent.py · sha256 {hashes['before'][:12]}… → {hashes['after'][:12]}…"),
            ("Running process", f"after the edit → restart {decision_for(r1, 'restart_service')['status'].upper()}  ← policy not in effect"),
            ("Redeployed process", f"restart → {decision_for(r2, 'restart_service')['status'].upper()}"),
            ("All four changes", f"{tot_files} file edits · {tot_lines} lines · {tot_redeploy} agent redeploys"),
            ("Credentials", f"{creds} static credential literals in agent code"),
        ],
        e.checks,
        verdict="NEGATIVE CONTROL · property broken by design",
    )
    rec_e = e.close(
        run_dir,
        EXPERIMENTS["P11"][1],
        {"agents": "acp/embedded/*.py", "changes": order},
        "a governance change is a code edit that takes effect only after a redeploy",
        f"{tot_files} edits, {tot_redeploy} redeploys; old process still restarted",
        "broken",
        "agent code: the running process kept its embedded rule until redeployed",
        proof_e,
    )

    # (C) the same four changes through the control plane
    c = Scenario("P11-C-control-plane", "C", "the same four governance changes, through the control plane")
    c.cp.bootstrap(0)
    agents_tree = tree(AGENTS_DIR)
    effects = {}
    v = c.publish("migrate-default-model", 10)
    r = c.run("finance-agent", FIN, "run-001", 12)
    effects["migrate-default-model"] = next(x["name"] for x in r["calls"] if x["kind"] == "model")
    v = c.publish("restart-requires-approval", 20)
    effects["restart-requires-approval"] = decision_for(c.run("incident-agent", INC, "run-002", 22), "restart_service")["status"]
    v = c.publish("revoke-observability-mcp", 30)
    effects["revoke-observability-mcp"] = decision_for(c.run("support-agent", {"case_id": "CASE-2231"}, "run-003", 32), "query_logs")["reason"]
    v = c.publish("suspend-incident-agent", 40)
    effects["suspend-incident-agent"] = c.run("incident-agent", INC, "run-004", 42)["reason"]
    for ch in order:
        c.step(0, "runtime", f"effect of {ch}", str(effects[ch]))
    c.check("default model moved at the next run (large-model)", effects["migrate-default-model"] == "large-model")
    c.check("restart held for approval at the next run", effects["restart-requires-approval"] == "pending_approval")
    c.check("observability tools denied at the next run", effects["revoke-observability-mcp"] == "MCP_SERVER_DISABLED")
    c.check("incident-agent denied at the next run", effects["suspend-incident-agent"] == "AGENT_SUSPENDED")
    c.check("0 agent files edited, 0 processes restarted, 4 bundle versions", changed(agents_tree, tree(AGENTS_DIR)) == [] and c.same_process and v == "v5")
    for k, val in (("files_edited", 0), ("lines_changed", 0), ("redeploys", 0), ("bundle_versions", 4), ("static_credential_literals", 0)):
        c.measure(k, val)
    proof_c = card(
        "P11b",
        "THE SAME FOUR CHANGES THROUGH THE CONTROL PLANE",
        [
            ("Changes", "model default · restart approval · revoke MCP · suspend"),
            ("Published", "v2 … v5 · 4 signed bundle versions"),
            ("Agent code", "0 files edited · 0 redeploys · one runtime process throughout"),
            ("Effect", "each change applied at the next enforcement point"),
        ],
        c.checks,
    )
    rec_c = c.close(
        run_dir,
        EXPERIMENTS["P11"][1],
        {"agents": "acp/agents/*.py", "changes": order},
        "each change takes effect at the next run with no code change",
        "4 versions; 0 edits; 0 redeploys",
        outcome_of(c),
        None,
        proof_c,
    )
    return [rec_e, rec_c]


# ---- P12 --------------------------------------------------------------------------------------------------------------
def p12(run_dir: Path) -> list[dict]:
    s = Scenario("P12-C-governing-the-control-plane", "C", "attempts to change the control plane, legitimate and not")
    s.cp.bootstrap(0)
    attempts = []

    def attempt(label, tick, **kw):
        try:
            v = s.cp.publish(**kw, tick=tick)
            attempts.append((label, "accepted", v, kw["author"]))
        except ChangeRejected as ex:
            attempts.append((label, "rejected", str(ex), kw["author"]))
        s.step(tick, kw["author"], label, f"{attempts[-1][1]}: {attempts[-1][2]}")

    grant_self = {"agents.incident-agent.tools.delete_resource": "allow"}
    attempt("grant itself delete_resource", 10, change_id="self-grant", sets=grant_self, author="incident-agent", reason="I need it")
    attempt(
        "raise incident-agent's tool quota",
        11,
        change_id="cross-team",
        sets={"agents.incident-agent.limits.max_tool_calls": 50},
        author="support.lead",
        reason="help",
    )
    attempt(
        "lower support-agent's tool quota (own scope)",
        12,
        change_id="own-scope",
        sets={"agents.support-agent.limits.max_tool_calls": 8},
        author="support.lead",
        reason="tighten",
    )
    attempt("widen incident-agent's tools alone", 13, change_id="widen-alone", sets=grant_self, author="platform.admin", reason="unblock")
    attempt(
        "platform.admin as its own second approver",
        14,
        change_id="widen-self-approved",
        sets=grant_self,
        author="platform.admin",
        reason="unblock",
        second_approver="platform.admin",
    )
    attempt(
        "raise a quota via break-glass",
        15,
        change_id="glass-widen",
        sets={"agents.incident-agent.limits.max_tool_calls": 50},
        author="oncall.ic",
        reason="faster",
        emergency=True,
    )
    attempt(
        "a plaintext credential in the registry (with sre.lead)",
        16,
        change_id="plaintext-cred",
        sets={"tools.restart_service.credential": "dpl-live-7c1e"},
        author="platform.admin",
        reason="rotate",
        second_approver="sre.lead",
    )
    c = s.cp.changes["suspend-incident-agent"]
    attempt(
        "suspend incident-agent (break-glass)", 17, change_id="suspend-incident-agent", sets=c["set"], author="oncall.ic", reason=c["reason"], emergency=True
    )
    c = s.cp.changes["restore-incident-agent"]
    attempt("restore incident-agent alone", 18, change_id="restore-incident-agent", sets=c["set"], author="oncall.ic", reason=c["reason"])
    attempt(
        "restore incident-agent with sre.lead",
        19,
        change_id="restore-incident-agent",
        sets=c["set"],
        author="oncall.ic",
        reason=c["reason"],
        second_approver="sre.lead",
    )
    log = s.dir / "controlplane" / "changelog.jsonl"
    rows = read_jsonl(log)
    tampered = s.dir / "changelog-tampered.jsonl"
    lines = log.read_text().splitlines()
    lines[2] = lines[2].replace('"rejected"', '"published"')
    tampered.write_text("\n".join(lines) + "\n")
    accepted = [a for a in attempts if a[1] == "accepted"]
    rejected = [a for a in attempts if a[1] == "rejected"]
    a = {label: (result, detail) for label, result, detail, _ in attempts}
    s.check("an agent cannot change the control plane (not an administrator)", a["grant itself delete_resource"][0] == "rejected")
    s.check("scope: a team lead cannot change another team's agent", a["raise incident-agent's tool quota"][0] == "rejected")
    s.check("scope: a team lead may restrict its own agent alone", a["lower support-agent's tool quota (own scope)"][0] == "accepted")
    s.check("two-person rule: a widening change needs a second approver", a["widen incident-agent's tools alone"][0] == "rejected")
    s.check("two-person rule: the second approver must be a different person", a["platform.admin as its own second approver"][0] == "rejected")
    s.check("break-glass may only restrict", a["raise a quota via break-glass"][0] == "rejected")
    plain = a["a plaintext credential in the registry (with sre.lead)"]
    s.check("validation: a plaintext credential never becomes a version", plain[0] == "rejected" and "secret://" in plain[1])
    s.check("break-glass suspension accepted from one on-call person", a["suspend incident-agent (break-glass)"][0] == "accepted")
    s.check(
        "restoring (widening) needs a second person",
        a["restore incident-agent alone"][0] == "rejected" and a["restore incident-agent with sre.lead"][0] == "accepted",
    )
    s.check("every attempt is on the change log, accepted or rejected", len(rows) == 1 + len(attempts))
    s.check("the change log is hash-chained and verifies", verify_chain(log))
    s.check("editing one change-log row breaks the chain", not verify_chain(tampered))
    s.check(
        "every version is signed; no bundle contains a plaintext credential",
        all((s.dir / "controlplane" / "bundles" / f"{v}.sig").exists() for v in s.cp.versions())
        and all(t["credential"].startswith("secret://") for v in s.cp.versions() for t in s.cp.state(v)["tools"].values()),
    )
    for k, v in (
        ("attempts", len(attempts)),
        ("accepted", len(accepted)),
        ("rejected", len(rejected)),
        ("changelog_rows", len(rows)),
        ("versions", len(s.cp.versions())),
        ("agent_self_grant", a["grant itself delete_resource"][0]),
        ("cross_team_change", a["raise incident-agent's tool quota"][0]),
        ("own_scope_restriction", a["lower support-agent's tool quota (own scope)"][0]),
        ("widening_alone", a["widen incident-agent's tools alone"][0]),
        ("self_approval", a["platform.admin as its own second approver"][0]),
        ("break_glass_widening", a["raise a quota via break-glass"][0]),
        ("plaintext_credential", a["a plaintext credential in the registry (with sre.lead)"][0]),
        ("break_glass_suspension", a["suspend incident-agent (break-glass)"][0]),
        ("restore_with_second_person", a["restore incident-agent with sre.lead"][0]),
        ("changelog_verifies", "yes" if verify_chain(log) else "no"),
        ("tampered_changelog_verifies", "yes" if verify_chain(tampered) else "no"),
    ):
        s.measure(k, v)
    proof = card(
        "P12",
        "GOVERNING THE CONTROL PLANE ITSELF",
        [(a[3], f"{a[0]} → {a[1].upper()} · {a[2]}") for a in attempts]
        + [("Change log", f"{len(rows)} rows, hash-chained · verifies; one edited row → chain broken · tamper-evident local log under POC assumptions")],
        s.checks,
    )
    return [
        s.close(
            run_dir,
            EXPERIMENTS["P12"][1],
            {"attempts": [a[0] for a in attempts]},
            "illegitimate changes rejected and logged; legitimate ones versioned and signed",
            f"{len(accepted)} accepted, {len(rejected)} rejected, all {len(rows)} on a verifying chain",
            outcome_of(s),
            None,
            proof,
        )
    ]


ALL = {"P1": p1, "P2": p2, "P3": p3, "P4": p4, "P5": p5, "P6": p6, "P7": p7, "P8": p8, "P9": p9, "P10": p10, "P11": p11, "P12": p12}


# ---- the run ----------------------------------------------------------------------------------------------------------
def config_hashes() -> dict:
    return {p.name: sha256(p.read_bytes()) for p in sorted(CONFIG.glob("*")) if p.is_file()}


def source_hashes() -> dict:
    return {str(p.relative_to(POC)): sha256(p.read_bytes()) for p in sorted((POC / "acp").rglob("*.py"))}


def run(run_id: str, only: list[str] | None = None) -> Path:
    from acp.facts import build_facts, summary_md

    run_dir = RUNS / run_id
    if run_dir.exists() and not only:
        shutil.rmtree(run_dir)
    (run_dir / "scenarios").mkdir(parents=True, exist_ok=True)
    scenarios, proofs = [], []
    for exp, fn in ALL.items():
        if only and exp not in only:
            continue
        recs = fn(run_dir)
        scenarios += recs
        checks = [c for r in recs for c in r["checks"]]
        agg = {
            "experiment": exp,
            "title": EXPERIMENTS[exp][0],
            "question": EXPERIMENTS[exp][1],
            "scenarios": [r["id"] for r in recs],
            "outcomes": {r["id"]: r["outcome"] for r in recs},
            "measures": {r["id"]: dict(r["measures"]) for r in recs},
            "checks_passed": sum(c["passed"] for c in checks),
            "checks_total": len(checks),
            "expected_failures": [c["check"] for c in checks if not c["passed"] and c["scenario"].split("-")[1] == "E"],
        }
        write_json(run_dir / f"{exp}.json", agg)
        proofs += [r["proof"] for r in recs]
    checks = [c for r in scenarios for c in r["checks"]]
    write_json(run_dir / "checks.json", checks)
    (run_dir / "proof.txt").write_text("\n\n".join(proofs) + "\n")
    manifest = {
        "run_id": run_id,
        "python": platform.python_version(),
        "agents_code_sha256": code_sha256(),
        "config_sha256": config_hashes(),
        "source_sha256": source_hashes(),
        "experiments": list(ALL if not only else only),
        "scenarios": [r["id"] for r in scenarios],
        "real": [
            "separate long-lived runtime processes (subprocess, JSON lines)",
            "control-plane versioning, signing (HMAC-SHA256), pointer, rollout",
            "change authorization, validation, hash-chained change log",
            "decision function and enforcement points",
            "hash-chained runtime audit",
            "code hashing of agent sources",
            "file-based state shared between processes",
        ],
        "simulated": [
            "enterprise systems (deploy, billing, support, observability) and their MCP servers",
            "model endpoints (deterministic text, token counts)",
            "network partition, lagging replica and in-transit tampering (flags in state/network/)",
            "credential broker (in-process minting)",
            "logical clock (ticks)",
        ],
        "agents": "fixed deterministic plans; no LLM",
    }
    write_json(run_dir / "manifest.json", manifest)
    write_json(
        run_dir / "scenarios.json",
        [
            {
                "experiment": exp,
                "role": ROLE[exp][0],
                "property": ROLE[exp][1],
                "title": EXPERIMENTS[exp][0],
                "scenarios": [
                    {"id": r["id"], "outcome": r["outcome"], "checks": f"{sum(c['passed'] for c in r['checks'])}/{len(r['checks'])}"}
                    for r in scenarios
                    if r["experiment"] == exp
                ],
            }
            for exp in (ALL if not only else only)
        ],
    )
    facts = build_facts(run_dir, scenarios)
    write_json(run_dir / "facts.json", facts)
    (run_dir / "summary.md").write_text(summary_md(run_dir, scenarios, checks))
    return run_dir
