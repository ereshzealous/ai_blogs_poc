"""The mandatory execution path in the control-plane arm.

    model proposal ─► resolve implementation ─► bind authoritative values ─► schema
    validation (server-declared inputSchema) ─► deterministic policy ─► approval ─►
    signed MCP tools/call ─► result + append-only audit

The model can only propose a capability tool it was shown: a concrete implementation name, even
the authoritative one, is rejected at the proposal stage (``handle``), so it cannot skip binding.

In the control-plane arm the agent loop holds no MCP session; only the gateway does, and
every server is started with ``--enforce-gateway-token`` so a call that skips the gateway
(or replays / alters a signed one) is rejected by the server itself.  That is a POC-level
mechanism (shared HMAC key, one host); production isolation and key management belong to
the Identity & Security learnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from ..mcp_host import Estate
from ..registry.model import Registry
from ..servers.serve import GATEWAY_META_KEY, IDEMPOTENCY_META_KEY, gateway_mac
from ..util import new_id
from .approval import ApprovalService
from .audit import AuditLog
from .binder import Binder, BindResult
from .invocation import CallContext, Invocation
from .policy import ALLOW, DENY, REQUIRE_APPROVAL, Policy
from .provenance import ungrounded_fields
from .resolve import SurfacedCapability, capability_tool_name


@dataclass
class GatewayTrace:
    model_tool: str
    model_args: dict[str, Any]
    proposal_kind: str  # capability | implementation | unknown
    capability: str | None = None
    binding: dict[str, Any] | None = None
    implementation: str | None = None
    canonical_invocation: dict[str, Any] | None = None
    schema_errors: list[str] = field(default_factory=list)
    policy: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    stage_reached: str = "proposal"  # proposal|binding|schema|policy|approval|executed|execution_failed
    audit_seq: list[int] = field(default_factory=list)

    def as_record(self) -> dict[str, Any]:
        return dict(self.__dict__)


class Gateway:
    def __init__(self, estate: Estate, registry: Registry, audit: AuditLog, approvals: ApprovalService, key: str):
        self.estate = estate
        self.registry = registry
        self.policy = Policy(registry)
        self.audit = audit
        self.approvals = approvals
        self.key = key.encode()
        self.binder = Binder(registry, self._internal_read, {q: t.input_schema for q, t in estate.tools.items()})
        self.binding_reads: list[dict[str, Any]] = []
        self.financial_digests_executed: set[str] = set()  # per request (one gateway instance per request in the POC)

    # ------------------------------------------------------------------ signed MCP calls
    async def _signed_call(self, implementation: str, arguments: dict[str, Any], idempotency_key: str | None = None):
        invocation_id = new_id("INV")
        meta: dict[str, Any] = {GATEWAY_META_KEY: {"invocation_id": invocation_id, "mac": gateway_mac(self.key, implementation, arguments, invocation_id)}}
        if idempotency_key:
            meta[IDEMPOTENCY_META_KEY] = idempotency_key
        return invocation_id, await self.estate.call(implementation, arguments, meta=meta)

    async def _internal_read(self, implementation: str, arguments: dict[str, Any], purpose: str = "binding_read"):
        inv_id, out = await self._signed_call(implementation, arguments)
        rec = {"implementation": implementation, "arguments": arguments, "invocation_id": inv_id, "is_error": out.is_error, "purpose": purpose}
        self.binding_reads.append(rec)
        self.audit.append(purpose, {**rec, "result": out.structured if not out.is_error else out.text[:300]})
        return (not out.is_error), out.structured, out.text

    async def context_read(self, implementation: str, arguments: dict[str, Any]):
        return await self._internal_read(implementation, arguments, "context_read")

    # ------------------------------------------------------------------ the pipeline
    async def handle(
        self,
        model_tool: str,
        model_args: dict[str, Any],
        ctx: CallContext,
        surfaced: dict[str, SurfacedCapability],
        request_text: str | None = None,
    ) -> tuple[dict[str, Any], GatewayTrace]:
        """The model-facing entry point: only a capability tool surfaced to the model may be proposed.

        A concrete implementation name (even the authoritative one) is rejected here, so a guessed
        ``server__tool`` name can never skip capability binding and its business invariants.
        """
        result, trace = await self._handle(model_tool, model_args, ctx, surfaced, request_text, model_facing=True)
        result["next_step"] = self._next_step(result, trace)
        return result, trace

    async def govern_implementation(
        self,
        implementation_tool: str,
        model_args: dict[str, Any],
        ctx: CallContext,
        request_text: str | None = None,
    ) -> tuple[dict[str, Any], GatewayTrace]:
        """Internal: run policy, approval and execution for a named implementation (no capability binding).

        Not reachable from the agent loop; used by deterministic tests of the policy rules (P1 to P5, schema)
        against implementations the binder would never choose.
        """
        result, trace = await self._handle(implementation_tool, model_args, ctx, {}, request_text, model_facing=False)
        result["next_step"] = self._next_step(result, trace)
        return result, trace

    async def _handle(self, model_tool, model_args, ctx, surfaced, request_text, model_facing):
        model_args = dict(model_args or {})
        if model_tool in surfaced:
            trace = GatewayTrace(model_tool, model_args, "capability", capability=surfaced[model_tool].capability)
        elif model_tool in self.estate.by_model_name and model_facing:
            # the model named a concrete implementation: recorded as such (the scorer judges what was proposed),
            # stopped at the proposal stage, before any binding, policy or execution
            impl = self.estate.by_model_name[model_tool].qualified
            rec = self.registry.get(impl)
            trace = GatewayTrace(model_tool, model_args, "implementation", capability=rec.capability if rec else None, implementation=impl)
            self._audit(trace, "proposal_rejected", {"model_tool": model_tool, "implementation": impl, "requester": ctx.requester_id,
                                                     "request_id": ctx.request_id, "reason": "implementation names cannot be called directly"})
            return {"status": "NOT_EXECUTED", "stage": "proposal", "kind": "not_surfaced",
                    "reason": f"{model_tool} is not a capability tool; implementations cannot be called directly",
                    "capability": trace.capability}, trace
        elif model_tool in self.estate.by_model_name:
            impl = self.estate.by_model_name[model_tool].qualified
            rec = self.registry.get(impl)
            trace = GatewayTrace(model_tool, model_args, "implementation", capability=rec.capability if rec else None, implementation=impl)
        else:
            trace = GatewayTrace(model_tool, model_args, "unknown")
            self._audit(trace, "proposal_rejected", {"model_tool": model_tool, "reason": "unknown tool"})
            return {"status": "NOT_EXECUTED", "stage": "proposal", "reason": f"unknown tool {model_tool}"}, trace

        self._audit(trace, "proposal", {"model_tool": model_tool, "model_args": model_args, "capability": trace.capability, "implementation": trace.implementation, "requester": ctx.requester_id, "request_id": ctx.request_id})

        # 0. the proposal must satisfy the capability's model-facing schema (types, enums) before anything is bound
        if trace.proposal_kind == "capability":
            perr = sorted(e.message for e in Draft202012Validator(surfaced[model_tool].parameters).iter_errors(model_args))
            if perr:
                trace.stage_reached = "proposal_schema"
                trace.schema_errors = perr
                self._audit(trace, "proposal_rejected", {"model_tool": model_tool, "errors": perr})
                return {"status": "NOT_EXECUTED", "stage": "proposal_schema", "reason": "; ".join(perr)}, trace

        # 1. bind
        if trace.proposal_kind == "capability":
            bind: BindResult = await self.binder.bind_capability(trace.capability, model_args)
        else:
            bind = await self.binder.bind_implementation(trace.implementation, model_args)
        trace.binding = bind.as_record()
        trace.stage_reached = "binding"
        self._audit(trace, "binding", trace.binding)
        if not bind.ok:
            return {"status": "NOT_EXECUTED", "stage": "binding", "reason": bind.error, "kind": bind.error_kind}, trace
        trace.implementation = bind.implementation
        inv = Invocation(bind.implementation, bind.arguments, ctx, tuple(bind.bound_fields))
        trace.canonical_invocation = inv.canonical()

        # 1b. provenance: requester-owned values must come from the requester
        cap_rec = self.registry.capabilities.get(trace.capability or "")
        if request_text is not None and cap_rec is not None and cap_rec.user_owned:
            missing_prov = ungrounded_fields(cap_rec.user_owned, inv.arguments, bind.bound_fields, request_text)
            if missing_prov:
                trace.stage_reached = "provenance"
                self._audit(trace, "provenance_rejected", {"invocation": inv.canonical(), "ungrounded": missing_prov})
                return {"status": "NOT_EXECUTED", "stage": "provenance", "kind": "ungrounded_user_value", "fields": missing_prov,
                        "reason": f"{', '.join(missing_prov)} must be provided by the requester; the request does not contain the value used"}, trace

        # 2. schema validation against what the server declared over MCP
        schema = self.estate.tools[inv.implementation].input_schema
        errors = sorted(e.message for e in Draft202012Validator(schema).iter_errors(inv.arguments))
        trace.stage_reached = "schema"
        if errors:
            trace.schema_errors = errors
            self._audit(trace, "schema_rejected", {"invocation": inv.canonical(), "errors": errors})
            owned = set(cap_rec.user_owned) if cap_rec else set()
            missing_owned = sorted(f for f in owned if f not in inv.arguments)
            return {"status": "NOT_EXECUTED", "stage": "schema", "reason": "; ".join(errors), **({"fields": missing_owned, "kind": "missing_user_value"} if missing_owned else {})}, trace

        # 3. deterministic policy (a human approval counts only if it matches this exact invocation's digest)
        approved = self.approvals.find_approved(inv.digest(self.policy.version))
        digest = inv.digest(self.policy.version)  # an identical retry is a replay (idempotent), not a second action
        facts = {**bind.facts, "prior_financial_writes": len(self.financial_digests_executed - {digest})}
        decision = self.policy.evaluate(inv, facts, approval_valid=approved is not None)
        trace.policy = decision.as_record()
        trace.stage_reached = "policy"
        self._audit(trace, "policy", {"invocation": inv.canonical(), **decision.as_record()})
        if decision.decision == DENY:
            return {"status": "DENIED", "rule": decision.rule, "reason": decision.reason, "invocation": self._summary(inv)}, trace

        # 4. approval for this exact invocation (a supervisor's rejection of the same invocation stands)
        if decision.decision == REQUIRE_APPROVAL and (rejected := self.approvals.find_rejected(inv.digest(self.policy.version))):
            trace.approval = rejected.as_record()
            trace.stage_reached = "approval"
            self._audit(trace, "approval_rejected_resubmission", {"approval_id": rejected.approval_id, "digest": rejected.digest})
            return {"status": "DENIED", "rule": "P7_APPROVAL_REJECTED", "reason": f"a supervisor rejected this exact invocation ({rejected.approval_id})",
                    "invocation": self._summary(inv)}, trace
        if decision.decision == REQUIRE_APPROVAL:
            apr = self.approvals.request(inv, self.policy.version, decision.reason)
            trace.approval = apr.as_record()
            trace.stage_reached = "approval"
            self._audit(trace, "approval_requested", apr.as_record())
            return {
                "status": "APPROVAL_REQUIRED",
                "rule": decision.rule,
                "approval_id": apr.approval_id,
                "reason": decision.reason,
                "invocation": self._summary(inv),
                "note": "Nothing was executed. A supervisor must approve this exact invocation; any change to it needs a new approval.",
            }, trace

        assert decision.decision == ALLOW
        if approved is not None and decision.rule == "P8_ALLOW":
            self.approvals.consume(approved.approval_id)
            trace.approval = approved.as_record()
            self._audit(trace, "approval_consumed", {"approval_id": approved.approval_id, "digest": approved.digest})
        return await self._execute(inv, trace)

    async def execute_approved(self, approval_id: str, inv: Invocation, facts: dict[str, Any]) -> tuple[dict[str, Any], GatewayTrace]:
        """Execution after a human approved: approval must match this invocation's digest."""
        trace = GatewayTrace(inv.implementation, inv.arguments, "approved_invocation", implementation=inv.implementation, canonical_invocation=inv.canonical())
        ok, why = self.approvals.check(approval_id, inv, self.policy.version)
        decision = self.policy.evaluate(inv, facts, approval_valid=ok)
        trace.policy = {**decision.as_record(), "approval_check": why}
        self._audit(trace, "policy", {"invocation": inv.canonical(), "approval_id": approval_id, "approval_check": why, **decision.as_record()})
        if decision.decision != ALLOW:
            return {"status": "DENIED" if decision.decision == DENY else "APPROVAL_REQUIRED", "rule": decision.rule, "reason": why if not ok else decision.reason}, trace
        self.approvals.consume(approval_id)
        return await self._execute(inv, trace)

    async def _execute(self, inv: Invocation, trace: GatewayTrace) -> tuple[dict[str, Any], GatewayTrace]:
        rec = self.registry.get(inv.implementation)
        idem = inv.digest(self.policy.version) if rec and rec.side_effect != "none" else None  # same invocation -> same key
        invocation_id, out = await self._signed_call(inv.implementation, inv.arguments, idem)
        trace.execution = {"invocation_id": invocation_id, "idempotency_key": idem, **out.as_record()}
        trace.stage_reached = "execution_failed" if out.is_error else "executed"
        rec_impl = self.registry.get(inv.implementation)
        if not out.is_error and rec_impl is not None and rec_impl.side_effect == "financial_write":
            self.financial_digests_executed.add(inv.digest(self.policy.version))
        self._audit(trace, "execution", {"invocation": inv.canonical(), "invocation_id": invocation_id, **out.as_record()})
        if out.is_error:
            return {"status": "FAILED", "reason": out.text[:500], "invocation": self._summary(inv)}, trace
        return {"status": "EXECUTED", "result": out.structured if out.structured is not None else out.text, "invocation": self._summary(inv)}, trace

    def _next_step(self, result: dict[str, Any], trace: GatewayTrace) -> str:
        st, kind, rule = result.get("status"), result.get("kind"), result.get("rule")
        if st == "EXECUTED":
            return "Done. Use this result; finish with outcome completed once all requested actions are done."
        if st == "APPROVAL_REQUIRED":
            return "Nothing was executed. Finish with outcome needs_approval and describe the action awaiting supervisor approval."
        if st == "DENIED" and rule == "P7_APPROVAL_REJECTED":
            return "A supervisor rejected this action. Do not retry it; finish with outcome refused and tell the representative."
        if st == "DENIED" and rule == "P6_SCOPE":
            return "This requester is not permitted to do this. Finish with outcome refused and suggest escalating to tier 2."
        if st == "DENIED":
            cap = trace.capability
            if cap and self.registry.capabilities.get(cap):
                return f"This implementation may not be used ({rule}). Use the capability tool {capability_tool_name(cap)} instead."
            return "This tool is not governed by the platform and may not be used. Use only the listed capability tools."
        if kind == "not_surfaced":
            cap = result.get("capability")
            if cap and self.registry.capabilities.get(cap):
                return f"Implementations cannot be called directly. Use the capability tool {capability_tool_name(cap)} instead."
            return "Implementations cannot be called directly. Use only the listed capability tools."
        if kind in ("entity_not_found", "no_matching_charge"):
            return "The target does not exist in the system of record. Do not retry with other values; finish with outcome refused and explain."
        if kind == "ambiguous":
            return "More than one record matches. Ask the representative which one (outcome needs_clarification)."
        if kind in ("ungrounded_user_value", "missing_user_value"):
            return f"Only the representative can provide {', '.join(result.get('fields', []))}. Do not guess; finish with outcome needs_clarification and ask for it."
        if st == "FAILED":
            return "The system of record rejected the call. Do not invent values; correct what the error says, or finish explaining why it cannot be done."
        return "Fix the arguments as the reason says, or finish explaining why it cannot be done."

    @staticmethod
    def _summary(inv: Invocation) -> dict[str, Any]:
        return {"implementation": inv.implementation, "arguments": inv.arguments, "platform_bound": list(inv.bound_fields)}

    def _audit(self, trace: GatewayTrace, kind: str, payload: dict[str, Any]) -> None:
        rec = self.audit.append(kind, payload)
        trace.audit_seq.append(rec["seq"])
