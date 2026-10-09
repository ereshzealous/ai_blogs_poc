"""Context + memory (P1 layer E), the operational half: retrieval fan-out, context size, and a cache with a scope.

Two uses:
  ``Retriever.fetch``   the load scenarios: a deterministic number of chunks per source, bounded by the release's
                        retrieval configuration (top_k, max_sources, context cap); latency and cost per query and chunk
  ``assemble``          E6: the knowledge fixture (experiments/fixtures/knowledge.json), naive vs bounded retrieval, with
                        each query's REQUIRED evidence ids declared in the fixture and checked mechanically
  ``Cache``             E6: a retrieval cache keyed by query text only (naive) or by tenant · principal scope ·
                        knowledge version · policy version · query (scoped)
"""

from __future__ import annotations

from .common import canonical, cfg, sha256_text
from .sim import sleep

W = cfg("workflows")["common"]
COST = cfg("platform")["costs"]


class Retriever:
    def __init__(self, contention=lambda: 1.0):
        self.contention = contention

    def fetch(self, sources: list[str], retrieval: dict):
        """A generator: (calls, chunks, context_tokens, latency_ms, cost_cu)."""
        src = sources[: retrieval["max_sources"]]
        if not src:
            return 0, 0, 0, 0, 0.0
        chunks = retrieval["top_k"] * len(src)
        tokens = min(retrieval["context_cap_tokens"], chunks * W["chunk_tokens"])
        lat = int(round((W["retrieval_base_ms"] * len(src) + W["retrieval_ms_per_chunk"] * chunks) * self.contention()))
        yield sleep(lat)
        cost = COST["retrieval_query_cu"] * len(src) + COST["retrieval_chunk_cu"] * chunks
        return len(src), chunks, tokens, lat, cost


# ---- E6: the knowledge fixture ------------------------------------------------------------------------------------------

NAIVE = {"top_k": 20, "sources": "all", "context_cap_tokens": None, "history": "full"}


def assemble(query: dict, kb: dict, mode: str, retrieval: dict) -> dict:
    """Build the context for one fixture query. mode: naive | bounded. Returns the admitted doc ids, token counts, the
    sources queried and whether every REQUIRED evidence id (declared in the fixture) is present."""
    docs = {d["id"]: d for d in kb["docs"]}
    if mode == "naive":
        sources, k, cap = kb["sources"], NAIVE["top_k"], None
        history = kb["history"]["turn_tokens"] * kb["history"]["turns"]
    else:
        sources = kb["routes"][query["type"]][: retrieval["max_sources"]]
        k, cap = retrieval["top_k"], retrieval["context_cap_tokens"]
        history = kb["history"]["turn_tokens"] * 3 + kb["history"]["summary_tokens"]
    picked = []
    for s in sources:
        cands = sorted((d for d in kb["docs"] if d["source"] == s and d["id"] in query["scores"]),
                       key=lambda d: (-query["scores"][d["id"]], d["id"]))
        picked += cands[:k]
    picked.sort(key=lambda d: (-query["scores"][d["id"]], d["id"]))
    admitted, tokens = [], 0
    budget = None if cap is None else cap - history
    for d in picked:
        if budget is not None and tokens + d["tokens"] > budget:
            continue                          # pruned: the next-best chunk that fits is still considered
        admitted.append(d["id"])
        tokens += d["tokens"]
    missing = [r for r in query["required"] if r not in admitted]
    return {"query": query["id"], "mode": mode, "sources": len(sources), "retrieved": len(picked), "admitted": admitted,
            "chunk_tokens": tokens, "history_tokens": history, "context_tokens": tokens + history + kb["system_tokens"],
            "required": query["required"], "missing_required": missing,
            "retrieval_cost_cu": round(COST["retrieval_query_cu"] * len(sources) + COST["retrieval_chunk_cu"] * len(picked), 4),
            "doc_check": all(r in docs for r in query["required"])}


class Cache:
    """A retrieval cache. ``scoped=False`` keys by the query text alone ("cache it for everyone"); ``scoped=True`` keys by
    tenant, principal (for personal questions; '*' for shared ones), knowledge version, policy version and the text."""

    def __init__(self, scoped: bool):
        self.scoped = scoped
        self.store: dict[str, dict] = {}

    def key(self, req: dict) -> str:
        text = " ".join(req["text"].lower().split())
        if not self.scoped:
            return sha256_text(text)
        return sha256_text(canonical([req["tenant"], req["principal"] if req["personal"] else "*", req["kb_version"],
                                      req["policy_version"], text]))

    def lookup(self, req: dict) -> dict:
        k = self.key(req)
        hit = self.store.get(k)
        if hit is None:
            self.store[k] = {"principal": req["principal"], "tenant": req["tenant"], "kb_version": req["kb_version"],
                             "policy_version": req["policy_version"], "personal": req["personal"]}
            return {"hit": False, "cross_principal": False, "cross_tenant": False, "stale": False}
        return {"hit": True,
                "cross_principal": bool(req["personal"] and hit["principal"] != req["principal"]),
                "cross_tenant": hit["tenant"] != req["tenant"],
                "stale": hit["kb_version"] != req["kb_version"] or hit["policy_version"] != req["policy_version"]}
