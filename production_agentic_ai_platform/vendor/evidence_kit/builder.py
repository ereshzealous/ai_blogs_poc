"""Build a learning's evidence: its spec (learning.toml) + what its adapter read from the recorded files → evidence.json
and the Lab Console.

    spec     the learning's words and layout: meta, dimensions, pages of view primitives, claims, hypotheses, failures,
             drill-down metrics, statements, charts, figure provenance.  Every number in it is a {{fact}}.
    data     the adapter's output: facts (with provenance), runs and rows, cases, datasets for the views, per-row case
             tabs (traces), hypothesis verdicts, failure rows, drill-down breakdowns, artifacts and cross-checks.

The kit joins the two by id, resolves the copy, refuses hand-typed numbers and unknown facts, checks that every page's
data exists and every referenced row was recorded, and renders.  It knows nothing about any particular experiment.
"""

from __future__ import annotations

import json
import re
import time
import tomllib
from pathlib import Path
from typing import Any

from . import components
from .facts import Facts, lint, resolve_tree

SCHEMA = "evidence-kit/5"
PRIMITIVES = {"head", "grid", "run_card", "rate_cards", "claims", "composition", "line_chart", "scatter", "heatmap", "mix",
              "paired_tests", "callout", "comparison", "funnel", "case_explorer", "hypotheses", "failures", "artifacts",
              "reproduce", "metric_grid", "table", "timeline", "distribution",
              "proof_hero", "profile", "scorecard", "claim_trace", "integrity", "control"}  # 5.0: Proof Contract v1 views
CHARTS = {"rate": components.rate_chart, "pairs": components.pair_chart, "log_bars": components.log_bars}


class SpecError(SystemExit):
    pass


def load_spec(path: Path) -> dict:
    return tomllib.loads(Path(path).read_text())


def _pick(obj: Any, facts: Facts) -> Any:
    """Conditional copy: {if = "fact", is = value, then = "…", else = "…"} picks by the fact's value."""
    if isinstance(obj, dict) and "if" in obj and ("then" in obj or "else" in obj):
        fid = obj["if"]
        if fid not in facts:
            raise SpecError(f"conditional copy: unknown fact {fid}")
        hit = facts.value(fid) == obj.get("is", True)
        return _pick(obj.get("then") if hit else obj.get("else"), facts)
    if isinstance(obj, dict):
        return {k: v for k, v in ((k, _pick(v, facts)) for k, v in obj.items()) if v is not None}
    if isinstance(obj, list):
        return [x for x in (_pick(v, facts) for v in obj) if x is not None]
    return obj


def _join(spec_items: list[dict], data_items: dict, key: str, what: str) -> list[dict]:
    """Spec entries (words) joined with the adapter's entries (numbers, rows) by `key`; "@field" takes a data field."""
    out, seen = [], set()
    for s in spec_items:
        k = str(s[key])
        d = data_items.get(k)
        if d is None:
            raise SpecError(f"{what} {k}: in the spec but not in the adapter's data")
        seen.add(k)

        used: set[str] = set()

        def at(v):
            if isinstance(v, str) and v.startswith("@"):
                if v[1:] not in d:
                    raise SpecError(f"{what} {k}: the spec asks for @{v[1:]}, the adapter has {sorted(d)}")
                used.add(v[1:])
                return d[v[1:]]
            if isinstance(v, list):
                return [at(x) for x in v]
            return v
        clash = sorted(set(s) & set(d) - {key})
        if clash:
            raise SpecError(f"{what} {k}: both the spec and the adapter set {clash}")
        words = {f: at(v) for f, v in s.items()}
        out.append({**words, **{f: v for f, v in d.items() if f not in used}})  # a field the words placed is not repeated
    missing = sorted(set(map(str, data_items)) - seen)
    if missing:
        raise SpecError(f"{what}: the adapter has {missing} but the spec does not describe them")
    return out


def _quoted_ok(errors: list[str], spec: dict, base: Path) -> list[str]:
    """Numbers in fields the spec declares as quotations (e.g. preregistered thresholds) must occur in the quoted file."""
    keep = []
    rules = [(re.compile(q["path"]), (base / q["file"]).read_text()) for q in spec.get("lint", {}).get("quote", [])]
    for e in errors:
        path, _, rest = e.partition(": typed number(s) ")
        nums = rest.split(" in ")[0].split(", ")
        rule = next((txt for rx, txt in rules if rx.fullmatch(path)), None)
        if rule is None or any(n not in rule for n in nums):
            keep.append(e)
    return keep


def resolve(spec: dict, facts: Facts, base: Path) -> dict:
    """Every string of the spec with its facts substituted; hand-typed numbers refused."""
    lint_cfg = spec.get("lint", {})
    allow = [re.compile(a) for a in lint_cfg.get("allow", [])]
    body = _pick({k: v for k, v in spec.items() if k not in ("lint", "kit")}, facts)
    errors: list[str] = []
    try:
        out = resolve_tree(body, facts, allow, errors=errors)
    except KeyError as e:
        raise SpecError(str(e.args[0]))
    errors = _quoted_ok(errors, spec, base)
    if errors:
        raise SpecError("hand-typed numbers in the spec (bind them to facts, or allow the identifier):\n  " + "\n  ".join(errors[:40])
                        + (f"\n  … and {len(errors) - 40} more" if len(errors) > 40 else ""))
    return out


def _blocks(blocks: list[dict]):
    for b in blocks:
        yield b
        if b.get("type") == "grid":  # only a grid holds blocks; other items lists are a block's own data
            yield from _blocks(b.get("items", []))


