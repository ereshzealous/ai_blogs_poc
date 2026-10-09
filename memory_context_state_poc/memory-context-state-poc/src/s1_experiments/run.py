"""Runs every preregistered experiment and writes runs/<run-id>/.

    record  live Ollama; every model and embedding response is recorded to runs/<run-id>/model-recordings/
    replay  answers come from runs/<run-id>/model-recordings/; no model server; output goes to runs/<run-id>/replay/

Per experiment: build the corpus, retrieve the same 20 candidates for every arm, admit (naive, naive_k5, governed),
render prompts with identical workflow and conversation sections, ask the agent once per seed per arm, score.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from governed_memory.context.assembler import governed_admission, naive_admission, render_messages
from governed_memory.context.manifest import audit_manifest
from governed_memory.models.authority import AuthorityPolicy
from governed_memory.platform.layered_adapter import (make_gateway, session_store, setup_tracing, span, workflow_facts,
                                                     workflow_store)
from governed_memory.retrieval.semantic import SemanticIndex
from governed_memory.stores.memory_store import GovernedMemoryStore, NaiveMemoryStore
from governed_memory.write_policy.policy import WritePolicy, naive_write
from s1_experiments import freeze
from s1_experiments.agent import decide
from s1_experiments.scenario import ROOT, Scenario
from s1_experiments.score import admission_metrics, invariants, outcome_metrics

ARMS = ["naive", "governed"]


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str) + "\n")


class Runner:
    def __init__(self, run_dir: Path, sc: Scenario):
        self.dir, self.sc, self.cfg = run_dir, sc, sc.config
        self.policy = AuthorityPolicy.load()
        self.results: list[dict[str, Any]] = []
        self.gateways: dict[int, Any] = {}

    def gateway(self, seed: int):
        if seed not in self.gateways:
            self.gateways[seed] = make_gateway(self.dir / "state" / "model_usage.db", model=self.cfg["model"],
                                               embedding_model=self.cfg["embedding_model"], seed=seed)
        return self.gateways[seed]

    def workflow_and_conversation(self, exp_id: str, workflow_key: str) -> tuple[dict, list]:
        """Workflow state and conversation come from F2's stores, by key, the same way for every arm."""
        wf_cfg = self.cfg["workflows"][workflow_key]
        db = self.dir / "state" / f"{exp_id}.db"
        ws, ss = workflow_store(db), session_store(db)
        if ws.get(wf_cfg["id"]) is None:
            ws.create({"id": wf_cfg["id"], "name": "incident-remediation", "incident_id": wf_cfg["incident_id"], "status": wf_cfg["status"],
                       "current_step": wf_cfg["current_step"], "channel": "cli", "requested_by": "alice",
                       "session_id": self.cfg["query_scope"]["session"]})
            sid = ss.open("cli", "alice", self.cfg["query_scope"]["session"])
            for m in self.cfg["conversation"]:
                ss.append(sid, m["role"], m["content"])
        facts = workflow_facts(ws, wf_cfg["id"], note=wf_cfg["note"])
        conv = [{"role": m["role"], "content": m["content"]} for m in ss.history(self.cfg["query_scope"]["session"])]
        return facts, conv

    async def ask(self, exp_id: str, arm: str, messages: list[dict[str, str]], correct: str) -> list[dict[str, Any]]:
        answers = []
        for seed in self.cfg["seeds"]:
            t0 = time.perf_counter()
            with span("s1.decide", **{"s1.experiment": exp_id, "s1.arm": arm, "s1.seed": seed}):
                a = await decide(self.gateway(seed), messages, self.sc.prompt["schema"], caller=f"{exp_id}/{arm}/seed{seed}")
            a |= {"experiment": exp_id, "arm": arm, "seed": seed, "correct": a["action"] == correct, "wall_ms": round((time.perf_counter() - t0) * 1000)}
            answers.append(a)
            self.results.append(a)
            print(f"  {exp_id} {arm:8s} seed {seed:2d}: {a['action']}", flush=True)
        return answers

    async def experiment(self, exp_id: str, index: SemanticIndex, corpus: dict[str, list], query_name: str, workflow_key: str,
                         correct: str) -> dict[str, Any]:
        """corpus: arm -> records (identical for every arm except M6B)."""
        q = self.sc.query(query_name)
        budget, n = self.cfg["evidence_budget_tokens"], self.cfg["candidates_n"]
        facts, conv = self.workflow_and_conversation(exp_id, workflow_key)
        out: dict[str, Any] = {"title": self.sc.experiments.get(exp_id, {}).get("title", exp_id), "correct_action": correct, "arms": {}}
        cand_cache: dict[tuple, list] = {}
        for arm in ["naive", "naive_k5", "governed"]:
            recs = corpus["governed" if arm == "governed" else "naive"]
            key = tuple(sorted(r.id for r in recs))
            if key not in cand_cache:
                await index.build(recs)
                cand_cache[key] = await index.candidates(q.text, n)
            cands = cand_cache[key]
            with span("s1.admit", **{"s1.experiment": exp_id, "s1.arm": arm}):
                if arm == "governed":
                    adm = governed_admission(cands, q, self.policy, budget, corpus={r.id: r for r in recs})
                elif arm == "naive_k5":
                    adm = naive_admission(cands, budget, k=self.cfg["sensitivity_k"])
                else:
                    adm = naive_admission(cands, budget)
            manifest = audit_manifest(adm)
            _dump(self.dir / "audit" / f"{exp_id}-{arm}.json", manifest)
            metrics = admission_metrics(manifest, self.labels, [r.id for r in recs])
            entry: dict[str, Any] = {"admission": metrics}
            if arm in ARMS:
                messages = render_messages(self.sc.prompt, q.text, facts, conv, adm, arm)
                (self.dir / "prompts").mkdir(parents=True, exist_ok=True)
                (self.dir / "prompts" / f"{exp_id}-{arm}.txt").write_text(messages[0]["content"] + "\n\n-----\n\n" + messages[1]["content"])
                answers = await self.ask(exp_id, arm, messages, correct)
                entry["outcome"] = outcome_metrics(answers, correct, self.sc.prompt["forbidden_actions"])
            if arm == "governed":
                tier_of = {r.id: self.policy.tier(r).rank for r in recs}
                entry["invariants"] = invariants(exp_id, metrics, manifest, budget, tier_of)
                entry["workflow_status_in_prompt"] = facts["status"]
            out["arms"][arm] = entry
        return out

    async def m6(self, index: SemanticIndex) -> dict[str, Any]:
        cfg, clock = self.cfg["m6"], self.sc.clock
        db = self.dir / "state" / "m6.db"
        naive_store, gov_store, wp = NaiveMemoryStore(db), GovernedMemoryStore(db), WritePolicy.load()
        writes = []
        for e in self.sc.write_events:
            nr = naive_write(e, clock)
            naive_store.put(nr)
            d = wp.apply(e, clock)
            if d.persisted:
                gov_store.put(d.record)
            writes.append({"event": e["id"], "kind": e["kind"], "label": e["label"], "naive_persisted": True,
                           "governed_persisted": d.persisted, "governed_reason": d.reason,
                           "governed_tier": self.policy.tier(d.record).label if d.persisted else None,
                           "governed_scope": vars(d.record.scope) if d.persisted else None,
                           "governed_expires_at": d.record.expires_at.isoformat() if d.persisted else None})
            for rid, label in ((nr.id, e["label"]), (f"mem-{e['id']}", e["label"])):
                failure = {"poisoned": "poisoned", "speculation": "speculation"}.get(label)
                self.labels[rid] = {"valid": failure is None, "relevant": True, "useful": label == "useful", "failure": failure}
        naive_recs = self.sc.base + [naive_write(e, clock) for e in self.sc.write_events]
        gov_recs = self.sc.base + gov_store.all()
        m6b = await self.experiment("M6B", index, {"naive": naive_recs, "governed": gov_recs}, cfg["query"], cfg["workflow"], cfg["correct_action"])
        user_mem = next((w for w in writes if w["event"] == "evt-user-assertion"), {})
        m6b["arms"]["governed"]["invariants"] |= {
            "assertion_contextual_only": user_mem.get("governed_tier") == "contextual",
            "assertion_session_scoped": (user_mem.get("governed_scope") or {}).get("session") == cfg["write_session"],
            "assertion_not_in_later_context": "mem-evt-user-assertion" not in m6b["arms"]["governed"]["admission"]["admitted"],
            "unverified_tool_not_persisted": not next(w for w in writes if w["event"] == "evt-unverified-tool")["governed_persisted"],
            "speculation_not_persisted": not next(w for w in writes if w["event"] == "evt-model-speculation")["governed_persisted"],
        }
        _dump(self.dir / "audit" / "M6A-writes.json", writes)
        return {"M6A": {"title": "Memory write path", "writes": writes}, "M6B": m6b}

    async def run(self) -> dict[str, Any]:
        self.labels = dict(self.sc.labels)
        embedder = self.gateway(self.cfg["seeds"][0])
        index = SemanticIndex(embedder)
        # Embed the whole frozen corpus (plus the M6 writer outputs) once, in a fixed order.
        clock = self.sc.clock
        m6_texts = [naive_write(e, clock) for e in self.sc.write_events] + [d.record for e in self.sc.write_events
                                                                          if (d := WritePolicy.load().apply(e, clock)).persisted]
        await index.build(self.sc.all_records() + m6_texts)
        experiments: dict[str, Any] = {}
        for exp_id, exp in self.sc.experiments.items():
            print(f"{exp_id} · {exp['title']}", flush=True)
            corpus = self.sc.corpus(exp_id)
            experiments[exp_id] = await self.experiment(exp_id, index, {"naive": corpus, "governed": corpus}, exp["query"], exp["workflow"], exp["correct_action"])
        print("M6 · Memory write path", flush=True)
        experiments |= await self.m6(index)
        for g in self.gateways.values():
            await g.close()
        return experiments


