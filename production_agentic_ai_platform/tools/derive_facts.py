"""docs/facts.json: every number and identifier the articles and figures may print, read from the published run's proof pack.

    python3 tools/derive_facts.py

The published run is the one evidence/published.json names (Production AI Engineering Proof Contract v1). Its proof
pack (production_agentic_ai_platform/evidence/runs/<run>/results.json) carries every fact with its source, derived by the
POC's tools/proof_facts.py from the recorded files; this script copies them, adding the POC folder to each source so the
path resolves from the article repository. Nothing is typed here. The documents reference facts as {{key}}; an unknown
key fails the build.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "production_agentic_ai_platform"
pub = json.loads((POC / "evidence" / "published.json").read_text())
res = json.loads((POC / pub["results"]).read_text())
facts = {k: {"value": f["value"], "display": f["display"], "source": f"{POC.name}/{f['source']}" if f.get("source") else f"{POC.name}/{pub['results']}"}
         for k, f in sorted(res["facts"].items())}
facts["published.run_id"] = {"value": pub["run_id"], "display": pub["run_id"], "source": f"{POC.name}/evidence/published.json"}
facts["published.promoted_at"] = {"value": pub["promoted_at"][:10], "display": pub["promoted_at"][:10], "source": f"{POC.name}/evidence/published.json"}
facts["published.previous_run"] = {"value": pub["history"][0]["run_id"], "display": pub["history"][0]["run_id"], "source": f"{POC.name}/evidence/published.json → history"}
out = ROOT / "docs" / "facts.json"
out.write_text(json.dumps(facts, indent=1, default=str, ensure_ascii=False))
print(f"{len(facts)} facts from the published run {pub['run_id']} -> {out.relative_to(ROOT)}")
