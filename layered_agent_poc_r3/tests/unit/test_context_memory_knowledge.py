from layered_platform.context.assembler import ContextAssembler
from layered_platform.context.knowledge import KnowledgeBase
from layered_platform.memory.store import MemoryStore
from layered_platform.storage.db import connect


def test_knowledge_returns_sourced_runbook_sections():
    kb = KnowledgeBase("simulated_enterprise/data/runbooks")
    hits = kb.search("checkout latency pool triage", 3, doc_hint="checkout")
    assert hits and all(h["source"].startswith("RB-") for h in hits)
    assert hits[0]["source"].startswith("RB-CHK-007")


def test_memory_is_keyed_so_a_resume_does_not_duplicate_it(tmp_path):
    mem = MemoryStore(connect(tmp_path / "p.db"), "simulated_enterprise/data/memory_seed.yaml")
    n = mem.count()
    mem.remember("wf-1", "checkout-api", "incident_outcome", "rolled back", "wf-1")
    mem.remember("wf-1", "checkout-api", "incident_outcome", "rolled back", "wf-1")
    assert mem.count() == n + 1
    assert {m["source"] for m in mem.recall("checkout-api")} >= {"INC-4630 postmortem"}


def test_context_labels_facts_knowledge_and_memory_separately(tmp_path):
    ctx = ContextAssembler(KnowledgeBase("simulated_enterprise/data/runbooks"), MemoryStore(connect(tmp_path / "p.db"), "simulated_enterprise/data/memory_seed.yaml"))
    msgs, manifest = ctx.build("instr", "task", {"incident": {"id": "INC-4917"}}, "checkout-api latency", "checkout-api")
    body = msgs[1]["content"]
    assert "## Facts from the workflow record" in body and "## Runbook excerpts" in body and "(advisory, may be stale)" in body
    assert manifest["knowledge"] and manifest["memory"]
