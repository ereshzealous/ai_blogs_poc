"""The parts every POC runner needs: output, the POC's Python, compare-and-restore, recorded-evidence guards, a pipeline."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def paint(s: str, code: str) -> str:
    return f"\033[{code}m{s}\033[0m" if TTY else s


OK, FAIL, WARN, INFO = paint("ok", "32"), paint("FAIL", "31;1"), paint("warn", "33"), paint("··", "2")
MARK_W = 13 if TTY else 4  # width of a painted mark in a column


def say(*a) -> None:
    print(*a, flush=True)


def head(title: str) -> None:
    say("\n" + paint(f"── {title} ", "1") + paint("─" * max(4, 72 - len(title)), "2"))


class Runner:
    """One POC: its repository root, its Python project and the recorded evidence nobody may overwrite.

    Steps run in the POC's own locked environment (``uv run --project <project>``), or in the container's environment
    when ``container_env`` is set, so the runner itself needs nothing beyond the standard library.
    """

    def __init__(self, root: Path, project: str = "poc", recorded: tuple[str, ...] = (), container_env: str = ""):
        self.root = root.resolve()
        self.project = self.root / project
        self.recorded = [(self.root / r).resolve() for r in recorded]
        self.in_container = Path("/.dockerenv").exists() or bool(container_env and os.environ.get(container_env) == "1")
        self._python: list[str] | None = None

    # ---------------------------------------------------------------- running the POC's Python
    def python(self) -> list[str]:
        """The interpreter of the POC's locked environment (uv syncs it on first use)."""
        if self._python is None:
            if self.in_container:
                self._python = [sys.executable]
            else:
                uv = shutil.which("uv")
                if not uv:
                    raise SystemExit("uv is not installed (https://docs.astral.sh/uv/); or run the same command in Docker")
                out = subprocess.run([uv, "run", "--quiet", "--project", str(self.project), "python", "-c", "import sys; print(sys.executable)"],
                                     capture_output=True, text=True)
                if out.returncode:
                    raise SystemExit(out.stderr.strip() or "could not prepare the POC environment")
                self._python = [out.stdout.strip()]
        return self._python

    def py(self, *args: str) -> bool:
        """Run one step with the POC's Python, from the POC directory, and print it first. True when it succeeded."""
        say(paint("$ python " + " ".join(args), "2"))
        return subprocess.run([*self.python(), *args], cwd=self.project).returncode == 0

    # ---------------------------------------------------------------- paths
    def rel(self, p: Path) -> str:
        p = Path(p).resolve()
        return str(p.relative_to(self.root)) if p.is_relative_to(self.root) else str(p)

    def is_recorded(self, p: Path) -> bool:
        return Path(p).resolve() in self.recorded

    # ---------------------------------------------------------------- compare-and-restore
    def snapshot(self, paths: list[str]) -> dict[Path, bytes]:
        """Every file under these repository paths, byte for byte."""
        snap = {}
        for p in (self.root / x for x in paths):
            for f in ([p] if p.is_file() else sorted(p.rglob("*")) if p.exists() else []):
                if f.is_file() and "__pycache__" not in f.parts:
                    snap[f] = f.read_bytes()
        return snap

    def changed(self, before: dict[Path, bytes], paths: list[str]) -> list[str]:
        """Repository paths of the files that were added, removed or rewritten since the snapshot."""
        after = self.snapshot(paths)
        return sorted(self.rel(f) for f in set(before) | set(after) if before.get(f) != after.get(f))

    def restore(self, before: dict[Path, bytes], paths: list[str]) -> None:
        """Put the snapshot back: rewritten files restored, added files removed."""
        after = self.snapshot(paths)
        for f in after:
            if f not in before:
                f.unlink()
        for f, b in before.items():
            if after.get(f) != b:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b)

    # ---------------------------------------------------------------- the pipeline
    def pipeline(self, steps: list[tuple[str, Callable[[], bool]]], skip: set[str], keep_going: bool, stop: set[str]) -> bool:
        """Run the steps in order and print a timed summary. A failure in a `stop` step ends the run unless keep_going."""
        results = []
        for name, fn in steps:
            if name in skip:
                results.append((name, INFO, 0.0, "skipped"))
                continue
            t0 = time.time()
            try:
                ok = fn()
            except SystemExit as e:  # a step refused to start (a usage or environment error)
                if e.code not in (None, 0) and not isinstance(e.code, int):
                    say(f"  {FAIL} {e.code}")
                ok = e.code in (None, 0)
            results.append((name, OK if ok else FAIL, time.time() - t0, ""))
            if not ok and name in stop and not keep_going:
                break
        head("summary")
        for name, s, dt, note in results:
            say(f"  {name:<10} {s:<{MARK_W}} {dt:6.1f}s  {note}")
        return all(s != FAIL for _, s, _, _ in results)
