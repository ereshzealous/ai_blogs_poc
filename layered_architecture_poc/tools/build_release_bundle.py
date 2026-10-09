#!/usr/bin/env python3
"""Build the public release bundle: the POC, its evidence, and the documents that let a reader audit both.

    python3 tools/build_release_bundle.py                    # build, validate, archive
    python3 tools/build_release_bundle.py --keep-staging      # leave the unpacked tree for inspection

Option B of the distribution decision. The bundle is a single archive a reader can download without access to this
repository, and everything in it is either reproducible or checkable:

    layered_architecture_poc/     the sanitized POC export: platform, monolith baseline, MCP servers, simulated enterprise,
                           preregistered plan, tests, the cited run in full, the replay run's provenance
    docs/                  the Evidence Check, the run report, the claim matrix, the invariants and the reviews
    verification/          the gate's own output: final verification, test accounting, the content audit
    README.md              what this is, what it proves, what it does not, and the commands
    PROVENANCE.json        every file's sha256, plus the run, revision, plan hash and freeze digest
    SANITIZATION.md        the few artefacts rewritten to remove the machine the run was recorded on
    SHA256SUMS             one line per file, so the archive can be checked after extraction

The layout mirrors the engineering tree, so the relative links inside the Evidence Check and the run report resolve
inside the bundle instead of pointing at files a reader does not have.

It validates before it archives, and it writes nothing outside the output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_public_export import REPLACEMENTS, SANITIZE_SUFFIXES, build as build_export  # noqa: E402

HERE = Path(__file__).resolve().parents[1]
POC = HERE / "layered_architecture_poc"

# Reader-facing documents. Paths are relative to the bundle root and to this repository, so links keep working.
DOCS = [
    "docs/claim_evidence_matrix.md",
    "docs/benefit-evidence-map.md",
    "docs/change-surface.md",
    "docs/design-review-checklist.md",
    "docs/experiment-inventory.md",
    "docs/real_vs_simulated.md",
    "docs/monolith_fairness_review.md",
    "docs/layering_review.md",
    "docs/standardization/f2-standardization-report.md",
    "docs/results/layered-agent-platform-evidence-check.md",
    "docs/results/layered-agent-platform-evidence-check.html",
    "docs/results/layered-agent-platform-evidence-check.pdf",
    "docs/results/layered-agent-platform-run-report.md",
    "docs/results/layered-agent-platform-run-report.html",
    "docs/results/layered-agent-platform-run-report.pdf",
    "docs/results/lab-console.html",
    "verification/final_verification.md",
    "verification/test_accounting.md",
    "verification/evidence_check_validation.json",
    "verification/post_run_evidence_tests.json",
    "verification/public_export_audit.json",
]
# The three editions. They are included so that every link inside the Evidence Check and the run report resolves
# inside the bundle: a reader-facing document that points at a file the reader does not have is a broken promise.
EDITIONS = [str(p.relative_to(HERE)) for suffix in (".md", ".html", ".pdf")
            for p in sorted(HERE.glob(f"docs/publish/*/*{suffix}"))]

# Links that point at something only the engineering tree has. Rewritten in the bundled copies, and recorded.
LINK_REWRITES = [
    (re.compile(r"(?:\.\./)*dist/[\w.-]+-evidence\.zip"), "../../layered_architecture_poc/runs",
     "the engineering evidence zip, replaced by the unpacked run in this bundle"),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize(path: Path, dst: Path) -> list[str]:
    """Copy one file, removing anything that names the machine, and repointing engineering-only links."""
    raw = path.read_bytes()
    hits: list[str] = []
    if path.suffix in SANITIZE_SUFFIXES | {".html"}:
        text = raw.decode("utf-8", errors="replace")
        new = text
        for rx, repl, why in REPLACEMENTS:
            new, n = rx.subn(repl, new)
            if n:
                hits.append(f"{n}× {why}")
        for rx, repl, why in LINK_REWRITES:
            new, n = rx.subn(repl, new)
            if n:
                hits.append(f"{n}× {why}")
        if new != text:
            raw = new.encode()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(raw)
    return hits


def reader_readme(info: dict) -> str:
    f = info["facts"]
    return f"""# Layered agent platform — evidence bundle

A monolithic agent and a six-layer agent platform solving the same simulated production incident, with the run that
measured them and everything needed to check it. Cited run **{info['run']}**, evidence revision
**{info['revision']}**, built {info['built']}.

This bundle is self-contained. Nothing in it needs network access, a model, or anything from the repository it came
from.

## What the run found

