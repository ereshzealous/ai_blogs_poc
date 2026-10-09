"""Write diagrams/manifest.json: every F3 figure, its frame name, files, Excalidraw+ location, data sources and provenance.

    python3 tools/diagram_manifest.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "diagrams"
POC = ROOT / "headless_ai_poc"

ARCH = "Architecture: concept figure; no measured values"
SOURCES = {
    "f01": ("Concept + recorded: cover metaphor; footer counts from the published run", ["facts.json"]),
    "f02": (ARCH, []),
    "f03": (ARCH, []),
    "f04": ("Architecture + implemented: the contract names come from hai/contracts.py", ["hai/contracts.py"]),
    "f05": ("Analogy: headless CMS (Storyblok, research/sources.md [1]); no measured values", []),
    "f06": ("Series map: learning-map.yaml (Foundation track); no measured values", []),
    "f07": ("Architecture: F2's six layers and F3's contract; no measured values", ["hai/contracts.py"]),
    "f08": ("Measured: X1, chat-centric baseline", ["X1.json"]),
    "f09": ("Measured: X1, layered chat-first baseline", ["X1.json"]),
    "f10": ("Recorded + implemented: the headless workflow steps of the published run", ["X2.json", "audit.jsonl"]),
    "f11": ("Measured: X2, eight heads during one investigation", ["X2.json"]),
    "f12": ("Derived: X7, arithmetic from config/*.yaml; not measured", ["X7.json"]),
    "f13": ("Recorded: X4, the event execution's identity; scopes from config/principals.yaml", ["X4.json"]),
    "f14": ("Measured: X4, approval attempts; ladder from config/policies.yaml", ["X4.json"]),
    "f15": ("Measured: X5, spans and audit records of the X2 execution", ["X5.json", "traces.jsonl", "audit.jsonl"]),
    "f16": (ARCH, []),
    "f17": (ARCH, []),
    "f18": ("Reasoned from the experiments named on each rule", ["checks.json"]),
    "f19": (ARCH, []),
    "f20": ("Series map: planned notes; no results claimed", []),
    "f21": ("Measured + implemented: X6 crash, approval timeout and token expiry; states from hai/runtime/service.py", ["X6.json"]),
    "f22": ("Measured: X3, duplicate, re-fired and malformed deliveries", ["X3.json"]),
}


def main() -> None:
    run = (POC / "runs" / "PUBLISHED").read_text().strip()
    scenes = json.loads((D / "scenes.json").read_text()) if (D / "scenes.json").exists() else {}
    figs = {}
    for fid, (prov, src) in SOURCES.items():
        sk = D / "premium" / "skeletons" / f"{fid}.json"
        if not sk.exists():
            continue
        s = json.loads(sk.read_text())
        measured = prov.startswith(("Measured", "Recorded", "Derived", "Concept + recorded"))
        figs[fid] = {
            "name": s["name"], "width": s["width"], "height": s["height"],
            "provenance": prov + (f" · run {run}" if measured else ""),
            "data_sources": [f"headless_ai_poc/runs/{run}/{x}" if x.endswith((".json", ".jsonl")) else f"headless_ai_poc/{x}" for x in src],
            "files": {k: f"diagrams/premium/{k}/{fid}.{ext}" for k, ext in (("skeletons", "json"), ("excalidraw", "excalidraw"), ("svg", "svg"), ("png", "png"))},
            "excalidraw": scenes.get(fid, {}),
        }
    manifest = {"collection": {"name": "AI_BLOGS", "id": "A10UVY9ELvm"}, "run": run, "figures": figs,
                "icons": {"collection": "Architecture Icons (6xMmyYanRuQ)", "category_scene": "17-anonymous — Generic architecture icons (7FNAR2m6lO4)",
                          "licence": "Lucide (ISC); 9 icons added from lucide-static 0.545.0"}}
    (D / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(len(figs), "figures")


if __name__ == "__main__":
    main()
