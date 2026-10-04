"""Measure how far one change spread, from a real git diff in an isolated worktree.

Per change: files, lines added/removed, test files, and the architectural concerns the changed lines belong to.
Concerns are assigned mechanically, by rules frozen in the preregistration (experiment_plan.yaml -> concern_map):
  * layered files: by path (each package is one layer or control)
  * monolith/incident_agent.py: by the top-level symbol that encloses the changed line in the *pre-change* file,
    refined by frozen anchors (e.g. the `if name in NEEDS_APPROVAL` block inside _execute_tool is "approval policy").
"Review surface" is the number of distinct concerns that live in the files the change touched: what a reviewer of the
diff has to hold in their head, not just what the diff edits.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Any


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def changed_lines(cwd: Path) -> dict[str, dict[str, list[int]]]:
    """Per file: removed lines in old-file coordinates, added lines in new-file coordinates."""
    out: dict[str, dict[str, list[int]]] = {}
    cur = None
    for line in _git(cwd, "diff", "-U0", "HEAD~1", "HEAD").splitlines():
        if line.startswith("--- "):
            continue
        if line.startswith("+++ "):
            cur = line[6:] if line != "+++ /dev/null" else None
            continue
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if m and cur:
            o, on, n, nn = int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1)
            rec = out.setdefault(cur, {"old": [], "new": []})
            rec["old"].extend(range(o, o + on))
            rec["new"].extend(range(n, n + nn))
    return out


def _symbol_ranges(source: str) -> list[tuple[int, int, str]]:
    tree = ast.parse(source)
    ranges: list[tuple[int, int, str]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    ranges.append((sub.lineno, sub.end_lineno or sub.lineno, sub.name))
                    for inner in ast.walk(sub):
                        if isinstance(inner, ast.If) and "NEEDS_APPROVAL" in (ast.get_source_segment(source, inner.test) or ""):
                            ranges.append((inner.lineno, inner.end_lineno or inner.lineno, f"{sub.name}:approval_gate"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ranges.append((node.lineno, node.end_lineno or node.lineno, node.name))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    ranges.append((node.lineno, node.end_lineno or node.lineno, t.id))
    return ranges


def concern_of_line(source: str, line: float, symbol_map: dict[str, str], new_source: str | None = None, old_source: str | None = None) -> str:
    """The concern of the smallest symbol range containing the line (or, for an insertion, the whole gap).  An insertion
    at module level defines a new top-level symbol: it takes the concern of the function that uses it in the new file."""
    best = None
    for a, b, name in _symbol_ranges(source):
        if a <= line <= b and (best is None or b - a < best[1] - best[0]):
            best = (a, b, name)
    if best is not None and best[2] in symbol_map:
        return symbol_map[best[2]]
    if new_source is not None:
        old_names = {n for _, _, n in _symbol_ranges(old_source)} if old_source else set()
        new_ranges = _symbol_ranges(new_source)
        for _, _, name in new_ranges if best is None else [best]:
            if name in old_names or name in symbol_map:
                continue
            users = [(a, b, n) for a, b, n in new_ranges if n != name and n in symbol_map and name in "\n".join(new_source.splitlines()[a - 1:b])]
            if users:
                a, b, n = min(users, key=lambda r: r[1] - r[0])
                return symbol_map[n]
    return "module"


def concern_of_path(path: str, path_map: dict[str, str]) -> str:
    for prefix, concern in sorted(path_map.items(), key=lambda kv: -len(kv[0])):
        if path.startswith(prefix):
            return concern
    return "unmapped"


def measure(worktree: Path, arch: str, concern_map: dict[str, Any], expected: list[str]) -> dict[str, Any]:
    numstat = [l.split("\t") for l in _git(worktree, "diff", "--numstat", "HEAD~1", "HEAD").splitlines() if l.strip()]
    files = [{"path": p, "added": int(a), "removed": int(r)} for a, r, p in numstat]
    lines = changed_lines(worktree)
    touched: dict[str, set[str]] = {}
    for f in files:
        path = f["path"]
        if path.endswith("incident_agent.py"):
            src, new = _git(worktree, "show", f"HEAD~1:{path}"), _git(worktree, "show", f"HEAD:{path}")
            sym = concern_map["monolith_symbols"]
            ch = lines.get(path, {"old": [], "new": []})
            touched[path] = {concern_of_line(src, n, sym, src) for n in ch["old"]} | {concern_of_line(new, n, sym, new, old_source=src) for n in ch["new"]}
        else:
            touched[path] = {concern_of_path(path, concern_map["paths"])}
    concerns = sorted(set().union(*touched.values()) - {"tests"}) if touched else []   # tests are counted separately
    # review surface: every concern that lives in a touched file
    surface: set[str] = set()
    surface_loc = 0
    for f in files:
        path = f["path"]
        before = _git(worktree, "show", f"HEAD~1:{path}")
        surface_loc += before.count("\n")
        if path.endswith("incident_agent.py"):
            surface |= {concern_map["monolith_symbols"].get(n, "unmapped") for _, _, n in _symbol_ranges(before)} - {"unmapped"}
        elif not path.startswith("tests/"):
            surface.add(concern_of_path(path, concern_map["paths"]))
    return {
        "arch": arch,
        "files_changed": len(files),
        "lines_added": sum(f["added"] for f in files),
        "lines_removed": sum(f["removed"] for f in files),
        "test_files_changed": sum(1 for f in files if f["path"].startswith("tests/")),
        "files": files,
        "concerns_touched": concerns,
        "concerns_touched_n": len(concerns),
        "concerns_by_file": {k: sorted(v) for k, v in touched.items()},
        "home_concern": expected,
        "outside_expected": sorted(set(concerns) - set(expected)),
        "spill_over_n": len(set(concerns) - set(expected)),
        "review_surface_concerns": sorted(surface),
        "review_surface_concerns_n": len(surface),
        "review_surface_loc": surface_loc,
    }
