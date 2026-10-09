"""H1 · Exact action binding: the scenarios run under arms A, B and C; arm C's preregistered invariants must hold."""
from hkit import check_experiment


def test_h1(tmp_path):
    check_experiment("H1", tmp_path)
