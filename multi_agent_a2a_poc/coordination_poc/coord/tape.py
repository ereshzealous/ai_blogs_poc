"""Record/replay of model traffic at the HTTP boundary to Ollama.  Every architecture and every agent process uses this same transport (copied from F2 recordreplay/tape.py).

    C1_TAPE=record:<dir>   forward every request to Ollama and append request hash + response to <dir>/model_tape.jsonl
    C1_TAPE=replay:<dir>   answer every request from the tape; an unknown request is an error, never a fresh model call
    (unset)                talk to Ollama directly, no tape

The key is the sha256 of the canonical request body, so a replay only succeeds when the code asks the model exactly
what it asked during the recording.  Identical requests are answered in recorded order.  Consumption is appended to a
side file, so a process that is SIGKILLed and restarted continues where it stopped, exactly as in the recording.
Every served call (recorded or replayed) is appended to <dir>/model_calls.jsonl with its token counts: a neutral
model-call ledger, independent of the platform store.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

_lock = threading.Lock()


def request_hash(path: str, body: bytes) -> str:
    try:
        canon = json.dumps(json.loads(body), sort_keys=True, separators=(",", ":"))
    except ValueError:
        canon = body.decode(errors="replace")
    return hashlib.sha256(f"{path}\n{canon}".encode()).hexdigest()


def _append(path: Path, rec: dict[str, Any]) -> None:
    with _lock, open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


class TapeMiss(RuntimeError):
    pass


class TapeTransport(httpx.AsyncBaseTransport):
    def __init__(self, mode: str, directory: str | Path, inner: httpx.AsyncBaseTransport | None = None):
        if mode not in ("record", "replay"):
            raise ValueError(mode)
        self.mode, self.dir = mode, Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.tape, self.consumed, self.ledger = self.dir / "model_tape.jsonl", self.dir / "model_tape.consumed.jsonl", self.dir / "model_calls.jsonl"
        self.inner = inner or httpx.AsyncHTTPTransport()
        self._answers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._used: dict[str, int] = defaultdict(int)
        if mode == "replay":
            for line in self.tape.read_text().splitlines() if self.tape.exists() else []:
                rec = json.loads(line)
                self._answers[rec["hash"]].append(rec)
            for line in self.consumed.read_text().splitlines() if self.consumed.exists() else []:
                self._used[json.loads(line)["hash"]] += 1

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        h = request_hash(request.url.path, body)
        caller = request.headers.get("x-c1-caller", "")
        if request.url.path != "/api/chat":  # tags / version probes are not model calls
            return await self.inner.handle_async_request(request) if self.mode == "record" else httpx.Response(200, json={"models": []})
        t0 = time.perf_counter()
        if self.mode == "record":
            resp = await self.inner.handle_async_request(request)
            content = await resp.aread()
            rec = {"hash": h, "status": resp.status_code, "response": content.decode(), "wall_s": round(time.perf_counter() - t0, 3),
                   "model": json.loads(body).get("model"), "caller": caller, "pid": os.getpid(), "ts": time.time()}
            _append(self.tape, rec)
            self._ledger(rec, replayed=False)
            return httpx.Response(resp.status_code, content=content, headers={"content-type": "application/json"}, request=request)
        answers = self._answers.get(h, [])
        idx = self._used[h]
        if idx >= len(answers):
            _append(self.dir / "model_tape.misses.jsonl", {"hash": h, "caller": caller, "pid": os.getpid(), "ts": time.time()})
            raise TapeMiss(f"replay: no recorded answer for request {h[:12]} from {caller or 'unknown caller'}")
        self._used[h] += 1
        _append(self.consumed, {"hash": h, "i": idx, "pid": os.getpid()})
        rec = dict(answers[idx], caller=caller, pid=os.getpid(), ts=time.time())
        self._ledger(rec, replayed=True)
        return httpx.Response(rec["status"], content=rec["response"].encode(), headers={"content-type": "application/json"}, request=request)

    def _ledger(self, rec: dict[str, Any], *, replayed: bool) -> None:
        try:
            data = json.loads(rec["response"])
        except ValueError:
            data = {}
        msg = data.get("message") or {}
        _append(self.ledger, {"hash": rec["hash"], "model": rec.get("model"), "caller": rec.get("caller", ""), "pid": rec["pid"],
                              "ts": rec["ts"], "replayed": replayed, "recorded_wall_s": rec.get("wall_s"), "status": rec["status"],
                              "prompt_tokens": data.get("prompt_eval_count", 0), "completion_tokens": data.get("eval_count", 0),
                              "tool_calls": [c.get("function", {}).get("name") for c in msg.get("tool_calls") or []]})

    async def aclose(self) -> None:
        await self.inner.aclose()


def transport_from_env() -> httpx.AsyncBaseTransport | None:
    """The single switch every process reads.  Returns None when no tape is configured."""
    spec = os.environ.get("C1_TAPE", "")
    if not spec:
        return None
    mode, _, directory = spec.partition(":")
    return TapeTransport(mode, directory)
