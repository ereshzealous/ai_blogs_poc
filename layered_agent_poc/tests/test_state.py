"""Workflow state, memory and sessions are different stores with different rules."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from agent_platform.memory.store import MemoryStore, MissingProvenance
from agent_platform.orchestration.store import WorkflowStore


def test_expired_memories_are_not_recalled(tmp_path):
    m = MemoryStore(tmp_path / "p.db")
    m.seed()
    recalled = m.recall("checkout-api", now=datetime(2026, 9, 8, tzinfo=timezone.utc))
    texts = " ".join(x.content for x in recalled)
    assert "INC-4630" in texts and "INC-4411" in texts
    assert "false positives" not in texts  # expired 2026-06-30
    assert all(x.source for x in recalled)


def test_memory_requires_provenance(tmp_path):
    with pytest.raises(MissingProvenance):
        MemoryStore(tmp_path / "p.db").remember("checkout-api", "something", source="", confidence=0.5)


def test_checkpoints_are_append_only_and_latest_wins(tmp_path):
    s = WorkflowStore(tmp_path / "p.db")
    s.create({"id": "wf-1", "name": "t", "incident_id": "INC-1", "status": "RUNNING", "current_step": "intake",
              "channel": "cli", "requested_by": "alice"})
    s.save_checkpoint("wf-1", "intake", "investigate", {"a": 1}, "RUNNING")
    s.save_checkpoint("wf-1", "investigate", "propose_remediation", {"a": 2}, "RUNNING")
    assert [c["seq"] for c in s.checkpoints("wf-1")] == [1, 2]
    assert s.latest_checkpoint("wf-1")["state"] == {"a": 2}
    assert s.get("wf-1")["current_step"] == "propose_remediation"


def test_lease_of_a_dead_worker_can_be_taken_over(tmp_path):
    s = WorkflowStore(tmp_path / "p.db")
    s.create({"id": "wf-2", "name": "t", "incident_id": "INC-1", "status": "RUNNING", "current_step": "intake",
              "channel": "cli", "requested_by": "alice"})
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    assert s.acquire("wf-2", dead.pid)
    assert s.acquire("wf-2", os.getpid())  # holder is gone
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        s.release("wf-2", os.getpid())
        assert s.acquire("wf-2", live.pid)
        assert not s.acquire("wf-2", os.getpid())  # holder alive
    finally:
        live.kill()


def test_approvals_are_bound_to_one_digest(tmp_path):
    s = WorkflowStore(tmp_path / "p.db")
    a = s.request_approval("wf-3", "d1", "source_control.rollback_release", {"target_version": "v4.16"}, "incident-commander", "r")
    again = s.request_approval("wf-3", "d1", "source_control.rollback_release", {"target_version": "v4.16"}, "incident-commander", "r")
    assert a["id"] == again["id"] and a["status"] == "PENDING"
    s.decide(a["id"], "alice", True)
    s.decide(a["id"], "bob", False)  # a decided approval cannot be flipped
    assert s.approval_for("wf-3", "d1")["status"] == "APPROVED"
