"""Channel adapters. Each turns its own protocol into capability requests and renders capability responses.

An adapter owns: parsing, the channel's identity claim, the channel's session reference, rendering and delivery.
It does not own: prompts, workflow steps, memory, tools, policy, approvals or model choice.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from headless_ai_platform.contracts import CapabilityError
from headless_ai_platform.gateway import CapabilityGateway
from headless_ai_platform.renderers import api

CAPABILITY = "incident.remediation"


def gateway(request: Request) -> CapabilityGateway:
    return request.app.state.gateway


def http_error(exc: CapabilityError) -> HTTPException:
    code, body = api.error(exc)
    return HTTPException(code, body["error"])
