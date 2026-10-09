"""Identifiers, and the scorer's verdict rules."""
from lineage.common import action_id, attempt_id, execution_id
from lineage.investigate import verdict


def test_identifiers_are_stable_and_distinct():
    x = execution_id("e01-success", "INC-4471")
    assert x == execution_id("e01-success", "INC-4471") != execution_id("e02-tool-failure", "INC-4471")
    a = action_id(x, "tool", "sha256:abc")
    assert a != action_id(x, "tool", "sha256:abd")
    assert attempt_id(a, 1) != attempt_id(a, 2) and attempt_id(a, 2).startswith(a)


def test_verdicts():
    t = {"model": "m", "prompt_template": "p@17"}
    assert verdict({"model": "m", "prompt_template": "p@17"}, t) == "CORRECT"
    assert verdict({"model": "m", "prompt_template": None}, t) == "INCOMPLETE"
    assert verdict({"model": "x", "prompt_template": None}, t) == "WRONG"
    assert verdict(None, t) == "UNANSWERABLE"
    assert verdict(None, None) == "CORRECT"
    assert verdict("AMBIGUOUS", 2) == "AMBIGUOUS"
    assert verdict(True, False) == "WRONG"
