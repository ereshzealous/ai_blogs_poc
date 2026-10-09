"""Apply a declared evidence revision to a recorded run: re-score from the run's own raw files, keep the as-recorded
values next to the new ones, and record the revision in the manifest.  No scenario is re-executed.

    uv run python scripts/rescore.py runs/<id> r2
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml

POC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))
from experiments.scorers import evidence, traces  # noqa: E402


def main(run_dir: Path, rev_id: str) -> None:
    revs = yaml.safe_load((POC / "experiments" / "evidence-revisions.yaml").read_text())["revisions"]
    rev = next(r for r in revs if r["id"] == rev_id)
    for sdir in sorted((run_dir / "scenarios").iterdir()):
        sc = json.loads((sdir / "score.json").read_text())
        raw = {p.stem: evidence.jsonl(p) for p in (sdir / "raw").glob("*.jsonl")}
        if "E8" in rev["affects"]:
            sc.setdefault("trace_as_recorded", sc["trace"])
            sc["trace"] = traces.layered(raw) if sc["arch"] == "layered" else traces.monolith(raw)
        (sdir / "score.json").write_text(json.dumps(sc, indent=1, default=str))
    m = json.loads((run_dir / "manifest.json").read_text())
    applied = [r for r in m.get("evidence_revisions", []) if r["id"] != rev_id]
    applied.append({"id": rev_id, "files": {f: hashlib.sha256((POC / f).read_bytes()).hexdigest() for f in rev["files"]}, "affects": rev["affects"]})
    m["evidence_revisions"] = applied
    sys.path.insert(0, str(POC / "scripts"))
    from record_run import FROZEN, sha_paths  # noqa: E402
    m["revised_hashes"] = {**m.get("revised_hashes", {}), **{k: sha_paths(v) for k, v in FROZEN.items()
                                                               if k != "experiment_plan" and sha_paths(v) != m["hashes"].get(k)}}
    (run_dir / "manifest.json").write_text(json.dumps(m, indent=1))
    print(f"{rev_id} applied to {run_dir.name}: re-scored {len(list((run_dir / 'scenarios').iterdir()))} scenarios")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), sys.argv[2])
