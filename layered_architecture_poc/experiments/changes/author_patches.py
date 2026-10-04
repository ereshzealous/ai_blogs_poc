"""Author the six change patches (E2, E3, E9 × monolith, layered) from the current source, as a real engineer would
make each change: the smallest edit that makes the change work and keeps that architecture's tests passing.

    uv run python experiments/changes/author_patches.py        -> experiments/changes/<change>/<arch>.patch

Each edit is a literal find/replace on the baseline file, so the patch is exactly what is written below.  The patches
are frozen (hashed) before the recorded run; the harness applies them in isolated git worktrees and measures the diff.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

POC = Path(__file__).resolve().parents[2]
OUT = POC / "experiments" / "changes"
Edit = tuple[str, str, str]  # (file, old, new)

CHANGES: dict[str, dict[str, list[Edit]]] = {
    "E2_model_swap": {
        "monolith": [
            ("monolith/incident_agent.py", 'MODEL = "gpt-oss:20b"\nTHINK: Any = "low"                  # gpt-oss takes low/medium/high',
             'MODEL = "qwen3:8b"\nTHINK: Any = False                  # qwen3 takes true/false'),
        ],
        "layered": [
            ("config/models.yaml", "  reasoning: {profile: gpt-oss-20b}\n  structured: {profile: gpt-oss-20b}",
             "  reasoning: {profile: qwen3-8b}\n  structured: {profile: qwen3-8b}"),
            ("config/models.yaml", "budget:",
             "  qwen3-8b:\n    model: qwen3:8b\n    think: false\n    options: {temperature: 0, seed: ${F2_SEED:-7}, num_ctx: 16384}\nbudget:"),
        ],
    },
    "E3_tool_v2": {
        "monolith": [
            ("monolith/incident_agent.py", 'SERVERS = ["itsm", "observability", "deploy"]', 'SERVERS = ["itsm", "observability", "deploy_v2"]'),
            ("monolith/incident_agent.py", 'NEEDS_APPROVAL = {"rollback_release", "restart_service", "scale_service"}   # production changes',
             'NEEDS_APPROVAL = {"rollback", "rollback_release", "restart_service", "scale_service"}   # production changes'),
            ("monolith/incident_agent.py", '        if name in NEEDS_APPROVAL and args.get("environment") == "production":',
             '        environment = args.get("environment") or str(args.get("service_ref", "")).rpartition("/")[2]\n'
             '        if name in NEEDS_APPROVAL and environment == "production":'),
            ("tests/integration/test_monolith_choke_point.py",
             'out = await agent._execute_tool("rollback_release", {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"})\n            read',
             'out = await agent._execute_tool("rollback", {"service_ref": "checkout-api/production", "target_revision": "rel-2030"})\n            read'),
            ("tests/integration/test_monolith_choke_point.py", 'assert asked == ["rollback_release"]', 'assert asked == ["rollback"]'),
            ("tests/integration/test_monolith_choke_point.py",
             'out = await agent._execute_tool("rollback_release", {"service": "checkout-api", "environment": "production", "to_release": "rel-2030"})\n        await agent.aclose()\n        m.TOOL_TIMEOUT_S = 5.0',
             'out = await agent._execute_tool("rollback", {"service_ref": "checkout-api/production", "target_revision": "rel-2030"})\n        await agent.aclose()\n        m.TOOL_TIMEOUT_S = 5.0'),
        ],
        "layered": [
            ("config/capabilities.yaml", "servers: [itsm, observability, deploy]", "servers: [itsm, observability, deploy_v2]"),
            ("config/capabilities.yaml",
             "  deploy.history:    {server: deploy,        tool: list_deployments, kind: read,  adapter: passthrough, contract: history}",
             "  deploy.history:    {server: deploy_v2,     tool: get_release_history, kind: read, adapter: deploy_v2_history, contract: history}"),
            ("config/capabilities.yaml",
             "  deploy.rollback:   {server: deploy,        tool: rollback_release, kind: write, risk: high, adapter: passthrough, key_param: idempotency_key}",
             "  deploy.rollback:   {server: deploy_v2,     tool: rollback,         kind: write, risk: high, adapter: deploy_v2_rollback, key_param: request_id}"),
            ("config/capabilities.yaml",
             "  deploy.restart:    {server: deploy,        tool: restart_service,  kind: write, risk: high, adapter: passthrough, key_param: idempotency_key}\n", ""),
            ("layered_platform/tools/adapters.py", 'ADAPTERS: dict[str, Adapter] = {\n    "passthrough": (_same, _same),\n}',
             'def _ref(a: dict[str, Any]) -> str:\n    return f"{a.pop(\'service\')}/{a.pop(\'environment\')}"\n\n\n'
             'def _v2_history_args(a: dict[str, Any]) -> dict[str, Any]:\n    return {"service_ref": _ref(a), **a}\n\n\n'
             'def _v2_rollback_args(a: dict[str, Any]) -> dict[str, Any]:\n    return {"service_ref": _ref(a), "target_revision": a.pop("to_release"), **a}\n\n\n'
             'def _v2_rollback_result(r: Any) -> Any:\n    return r["operation"]["detail"] if isinstance(r, dict) and "operation" in r else r\n\n\n'
             'ADAPTERS: dict[str, Adapter] = {\n    "passthrough": (_same, _same),\n    "deploy_v2_history": (_v2_history_args, _same),\n'
             '    "deploy_v2_rollback": (_v2_rollback_args, _v2_rollback_result),\n}'),
            ("tests/unit/test_policy.py",
             '    ("deploy.restart", {"service": "checkout-api", "environment": "production"}, "REQUIRE_APPROVAL", "P3-high-risk-production-write"),',
             '    ("deploy.restart", {"service": "checkout-api", "environment": "production"}, "DENY", "P0-unregistered"),   # v2 has no restart'),
        ],
    },
    "E9_dry_run": {
        "monolith": [
            ("monolith/incident_agent.py", '        self.usage = {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0}\n',
             '        self.usage = {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0}\n        self.dry_run = False\n'),
            ("monolith/incident_agent.py", '    async def run(self, user_message: str) -> str:\n        self._log("run_start", message=user_message)',
             '    async def run(self, user_message: str, dry_run: bool = False) -> str:\n        self.dry_run = dry_run\n'
             '        self._log("run_start", message=user_message, dry_run=dry_run)'),
            ("monolith/incident_agent.py",
             '            system = SYSTEM_PROMPT.format(runbook=_load_runbook(self.service), memory=_load_memory(self.service))\n',
             '            system = SYSTEM_PROMPT.format(runbook=_load_runbook(self.service), memory=_load_memory(self.service))\n'
             '            if dry_run:\n                system += DRY_RUN_NOTE\n'),
            ("monolith/incident_agent.py", "def _load_runbook(service: str) -> str:",
             'DRY_RUN_NOTE = """\nDRY RUN: production changes are simulated, not executed.  Do not verify recovery.  Set the incident to "investigating"\n'
             'with a note that starts with "DRY RUN plan:" and gives the action you would take.  Report the plan.\n"""\n\n\n'
             "def _load_runbook(service: str) -> str:"),
            ("monolith/incident_agent.py",
             '                return f"Error: {name} was not approved by the incident commander. Do not retry; report instead."\n',
             '                return f"Error: {name} was not approved by the incident commander. Do not retry; report instead."\n'
             '        if self.dry_run and name in NEEDS_APPROVAL:\n            self._log("dry_run_skip", tool=name, args=args)\n'
             '            return json.dumps({"dry_run": True, "would_call": name, "arguments": args, "executed": False})\n'),
        ],
        "layered": [
            ("layered_platform/contracts.py", '    instructions: str = "Investigate the incident and remediate it safely."\n',
             '    instructions: str = "Investigate the incident and remediate it safely."\n    dry_run: bool = False\n'),
            ("layered_platform/service.py", '"request_id": req.request_id}, trace_id, span_id)', '"request_id": req.request_id, "dry_run": req.dry_run}, trace_id, span_id)'),
            ("layered_platform/orchestration/incident_workflow.py", '        policy = decision.model_dump()\n        if decision.effect == "DENY":',
             '        policy = decision.model_dump()\n        if s.get("dry_run"):  # evaluate policy, then stop short of approval and execution\n'
             '            return StepResult("record", updates={"policy": policy, "outcome": "dry_run", "planned_action": {"capability": cap, "args": args}})\n'
             '        if decision.effect == "DENY":'),
            ("layered_platform/orchestration/incident_workflow.py", '        status = "mitigated" if s.get("outcome") == "mitigated" else "investigating"\n        note = (',
             '        status = "mitigated" if s.get("outcome") == "mitigated" else "investigating"\n'
             '        if s.get("outcome") == "dry_run":\n            plan = s["planned_action"]\n'
             '            note = (f"[{wf}] DRY RUN plan: {plan[\'capability\']} {plan[\'args\']} (policy {s[\'policy\'][\'effect\']} by {s[\'policy\'][\'rule\']}). "\n'
             '                    f"Root cause: {dx.get(\'root_cause\', \'unknown\')} (suspect release {dx.get(\'suspect_release\')}).")\n'
             '            await self.gateway.execute("incident.update", {"incident_id": inc["id"], "status": status, "note": note}, self._ctx(wf, "record", s))\n'
             '            return StepResult("complete", updates={"recorded_status": status})\n        note = ('),
            ("layered_platform/orchestration/incident_workflow.py",
             '        dx, act, ver = s.get("diagnosis") or {}, s.get("action") or {}, s.get("verification") or {}\n        report = "\\n".join([',
             '        dx, act, ver = s.get("diagnosis") or {}, s.get("action") or {}, s.get("verification") or {}\n'
             '        if s.get("outcome") == "dry_run":\n            plan = s["planned_action"]\n'
             '            report = (f"Root cause: {dx.get(\'root_cause\', \'unknown\')} (release {dx.get(\'suspect_release\')})\\n"\n'
             '                      f"DRY RUN plan: {plan[\'capability\']} {plan[\'args\']} - policy {s[\'policy\'][\'effect\']} ({s[\'policy\'][\'rule\']}); nothing executed")\n'
             '            return StepResult("done", status="COMPLETED", updates={"report": report})\n        report = "\\n".join(['),
            ("layered_platform/experience/cli.py", "request_id=a.request_id or uuid.uuid4().hex, instructions=a.instructions))",
             "request_id=a.request_id or uuid.uuid4().hex, instructions=a.instructions, dry_run=a.dry_run))"),
            ("layered_platform/experience/cli.py", '    p.add_argument("--reject", action="store_true")',
             '    p.add_argument("--reject", action="store_true")\n    p.add_argument("--dry-run", action="store_true", help="plan and authorize the remediation, execute nothing")'),
        ],
    },
}


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        shutil.copytree(POC, src, ignore=shutil.ignore_patterns(".venv", "var", "runs", "__pycache__", "*.pyc", ".pytest_cache"))
        g = lambda *a: subprocess.run(["git", "-c", "user.email=poc@local", "-c", "user.name=author", *a], cwd=src, check=True, capture_output=True, text=True)  # noqa: E731
        g("init", "-q")
        g("add", "-A")
        g("commit", "-qm", "baseline")
        for change, per_arch in CHANGES.items():
            for arch, edits in per_arch.items():
                for f, old, new in edits:
                    p = src / f
                    text = p.read_text()
                    if text.count(old) != 1:
                        raise SystemExit(f"{change}/{arch}: expected exactly one match in {f} for {old[:60]!r}, found {text.count(old)}")
                    p.write_text(text.replace(old, new))
                (OUT / change).mkdir(parents=True, exist_ok=True)
                (OUT / change / f"{arch}.patch").write_text(g("diff").stdout)
                g("checkout", "-q", ".")
                print(f"{change}/{arch}: {len(edits)} edits")


if __name__ == "__main__":
    main()
