"""Model services: the model gateway, the routing policy and the providers behind it.

Agents ask for a capability class and a quality ("incident-reasoning", "high"); they never name a vendor or a model.  The
gateway filters the control plane's model registry by approval, class, quality, the tenant's residency, the data
classification of the request and the context window; orders the eligible models by priority; skips unhealthy ones; and
falls back to the next.  No eligible, healthy model: the call is refused (fail closed), never silently downgraded.

Providers in the published proof are deterministic *recorded* providers: RecordedModelA / RecordedModelB replay scripted
responses from JSONL tapes (scenarios/inc_4917/tapes/), matched on the request's purpose and content.  They are fixtures
that stand in for real models so the proof replays offline, byte for byte.  They do not measure model quality.  Token
counts are estimates (characters / 4) and cost units come from the registry's price table: synthetic accounting, used to
exercise budgets, not to report spend.  An opt-in live adapter (Ollama) exists for local experiments and is not part of
the published evidence.
"""

from __future__ import annotations

import json
import math
import os
import urllib.request
from pathlib import Path
from typing import Any

from agentic_platform.observability import span

QUALITY = {"low": 0, "medium": 1, "high": 2}


class ProviderUnavailable(Exception):
    pass


class TapeMiss(Exception):
    pass


class NoEligibleModel(Exception):
    code = "NO_ELIGIBLE_MODEL"


def est_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


class RecordedProvider:
    """Replays scripted responses.  A request that matches no tape entry is an error, never an improvised answer."""

    def __init__(self, name: str, tape: Path):
        self.name, self.tape = name, tape
        self.entries = [json.loads(l) for l in tape.read_text().splitlines() if l.strip()]

    def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        text = request["prompt"]
        for e in self.entries:
            w = e.get("when", {})
            if e["purpose"] != request["purpose"]:
                continue
            if "round" in w and w["round"] != request.get("round"):
                continue
            if any(s not in text for s in w.get("context_contains", [])):
                continue
            if any(s in text for s in w.get("context_lacks", [])):
                continue
            return {"tape_entry": e["id"], "content": e["response"]}
        raise TapeMiss(f"{self.name}: no tape entry for purpose={request['purpose']} round={request.get('round')}")


class OllamaProvider:
    """Opt-in live adapter (PAP_LIVE_MODEL=ollama:<model>).  Not used by the published proof."""

    def __init__(self, model: str, url: str = "http://127.0.0.1:11434"):
        self.name, self.model, self.url = f"ollama:{model}", model, url

    def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"model": self.model, "stream": False, "format": "json", "options": {"temperature": 0},
                           "messages": [{"role": "user", "content": request["prompt"] + "\nRespond with JSON only."}]}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(self.url + "/api/chat", body, {"Content-Type": "application/json"}), timeout=120) as r:
                return {"tape_entry": None, "content": json.loads(json.loads(r.read())["message"]["content"])}
        except OSError as exc:
            raise ProviderUnavailable(str(exc)) from exc


