"""verification/evidence-manifest.json: every published artefact of S2 with its sha256, tied to one run.

    python3 tools/build_evidence_manifest.py

Lists the published run (its SHA256SUMS digest and file count), the frozen inputs (FROZEN.sha256 digest and count), the
three documents in every format, the figures in every export format, the research files and the verification outputs.
A reader can check that the editions, the figures and the run belong together: the editions name the run, the run's
SHA256SUMS covers its rows and tapes, and this file covers the rest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POC = ROOT / "enterprise_knowledge_rag_poc"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def files(*globs: str) -> dict[str, str]:
    out = {}
    for g in globs:
        for p in sorted(ROOT.glob(g)):
            if p.is_file():
                out[str(p.relative_to(ROOT))] = sha(p)
    return out


def main() -> None:
    run = (POC / "runs" / "PUBLISHED").read_text().strip()
    rdir = POC / "runs" / run
    sums = rdir / "SHA256SUMS"
    frozen = POC / "experiments" / "FROZEN.sha256"
    m = {
        "run": run,
        "run_sha256sums": {"sha256": sha(sums), "files": len(sums.read_text().splitlines())} if sums.exists() else None,
        "frozen_inputs": {"sha256": sha(frozen), "files": len(frozen.read_text().splitlines()),
                          "frozen_at": (POC / "experiments" / "FROZEN.at").read_text().strip()},
        "facts": {"path": f"enterprise_knowledge_rag_poc/runs/{run}/facts.json", "sha256": sha(rdir / "facts.json"),
                  "count": len(json.loads((rdir / "facts.json").read_text()))},
        "derived_facts": files("docs/derived-facts.json"),
        "documents": files("medium/*", "technical/*", "results/*"),
        "poc_readme": files("enterprise_knowledge_rag_poc/README.md"),
        "figures": files("diagrams/premium/svg/*.svg", "diagrams/premium/png/*.png", "diagrams/premium/excalidraw/*.excalidraw"),
        "figure_manifest": files("diagrams/manifest.json", "diagrams/scenes.json"),
        "research": files("research/*"),
        "verification": {k: v for k, v in files("verification/*").items() if not k.endswith("evidence-manifest.json")},
        "exploratory": files(f"enterprise_knowledge_rag_poc/runs/{run}-exploratory/*"),
    }
    (ROOT / "verification").mkdir(exist_ok=True)
    (ROOT / "verification" / "evidence-manifest.json").write_text(json.dumps(m, indent=1) + "\n")
    n = sum(len(v) for v in m.values() if isinstance(v, dict) and all(isinstance(x, str) for x in v.values()))
    print(f"evidence manifest: run {run}, {n} files hashed -> verification/evidence-manifest.json")


if __name__ == "__main__":
    main()
