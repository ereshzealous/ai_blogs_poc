"""The headless capability contract, version 1.0.

A channel sends a `CapabilityRequest` and receives a `CapabilityResponse`. Neither holds HTML, Slack blocks or
terminal text: the contract says what happened, what state exists and what can be done next. Renderers decide how it
looks.
"""

from headless_ai_platform.contracts.errors import CapabilityError, ErrorCode
from headless_ai_platform.contracts.request import Actor, CapabilityRequest, ChannelContext, Operation
from headless_ai_platform.contracts.response import (ActionType, AvailableAction, CapabilityResponse, CapabilityState,
                                                     RecommendedAction, ResolvedActor, Status)

__all__ = ["Actor", "ActionType", "AvailableAction", "CapabilityError", "CapabilityRequest", "CapabilityResponse",
           "CapabilityState", "ChannelContext", "ErrorCode", "Operation", "RecommendedAction", "ResolvedActor", "Status"]
