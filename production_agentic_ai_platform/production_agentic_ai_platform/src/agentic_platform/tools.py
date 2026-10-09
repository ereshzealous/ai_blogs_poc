"""Tool & action platform: capability registry, discovery, and the governed execution gateway in front of MCP.

Two different questions, two different mechanisms:

  DISCOVERY PLANE       "Which capabilities may this agent consider?"   registry filter + ranking.  Probabilistic is fine.
  EXECUTION GOVERNANCE  "May this exact invocation execute now?"       registry facts + identity + policy + risk + budget
                                                                        + approval digest + scoped capability.  Deterministic.

MCP is the transport and the capability boundary: it tells the platform what a server exposes and carries the call.  It
does not decide whether the platform trusts the server, whether this agent may use the tool, whether a human must
approve, or whether the call still matches what was approved.  Those decisions happen here, before the MCP call, and the
release server re-checks the capability on its side.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import mcp_types as types
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError

from agentic_platform import capability as capmod
from agentic_platform import policy as pol
from agentic_platform.approval import ApprovalError
from agentic_platform.budget import BudgetExceeded
from agentic_platform.canonical import invocation, invocation_digest, stable_id
from agentic_platform.identity import IdentityService
from agentic_platform.observability import span, traceparent

SERVERS = ("incident", "release", "toolbox")
META_CAP, META_IDEM = "io.agentic-platform/capability", "io.agentic-platform/idempotency-key"


class ActionDenied(Exception):
    def __init__(self, code: str, detail: str = "", decision: dict | None = None):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.decision = code, detail, decision


def crash_point(name: str) -> None:
    """Failure injection: at the named point, announce it and wait to be SIGKILLed by the parent process."""
    if os.environ.get("PAP_CRASH_AT") == name:
        print(f"CRASHPOINT {name} pid={os.getpid()}", flush=True)
        time.sleep(3600)


class McpPool:
    """The platform's only MCP client: one stdio session per server.  Agents never get one."""

    def __init__(self, root: Path, world_db: Path, cap_key: bytes, extra_env: dict[str, str] | None = None):
        self.root, self.world_db, self.key, self.extra = root, world_db, cap_key, extra_env or {}
        self.clients: dict[str, Client] = {}
        self.exposed: dict[str, list[dict[str, Any]]] = {}
        self._stack: AsyncExitStack | None = None

    async def start(self) -> None:
        env = dict(os.environ, PYTHONPATH=str(self.root / "src"), PAP_WORLD_DB=str(self.world_db), PAP_CAPABILITY_KEY=self.key.decode(), **self.extra)
        env.pop("PAP_CRASH_AT", None)
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for s in SERVERS:
            c = await self._stack.enter_async_context(Client(StdioServerParameters(command=sys.executable, args=["-m", "mcp_servers", s], env=env, cwd=str(self.root))))
            self.clients[s] = c
            self.exposed[s] = [{"name": t.name, "description": t.description, "destructive": bool(t.annotations and t.annotations.destructive_hint)}
                               for t in (await c.list_tools()).tools]

    async def close(self) -> None:
        if self._stack:
            await self._stack.__aexit__(None, None, None)
            self._stack = None

    async def call(self, server: str, tool: str, args: dict[str, Any], meta: dict[str, Any], timeout_s: float = 20) -> Any:
        try:
            r = await self.clients[server].call_tool(tool, args, read_timeout_seconds=timeout_s, meta=meta)
        except MCPError as exc:
            raise ActionDenied("TOOL_CALL_FAILED", str(exc)) from exc
        text = "".join(c.text for c in r.content if isinstance(c, types.TextContent))
        if r.is_error:
            m = re.search(r"([A-Z][A-Z_]{5,}):", text)
            raise ActionDenied(m.group(1) if m else "TOOL_ERROR", text)
        return json.loads(text)


