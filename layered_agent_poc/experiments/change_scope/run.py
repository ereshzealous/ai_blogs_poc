"""E1 · change scope. Apply each requirement change to a scratch copy of the repo and measure what it touches.

    uv run python -m experiments.change_scope.run            # writes runs/change-scope.json

For each patch: check it applies cleanly, count files and lines, compile the result, import the touched modules, and
for the layered platform re-run the import-linter contracts on the patched tree.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def numstat(patch: Path) -> tuple[int, int, list[str]]:
    added = removed = 0
    files = []
    current = None
    for line in patch.read_text().splitlines():
        if line.startswith("+++ "):
            current = line[4:].split("\t")[0].removeprefix("b/")
            files.append(current)
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed, files


def verify(patch: Path, layered: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="lap-scope-") as tmp:
        t = Path(tmp)
        for d in ("agent_platform", "config", "monolith", "mock_enterprise"):
            shutil.copytree(ROOT / d, t / d, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(ROOT / ".importlinter", t / ".importlinter")
        check = subprocess.run(["patch", "-p1", "--dry-run", "-i", str(patch)], cwd=t, capture_output=True, text=True)
        if check.returncode:
            return {"applies": False, "error": check.stdout + check.stderr}
        subprocess.run(["patch", "-p1", "-s", "-i", str(patch)], cwd=t, check=True)
        _, _, files = numstat(patch)
        py = [f for f in files if f.endswith(".py")]
        env = {"PYTHONPATH": str(t), "PATH": str(Path(sys.executable).parent)}
        compiled = subprocess.run([sys.executable, "-m", "py_compile", *py], cwd=t, capture_output=True, text=True).returncode == 0 if py else True
        modules = [f[:-3].replace("/", ".") for f in py]
        imported = subprocess.run([sys.executable, "-c", "; ".join(f"import {m}" for m in modules) or "pass"],
                                  cwd=t, env=env, capture_output=True, text=True)
        out = {"applies": True, "compiles": compiled, "imports": imported.returncode == 0,
               "import_error": imported.stderr[-300:] if imported.returncode else None}
        if layered:
            lint = subprocess.run([str(Path(sys.executable).parent / "lint-imports")], cwd=t, env=env, capture_output=True, text=True)
            out["contracts_kept"] = lint.returncode == 0
        return out


def main(out: Path | None = None) -> None:
    spec = yaml.safe_load((HERE / "changes.yaml").read_text())
    results = []
    for ch in spec["changes"]:
        row = {"id": ch["id"], "title": ch["title"]}
        for side in ("monolith", "layered"):
            s = ch[side]
            patch = HERE / "patches" / s["patch"]
            added, removed, files = numstat(patch)
            row[side] = {"files": len(files), "added": added, "removed": removed, "file_list": files,
                         "concerns": s["concerns"], "notes": s["notes"], **verify(patch, side == "layered")}
        results.append(row)
        m, l = row["monolith"], row["layered"]
        print(f"{ch['id']:14} monolith {m['files']} files +{m['added']}/-{m['removed']} {m['concerns']}  |  "
              f"layered {l['files']} files +{l['added']}/-{l['removed']} {l['concerns']}  "
              f"(applies={m['applies'] and l['applies']}, contracts_kept={l.get('contracts_kept')})")
    out = out or ROOT / "runs" / "change-scope.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"changes": results}, indent=2))
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


if __name__ == "__main__":
    main()
