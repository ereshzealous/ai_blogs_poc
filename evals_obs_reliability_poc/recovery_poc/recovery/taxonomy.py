"""The failure taxonomy: failure classes, the layer each originates in, execution certainty and recovery actions.

"The agent failed" is not one of these.  Every failure the runtime records is one class from this list, with the
layer it came from and an execution certainty, because the recovery for each is different.
"""

from __future__ import annotations

# ---- execution certainty: did the target system execute this operation attempt? ---------------------------------------
NOT_EXECUTED = "NOT_EXECUTED"
EXECUTED = "EXECUTED"
UNKNOWN = "UNKNOWN"
CERTAINTIES = (NOT_EXECUTED, EXECUTED, UNKNOWN)

# ---- recovery actions -------------------------------------------------------------------------------------------------
ACTIONS = ("CONTINUE", "RETRY", "REPAIR", "RESUME", "RECONCILE", "FALLBACK", "COMPENSATE", "ESCALATE", "ABORT")

# ---- failure classes and the layer each originates in ----------------------------------------------------------------
LAYER = {
    "RETRIEVAL_UNAVAILABLE": "retrieval",
    "MODEL_UNAVAILABLE": "model invocation",
    "MODEL_RATE_LIMITED": "model invocation",
    "MODEL_OUTPUT_INVALID": "structured-output parsing",
    "TOOL_SELECTION_INVALID": "tool selection",
    "ARGUMENT_VALIDATION": "tool arguments",
    "AUTHORIZATION_DENIED": "authorization / policy",
    "TOOL_UNAVAILABLE": "tool transport",
    "TOOL_REJECTED": "tool execution",
    "TOOL_SERVER_ERROR": "tool execution",
    "RESPONSE_LOST": "network response",
    "RECONCILE_FAILED": "downstream dependency",
    "DUPLICATE_EFFECT": "external side effect",
    "CHECKPOINT_WRITE_FAILED": "workflow persistence",
    "PROCESS_INTERRUPTED": "orchestrator",
    "STATE_INCONSISTENT": "workflow state",
    "GENERIC_ERROR": "unknown",            # only the X8 mutant produces this
}
# Not failures, but decision points the matrix also covers.
DECISION_CLASSES = ("NONE", "RECONCILED")
FAILURE_CLASSES = tuple(LAYER)
TERMINAL_STATUSES = ("COMPLETED", "DENIED", "REQUIRES_HUMAN", "FAILED")
