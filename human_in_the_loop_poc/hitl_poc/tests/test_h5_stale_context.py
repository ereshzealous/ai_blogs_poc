"""H5 · Stale world state after a 37-minute pause: the scenarios run under arms A, B and C; arm C's preregistered invariants must hold."""
from hkit import check_experiment


def test_h5(tmp_path):
    check_experiment("H5", tmp_path)
