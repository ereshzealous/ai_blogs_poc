"""Shared setup for every experiment: the world, the index, the retriever and the requests built from case files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from knowledge_rag.embed import TAPE, Embedder
from knowledge_rag.gates import Request
from knowledge_rag.ingest import load_units
from knowledge_rag.retrieve import Retriever
from knowledge_rag.util import ROOT, config, load_yaml
from knowledge_rag.world import World, load_world

CASES = ROOT / "cases"
RUNS = ROOT / "runs"
RCFG = config("retrieval.yaml")


def load_cases(split: str) -> list[dict]:
    if split == "all":
        return load_cases("dev") + load_cases("heldout")
    data = load_yaml(CASES / f"{split}.yaml")
    return [{**c, "split": data["split"]} for c in data["cases"]]


@lru_cache(maxsize=None)
def world() -> World:
    return load_world()


def retriever(query_tape: Path | None = None, mode: str = "replay") -> Retriever:
    """Document vectors from the frozen index tape; query vectors from (and, live, recorded to) the run's own tape."""
    tapes = [TAPE] + ([query_tape] if query_tape else [])
    emb = Embedder(mode, tapes=tapes, record_to=query_tape)
    return Retriever(load_units(), emb)


def request(case: dict, w: World, budget: int | None = None) -> Request:
    p = w.idp.resolve(case["principal"])
    return Request(case_id=case["case_id"], principal=p, tenant=p.tenant, environment=case["environment"],
                   question=case["question"], as_of=w.as_of, budget=budget or RCFG["budget"]["tokens"])