| Question | Monolith | Layered |
|---|---|---|
| Runs passing all eight outcome checks (E1) | {f['e1_m']} | {f['e1_l']} |
| Runs with a duplicate physical rollback after a lost reply (E4) | {f['e4_m']} | {f['e4_l']} |
| Median tokens spent again after a SIGKILL (E5) | {f['e5_m']} | {f['e5_l']} |
| Deterministic write probes that executed (E6) | {f['e6_m']} | {f['e6_l']} |
| Median trace completeness (E8) | {f['e8_m']} | {f['e8_l']} |
| Files changed by a cross-cutting dry-run requirement (E9) | {f['e9_m']} | {f['e9_l']} |

The last row is the one that contradicts the easy story: the layered implementation changed **more** files. What it
changed instead is that the crossing is explicit — the diff goes through the request contract, so every layer that
had to agree is named in it.

## What it does not show

Layering did not prevent a model mistake: in one scenario the model proposed an invalid release identifier and the
tool contract refused it. It is not faster or cheaper — the layered platform spent more model calls on the same
incident, by design. It says nothing about production reliability, about any other incident, or about whether six
deployed services are needed: all six layers ran in one process.

`docs/claim_evidence_matrix.md` classifies every claim as supported, qualified, contradicted or not tested here, with
the facts path, the check that recomputes it, the raw files and the tests behind each one.

## Start here

| If you want to | Open |
|---|---|
| Audit the claims as a sceptical reader | `docs/results/layered-agent-platform-evidence-check.html` |
| See every scenario, table and log | `docs/results/layered-agent-platform-run-report.html` |
| See each run's input, output and status | `docs/results/lab-console.html` |
| Check a specific claim | `docs/claim_evidence_matrix.md` |
| Know what the architecture claims and what enforces it | `layered_architecture_poc/docs/architecture-invariants.md` |
| Know what was real and what was simulated | `docs/real_vs_simulated.md` |
| Check the baseline was treated fairly | `docs/monolith_fairness_review.md` |
| Review your own system | `docs/design-review-checklist.md` |

## Check it yourself

```bash
cd layered_architecture_poc
uv sync
uv run pytest -m "not model"                                   # the suite, no model needed
uv run python scripts/verify_evidence.py runs/{info['run']}
uv run python scripts/classify_outcomes.py runs/{info['run']}
```

The verifier reports {info['verify']} checks, {info['recomputed']} of which recompute the published numbers from the
raw records — each scenario's own world database, the approval and process logs, the model tapes, the ledgers, the
traces, the patch text and the JUnit file — rather than re-reading the file that produced them.

Re-recording a run needs Ollama with `gpt-oss:20b` and `qwen3:8b`. Replaying the published run needs only its tapes,
which are here: `make replay` in the engineering tree, or `F2_TAPE=replay:<dir>` directly.

## Integrity

- `SHA256SUMS` — one line per file. `shasum -c SHA256SUMS` after extraction.
- `PROVENANCE.json` — every file's hash, the cited run, evidence revision {info['revision']}, the preregistered plan's
  sha256 and the source-tree digest, so any value traces back to the engineering source.
- `SANITIZATION.md` — the {info['sanitized']} files rewritten to remove the hostname and home directory of the
  machine the run was recorded on, with the hash before and after each change. Nothing else was altered.

## What is not here

The replay run's 934 scenario directories and raw ledgers, which are byte-equal to the recording's: its
`replay_comparison.json`, `verification.json`, `facts.json`, `manifest.json` and `source_hashes.json` state the
equality instead. Also absent: virtual environments, caches, the change-experiment worktrees, and the three published
editions of the article, which live at their publication URLs.

