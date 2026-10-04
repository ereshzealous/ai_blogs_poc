"""Freeze (or verify) everything the blind run depends on.

    uv run python scripts/freeze.py                  # write experiment/frozen-hashes.json (r1, the blind-run freeze)
    uv run python scripts/freeze.py --revision r2    # write experiment/frozen-hashes-r2.json (a later evidence revision)
    uv run python scripts/freeze.py --verify         # compare with the current revision; exit 1 on any drift

The blind-run freeze (r1) is never rewritten.  A change to frozen inputs after the run becomes a new evidence revision,
declared in experiment/evidence-revisions.json with the files it changed and how the recorded evidence was re-verified;
--verify checks today's files against the current revision and that it differs from r1 only in the declared files.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

from sprawl_poc.util import DATA_DIR, EXPERIMENT_DIR, POC_ROOT, REPO_ROOT, read_json, sha256_file, write_json

OUT = EXPERIMENT_DIR / "frozen-hashes.json"
REVISIONS = EXPERIMENT_DIR / "evidence-revisions.json"


def freeze_file(revision: str | None) -> Path:
    return OUT if revision in (None, "r1") else EXPERIMENT_DIR / f"frozen-hashes-{revision}.json"


def current_revision() -> dict:
    """The revision today's files should match: the last one in evidence-revisions.json, else the blind-run freeze."""
    if REVISIONS.exists():
        revs = read_json(REVISIONS)
        return next(r for r in revs["revisions"] if r["id"] == revs["current"])
    return {"id": "r1", "freeze": str(OUT.relative_to(REPO_ROOT)), "changed_from_r1": []}


def tree_hash(root: Path, pattern: str) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob(pattern)):
        if "__pycache__" in p.parts:
            continue
        h.update(str(p.relative_to(root)).encode())
        h.update(sha256_file(p).encode())
    return h.hexdigest()


def ollama_digest(name: str) -> str | None:
    out = subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout
    for line in out.splitlines()[1:]:
        parts = line.split()
        if parts and parts[0] == name:
            return parts[1]
    return None


def compute() -> dict:
    files = {
        "benchmark/cases.json": EXPERIMENT_DIR / "benchmark" / "cases.json",
        "preregistration.md": EXPERIMENT_DIR / "preregistration.md",
        "label-review-decisions.md": EXPERIMENT_DIR / "label-review-decisions.md",
        "world/seed.db": DATA_DIR / "world" / "seed.db",
        "poc/uv.lock": POC_ROOT / "uv.lock",
        "poc/pyproject.toml": POC_ROOT / "pyproject.toml",
    }
    for n in (50, 100, 500):
        d = DATA_DIR / "estates" / f"estate-{n}"
        files[f"estate-{n}/registry.yaml"] = d / "registry.yaml"
        files[f"estate-{n}/manifest.json"] = d / "manifest.json"
    hashes = {k: sha256_file(p) for k, p in files.items()}
    for n in (50, 100, 500):
        hashes[f"estate-{n}/servers/*.json"] = tree_hash(DATA_DIR / "estates" / f"estate-{n}" / "servers", "*.json")
    hashes["poc/src/**/*.py"] = tree_hash(POC_ROOT / "src", "*.py")
    for k in ("bench/evaluate.py", "bench/analyze.py", "bench/runner.py", "agent/prompts.py", "control_plane/policy.py", "control_plane/gateway.py"):
        hashes[f"poc/src/sprawl_poc/{k}"] = sha256_file(POC_ROOT / "src" / "sprawl_poc" / k)
    bench = read_json(files["benchmark/cases.json"])
    return {
        "hashes": hashes,
        "cases_sha256": bench["cases_sha256"],
        "counts": bench["counts"],
        "models": {"gpt-oss:20b": ollama_digest("gpt-oss:20b"), "nomic-embed-text:latest": ollama_digest("nomic-embed-text:latest")},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--revision", help="write a later evidence revision (r2, …) instead of the blind-run freeze")
    ns = ap.parse_args()
    now = compute()
    if not ns.verify:
        out = freeze_file(ns.revision)
        if out == OUT and OUT.exists():
            raise SystemExit("the blind-run freeze (r1) is never rewritten; pass --revision r2 (or later)")
        write_json(out, now)
        print(f"wrote {out.relative_to(REPO_ROOT)}: {len(now['hashes'])} hashes")
        return
    rev = current_revision()
    frozen = read_json(REPO_ROOT / rev["freeze"])
    drift = [k for k in sorted(set(frozen["hashes"]) | set(now["hashes"])) if frozen["hashes"].get(k) != now["hashes"].get(k)]
    if frozen["models"] != now["models"]:
        drift.append("models")
    for k in drift:
        print("DRIFT:", k)
    if rev["id"] != "r1":  # a revision may differ from the blind-run freeze only in the files it declares
        r1 = read_json(OUT)["hashes"]
        changed = sorted(k for k in set(r1) | set(frozen["hashes"]) if r1.get(k) != frozen["hashes"].get(k))
        undeclared = sorted(set(changed) - set(rev["changed_from_r1"]))
        for k in undeclared:
            print("UNDECLARED CHANGE FROM r1:", k)
        drift += [f"undeclared:{k}" for k in undeclared]
        print(f"revision {rev['id']}: differs from the blind-run freeze (r1) in {len(changed)} declared input(s): {', '.join(changed)}")
    print(f"FREEZE OK ({rev['id']})" if not drift else f"FREEZE FAILED ({rev['id']}, {len(drift)})")
    sys.exit(1 if drift else 0)


if __name__ == "__main__":
    main()
