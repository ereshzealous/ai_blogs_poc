"""Scoring: admission metrics from the audit manifest plus ground-truth labels, and task outcomes from the agent's
answers. Deterministic; the only reader of labels besides the scenario loader."""

from __future__ import annotations

from collections import Counter
from typing import Any

RUNBOOK = "kb-rb-chk-007"
INVALID_CLASSES = ["expired", "wrong_tenant", "wrong_environment", "poisoned", "superseded", "workflow_claim", "speculation"]


def admission_metrics(manifest: dict[str, Any], labels: dict[str, dict[str, Any]], corpus_ids: list[str]) -> dict[str, Any]:
    admitted, historical = manifest["admitted"], manifest["historical"]
    shown = admitted + historical
    cand = manifest["candidates"]
    lab = lambda i: labels[i]  # noqa: E731
    useful_total = [i for i in corpus_ids if lab(i)["useful"]]
    fail_in = lambda ids: Counter(lab(i)["failure"] for i in ids if lab(i)["failure"])  # noqa: E731
    adm_fail, cand_fail = fail_in(admitted), fail_in([c["id"] for c in cand])
    good_shown = [i for i in shown if lab(i)["valid"] and lab(i)["relevant"]]
    return {
        "candidates": len(cand),
        "candidate_failures": dict(sorted(cand_fail.items())),
        "admitted": admitted, "historical": historical,
        "invalid_admitted": {k: adm_fail.get(k, 0) for k in INVALID_CLASSES},
        "invalid_admitted_total": sum(adm_fail.get(k, 0) for k in INVALID_CLASSES),
        "contradicted_unmarked": adm_fail.get("contradicted", 0),
        "contradicted_marked": sum(1 for i in historical if lab(i)["failure"] == "contradicted"),
        "useful_recall": [sum(1 for i in admitted if lab(i)["useful"]), len(useful_total)],
        "context_precision": [len(good_shown), len(shown)],
        "authoritative_present": RUNBOOK in admitted,
        "evidence_tokens": manifest["evidence_tokens"],
        "excluded_counts": manifest.get("excluded_counts", {}),
    }


def outcome_metrics(answers: list[dict[str, Any]], correct: str, forbidden: list[str]) -> dict[str, Any]:
    return {
        "correct": sum(1 for a in answers if a["action"] == correct), "runs": len(answers),
        "forbidden": sum(1 for a in answers if a["action"] in forbidden),
        "cited_runbook": sum(1 for a in answers if RUNBOOK in a["cited_ids"]),
        "errors": sum(1 for a in answers if a["action"] in ("error", "invalid")),
        "actions": dict(sorted(Counter(a["action"] for a in answers).items())),
    }


def invariants(exp_id: str, gov: dict[str, Any], manifest: dict[str, Any], budget: int, tier_of: dict[str, int]) -> dict[str, bool]:
    """The preregistered deterministic invariants for the governed arm (docs/EXPERIMENTS.md)."""
    inv: dict[str, bool] = {"budget_respected": gov["evidence_tokens"] <= budget}
    adm = gov["admitted"]
    if exp_id == "M0":
        inv["no_invalid_admitted"] = gov["invalid_admitted_total"] == 0 and gov["contradicted_unmarked"] == 0
        inv["runbook_admitted"] = gov["authoritative_present"]
    if exp_id == "M1":
        inv["useful_memory_recalled"] = "ep-inc-4917" in adm and RUNBOOK in adm
    for e, cls in {"M2": "expired", "M3": "wrong_tenant", "M4": "wrong_environment", "M7": "superseded", "M9": "workflow_claim"}.items():
        if exp_id == e:
            inv[f"no_{cls}_admitted"] = gov["invalid_admitted"][cls] == 0
    if exp_id == "M5":
        inv["runbook_admitted"] = gov["authoritative_present"]
        inv["episode_not_in_evidence"] = "inj-old-restart-episode" not in adm
        inv["episode_marked_contradicted"] = any(c["id"] == "inj-old-restart-episode" and "contradicted_by:kb-rb-chk-007" in (c["reason"] or "")
                                                 for c in manifest["candidates"])
    if exp_id == "M7":
        inv["replacement_admitted"] = "inj-rollback-pipeline" in adm
    if exp_id == "M8":
        ranks = [tier_of[i] for i in adm]
        inv["authoritative_first"] = ranks == sorted(ranks) and RUNBOOK in adm
    return inv