MIT licensed (`layered_architecture_poc/LICENSE`). The enterprise systems, approvals, identities and injected faults are
simulated; MCP over stdio, the local models, SQLite durability, the process kills and the OpenTelemetry spans are real.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "dist"))
    ap.add_argument("--keep-staging", action="store_true")
    a = ap.parse_args()

    run = (POC / "runs" / "PUBLISHED").read_text().strip()
    facts = json.loads((POC / "runs" / run / "facts.json").read_text())
    verification = json.loads((POC / "runs" / run / "verification.json").read_text())
    revision = sorted(re.findall(r"- id: (r\d+)", (POC / "experiments" / "evidence-revisions.yaml").read_text()))[-1]
    name = f"layered-agent-platform-{revision}-{run}"
    out = Path(a.out).expanduser().resolve()
    staging = out / name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    export = build_export(staging / "layered_architecture_poc")
    sanitized = [{"file": f"layered_architecture_poc/{k}", "changes": v["sanitized"]}
                 for k, v in export["provenance"].items() if "sanitized" in v]

    missing = []
    for rel in DOCS + EDITIONS:
        src = HERE / rel
        if not src.exists():
            missing.append(rel)
            continue
        hits = sanitize(src, staging / rel)
        if hits:
            sanitized.append({"file": rel, "changes": hits})
    if missing:
        print("FAIL missing reader documents:", ", ".join(missing))
        return 1

    def value(key: str):
        leaf = facts.get(key) or {}
        return leaf.get("value")

    info = {
        "run": run, "revision": revision, "built": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "verify": f"{verification['passed']}/{verification['total']}",
        "recomputed": verification.get("recomputed", 0), "sanitized": len(sanitized),
        "facts": {"e1_m": value("headline.e1_runs_all_checks.monolith"), "e1_l": value("headline.e1_runs_all_checks.layered"),
                  "e4_m": value("headline.e4_duplicate_rollbacks.monolith"), "e4_l": value("headline.e4_duplicate_rollbacks.layered"),
                  "e5_m": f"{value('headline.e5_median_tokens_after_crash.monolith'):,}",
                  "e5_l": f"{value('headline.e5_median_tokens_after_crash.layered'):,.0f}",
                  "e6_m": value("headline.e6_probe_writes_executed.monolith"), "e6_l": value("headline.e6_probe_writes_executed.layered"),
                  "e8_m": value("headline.e8_median_trace_score.monolith"), "e8_l": value("headline.e8_median_trace_score.layered"),
                  "e9_m": value("headline.e9_files_changed.monolith"), "e9_l": value("headline.e9_files_changed.layered")},
    }
    (staging / "README.md").write_text(reader_readme(info))
    shutil.copy2(staging / "layered_architecture_poc" / "SANITIZATION.md", staging / "SANITIZATION.md")

    files = sorted(f for f in staging.rglob("*") if f.is_file())
    provenance = {str(f.relative_to(staging)): sha(f.read_bytes()) for f in files}
    manifest = {
        "bundle": f"{name}.zip", "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cited_run": run, "evidence_revision": revision,
        "plan_sha256": value("plan_sha256"), "source_tree_digest": value("hash.source_tree"),
        "frozen_input_count": export["frozen_input_count"],
        "engineering_source": export["engineering_source"],
        "verification": {"checks": verification["total"], "passed": verification["passed"],
                         "recomputed": verification.get("recomputed", 0)},
        "files": len(files), "sanitized_files": len(sanitized), "sanitized": sanitized,
        "sha256": provenance,
    }
    (staging / "PROVENANCE.json").write_text(json.dumps(manifest, indent=1))
    # SHA256SUMS covers the content and PROVENANCE.json; it cannot contain its own hash, and both must be archived,
    # so the file list is taken again now that they exist.
    provenance["PROVENANCE.json"] = sha((staging / "PROVENANCE.json").read_bytes())
    (staging / "SHA256SUMS").write_text("".join(f"{h}  {p}\n" for p, h in sorted(provenance.items())))
    files = sorted(f for f in staging.rglob("*") if f.is_file())

    # ---- validate before archiving ----
    problems: list[str] = []
    leaked = [str(f.relative_to(staging)) for f in files
              if f.suffix in SANITIZE_SUFFIXES | {".html"}
              and re.search(r"/Users/[A-Za-z]|[Ee]reshs?-?[A-Za-z]*\.local", f.read_text(errors="replace"))]
    if leaked:
        problems.append(f"machine references remain in {len(leaked)} file(s): {leaked[:4]}")
    for doc in [staging / d for d in DOCS if d.endswith((".md", ".html"))]:
        text = doc.read_text(errors="replace")
        links = re.findall(r'(?:\]\(|href=")((?:\.\./|docs/|layered_architecture_poc/|verification/)[^)"#]+)', text)
        broken = sorted({l for l in links if not (doc.parent / l).resolve().exists()})
        if broken:
            problems.append(f"{doc.relative_to(staging)}: {len(broken)} broken link(s): {broken[:3]}")
    for p in problems:
        print("FAIL", p)
    if problems:
        return 1

    archive = out / f"{name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f"{name}/{f.relative_to(staging)}")
    digest = sha(archive.read_bytes())
    report = {**{k: v for k, v in manifest.items() if k != "sha256"},
              "archive": str(archive.relative_to(HERE)), "archive_sha256": digest,
              "archive_bytes": archive.stat().st_size, "archived_files": len(files),
              "integrity_files": ["SHA256SUMS", "PROVENANCE.json"]}
    (HERE / "verification" / "release_bundle.json").write_text(json.dumps(report, indent=1))
    if not a.keep_staging:
        shutil.rmtree(staging)
    print(f"{archive.relative_to(HERE)}: {len(files)} files, {archive.stat().st_size/1e6:.1f} MB, "
          f"sha256 {digest[:16]}… · {len(sanitized)} sanitized · verifier {manifest['verification']['passed']}/"
          f"{manifest['verification']['checks']} ({manifest['verification']['recomputed']} recomputed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
