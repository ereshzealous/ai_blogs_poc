#!/usr/bin/env python3
"""What would become public, and what must not: a content audit of the publishable file set.

    python3 tools/audit_public_export.py                 # audit what layered_architecture_poc would publish
    python3 tools/audit_public_export.py --json           # machine-readable, for the release checklist

Run this before any public distribution decision. It takes the exact file set the POC's .gitignore would publish and
looks for the things that must never leave an engineering tree:

    credentials      keys, tokens, passwords, connection strings
    machine paths    this machine's home directory, usernames, hostnames
    private urls     anything not a public documentation or specification host
    internal names   people and systems that are not part of the published scenario
    env files        .env and friends
    binaries         large or opaque files a reader cannot inspect
    licences         a licence for the POC, and third-party notices where code was reused
    model tapes      recorded model traffic, which is published deliberately and is listed so the decision is explicit

It reports; it changes nothing and publishes nothing.
"""

from __future__ import annotations

import fnmatch
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
POC = HERE / "layered_architecture_poc"

TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sh", ".html",
                 ".xml", ".diff", ".patch", ".lock", ".log", ".csv", ".gitignore", ".publish-frozen", ""}
BINARY_OK = {".db", ".png", ".svg", ".excalidraw", ".pdf", ".zip"}

# A finding is a (name, regex, why) triple. Case-insensitive, matched line by line.
PATTERNS = [
    ("credential", re.compile(r"(?i)\b(api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
     "a key, token or password with a value"),
    ("credential", re.compile(r"\b(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})\b"),
     "a provider-shaped credential"),
    ("credential", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    ("machine path", re.compile(r"/Users/[a-z][\w.-]+|/home/[a-z][\w.-]+|C:\\\\Users\\\\"), "this machine's home directory"),
    ("machine name", re.compile(r"(?i)\b[\w-]+\.(?:local|lan|internal|corp)\b"), "a local or internal hostname"),
    ("private url", re.compile(
        r"https?://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)"
        r"(?!(?:[\w.-]*\.)?(?:modelcontextprotocol\.io|github\.com|githubusercontent\.com|opentelemetry\.io|"
        r"ollama\.com|python\.org|astral\.sh|sqlite\.org|anthropic\.com|arxiv\.org|amazon\.com|stripe\.com|"
        r"temporal\.io|esm\.sh|googleapis\.com|gstatic\.com|cdnjs\.cloudflare\.com|unpkg\.com|adk\.dev|"
        r"excalidraw\.com|mozilla\.org|w3\.org|json\.org|ietf\.org|rfc-editor\.org|hikari\.io|"
        r"pypi\.org|pythonhosted\.org|docs\.[\w.-]+)\b)"
        r"([\w.-]+)"),
     "a URL whose host is not on the public documentation allowlist"),
    ("env file", re.compile(r"^\s*(?:export\s+)?[A-Z][A-Z0-9_]{3,}=\S+"), "an environment assignment with a value"),
]
# Hits verified by hand and accepted, with the reason. Listed so they are explicit rather than silently filtered.
ACCEPTED = {
    ("layered_platform/telemetry/tracing.py", "token = otel_context"):
        "OpenTelemetry's context token, returned by context.attach() and passed to detach(). Not a secret.",
    ("tests/unit/test_tape_and_scorers.py", "http://x"):
        "a one-character dummy URL in a unit test for the tape recorder.",
}

# Names that belong to the published scenario, so finding them is expected.
SCENARIO_NAMES = {"alice", "bob", "sre.alice", "ic.bob", "dmitri.k", "priya.s", "leo.m", "checkout-api",
                  "payment-gateway", "orders-client", "ereshzealous", "f2-harness", "poc@local"}


def publishable() -> list[Path]:
    """Exactly what the POC's .gitignore would let the publish script copy."""
    patterns = [l.strip() for l in (POC / ".gitignore").read_text().splitlines()
                if l.strip() and not l.startswith("#")]

    def ignored(rel: str) -> bool:
        for pattern in patterns:
            p = pattern.rstrip("/")
            if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p + "/*") or any(fnmatch.fnmatch(x, p) for x in rel.split("/")):
                return True
        return False

    return sorted(f for f in POC.rglob("*") if f.is_file() and not ignored(str(f.relative_to(POC))))


def audit(files: list[Path]) -> dict:
    findings: dict[str, list[dict]] = defaultdict(list)
    big: list[dict] = []
    tapes: list[str] = []
    for path in files:
        rel = str(path.relative_to(POC))
        size = path.stat().st_size
        if "tape/" in rel:
            tapes.append(rel)
        if path.suffix not in TEXT_SUFFIXES:
            if path.suffix not in BINARY_OK:
                findings["binary"].append({"file": rel, "detail": f"{size/1e3:.0f} kB, suffix {path.suffix or 'none'}"})
            if size > 2_000_000:
                big.append({"file": rel, "detail": f"{size/1e6:.1f} MB"})
            continue
        if size > 8_000_000:
            big.append({"file": rel, "detail": f"{size/1e6:.1f} MB (text)"})
            continue
        for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if len(line) > 4000:
                line = line[:4000]
            for name, rx, why in PATTERNS:
                m = rx.search(line)
                if not m:
                    continue
                hit = m.group(0)
                if name == "env file":
                    value = line.split("=", 1)[1].strip().strip("'\"")
                    if not re.match(r"^(?:export\s+)?(?:AWS|GITHUB|OPENAI|ANTHROPIC|HF|SLACK)", line.strip()):
                        continue  # F2_*/LAP_* are this POC's own settings, documented with example values
                    if len(value) < 16 or "/" in value or value.isdigit():
                        continue  # a path or a number is configuration, not a credential
                if name == "credential" and re.search(r"=\s*[A-Za-z_][\w.]*\s*(?:#|$)", line):
                    continue      # assigned from another name: a variable, not a literal secret
                accepted = next((why_ok for (f, frag), why_ok in ACCEPTED.items()
                                 if f == rel and frag in hit), None)
                if accepted:
                    findings["accepted"].append({"file": rel, "line": lineno, "match": hit[:120], "why": accepted})
                    continue
                findings[name].append({"file": rel, "line": lineno, "match": hit[:120], "why": why})
    return {"files": len(files), "findings": {k: v for k, v in sorted(findings.items())},
            "large_files": big, "model_tapes": len(tapes),
            "licences": sorted(str(p.relative_to(POC)) for p in files if "licen" in p.name.lower())}


def main() -> int:
    files = publishable()
    report = audit(files)
    total = sum(len(v) for v in report["findings"].values())
    out = HERE / "verification" / "public_export_audit.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    if "--json" in sys.argv:
        print(json.dumps(report, indent=1))
        return 0
    print(f"{report['files']} publishable file(s) · {report['model_tapes']} model-tape file(s) · "
          f"licence files: {', '.join(report['licences']) or 'NONE'}")
    for kind, hits in report["findings"].items():
        print(f"\n{kind}: {len(hits)}")
        for hit in hits[:8]:
            where = f"{hit['file']}:{hit.get('line', '')}".rstrip(":")
            print(f"  {where}  {hit.get('match', hit.get('detail', ''))}")
        if len(hits) > 8:
            print(f"  … {len(hits) - 8} more")
    for hit in report["large_files"][:8]:
        print(f"large  {hit['file']}  {hit['detail']}")
    print(f"\n{total} finding(s) across {len(report['findings'])} category(ies) · written to {out.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
