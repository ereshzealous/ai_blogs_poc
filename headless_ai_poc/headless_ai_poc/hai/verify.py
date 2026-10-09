"""EVIDENCE VERIFICATION for a recorded run: what a reader runs to check the published numbers without trusting them.

    uv run hai verify [RUN_ID]            -> report on stdout, runs/verification/<RUN_ID>.{txt,json}; exit 1 unless VERIFIED
    uv run hai verify [RUN_ID] --check    the same, read-only (used by scripts/publish-checks.sh)

Sections, each PASS or FAIL:

    Manifest     the run's manifest names the run, and the config it hashed is the config in this folder
    Integrity    SHA256SUMS lists every file of the run and every hash matches
    Checks       every architecture check in checks.json passed
    Claims       every claim in proof/claims.toml rests on checks that exist and passed, and on facts the run recorded
    Replay       the seven experiments, re-run into a temporary folder, reproduce every file byte for byte
                 (the manifest's Python version is the only field allowed to differ: it describes the machine)
    Scan         no credential and no local path (home, temp, file://, this folder's absolute path) in the run
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from hai.config import CONFIG
from hai.experiments import ROOT, run
from hai.vendor.publication import local_path_findings

SECRETS = [
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("API key (sk-)", r"\bsk-[A-Za-z0-9_-]{20,}"),
    ("AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    ("Slack token", r"\bxox[abpors]-[A-Za-z0-9-]{10,}"),
    ("bearer token", r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
]


def published() -> str:
    return (ROOT / "runs" / "PUBLISHED").read_text().strip()


def _manifest(rd: Path, run_id: str) -> tuple[bool, str]:
    m = json.loads((rd / "manifest.json").read_text())
    now = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(CONFIG.glob("*.yaml"))}
    drift = sorted(k for k in set(now) | set(m["config_sha256"]) if now.get(k) != m["config_sha256"].get(k))
    ok = m["run_id"] == run_id and not drift
    return ok, f"run {m['run_id']}; {len(now)} config files hashed" + (f"; config changed since the run: {drift}" if drift else ", unchanged")


def _integrity(rd: Path) -> tuple[bool, str]:
    sums = rd / "SHA256SUMS"
    if not sums.exists():
        return False, "SHA256SUMS missing"
    listed = dict(reversed(line.split("  ", 1)) for line in sums.read_text().splitlines() if line)
    files = {f.relative_to(rd).as_posix() for f in rd.rglob("*") if f.is_file() and f.name != "SHA256SUMS"}
    bad = sorted(p for p, h in listed.items() if not (rd / p).is_file() or hashlib.sha256((rd / p).read_bytes()).hexdigest() != h)
    unlisted = sorted(files - set(listed))
    return not bad and not unlisted, f"{len(listed)} files match SHA256SUMS" + (f"; mismatched {bad}" if bad else "") + \
        (f"; not listed {unlisted}" if unlisted else "")


def _checks(rd: Path) -> tuple[bool, str, list[dict[str, Any]]]:
    checks = json.loads((rd / "checks.json").read_text())
    failed = [f"{c['experiment']}: {c['check']}" for c in checks if not c["passed"]]
    return not failed, f"{len(checks) - len(failed)}/{len(checks)} architecture checks passed" + (f"; failed {failed}" if failed else ""), checks


def _claims(rd: Path, checks: list[dict[str, Any]]) -> tuple[bool, str]:
    claims = tomllib.loads((ROOT / "proof" / "claims.toml").read_text())["claims"]
    facts = json.loads((rd / "facts.json").read_text())
    by_name = {f"{c['experiment']}: {c['check']}": c for c in checks}
    probs = []
    for c in claims:
        for name in (list(by_name) if c.get("checks") == ["*"] else c.get("checks", [])):
            if name not in by_name:
                probs.append(f"{c['id']}: no check '{name}'")
            elif not by_name[name]["passed"]:
                probs.append(f"{c['id']}: check '{name}' failed")
        probs += [f"{c['id']}: fact '{f}' not in the run" for f in c.get("facts", []) if f not in facts]
        if c.get("type") != "derived" and not c.get("checks"):
            probs.append(f"{c['id']}: a measured claim must rest on at least one check")
    return not probs, f"{len(claims)} claims traced to checks and facts" + (f"; {probs}" if probs else "")


def _replay(rd: Path, run_id: str) -> tuple[bool, str]:
    tmp = Path(tempfile.mkdtemp(prefix="hai-replay-"))
    try:
        again = run(run_id, out=tmp)
        a = {f.relative_to(rd).as_posix() for f in rd.rglob("*") if f.is_file()}
        b = {f.relative_to(again).as_posix() for f in again.rglob("*") if f.is_file()}
        diff = sorted(a ^ b)
        for p in sorted(a & b):
            x, y = (rd / p).read_bytes(), (again / p).read_bytes()
            if p == "manifest.json":
                x, y = (json.dumps({k: v for k, v in json.loads(z).items() if k != "python"}, sort_keys=True).encode() for z in (x, y))
            if p == "SHA256SUMS":
                x, y = (b"".join(l for l in z.splitlines(True) if not l.endswith(b"  manifest.json\n")) for z in (x, y))
            if x != y:
                diff.append(p)
        return not diff, f"{len(a & b)} files reproduced byte for byte" + (f"; differ: {diff}" if diff else "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _scan(rd: Path) -> tuple[bool, str]:
    files = sorted(f for f in rd.rglob("*") if f.is_file())
    rules = [(k, re.compile(r)) for k, r in SECRETS]
    secrets = [(f.name, k) for f in files for k, rx in rules if rx.search(f.read_text(errors="replace"))]
    paths = local_path_findings(files, ROOT, forbid=[ROOT.resolve(), Path.home()])
    return not secrets and not paths, f"{len(files)} files: no credential, no local path" if not secrets and not paths else \
        f"credentials {secrets[:3]}; local paths {[(p['file'], p['match']) for p in paths[:3]]}"


def verify(run_id: str | None = None, write: bool = True) -> bool:
    run_id = run_id or published()
    rd = ROOT / "runs" / run_id
    rows: list[tuple[str, bool, str]] = []
    if not rd.is_dir():
        rows.append(("Run", False, f"runs/{run_id} not found"))
    else:
        rows.append(("Manifest", *_manifest(rd, run_id)))
        rows.append(("Integrity", *_integrity(rd)))
        ok, detail, checks = _checks(rd)
        rows.append(("Checks", ok, detail))
        rows.append(("Claims", *_claims(rd, checks)))
        rows.append(("Replay", *_replay(rd, run_id)))
        rows.append(("Scan", *_scan(rd)))
    verified = all(ok for _, ok, _ in rows)
    text = "EVIDENCE VERIFICATION\n\n" + "".join(f"{n:<11}{'PASS' if ok else 'FAIL':<6}{d}\n" for n, ok, d in rows) + \
        ("\nVERIFIED\n" if verified else "\nNOT VERIFIED\n")
    print(text, end="")
    if write:
        out = ROOT / "runs" / "verification"
        out.mkdir(exist_ok=True)
        (out / f"{run_id}.txt").write_text(text)
        (out / f"{run_id}.json").write_text(json.dumps({"run_id": run_id, "verified": verified,
                                                        "sections": [{"section": n, "ok": ok, "detail": d} for n, ok, d in rows]}, indent=1) + "\n")
    return verified


if __name__ == "__main__":
    sys.exit(0 if verify(*sys.argv[1:2]) else 1)
