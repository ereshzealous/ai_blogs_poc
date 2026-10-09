"""The frozen scenario is internally consistent, and ground truth stays out of the system under test."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "governed_memory"


def test_every_record_has_a_label(scenario):
    ids = {r.id for r in scenario.all_records()}
    assert ids == set(scenario.labels)


def test_relations_point_at_existing_records(scenario):
    ids = {r.id for r in scenario.all_records()}
    for r in scenario.all_records():
        assert set(r.contradicts) <= ids, r.id
        assert r.superseded_by is None or r.superseded_by in ids, r.id


def test_experiment_corpora_are_the_same_for_both_arms(scenario):
    for exp in scenario.experiments:
        assert [r.id for r in scenario.corpus(exp)] == [r.id for r in scenario.corpus(exp)]
        assert len({r.id for r in scenario.corpus(exp)}) == len(scenario.corpus(exp))


def test_injections_belong_to_their_experiment(scenario):
    assert "inj-expired-workaround" in {r.id for r in scenario.corpus("M2")}
    assert "inj-expired-workaround" not in {r.id for r in scenario.corpus("M1")}
    m0 = {r.id for r in scenario.corpus("M0")}
    assert {"inj-globex-kubectl", "inj-poisoned-assertion", "inj-approval-claim"} <= m0


def test_system_under_test_never_imports_labels_or_experiments():
    for py in SRC.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                assert not any(m.startswith("s1_experiments") for m in mods), py
        assert "labels.yaml" not in py.read_text(), py
