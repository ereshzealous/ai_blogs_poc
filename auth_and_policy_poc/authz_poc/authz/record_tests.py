"""Run the test suite (L1–L4) and record every test and subtest, so the Lab Console reads results instead of re-running.

Called by `python3 -m authz.verify`, which writes tests.json into the run directory. Timings are left out so the file
is deterministic: same code, same bytes.
"""

from __future__ import annotations

import io
import json
import re
import sys
import unittest
from pathlib import Path

from .world import ROOT

LAYERS = {"test_l1_policy": ("L1", "Policy unit tests"), "test_l2_invariants": ("L2", "Authorization invariants"),
          "test_l3_gateway": ("L3", "Gateway integration tests"), "test_l4_replay": ("L4", "Recorded incident replay")}


class Recorder(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.entries: list[dict] = []
        self._had_sub: set[str] = set()

    def _add(self, test, case, status, err=None):
        module, suite, name = test.id().split(".")[-3:]
        layer, layer_name = LAYERS.get(module, ("?", module))
        msg = self._exc_info_to_string(err, test).strip().splitlines()[-1] if err else ""
        doc = (test._testMethodDoc or "").strip()
        inv = re.match(r"(AUTHZ-INV-\d{2})", doc)
        self.entries.append({"layer": layer, "layer_name": layer_name, "module": module, "suite": suite, "test": name,
                             "invariant": inv.group(1) if inv else None, "case": case, "status": status, "message": msg})

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        self._had_sub.add(test.id())
        case = subtest._subDescription().strip("[]() ")
        self._add(test, case, "error" if err and not issubclass(err[0], test.failureException) else "fail" if err else "pass", err)

    def addSuccess(self, test):
        super().addSuccess(test)
        if test.id() not in self._had_sub:
            self._add(test, "", "pass")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, "", "fail", err)

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, "", "error", err)


def run_suite() -> dict:
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
    res = unittest.TextTestRunner(resultclass=Recorder, verbosity=0, stream=io.StringIO()).run(suite)
    entries = sorted(res.entries, key=lambda e: (e["layer"], e["module"], e["suite"], e["test"]))  # stable order
    import test_l1_policy  # the decision table's expected answers, recorded beside each case
    table = {name: {"action": r.action, "resource": r.resource, "environment": r.environment, "principal": r.principal,
                    "acting_for": r.acting_for, "expect": want, "expect_rule": rule} for name, r, _, want, rule in test_l1_policy.TABLE}
    for e in entries:
        if e["test"] == "test_decision_table" and e["case"] in table:
            e.update(table[e["case"]])
    layers = {}
    for layer, name in sorted(LAYERS.values()):
        es = [e for e in entries if e["layer"] == layer]
        layers[layer] = {"name": name, "tests": len({(e["suite"], e["test"]) for e in es}), "checks": len(es),
                         "passed": sum(e["status"] == "pass" for e in es), "failed": sum(e["status"] != "pass" for e in es)}
    return {"command": "python3 -m unittest discover -s tests -v", "tests": res.testsRun, "checks": len(entries),
            "passed": sum(e["status"] == "pass" for e in entries), "failed": sum(e["status"] == "fail" for e in entries),
            "errors": sum(e["status"] == "error" for e in entries), "ok": res.wasSuccessful(), "layers": layers,
            "results": entries}


def record(out: Path) -> dict:
    doc = run_suite()
    out.mkdir(parents=True, exist_ok=True)
    (out / "tests.json").write_text(json.dumps(doc, indent=2) + "\n")
    return doc
