"""Policy decision point (prod-change-policy).  Pure, ordered, fail-closed.

    tier(capability) → decision        read/analyze/recommend/low_write → ALLOW · high_write → REQUIRE_APPROVAL ·
                                       prohibited → DENY · unknown capability → DENY
    evaluation error                   → DENY with rule "P0-fail-closed" (never ALLOW by default)
    required_approvals(action)         1, or 2 for a target the version lists under approval.two_person

Approval never changes a decision: a DENY stays a DENY whatever a human decides later.  Every evaluation has a
deterministic decision id, so an approval can name the exact policy decision it answered.
"""

from __future__ import annotations

from dataclasses import dataclass

from hitl.base import load, short_id


class PolicyUnavailable(Exception):
    pass


@dataclass
class Decision:
    decision: str            # ALLOW | DENY | REQUIRE_APPROVAL
    rule: str
    tier: str
    reason: str
    required_role: str | None = None
    required_approvals: int = 0
    decision_id: str = ""


class PolicyEngine:
    def __init__(self, file: str = "policy.yaml") -> None:
        self.capabilities: dict[str, dict] = load("capabilities.yaml")["capabilities"]
        self.available = True                     # tests switch the PDP off to prove fail-closed behaviour
        self.use(file)

    def use(self, file: str) -> None:
        """Load a policy version (the scenarios that change policy during a pause switch v7 → v8 with this)."""
        cfg = load(file)
        self.file = file
        self.policy_id: str = cfg["policy_id"]
        self.version: str = str(cfg["version"])
        self.tiers: dict[str, dict] = cfg["tiers"]
        self.approval: dict = cfg["approval"]

    def tier(self, capability: str) -> str | None:
        c = self.capabilities.get(capability)
        return c["tier"] if c else None

    def required_approvals(self, capability: str, service: str | None = None, environment: str | None = None) -> int:
        for r in self.approval.get("two_person", []):
            if (r.get("capability"), r.get("service"), r.get("environment")) == (capability, service, environment):
                return 2
        return int(self.approval.get("required_approvals", 1))

    def _decide(self, capability: str, service: str | None, environment: str | None) -> Decision:
        if not self.available:
            raise PolicyUnavailable("policy decision point unreachable")
        tier = self.tier(capability)
        if tier is None:
            return Decision("DENY", "P1-unregistered", "unknown", "not a registered capability")
        d = self.tiers[tier]["decision"]
        if d == "REQUIRE_APPROVAL":
            n = self.required_approvals(capability, service, environment)
            why = "high-risk production write: a production approver must decide this exact action"
            return Decision(d, "P3-high-risk-write" if n == 1 else "P3b-two-person", tier,
                            why if n == 1 else why.replace("a production approver", "two distinct production approvers"),
                            self.approval["required_role"], n)
        if d == "DENY":
            return Decision(d, "P2-prohibited", tier, "prohibited for automated execution; no approval can permit it")
        return Decision(d, f"P4-{tier}", tier, f"{tier} capability: automatic")

    def evaluate(self, capability: str, service: str | None = None, environment: str | None = None) -> Decision:
        """Fail closed: any failure to decide is a DENY."""
        try:
            d = self._decide(capability, service, environment)
        except Exception as e:  # noqa: BLE001
            d = Decision("DENY", "P0-fail-closed", self.tier(capability) or "unknown", f"policy evaluation failed: {e}")
        d.decision_id = short_id("pd", self.policy_id, self.version, capability, service, environment, d.decision, d.rule)
        return d

    def ref(self) -> dict[str, str]:
        return {"policy_id": self.policy_id, "version": self.version}
