"""Evidence admission: authorization (index pre-filter and authoritative recheck), scope, lifecycle, authority, conflict.

Every decision is deterministic and made from metadata the sources own (ACLs, status, effective windows, the CMDB's
runbook-of-record pointers) and the request (principal, tenant, environment, service). No model, reranker or similarity
score can admit a unit these gates exclude. Each candidate leaves with a decision record: admitted, or excluded by
which gate and why. Exclusions for authorization are never shown to the model (not even as a count by reason): telling a
caller that a restricted document exists is itself a leak.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime

from knowledge_rag.util import config, ts
from knowledge_rag.world import Principal, SourceUnavailable, World, record_text

AUTH = config("authority.yaml")
ROLE = AUTH["roles"]


@dataclass
class Request:
    case_id: str
    principal: Principal
    tenant: str
    environment: str
    question: str
    as_of: datetime
    budget: int


@dataclass
class Candidate:
    unit: dict
    origin: str             # hybrid | vector | bm25 | identifier | structured | source-replacement
    rank: int               # 1-based relevance rank within its origin (structured: recency order)
    score: float = 0.0
    live: dict = field(default_factory=dict)   # what the source says at as_of (filled by the recheck)
    role: str | None = None
    tier: int | None = None
    decision: str = "candidate"                 # admitted | excluded
    gate: str | None = None
    reason: str | None = None

    @property
    def uid(self) -> str:
        return self.unit["unit_id"]

    def exclude(self, gate: str, reason: str) -> None:
        self.decision, self.gate, self.reason = "excluded", gate, reason

    def trace(self) -> dict:
        return {"unit_id": self.uid, "origin": self.origin, "rank": self.rank, "score": round(self.score, 6),
                "role": self.role, "tier": self.tier, "decision": self.decision, "gate": self.gate, "reason": self.reason}


# ---- structured records as evidence units ---------------------------------------------------------------------------
def record_unit(r: dict, system: str) -> dict:
    kind = "deployment" if system == "deployments" else "cmdb"
    heading = f"{r['service']} {r['version']}" if kind == "deployment" else f"{r['service']} ({r['environment']})"
    return {"unit_id": r["record_id"], "doc_id": r["record_id"], "version": "live", "doc_key": r["record_id"], "source": system,
            "doc_type": kind, "title": "deployment record" if kind == "deployment" else "CMDB record", "heading": heading,
            "text": record_text(r), "compact_text": record_text(r, compact=True), "qualifier": False, "record": r,
            "meta": {"tenant": r["tenant"], "environments": [r["environment"]], "services": [r["service"]], "status": "active",
                     "valid_from": r.get("deployed_at", "1970-01-01T00:00:00Z"), "valid_to": None, "superseded_by": None,
                     "procedure_key": None, "action": None, "approval": None, "owner": r.get("owner", system), "acl": ["tenant-engineers"]},
            "ingested_at": None}


def source_units(doc) -> list[dict]:
    """Units for a document fetched from the source API (not from the index): same shape, no ingestion time."""
    from knowledge_rag.ingest import units_for
    out = units_for(doc, ingested_at=None)
    for u in out:
        u["fetched_from_source"] = True
    return out


# ---- authorization ------------------------------------------------------------------------------------------------------
def index_prefilter(principal: Principal):
    """Security trimming at the index, with the ACL and tenant AS INDEXED (possibly stale). A fast first filter only."""
    groups = set(principal.groups)

    def ok(u: dict) -> bool:
        m = u["meta"]
        return m["tenant"] in (principal.tenant, "*") and bool(groups & set(m["acl"]))
    return ok


def recheck(cands: list[Candidate], req: Request, world: World, fetch_replacements: bool = True) -> list[Candidate]:
    """The authoritative recheck: ask each prose candidate's source what it says NOW (status, ACL, supersession).
    Unreachable source -> excluded (fail closed). Not readable by the principal at the source -> excluded.
    Superseded at the source by a version the index does not hold yet -> the current version is fetched from the source
    as a replacement candidate. Structured records come from live queries already; they are checked for tenant only."""
    groups = set(req.principal.groups)
    extra: list[Candidate] = []
    seen = {c.uid for c in cands}
    for c in cands:
        if c.decision != "candidate":
            continue
        u = c.unit
        if u["doc_type"] in ("deployment", "cmdb"):
            c.live = {"status": "active", "acl": None}
            if u["meta"]["tenant"] != req.tenant:
                c.exclude("authorization", "structured record of another tenant")
            continue
        try:
            st = world.sources.state(u["doc_key"], req.as_of)
        except SourceUnavailable as e:
            c.exclude("authorization", f"source unreachable, fail closed ({e})")
            continue
        c.live = {"status": st.status, "acl": list(st.acl), "superseded_by": st.superseded_by, "reason": st.reason}
        if not st.exists:
            c.exclude("authorization", "no longer exists at the source")
        elif not groups & set(st.acl):
            c.exclude("authorization", "not readable by the principal at the source")
        elif fetch_replacements and st.status == "superseded" and st.superseded_by:
            try:
                new = world.sources.get(st.superseded_by)
            except (KeyError, SourceUnavailable):
                continue
            nst = world.sources.state(new.key, req.as_of)
            if nst.exists and groups & set(nst.acl) and ts(new.valid_from) <= req.as_of:
                for nu in source_units(new):
                    if nu["unit_id"] not in seen:
                        seen.add(nu["unit_id"])
                        nc = Candidate(nu, "source-replacement", c.rank, c.score)
                        nc.live = {"status": nst.status, "acl": list(nst.acl), "superseded_by": nst.superseded_by, "reason": None}
                        extra.append(nc)
    return cands + extra


# ---- scope ----------------------------------------------------------------------------------------------------------------
def scope_gate(cands: list[Candidate], req: Request, service: str | None, world: World) -> None:
    allowed = None
    if service:
        rec = world.cmdb.lookup(req.tenant, req.environment, service)
        allowed = {service, "*"} | set((rec or {}).get("depends_on", []))
    for c in live(cands):
        m = c.unit["meta"]
        if m["tenant"] not in (req.tenant, "*"):
            c.exclude("scope", f"tenant {m['tenant']} is not the request's tenant {req.tenant}")
        elif req.environment not in m["environments"]:
            c.exclude("scope", f"applies to {', '.join(m['environments'])}, not {req.environment}")
        elif allowed is not None and not set(m["services"]) & allowed:
            c.exclude("scope", f"about {', '.join(m['services'])}, not {service} or its dependencies")


# ---- lifecycle ------------------------------------------------------------------------------------------------------------
def lifecycle_gate(cands: list[Candidate], req: Request) -> None:
    for c in live(cands):
        m, st = c.unit["meta"], (c.live.get("status") or c.unit["meta"]["status"])
        vf, vt = ts(m["valid_from"]), ts(m["valid_to"])
        if st == "withdrawn":
            c.exclude("lifecycle", f"withdrawn at the source ({c.live.get('reason') or 'no reason given'})")
        elif st == "draft":
            c.exclude("lifecycle", f"draft, not approved (would take effect {m['valid_from'][:10]})")
        elif st == "superseded":
            by = c.live.get("superseded_by") or m["superseded_by"]
            c.exclude("lifecycle", f"superseded by {by}")
        elif vf and vf > req.as_of:
            c.exclude("lifecycle", f"not yet effective (valid from {m['valid_from'][:10]})")
        elif vt and vt <= req.as_of:
            c.exclude("lifecycle", f"expired (valid to {m['valid_to'][:10]})")


# ---- authority ------------------------------------------------------------------------------------------------------------
def procedure_tier(u: dict, req: Request, service: str | None, world: World) -> int:
    m = u["meta"]
    if m["services"] == ["*"] and m["owner"] == AUTH["platform_owner"]:
        return 1
    for svc in ([service] if service else []) + [s for s in m["services"] if s != "*"]:
        rec = world.cmdb.lookup(req.tenant, req.environment, svc)
        if rec and u["doc_id"] in rec.get("runbooks", {}).values():
            return 1
    if service:
        rec = world.cmdb.lookup(req.tenant, req.environment, service)
        if rec and m["owner"] == rec["owner"] and service in m["services"]:
            return 2
    return 3


def assign_roles(cands: list[Candidate], req: Request, service: str | None, world: World) -> None:
    for c in cands:
        c.role = ROLE.get(c.unit["doc_type"], "advisory")
        c.tier = procedure_tier(c.unit, req, service, world) if c.role == "procedure" else None


def target_procedure_key(cands: list[Candidate]) -> str | None:
    """The procedure the question is about: the procedure key of the best-ranked in-scope runbook candidate, whatever its
    lifecycle state. Chosen by relevance among candidates, never by a label."""
    best = None
    for c in cands:
        if c.role != "procedure" or c.gate in ("authorization", "scope"):
            continue
        if best is None or (c.origin != "structured" and (c.rank, c.uid) < (best.rank, best.uid)):
            best = c
    return best.unit["meta"]["procedure_key"] if best else None


def authority_gate(cands: list[Candidate], req: Request, tasks: list[str], target_key: str | None, world: World) -> None:
    """Applies config/authority.yaml. Excludes tier-3 procedure, and history or advisory units the policy does not need."""
    ok = live(cands)
    for c in ok:
        if c.role == "procedure" and c.tier == 3:
            c.exclude("authority", "runbook of another owner: not authoritative for this service's procedure")
    proc_for_target = [c for c in live(cands) if c.role == "procedure" and c.tier in (1, 2)
                       and (target_key is None or c.unit["meta"]["procedure_key"] == target_key)]
    any_proc = [c for c in live(cands) if c.role == "procedure" and c.tier in (1, 2)]
    policy = [c for c in live(cands) if c.role == "approval"]
    wants_history = any(t in tasks for t in ("history", "root_cause"))
    for c in live(cands):
        if c.role == "history" and not wants_history and proc_for_target:
            c.exclude("authority", "history: the question does not ask about history and an authoritative procedure exists")
        elif c.role == "advisory" and (any_proc or policy):
            c.exclude("authority", "advisory (wiki or guide): an authoritative procedure or policy exists for this request")


def conflict_gate(cands: list[Candidate]) -> list[dict]:
    """Same procedure key, both admissible: a tier-1 runbook outranks a disagreeing tier-2 one; two disagreeing tier-2
    runbooks with no tier 1 are an UNRESOLVED conflict and both stay, so the answer has to surface it."""
    conflicts = []
    by_key: dict[str, list[Candidate]] = {}
    for c in live(cands):
        if c.role == "procedure" and c.tier in (1, 2):
            by_key.setdefault(c.unit["meta"]["procedure_key"], []).append(c)
    for key, group in sorted(by_key.items()):
        sig = lambda c: (c.unit["meta"]["action"], c.unit["meta"]["approval"])  # noqa: E731
        t1 = [c for c in group if c.tier == 1]
        if t1:
            win = {sig(c) for c in t1}
            for c in group:
                if c.tier == 2 and sig(c) not in win:
                    c.exclude("conflict", f"outranked: disagrees with the runbook of record {t1[0].unit['doc_key']}")
            if len(win) > 1:
                conflicts.append(_conflict(key, t1))
        else:
            if len({sig(c) for c in group}) > 1:
                conflicts.append(_conflict(key, group))
    return conflicts


def _conflict(key: str, group: list[Candidate]) -> dict:
    docs = {}
    for c in group:
        m = c.unit["meta"]
        docs[c.unit["doc_key"]] = {"action": m["action"], "approval": m["approval"], "owner": m["owner"]}
    return {"procedure_key": key, "documents": docs, "resolution": "unresolved: same authority tier, no runbook of record"}


def gaps_for(cands: list[Candidate], req: Request, service: str | None, target_key: str | None, world: World) -> list[str]:
    """Evidence gaps the model is told about. Never mentions a unit excluded for authorization."""
    gaps = []
    if service and not world.cmdb.lookup(req.tenant, req.environment, service):
        gaps.append(f"The CMDB has no record for {service} in {req.tenant}/{req.environment}.")
    if service and target_key:
        rob = world.cmdb.runbook_of_record(req.tenant, req.environment, service, target_key)
        admitted = [c for c in live(cands) if c.role == "procedure" and c.unit["meta"]["procedure_key"] == target_key]
        if rob and not admitted:
            why = sorted({c.reason for c in cands if c.unit["doc_id"] == rob and c.gate == "lifecycle"})
            gaps.append(f"The CMDB names {rob} as the runbook of record for {target_key}, but no current version is "
                        f"available" + (f": {'; '.join(why)}." if why else "."))
        if not rob and not admitted:
            gaps.append(f"The CMDB names no runbook of record for {target_key} on {service}.")
    if service and not target_key and not any(c.role == "procedure" for c in live(cands)):
        gaps.append(f"No runbook in scope for {service} in {req.tenant}/{req.environment}.")
    down = sorted({c.unit["source"] for c in cands if c.gate == "authorization" and "source unreachable" in (c.reason or "")})
    for s in down:
        gaps.append(f"The {s} source could not be reached; its documents were left out (fail closed).")
    return gaps


def live(cands: list[Candidate]) -> list[Candidate]:
    return [c for c in cands if c.decision == "candidate"]


def admit(cands: list[Candidate]) -> list[Candidate]:
    for c in live(cands):
        c.decision = "admitted"
    return [c for c in cands if c.decision == "admitted"]


def clone(cands: list[Candidate]) -> list[Candidate]:
    return [copy.deepcopy(c) for c in cands]
