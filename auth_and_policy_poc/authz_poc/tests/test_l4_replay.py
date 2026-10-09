"""L4 · Recorded incident replay and regression tests.

The canonical incident is re-run into a fresh directory and compared, byte for byte, with the recorded run
(runs/2026-09-29-recorded). The published facts are then checked against the generated artifacts themselves: every
expected value below is read from the run's files or derived from the decision log, never restated by hand.

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from authz.audit import AuditLog  # noqa: E402
from authz.run import RUN_ID, run  # noqa: E402
from authz.world import ROOT, scenario  # noqa: E402

RECORDED = ROOT / "runs" / RUN_ID
OUTPUTS = ["decisions.jsonl", "timeline.json", "timeline.md", "sweep.json", "sweep.md", "invariants.json",
           "expectations.json", "receipt.json", "transcript.txt", "facts.json"]


def load(d: Path, name: str):
    p = d / name
    return [json.loads(line) for line in p.read_text().splitlines()] if name.endswith(".jsonl") else json.loads(p.read_text())


class Replay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fresh = Path(cls.tmp.name) / RUN_ID
        run(cls.fresh)
        cls.log = load(cls.fresh, "decisions.jsonl")
        cls.decisions = [r["record"] for r in cls.log if r["kind"] == "policy.decision"]
        cls.facts = load(cls.fresh, "facts.json")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def first(self, action, resource, environment):
        return [d for d in self.decisions if (d["action"], d["resource"], d["environment"]) == (action, resource, environment)
                and not d["recheck_of"]]

    # -- determinism -------------------------------------------------------------------------------------------------
    def test_replay_is_byte_identical_to_the_recorded_run(self):
        for name in OUTPUTS:
            with self.subTest(name):
                self.assertEqual((self.fresh / name).read_bytes(), (RECORDED / name).read_bytes(),
                                 f"{name} differs from the recorded run: re-record with python3 -m authz.run")

    def test_recorded_chain_verifies_from_the_file(self):
        log = AuditLog()
        log.records = load(RECORDED, "decisions.jsonl")
        self.assertTrue(log.verify())

    # -- the published story, read from the artifacts -----------------------------------------------------------------
    def test_one_identity_many_answers(self):
        scn = scenario()
        self.assertEqual({(d["principal"], d["acting_for"]) for d in self.decisions},
                         {(scn["agent"]["principal"], scn["agent"]["acting_for"])})
        kinds = {d["decision"] for d in self.decisions if not d["recheck_of"]}
        self.assertEqual(kinds, set(self.facts["decisions_by_type"]))
        self.assertEqual(len(kinds), 4)

    def test_namespace_deletion_is_denied_and_nothing_is_deleted(self):
        (d,) = self.first("kubernetes.deleteNamespace", "namespace/payments-canary", "production")
        self.assertEqual(d["decision"], "DENY")
        self.assertIn("payments-canary", self.facts["namespaces_after_run"])

    def test_checkout_rollback_is_denied_for_ownership(self):
        (d,) = self.first("kubernetes.rollbackDeployment", "deployment/checkout-service", "production")
        self.assertEqual(d["decision"], "DENY")
        self.assertIn("rebac.not-owner", d["matched_rules"])

    def test_staging_rollback_is_allowed(self):
        (d,) = self.first("kubernetes.rollbackDeployment", "deployment/payment-service", "staging")
        self.assertEqual(d["decision"], "ALLOW")

    def test_same_production_rollback_denied_then_approvable_on_evidence(self):
        weak, strong = self.first("kubernetes.rollbackDeployment", "deployment/payment-service", "production")
        self.assertEqual((weak["decision"], strong["decision"]), ("DENY", "ALLOW_WITH_APPROVAL"))
        self.assertEqual(weak["request_fingerprint"], strong["request_fingerprint"])
        attempts = self.facts["production_rollback_attempts"]
        self.assertEqual([a["evidence"] for a in attempts], [weak["attributes"]["evidence_score"], strong["attributes"]["evidence_score"]])
        self.assertLess(weak["attributes"]["evidence_score"], 0.80)
        self.assertGreaterEqual(strong["attributes"]["evidence_score"], 0.80)
        self.assertEqual(weak["attribute_sources"]["evidence_score"], "evidence evaluator")

    def test_self_approval_refused_then_executed_after_recheck(self):
        rejected = [r for r in self.log if r["kind"] == "approval.rejected"]
        granted = [r for r in self.log if r["kind"] == "approval.granted"]
        self.assertEqual([r["record"]["approver"] for r in rejected], [scenario()["agent"]["principal"]])
        self.assertEqual(len(granted), 1)
        recheck = [d for d in self.decisions if d["recheck_of"]]
        self.assertEqual(len(recheck), 1)
        executed = [r["record"] for r in self.log if r["kind"] == "tool.executed" and r["record"]["decision_id"] == recheck[0]["decision_id"]]
        self.assertEqual(executed[0]["approved_by"], granted[0]["record"]["approver"])
        self.assertEqual(executed[0]["output"]["rolled_back_to"], self.facts["payment_service_production_version"])
        self.assertEqual(executed[0]["output"]["rolled_back_to"], recheck[0]["arguments"]["to_version"])

    def test_every_expected_outcome_holds(self):
        exp = load(self.fresh, "expectations.json")
        self.assertEqual(exp["passed"], exp["checks"])

    def test_facts_are_derived_from_the_log(self):
        first_pass = [d for d in self.decisions if not d["recheck_of"]]
        self.assertEqual(self.facts["decisions_total"], len(self.decisions))
        self.assertEqual(self.facts["tool_calls_proposed"], len(first_pass))
        self.assertEqual(self.facts["executed"], sum(r["kind"] == "tool.executed" for r in self.log))
        self.assertEqual(self.facts["credentials_issued"], self.facts["executed"])
        self.assertEqual(self.facts["audit_records"], len(self.log))
        self.assertEqual(self.facts["invariants_passed"], self.facts["invariants_total"])
        self.assertEqual(self.facts["invariants_total"], 14)

    def test_receipt_is_the_log(self):
        rc = load(self.fresh, "receipt.json")
        by_seq = {r["seq"]: r for r in self.log}
        for r in rc["records"]:
            self.assertEqual(r, by_seq[r["seq"]])
        rec = rc["reconstruction"]
        self.assertEqual(rec["decision"], "ALLOW_WITH_APPROVAL")
        self.assertEqual(rec["recheck"]["decision"], "ALLOW_WITH_APPROVAL")
        self.assertTrue(rec["delegation_chain"] and rec["execution"]["credential"]["id"].startswith("cred-"))


if __name__ == "__main__":
    unittest.main()
