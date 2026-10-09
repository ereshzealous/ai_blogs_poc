"""Context packing under a fixed budget (estimated tokens), three ways.

- truncate:   the common pattern. Units in relevance order, concatenated, cut at the budget wherever it falls, mid-sentence
              if need be.
- relevance:  whole units in relevance order until the next one does not fit. Experiment B uses it for BOTH arms, so
              only admission differs.
- assembler:  the evidence assembler. Qualifier sections (approvals, exceptions, cautions, limits) travel with the
              procedure they qualify or not at all; identical content is kept once; units are taken by role priority for
              the task (the question's procedure first, then change facts, policy, ownership, history, the rest), then by
              relevance; a structured record that does not fit falls back to its compact form; nothing is cut mid-unit;
              every drop is recorded with its reason.

Every packer returns the same shape, so experiments compare like with like.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from knowledge_rag.gates import Candidate
from knowledge_rag.util import est_tokens

ROLE_LABEL = {"procedure": "runbook", "approval": "change policy", "history": "history only, not a procedure",
              "change_summary": "release notes (summary)", "advisory": "advisory, not authoritative", "reference": "reference",
              "change_fact": "release system, system of record, live query", "ownership": "CMDB, system of record, live query"}


@dataclass
class Packed:
    method: str
    budget: int
    text: str
    entries: list[dict] = field(default_factory=list)    # one per evidence id: eid, unit_id, tokens, truncated, role, tier, text
    dropped: list[dict] = field(default_factory=list)
    used_tokens: int = 0

    def eid_map(self) -> dict[str, dict]:
        return {e["eid"]: e for e in self.entries}

    def summary(self) -> dict:
        return {"method": self.method, "budget": self.budget, "used_tokens": self.used_tokens,
                "entries": [{k: v for k, v in e.items() if k != "text"} for e in self.entries], "dropped": self.dropped}


# ---- rendering --------------------------------------------------------------------------------------------------------
def render_naive(eid: str, c: Candidate) -> str:
    u = c.unit
    body = u.get("index_text") or f"{u['title']} — {u['heading']}\n{u['text']}"
    return f"[{eid}] {body}"


def render_governed(eid: str, c: Candidate, compact: bool = False) -> str:
    u, m = c.unit, c.unit["meta"]
    if u["doc_type"] in ("deployment", "cmdb"):
        what = "deployment record" if u["doc_type"] == "deployment" else "CMDB record"
        text = u["compact_text"] if compact else u["text"]
        return f"[{eid}] {what} {u['unit_id']} — {ROLE_LABEL[c.role]}\n{text}"
    label = ROLE_LABEL.get(c.role, c.role)
    if c.role == "procedure":
        label = "runbook of record" if c.tier == 1 else "owner runbook (not named by the CMDB)"
    bits = [f"{u['doc_id']} {u['version']} · {u['heading']}", label, f"owner {m['owner']}",
            f"{c.live.get('status') or m['status']} since {m['valid_from'][:10]}"]
    if u.get("fetched_from_source"):
        bits.append("fetched from the source (newer than the index)")
    return f"[{eid}] " + " · ".join(bits) + f"\n{u['text']}"


def _join(parts: list[str]) -> str:
    return "\n\n".join(parts)


# ---- packers ------------------------------------------------------------------------------------------------------------
def truncate(cands: list[Candidate], budget: int, render=render_naive, prelude: str = "") -> Packed:
    """Concatenate in the given order, then cut the text at the budget (estimated tokens = bytes / 4)."""
    p = Packed("truncate", budget, "")
    parts, used = ([prelude] if prelude else []), est_tokens(prelude) if prelude else 0
    for i, c in enumerate(cands, start=1):
        eid = f"E{i}"
        block = render(eid, c)
        t = est_tokens(block)
        room = budget - used - (1 if parts else 0)
        if room <= 0:
            p.dropped.append({"unit_id": c.uid, "reason": "budget exhausted"})
            continue
        if t <= room:
            parts.append(block)
            used += t + (1 if len(parts) > 1 else 0)
            p.entries.append(_entry(eid, c, block, t, False))
        else:
            cut = block.encode("utf-8")[: max(0, room * 4)].decode("utf-8", "ignore")
            parts.append(cut)
            used = budget
            p.entries.append(_entry(eid, c, cut, est_tokens(cut), True))
    p.text = _join(parts)
    p.used_tokens = est_tokens(p.text)
    return p


def relevance(cands: list[Candidate], budget: int, render=render_naive, prelude: str = "") -> Packed:
    """Whole units in the given order while they fit; a unit that does not fit is skipped, the next one tried."""
    p = Packed("relevance", budget, "")
    parts = [prelude] if prelude else []
    n = 0
    for c in cands:
        eid = f"E{n + 1}"
        block = render(eid, c)
        if est_tokens(_join(parts + [block])) <= budget:
            parts.append(block)
            n += 1
            p.entries.append(_entry(eid, c, block, est_tokens(block), False))
        else:
            p.dropped.append({"unit_id": c.uid, "reason": "does not fit the remaining budget"})
    p.text = _join(parts)
    p.used_tokens = est_tokens(p.text)
    return p


def _priority(c: Candidate, tasks: list[str], target_key: str | None) -> int:
    m = c.unit["meta"]
    if c.role == "procedure" and target_key and m["procedure_key"] == target_key:
        return 0
    if c.role == "change_fact":
        return 1
    if c.role == "approval":
        return 2
    if c.role == "ownership":
        return 3
    if c.role == "procedure":
        return 4 if not target_key else 5
    if c.role == "history":
        return 4 if any(t in tasks for t in ("history", "root_cause")) else 6
    return 7


def assembler(cands: list[Candidate], budget: int, tasks: list[str], target_key: str | None, prelude: str = "") -> Packed:
    p = Packed("assembler", budget, "")
    order = {id(c): i for i, c in enumerate(cands)}
    # 1. one item per non-qualifier unit, with the qualifier sections of the same document version bound to it;
    #    a qualifier whose procedure is not admitted stands alone
    quals: dict[str, list[Candidate]] = {}
    for c in cands:
        if c.unit.get("qualifier"):
            quals.setdefault(c.unit["doc_key"], []).append(c)
    items, bound = [], set()
    for c in cands:
        if c.unit.get("qualifier"):
            continue
        q = sorted(quals.get(c.unit["doc_key"], []), key=lambda x: x.unit.get("section_index", 0))
        q = [x for x in q if id(x) not in bound]
        bound |= {id(x) for x in q}
        items.append([c] + q)
    for qs in quals.values():
        for x in qs:
            if id(x) not in bound:
                items.append([x])
    # 2. identical content once
    seen, uniq = set(), []
    for it in items:
        h = tuple(x.unit.get("content_hash") or x.uid for x in it)
        if h in seen:
            p.dropped.extend({"unit_id": x.uid, "reason": "duplicate content"} for x in it)
            continue
        seen.add(h)
        uniq.append(it)
    # 3. breadth first by role: every role's best item, then every role's second-best, and so on; within a round, role
    #    priority for the task; within a role, relevance (the order the candidates arrived in)
    uniq.sort(key=lambda it: (_priority(it[0], tasks, target_key), order[id(it[0])]))
    nth: dict[int, int] = {}
    keyed = []
    for it in uniq:
        pr = _priority(it[0], tasks, target_key)
        keyed.append((nth.get(pr, 0), pr, order[id(it[0])], it))
        nth[pr] = nth.get(pr, 0) + 1
    uniq = [k[3] for k in sorted(keyed, key=lambda k: k[:3])]
    parts = [prelude] if prelude else []
    n = 0
    for it in uniq:
        blocks = [render_governed(f"E{n + 1 + j}", x) for j, x in enumerate(it)]
        if est_tokens(_join(parts + blocks)) > budget and it[0].unit["doc_type"] in ("deployment", "cmdb"):
            blocks = [render_governed(f"E{n + 1}", it[0], compact=True)]
        if est_tokens(_join(parts + blocks)) <= budget:
            for j, (x, b) in enumerate(zip(it, blocks)):
                parts.append(b)
                p.entries.append(_entry(f"E{n + 1 + j}", x, b, est_tokens(b), False))
            n += len(blocks)
        else:
            reason = "does not fit the remaining budget" + (" (kept with its qualifiers or not at all)" if len(it) > 1 else "")
            p.dropped.extend({"unit_id": x.uid, "reason": reason} for x in it)
    p.text = _join(parts)
    p.used_tokens = est_tokens(p.text)
    return p


def _entry(eid: str, c: Candidate, text: str, tokens: int, truncated: bool) -> dict:
    return {"eid": eid, "unit_id": c.uid, "doc_key": c.unit["doc_key"], "doc_type": c.unit["doc_type"], "role": c.role,
            "tier": c.tier, "tokens": tokens, "truncated": truncated, "qualifier": bool(c.unit.get("qualifier")),
            "action": c.unit["meta"].get("action"), "approval": c.unit["meta"].get("approval"),
            "procedure_key": c.unit["meta"].get("procedure_key"), "text": text}
