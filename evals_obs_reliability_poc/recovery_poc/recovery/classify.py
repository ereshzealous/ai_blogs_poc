"""Evidence -> failure class + execution certainty.  Deterministic; the rules are config/recovery-matrix.toml [[certainty]].

Detection is "the call did not return 2xx".  Diagnosis is this module's output: which layer, which class, whether the
target executed, which certainty rule says so, what the tool's contract makes of it.  The FailureEvent is the
machine-actionable record the recovery policy reads, and the record an operator reads at 3 a.m.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .taxonomy import EXECUTED, LAYER, NOT_EXECUTED, UNKNOWN
from .toolclient import Evidence

# Provider error codes that mean "your arguments were wrong" rather than "the provider declined on a business rule".
ARGUMENT_CODES = {"AMOUNT_MISMATCH", "NO_SUCH_CHARGE"}


@dataclass
class FailureEvent:
    run_id: str
    step: str
    operation: str
    component: str
    failure_class: str
    layer: str
    execution_certainty: str
    certainty_rule: str
    certainty_basis: str
    attempt_id: str | None = None
    operation_id: str | None = None
    idempotency_key: str | None = None
    side_effect: str = "NONE"                   # the tool contract's effect
    request_sent: bool | None = None
    response_received: bool | None = None
    transport: str | None = None
    http_status: int | None = None
    error_code: str | None = None
    detail: str = ""
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


CERTAINTY_BASIS = {
    "C1": "the request never left the runtime",
    "C2": "connection refused: nothing was delivered",
    "C3": "the provider answered that it executed",
    "C4": "the provider documents this status as a rejection before any effect",
    "C5": "the provider shed the request before accepting it",
    "C6": "sent, and no answer came back",
    "C7": "intent recorded, no result: the worker died in flight",
    "C8": "the outcome was recorded before the interruption",
    "C9": "no intent recorded, so no dispatch",
    "C10": "the system of record, queried after the request deadline",
    "C11": "a server error after delivery says nothing about the effect",
}


def certainty(ev: Evidence, pre_execution: list[int], unknown_as_failed: bool = False) -> tuple[str, str]:
    """(certainty, rule id) for one attempt.  unknown_as_failed is the X1 mutant (a timeout treated as a failed call)."""
    if not ev.request_sent and ev.transport != "CONNECT_REFUSED":
        return NOT_EXECUTED, "C1"
    if ev.transport == "CONNECT_REFUSED":
        return NOT_EXECUTED, "C2"
    if not ev.response_received:
        return (NOT_EXECUTED, "C6") if unknown_as_failed else (UNKNOWN, "C6")
    if 200 <= (ev.status or 0) < 300:
        return EXECUTED, "C3"
    if ev.status in pre_execution or ev.status in (408, 429):
        return NOT_EXECUTED, "C4"
    if ev.status == 503 and ev.not_executed_header:
        return NOT_EXECUTED, "C5"
    return (NOT_EXECUTED, "C11") if unknown_as_failed else (UNKNOWN, "C11")


def classify_call(run_id: str, step: str, kind: str, ev: Evidence, contract: dict, *, generic: bool = False,
                  unknown_as_failed: bool = False, retry_terminal: bool = False) -> FailureEvent | None:
    """None when the call succeeded; otherwise the classified failure.  kind: model | kb | tool."""
    cert, rule = certainty(ev, contract.get("pre_execution", []), unknown_as_failed)
    if cert == EXECUTED and ev.response_received and 200 <= ev.status < 300:
        return None
    code = (ev.body or {}).get("error")
    if kind == "model":
        cls = "MODEL_RATE_LIMITED" if ev.status == 429 else "MODEL_UNAVAILABLE"
    elif kind == "kb":
        cls = "RETRIEVAL_UNAVAILABLE"
    elif ev.transport == "CONNECT_REFUSED" or (ev.status == 503 and ev.not_executed_header) or ev.status == 408:
        cls = "TOOL_UNAVAILABLE"
    elif not ev.response_received:
        cls = "RESPONSE_LOST"
    elif ev.status in (401, 403):
        cls = "AUTHORIZATION_DENIED"
    elif code in ARGUMENT_CODES:
        cls = "ARGUMENT_VALIDATION"
    elif ev.status in contract.get("pre_execution", []):
        cls = "TOOL_REJECTED"
    else:
        cls = "TOOL_SERVER_ERROR"
    if retry_terminal and cls in ("TOOL_REJECTED", "AUTHORIZATION_DENIED"):
        cls = "TOOL_UNAVAILABLE"                 # X2 mutant: a terminal refusal treated as a transient outage
    if generic:
        cls = "GENERIC_ERROR"                    # X8 mutant
    return FailureEvent(run_id=run_id, step=step, operation=ev.target, component=kind, failure_class=cls, layer=LAYER[cls],
                        execution_certainty=cert, certainty_rule=rule, certainty_basis=CERTAINTY_BASIS[rule],
                        attempt_id=ev.attempt_id, operation_id=ev.operation_id, idempotency_key=ev.idempotency_key,
                        side_effect=contract.get("effect", "NONE"), request_sent=ev.request_sent, response_received=ev.response_received,
                        transport=ev.transport, http_status=ev.status, error_code=code, evidence=ev.facts())


def gate_failure(run_id: str, step: str, operation: str, cls: str, detail: str, contract: dict | None = None,
                 generic: bool = False) -> FailureEvent:
    """A failure decided inside the runtime before dispatch (validation, selection, policy, parsing, the journal)."""
    certainty_ = EXECUTED if cls == "MODEL_OUTPUT_INVALID" else NOT_EXECUTED
    rule = "C3" if cls == "MODEL_OUTPUT_INVALID" else "C1"
    if generic:
        cls = "GENERIC_ERROR"
    return FailureEvent(run_id=run_id, step=step, operation=operation, component="runtime", failure_class=cls, layer=LAYER[cls],
                        execution_certainty=certainty_, certainty_rule=rule, certainty_basis=CERTAINTY_BASIS[rule],
                        side_effect=(contract or {}).get("effect", "NONE"), request_sent=False, detail=detail)
