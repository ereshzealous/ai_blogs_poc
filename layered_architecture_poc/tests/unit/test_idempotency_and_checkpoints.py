import os

import pytest

from layered_platform.runtime.checkpoints import CheckpointStore, LeaseHeld
from layered_platform.storage.db import connect
from layered_platform.tools.idempotency import OperationConflict, Operations, op_id


def test_op_id_is_deterministic_and_argument_order_free():
    a = op_id("wf1", "execute", "deploy.rollback", {"service": "s", "to_release": "r"})
    b = op_id("wf1", "execute", "deploy.rollback", {"to_release": "r", "service": "s"})
    assert a == b and a != op_id("wf1", "record", "deploy.rollback", {"service": "s", "to_release": "r"})


def test_completed_operation_returns_stored_result(tmp_path):
    ops = Operations(connect(tmp_path / "p.db"))
    assert ops.begin("op1", "wf", "c", {"a": 1}) is None
    ops.finish("op1", "COMPLETED", {"ok": True})
    assert ops.begin("op1", "wf", "c", {"a": 1}) == {"ok": True}
    with pytest.raises(OperationConflict):
        ops.begin("op1", "wf", "c", {"a": 2})


def test_in_flight_operation_is_retried_with_the_same_id(tmp_path):
    ops = Operations(connect(tmp_path / "p.db"))
    ops.begin("op1", "wf", "c", {"a": 1})              # process dies here, state IN_FLIGHT
    assert ops.begin("op1", "wf", "c", {"a": 1}) is None
    assert ops.get("op1")["attempts"] == 2


def test_checkpoint_is_atomic_and_append_only(tmp_path):
    st = CheckpointStore(connect(tmp_path / "p.db"))
    st.create("wf1", "r1", "INC-4917", "sre.alice", "cli", "intake", {"x": 1}, "0" * 32, "0" * 16)
    st.checkpoint("wf1", "intake", "investigate", "RUNNING", {"x": 2})
    st.checkpoint("wf1", "investigate", "propose", "RUNNING", {"x": 3})
    rec = st.load("wf1")
    assert rec["step"] == "propose" and rec["state"] == {"x": 3}
    assert [c["seq"] for c in st.history("wf1")] == [1, 2]


def test_lease_blocks_a_live_other_process_and_is_taken_from_a_dead_one(tmp_path):
    db = connect(tmp_path / "p.db")
    st = CheckpointStore(db)
    st.create("wf1", "r1", "INC-4917", "sre.alice", "cli", "intake", {}, "0" * 32, "0" * 16)
    db.execute("UPDATE workflows SET lease_pid=?, lease_until=9e12 WHERE id='wf1'", (os.getppid(),))
    with pytest.raises(LeaseHeld):
        st.acquire("wf1")
    db.execute("UPDATE workflows SET lease_pid=999999, lease_until=9e12 WHERE id='wf1'")
    st.acquire("wf1")
    assert st.load("wf1")["lease_pid"] == os.getpid()
