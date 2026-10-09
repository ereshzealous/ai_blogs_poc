"""The trusted capability + MCP registry (F1 Tool Sprawl). Two jobs:

  resolve(tool, arm)      -> is this tool allowed to be resolved at all? (I-CAP)
  metadata(tool, arm)     -> which description does the MODEL see, and is the live metadata still the pinned one? (I-META)

In arm C only allowlisted tools resolve, the model is shown registry-owned descriptions, and a tool whose live metadata
hash differs from the pin is quarantined. In arm A every tool resolves and the model sees server-provided descriptions.
"""
from __future__ import annotations

from dataclasses import dataclass

from redteam.base import Arm, Decision, GateEvent, load_yaml


@dataclass
class Resolution:
    tool: str
    event: GateEvent
    description: str          # what the model is allowed to read for this tool
    resolved: bool


class Registry:
    def __init__(self) -> None:
        cfg = load_yaml("registry.yaml")
        self.allowlist: set[str] = set(cfg["allowlist"])
        self.servers = cfg["mcp_servers"]
        # pinned (registry-owned) metadata per qualified tool
        self._pins: dict[str, dict] = {}
        for sid, s in self.servers.items():
            for tool, meta in (s.get("tools") or {}).items():
                self._pins[tool] = {"server": sid, "trusted": s["trusted"], **meta}

    def _live_metadata_hash(self, tool: str, server_claimed_hash: str | None) -> str | None:
        """What the server reports on this tools/list. A rug-pull sends a hash different from the pin."""
        return server_claimed_hash or (self._pins.get(tool, {}).get("metadata_hash"))

    def resolve(self, tool: str, arm: Arm, *, server_metadata_hash: str | None = None,
                server_description: str | None = None) -> Resolution:
        pin = self._pins.get(tool)

        if arm is Arm.A:
            # Vulnerable toy: anything the model names resolves, and it reads the server's own description verbatim.
            return Resolution(tool, GateEvent("registry", Decision.ALLOW, "no allowlist (toy)"),
                              server_description or (pin or {}).get("registry_description", ""), True)

        if arm is Arm.B:
            # Same reachability as A; the guard sits elsewhere (classifier). Registry does not constrain resolution.
            return Resolution(tool, GateEvent("registry", Decision.ALLOW, "no allowlist (guard arm)"),
                              server_description or (pin or {}).get("registry_description", ""), True)

        # arm C
        if tool not in self.allowlist:
            return Resolution(tool, GateEvent("registry", Decision.UNRESOLVED,
                              "not in agent allowlist (least privilege)", {"tool": tool}), "", False)
        if pin is not None:
            if not pin["trusted"]:
                return Resolution(tool, GateEvent("registry", Decision.QUARANTINE,
                                  "MCP server connected but not registered (connectivity != trust)",
                                  {"server": pin["server"]}), "", False)
            live = self._live_metadata_hash(tool, server_metadata_hash)
            if live != pin["metadata_hash"]:
                return Resolution(tool, GateEvent("registry", Decision.QUARANTINE,
                                  "MCP tool metadata changed since registration (rug-pull): re-approval required",
                                  {"pinned": pin["metadata_hash"], "live": live}), "", False)
            # Trusted + pinned: the model sees the REGISTRY description, never the server-provided one.
            return Resolution(tool, GateEvent("registry", Decision.ALLOW, "allowlisted; MCP metadata pinned",
                              {"server": pin["server"]}), pin["registry_description"], True)
        # a first-party (non-MCP) allowlisted tool
        return Resolution(tool, GateEvent("registry", Decision.ALLOW, "allowlisted first-party tool"), "", True)
