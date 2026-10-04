"""What this machine has for the Learning 01 POC, and whether a live run can start.

    python scripts/doctor.py --endpoint DESC              the machine check (./sprawl doctor)
    python scripts/doctor.py --live --split blind|dev     refuse a live run that cannot start (./sprawl run)

Ollama is always asked at http://127.0.0.1:11434: ./sprawl relays that address when --ollama-host is elsewhere.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

POC = Path(__file__).resolve().parents[1]
ROOT = POC.parent
MODELS = ("gpt-oss:20b", "nomic-embed-text:latest")
TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def paint(s: str, code: str) -> str:
    return f"\033[{code}m{s}\033[0m" if TTY else s


OK, FAIL, WARN, INFO = paint("ok", "32"), paint("FAIL", "31;1"), paint("warn", "33"), paint("··", "2")


def api(path: str, timeout: float = 5.0):
    with urllib.request.urlopen(f"http://127.0.0.1:11434{path}", timeout=timeout) as r:
        return json.load(r)


def ollama_models() -> dict[str, str] | None:
    try:
        return {m["name"]: m["digest"][:12] for m in api("/api/tags")["models"]}
    except Exception:
        return None


def live_guard(split: str, allow_dirty: bool) -> None:
    if split == "blind" and not (ROOT / ".git").exists() and not allow_dirty:
        sys.exit("a blind run records the commit it ran from; mount the repository with its .git "
                 "(docker compose does this) or pass --allow-dirty for an unrecorded run")
    models = ollama_models()
    if models is None:
        sys.exit("live runs need Ollama: install it (https://ollama.com), or pass --ollama-host URL")
    missing = [m for m in MODELS if m not in models]
    if missing:
        sys.exit("missing model(s): " + ", ".join(missing) + " -> ollama pull " + " ".join(missing))


def doctor(endpoint: str) -> None:
    rows, live_ok = [], True
    in_container = Path("/.dockerenv").exists() or os.environ.get("SPRAWL_IN_CONTAINER") == "1"
    host = f"{platform.system()} {platform.release()} · {platform.machine()}"
    if platform.system() == "Darwin":
        chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
        mem = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip()
        host = f"macOS {platform.mac_ver()[0]} · {chip} · {int(mem) / 2**30:.0f} GB" if mem.isdigit() else host
    rows.append(("host", OK, host + (" · container" if in_container else "")))
    rows.append(("python", OK if sys.version_info[:2] == (3, 12) else WARN, f"{platform.python_version()} (runs used 3.12.13)"))
    uv = shutil.which("uv")
    rows.append(("uv", OK if uv or in_container else WARN, subprocess.run([uv, "--version"], capture_output=True, text=True).stdout.strip() if uv else "not on PATH (the container does not need it)"))
    try:
        mcp_v = importlib.metadata.version("mcp")
        rows.append(("mcp sdk", OK if mcp_v == "2.2.0" else FAIL, f"mcp {mcp_v} (pinned 2.2.0)"))
    except importlib.metadata.PackageNotFoundError:
        rows.append(("mcp sdk", FAIL, "not installed: cd poc && uv sync"))
        live_ok = False
    frozen = json.loads((ROOT / "experiment" / "frozen-hashes.json").read_text())["models"]
    models = ollama_models()
    if models is None:
        rows.append(("ollama", WARN, f"unreachable at {endpoint}; evidence mode still works, live runs need it"))
        live_ok = False
    else:
        try:
            ver = api("/api/version")["version"]
        except Exception:
            ver = "?"
        rows.append(("ollama", OK, f"{ver} at {endpoint}"))
        for m in MODELS:
            have, want = models.get(m), frozen.get(m)
            state = OK if have == want else (WARN if have else FAIL)
            live_ok &= have is not None
            rows.append((m, state, f"digest {have or 'missing'} (frozen {want})" + ("" if have else f": ollama pull {m}")))
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" if Path("/Applications/Google Chrome.app").exists() else None)
    rows.append(("chrome", OK if chrome else INFO, "found (article PDFs and figure export)" if chrome else "not found (only needed to rebuild article PDFs)"))
    docker = shutil.which("docker")
    rows.append(("docker", OK if docker else INFO, "found" if docker else "not found (optional)"))
    cache = POC / "data" / "embeddings" / "nomic-embed-text.json"  # ./sprawl restores it from the committed snapshot
    rows.append(("embedding cache", OK if cache.exists() else WARN, os.environ.get("SPRAWL_EMBED_CACHE") or ("present" if cache.exists() else "missing")))
    rows.append(("git", OK if (ROOT / ".git").exists() else WARN, "repository present" if (ROOT / ".git").exists() else "no .git: run ids cannot record a commit"))
    for k, s, v in rows:
        print(f"  {k:<26} {s:<{13 if TTY else 4}} {v}")
    print("\n  evidence mode (verify, test, analyze, replay, report): ready")
    print(f"  live mode (run): {'ready' if live_ok else 'not ready: see above'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:11434 (local)")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--allow-dirty", action="store_true")
    ns = ap.parse_args()
    live_guard(ns.split, ns.allow_dirty) if ns.live else doctor(ns.endpoint)


if __name__ == "__main__":
    main()
