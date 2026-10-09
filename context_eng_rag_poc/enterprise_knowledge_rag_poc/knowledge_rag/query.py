"""Query understanding, by rules: no model decides what the question is about or who is asking.

From the question it extracts identifiers (versions, document ids, incident ids), service names (the CMDB catalogue plus
every service a document names) and task cues (procedure, history, root cause, change, ownership). Tenant and
environment come from the request (the authenticated principal and the console), never from the question text; a
tenant the question mentions is recorded only so a mismatch is visible in the trace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from knowledge_rag.util import config
from knowledge_rag.world import World, known_services

VOCAB = config("vocabulary.yaml")
VERSION = re.compile(r"(?<![\w.])\d+\.\d+\.\d+(?![\w.])")
DOC_ID = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9.]+)+\b")
INCIDENT = re.compile(r"\bINC-\d+\b")
_SERVICES = sorted(known_services(), key=len, reverse=True)


@dataclass
class QueryAnalysis:
    question: str
    tenant: str
    environment: str
    services: list[str] = field(default_factory=list)
    service: str | None = None
    service_from: str | None = None          # "question" | "identifier" | None
    versions: list[str] = field(default_factory=list)
    doc_ids: list[str] = field(default_factory=list)
    incidents: list[str] = field(default_factory=list)
    tenant_mentions: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def find_services(question: str) -> list[str]:
    q, found = question.lower(), []
    for s in _SERVICES:
        for m in re.finditer(rf"(?<![\w-]){re.escape(s)}(?![\w-])", q):
            found.append((m.start(), s))
    taken: list[tuple[int, int]] = []
    out = []
    for start, s in sorted(found, key=lambda x: (x[0], -len(x[1]))):
        if any(a <= start < b for a, b in taken):
            continue
        taken.append((start, start + len(s)))
        if s not in out:
            out.append(s)
    return out


def tasks_for(question: str) -> list[str]:
    q = question.lower()
    return [t for t, cues in VOCAB["task_cues"].items() if any(c in q for c in cues)]


def analyze_query(question: str, tenant: str, environment: str, world: World) -> QueryAnalysis:
    qa = QueryAnalysis(question=question, tenant=tenant, environment=environment)
    qa.services = find_services(question)
    qa.versions = VERSION.findall(question)
    qa.incidents = INCIDENT.findall(question)
    catalog = {d.doc_id for d in world.documents}
    qa.doc_ids = [m for m in DOC_ID.findall(question) if m in catalog and m not in qa.incidents]
    qa.tenant_mentions = [t for t in ("acme", "globex") if re.search(rf"\b{t}\b", question.lower())]
    qa.tasks = tasks_for(question)
    if qa.services:
        qa.service, qa.service_from = qa.services[0], "question"
    elif qa.doc_ids:
        docs = [d for d in world.documents if d.doc_id == qa.doc_ids[0]]
        svc = [s for s in docs[0].services if s != "*"]
        if svc:
            qa.service, qa.service_from = svc[0], "identifier"
    return qa
