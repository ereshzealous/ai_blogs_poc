"""L1 · Policy unit tests: the PDP and its parts, evaluated directly, without the gateway.

    python3 -m unittest discover -s tests -v

A decision table (request → expected decision and deciding rule), the freeze case, the combining rule, condition
semantics, the evidence evaluator, the request fingerprint and the caller-facing view.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from authz.evidence import WEIGHTS, fixed  # noqa: E402
from authz.model import ALLOW, APPROVAL, CONSTRAINED, DENY  # noqa: E402
from authz.pdp import condition_holds  # noqa: E402
from authz.world import request, world  # noqa: E402

FULL, EARLY = fixed(list(WEIGHTS)), fixed(["release_correlation", "error_signature"])

# (name, request, evidence, expected decision, expected rule id or None)
TABLE = [
    ("read deployment", request("kubernetes.readDeployment", "deployment/payment-service"), FULL, ALLOW, None),
    ("read logs are redacted", request("logs.query", "logs/payment-service"), FULL, CONSTRAINED, "C2-restricted-logs"),
    ("restart pod in staging", request("kubernetes.restartPod", "pods/payment-service", "staging"), FULL, ALLOW, None),
    ("restart pod in production", request("kubernetes.restartPod", "pods/payment-service"), EARLY, CONSTRAINED, "C1-production-restart"),
    ("rollback staging", request("kubernetes.rollbackDeployment", "deployment/payment-service", "staging", to_version="v4.17.2"), EARLY, ALLOW, None),
    ("rollback production", request("kubernetes.rollbackDeployment", "deployment/payment-service", to_version="v4.17.2"), FULL, APPROVAL, "A1-production-rollback"),
    ("rollback production, weak evidence", request("kubernetes.rollbackDeployment", "deployment/payment-service", to_version="v4.17.2"), EARLY, DENY, "F2-insufficient-evidence-high-risk-write"),
    ("delete namespace", request("kubernetes.deleteNamespace", "namespace/payments-canary"), FULL, DENY, "F1-no-namespace-deletion"),
    ("not the owner", request("kubernetes.rollbackDeployment", "deployment/checkout-service", to_version="v2.9.0"), FULL, DENY, "rebac.not-owner"),
    ("no acting-for principal", request("kubernetes.restartPod", "pods/payment-service", acting_for=None), FULL, DENY, "rebac.no-principal"),
    ("read-only agent cannot restart", request("kubernetes.restartPod", "pods/payment-service", principal="release-guard-prod"), FULL, DENY, "rbac.no-grant"),
    ("cross-tenant log query", request("logs.query", "logs/payment-service", tenant="globex"), FULL, DENY, "F4-tenant-boundary"),
    ("exec is not in any role", request("kubernetes.execShell", "pods/payment-service"), FULL, DENY, "default.unknown-action"),
    ("unknown resource", request("kubernetes.readDeployment", "deployment/ledger-service"), FULL, DENY, "default.unknown-resource"),
    ("unknown environment", request("kubernetes.readDeployment", "deployment/payment-service", "prod-eu"), FULL, DENY, "default.unknown-environment"),
]


class DecisionTable(unittest.TestCase):
    def test_decision_table(self):
        for name, r, ev, expected, rule in TABLE:
            with self.subTest(name):
                overrides = {"tenants": ["acme"]} if "tenant" in r.arguments else None
                d = world(overrides, evidence=ev).pdp.evaluate(r)
                self.assertEqual(d.decision, expected, d.reason)
                if rule:
                    self.assertIn(rule, d.matched)

    def test_freeze_blocks_sev3_but_not_sev1(self):
        r = request("kubernetes.rollbackDeployment", "deployment/payment-service", time="2026-09-29T15:04:00Z", to_version="v4.17.2")
        self.assertEqual(world({"severity": "SEV-3"}, evidence=FULL).pdp.evaluate(r).decision, DENY)
        self.assertEqual(world({"severity": "SEV-1"}, evidence=FULL).pdp.evaluate(r).decision, APPROVAL)


class CombiningRule(unittest.TestCase):
    """Our gateway's fail-closed precedence: DENY > ALLOW_WITH_APPROVAL > ALLOW_WITH_CONSTRAINTS > ALLOW."""

    def rules(self, *effects):
        out = []
        for i, eff in enumerate(effects):
            r = {"id": f"T{i}-{eff}", "effect": eff, "reason": eff, "code": eff, "message": eff,
                 "when": {"action": "kubernetes.restartPod", "environment": "staging"}}
            if eff == CONSTRAINED:
                r["constraints"] = {"maxPods": 1}
            if eff == APPROVAL:
                r["constraints"] = {"approverRole": "IncidentCommander", "expiresIn": "10m"}
            out.append(r)
        return out

    def decide(self, *effects):
        gw = world(evidence=FULL)
        gw.pdp.policy = {**gw.pdp.policy, "rule": self.rules(*effects)}
        return gw.pdp.evaluate(request("kubernetes.restartPod", "pods/payment-service", "staging", pods=["a", "b"]))

    def test_precedence(self):
        self.assertEqual(self.decide().decision, ALLOW)
        self.assertEqual(self.decide(CONSTRAINED).decision, CONSTRAINED)
        self.assertEqual(self.decide(CONSTRAINED, APPROVAL).decision, APPROVAL)
        self.assertEqual(self.decide(APPROVAL, CONSTRAINED, DENY).decision, DENY)

    def test_constraints_from_several_rules_merge(self):
        d = self.decide(CONSTRAINED, APPROVAL)
        self.assertEqual(d.constraints, {"maxPods": 1, "approverRole": "IncidentCommander", "expiresIn": "10m"})


