"""Contract errors. Channels map the code to their own form (HTTP status, ephemeral message, exit code)."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"          # the request does not match the contract
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"  # schema_version or capability version the platform does not serve
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    UNKNOWN_IDENTITY = "UNKNOWN_IDENTITY"        # the channel identity maps to no enterprise principal
    FORBIDDEN = "FORBIDDEN"                      # the principal lacks the role the action requires
    NOT_FOUND = "NOT_FOUND"                      # no such workflow
    CONFLICT = "CONFLICT"                        # the action is not available in the workflow's current state


class CapabilityError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}