class ToolPlatform:
    def __init__(self, rt):
        self.rt = rt

    # ---- discovery plane -------------------------------------------------------------------------------------------------
    def discover(self, query: str, k: int = 8) -> list[dict[str, Any]]:
        b = self.rt.bundle()
        agent = b.agent(self.rt.agent_id)
        terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        offered, withheld = [], []
        for name, c in b.tools.items():
            why = [w for w, bad in (("not in agent's capability list", name not in agent["capabilities"]), ("untrusted", c["trust"] != "trusted"),
                                    ("not active", c["lifecycle"] != "active"), ("disabled", not c["enabled"])) if bad]
            if why:
                withheld.append({"name": name, "why": why})
                continue
            score = len(terms & set(re.findall(r"[a-z0-9]+", (c["keywords"] + " " + c["tool"]).lower())))
            offered.append({"name": name, "description": c["keywords"], "side_effect": c["side_effect"], "score": score})
        offered.sort(key=lambda o: (-o["score"], o["name"]))
        exposed = [f"{s}.{t['name']}" for s, ts in self.rt.mcp.exposed.items() for t in ts]
        self.rt.ev.record("tools.discovered", {"query": query, "offered": [o["name"] for o in offered[:k]], "withheld": withheld,
                                               "mcp_exposed": exposed, "registered": sorted(b.tools)}, workflow_id=self.rt.wf_id)
        return offered[:k]

    # ---- execution governance ------------------------------------------------------------------------------------------
    def _invocation(self, cap_name: str, cap: dict | None, args: dict[str, Any]) -> dict[str, Any]:
        inc = self.rt.incident
        return invocation(tenant=self.rt.tenant, environment=args.get("environment", inc["environment"]), tool=cap_name,
                          tool_version=(cap or {}).get("version", "unregistered"), operation=(cap or {}).get("operation", (cap or {}).get("side_effect", "unknown")),
                          arguments=args, incident=inc["id"], workflow_id=self.rt.wf_id, agent=self.rt.agent_id, on_behalf_of=self.rt.user.id)

    async def authorize(self, cap_name: str, args: dict[str, Any], *, purpose: str = "execute") -> dict[str, Any]:
        """Build the policy input from authoritative sources and evaluate it.  Records the full input and decision."""
        b = self.rt.bundle()
        cap = b.tools.get(cap_name)
        inv = self._invocation(cap_name, cap, args)
        svc = args.get("service", self.rt.incident["service"])
        env = inv["environment"]
        perm = (cap or {}).get("permission", "unknown:{service}:{environment}").format(service=svc, environment=env)
        eff = self.rt.effective
        seed_svc = self.rt.world_seed["services"].get(svc, {})
        authoritative = {}
        if cap and cap.get("validate") == "previous_release":
            authoritative["deployment"] = await self.rt.mcp.call("release", "get_deployment", {"service": svc, "environment": env},
                                                                 {"traceparent": traceparent()})   # policy information point: the system of record
        inp = {
            "user": self.rt.user.id, "agent": {**{k: b.agent(self.rt.agent_id)[k] for k in ("id", "version", "lifecycle", "capabilities")}},
            "workload": self.rt.workload.id, "tenant": self.rt.tenant, "resource_tenant": seed_svc.get("tenant"), "environment": env,
            "incident": self.rt.incident["id"], "capability_name": cap_name, "capability": cap, "operation": inv["operation"], "arguments": args,
            "required_permission": perm, "effective_authority": eff["effective"], "removed_by": IdentityService.removed_by(eff["layers"], perm),
            "delegation": {"id": self.rt.delegation.id, "valid": self.rt.delegation.valid(), "incident": self.rt.delegation.incident,
                           "scope": sorted(self.rt.delegation.scope)},
            "risk": pol.classify_risk(b, cap, env, seed_svc.get("tier")), "budget": self.rt.budget.state(),
            "authoritative_context": authoritative, "bundle_version": b.version, "purpose": purpose,
        }
        with span(self.rt.t, f"policy.evaluate {cap_name}", **{"platform.policy.version": b.policy_version}) as s:
            d = pol.evaluate(b, inp)
            s.set_attribute("platform.policy.decision", d["decision"])
            s.set_attribute("platform.policy.code", d["code"])
        digest = invocation_digest(inv)
        self.rt.ev.record("policy.decided", {"capability": cap_name, "decision": d["decision"], "code": d["code"], "reasons": d["reasons"],
                                             "decision_id": d["decision_id"], "policy_version": d["policy_version"], "bundle_version": d["bundle_version"],
                                             "invocation_digest": digest, "risk": inp["risk"]["level"], "purpose": purpose},
                          workflow_id=self.rt.wf_id, category="policy", detail={"capability": cap_name, "purpose": purpose, "input": inp, "decision": d, "invocation": inv, "invocation_digest": digest})
        return {"decision": d, "invocation": inv, "digest": digest, "capability": cap, "input": inp}

    async def read(self, cap_name: str, args: dict[str, Any]) -> Any:
        """A read goes through the same policy; it needs no approval and no execution capability."""
        az = await self.authorize(cap_name, args, purpose="read")
        d = az["decision"]
        if d["decision"] != "ALLOW":
            raise ActionDenied(d["code"], "; ".join(d["reasons"]), d)
        cap = az["capability"]
        self.rt.budget.charge("tool_call", 1, cap_name, cost_units=1)
        with span(self.rt.t, f"mcp.call {cap['server']}.{cap['tool']}", **{"rpc.system": "mcp", "platform.capability": cap_name}):
            return await self.rt.mcp.call(cap["server"], cap["tool"], args, {"traceparent": traceparent()})

    async def execute(self, inv: dict[str, Any], approval: dict[str, Any] | None, *, recovery: str | None = None) -> dict[str, Any]:
        """Run one consequential invocation: re-authorize under the *current* bundle, validate the approval against this
        invocation's digest, issue a scoped capability, journal the attempt, call MCP with an idempotency key."""
        cap_name, args = inv["tool"], inv["arguments"]
        digest = invocation_digest(inv)
        idem = ("idem-" + digest[:32]) if not os.environ.get("PAP_NAIVE_IDEMPOTENCY") else "naive-" + uuid.uuid4().hex[:12]
        az = await self.authorize(cap_name, args, purpose="execute")
        if az["digest"] != digest:
            raise ActionDenied("INVOCATION_CHANGED", "the invocation rebuilt at execution time differs from the one presented")
        d = az["decision"]
        if d["decision"] == "DENY":
            raise ActionDenied(d["code"], "; ".join(d["reasons"]), d)
        approval_id = None
        if d["decision"] == "REQUIRE_APPROVAL":
            if not approval:
                raise ActionDenied("APPROVAL_REQUIRED", "no approval presented", d)
            try:
                checked = self.rt.approvals.validate(approval, inv, self.rt.agent_id)
            except ApprovalError as exc:
                self.rt.ev.record("approval.rejected_at_execution", {"code": exc.code, "detail": exc.detail, "approval_id": approval["id"],
                                                                     "approved_digest": approval["digest"], "presented_digest": digest},
                                  workflow_id=self.rt.wf_id, category="approvals")
                raise ActionDenied(exc.code, exc.detail, d) from None
            approval_id = approval["id"]
            self.rt.ev.record("approval.validated", {"approval_id": approval_id, "approver": approval["approver"], "approved_digest": approval["digest"],
                                                     "executing_digest": checked, "match": True}, workflow_id=self.rt.wf_id, category="approvals")
        # Recovery after an ambiguous failure: ask the system of record before sending anything again.
        if recovery == "lookup":
            with span(self.rt.t, "platform.reconcile get_operation", **{"platform.idempotency_key": idem}):
                op = await self.rt.mcp.call("release", "get_operation", {"idempotency_key": idem}, {"traceparent": traceparent()})
            self.rt.ev.record("action.reconciled", {"idempotency_key": idem, "found": op["found"], "result": op["result"]}, workflow_id=self.rt.wf_id)
            if op["found"]:
                self._journal(digest, idem, None, "SUCCEEDED", {**op["result"], "recovered_via": "idempotency_lookup"})
                return {**op["result"], "recovered_via": "idempotency_lookup", "idempotency_key": idem}
        self.rt.budget.charge("tool_call", 1, cap_name, cost_units=1)
        b = self.rt.bundle()
        cap = az["capability"]
        issued = self.rt.store.q("SELECT COUNT(*) FROM action_journal WHERE workflow_id=? AND digest=? AND status='STARTED'", self.rt.wf_id, digest)[0][0]
        token, claims = capmod.issue(self.rt.cap_key, inv, workload=self.rt.workload.id, audience=b.policy["capability"]["audience"][cap["server"]],
                                     decision_id=d["decision_id"], approval_id=approval_id, ttl_s=b.policy["capability"]["ttl_s"],
                                     jti=stable_id("cap", digest, issued, n=16))
        self.rt.ev.record("capability.issued", {"jti": claims["jti"], "digest": claims["digest"], "tool": claims["tool"], "args": claims["args"],
                                                "aud": claims["aud"], "exp_in_s": claims["exp"] - claims["iat"], "decision_id": d["decision_id"],
                                                "approval_id": approval_id, "sub": claims["sub"], "act": claims["act"], "wl": claims["wl"]},
                          workflow_id=self.rt.wf_id, category="capability", detail={"claims": claims})
        attempt = self._journal(digest, idem, claims["jti"], "STARTED", None)
        with span(self.rt.t, f"mcp.call {cap['server']}.{cap['tool']}", **{"rpc.system": "mcp", "platform.capability": cap_name,
                                                                          "platform.invocation_digest": digest, "platform.idempotency_key": idem,
                                                                          "platform.capability_jti": claims["jti"]}):
            try:
                result = await self.rt.mcp.call(cap["server"], cap["tool"], args, {"traceparent": traceparent(), META_CAP: token, META_IDEM: idem})
            except ActionDenied as exc:
                self._journal(digest, idem, claims["jti"], "FAILED", {"code": exc.code, "detail": exc.detail})
                self.rt.ev.record("action.failed", {"code": exc.code, "detail": exc.detail, "jti": claims["jti"]}, workflow_id=self.rt.wf_id)
                raise
            crash_point("after_mcp_return")
        self._journal(digest, idem, claims["jti"], "SUCCEEDED", result)
        self.rt.ev.record("action.executed", {"capability": cap_name, "digest": digest, "idempotency_key": idem, "jti": claims["jti"],
                                              "attempt": attempt, "result": result}, workflow_id=self.rt.wf_id)
        return {**result, "idempotency_key": idem, "jti": claims["jti"]}

    def _journal(self, digest: str, idem: str, jti: str | None, status: str, result: Any) -> int:
        s = self.rt.store
        n = s.q("SELECT COUNT(*) FROM action_journal WHERE workflow_id=? AND digest=? AND status='STARTED'", self.rt.wf_id, digest)[0][0]
        s.db.execute("INSERT INTO action_journal (workflow_id, digest, idempotency_key, attempt, capability_jti, status, result_json, at, pid) VALUES (?,?,?,?,?,?,?,?,?)",
                     (self.rt.wf_id, digest, idem, n + (status == "STARTED"), jti, status, json.dumps(result, default=str), time.time(), os.getpid()))
        return n + (status == "STARTED")


def unfinished_attempt(store, workflow_id: str, digest: str) -> bool:
    rows = store.q("SELECT status FROM action_journal WHERE workflow_id=? AND digest=? ORDER BY id", workflow_id, digest)
    return bool(rows) and rows[-1][0] == "STARTED"


__all__ = ["ActionDenied", "BudgetExceeded", "McpPool", "ToolPlatform", "crash_point", "unfinished_attempt"]
