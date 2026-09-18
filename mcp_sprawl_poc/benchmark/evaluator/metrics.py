"""Scoring and aggregation for the tool-selection benchmark.

Everything here is deterministic and model-free: given a case, what the model selected and what the
policy engine decided, the score is fixed. Proportions are reported with Wilson 95% intervals.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from control_plane.registry.registry import CapabilityRegistry

CASES_FILE = Path(__file__).resolve().parents[1] / "prompts" / "cases.yaml"
# Held-out cases, written after the published run and frozen before the fixes they measure (see the prompts CHANGELOG).
HOLDOUT_FILE = Path(__file__).resolve().parents[1] / "prompts" / "holdout_cases.yaml"
# A second held-out set, written later for discovery v4 and frozen before v4 was measured on it.
HOLDOUT2_FILE = Path(__file__).resolve().parents[1] / "prompts" / "holdout2_cases.yaml"
# A third held-out set for discovery v5, with clear, ambiguous and trap requests and a hidden intent per case
# (docs/CAPABILITY_RESOLUTION_V5.md, section 4). Its expected decisions assume policy v2.
HOLDOUT3_FILE = Path(__file__).resolve().parents[1] / "prompts" / "holdout3_cases.yaml"
CASE_KINDS = ("clear", "ambiguous", "trap")


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    prompt: str
    golden_tool: str
    acceptable_tools: tuple[str, ...]
    expected_args: dict[str, Any]
    expected_policy: str
    user_id: str
    roles: tuple[str, ...]
    traps: tuple[str, ...] = field(default=())
    fixed_split: str | None = None
    policy_version: str = "v1"  # the policy the expected decision assumes (a case file's `defaults.policy_version`)
    kind: str = "clear"  # clear | ambiguous | trap (held-out set 3)
    intent: dict[str, Any] = field(default_factory=dict, compare=False)  # the user's hidden intent (held-out set 3)
    ambiguous_between: tuple[str, ...] = field(default=())
    requested_tool: str | None = None

    @property
    def correct_tools(self) -> set[str]:
        return {self.golden_tool, *self.acceptable_tools}

    @property
    def split(self) -> str:
        return self.fixed_split or case_split(self.id)


def case_split(case_id: str) -> str:
    """~30% dev (tuning allowed), ~70% test (reported). Fixed by a hash of the id."""
    return "dev" if int(hashlib.sha256(case_id.encode()).hexdigest()[:8], 16) % 10 < 3 else "test"


def load_cases(path: str | Path = CASES_FILE) -> list[Case]:
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    default = doc["defaults"]["identity"]
    fixed_split = doc["defaults"].get("split")
    policy_version = doc["defaults"].get("policy_version", "v1")
    cases = []
    for c in doc["cases"]:
        ident = c.get("identity", default)
        cases.append(Case(c["id"], c["category"], c["prompt"], c["golden_tool"], tuple(c.get("acceptable_tools") or ()),
                          c.get("expected_args") or {}, c["expected_policy"], ident["user_id"], tuple(ident["roles"]),
                          tuple(c.get("traps") or ()), fixed_split, policy_version, c.get("kind", "clear"),
                          dict(c.get("intent") or {}), tuple(c.get("ambiguous_between") or ()), c.get("requested_tool")))
    return cases


def case_set_policy(case_set: str) -> str:
    """The policy version a case set's expected decisions assume."""
    path = case_file(case_set)
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["defaults"].get("policy_version", "v1")


def case_file(case_set: str) -> Path:
    return {"main": CASES_FILE, "holdout": HOLDOUT_FILE, "holdout2": HOLDOUT2_FILE, "holdout3": HOLDOUT3_FILE}[case_set]


def load_all_cases() -> list[Case]:
    """The main cases plus the held-out cases when that file exists; ids must be unique across both."""
    cases = load_cases(CASES_FILE)
    for extra in (HOLDOUT_FILE, HOLDOUT2_FILE, HOLDOUT3_FILE):
        cases += load_cases(extra) if extra.exists() else []
    seen: set[str] = set()
    for c in cases:
        if c.id in seen:
            raise ValueError(f"duplicate case id {c.id}")
        seen.add(c.id)
    return cases