def validate(ev: dict) -> list[str]:
    problems = []
    runs = {r["id"]: {x["id"] for x in r["rows"]} for r in ev["runs"]}
    primary = ev["runs"][0]["id"] if ev["runs"] else None
    for p in ev["pages"]:
        for b in _blocks(p.get("blocks", [])):
            if b.get("type") not in PRIMITIVES:
                problems.append(f"page {p['id']}: unknown block type {b.get('type')!r}")
            if b.get("data") and b["data"] not in ev["datasets"]:
                problems.append(f"page {p['id']}: block {b['type']} needs dataset {b['data']!r}")
    for m in ev["metrics"]:
        run = m.get("run", primary)
        lost = [x for x in m.get("rows", []) + [y for bk in m.get("breakdown", []) for y in bk["rows"]] if x not in runs.get(run, set())]
        if lost:
            problems.append(f"metric {m['id']}: rows not recorded in {run}: {lost[:3]}")
    for f in ev["failures"]:
        lost = [x for x in f.get("row_ids", []) if x not in runs.get(primary, set())]
        if lost:
            problems.append(f"failure {f['n']}: rows not recorded: {lost}")
    for h in ev["hypotheses"]:
        if not h.get("status"):
            problems.append(f"hypothesis {h['id']}: no verdict")
    proof = ev.get("proof") or {}
    checks = {c["id"] for c in proof.get("checks", [])}
    used = [it.get("check") for c in (proof.get("profile") or {}).get("classes", []) for it in c.get("items", [])]
    used += [r[2] for g in (proof.get("profile") or {}).get("groups", []) for r in g.get("rows", []) if len(r) > 2]
    used += [c for p in ev["pages"] for b in _blocks(p.get("blocks", [])) for c in (b.get("prov") or {}).get("checks", [])]
    for c in filter(None, used):
        if c not in checks:
            problems.append(f"proof: check {c} is referenced but not in the published run's checks")
    for fid, f in ev["facts"].items():
        if f.get("rows"):
            lost = [x for x in f["rows"]["ids"] if x not in runs.get(f["rows"]["run"], set())]
            if lost:
                problems.append(f"fact {fid}: rows not recorded in {f['rows']['run']}: {lost[:3]}")
    return problems


def _common_freeze(facts: Facts) -> str | None:
    from collections import Counter
    c = Counter(f.get("freeze") for f in facts.d.values() if f.get("freeze"))
    return c.most_common(1)[0][0] if c else None


def _facts_json(facts: Facts) -> dict:
    """The registry, with the freeze most facts share stated once (evidence["provenance"]["freeze"])."""
    common = _common_freeze(facts)
    return {k: {f: v for f, v in e.items() if not (f == "freeze" and v == common)} for k, e in facts.to_json().items()}


def build(spec_path: Path, data: dict, facts: Facts, out_html: Path, out_json: Path | None = None, *, kit_version: str,
          generated_by: str = "") -> dict:
    spec = load_spec(spec_path)
    base = Path(spec_path).resolve().parent
    for up in [base, *base.parents]:  # quoted files are named from the repository root
        if (up / ".git").exists():
            base = up
            break
    dims = spec.get("dimensions", {})
    for v in dims.get("variants", []):  # the variant names are facts too: copy says {{variant.C.name}}
        where = f"{Path(spec_path).resolve().relative_to(base).as_posix() if Path(spec_path).resolve().is_relative_to(base) else Path(spec_path).name} → dimensions.variants"
        facts.add(f"variant.{v['key']}.name", v["name"], source=where)
        facts.add(f"variant.{v['key']}.name_lower", v["name"].lower(), source=where)
    S = resolve(spec, facts, base)
    D = S.get("dimensions", {})
    datasets = dict(data.get("datasets", {}))
    svg = {}
    for cid, c in S.get("charts", {}).items():
        body = {**datasets[c["data"]], **{k: v for k, v in c.items() if k not in ("type", "data")}}
        svg[cid] = CHARTS[c["type"]](body)
    ev = {
        "kit": kit_version, "schema": SCHEMA,
        "meta": S.get("learning", {}),
        "dimensions": {**D, "factor": {**D.get("factor", {}), **data.get("factor", {})}, "groups": data.get("groups", {})},
        "facts": _facts_json(facts),
        "provenance": {"freeze": _common_freeze(facts)},
        "claims": S.get("claims", {}),
        "hypotheses": _join(S.get("hypotheses", []), data.get("hypotheses", {}), "id", "hypothesis"),
        "failures": _join(S.get("failures", []), data.get("failures", {}), "n", "failure"),
        "failure_classes": data.get("failure_classes", []),
        "metrics": _join(S.get("metrics", []), data.get("metrics", {}), "id", "metric"),
        "datasets": datasets,
        "runs": data.get("runs", []), "cases": data.get("cases", {}), "default_row": data.get("default_row"),
        "artifacts": data.get("artifacts", {}),
        "pages": S.get("pages", []), "case_tabs": S.get("case_tabs", []),
        "statements": S.get("statements", {}), "svg": svg, "charts": {k: datasets[c["data"]] for k, c in S.get("charts", {}).items()},
        "figures": S.get("figures", {}), "sections": S.get("sections", {}),
        "proof": data.get("proof", {}),
        "article": S.get("article", {}),  # 5.0: an article's proof components (proof strip, reality map, evidence links, refresh note)
        "generated": {"at": time.strftime("%Y-%m-%d %H:%M %Z"), "by": generated_by, **data.get("generated", {})},
    }
    problems = validate(ev)
    if problems:
        raise SpecError("evidence does not hold together:\n  " + "\n  ".join(problems[:30]))
    out_json = out_json or out_html.parent / "evidence.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(ev, ensure_ascii=False, indent=1) + "\n")
    from . import render_console
    res = render_console(ev, data.get("traces", {}), out_html)
    return {**res, "evidence": ev}
