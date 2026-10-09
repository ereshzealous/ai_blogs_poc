"""Shared fixtures: the frozen scenario, a deterministic fake embedder (no model needed) and small record builders."""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone

import pytest

from governed_memory.models.authority import AuthorityPolicy
from governed_memory.models.record import MemoryRecord, Query
from s1_experiments.scenario import Scenario


class FakeEmbedder:
    """Bag of words hashed into 256 dims, L2-normalised. Deterministic and good enough to rank by word overlap."""

    def __init__(self):
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        out = []
        for t in texts:
            v = [0.0] * 256
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 256] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


CLOCK = datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def scenario() -> Scenario:
    return Scenario.load()


@pytest.fixture
def policy() -> AuthorityPolicy:
    return AuthorityPolicy.load()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def query(scenario) -> Query:
    return scenario.query("incident_query")


def rec(id: str, content: str = "checkout-api latency after deploy rollback", **over) -> MemoryRecord:
    base = {
        "id": id, "memory_type": "episode", "content": content,
        "source": {"type": "incident", "id": id.upper()},
        "provenance": {"created_by": "incident-summary-agent", "evidence_refs": ["PM-1"]},
        "scope": {"tenant": "acme", "environment": "production", "entities": ["checkout-api"]},
        "created_at": "2026-08-01T00:00:00Z", "expires_at": "2027-01-01T00:00:00Z",
        "trust": {"source_class": "platform-verified"}, "claim_type": "incident_history",
    }
    for k, v in over.items():
        base[k] = v
    return MemoryRecord.from_dict(base)
