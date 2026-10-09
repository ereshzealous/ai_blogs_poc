"""Claim-to-source citation verification, and binding the final answer to the evidence.

A citation is not valid because the cited chunk exists. A material claim (cause, procedure, approval, history, fact) is
SUPPORTED only if all of these hold:

1. it cites at least one evidence id, and every cited id was in the context the model saw;
2. every quote appears verbatim (after whitespace/typography normalisation) in the evidence it cites;
3. every anchor in the claim (numbers, versions, identifiers with digits, dotted flags) appears in the cited evidence,
   unless the anchor came from the question itself;
4. every action the claim mentions appears in the cited evidence with the same polarity ("do not restart" does not
   support "restart"); when the quote itself names the action, the quote's polarity decides;
5. the cited evidence may decide this kind of claim: procedure needs an admissible runbook of record or owner runbook
   (tier 1-2), approval needs that or a change policy, history needs a ticket, postmortem or release record; and a claim that is phrased
   as a recommendation is held to procedure authority whatever kind the model gave it.

This is a lexical verifier: deterministic and auditable, blind to paraphrase it cannot match and to entailment it
cannot see. Experiment D2 measures exactly how often it is wrong on a labelled set.

Binding (governed pipeline only) then removes unsupported claims, removes a recommended action that no supported
procedure claim backs (the cited runbook prescribes it, by its front matter or in the cited section), never lets an
answer drop an approval the backing runbook requires, and turns an answer that touches an unresolved conflict into an
escalation.
"""

from __future__ import annotations

import copy
import re

from knowledge_rag.util import config, norm

VOCAB = config("vocabulary.yaml")
MATERIAL = {"cause", "procedure", "approval", "history", "fact"}
NUM = re.compile(r"(?<![\w.])\d+(?:[.,:]\d+)*(?![\w])")
IDENT = re.compile(r"(?<![\w.-])[A-Za-z][A-Za-z0-9]*(?:[-_.][A-Za-z0-9]+)+(?![\w-])")
POST_NEG = re.compile(r"^\w*(?:\s+(?!and\b|or\b|then\b)\S+){0,2}?\s*,?\s*(?:is|are|was|does|do|did|will|would|can|could|should|must)?\s*"
                      r"(?:not|no longer|never)\b|^\w*\s*(?:isn't|aren't|doesn't|don't|won't|can't)\b")


def _num(s: str) -> str:
    return s.replace(",", "")


def anchors(text: str, question: str = "") -> set[str]:
    q = norm(question)
    out = {_num(m.group(0)) for m in NUM.finditer(text)}
    out |= {m.group(0).lower() for m in IDENT.finditer(text) if re.search(r"[\d_.]", m.group(0))}
    out = {a for a in out if len(a) > 1 or a.isdigit() and int(a) > 9}
    return {a for a in out if not _contains(q, a)}


def _contains(hay: str, a: str) -> bool:
    hay = re.sub(r"(?<=\d),(?=\d)", "", hay)
    if re.fullmatch(r"[\d.:]+", a):
        return re.search(rf"(?<![\d.]){re.escape(a)}(?![\d])", hay) is not None
    return a in hay


def action_mentions(text: str) -> list[tuple[str, bool]]:
    """(action, negated) for every action term in the text. Negation: a cue in the 32 characters before the term, or a
    'is not / no longer' right after it."""
    low, out = text.lower(), []
    for action, terms in list(VOCAB["actions"].items()) + [(f"term:{t}", [t]) for t in VOCAB["polarity_terms"]]:
        for t in terms:
            for m in re.finditer(re.escape(t), low):
                before = low[max(0, m.start() - 32):m.start()]
                before = re.split(r"[.;:!?]", before)[-1]
                neg = any(n in before for n in VOCAB["negations"]) or bool(POST_NEG.match(low[m.end():m.end() + 24]))
                out.append((action, neg))
    return out


def quote_found(quote: str, evidence_text: str) -> bool:
    q, t = norm(quote), norm(evidence_text)
    pieces = [p.strip() for p in re.split(r"\.\.\.|…", q) if p.strip()]
    if not pieces or sum(len(p) for p in pieces) < 8:
        return False
    pos = 0
    for p in pieces:
        i = t.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def _normative(text: str) -> bool:
    low = text.lower()
    return any(c in low for c in VOCAB["normative"])


