"""The tool gateway: the execution boundary between an agent's decision and a production system.

Before anything leaves the platform the gateway checks that the capability is in the agent's tool catalog and that the call
carries a policy evaluation that permitted it (and, where required, approvals bound to this exact action).  It then gives
the action a stable identity and every try at it an identity of its own:

    action_id   one per decided action, derived from the execution and the action digest; it is the Idempotency-Key
    attempt_id  action_id + ".a<n>", numbered durably in state/workflow.db, so attempts stay distinct across retries,
                duplicate deliveries and process restarts

Every attempt is recorded before it is sent (attempt.started, fsynced) and after its result is known (attempt.finished).
A timeout is recorded as what it is: an unknown outcome, not a failure.  Arguments are recorded as the allow-listed fields
of the capability; the credential is never recorded.
"""

from __future__ import annotations

import http.client
import json
import socket
import sqlite3
import time
from pathlib import Path

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from . import crash
from . import semconv as sc
from .common import attempt_id, load, now_iso, short
from .telemetry import inject_headers

CATALOG = load("control_plane.toml")["tool_catalogs"]
TOKEN = "dpl_live_7Fq2xW9rTt3LmZ"        # the gateway's deploy-api credential (see deploysvc.CREDENTIALS)
TOOL_IDENTITY = "spiffe://prod.example/ns/agents/sa/tool-gateway"
RETRYABLE = {"TIMEOUT", "UNAVAILABLE", "CONFLICT_IN_PROGRESS", "CONNECTION_ERROR"}


