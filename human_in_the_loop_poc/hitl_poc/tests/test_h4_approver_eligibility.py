"""H4 · Approver eligibility and separation of duties: the scenarios run under arms A, B and C; arm C's preregistered invariants must hold."""
from hkit import check_experiment


def test_h4(tmp_path):
    check_experiment("H4", tmp_path)
