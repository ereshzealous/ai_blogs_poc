"""The capability gateway: the one entry point every channel adapter calls.

    adapter → validate contract → resolve identity → capability → platform facade
                                                   ↘ interactions, subscriptions, outbox (channel-facing state)

It schedules platform commands in the background (a chat webhook must answer in seconds) or awaits them (a CLI
process that exits when it is done). It does not decide workflow steps, policy or approvals: those stay in the
layered platform.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from pydantic import ValidationError

from headless_ai_platform import SCHEMA_VERSION
from headless_ai_platform.capabilities.incident_remediation import IncidentRemediation
from headless_ai_platform.contracts import (Actor, CapabilityError, CapabilityRequest, CapabilityResponse, ErrorCode,
                                            Operation, Status)
from headless_ai_platform.identity.resolver import IdentityResolver, Principal
from headless_ai_platform.interactions import InteractionStore
from headless_ai_platform.platform.port import PlatformPort, View
from headless_ai_platform.settings import Settings, load_settings

log = logging.getLogger("headless")
Sender = Callable[[str, str | None, dict[str, Any]], Awaitable[None]]  # (address, thread_ref, response) -> delivered


def parse(payload: Any) -> CapabilityRequest:
    """Contract validation, with the version checked before the shape so old clients get a clear answer."""
    if isinstance(payload, CapabilityRequest):
        payload = payload.model_dump(mode="json")
    if not isinstance(payload, dict):
        raise CapabilityError(ErrorCode.INVALID_REQUEST, "a capability request is a JSON object")
    version = payload.get("schema_version", SCHEMA_VERSION)
    if str(version).split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise CapabilityError(ErrorCode.UNSUPPORTED_VERSION, f"schema_version {version} is not served; use {SCHEMA_VERSION}")
    try:
        return CapabilityRequest.model_validate(payload)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'request'}: {e['msg']}" for e in exc.errors())
        raise CapabilityError(ErrorCode.INVALID_REQUEST, problems) from exc


class CapabilityGateway:
    def __init__(self, platform: PlatformPort, store: InteractionStore, *, settings: Settings | None = None,
                 resolver: IdentityResolver | None = None):
        s = settings or load_settings()
        self.platform = platform
        self.store = store
        self.resolver = resolver or IdentityResolver(platform.principal)
        cfg = s.capability(IncidentRemediation.name) or {}
        self.capabilities = {IncidentRemediation.name: IncidentRemediation(platform, str(cfg.get("version", "1")),
                                                                           cfg.get("default_request", "Investigate this incident."))}
        self.notify_cfg = s.raw.get("notifications", {})
        self.tasks: set[asyncio.Task[Any]] = set()

    # ---------------------------------------------------------------- entry point
    async def handle(self, payload: Any, *, wait: bool = False) -> CapabilityResponse:
        req = parse(payload)
        principal: Principal | None = None
        wf_id = req.workflow_id
        try:
            cap = self.capabilities.get(req.capability)
            if cap is None:
                raise CapabilityError(ErrorCode.UNKNOWN_CAPABILITY, f"no capability named {req.capability!r}")
            principal = self.resolver.resolve(req.actor, service=req.input.get("service"))
            if req.operation is Operation.START:
                resp = await self._start(cap, principal, req, wait)
            else:
                view = self._view(str(wf_id))
                if req.operation is Operation.GET:
                    resp = cap.response(view, principal, req.actor.channel)
                else:
                    run = cap.act(principal, req, view)
                    self._subscribe(str(wf_id), req, principal)
                    resp = await self._run(cap, principal, req.actor.channel, str(wf_id), run, wait)
        except CapabilityError as exc:
            self._record(req, principal, wf_id, exc.code.value, None, None)
            raise
        self._record(req, principal, resp.workflow_id, "OK", resp.status.value, resp.trace_id)
        return resp

    def validate(self, payload: Any) -> CapabilityRequest:
        return parse(payload)

    def principal_for(self, actor: Actor) -> Principal:
        return self.resolver.resolve(actor)

    # ---------------------------------------------------------------- operations
    async def _start(self, cap: IncidentRemediation, principal: Principal, req: CapabilityRequest,
                     wait: bool) -> CapabilityResponse:
        ctx, channel = req.channel_context, req.actor.channel
        if ctx.idempotency_key:
            existing = self.store.remembered(channel, ctx.idempotency_key)
            if existing:  # a retried webhook or a repeated alert: same workflow, no second investigation
                return cap.response(self._view(existing), principal, channel)
        session_id = f"{channel}:{ctx.thread_ref}" if ctx.thread_ref else None
        wf_id, run = cap.start(principal, req, session_id)
        if ctx.idempotency_key:
            self.store.remember(channel, ctx.idempotency_key, wf_id)
        self._subscribe(wf_id, req, principal)
        return await self._run(cap, principal, channel, wf_id, run, wait)

    async def _run(self, cap: IncidentRemediation, principal: Principal, channel: str, wf_id: str,
                   run: Coroutine[Any, Any, View], wait: bool) -> CapabilityResponse:
        if wait:
            try:
                await run
            finally:
                self.reconcile(wf_id)
        else:
            self._background(wf_id, run)
        return cap.response(self._view(wf_id), principal, channel)

    def _view(self, wf_id: str) -> View:
        try:
            return self.platform.view(wf_id)
        except KeyError as exc:
            raise CapabilityError(ErrorCode.NOT_FOUND, f"unknown workflow {wf_id}") from exc

    def _background(self, wf_id: str, run: Coroutine[Any, Any, View]) -> None:
        async def go() -> None:
            try:
                await run
            except Exception:  # the platform recorded the failure; the channel learns it from the workflow state
                log.exception("workflow %s stopped with an error", wf_id)
            finally:
                self.reconcile(wf_id)

        task = asyncio.create_task(go())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def drain(self) -> None:
        """Wait for background work (tests, experiments, shutdown)."""
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    # ---------------------------------------------------------------- channel-facing state
    def _subscribe(self, wf_id: str, req: CapabilityRequest, principal: Principal) -> None:
        if req.channel_context.reply_to:
            self.store.subscribe(wf_id, req.actor.channel, req.channel_context.reply_to, principal.principal_id,
                                 req.channel_context.thread_ref)

    def _record(self, req: CapabilityRequest, principal: Principal | None, wf_id: str | None, outcome: str,
                status: str | None, trace_id: str | None) -> None:
        self.store.record(workflow_id=wf_id, capability=req.capability, channel=req.actor.channel,
                          channel_subject=req.actor.channel_subject,
                          principal_id=principal.principal_id if principal else None, operation=req.operation.value,
                          action_id=req.action_id, outcome=outcome, status=status, trace_id=trace_id,
                          thread_ref=req.channel_context.thread_ref)

    def reconcile(self, wf_id: str) -> int:
        """Queue a notification for every subscriber whose last seen status differs from the workflow's."""
        try:
            view = self.platform.view(wf_id)
        except KeyError:
            return 0
        if view["status"] == Status.RUNNING:
            return 0
        cap = self.capabilities[IncidentRemediation.name]
        queued = 0
        for sub in self.store.subscriptions(wf_id):
            principal = self.resolver.resolve_principal(sub["principal_id"])
            payload = cap.response(view, principal, sub["channel"]).model_dump(mode="json")
            queued += self.store.enqueue(sub, view["status"], payload)
        return queued

    async def deliver(self, senders: dict[str, Sender]) -> dict[str, int]:
        """One delivery pass for the channels this process can reach. Failures stay queued."""
        out = {"delivered": 0, "failed": 0}
        if not senders:
            return out
        for item in self.store.pending(list(senders), int(self.notify_cfg.get("max_attempts", 50))):
            try:
                await senders[item["channel"]](item["address"], item["thread_ref"], item["payload"])
            except Exception as exc:
                self.store.failed(item["id"], f"{type(exc).__name__}: {exc}")
                out["failed"] += 1
            else:
                self.store.delivered(item["id"])
                out["delivered"] += 1
        return out

    async def delivery_loop(self, senders: dict[str, Sender]) -> None:
        interval = float(self.notify_cfg.get("poll_interval_s", 0.5))
        while True:
            try:
                await self.deliver(senders)
            except Exception:
                log.exception("notification delivery pass failed")
            await asyncio.sleep(interval)
