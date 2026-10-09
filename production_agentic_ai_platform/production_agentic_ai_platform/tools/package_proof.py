"""The publication package (Proof Contract §1, uv run pap package): dist/production-agentic-ai-platform-poc.zip.

    uv run python tools/package_proof.py

The POC with its proof definitions, tools, runner, vendored kit, the Proof Lab, and the evidence: the published run named
by evidence/published.json and the runs in its history (their raw files, replays and negative controls), the relocation
record and the last verification. Left out: .venv, caches, evidence/local/ (scratch) and dist/.

Recorded files are never edited, but a known finding of the secret scan (proof/hygiene.toml, e.g. a local path printed
by an early run) is redacted in the package: the match is replaced, and REDACTIONS.json lists each file with its original
and redacted SHA-256 and why. The package is then scanned again and refused if anything is found. Entries are sorted and
carry a fixed timestamp, so the same tree gives the same ZIP; PACKAGE-SHA256SUMS lists every file in it.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
from evidence_kit import proof  # noqa: E402

OUT = ROOT / "dist" / "production-agentic-ai-platform-poc.zip"
SKIP_PARTS = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".DS_Store", "dist", "local"}
STAMP = (2026, 10, 4, 0, 0, 0)


def wanted(p: Path, runs: set[str]) -> bool:
    rel = p.relative_to(ROOT)
    if SKIP_PARTS & set(rel.parts):
        return False
    if rel.parts[:2] == ("evidence", "runs") and len(rel.parts) > 2:
        return rel.parts[2] in runs or rel.parts[2] == "PUBLISHED"
    return True


def main() -> int:
    pub = json.loads((ROOT / "evidence" / "published.json").read_text())
    runs = {pub["run_id"]} | {h["run_id"] for h in pub["history"]}
    hyg = tomllib.loads((ROOT / "proof" / "hygiene.toml").read_text())
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and wanted(p, runs))
    redactions, content = [], {}
    for p in files:
        rel, data = p.relative_to(ROOT).as_posix(), p.read_bytes()
        for k in hyg.get("known", []):
            if rel in k["files"]:
                new = re.sub(k["pattern"], k["redact"], data.decode()).encode()
                if new != data:
                    redactions.append({"file": rel, "pattern": k["pattern"], "redact": k["redact"], "why": k["why"],
                                       "original_sha256": hashlib.sha256(data).hexdigest(), "redacted_sha256": hashlib.sha256(new).hexdigest()})
                    data = new
        content[rel] = data
    content["REDACTIONS.json"] = (json.dumps({"schema": proof.SCHEMA, "redactions": redactions}, indent=1) + "\n").encode()
    content["PACKAGE-SHA256SUMS"] = "".join(f"{hashlib.sha256(d).hexdigest()}  {r}\n" for r, d in sorted(content.items())).encode()
    # scan what will ship (as text), after redaction
    tmp = ROOT / "dist" / ".scan"
    tmp.mkdir(parents=True, exist_ok=True)
    hits = []
    for rel, d in content.items():
        if Path(rel).suffix in (".json", ".jsonl", ".md", ".txt", ".toml", ".yaml", ".html", ".diff", ".py"):
            f = tmp / "x"
            f.write_bytes(d)
            for h in proof.scan([f], tmp, allow=hyg.get("allow", [])):
                hits.append(f"{rel}:{h['line']}: {h['kind']}")
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    if hits:
        print("refused: the package would publish\n  " + "\n  ".join(hits[:20]))
        return 1
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in sorted(content):
            info = zipfile.ZipInfo(f"{ROOT.name}/{rel}", STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, content[rel])
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    (OUT.parent / (OUT.name + ".sha256")).write_text(f"{digest}  {OUT.name}\n")
    print(json.dumps({"zip": str(OUT.relative_to(ROOT)), "files": len(content), "kb": OUT.stat().st_size // 1024, "published": pub["run_id"],
                      "runs": sorted(runs), "redacted": [r["file"] for r in redactions], "sha256": digest}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
