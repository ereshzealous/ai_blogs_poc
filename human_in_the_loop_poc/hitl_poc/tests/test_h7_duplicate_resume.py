"""H7 · Duplicate callback and concurrent resume: the scenarios run under arms A, B and C; arm C's preregistered invariants must hold."""
from hkit import check_experiment


def test_h7(tmp_path):
    check_experiment("H7", tmp_path)