def verify_claim(claim: dict, entries: dict[str, dict], question: str) -> dict:
    kind = claim.get("kind", "fact")
    cites = claim.get("citations") or []
    res = {"kind": kind, "material": kind in MATERIAL, "citations": [], "problems": []}
    texts = []
    for c in cites:
        e = entries.get(c.get("evidence_id", ""))
        cv = {"evidence_id": c.get("evidence_id"), "id_ok": e is not None, "quote_ok": False, "unit_id": e["unit_id"] if e else None}
        if e:
            cv["quote_ok"] = quote_found(c.get("quote", ""), e["text"])
            texts.append(e["text"])
        res["citations"].append(cv)
    if not res["material"]:
        res["supported"] = None
        return res
    if not cites:
        res["problems"].append("no citation")
    if any(not c["id_ok"] for c in res["citations"]):
        res["problems"].append("cites an id that was not in the context")
    if any(c["id_ok"] and not c["quote_ok"] for c in res["citations"]):
        res["problems"].append("quote not found in the cited evidence")
    joined = norm(" \n ".join(texts))
    missing = sorted(a for a in anchors(claim.get("text", ""), question) if not _contains(joined, a))
    if missing:
        res["problems"].append(f"anchors not in the cited evidence: {', '.join(missing)}")
    claim_actions = action_mentions(claim.get("text", ""))
    ev_actions = action_mentions(" \n ".join(texts))
    q_actions = action_mentions(" \n ".join(c.get("quote", "") for c in cites))
    for action, neg in sorted(set(claim_actions)):
        if action in ("none", "escalate"):
            continue
        if action.startswith("term:") and not any(x[0] == action for x in ev_actions):
            continue                                  # a polarity term absent from the evidence is not an anchor
        pool = q_actions if any(x[0] == action for x in q_actions) else ev_actions   # the quote decides when it names the term
        same = [x for x in pool if x[0] == action and x[1] == neg]
        if not same:
            opposite = [x for x in pool if x[0] == action]
            res["problems"].append(f"{'negated ' if neg else ''}{action} {'has the opposite polarity in' if opposite else 'not in'} the cited evidence")
    cited = [entries[c["evidence_id"]] for c in res["citations"] if c["id_ok"]]
    affirmative = [a for a, n in claim_actions if not n and a not in ("none", "escalate") and not a.startswith("term:")]
    need = kind
    if kind in ("history", "fact", "cause") and affirmative and _normative(claim.get("text", "")):
        need = "procedure"
    ok_auth = {
        "procedure": lambda e: e.get("admissible", True) and e["role"] == "procedure" and e.get("tier") in (1, 2),
        "approval": lambda e: e.get("admissible", True) and (e["role"] == "approval" or (e["role"] == "procedure" and e.get("tier") in (1, 2))),
        "history": lambda e: e.get("admissible", True) and e["role"] in ("history", "change_fact"),
    }.get(need, lambda e: e.get("admissible", True))
    if cited and not any(ok_auth(e) for e in cited):
        res["problems"].append(f"no cited evidence may decide a {need} claim")
    res["held_to"] = need
    res["supported"] = not res["problems"]
    return res


def verify_answer(answer: dict, entries: dict[str, dict], question: str) -> dict:
    claims = [verify_claim(c, entries, question) for c in answer.get("claims", [])]
    mat = [c for c in claims if c["material"]]
    cits = [x for c in claims for x in c["citations"]]
    return {"claims": claims, "material": len(mat), "supported": sum(1 for c in mat if c["supported"]),
            "citations": len(cits), "citations_valid": sum(1 for x in cits if x["id_ok"] and x["quote_ok"])}


def bind(answer: dict, verdict: dict, entries: dict[str, dict], conflicts: list[dict], owner: dict | None) -> tuple[dict, list[str]]:
    """The governed final answer: supported claims only, an action only if a supported procedure claim backs it, the
    approval requirement from that procedure's metadata, escalation when the action touches an unresolved conflict."""
    final, notes = copy.deepcopy(answer), []
    kept = []
    for c, v in zip(answer.get("claims", []), verdict["claims"]):
        if v["material"] and not v["supported"]:
            notes.append(f"removed unsupported claim: {c.get('text', '')[:90]!r} ({'; '.join(v['problems'])})")
            continue
        kept.append(c)
    final["claims"] = kept
    ra = final.get("recommended_action") or {"action": "none", "target": "", "approval_required": False, "approver": ""}
    act = ra.get("action", "none")
    backing = []
    for c, v in zip(answer.get("claims", []), verdict["claims"]):
        if v.get("supported") and v.get("held_to") in ("procedure", "approval"):
            for x in v["citations"]:
                e = entries.get(x["evidence_id"])
                if not e or e["role"] != "procedure" or e.get("tier") not in (1, 2):
                    continue
                named = any(a == act and not neg for a, neg in action_mentions(e["text"].split("\n", 1)[-1]))
                if e.get("action") == act or named:   # the document's action, or one its cited section prescribes
                    backing.append(e)
    conflict_actions = {d["action"] for cf in conflicts for d in cf["documents"].values()}
    if act not in ("none", "escalate"):
        if conflicts and act in conflict_actions:
            notes.append(f"action {act} touches an unresolved conflict: escalated")
            final["status"] = "escalate"
            ra = {"action": "escalate", "target": (owner or {}).get("owner", "the owning team"), "approval_required": False, "approver": ""}
        elif not backing:
            notes.append(f"removed recommended action {act}: no supported procedure claim cites a procedure prescribing it")
            ra = {"action": "none", "target": "", "approval_required": False, "approver": ""}
            if final.get("status") == "answer":
                final["status"] = "partial"
        else:
            appr = next((b.get("approval") for b in backing if (b.get("approval") or "none") != "none"), "none")
            if appr != "none" and not ra.get("approval_required"):      # never let an answer drop a required approval
                notes.append(f"approval required by {backing[0]['doc_key']} ({appr}): the answer said none")
                ra = {**ra, "approval_required": True, "approver": ra.get("approver") or appr}
    final["recommended_action"] = ra
    if conflicts and final.get("status") == "answer":
        final["status"] = "escalate"
        notes.append("unresolved conflict in the evidence: status escalate")
    mat_kept = [c for c in kept if c.get("kind") in MATERIAL]
    if final.get("status") in ("answer", "partial") and not mat_kept:
        final["status"] = "abstain"
        notes.append("no supported material claim left: abstain")
    return final, notes
