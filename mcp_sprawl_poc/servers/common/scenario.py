"""Loads the INC-4917 scenario and derives deterministic time series from it."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "mock_data" / "inc4917" / "scenario.yaml"


@dataclass(frozen=True)
class Scenario:
    raw: dict[str, Any]

    def __getattr__(self, item: str) -> Any:
        try:
            return self.raw[item]
        except KeyError as exc:  # pragma: no cover - programming error
            raise AttributeError(item) from exc

    @property
    def day(self) -> str:
        return self.raw["date"]

    def at(self, hhmm: str) -> datetime:
        return datetime.fromisoformat(f"{self.day}T{hhmm}:00+00:00")


@lru_cache(maxsize=4)
def load_scenario(path: str | Path = SCENARIO_PATH) -> Scenario:
    with open(path, encoding="utf-8") as fh:
        return Scenario(yaml.safe_load(fh))


def parse_window(time_range: str | None, default: str = "15m") -> timedelta:
    m = re.fullmatch(r"(\d+)([mh])", (time_range or default).strip())
    if not m:
        m = re.fullmatch(r"(\d+)([mh])", default)
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(minutes=n) if unit == "m" else timedelta(hours=n)


def _jitter(key: str, amplitude: float) -> float:
    """Deterministic pseudo-noise in [-amplitude, amplitude] derived from a string key."""
    if not amplitude:
        return 0.0
    h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return (h * 2 - 1) * amplitude


def metric_value(
    scenario: Scenario,
    service: str,
    environment: str,
    metric: str,
    minute: datetime,
    recovered_at: datetime | None,
) -> float | None:
    env = scenario.metrics.get(service, {}).get(environment)
    if not env or metric not in env:
        return None
    shape = env[metric]
    start = env.get("incident_start")
    in_incident = (
        start is not None
        and "incident" in shape
        and minute >= scenario.at(start)
        and (recovered_at is None or minute < recovered_at)
    )
    base = shape["incident"] if in_incident else shape["baseline"]
    value = base + _jitter(f"{service}|{environment}|{metric}|{minute.isoformat()}", shape.get("jitter", 0))
    return round(value, 1 if isinstance(shape.get("jitter", 0), float) and shape["jitter"] < 1 else 0)


def series(
    scenario: Scenario,
    service: str,
    environment: str,
    metric: str,
    end: datetime,
    window: timedelta,
    recovered_at: datetime | None,
    step_minutes: int = 1,
) -> list[dict[str, Any]]:
    points = []
    t = (end - window).replace(second=0, microsecond=0)
    while t <= end:
        v = metric_value(scenario, service, environment, metric, t, recovered_at)
        if v is not None:
            points.append({"t": t.astimezone(timezone.utc).strftime("%H:%M"), "value": v})
        t += timedelta(minutes=step_minutes)
    return points


def summarize(points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        return {"points": 0}
    values = [p["value"] for p in points]
    return {
        "points": len(values),
        "min": min(values),
        "max": max(values),
        "avg": round(sum(values) / len(values), 1),
        "first": values[0],
        "last": values[-1],
    }
