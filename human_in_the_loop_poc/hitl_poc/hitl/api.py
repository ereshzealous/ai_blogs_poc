"""The HTTP surface and the approval inbox (stdlib only).

    POST /events                         a monitoring event (Authorization: Bearer <workload credential>)
    GET  /executions/{correlation_id}    the execution and its proposals
    GET  /approvals                      proposals awaiting a decision, with everything an approver needs to see
    GET  /approvals/{proposal_id}        one proposal
    POST /approvals/{proposal_id}/decision   {"decision": "approve"|"deny", "action_digest": ..., "reason": ...}
                                         the approver is the credential's principal; a body cannot name one
    GET  /audit/{correlation_id}         the hash-chained audit records
    GET  /                               the approval inbox (a page; pick a demo identity, then decide)

    uv run hitl serve                    → http://127.0.0.1:8787/
"""

from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from hitl.approvals import DecisionRefused, ServiceUnavailable
from hitl.base import AuthError, iso
from hitl.contracts import DecisionRequest
from hitl.platform import Platform

INBOX = Path(__file__).with_name("inbox.html")


def approval_card(p: Platform, rec: dict[str, Any]) -> dict[str, Any]:
    """Everything a human needs to decide without reconstructing a conversation."""
    pr = rec["proposal"]
    return {"proposal_id": pr.proposal_id, "state": rec["state"], "what": f"{pr.capability} {pr.target.service}",
            "where": pr.target.environment, "from": pr.arguments.get("from_version"), "to": pr.arguments.get("to_version"),
            "why": pr.reason, "risk": pr.risk, "evidence": pr.evidence_refs, "requested_by": f"{pr.requested_by.agent_id} (agent) via {pr.requested_by.runtime}",
            "invoked_by": pr.requested_by.invoker, "acting_for": pr.acting_on_behalf_of.id,
            "policy": f"{pr.policy.policy_id} v{pr.policy.version} · {pr.policy.rule}", "expires": iso(pr.expires_at),
            "impact": pr.context.get("impact"), "recovery": pr.context.get("recovery"), "deployment_author": pr.context.get("deployment_author"),
            "precondition": f"running version is {pr.preconditions.get('current_version')}", "action_digest": pr.action_digest,
            "you_are_authorizing": f"exactly one call: {pr.capability}({pr.target.service}, {pr.target.environment}, "
                                   + ", ".join(f"{k}={v}" for k, v in pr.arguments.items()) + ")"}