class ConditionSemantics(unittest.TestCase):
    def test_unknown_attribute_makes_a_restrictive_rule_apply(self):
        self.assertTrue(condition_holds("change_window", "freeze", {}))
        self.assertTrue(condition_holds("evidence_score.lt", 0.80, {}))

    def test_operators(self):
        attrs = {"evidence_score": 0.62, "severity": "SEV-1", "environment": "production"}
        self.assertTrue(condition_holds("evidence_score.lt", 0.80, attrs))
        self.assertFalse(condition_holds("evidence_score.gte", 0.80, attrs))
        self.assertFalse(condition_holds("severity.not_in", ["SEV-1"], attrs))
        self.assertTrue(condition_holds("environment", ["production", "staging"], attrs))


class Evidence(unittest.TestCase):
    def test_evidence_is_looked_up_only_for_high_risk_writes(self):
        gw = world(evidence=FULL)
        read = gw.pdp.evaluate(request("kubernetes.readDeployment", "deployment/payment-service"))
        rollback = gw.pdp.evaluate(request("kubernetes.rollbackDeployment", "deployment/payment-service", to_version="v4.17.2"))
        self.assertNotIn("evidence_score", read.attributes)
        self.assertEqual(rollback.attributes["evidence_score"], 0.94)
        self.assertEqual(rollback.attributes["evidence_signals"], list(WEIGHTS))

    def test_score_is_the_sum_of_observed_signal_weights(self):
        self.assertEqual(EARLY("payment-service", {}, None)[0], 0.62)
        self.assertEqual(FULL("payment-service", {}, None)[0], 0.94)


class Fingerprint(unittest.TestCase):
    def test_fingerprint_ignores_the_clock_and_covers_the_call(self):
        base = request("kubernetes.rollbackDeployment", "deployment/payment-service", to_version="v4.17.2")
        fp = base.fingerprint()
        self.assertEqual(fp, request("kubernetes.rollbackDeployment", "deployment/payment-service", time="2026-09-29T14:09:02Z",
                                     to_version="v4.17.2").fingerprint())
        for changed in (request("kubernetes.rollbackDeployment", "deployment/payment-service", to_version="v4.16.0"),
                        request("kubernetes.rollbackDeployment", "deployment/payment-service", "staging", to_version="v4.17.2"),
                        request("kubernetes.rollbackDeployment", "deployment/checkout-service", to_version="v4.17.2"),
                        request("kubernetes.rollbackDeployment", "deployment/payment-service", acting_for="checkout-team", to_version="v4.17.2"),
                        request("kubernetes.rollbackDeployment", "deployment/payment-service", context={"incident_id": "INC-9999"},
                                to_version="v4.17.2")):
            self.assertNotEqual(changed.fingerprint(), fp)


class CallerView(unittest.TestCase):
    def test_caller_view_carries_only_safe_fields(self):
        d = world(evidence=FULL).pdp.evaluate(request("kubernetes.rollbackDeployment", "deployment/checkout-service", to_version="v2.9.0"))
        view = d.public()
        self.assertLessEqual(set(view), {"decision", "code", "reason", "next", "constraints"})
        self.assertNotIn("checkout-team", str(view))
        self.assertNotIn("rebac", str(view))
        self.assertIn("sre-team does not own checkout-service", d.reason)  # the audit reason keeps the detail


if __name__ == "__main__":
    unittest.main()
