"""End-to-end plumbing with a fake embedder and a fake model: every experiment runs, writes audit files and a summary,
and conversation/workflow sections are identical across arms. No real model output is produced or inspected here."""

import json
from types import SimpleNamespace

from s1_experiments import report, run
from s1_experiments.scenario import Scenario

from .conftest import FakeEmbedder


class FakeGateway(FakeEmbedder):
    async def chat(self, route, messages, *, schema=None, workflow_id, agent, tools=None):
        return SimpleNamespace(content=json.dumps({"action": "escalate_to_human", "rationale": "fake", "cited_ids": []}),
                               model="fake", input_tokens=1, output_tokens=1, latency_ms=0.0)

    async def close(self):
        return None


async def test_all_experiments_run_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "make_gateway", lambda *a, **k: FakeGateway())
    sc = Scenario.load()
    r = run.Runner(tmp_path, sc)
    exps = await r.run()
    assert set(exps) == set(sc.experiments) | {"M6A", "M6B"}
    s = run.summarize("smoke", "fake", {"x": "y"}, sc.config, exps)
    assert s["invariants_total"] == len(sc.experiments) + 1
    assert "| M0 | naive |" in report.render(s)
    assert len(r.results) == (len(sc.experiments) + 1) * 2 * len(sc.config["seeds"])
    for exp in list(sc.experiments) + ["M6B"]:
        n = (tmp_path / "prompts" / f"{exp}-naive.txt").read_text()
        g = (tmp_path / "prompts" / f"{exp}-governed.txt").read_text()
        for block in ("## Workflow facts (from the workflow store)", "## Conversation (this session)"):
            assert n.split(block)[1].split("## ")[0] == g.split(block)[1].split("## ")[0], exp
        assert (tmp_path / "audit" / f"{exp}-governed.json").exists()
    assert "WAITING_APPROVAL" in (tmp_path / "prompts" / "M9-naive.txt").read_text()
