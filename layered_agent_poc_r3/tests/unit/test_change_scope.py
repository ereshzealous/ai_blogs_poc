from pathlib import Path

import yaml

from experiments.scorers.change_scope import concern_of_line, concern_of_path

ROOT = Path(__file__).resolve().parents[2]
PLAN = yaml.safe_load((ROOT / "experiments/preregistration/experiment_plan.yaml").read_text())
SRC = (ROOT / "monolith/incident_agent.py").read_text()


def line_of(text):
    return next(i for i, l in enumerate(SRC.splitlines(), 1) if text in l)


def test_monolith_lines_map_to_frozen_concerns():
    sym = PLAN["concern_map"]["monolith_symbols"]
    assert concern_of_line(SRC, line_of("MODEL = "), sym) == "model-provider"
    assert concern_of_line(SRC, line_of("if name in NEEDS_APPROVAL and"), sym) == "approval-policy"
    assert concern_of_line(SRC, line_of("result = await self.clients[self.tool_server[name]].call_tool"), sym) == "tool-execution"
    assert concern_of_line(SRC, line_of("SYSTEM_PROMPT = "), sym) == "prompt"


def test_layered_paths_map_to_layers():
    paths = PLAN["concern_map"]["paths"]
    assert concern_of_path("config/models.yaml", paths) == "model-services"
    assert concern_of_path("layered_platform/tools/adapters.py", paths) == "tools-actions"
    assert concern_of_path("layered_platform/orchestration/incident_workflow.py", paths) == "orchestration"


def test_a_new_top_level_symbol_takes_the_concern_of_its_user():
    sym = PLAN["concern_map"]["monolith_symbols"]
    new = SRC.replace("def _load_runbook(", 'EXTRA_NOTE = "x"\n\n\ndef _load_runbook(').replace("messages: list[dict[str, Any]] = [", "system += EXTRA_NOTE\n            messages: list[dict[str, Any]] = [")
    line = next(i for i, l in enumerate(new.splitlines(), 1) if l.startswith("EXTRA_NOTE"))
    assert concern_of_line(new, line, sym, new, old_source=SRC) == "orchestration-loop"
