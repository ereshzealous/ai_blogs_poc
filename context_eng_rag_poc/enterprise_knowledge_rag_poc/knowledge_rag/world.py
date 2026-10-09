"""The simulated enterprise: source systems, their documents and records, the identity provider, and the clock.

Three read paths, deliberately separate:

- the **index** (knowledge_rag.ingest) is a copy of the prose sources made at the nightly watermark;
- the **source APIs** (SourceAPI) answer what a source says *now*: current status, ACL and the current version of a
  document, including versions published after the watermark;
- the **structured systems of record** (Deployments, Cmdb) are queried live and never copied into the text index.

Everything here is simulated and deterministic; no wall clock is read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from typing import Any

from knowledge_rag.util import CORPUS, load_yaml, slug, ts


@dataclass(frozen=True)
class Section:
    heading: str
    text: str

    @property
    def slug(self) -> str:
        return slug(self.heading)


@dataclass(frozen=True)
class Document:
    source: str
    doc_id: str
    version: str
    title: str
    doc_type: str
    owner: str
    tenant: str
    environments: tuple[str, ...]
    services: tuple[str, ...]
    status: str
    valid_from: str
    valid_to: str | None
    superseded_by: str | None
    acl: tuple[str, ...]
    updated_at: str
    sections: tuple[Section, ...]
    supersedes: str | None = None
    procedure_key: str | None = None
    action: str | None = None
    approval: str | None = None
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def key(self) -> str:
        return f"{self.doc_id}@{self.version}"


def _doc(source: str, d: dict) -> Document:
    known = {"doc_id", "version", "title", "doc_type", "owner", "tenant", "environments", "services", "status", "valid_from",
             "valid_to", "superseded_by", "acl", "updated_at", "sections", "supersedes", "procedure_key", "action", "approval"}
    return Document(
        source=source, doc_id=d["doc_id"], version=d["version"], title=d["title"], doc_type=d["doc_type"], owner=d["owner"],
        tenant=d["tenant"], environments=tuple(d["environments"]), services=tuple(d["services"]), status=d["status"],
        valid_from=d["valid_from"], valid_to=d.get("valid_to"), superseded_by=d.get("superseded_by"), acl=tuple(d["acl"]),
        updated_at=d["updated_at"], sections=tuple(Section(s["heading"], " ".join(s["text"].split())) for s in d["sections"]),
        supersedes=d.get("supersedes"), procedure_key=d.get("procedure_key"), action=d.get("action"), approval=d.get("approval"),
        extra={k: v for k, v in d.items() if k not in known},
    )


def load_documents() -> list[Document]:
    """Every prose document version that existed at the watermark, from every connector file."""
    docs: list[Document] = []
    rb = load_yaml(CORPUS / "runbooks.yaml")
    docs += [_doc(rb["source"], d) for d in rb["documents"]]
    for fname in ("documents.yaml", "estate.yaml"):
        for block in load_yaml(CORPUS / fname)["sources"]:
            docs += [_doc(block["source"], d) for d in block["documents"]]
    keys = [d.key for d in docs]
    dup = {k for k in keys if keys.count(k) > 1}
    if dup:
        raise ValueError(f"duplicate document versions in the corpus: {sorted(dup)}")
    return docs


@dataclass(frozen=True)
class Principal:
    name: str
    display: str
    tenant: str
    role: str
    groups: tuple[str, ...]


class IdentityProvider:
    def __init__(self) -> None:
        raw = load_yaml(CORPUS / "identity.yaml")["principals"]
        self._p = {k: Principal(k, v["display"], v["tenant"], v["role"], tuple(v["groups"])) for k, v in raw.items()}

    def resolve(self, name: str) -> Principal:
        if name not in self._p:
            raise PermissionError(f"unknown principal {name!r}")
        return self._p[name]


@dataclass(frozen=True)
class SourceState:
    """What the source system says about one document version at a point in time."""
    exists: bool
    status: str | None
    acl: tuple[str, ...]
    superseded_by: str | None
    reason: str | None


class SourceUnavailable(RuntimeError):
    """The source API could not be reached. The governed pipeline fails closed on it."""


class SourceAPI:
    """The prose source systems' live APIs (runbook repo, policy repo, ticketing, wiki, restricted store), simulated by
    replaying the event log up to the requested time. `down` names sources that are unreachable (a fault injection)."""

    def __init__(self, documents: list[Document], down: frozenset[str] = frozenset()) -> None:
        cfg = load_yaml(CORPUS / "sources.yaml")
        self.as_of = ts(cfg["as_of"])
        self.watermark = ts(cfg["watermark"])
        self.events = sorted(cfg["events"], key=lambda e: e["at"])
        self.down = down
        self._docs = {d.key: d for d in documents}
        for d in cfg.get("source_only", []):
            doc = _doc(d.get("source", "runbooks"), d)
            self._docs[doc.key] = doc
        self._source_of = {d.key: d.source for d in self._docs.values()}

    def _check(self, key: str) -> None:
        src = self._source_of.get(key)
        if src in self.down:
            raise SourceUnavailable(f"{src} unreachable")

    def state(self, key: str, at: datetime) -> SourceState:
        """Status and ACL of document version `key` at time `at`: the watermark copy, then every event up to `at`."""
        self._check(key)
        d = self._docs.get(key)
        if d is None:
            return SourceState(False, None, (), None, "no such document version")
        status, acl, sup, reason = d.status, d.acl, d.superseded_by, None
        for e in self.events:
            if ts(e["at"]) > at or f"{e['doc_id']}@{e['from_version']}" != key:
                continue
            if e["change"] == "withdrawn":
                status, reason = "withdrawn", e.get("note")
            elif e["change"] == "superseded":
                status, sup, reason = "superseded", f"{e['doc_id']}@{e['new_version']}", e.get("note")
            elif e["change"] == "acl":
                acl, reason = tuple(e["acl"]), e.get("note")
        return SourceState(True, status, acl, sup, reason)

    def get(self, key: str) -> Document:
        self._check(key)
        return self._docs[key]

    def published_at(self, key: str) -> datetime:
        d = self._docs[key]
        return ts(d.updated_at)

    def in_index_copy(self, key: str) -> bool:
        """Whether this version existed at the watermark (so the nightly connector copied it)."""
        return key in self._docs and ts(self._docs[key].updated_at) <= self.watermark

    def by_doc_id(self, doc_id: str) -> list[Document]:
        """Every version the source holds for a document id (an identifier lookup against the source of record)."""
        out = [d for d in self._docs.values() if d.doc_id == doc_id]
        for d in out:
            self._check(d.key)
        return sorted(out, key=lambda d: d.valid_from)


class Deployments:
    """The release system: structured, queried live."""

    def __init__(self) -> None:
        self.records = load_yaml(CORPUS / "structured.yaml")["deployments"]

    def query(self, tenant: str, environment: str, service: str, since: datetime | None = None,
              until: datetime | None = None, version: str | None = None) -> list[dict]:
        out = []
        for r in self.records:
            if (r["tenant"], r["environment"], r["service"]) != (tenant, environment, service):
                continue
            t = ts(r["deployed_at"])
            if until and t > until:
                continue
            if since and t < since:
                continue
            if version and r["version"] != version:
                continue
            out.append(r)
        return sorted(out, key=lambda r: r["deployed_at"], reverse=True)

    def by_version(self, version: str) -> list[dict]:
        return [r for r in self.records if r["version"] == version]


class Cmdb:
    def __init__(self) -> None:
        self.records = load_yaml(CORPUS / "structured.yaml")["cmdb"]

    def lookup(self, tenant: str, environment: str, service: str) -> dict | None:
        for r in self.records:
            if (r["tenant"], r["environment"], r["service"]) == (tenant, environment, service):
                return r
        return None

    @cached_property
    def services(self) -> set[str]:
        return {r["service"] for r in self.records}

    def runbook_of_record(self, tenant: str, environment: str, service: str, procedure_key: str) -> str | None:
        r = self.lookup(tenant, environment, service)
        return (r or {}).get("runbooks", {}).get(procedure_key)


@dataclass
class World:
    documents: list[Document]
    sources: SourceAPI
    deployments: Deployments
    cmdb: Cmdb
    idp: IdentityProvider

    @property
    def as_of(self) -> datetime:
        return self.sources.as_of


def load_world(down: frozenset[str] = frozenset()) -> World:
    docs = load_documents()
    return World(docs, SourceAPI(docs, down), Deployments(), Cmdb(), IdentityProvider())


def known_services() -> set[str]:
    """Service names the query analyser can recognise: the CMDB catalogue plus every service a document names."""
    out = set(Cmdb().services)
    for d in load_documents():
        out |= {s for s in d.services if s != "*"}
    return out


def record_text(r: dict[str, Any], compact: bool = False) -> str:
    """How a structured record is rendered as evidence. `compact` keeps only the fields that answer change questions."""
    if r["record_id"].startswith("dep:"):
        diff = "; ".join(r.get("config_diff", []))
        mig = f"migration: {'true' if r.get('migration') else 'false'}" + (f" ({r['migration_id']})" if r.get("migration_id") else "")
        if compact:
            return f"{r['service']} {r['version']} (previous {r['previous_version']}), deployed {r['deployed_at']}, {mig}, config_diff: {diff}"
        return (f"service: {r['service']} · tenant: {r['tenant']} · environment: {r['environment']} · kind: {r['kind']}\n"
                f"version: {r['version']} · previous_version: {r['previous_version']} · deployed_at: {r['deployed_at']} · "
                f"status: {r['status']} · {mig}\nconfig_diff: {diff}")
    rb = "; ".join(f"{k} -> {v}" for k, v in r.get("runbooks", {}).items()) or "none recorded"
    if compact:
        return f"{r['service']} owner {r['owner']}, on-call {r['oncall']}, approver {r['approver']}, runbooks of record: {rb}"
    return (f"service: {r['service']} · tenant: {r['tenant']} · environment: {r['environment']} · tier: {r['tier']}\n"
            f"owner: {r['owner']} · oncall: {r['oncall']} · approver: {r['approver']} · depends_on: {', '.join(r['depends_on']) or 'none'}\n"
            f"runbooks of record: {rb}")
