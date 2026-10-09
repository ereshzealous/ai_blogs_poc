"""H8 · Deny, timeout, expiry and escalation: the scenarios run under arms A, B and C; arm C's preregistered invariants must hold."""
from hkit import check_experiment


def test_h8(tmp_path):
    check_experiment("H8", tmp_path)
