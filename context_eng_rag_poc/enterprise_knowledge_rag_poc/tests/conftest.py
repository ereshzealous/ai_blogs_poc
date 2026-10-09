"""Shared fixtures. Every test runs without a model and without Ollama: document vectors come from the frozen index tape,
query vectors for the dev questions from tests/fixtures/query_embeddings.jsonl, generation from the scripted surrogate."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_rag.generate import ModelClient
from knowledge_rag.util import config
from knowledge_rag.world import load_world
from s2_eval.common import load_cases, request, retriever

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def w():
    return load_world()


@pytest.fixture(scope="session")
def retr():
    return retriever(FIX / "query_embeddings.jsonl", "replay")


@pytest.fixture(scope="session")
def scripted():
    return ModelClient(config("models.yaml")["primary"], "scripted", None)


@pytest.fixture(scope="session")
def dev_cases():
    return {c["case_id"]: c for c in load_cases("dev")}


@pytest.fixture
def req(w, dev_cases):
    def make(case_id: str, **over):
        c = {**dev_cases[case_id], **over}
        return request(c, w)
    return make
