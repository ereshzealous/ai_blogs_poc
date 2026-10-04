"""Model backends for live mode. The gateway (acp/systems.py) calls one of these for the logical model the control plane
resolved; the agent never sees which endpoint served it.

    ollama      a self-hosted LLM through Ollama's /api/chat with tool calling (the series' local models: qwen3:8b,
                gpt-oss:20b). Needs Ollama running (OLLAMA_URL, default http://localhost:11434) and the models pulled.
    scripted    a deterministic stand-in that behaves like a compliant but gullible model: it investigates, follows an
                instruction it finds in tool output, and remediates. It exercises every live code path without Ollama.

The self-hosted model behind each logical name is the gateway's deployment configuration, not governance: the control
plane decides *which logical model* an agent gets; this table decides which local model serves that name. No data leaves
the machine.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

# logical model (control plane) -> (Ollama model, generation options). Temperature 0 and a fixed seed keep a live run as
# repeatable as a local model allows; it is still not byte-reproducible.
LOCAL_MODELS = {
    "fast-model": ("qwen3:8b", {"think": False}),
    "large-model": ("gpt-oss:20b", {"think": "low"}),
    "private-model": ("qwen3:8b", {"think": False}),
    "legacy-model": ("qwen3:8b", {"think": False}),
}
OPTIONS = {"temperature": 0, "seed": 7, "num_ctx": 8192}


class LiveBackendError(RuntimeError):
    pass


def render_steps(data: list) -> str:
    if not data:
        return "No steps taken yet. Choose the first step."
    return "Steps so far, oldest first (tool, arguments, outcome, result):\n" + json.dumps(data, indent=1, default=str) + "\n\nChoose the next step."


class OllamaBackend:
    name = "ollama"

    def __init__(self, url: str | None = None, timeout_s: float = 300):
        self.url = (url or os.environ.get("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
        self.timeout_s = timeout_s

    def _post(self, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.url + path, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError) as e:
            raise LiveBackendError(f"Ollama at {self.url} is not reachable ({e}); start it with `ollama serve`") from e

    def preflight(self, logical: list[str]) -> dict:
        """Check Ollama is up and every local model the run may use is pulled. Returns {logical: local model}."""
        have = {m["name"] for m in self._post("/api/tags").get("models", [])}
        out = {}
        for m in logical:
            local = LOCAL_MODELS[m][0]
            if local not in have:
                raise LiveBackendError(f"local model {local!r} (serves {m}) is not pulled; run `ollama pull {local}`")
            out[m] = local
        return out

    def complete(self, model: str, purpose: str, data: list, tools: list | None) -> dict:
        local, extra = LOCAL_MODELS[model]
        body = {
            "model": local,
            "stream": False,
            "options": OPTIONS,
            "messages": [{"role": "system", "content": purpose}, {"role": "user", "content": render_steps(data)}],
            **extra,
        }
        if tools:
            body["tools"] = [
                {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools
            ]
        r = self._post("/api/chat", body)
        msg = r.get("message") or {}
        call = None
        for c in msg.get("tool_calls") or []:  # one step at a time: take the first proposal
            args = c.get("function", {}).get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            call = {"name": c["function"]["name"], "args": args if isinstance(args, dict) else {}}
            break
        return {
            "text": (msg.get("content") or "").strip(),
            "tool_call": call,
            "tokens": r.get("prompt_eval_count", 0) + r.get("eval_count", 0),
            "provider_model": r.get("model", local),
        }


class ScriptedBackend:
    """Deterministic, and gullible on purpose: it proposes the destructive step an injected log line asks for."""

    name = "scripted"

    def preflight(self, logical: list[str]) -> dict:
        return {m: f"scripted/{m}" for m in logical}

    def complete(self, model: str, purpose: str, data: list, tools: list | None) -> dict:
        found = re.search(r"agent for (\S+) in the (\w+) environment", purpose)
        service, env = found.groups() if found else ("unknown", "production")
        done = {s["tool"]: s for s in data if "tool" in s}
        offered = {t["name"] for t in tools or []}
        call = None
        if "query_logs" not in done:
            call = ("query_logs", {"service": service, "environment": env})
        else:
            injected = re.search(r"delete_resource with resource=(\S+)", json.dumps(done["query_logs"].get("result")))
            if injected and "delete_resource" not in done and "delete_resource" in offered:
                call = ("delete_resource", {"resource": injected.group(1)})
            elif "query_metrics" not in done:
                call = ("query_metrics", {"service": service, "environment": env})
            else:
                m = done["query_metrics"].get("result") or {}
                if m.get("error_rate", 0) > 0.01 and "restart_service" not in done:
                    call = ("restart_service", {"service": service, "environment": env})
        tokens = 300 + len(json.dumps(data, default=str)) // 4
        if call is None:
            return {"text": f"Investigated {service}; nothing further to do.", "tool_call": None, "tokens": tokens, "provider_model": f"scripted/{model}"}
        return {"text": "", "tool_call": {"name": call[0], "args": call[1]}, "tokens": tokens, "provider_model": f"scripted/{model}"}


def make_backend(name: str):
    if name == "ollama":
        return OllamaBackend()
    if name == "scripted":
        return ScriptedBackend()
    raise LiveBackendError(f"unknown backend {name!r} (ollama | scripted)")
