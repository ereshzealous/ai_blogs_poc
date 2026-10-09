"""Generate proof/experiments.toml (the pae-proof/v1 checks) from proof/preregistration.toml and hitl/suite.py.

    uv run python scripts/gen_experiments.py        (then `uv run hitl freeze`, then `uv run hitl proof`)

The checks are the preregistered pass criteria, mechanically: one check per hypothesis of H1–H9, one per fixed global
assertion (arm C), one per conformance test, two for the HTTP surface.  Nothing here reads a result.
"""
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hitl.suite import TESTS  # noqa: E402

PRE = tomllib.loads((ROOT / "proof" / "preregistration.toml").read_text())
KIND = {"invariant": ("invariant", "hold"), "hypothesis": ("hypothesis", "hold"), "control": ("control", "fail")}


def q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fact_for(x: str, arm: str, metric: str) -> str:
    """'writes@H1b' → H1b.A.writes · 'm@H7a+H7b' → H7.B.m.H7a_H7b · 'm@all' → all.C.m · 'm' → H1.C.m"""
    if "@" not in metric:
        return f"{x}.{arm}.{metric}"
    name, scope = metric.split("@")
    if scope == "all":
        return f"all.{arm}.{name}"
    if "+" in scope:
        return f"{x}.{arm}.{name}.{scope.replace('+', '_')}"
    return f"{scope}.{arm}.{name}"


def main() -> None:
    L = ["# T3 · Human-in-the-Loop · experiments → checks (Production AI Engineering Proof Contract v1, pae-proof/v1)", "#",
         "# GENERATED from proof/preregistration.toml and hitl/suite.py by scripts/gen_experiments.py; frozen with it (proof/FREEZE.json).",
         "# H1–H9: one check per preregistered hypothesis (invariant: must hold · hypothesis: a prediction, FAIL = NOT SUPPORTED ·",
         "# control: predicted to break under that arm, EXPECTED_FAILURE when it does).  GA: the fixed global assertions on arm C.",
         "# CS: the arm-C conformance suite (30 regression tests).  API: the HTTP surface.", ""]
    for x in PRE["experiments"]:
        xid = "T3-R" + x["id"][1:]                       # the contract's article-scoped id; H<n> is T3-R<n>
        L += ["[[experiments]]", f"id = {q(xid)}", f"title = {q(x['id'] + ' · ' + x['title'])}", f"h = {q(x['id'])}", f"question = {q(x['question'])}", f"claim = {q(x['invariant'])}",
              f"hypothesis = {q(' '.join(h['arm'] + ': ' + h['text'] for h in x['hypotheses']))}", f"setup = {q(x['setup'])}",
              f"invariant = {q(x['invariant'])}", f"scenarios = [{', '.join(q(s['id']) for s in x['scenarios'])}]",
              'limitations = "Deterministic simulation: simulated Kubernetes, identity provider, chat channel and clock; scripted human decisions; no model."', ""]
        n: dict[str, int] = {}
        for k, h in enumerate(x["hypotheses"], 1):
            n[h["arm"]] = n.get(h["arm"], 0) + 1
            kind, expect = KIND[h["kind"]]
            L += ["[[experiments.checks]]", f"id = {q(xid + '-C' + format(k, '02d'))}", f"label = {q(x['id'] + '-' + h['arm'] + format(n[h['arm']], '02d'))}",
                  f"description = {q(x['id'] + ' · arm ' + h['arm'] + ' · ' + h['text'])}", f"kind = {q(kind)}",
                  f"arm = {q(h['arm'])}", f"fact = {q(fact_for(x['id'], h['arm'], h['metric']))}", f"op = {q(h['op'])}", f"value = {h['value']}",
                  f"expect = {q(expect)}", ""]
    L += ["[[experiments]]", 'id = "T3-R10"', 'title = "GA · Fixed global assertions (arm C)"', 'h = "GA"',
          'question = "Across every hardened scenario, does anything unsafe happen at all?"',
          'claim = "Under the revalidated protocol every global failure count is zero."',
          'hypothesis = "C: zero unauthorized executions, mutated-action bypasses, replays, duplicates, expired executions, ineligible acceptances, silent stale resumes and audit gaps."',
          'setup = "The sums over all thirty scenarios of H1–H9 under arm C; the same sums for A and B are reported as observations."',
          'invariant = "Each count is 0."', ""]
    for i, g in enumerate(PRE["global"], 1):
        L += ["[[experiments.checks]]", f"id = {q(f'T3-R10-C{i:02d}')}", f"label = {q(f'GA-{i:02d}')}", f"description = {q('GA · ' + g['metric'].replace('_', ' ') + ' = 0 under arm C')}", 'kind = "invariant"',
              'arm = "C"', f"fact = {q('global.C.' + g['metric'])}", 'op = "=="', "value = 0", ""]
    L += ["[[experiments]]", 'id = "T3-R11"', 'title = "CS · Arm C conformance suite (30 regression tests)"', 'h = "CS"',
          'question = "Does the revalidated protocol keep its routing, lifecycle, identity, duplicate, fail-closed and audit guarantees, test by test?"',
          'claim = "Every conformance test holds every assertion it makes."', 'hypothesis = "30 of 30 tests pass."',
          'setup = "hitl/suite.py: a fresh platform per test, clock at 14:02:00 UTC, the F3 incident; the gate and approval service of arm C."',
          'invariant = "held == assertions for every test."', ""]
    for n, (tid, name, cat, invs, _) in enumerate(TESTS, 1):
        L += ["[[experiments.checks]]", f"id = {q(f'T3-R11-C{n:02d}')}", f"label = {q(f'CS-{tid[-3:]}')}", f"description = {q(f'CS · {tid} · {name}')}", 'kind = "invariant"',
              f"fact = {q(f'tests.{tid}.held')}", 'op = "=="', f"ref = {q(f'tests.{tid}.assertions')}", "invariants = [" + ", ".join(q(i) for i in invs) + "]", ""]
    L += ["[[experiments]]", 'id = "T3-R12"', 'title = "API · Implementation: the HTTP surface and approval inbox"', 'h = "API"',
          'question = "Does the same boundary hold through the real HTTP API a person or a client would use?"',
          'claim = "Events, the inbox, decisions and the audit are served over HTTP, and the approver is the credential\'s principal."',
          'hypothesis = "Every call returns its expected status; exactly one rollback follows the one valid approval."',
          'setup = "uv run hitl serve, driven by urllib in-process: POST /events, GET /approvals, POST /approvals/{id}/decision, GET /audit/{id}."',
          'invariant = "Each call returns the expected status and exactly one rollback follows the one valid approval."', "",
          "[[experiments.checks]]", 'id = "T3-R12-C01"', 'label = "API-01"', 'description = "API · Every HTTP call returned its expected status"', 'kind = "implementation"',
          'fact = "api.calls_ok"', 'op = "=="', 'ref = "api.calls"', "",
          "[[experiments.checks]]", 'id = "T3-R12-C02"', 'label = "API-02"', 'description = "API · Exactly one rollback after the one valid approval"', 'kind = "implementation"',
          'fact = "api.rollbacks"', 'op = "=="', "value = 1", ""]
    (ROOT / "proof" / "experiments.toml").write_text("\n".join(L))
    print("proof/experiments.toml written")


if __name__ == "__main__":
    main()
