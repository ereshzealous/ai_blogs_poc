"""The knowledge capability behind the headless boundary (F3): one request shape in, one view out, whatever head calls it.

Identity comes from the authenticated invoker in the request, resolved by the identity provider. The question is data:
nothing in it can widen the tenant, the environment or the groups the gates use. The view carries the answer, its
verified citations and the evidence packet's identity; it never carries excluded evidence.
"""

from __future__ import annotations

from knowledge_rag.contracts import KnowledgeRequest
from knowledge_rag.gates import Request
from knowledge_rag.generate import ModelClient
from knowledge_rag.pipeline import GOVERNED, run
from knowledge_rag.retrieve import Retriever
from knowledge_rag.util import iso, sha256
from knowledge_rag.world import World


class KnowledgeCapability:
    def __init__(self, world: World, retriever: Retriever, model: ModelClient, seed: int = 7) -> None:
        self.world, self.retriever, self.model, self.seed = world, retriever, model, seed

    def answer(self, kr: KnowledgeRequest) -> dict:
        principal = self.world.idp.resolve(kr.invoker)          # authentication happened upstream; this is resolution
        req = Request(case_id=kr.request_id, principal=principal, tenant=principal.tenant, environment=kr.environment,
                      question=kr.question, as_of=self.world.as_of, budget=kr.budget_tokens)
        res = run(req, GOVERNED, self.retriever, self.world, self.model, self.seed)
        res.pop("_timings_ms", None)
        final = res["final_answer"]
        packet_id = sha256(res["context_text"])[:16]
        return {
            "request_id": kr.request_id, "correlation_id": kr.correlation_id, "channel": kr.channel, "invoker": kr.invoker,
            "tenant": principal.tenant, "environment": kr.environment, "as_of": iso(self.world.as_of),
            "status": final["status"], "summary": final.get("summary", ""), "recommended_action": final["recommended_action"],
            "claims": final["claims"], "gaps": final.get("gaps", []), "conflicts": res["conflicts"],
            "evidence": [{"evidence_id": e["eid"], "unit_id": e["unit_id"], "role": e["role"]} for e in res["packed"]["entries"]],
            "packet_id": packet_id, "binding_notes": res["binding_notes"],
        }