def summarize(run_id: str, mode: str, hashes: dict[str, str], cfg: dict[str, Any], experiments: dict[str, Any]) -> dict[str, Any]:
    inv = {e: v["arms"]["governed"].get("invariants", {}) for e, v in experiments.items() if "arms" in v}
    return {
        "run_id": run_id, "mode": mode, "frozen_digest": freeze.digest(hashes),
        "model": cfg["model"], "embedding_model": cfg["embedding_model"], "seeds": cfg["seeds"],
        "candidates_n": cfg["candidates_n"], "evidence_budget_tokens": cfg["evidence_budget_tokens"], "sensitivity_k": cfg["sensitivity_k"],
        "clock": cfg["clock"],
        "invariants_passed": sum(all(v.values()) for v in inv.values() if v), "invariants_total": sum(1 for v in inv.values() if v),
        "experiments": experiments,
    }


def execute(run_id: str, mode: str, allow_unfrozen: bool = False) -> dict[str, Any]:
    changed = freeze.check()
    if changed and not allow_unfrozen:
        raise SystemExit("frozen inputs changed since `s1 freeze`:\n  " + "\n  ".join(changed))
    run_dir = ROOT / "runs" / run_id
    rec_dir = run_dir / "model-recordings"
    out_dir = run_dir / "replay" if mode == "replay" else run_dir
    if mode == "record" and (rec_dir / "chat.jsonl").exists():
        raise SystemExit(f"{rec_dir} already has a recording; choose a new run id")
    if mode in ("record", "replay"):
        os.environ["LAP_MODEL_TRAFFIC"] = f"{mode}:{rec_dir}"
    out_dir.mkdir(parents=True, exist_ok=True)
    setup_tracing(out_dir)
    sc = Scenario.load()
    hashes = freeze.current_hashes()
    _dump(out_dir / "hashes.json", hashes)
    _dump(out_dir / "config.json", sc.config)
    t0 = time.time()
    runner = Runner(out_dir, sc)
    experiments = asyncio.run(runner.run())
    summary = summarize(run_id, mode, hashes, sc.config, experiments)
    summary["wall_seconds"] = round(time.time() - t0)
    _dump(out_dir / "summary.json", summary)
    with (out_dir / "results.jsonl").open("w") as f:
        for r in runner.results:
            f.write(json.dumps(r, default=str) + "\n")
    return summary