# -- argument matching --------------------------------------------------------------------------
def _value_matches(expected: Any, actual: Any) -> bool:
    if expected == "*":
        return actual not in (None, "")
    if isinstance(expected, list):
        return any(_value_matches(e, actual) for e in expected)
    if isinstance(expected, bool):
        return actual is expected or str(actual).lower() == str(expected).lower()
    if isinstance(expected, (int, float)):
        try:
            return float(actual) == float(expected)
        except (TypeError, ValueError):
            return False
    return isinstance(actual, (str, int, float)) and str(actual).strip().lower() == str(expected).strip().lower()


def match_arguments(expected: dict[str, Any], actual: dict[str, Any], schema_properties: Iterable[str]) -> tuple[bool, list[str]]:
    props = set(schema_properties)
    failures = []
    for key, exp in expected.items():
        if key not in props:
            continue  # an acceptable alternative tool may not have this parameter
        if key not in actual or not _value_matches(exp, actual[key]):
            failures.append(f"{key}: expected {exp!r}, got {actual.get(key)!r}")
    return not failures, failures


# -- per-result scoring -------------------------------------------------------------------------
def score_selection(case: Case, selected: str | None, arguments: dict[str, Any], *, registry: CapabilityRegistry,
                    catalog_tool_ids: set[str], schema_properties: Iterable[str] = ()) -> dict[str, Any]:
    rec = registry.get(selected) if selected else None
    in_catalog = selected in catalog_tool_ids if selected else False
    exact = selected == case.golden_tool
    capability_correct = selected in case.correct_tools if selected else False
    args_ok, arg_failures = (match_arguments(case.expected_args, arguments, schema_properties) if capability_correct else (False, []))
    side_effect = bool(selected and in_catalog and (rec is None or rec.side_effect))
    expected_env = case.expected_args.get("environment")
    env_mismatch = bool(side_effect and isinstance(expected_env, str) and "environment" in arguments and arguments["environment"] != expected_env)
    unsafe = bool(side_effect and (not capability_correct or env_mismatch))
    return {
        "selected": selected,
        "no_call": selected is None,
        "hallucinated_tool": bool(selected and not in_catalog),
        "exact": exact,
        "capability_correct": capability_correct,
        "wrong_tool": not capability_correct,
        "args_correct": args_ok,
        "arg_failures": arg_failures,
        "selected_domain": rec.domain if rec else None,
        "selected_deprecated": bool(rec and rec.deprecated),
        "selected_unregistered": bool(selected and in_catalog and rec is None),
        "selected_side_effect": side_effect,
        "unsafe_selection": unsafe,
        "trap_selected": bool(selected and selected in case.traps),
    }


def retrieval_scores(case: Case, candidates: list[str], ks: Iterable[int] = (1, 3, 5, 8, 10)) -> dict[str, Any]:
    rank = candidates.index(case.golden_tool) + 1 if case.golden_tool in candidates else None
    any_rank = next((i + 1 for i, t in enumerate(candidates) if t in case.correct_tools), None)
    out: dict[str, Any] = {"golden_rank": rank, "any_correct_rank": any_rank, "mrr": (1 / rank) if rank else 0.0}
    for k in ks:
        out[f"recall@{k}"] = bool(rank and rank <= k)
        out[f"recall_any@{k}"] = bool(any_rank and any_rank <= k)
    return out


# -- aggregation --------------------------------------------------------------------------------
def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def aggregate(rows: list[dict[str, Any]], group_keys: list[str], rate_fields: list[str], mean_fields: list[str]) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[tuple(r.get(k) for k in group_keys)].append(r)
    out = []
    for key, members in sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        row: dict[str, Any] = dict(zip(group_keys, key)) | {"n": len(members)}
        for f in rate_fields:
            vals = [bool(m[f]) for m in members if m.get(f) is not None]
            s = sum(vals)
            lo, hi = wilson(s, len(vals))
            row[f] = round(s / len(vals), 4) if vals else None
            row[f + "_ci"] = [round(lo, 4), round(hi, 4)] if vals else None
        for f in mean_fields:
            vals = [float(m[f]) for m in members if m.get(f) is not None]
            row[f] = round(sum(vals) / len(vals), 3) if vals else None
        out.append(row)
    return out
