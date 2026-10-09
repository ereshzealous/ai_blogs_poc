"""Headless ingress: the single front door for every head.

    authenticate the head's credential (bound to its channel)
    translate the native payload with the head's adapter; a payload that cannot become a valid envelope is a
        poison message and goes to the dead-letter table, not to the runtime
    authorize the INVOCATION (may this principal start this intent?)  -- not the actions that may follow
    de-duplicate: the same (source, event_id) delivered again returns the original execution
    join: a different delivery about the same situation (fingerprint) joins the open execution
    start: sync heads wait for the analysis; async heads get 202 and an execution id
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from hai.config import load, short_id
from hai.contracts import Accepted, ExecutionView, Rejected
from hai.control.identity import AuthError
from hai.ingress.adapters import ADAPTERS
from hai.runtime.service import HeadlessRuntime


class HeadlessIngress:
    def __init__(self, runtime: HeadlessRuntime):
        self.rt = runtime
        cfg = load("consumers.yaml")
        self.consumers: dict[str, dict[str, Any]] = cfg["consumers"]
        self.window = float(cfg["dedupe_window_s"])
        self.queue: list[str] = []

    def _corr(self, fingerprint: str) -> str:
        open_id = self.rt.open_execution(fingerprint, self._intent_of(fingerprint), self.rt.clock.now() - self.window)
        if open_id:
            return self.rt._load(open_id)["correlation_id"]
        return short_id("cor", fingerprint, int(self.rt.clock.now() // self.window))

    @staticmethod
    def _intent_of(fp: str) -> str:
        return {"degradation": "investigate_incident", "sweep": "health_sweep", "release": "release_check"}[fp.split(":")[0]]

    def receive(self, channel: str, credential: str, payload: dict[str, Any]) -> Accepted | ExecutionView | Rejected:
        rt = self.rt
        with rt.tel.span("request" if channel != "event" else "event", short_id("ingress", channel, json.dumps(payload, sort_keys=True)),
                         f"ingress.{channel}") as sp:
            try:
                principal = rt.directory.authenticate(credential, channel)
            except AuthError as e:
                rt.audit.record("ingress.rejected", None, None, channel=channel, stage="authenticate", reason=str(e))
                sp["attrs"]["outcome"] = "rejected:authenticate"
                return Rejected(reason=str(e), stage="authenticate")
            try:
                env = ADAPTERS[channel](payload, principal, self._corr)
            except (KeyError, ValueError, TypeError, ValidationError) as e:
                reason = f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"
                rt.db.execute("INSERT INTO dead_letters (source, reason, payload, t) VALUES (?,?,?,?)",
                              (channel, reason, json.dumps(payload, sort_keys=True), rt.clock.now()))
                rt.db.commit()
                rt.audit.record("ingress.dead_letter", None, None, channel=channel, principal=principal, reason=reason)
                sp["attrs"]["outcome"] = "dead_letter"
                return Rejected(reason=reason, stage="dead_letter")
            sp["trace_id"] = env.correlation_id
            if env.intent not in self.consumers[channel]["intents"] or not rt.directory.may_invoke(env.on_behalf_of or principal, env.intent):
                rt.audit.record("ingress.rejected", None, env.correlation_id, channel=channel, stage="authorize_invocation", invoker=principal,
                                on_behalf_of=env.on_behalf_of, intent=env.intent)
                sp["attrs"]["outcome"] = "rejected:authorize_invocation"
                return Rejected(reason=f"{env.on_behalf_of or principal} may not start {env.intent}", stage="authorize_invocation")
            seen = rt.db.execute("SELECT execution_id FROM inbox WHERE source=? AND event_id=?", (env.source, env.event_id)).fetchone()
            if seen:
                rt.audit.record("ingress.duplicate", seen["execution_id"], env.correlation_id, source=env.source, event_id=env.event_id)
                sp["attrs"]["outcome"] = "duplicate"
                return Accepted(execution_id=seen["execution_id"], status_url=f"/executions/{seen['execution_id']}", duplicate=True)
            joined = rt.open_execution(env.fingerprint, env.intent, rt.clock.now() - self.window)
            xid = joined or rt.new_execution_id(env)
            rt.db.execute("INSERT INTO inbox VALUES (?,?,?,?,?)", (env.source, env.event_id, rt.clock.now(), env.model_dump_json(), xid))
            rt.db.commit()
            if joined:
                rt.audit.record("execution.joined", xid, env.correlation_id, source=env.source, event_id=env.event_id, channel=channel,
                                invoker=principal, causation_id=env.causation_id)
                sp["attrs"]["outcome"] = "joined"
                return rt.view(xid, joined=True)
            rt.start(env, xid)
            sp["attrs"]["outcome"] = "started"
            if self.consumers[channel]["mode"] == "async":
                self.queue.append(xid)
                return Accepted(execution_id=xid, status_url=f"/executions/{xid}")
        return rt.run(xid)

    def drain(self) -> list[ExecutionView]:
        """The worker: process queued async executions (at-least-once; a re-run of a finished one is a no-op)."""
        out = []
        while self.queue:
            out.append(self.rt.run(self.queue.pop(0)))
        return out
