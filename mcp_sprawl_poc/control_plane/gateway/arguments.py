"""Argument checks the gateway runs before policy.

Arguments are validated against the tool's published input schema (JSON Schema 2020-12, as the servers
do) and then put in one canonical form: schema defaults filled in for omitted top-level properties, keys
sorted, and a private copy parsed back from that JSON. Policy, approval and the MCP call all use that copy,
so an approval covers exactly what runs. Nothing is repaired: an invalid value is rejected, never guessed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

MAX_PROBLEMS = 3


def canonical_json(arguments: Any) -> str:
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class CheckedArguments:
    arguments: dict[str, Any]  # the canonical copy when valid; what the caller sent otherwise
    problems: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.problems

    @property
    def message(self) -> str:
        return "Invalid arguments: " + "; ".join(self.problems)


class ArgumentChecker:
    """One compiled validator per tool; `clear()` when the tool list is refreshed."""

    def __init__(self) -> None:
        self._validators: dict[str, Draft202012Validator] = {}

    def clear(self) -> None:
        self._validators.clear()

    def check(self, key: str, schema: dict[str, Any], arguments: dict[str, Any]) -> CheckedArguments:
        if not isinstance(arguments, dict):
            return CheckedArguments(arguments, ("arguments must be a JSON object",))
        defaults = {name: prop["default"] for name, prop in schema.get("properties", {}).items()
                    if isinstance(prop, dict) and "default" in prop and name not in arguments}
        filled = {**arguments, **defaults}
        validator = self._validators.get(key)
        if validator is None:
            validator = self._validators[key] = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(filled), key=lambda e: (list(map(str, e.path)), e.message))
        if errors:
            return CheckedArguments(arguments, tuple(e.message for e in errors[:MAX_PROBLEMS]))
        return CheckedArguments(json.loads(canonical_json(filled)), ())
