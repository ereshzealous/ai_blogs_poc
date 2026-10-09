import asyncio
import json

import httpx
import pytest

from layered_platform.evals.checks import evaluate, normalise
from recordreplay.tape import TapeMiss, TapeTransport


class Echo(httpx.AsyncBaseTransport):
    def __init__(self):
        self.n = 0

    async def handle_async_request(self, request):
        self.n += 1
        return httpx.Response(200, json={"message": {"content": f"answer {self.n}"}, "prompt_eval_count": 5, "eval_count": 2})


async def _post(transport, body):
    async with httpx.AsyncClient(transport=transport, base_url="http://x") as c:
        return (await c.post("/api/chat", json=body)).json()["message"]["content"]


def test_record_then_replay_in_order_across_processes(tmp_path):
    inner = Echo()
    rec = TapeTransport("record", tmp_path, inner)
    assert [asyncio.run(_post(rec, {"q": 1})), asyncio.run(_post(rec, {"q": 1}))] == ["answer 1", "answer 2"]
    first = TapeTransport("replay", tmp_path)
    assert asyncio.run(_post(first, {"q": 1})) == "answer 1"
    second = TapeTransport("replay", tmp_path)          # a restarted process continues where the first stopped
    assert asyncio.run(_post(second, {"q": 1})) == "answer 2"
    ledger = [json.loads(l) for l in (tmp_path / "model_calls.jsonl").read_text().splitlines()]
    assert [e["replayed"] for e in ledger] == [False, False, True, True] and inner.n == 2


def test_replay_never_calls_a_model_for_an_unrecorded_request(tmp_path):
    TapeTransport("record", tmp_path, Echo())
    with pytest.raises(TapeMiss):
        asyncio.run(_post(TapeTransport("replay", tmp_path), {"q": "new"}))


def test_eval_normalises_typography():
    assert normalise("rel‑2031, 400 ms") == "rel-2031, 400 ms"


def test_evals_read_the_world_not_the_claim(world):
    report = "Root cause: rel-2031 pool exhaustion. Action: rolled back. Verification: fine."
    checks = evaluate(report, world, True)
    assert checks["diagnosis_names_release"] and not checks["rolled_back_to_healthy"] and not checks["rollback_exactly_once"]
