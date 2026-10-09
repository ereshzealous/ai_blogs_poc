"""The model gateway: one structured proposal per call, through the F2/T3 record/replay tape.

    LINEAGE_TAPE=record:<dir>   forward to Ollama; append request hash + response to <dir>/model_tape.jsonl
    LINEAGE_TAPE=replay:<dir>   answer from the tape; an unknown request is an error, never a fresh call
    (unset)                     talk to Ollama directly

The tape key is the sha256 of the canonical request, so a replay succeeds only if the code asks the model exactly what it
asked during the recording.  Consumption is appended to a side file, so a SIGKILLed and restarted process continues where it
stopped.

What the gateway records about a call is decision evidence, not reasoning: provider, model, the model's digest as the model
server reports it, prompt-template version and digest, agent-config version, sampling options, input digest, token counts,
latency and the structured output the model was asked for (the proposal and its one-to-two sentence rationale).  Thinking
is disabled in the request, and no free-text reasoning is kept.  The prompt itself is not stored anywhere but the tape; its
digest is.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

from opentelemetry import trace
from opentelemetry.trace import SpanKind

from . import semconv as sc
from .common import append_jsonl, jl, load, sha

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
CP = load("control_plane.toml")


class TapeMiss(RuntimeError):
    pass


def call(path: str, body: dict | None, caller: str) -> tuple[dict, dict]:
    """Returns (response json, tape meta).  GET when body is None."""
    spec = os.environ.get("LINEAGE_TAPE", "")
    mode, _, directory = spec.partition(":")
    h = sha({"path": path, "body": body})
    if mode == "replay":
        d = Path(directory)
        answers = [r for r in jl(d / "model_tape.jsonl") if r["hash"] == h]
        used = sum(1 for r in jl(d / "model_tape.consumed.jsonl") if r["hash"] == h)
        if used >= len(answers):
            append_jsonl(d / "model_tape.misses.jsonl", {"hash": h, "caller": caller, "pid": os.getpid()}, fsync=True)
            raise TapeMiss(f"replay: no recorded answer for {path} request {h[:12]} from {caller}")
        append_jsonl(d / "model_tape.consumed.jsonl", {"hash": h, "i": used, "pid": os.getpid()}, fsync=True)
        rec = answers[used]
        return json.loads(rec["response"]), {"replayed": True, "wall_s": rec.get("wall_s"), "hash": h}
    t0 = time.perf_counter()
    req = urllib.request.Request(f"{OLLAMA}{path}", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=600) as r:
        raw = r.read().decode()
    wall = round(time.perf_counter() - t0, 3)
    if mode == "record":
        append_jsonl(Path(directory) / "model_tape.jsonl", {"hash": h, "path": path, "response": raw, "wall_s": wall,
                                                            "caller": caller, "pid": os.getpid(), "ts": time.time()}, fsync=True)
    return json.loads(raw), {"replayed": False, "wall_s": wall, "hash": h}


def model_digest(model: str, caller: str) -> str:
    tags, _ = call("/api/tags", None, caller)
    for m in tags.get("models", []):
        if m.get("name") == model or m.get("model") == model:
            return "sha256:" + m["digest"]
    return "unknown"


TOOLS = [{
    "type": "function",
    "function": {
        "name": "propose_action",
        "description": "Propose one remediation action for the platform to authorize.",
        "parameters": {
            "type": "object",
            "properties": {
                "capability": {"type": "string", "enum": ["deployment.rollback", "pods.restart", "diagnostics.run", "noAction"]},
                "service": {"type": "string"},
                "environment": {"type": "string", "enum": ["production", "staging"]},
                "to_version": {"type": "string", "description": "Target version for deployment.rollback, e.g. v4.17.2. Empty otherwise."},
                "rationale": {"type": "string", "description": "One or two sentences: why this action, citing the evidence."},
            },
            "required": ["capability", "service", "environment", "to_version", "rationale"],
        },
    },
}]


def config(ref: str) -> dict:
    """'incident-agent-prod@8' -> the resolved agent configuration, with its prompt template and digests."""
    ver = ref.split("@")[1]
    c = dict(CP["agent_configs"][ver])
    tver = c["prompt_template"].split("@")[1]
    system = CP["prompt_templates"][tver]["system"]
    c.update(ref=ref, system=system, prompt_template_digest="sha256:" + sha(system), config_digest="sha256:" + sha({k: v for k, v in c.items() if k != "system"}))
    return c


def propose(cfg: dict, context_text: str, caller: str, agent: dict) -> dict:
    """One model call -> {proposal, meta}.  meta is everything the evidence and the span may say about the call."""
    tracer = trace.get_tracer("lineage")
    body = {"model": cfg["model"], "stream": False, "think": False,
            "options": {"temperature": cfg["temperature"], "seed": cfg["seed"], "num_ctx": cfg["num_ctx"]},
            "messages": [{"role": "system", "content": cfg["system"]}, {"role": "user", "content": context_text}], "tools": TOOLS}
    with tracer.start_as_current_span(f"chat {cfg['model']}", kind=SpanKind.CLIENT, attributes={
            sc.OP: "chat", sc.PROVIDER: "ollama", sc.REQ_MODEL: cfg["model"], sc.TEMPERATURE: float(cfg["temperature"]),
            sc.SEED: int(cfg["seed"]), sc.AGENT_NAME: agent["id"]}) as span:
        t0 = time.perf_counter()
        data, tape = call("/api/chat", body, caller)
        latency = round((time.perf_counter() - t0) * 1000, 1)
        span.set_attribute(sc.RESP_MODEL, data.get("model", ""))
        span.set_attribute(sc.IN_TOKENS, int(data.get("prompt_eval_count", 0)))
        span.set_attribute(sc.OUT_TOKENS, int(data.get("eval_count", 0)))
        span.set_attribute(sc.FINISH, [data.get("done_reason", "stop")])
    proposal = parse(data)
    meta = {"provider": "ollama", "model": data.get("model", cfg["model"]), "input_digest": "sha256:" + sha(body["messages"]),
            "input_tokens": int(data.get("prompt_eval_count", 0)), "output_tokens": int(data.get("eval_count", 0)),
            "latency_ms": latency if not tape["replayed"] else round((tape["wall_s"] or 0) * 1000, 1),
            "finish_reason": data.get("done_reason", "stop"), "replayed": tape["replayed"],
            "options": body["options"], "raw_content_chars": len((data.get("message") or {}).get("content") or "")}
    return {"proposal": proposal, "meta": meta}


def parse(data: dict) -> dict:
    import re
    msg = data.get("message") or {}
    for c in msg.get("tool_calls") or []:
        fn = c.get("function", {})
        if fn.get("name") == "propose_action":
            args = fn.get("arguments")
            args = json.loads(args) if isinstance(args, str) else dict(args or {})
            return clean(args)
    m = re.search(r"\{.*\}", msg.get("content") or "", re.S)
    if m:
        try:
            return clean(json.loads(m.group(0)))
        except ValueError:
            pass
    return {"capability": "noAction", "service": "", "environment": "production", "to_version": "",
            "rationale": "(the model returned no parsable proposal)", "parse_error": True}


def clean(a: dict) -> dict:
    out = {k: str(a.get(k, "") or "") for k in ("capability", "service", "environment", "to_version", "rationale")}
    out["rationale"] = out["rationale"][:400]
    return out
