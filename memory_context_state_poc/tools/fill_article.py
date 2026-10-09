#!/usr/bin/env python3
"""Fill the article's numbers from ONE recorded run. No measured number in any edition is typed by hand.

    python3 tools/fill_article.py [--run-id RUN]

Reads article/article-numbers.json (written by tools/export_diagram_data.py from runs/<run>/summary.json) and the POC
test suite, renders article/*.template.md -> article/*.md and templates/poc-README.template.md -> the POC README, and
fails if any {{placeholder}} is left unfilled or if a template types a result by hand (a fraction, "N of M", "N -> M").
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
POC = HERE / "memory-context-state-poc"
ARTICLE_RUN = "2026-09-18-recorded"
MANIFEST = HERE.parent / "series-start-here" / "learning-map.yaml"


def medium_link() -> str:
    """The published article URL comes from the learning-map manifest (items: id: memory -> article: url), never typed here."""
    text = MANIFEST.read_text() if MANIFEST.exists() else ""
    m = re.search(r"-\s*id:\s*memory\b.*?\n\s*article:\s*\n\s*url:\s*(\S+)", text, re.S)
    url = m.group(1).strip("\"'") if m else "null"
    return f"[the article on Medium]({url})" if url != "null" else "the article on Medium (the link is added when it is published)"


def frac(p: list[int]) -> str:
    return f"{p[0]}/{p[1]}"


def numbers(run_id: str) -> dict[str, str]:
    f = json.loads((HERE / "article" / "article-numbers.json").read_text())
    if f["run_id"] != run_id:
        raise SystemExit(f"article-numbers.json is from {f['run_id']}, not {run_id}: run tools/export_diagram_data.py {run_id}")
    s = json.loads((POC / "runs" / run_id / "summary.json").read_text())
    rows = {r["exp"]: r for r in f["rows"]}
    inv = lambda r, arm: r[arm]["invalid"] + r[arm]["contradicted_unmarked"]  # noqa: E731
    tests = sum(1 for p in (POC / "tests").glob("test_*.py") for n in ast.walk(ast.parse(p.read_text()))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_"))
    contracts = (POC / ".importlinter").read_text().count("[importlinter:contract:")
    top5 = [c for c in f["m0_candidates"] if c["naive_k5"] == "admitted"]
    m6a = f["m6a"]
    n = {
        "run_id": run_id, "model": f["model"], "embedding_model": f["embedding_model"], "seeds": ", ".join(map(str, f["seeds"])),
        "budget": str(f["budget"]), "candidates_n": str(f["candidates_n"]), "frozen_digest": f["frozen_digest"],
        "tests": str(tests), "contracts": str(contracts),
        "invariants": f"{f['invariants_passed']}/{f['invariants_total']}",
        "naive_invalid_total": str(sum(inv(r, "naive") for r in f["rows"])),
        "k5_invalid_total": str(sum(inv(r, "naive_k5") for r in f["rows"])),
        "governed_invalid_total": str(sum(inv(r, "governed") for r in f["rows"])),
        "experiments_injected_naive_admitted": str(sum(1 for e, r in rows.items() if e not in ("M1", "M8") and inv(r, "naive") > 0)),
        "m0_top5_invalid": str(sum(1 for c in top5 if c["failure"])), "m0_top5_total": str(len(top5)),
        "m0_runbook_rank": str(f["m0_runbook_rank"]),
        "m0_naive_invalid": str(inv(rows["M0"], "naive")),
        "m0_naive_recall": frac(rows["M0"]["naive"]["recall"]), "m0_gov_recall": frac(rows["M0"]["governed"]["recall"]),
        "m0_naive_precision": frac(rows["M0"]["naive"]["precision"]), "m0_gov_precision": frac(rows["M0"]["governed"]["precision"]),
        "m8_naive_recall": frac(rows["M8"]["naive"]["recall"]), "m8_gov_recall": frac(rows["M8"]["governed"]["recall"]),
        "k5_runbook_present": str(sum(1 for r in f["rows"] if r["naive_k5"]["runbook"])), "rows_total": str(len(f["rows"])),
        "m9_naive_proceeded": str(rows["M9"]["naive"]["actions"].get("rollback_release_pipeline", 0)),
        "m9_gov_waited": str(rows["M9"]["governed"]["correct"]), "m9_runs": str(rows["M9"]["governed"]["runs"]),
        "m9_quote": f["m9_naive_rationale"].replace("‑", "-"),
        "forbidden_naive": str(f["totals"]["naive"]["forbidden"]), "forbidden_gov": str(f["totals"]["governed"]["forbidden"]),
        "runs_per_arm": str(f["totals"]["naive"]["runs"]),
        "m6a_naive_persisted": str(sum(1 for w in m6a if w["naive_persisted"])), "m6a_gov_persisted": str(sum(1 for w in m6a if w["governed_persisted"])),
        "m6a_events": str(len(m6a)),
        "m6b_naive_invalid": str(inv(rows["M6B"], "naive")), "m6b_gov_invalid": str(inv(rows["M6B"], "governed")),
        "decisions_total": str(sum(r[a].get("runs", 0) for r in f["rows"] for a in ("naive", "governed"))),
        "wall_minutes": str(round(s["wall_seconds"] / 60)),
        "tests_list": "\n".join(f"- `{p.stem}::{fn.name}`" for p in sorted((POC / "tests").glob("test_*.py"))
                                for fn in ast.parse(p.read_text()).body
                                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name.startswith("test_")),
    }
    for e in ("M1", "M2", "M3", "M4", "M5", "M7", "M8", "M9", "M0", "M6B"):
        for arm, key in (("naive", "n"), ("governed", "g")):
            o = rows[e][arm]
            n[f"{e}_{key}_correct"] = f"{o['correct']}/{o['runs']}"
    return n


def include(text: str, n: dict[str, str]) -> str:
    """{{> path}} embeds a generated or documentation file (relative to this folder), its H1 dropped and headings
    demoted one level, so docs and run reports are included, never copied by hand. {run_id} expands in the path."""
    def one(m):
        body = (HERE / m.group(1).strip().replace("{run_id}", n["run_id"])).read_text().splitlines()
        if body and body[0].startswith("# "):
            body = body[1:]
        return "\n".join(("#" + l) if re.match(r"#{1,5} ", l) else l for l in body).strip()
    return re.sub(r"\{\{>\s*(.+?)\}\}", one, text)


# Series rule: no prose layer owns a measured number. A result shape typed into a template (a fraction, "N of M",
# "N out of M", "N -> M") fails the build; results enter only through {{placeholders}} filled from the recorded run.
TYPED_RESULT = re.compile(r"(?<![\w{.-])\d+\s*(?:/\s*\d+|\s(?:out\s+)?of\s+\d+|\s*(?:→|->)\s*\d+)(?![\w}])")


def typed_results(text: str) -> list[str]:
    """Measured-looking numbers written by hand, outside code blocks, inline code, links and placeholders."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`|\{\{.*?\}\}|\]\([^)]*\)", "", text)
    return [m.group(0) for m in TYPED_RESULT.finditer(text)]


