"""The claim-to-evidence matrix: every published claim, the file it rests on, and what it does not show.

    uv run python -m experiments.claims --run-id 2026-09-17-recorded      # check, then write docs/claim-evidence-matrix.md

docs/claims.json lists the claims. This module checks each one against the run it is published with -- the facts.json
path exists, the verification check ran and passed, the run files are there, the test is in the suite -- and renders
the matrix from what it found. A claim whose evidence is missing is a failure here, not a footnote in the article.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
CLAIMS = ROOT / "docs" / "claims.json"
MATRIX = ROOT / "docs" / "claim-evidence-matrix.md"
KINDS = {"measured": "Measured in the run", "guaranteed": "Pinned down by a test", "scoped": "Limits on the evidence"}


def dig(data: Any, dotted: str) -> tuple[bool, Any]:
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def load(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else None


def related(a: str, b: str) -> bool:
    """Two facts paths describe the same value when one is the other, or its parent."""
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def check(base: Path, checks: dict[str, dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Each claim with what its evidence resolved to, and the problems found.

    `checks` are the verification results to judge against; by default the ones the run has on disk. The verifier
    passes the results it is still computing, so a claim and the check behind it cannot disagree.
    """
    doc = json.loads(CLAIMS.read_text())
    facts = load(base / "facts.json")
    if facts is None:
        raise SystemExit(f"runs/{base.name} has no facts.json: build it first")
    if checks is None:
        checks = {c["check"]: c for c in (load(base / "verification.json") or {}).get("checks", [])}
    evidence = load(base / "article-evidence.json")
    cited = (evidence or {}).get("values", {})
    problems: list[str] = []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    for c in doc["claims"]:
        cid = c["id"]
        if cid in seen:
            problems.append(f"{cid}: duplicate id")
        seen.add(cid)
        if c["kind"] not in KINDS:
            problems.append(f"{cid}: unknown kind {c['kind']}")
        values: dict[str, Any] = {}
        for path in c["facts"]:
            ok, value = dig(facts, path)
            if not ok:
                problems.append(f"{cid}: facts.json has no {path}")
            else:
                values[path] = value
        for name in c["placeholders"]:
            if evidence is None:
                continue  # the run was published without the article's values
            if name not in cited:
                problems.append(f"{cid}: the article has no placeholder {{{{{name}}}}}")
            elif c["facts"] and not cited[name].get("not_measured") and not any(
                    related(p, q) for p in cited[name]["facts"] for q in c["facts"]):
                problems.append(f"{cid}: {{{{{name}}}}} reads {cited[name]['facts']}, none of this claim's facts")
        for name in c["verified_by"]:
            if name not in checks:
                problems.append(f"{cid}: verification.json has no check '{name}'")
            elif checks[name]["status"] != "pass":
                problems.append(f"{cid}: check '{name}' {checks[name]['status']}ped in this run"
                                if checks[name]["status"] == "skip" else f"{cid}: check '{name}' failed")
        files: list[str] = []
        for pattern in c["evidence"]:
            hit = sorted(str(p.relative_to(base)) for p in base.glob(pattern))
            if not hit:
                problems.append(f"{cid}: no file in the run matches {pattern}")
            files += hit
        for node in c["tests"]:
            path, _, name = node.partition("::")
            source = ROOT / path
            if not source.exists():
                problems.append(f"{cid}: no test file {path}")
            elif f"def {name}(" not in source.read_text():
                problems.append(f"{cid}: {path} has no {name}")
        out.append({**c, "values": values, "files": files})
    return out, problems


def matrix(base: Path, claims: list[dict[str, Any]]) -> str:
    run = load(base / "run.json") or {}
    ver = load(base / "verification.json") or {}
    freeze = load(base / "freeze.json") or {}
    lines = [
        "# Claim-to-evidence matrix",
        "",
        f"Every claim the article makes about this POC, and the file in run `{base.name}` that carries it. "
        "Generated by `experiments/claims.py` from `docs/claims.json`; a claim whose evidence is missing fails the build.",
        "",
        f"- Run: `runs/{base.name}/` ({run.get('mode', '?')}, profile `{run.get('profile', '?')}`, "
        f"finished {run.get('finished', '?')})",
        f"- Values: `facts.json`, recomputed from the raw records by `verification.json` "
        f"({ver.get('passed', '?')} checks passed, {ver.get('failed', '?')} failed, {ver.get('skipped', '?')} not applicable)",
        f"- Inputs: `freeze.json` ({freeze.get('files', '?')} files, digest `{str(freeze.get('digest', ''))[:16]}`)",
        "- Claims about specifications and other people's writing are not here. They are checked as links and quotes in",
        "  the article's research notes.",
        "",
        "Regenerate with:",
        "",
        "```bash",
        f"uv run python -m experiments.claims --run-id {base.name}",
        "```",
    ]
    for kind, title in KINDS.items():
        rows = [c for c in claims if c["kind"] == kind]
        if not rows:
            continue
        lines += ["", f"## {title}", "", "| Claim | Evidence | What it does not show |", "|---|---|---|"]
        for c in rows:
            bits = []
            if c["values"]:
                bits.append("`facts.json`: " + ", ".join(f"`{k}` = {json.dumps(v)}" for k, v in c["values"].items()))
            if c["verified_by"]:
                bits.append("recomputed: " + ", ".join(f"*{n}*" for n in c["verified_by"]))
            if c["files"]:
                shown = c["files"][:3] + ([f"+{len(c['files']) - 3} more"] if len(c["files"]) > 3 else [])
                bits.append("files: " + ", ".join(f"`{p}`" if not p.startswith("+") else p for p in shown))
            if c["tests"]:
                bits.append("tests: " + ", ".join(f"`{n.split('::')[-1]}`" for n in c["tests"]))
            claim = f"**{c['id']}** {c['claim']}<br>*{c['section']}*"
            lines.append(f"| {claim} | {'<br>'.join(bits) or '—'} | {c['limits']} |")
    return "\n".join(lines) + "\n"


def write(base: Path, checks: dict[str, dict[str, Any]] | None = None) -> tuple[list[str], Path]:
    claims, problems = check(base, checks)
    MATRIX.write_text(matrix(base, claims))
    return problems, MATRIX


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--check", action="store_true", help="only report problems, do not write the matrix")
    a = ap.parse_args()
    base = RUNS / a.run_id
    if not base.is_dir():
        sys.exit(f"no run directory {base}")
    if a.check:
        problems = check(base)[1]
    else:
        problems, out = write(base)
        print(f"[claims] {out.relative_to(ROOT)}: {len(json.loads(CLAIMS.read_text())['claims'])} claims")
    for p in problems:
        print("  FAIL", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