class Gateway:
    def __init__(self, rt, port: int, idempotency: bool, timeout_s: float, max_attempts: int) -> None:
        self.rt, self.port, self.idempotency, self.timeout, self.max = rt, port, idempotency, timeout_s, max_attempts
        self.db: sqlite3.Connection = rt.wf
        self.db.execute("CREATE TABLE IF NOT EXISTS attempts (action_id TEXT, n INTEGER, attempt_id TEXT, status TEXT, request_id TEXT, "
                        "result TEXT, PRIMARY KEY (action_id, n))")

    # ---- authorization at the boundary -------------------------------------------------------------------------------
    def authorize(self, action: dict, catalog_ref: str, pe: dict | None, approvals_ok: bool, path: str) -> str | None:
        """Returns a refusal reason, or None when the call may leave the platform."""
        granted = CATALOG[catalog_ref.split("@")[1]]["granted"]
        if action["capability"] not in granted:
            return f"capability {action['capability']} is not in tool catalog {catalog_ref}"
        if pe is None or pe["decision"] not in ("ALLOW", "ALLOW_WITH_APPROVAL"):
            return "no policy evaluation permits this call"
        if pe["decision"] == "ALLOW_WITH_APPROVAL" and not approvals_ok:
            return "approval required and not satisfied for this action digest"
        return None

    def deny(self, action: dict, catalog_ref: str, reason: str, pe_id: str | None, path: str) -> None:
        rt = self.rt
        rt.tlog("WARN", "call refused", capability=action["capability"], service=action.get("service"), incident=rt.incident, reason=reason)
        rt.evidence("gateway.denied", {"capability": action["capability"], "target": action.get("service"), "reason": reason,
                                       "catalog": catalog_ref, "policy_evaluation_id": pe_id, "path": path})

    # ---- attempts ----------------------------------------------------------------------------------------------------
    def next_n(self, action_id: str) -> int:
        (m,) = self.db.execute("SELECT COALESCE(MAX(n), 0) FROM attempts WHERE action_id=?", (action_id,)).fetchone()
        return m + 1

    def in_flight(self, action_id: str) -> list[tuple[int, str]]:
        return self.db.execute("SELECT n, request_id FROM attempts WHERE action_id=? AND status='IN_FLIGHT' ORDER BY n", (action_id,)).fetchall()

    def invoke(self, action: dict, action_id: str) -> dict:
        """Try the action until it succeeds, fails for good, or attempts run out.  Returns the last attempt's result."""
        rt = self.rt
        tracer = trace.get_tracer("lineage")
        result: dict = {}
        tries = 0
        while tries < self.max:
            tries += 1
            n = self.next_n(action_id)
            aid = attempt_id(action_id, n)
            rid = "tgw-" + short([aid, rt.role], 12)
            key = action_id if self.idempotency else None
            self.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?)", (action_id, n, aid, "IN_FLIGHT", rid, None))
            with tracer.start_as_current_span(f"execute_tool {action['capability']}", kind=SpanKind.INTERNAL,
                                              attributes={sc.OP: "execute_tool", sc.TOOL_NAME: action["capability"], sc.TOOL_TYPE: "extension",
                                                          sc.TOOL_CALL_ID: rid}):
                rt.evidence("attempt.started", {"attempt": n, "request_id": rid, "idempotency_key": key,
                                                "endpoint": f"POST /v1/deployments/{action['service']}/rollback"}, action_id=action_id, attempt_id=aid)
                rt.tlog("INFO", "calling deploy-api", request_id=rid, capability=action["capability"], service=action["service"],
                        to_version=action["to_version"], incident=rt.incident, attempt=n)
                result = self._post(action, rid, key)
                crash.hit("after_dispatch")      # the response is in memory; nothing about it is recorded yet
            self.db.execute("UPDATE attempts SET status=?, result=? WHERE action_id=? AND n=?", (result["result"], json.dumps(result), action_id, n))
            rt.evidence("attempt.finished", {"attempt": n, "result": result["result"], "http_status": result.get("http_status"),
                                             "external_transaction_id": result.get("txn"), "replayed": result.get("replayed", False),
                                             "latency_ms": result["latency_ms"], "error": result.get("error"),
                                             "claimed_status": result.get("claimed_status")}, action_id=action_id, attempt_id=aid)
            level = "INFO" if result["result"] in ("COMMITTED", "REPLAYED") else "WARN"
            rt.tlog(level, "deploy-api " + ("responded" if result.get("http_status") else "did not respond"), request_id=rid,
                    status=result.get("http_status"), result=result["result"], duration_ms=result["latency_ms"], incident=rt.incident, attempt=n,
                    error=result.get("error"))
            rt.metric_attempt(action["capability"], result["result"])
            if result["result"] not in RETRYABLE:
                break
            if tries < self.max:
                rt.tlog("INFO", "retrying", incident=rt.incident, attempt=n + 1)
                time.sleep(0.2 * tries)
        return result

    def _post(self, action: dict, rid: str, key: str | None) -> dict:
        body = json.dumps({"to_version": action["to_version"]})
        headers = {"content-type": "application/json", "authorization": f"Bearer {TOKEN}", "x-request-id": rid, "x-actor": self.rt.agent_id}
        if key:
            headers["idempotency-key"] = key
        path = f"/v1/deployments/{action['service']}/rollback"
        tracer = trace.get_tracer("lineage")
        t0 = time.perf_counter()
        with tracer.start_as_current_span("POST", kind=SpanKind.CLIENT, attributes={
                sc.HTTP_METHOD: "POST", sc.URL_FULL: f"http://127.0.0.1:{self.port}{path}", sc.SERVER_ADDRESS: "127.0.0.1",
                sc.SERVER_PORT: self.port}) as span:
            inject_headers(headers)
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout)
            try:
                conn.request("POST", path, body=body, headers=headers)
                r = conn.getresponse()
                data = json.loads(r.read() or b"{}")
                span.set_attribute(sc.HTTP_STATUS, r.status)
                replayed = r.getheader("Idempotent-Replayed") == "true"
                out = {"http_status": r.status, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
                if r.status == 200:
                    out.update(result="REPLAYED" if replayed else "COMMITTED", txn=data.get("transaction_id"), replayed=replayed,
                               claimed_status=data.get("status"), response={k: data.get(k) for k in ("revision", "previous_revision", "to_version")})
                elif r.status == 409:
                    out.update(result="CONFLICT_IN_PROGRESS", error=data.get("error"))
                elif r.status == 503:
                    out.update(result="UNAVAILABLE", error=data.get("error"))
                    span.set_status(Status(StatusCode.ERROR))
                else:
                    out.update(result="REFUSED", error=data.get("error"))
                    span.set_status(Status(StatusCode.ERROR))
                return out
            except (socket.timeout, TimeoutError):
                span.set_attribute(sc.ERROR_TYPE, "timeout")
                span.set_status(Status(StatusCode.ERROR))
                return {"result": "TIMEOUT", "http_status": None, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                        "error": f"no response within {self.timeout}s: outcome unknown"}
            except (ConnectionError, http.client.HTTPException) as e:
                span.set_attribute(sc.ERROR_TYPE, type(e).__name__)
                span.set_status(Status(StatusCode.ERROR))
                return {"result": "CONNECTION_ERROR", "http_status": None, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                        "error": type(e).__name__}
            finally:
                conn.close()

    # ---- reads (state observation and reconciliation) -----------------------------------------------------------------
    def get(self, path: str) -> dict:
        tracer = trace.get_tracer("lineage")
        with tracer.start_as_current_span("GET", kind=SpanKind.CLIENT, attributes={sc.HTTP_METHOD: "GET", sc.URL_FULL: f"http://127.0.0.1:{self.port}{path}"}) as span:
            headers = inject_headers({"authorization": f"Bearer {TOKEN}", "x-request-id": "tgw-r-" + short([path, now_iso()], 10)})
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            try:
                conn.request("GET", path, headers=headers)
                r = conn.getresponse()
                span.set_attribute(sc.HTTP_STATUS, r.status)
                return json.loads(r.read())
            finally:
                conn.close()
