"""H3 · Approval replay: the scenarios run under arms A, B and C; arm C's preregistered invariants must hold."""
from hkit import check_experiment


def test_h3(tmp_path):
    check_experiment("H3", tmp_path)