class ModelGateway:
    def __init__(self, root: Path, registry: dict[str, Any], faults_path: Path, tracer, evidence, budget, residency: str):
        self.root, self.reg, self.faults_path, self.t, self.ev, self.budget, self.residency = root, registry, faults_path, tracer, evidence, budget, residency

    def _faults(self) -> dict[str, Any]:
        return json.loads(self.faults_path.read_text()) if self.faults_path.exists() else {}

    def _provider(self, name: str, m: dict[str, Any]):
        live = os.environ.get("PAP_LIVE_MODEL")
        if live and live.startswith("ollama:"):
            return OllamaProvider(live.split(":", 1)[1])
        tape = self._faults().get("tape_override", {}).get(name, m["tape"])
        return RecordedProvider(m["provider"], self.root / tape)

    def route(self, cls: str, quality: str, classification: str, prompt_tokens: int, order: list[str]) -> list[dict[str, Any]]:
        out = []
        for name, m in self.reg["models"].items():
            why = []
            if not m["approved"]:
                why.append("not approved")
            if cls not in m["classes"]:
                why.append(f"no {cls} capability")
            if QUALITY[m["quality"]] < QUALITY[quality]:
                why.append("quality below request")
            if m["residency"] != self.residency:
                why.append(f"residency {m['residency']} != tenant {self.residency}")
            if order.index(classification) > order.index(m["max_classification"]):
                why.append(f"data classification {classification} above {m['max_classification']}")
            if prompt_tokens > m["context_window"]:
                why.append("context window too small")
            out.append({"model": name, "provider": m["provider"], "priority": m["priority"], "eligible": not why, "excluded_because": why})
        return sorted(out, key=lambda c: (not c["eligible"], c["priority"], c["model"]))

    def complete(self, *, workflow_id: str, purpose: str, cls: str, quality: str, classification: str, order: list[str], prompt: str,
                 round_: int | None = None) -> dict[str, Any]:
        ptoks = est_tokens(prompt)
        candidates = self.route(cls, quality, classification, ptoks, order)
        eligible = [c for c in candidates if c["eligible"]]
        attempts: list[dict[str, Any]] = []
        down = set(self._faults().get("unavailable", []))
        with span(self.t, f"model.route {cls}", **{"gen_ai.operation.name": "chat", "platform.model.capability_class": cls,
                                                   "platform.model.quality": quality, "platform.data.classification": classification}) as rs:
            for c in eligible:
                m = self.reg["models"][c["model"]]
                if c["model"] in down:
                    attempts.append({"model": c["model"], "outcome": "UNAVAILABLE", "detail": "health check failed (injected provider outage)"})
                    continue
                prov = self._provider(c["model"], m)
                # Budget is checked before the call; a refused call consumes nothing.
                cost = m["price"]["per_call"]
                self.budget.charge("model_call", 1, f"model:{purpose}", cost_units=cost)
                with span(self.t, f"chat {c['model']}", **{"gen_ai.operation.name": "chat", "gen_ai.request.model": c["model"],
                                                          "gen_ai.provider.name": prov.name, "platform.model.purpose": purpose}) as ms:
                    try:
                        resp = prov.complete({"purpose": purpose, "prompt": prompt, "round": round_})
                    except ProviderUnavailable as exc:
                        attempts.append({"model": c["model"], "outcome": "UNAVAILABLE", "detail": str(exc)})
                        continue
                    otoks = est_tokens(json.dumps(resp["content"]))
                    extra = math.ceil((ptoks + otoks) / 1000 * m["price"]["per_1k_tokens"])
                    if extra:
                        self.budget.s.charge(workflow_id, "cost_units", extra, f"tokens:{purpose}")
                    ms.set_attribute("gen_ai.response.model", c["model"])
                    ms.set_attribute("gen_ai.usage.input_tokens", ptoks)
                    ms.set_attribute("gen_ai.usage.output_tokens", otoks)
                    attempts.append({"model": c["model"], "outcome": "OK"})
                    decision = {"purpose": purpose, "requested": {"class": cls, "quality": quality, "classification": classification,
                                                                  "residency": self.residency}, "candidates": candidates, "attempts": attempts,
                                "chosen": c["model"], "fallback": len(attempts) > 1, "tape_entry": resp["tape_entry"],
                                "usage": {"input_tokens_est": ptoks, "output_tokens_est": otoks, "cost_units": cost + extra}}
                    rs.set_attribute("platform.model.chosen", c["model"])
                    rs.set_attribute("platform.model.fallback", decision["fallback"])
                    self.ev.record("model.routed", {k: decision[k] for k in ("purpose", "chosen", "fallback", "attempts", "usage", "tape_entry")},
                                   workflow_id=workflow_id, category="model_io",
                                   detail={**decision, "prompt": prompt, "response": resp["content"]})
                    return {"content": resp["content"], "routing": decision}
            decision = {"purpose": purpose, "candidates": candidates, "attempts": attempts, "chosen": None}
            self.ev.record("model.refused", {"purpose": purpose, "attempts": attempts, "code": "NO_ELIGIBLE_MODEL"}, workflow_id=workflow_id,
                           category="model_io", detail={**decision, "prompt": prompt})
            raise NoEligibleModel(f"NO_ELIGIBLE_MODEL for {cls}/{quality}/{classification}: {attempts}")
