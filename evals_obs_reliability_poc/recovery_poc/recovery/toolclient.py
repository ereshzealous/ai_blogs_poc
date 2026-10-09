"""The provider client: one HTTP call, and the evidence about it a recovery decision needs.

The client never decides anything.  It returns an Evidence record: was the request sent, how did transport end, was a
response received, which status and headers.  Classification (classify.py) turns that into a failure class and an
execution certainty.  This split is the article's first move: observe facts, then interpret them.

INJECTED transport fault: `tool:<t>:refused@n` makes the n-th attempt connect to a closed local port, a real
ECONNREFUSED (nothing was delivered).  Every other fault is injected by the provider (world.py).
"""

from __future__ import annotations

import http.client
import json
import socket
import time
from dataclasses import asdict, dataclass, field


@dataclass
class Evidence:
    target: str
    method: str
    path: str
    attempt_id: str
    operation_id: str | None = None
    idempotency_key: str | None = None
    deadline_ms: float | None = None
    request_sent: bool = False
    transport: str = "NOT_ATTEMPTED"          # OK | CONNECT_REFUSED | TIMEOUT | RESET | NOT_ATTEMPTED
    response_received: bool = False
    status: int | None = None
    not_executed_header: bool = False
    replayed: bool = False
    body: dict = field(default_factory=dict)

    def facts(self) -> dict:
        d = asdict(self)
        d.pop("body")
        return d


def closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Client:
    def __init__(self, port: int, timeout_ms: int, deadline_ms: int, refused: dict[str, set] | None = None):
        self.port, self.timeout, self.deadline_ms = port, timeout_ms / 1000, deadline_ms
        self.refused = refused or {}                # target -> attempt ordinals to refuse
        self.counts: dict[str, int] = {}

    def call(self, target: str, method: str, path: str, body: dict | None, attempt_id: str, op_id: str | None = None,
             key: str | None = None, on_sent=None, deadline: bool = True, timeout_ms: int | None = None) -> Evidence:
        n = self.counts[target] = self.counts.get(target, 0) + 1
        ev = Evidence(target=target, method=method, path=path, attempt_id=attempt_id, operation_id=op_id, idempotency_key=key)
        headers = {"Content-Type": "application/json", "X-Attempt-Id": attempt_id}
        if op_id:
            headers["X-Operation-Id"] = op_id
        if key:
            headers["Idempotency-Key"] = key
        if deadline:
            ev.deadline_ms = time.time() * 1000 + self.deadline_ms
            headers["X-Deadline-Epoch-Ms"] = f"{ev.deadline_ms:.0f}"
        port = closed_port() if n in self.refused.get(target, set()) else self.port
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=(timeout_ms / 1000) if timeout_ms else self.timeout)
        try:
            try:
                conn.connect()
            except ConnectionRefusedError:
                ev.transport = "CONNECT_REFUSED"
                return ev
            data = json.dumps(body).encode() if body is not None else None
            conn.request(method, path, body=data, headers=headers)
            ev.request_sent = True
            if on_sent:
                on_sent()                          # the SIGKILL "in flight" crash point
            try:
                r = conn.getresponse()
                raw = r.read()
            except (socket.timeout, TimeoutError):
                ev.transport = "TIMEOUT"
                return ev
            except (ConnectionResetError, http.client.RemoteDisconnected, http.client.IncompleteRead):
                ev.transport = "RESET"
                return ev
            ev.transport = "OK"
            ev.response_received = True
            ev.status = r.status
            ev.not_executed_header = r.getheader("Not-Executed") == "true"
            ev.replayed = r.getheader("Idempotent-Replayed") == "true"
            try:
                ev.body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                ev.body = {"raw": raw.decode(errors="replace")[:200]}
            return ev
        finally:
            conn.close()
