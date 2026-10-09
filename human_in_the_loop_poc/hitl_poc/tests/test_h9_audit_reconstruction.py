"""H9 · Audit reconstruction: the scenarios run under arms A, B and C; arm C's preregistered invariants must hold."""
from hkit import check_experiment


def test_h9(tmp_path):
    check_experiment("H9", tmp_path)
