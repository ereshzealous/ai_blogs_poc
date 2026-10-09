"""Answer generation: the same prompt contract for every arm, a local model over Ollama, and a tape.

Modes
- live:     call Ollama (/api/chat, structured JSON output), append the exchange to the run's tape;
- replay:   read the tape only, keyed by sha256 of (model, messages, options, schema); a missing key is an error;
- scripted: a deterministic surrogate for tests and smoke runs. It is NOT a model: it never produces a reported number.

The tape records the full request, the raw response, the server's token counts and timings, so a reader can audit every
answer without running a model.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

from knowledge_rag.contracts import ACTIONS, ANSWER_SCHEMA, Answer
from knowledge_rag.util import canonical, config, sha256

PROMPTS = config("prompts.yaml")
VOCAB = config("vocabulary.yaml")
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


class TapeMissing(KeyError):
    """Replay asked for a model exchange the tape does not hold."""


def messages_for(question: str, principal, tenant: str, environment: str, as_of: str, evidence: str) -> list[dict]:
    user = PROMPTS["user"].format(question=question, display=principal.display, role=principal.role, tenant=tenant,
                                  environment=environment, as_of=as_of, evidence=evidence or "(no evidence)",
                                  actions=", ".join(ACTIONS))
    return [{"role": "system", "content": PROMPTS["system"]}, {"role": "user", "content": user}]


class ModelClient:
    def __init__(self, profile: dict, mode: str, tape: Path | None) -> None:
        if mode not in ("live", "replay", "scripted"):
            raise ValueError(mode)
        self.profile, self.mode, self.tape_path = profile, mode, tape
        self.tape: dict[str, dict] = {}
        if tape and tape.exists():
            for line in tape.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.tape[r["key"]] = r

    def request(self, messages: list[dict], seed: int) -> dict:
        p = self.profile
        return {"model": p["model"], "messages": messages, "stream": False, "format": ANSWER_SCHEMA, "think": p["think"],
                "options": {"temperature": p["temperature"], "seed": seed, "num_ctx": p["num_ctx"]}}

    def key(self, req: dict) -> str:
        return sha256(canonical(req))

    def complete_raw(self, messages: list[dict], schema: dict, seed: int) -> dict:
        """A recorded exchange with an arbitrary JSON schema (the D2 judge). Same tape rules as complete()."""
        req = {**self.request(messages, seed), "format": schema}
        k = self.key(req)
        if k in self.tape:
            return {"key": k, "content": self.tape[k]["content"], "usage": self.tape[k]["usage"]}
        if self.mode != "live":
            raise TapeMissing(f"judge exchange {k[:12]} not on the tape {self.tape_path}")
        return self._call(req, k, seed)

    def _call(self, req: dict, k: str, seed: int) -> dict:
        body = json.dumps(req).encode()
        http = urllib.request.Request(f"{OLLAMA}/api/chat", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(http, timeout=900) as resp:
            out = json.loads(resp.read())
        msg = out.get("message", {})
        usage = {"prompt_eval_count": out.get("prompt_eval_count"), "eval_count": out.get("eval_count"),
                 "total_duration_ns": out.get("total_duration"), "load_duration_ns": out.get("load_duration")}
        rec = {"key": k, "model": self.profile["model"], "digest": self.profile.get("digest"), "seed": seed,
               "request": req, "content": msg.get("content", ""), "thinking": msg.get("thinking"), "usage": usage}
        self.tape[k] = rec
        if self.tape_path:
            self.tape_path.parent.mkdir(parents=True, exist_ok=True)
            with self.tape_path.open("a") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"key": k, "content": rec["content"], "usage": usage}

    def complete(self, messages: list[dict], seed: int) -> dict:
        """Returns {key, content, parsed (Answer dict or None), parse_error, usage, from_tape}."""
        req = self.request(messages, seed)
        k = self.key(req)
        if self.mode == "scripted":
            content = json.dumps(scripted_answer(messages[-1]["content"]))
            return self._result(k, content, {"prompt_eval_count": None, "eval_count": None, "total_duration_ns": None}, True)
        if k in self.tape:
            r = self.tape[k]
            return self._result(k, r["content"], r["usage"], True)
        if self.mode == "replay":
            raise TapeMissing(f"model exchange {k[:12]} not on the tape {self.tape_path}")
        out = self._call(req, k, seed)
        return self._result(k, out["content"], out["usage"], False)

    @staticmethod
    def _result(k: str, content: str, usage: dict, from_tape: bool) -> dict:
        try:
            parsed = Answer.model_validate(json.loads(content)).model_dump()
            err = None
        except Exception as e:  # noqa: BLE001 - any malformed model output is recorded, never repaired
            parsed, err = None, f"{type(e).__name__}: {str(e)[:200]}"
        return {"key": k, "content": content, "parsed": parsed, "parse_error": err, "usage": usage, "from_tape": from_tape}


# ---- the scripted surrogate (tests and smoke runs only) -------------------------------------------------------------------
_EVID = re.compile(r"^\[(E\d+)\] (.*)$", re.M)


def scripted_answer(user_prompt: str) -> dict:
    """A stand-in with fixed, simple behaviour: take the first evidence block whose text affirmatively names an action
    and recommend that action, quoting its first sentence. With no such block, abstain. It reads no metadata, so the same
    rule runs on both arms; it exists to exercise the pipeline, never to estimate model behaviour."""
    ev = user_prompt.split("EVIDENCE:\n", 1)[-1].split("\n\nReturn JSON", 1)[0]
    blocks = re.split(r"\n\n(?=\[E\d+\])", ev)
    for b in blocks:
        m = re.match(r"\[(E\d+)\]", b)
        if not m:
            continue
        body = b.split("\n", 1)[-1] if "\n" in b else b
        low = body.lower()
        for action, terms in VOCAB["actions"].items():
            for t in terms:
                i = low.find(t)
                if i >= 0 and not any(low[max(0, i - 12):i].endswith(n) or n in low[max(0, i - 12):i] for n in VOCAB["negations"]):
                    sent = re.split(r"(?<=[.!?])\s", body.strip())[0][:160]
                    return {"status": "answer", "summary": sent, "recommended_action": {"action": action, "target": "", "approval_required": False, "approver": ""},
                            "claims": [{"text": sent, "kind": "procedure", "citations": [{"evidence_id": m.group(1), "quote": sent}]}],
                            "gaps": [], "conflicts": []}
    return {"status": "abstain", "summary": "No evidence prescribes an action.", "recommended_action": {"action": "none", "target": "", "approval_required": False, "approver": ""},
            "claims": [], "gaps": ["no evidence"], "conflicts": []}
