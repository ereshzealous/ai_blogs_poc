"""Simulated identity: principal -> roles.  Stands in for an identity provider."""

from __future__ import annotations

from layered_platform.config import load


class Directory:
    def __init__(self) -> None:
        self.principals = load("principals.yaml")["principals"]

    def roles(self, principal: str) -> set[str]:
        return set(self.principals.get(principal, {}).get("roles", []))

    def exists(self, principal: str) -> bool:
        return principal in self.principals