def render(template: Path, out: Path, n: dict[str, str]) -> None:
    typed = typed_results(template.read_text())
    if typed:
        raise SystemExit(f"{template.name}: measured numbers typed into prose {typed}; use a placeholder from the run")
    text = include(template.read_text(), n)
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)) - set(n))
    if missing:
        raise SystemExit(f"{template.name}: no value for {missing}")
    out.write_text(re.sub(r"\{\{(\w+)\}\}", lambda m: n[m.group(1)], text))
    print("wrote", out.relative_to(HERE))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=ARTICLE_RUN)
    a = ap.parse_args()
    n = numbers(a.run_id)
    flat = json.dumps({k: v for k, v in n.items() if k != "tests_list"}, indent=1) + "\n"
    (HERE / "article" / "article-numbers.flat.json").write_text(flat)
    (POC / "runs" / a.run_id / "article-numbers.json").write_text(flat)  # the series manifest reads it from the run folder
    n["medium_link"] = medium_link()
    for t in sorted((HERE / "article").glob("*.template.md")):
        render(t, t.with_name(t.name.replace(".template", "")), n)
    tpl = HERE / "templates" / "poc-README.template.md"
    if tpl.exists():
        render(tpl, POC / "README.md", n)


if __name__ == "__main__":
    main()