class Handler(BaseHTTPRequestHandler):
    platform: Platform

    def log_message(self, *a):  # quiet
        pass

    def _send(self, status: int, body: Any, ctype: str = "application/json") -> None:
        data = body.encode() if isinstance(body, str) else json.dumps(body, indent=1, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _cred(self) -> str | None:
        h = self.headers.get("Authorization", "")
        return h.split(" ", 1)[1] if h.startswith("Bearer ") else None

    def _body(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self) -> None:  # noqa: N802
        P, parts = self.platform, [x for x in self.path.split("?")[0].split("/") if x]
        try:
            if not parts:
                return self._send(200, INBOX.read_text(), "text/html; charset=utf-8")
            P.directory.authenticate(self._cred())
            if parts == ["approvals"]:
                P.approvals.expire_due()
                return self._send(200, [approval_card(P, r) for r in P.approvals.list("PENDING_APPROVAL")])
            if parts[0] == "approvals" and len(parts) == 2:
                r = P.approvals.get(parts[1])
                return self._send(200, approval_card(P, r)) if r else self._send(404, {"error": "no such proposal"})
            if parts[0] == "executions" and len(parts) == 2:
                return self._send(200, P.view(parts[1]))
            if parts[0] == "audit" and len(parts) == 2:
                return self._send(200, P.audit.records(parts[1]))
            return self._send(404, {"error": "not found"})
        except AuthError:
            return self._send(401, {"error": "unauthenticated"})
        except ServiceUnavailable as e:
            return self._send(503, {"error": str(e)})

    def do_POST(self) -> None:  # noqa: N802
        P, parts = self.platform, [x for x in self.path.split("?")[0].split("/") if x]
        try:
            if parts == ["events"]:
                return self._send(202, P.receive(self._cred(), self._body()))
            if len(parts) == 3 and parts[0] == "approvals" and parts[2] == "decision":
                body = self._body()
                claimed = body.pop("approver", None)                       # recorded and ignored: identity comes from the credential
                req = DecisionRequest.model_validate(body)
                d = P.approvals.decide(parts[1], self._cred(), req, claimed_approver=claimed)
                out: dict[str, Any] = {"decision": d.model_dump()}
                if d.decision == "approve":                                # the workflow resumes: the gate re-checks everything
                    out["execution"] = P.execute_proposal(parts[1]).model_dump()
                return self._send(200, out)
            return self._send(404, {"error": "not found"})
        except AuthError:
            return self._send(401, {"error": "unauthenticated"})
        except DecisionRefused as e:
            return self._send(e.status, {"error": e.reason})
        except ValidationError as e:
            return self._send(422, {"error": str(e).splitlines()[0]})
        except ServiceUnavailable as e:
            return self._send(503, {"error": str(e)})


def make_server(workdir: Path, port: int = 8787) -> ThreadingHTTPServer:
    P = Platform(workdir)
    h = type("H", (Handler,), {"platform": P})
    return ThreadingHTTPServer(("127.0.0.1", port), h)


def _call(base: str, method: str, path: str, cred: str | None, body: dict | None = None) -> tuple[int, Any]:
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {cred}"} if cred else {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def roundtrip(workdir: Path) -> dict[str, Any]:
    """Drive the real HTTP surface once: event in, inbox, a refused and an accepted decision, execution, audit out."""
    srv = make_server(workdir, 0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    log: list[dict[str, Any]] = []

    def step(name, want, method, path, cred, body=None):
        s, b = _call(base, method, path, cred, body)
        log.append({"step": name, "method": method, "path": path.split("/")[1] if "/" in path else path, "status": s, "expected": want, "ok": s == want})
        return b

    try:
        ev = step("event", 202, "POST", "/events", "tok-monitor", {"source": "monitoring/datadog", "id": "dd-api-1", "service": "payment-service",
                                                                     "environment": "production", "signal": {"error_rate": 0.14}})
        step("inbox without a credential", 401, "GET", "/approvals", None)
        inbox = step("inbox", 200, "GET", "/approvals", "tok-alice")
        card = inbox[0]
        step("one approval", 200, "GET", f"/approvals/{card['proposal_id']}", "tok-alice")
        step("readonly engineer decides", 403, "POST", f"/approvals/{card['proposal_id']}/decision", "tok-reggie",
             {"decision": "approve", "action_digest": card["action_digest"]})
        step("agent claims to be alice", 403, "POST", f"/approvals/{card['proposal_id']}/decision", "tok-agent",
             {"decision": "approve", "action_digest": card["action_digest"], "approver": "alice"})
        done = step("alice approves the exact digest", 200, "POST", f"/approvals/{card['proposal_id']}/decision", "tok-alice",
                    {"decision": "approve", "action_digest": card["action_digest"], "reason": "evidence reviewed"})
        step("execution view", 200, "GET", f"/executions/{ev['correlation_id']}", "tok-alice")
        audit = step("audit", 200, "GET", f"/audit/{ev['correlation_id']}", "tok-alice")
        rollbacks = srv.RequestHandlerClass.platform.ent.effect_count("rollback")
        return {"calls": len(log), "calls_ok": sum(x["ok"] for x in log), "rollbacks": rollbacks, "execution_code": done["execution"]["code"],
                "audit_records": len(audit), "card_fields": sorted(card), "log": log}
    finally:
        srv.shutdown()


def serve(port: int = 8787) -> None:
    work = Path(tempfile.mkdtemp(prefix="hitl-serve-"))
    srv = make_server(work, port)
    P = srv.RequestHandlerClass.platform
    P.receive("tok-monitor", {"source": "monitoring/datadog", "id": "dd-evt-88121", "service": "payment-service", "environment": "production",
                              "signal": {"error_rate": 0.14}})
    print(f"approval inbox: http://127.0.0.1:{port}/   (a payment-service rollback is waiting; state in {work})")
    srv.serve_forever()
