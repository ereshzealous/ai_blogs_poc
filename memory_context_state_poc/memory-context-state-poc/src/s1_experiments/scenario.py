"""Loads the frozen scenario (scenarios/*.yaml). This package, not governed_memory, is the only reader of labels.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from governed_memory.models.record import MemoryRecord, Query, parse_time

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "scenarios"


def _y(name: str) -> Any:
    return yaml.safe_load((SCENARIOS / name).read_text())


@dataclass
class Scenario:
    config: dict[str, Any]
    base: list[MemoryRecord]
    injections: dict[str, list[MemoryRecord]]
    labels: dict[str, dict[str, Any]]
    write_events: list[dict[str, Any]]
    prompt: dict[str, Any]

    @classmethod
    def load(cls) -> Scenario:
        corpus = _y("corpus.yaml")
        return cls(config=_y("experiments.yaml"),
                   base=[MemoryRecord.from_dict(d) for d in corpus["base"]],
                   injections={k: [MemoryRecord.from_dict(d) for d in v] for k, v in corpus["injections"].items()},
                   labels=_y("labels.yaml"), write_events=_y("write_events.yaml"), prompt=_y("prompt.yaml"))

    @property
    def experiments(self) -> dict[str, dict[str, Any]]:
        return self.config["experiments"]

    @property
    def clock(self):
        return parse_time(self.config["clock"])

    def all_records(self) -> list[MemoryRecord]:
        return self.base + [r for group in self.injections.values() for r in group]

    def record(self, rid: str) -> MemoryRecord:
        return next(r for r in self.all_records() if r.id == rid)

    def corpus(self, exp_id: str) -> list[MemoryRecord]:
        exp = self.experiments[exp_id]
        return self.base + [r for g in exp["inject"] for r in self.injections[g]]

    def query(self, name: str) -> Query:
        s = self.config["query_scope"]
        return Query(text=" ".join(self.config[name].split()), tenant=s["tenant"], environment=s["environment"],
                     entities=tuple(s["entities"]), user=s["user"], session=s["session"], clock=self.clock)
