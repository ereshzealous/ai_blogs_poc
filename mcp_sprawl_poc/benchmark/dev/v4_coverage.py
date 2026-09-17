"""Development check: how often each control-plane profile shows the right tool (main set and held-out set 1).

    python -m benchmark.dev.v4_coverage benchmark/runs/_dev-v4b-coverage/rewrites.json

The model's rewrites are read from (and missing ones added to) the JSON file, so a rerun without Ollama chat calls
reproduces the published development numbers. Held-out set 2 is never read here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agent.llm import make_llm
from benchmark.evaluator.metrics import HOLDOUT_FILE, load_cases
from control_plane.discovery.pipeline import DiscoveryService
from control_plane.discovery.rewrite import QueryRewriter, Rewrite
from control_plane.discovery.semantic import OllamaEmbedder
from control_plane.paths import CATALOG_DIR
from control_plane.registry.registry import CapabilityRegistry


def main() -> None:
    cache = Path(sys.argv[1])
    cases = load_cases() + load_cases(HOLDOUT_FILE)
    registry, embedder = CapabilityRegistry.load(), OllamaEmbedder()
    rewriter = QueryRewriter(make_llm("ollama", None, num_ctx=32768))
    if cache.exists():
        for request, saved in json.loads(cache.read_text()).items():
            rewriter._cache[request] = Rewrite(**saved["rewrite"]) if saved["rewrite"] else None
            rewriter._usage[request] = saved["usage"]
    for case in cases:
        rewriter.rewrite(case.prompt)
    cache.write_text(json.dumps({r: {"rewrite": rw.to_dict() if rw else None, "usage": rewriter._usage[r]}
                                 for r, rw in rewriter._cache.items()}, indent=1, sort_keys=True) + "\n")
    agree = sum((rewriter.rewrite(c.prompt).operation == "write") == registry.get(c.golden_tool).side_effect
                for c in cases if rewriter.rewrite(c.prompt))
    print(f"model read/write judgement matches the golden tool: {agree}/{len(cases)}")
    groups = {split: [c for c in cases if c.split == split] for split in ("dev", "test", "holdout")}
    for catalog in ("catalog_50", "catalog_100", "catalog_250", "catalog_500"):
        manifest = json.loads((CATALOG_DIR / f"{catalog}.json").read_text())
        tools = {f"{t['server']}.{t['name']}": (t["server"], t["name"], t["description"], t["input_schema"])
                 for t in manifest["tools"]}
        parts = []
        for profile in ("v1", "v3", "v4"):
            service = DiscoveryService(tools, registry, embedder, profile=profile, rewriter=rewriter if profile == "v4" else None)
            for split, subset in groups.items():
                shown = {c.id: service.control_plane(c.prompt, k=5).tool_ids for c in subset if c.golden_tool in tools}
                hit = sum(bool(c.correct_tools & set(shown[c.id])) for c in subset if c.id in shown)
                mean = sum(map(len, shown.values())) / len(shown)
                parts.append(f"{profile}/{split} {hit}/{len(shown)} ({mean:.1f} tools)")
        print(catalog, " | ".join(parts))


if __name__ == "__main__":
    main()
