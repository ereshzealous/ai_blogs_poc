"""REST: the contract itself as JSON, and the HTTP status for contract errors."""

from __future__ import annotations

from typing import Any

from headless_ai_platform.contracts import CapabilityError, CapabilityResponse, ErrorCode, Status

HTTP = {ErrorCode.INVALID_REQUEST: 422, ErrorCode.UNSUPPORTED_VERSION: 400, ErrorCode.UNKNOWN_CAPABILITY: 404,
        ErrorCode.UNKNOWN_IDENTITY: 401, ErrorCode.FORBIDDEN: 403, ErrorCode.NOT_FOUND: 404, ErrorCode.CONFLICT: 409}


def render(r: CapabilityResponse) -> dict[str, Any]:
    body = r.model_dump(mode="json")
    body["links"] = {"self": f"/v1/capabilities/{r.capability}/workflows/{r.workflow_id}",
                     "actions": f"/v1/capabilities/{r.capability}/workflows/{r.workflow_id}/actions"}
    return body


def status_code(r: CapabilityResponse, created: bool = False) -> int:
    if created:
        return 202 if r.status is Status.RUNNING else 201
    return 200


def error(exc: CapabilityError) -> tuple[int, dict[str, Any]]:
    return HTTP[exc.code], {"error": exc.to_dict()}
