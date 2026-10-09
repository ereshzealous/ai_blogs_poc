"""H2 · Mutation after approval: the scenarios run under arms A, B and C; arm C's preregistered invariants must hold."""
from hkit import check_experiment


def test_h2(tmp_path):
    check_experiment("H2", tmp_path)
