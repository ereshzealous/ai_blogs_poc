"""Write diagrams/manifest.json: every F2 figure, its frame name, files, Excalidraw+ location, data sources and provenance.

    python3 tools/diagram_manifest.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "diagrams"
POC = ROOT / "layered_architecture_poc"

ARCH = "Architecture: POC design; no measured values"
SOURCES = {
    "f01": ("Measured + scenario: INC-4917 page from the scenario file, headline facts of the published run", ["facts.json", "../../simulated_enterprise/data/inc4917.yaml"]),
    "f01b": ("Recorded: E5 seed 11 of the published run (score.json of both architectures)", ["scenarios/E5-monolith-s11/score.json", "scenarios/E5-layered-s11/score.json"]),
    "f02": ("Architecture + recorded behaviour of the demo path; no measured values", ["monolith/incident_agent.py", "mcp_servers/servers.py"]),
    "f03": (ARCH, []),
    "f04": ("Architecture: the POC monolith, symbol by symbol", ["monolith/incident_agent.py"]),
    "f05": (ARCH, ["layered_platform/"]),
    "f06": ("Architecture + implemented: package paths and the AST dependency rule", ["layered_platform/", "tests/architecture/test_import_rules.py"]),
    "f07": ("Architecture + implemented: contracts in layered_platform/contracts.py", ["layered_platform/contracts.py"]),
    "f08": ("Architecture + implemented: context/, memory/, runtime/checkpoints.py", ["layered_platform/context/", "layered_platform/memory/"]),
    "f09": ("Architecture + implemented: tools/gateway.py, policy/", ["layered_platform/tools/gateway.py", "layered_platform/policy/", "config/policies.yaml"]),
    "f10": ("Recorded: one layered run of the published run (E1, seed 7)",
            ["scenarios/E1-layered-s7/raw/*.jsonl", "scenarios/E1-layered-s7/platform/platform.db",
             "scenarios/E1-layered-s7/score.json"]),
    "f11": ("Design: preregistered plan (experiment_plan.yaml)", ["experiments/preregistration/experiment_plan.yaml"]),
    "f12": ("Design: preregistered plan (experiment_plan.yaml)", ["experiments/preregistration/experiment_plan.yaml"]),
    "f13": ("Measured: summary.json of the published run", ["summary.json"]),
    "f14": ("Measured + recorded: E5 scenarios of the published run", ["experiments/E5.json", "scenarios/E5-*/raw/*.jsonl"]),
    "f15": ("Measured: git diffs of frozen patches in isolated worktrees", ["experiments/E2.json", "experiments/E3.json", "experiments/E9.json", "diffs/*.diff"]),
    "f16": ("Measured: deterministic probes against both choke points + adversarial runs", ["experiments/E6_probes.json", "experiments/E6.json"]),
    "f17": ("Reasoned from the experiments named on each rule", ["summary.json"]),
}


def where(path: str, run: str | None) -> str:
    """Resolve a figure's data source: inside the published run if it exists there, else in the POC tree."""
    if run:
        base = POC / "runs" / run
        if list(base.glob(path)) or (base / path).exists():
            return f"layered_architecture_poc/runs/{run}/{path}"
    return f"layered_architecture_poc/{path}"


def main() -> None:
    run = (POC / "runs" / "PUBLISHED").read_text().strip() if (POC / "runs" / "PUBLISHED").exists() else None
    manifest = json.loads((D / "manifest.json").read_text()) if (D / "manifest.json").exists() else {}
    scenes = json.loads((D / "scenes.json").read_text()) if (D / "scenes.json").exists() else {}
    figs = {}
    for fid, (prov, src) in SOURCES.items():
        sk = D / "premium" / "skeletons" / f"{fid}.json"
        if not sk.exists():
            continue
        s = json.loads(sk.read_text())
        measured = prov.startswith(("Measured", "Recorded"))
        figs[fid] = {
            "name": s["name"], "width": s["width"], "height": s["height"],
            "provenance": prov + (f" · run {run}" if measured and run else ""),
            # a source path belongs to the run when it resolves there; otherwise it is a path in the POC tree
            "data_sources": [where(x, run) for x in src],
            "files": {k: f"diagrams/premium/{k}/{fid}.{ext}" for k, ext in (("skeletons", "json"), ("excalidraw", "excalidraw"), ("svg", "svg"), ("png", "png"))},
            "excalidraw": scenes.get(fid, {}),
        }
    manifest.update({"collection": {"name": "AI_BLOGS", "id": "A10UVY9ELvm"}, "run": run, "figures": figs,
                     "icons": {"collection": "Architecture Icons (6xMmyYanRuQ)", "category_scene": "17-anonymous — Generic architecture icons (7FNAR2m6lO4)",
                               "licence": "Lucide 1.45, ISC"}})
    (D / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(len(figs), "figures")


if __name__ == "__main__":
    main()
