"""L3 · Gateway integration tests: the real enforcement path, end to end.

    agent request → gateway (PEP) → policy (PDP + PIP) → constraint / approval / denial → credential → tool → audit

Every simulated tool counts the effects it performed, so "never executed" is observed at the tool, not assumed.

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from authz.broker import CredentialError  # noqa: E402
from authz.evidence import WEIGHTS, fixed  # noqa: E402
from authz.model import ALLOW, APPROVAL, DENY, Decision  # noqa: E402
from authz.world import request, world  # noqa: E402

FULL = fixed(list(WEIGHTS))
EARLY = fixed(["release_correlation", "error_signature"])
LATER = "2026-09-29T14:09:00Z"
ROLLBACK = ("kubernetes.rollbackDeployment", "deployment/payment-service")


def effects(gw) -> int:
    return sum(t.calls for a, t in gw.tools.items() if not a.startswith("_"))


def records(gw, kind):
    return [r["record"] for r in gw.audit.records if r["kind"] == kind]


class DeniedCallsNeverExecute(unittest.TestCase):
    def test_denied_calls_never_reach_a_tool(self):
        cases = {
            "delete namespace": (request("kubernetes.deleteNamespace", "namespace/payments-canary", namespace="payments-canary"), FULL),
            "rollback a service sre-team does not own": (request(*ROLLBACK[:1], "deployment/checkout-service", to_version="v2.9.0"), FULL),
            "production rollback on weak evidence": (request(*ROLLBACK, to_version="v4.17.2"), EARLY),
            "write without an acting-for principal": (request("kubernetes.restartPod", "pods/payment-service", acting_for=None,
                                                              pods=["payment-service-7f9c-1"]), FULL),
            "exec (no role grants it)": (request("kubernetes.execShell", "pods/payment-service"), FULL),
        }
        for name, (req, ev) in cases.items():
            with self.subTest(name):
                gw = world(evidence=ev)
                res = gw.invoke(req)
                self.assertEqual(res["status"], "denied")
                self.assertEqual(effects(gw), 0)
                self.assertEqual(records(gw, "tool.executed"), [])
                self.assertEqual(gw.broker.issued, [])  # no credential was ever minted
                self.assertEqual(records(gw, "policy.decision")[0]["decision"], DENY)  # and the denial is on the record
        gw = world(evidence=FULL)
        gw.invoke(cases["delete namespace"][0])
        self.assertIn("payments-canary", gw.tools["_k8s"].namespaces)


class ConstraintsAreEnforcedByTheGateway(unittest.TestCase):
    def test_restart_is_reshaped_to_one_pod(self):
        gw = world(evidence=FULL)
        pods = ["payment-service-7f9c-1", "payment-service-7f9c-2", "payment-service-7f9c-3"]
        res = gw.invoke(request("kubernetes.restartPod", "pods/payment-service", pods=pods))
        self.assertEqual(res["status"], "executed")
        self.assertEqual(gw.tools["_k8s"].restarted, pods[:1])
        self.assertEqual(res["constraints_applied"], ["maxPods=1 (requested 3)"])

    def test_restricted_logs_come_back_redacted(self):
        gw = world(evidence=FULL)
        out = gw.invoke(request("logs.query", "logs/payment-service", window="15m"))["output"]
        text = "\n".join(out["lines"])
        self.assertNotRegex(text, r"card_number=\d")
        self.assertNotRegex(text, r"email=[^\[]")


class ApprovalRequiredCallsWait(unittest.TestCase):
    def test_nothing_executes_before_approval(self):
        gw = world(evidence=FULL)
        res = gw.invoke(request(*ROLLBACK, to_version="v4.17.2"))
        k8s = gw.tools["_k8s"]
        self.assertEqual(res["status"], "pending_approval")
        self.assertEqual(effects(gw), 0)
        self.assertEqual(k8s.deployments[("payment-service", "production")]["version"], "v4.18.0")
        refused = gw.execute_approved(res["approval_id"], request(*ROLLBACK, time=LATER, to_version="v4.17.2"))
        self.assertEqual(refused["reason"], "approval not granted")
        gw.approve(res["approval_id"], "ic.dev", "2026-09-29T14:08:50Z")
        done = gw.execute_approved(res["approval_id"], request(*ROLLBACK, time=LATER, to_version="v4.17.2"))
        self.assertEqual(done["status"], "executed")
        self.assertEqual(k8s.deployments[("payment-service", "production")]["version"], "v4.17.2")
        self.assertEqual(gw.tools["kubernetes.rollbackDeployment"].calls, 1)

    def test_stale_authorization_is_rechecked(self):
        gw = world(evidence=FULL)
        apr = gw.invoke(request(*ROLLBACK, to_version="v4.17.2"))["approval_id"]
        gw.approve(apr, "ic.dev", "2026-09-29T14:08:50Z")
        gw.pdp.pip.incidents["INC-4471"]["state"] = "resolved"
        res = gw.execute_approved(apr, request(*ROLLBACK, time=LATER, to_version="v4.17.2"))
        self.assertEqual(res["status"], "denied")
        self.assertEqual(effects(gw), 0)
        recheck = [r for r in records(gw, "policy.decision") if r["recheck_of"]]
        self.assertEqual(len(recheck), 1)
        self.assertEqual(recheck[0]["decision"], DENY)


class EveryExecutionLeavesAReceipt(unittest.TestCase):
    def test_execution_records_link_decision_credential_and_approval(self):
        gw = world(evidence=FULL)
        gw.invoke(request("kubernetes.readDeployment", "deployment/payment-service"))
        apr = gw.invoke(request(*ROLLBACK, to_version="v4.17.2"))["approval_id"]
        gw.approve(apr, "ic.dev", "2026-09-29T14:08:50Z")
        gw.execute_approved(apr, request(*ROLLBACK, time=LATER, to_version="v4.17.2"))
        decisions = {r["decision_id"]: r for r in records(gw, "policy.decision")}
        executed = records(gw, "tool.executed")
        self.assertEqual(len(executed), 2)
        for x in executed:
            self.assertIn(x["decision_id"], decisions)
            self.assertIn(decisions[x["decision_id"]]["decision"], (ALLOW, APPROVAL))
            self.assertTrue(x["credential"]["id"].startswith("cred-"))
        self.assertEqual(executed[1]["approved_by"], "ic.dev")
        self.assertTrue(gw.audit.verify())


class RuntimeCannotBypassTheGateway(unittest.TestCase):
    """What the POC can model of non-bypassability: tools redeem only broker credentials minted for one exact call."""

    def setUp(self):
        self.gw = world(evidence=FULL)
        self.k8s = self.gw.tools["_k8s"]
        self.tool = self.gw.tools["kubernetes.rollbackDeployment"]
        self.call = dict(resource="deployment/payment-service", environment="production", now=LATER, to_version="v4.17.2")

    def assertRefused(self, **kw):
        with self.assertRaises(CredentialError):
            self.tool(**{**self.call, **kw})
        self.assertEqual(self.k8s.deployments[("payment-service", "production")]["version"], "v4.18.0")
        self.assertEqual(self.tool.calls, 0)

    def permitting(self):
        d = self.gw.pdp.evaluate(request(*ROLLBACK, env="staging", to_version="v4.17.2"))
        self.assertEqual(d.decision, ALLOW)
        return d

    def test_no_credential(self):
        self.assertRefused()

    def test_forged_credential(self):
        token = self.gw.broker.issue(self.permitting(), *ROLLBACK, "production", {"to_version": "v4.17.2"}, LATER)
        self.assertRefused(credential={**token, "sig": "0" * 16})

    def test_credential_for_another_call(self):
        token = self.gw.broker.issue(self.permitting(), *ROLLBACK, "staging", {"to_version": "v4.17.2"}, LATER)
        self.assertRefused(credential=token)  # issued for staging, presented for production

    def test_expired_credential(self):
        token = self.gw.broker.issue(self.permitting(), *ROLLBACK, "production", {"to_version": "v4.17.2"}, "2026-09-29T14:07:00Z")
        self.assertRefused(credential=token)

    def test_credential_is_single_use(self):
        d = self.permitting()
        token = self.gw.broker.issue(d, *ROLLBACK, "staging", {"to_version": "v4.17.2"}, LATER)
        call = {**self.call, "environment": "staging", "credential": token}
        self.tool(**call)
        with self.assertRaises(CredentialError):
            self.tool(**call)

    def test_broker_refuses_without_a_permitting_decision(self):
        deny = self.gw.pdp.evaluate(request("kubernetes.deleteNamespace", "namespace/payments-canary"))
        pending = self.gw.pdp.evaluate(request(*ROLLBACK, to_version="v4.17.2"))
        self.assertEqual((deny.decision, pending.decision), (DENY, APPROVAL))
        with self.assertRaises(CredentialError):
            self.gw.broker.issue(deny, "kubernetes.deleteNamespace", "namespace/payments-canary", "production", {}, LATER)
        with self.assertRaises(CredentialError):
            self.gw.broker.issue(pending, *ROLLBACK, "production", {"to_version": "v4.17.2"}, LATER)  # approval not granted


class PolicyFailureFailsClosed(unittest.TestCase):
    def test_pdp_unavailable(self):
        gw = world(evidence=FULL)

        def down(_req):
            raise ConnectionError("policy engine unreachable")
        gw.pdp.evaluate = down
        res = gw.invoke(request("kubernetes.readDeployment", "deployment/payment-service"))
        self.assertEqual((res["status"], res["code"]), ("denied", "POLICY_UNAVAILABLE"))
        self.assertEqual(effects(gw), 0)
        self.assertEqual(records(gw, "policy.decision")[0]["matched_rules"], ["gateway.pdp-unavailable"])

    def test_invalid_policy_response(self):
        gw = world(evidence=FULL)
        gw.pdp.evaluate = lambda req: Decision("MAYBE", ["?"], "?", "?", None, {}, "x", [], [], {})
        res = gw.invoke(request("kubernetes.readDeployment", "deployment/payment-service"))
        self.assertEqual((res["status"], res["code"]), ("denied", "POLICY_UNAVAILABLE"))
        self.assertEqual(effects(gw), 0)


class CallerFacingDenials(unittest.TestCase):
    def test_denial_tells_the_agent_what_to_do_not_how_policy_works(self):
        gw = world(evidence=FULL)
        res = gw.invoke(request(*ROLLBACK[:1], "deployment/checkout-service", to_version="v2.9.0"))
        self.assertLessEqual(set(res), {"status", "decision", "code", "reason", "next"})
        for leak in ("sre-team", "checkout-team", "rebac", "owns", "F2", "evidence"):
            self.assertNotIn(leak, str(res))
        audit = records(gw, "policy.decision")[0]
        self.assertIn("sre-team does not own checkout-service", audit["reason"])  # the auditor sees the detail


if __name__ == "__main__":
    unittest.main()
