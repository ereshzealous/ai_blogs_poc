"""H6 · Identity or policy change during the pause: the scenarios run under arms A, B and C; arm C's preregistered invariants must hold."""
from hkit import check_experiment


def test_h6(tmp_path):
    check_experiment("H6", tmp_path)
