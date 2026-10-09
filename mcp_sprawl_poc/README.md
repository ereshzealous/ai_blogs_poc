# F1 · MCP Tool Sprawl

*Which capability should the agent see, and may this exact call execute?*

Production AI Engineering · F1 · Foundation · chapter 1 of 15

## Read it

- **The article:** "F1 · MCP Tool Sprawl", on Medium
- **Results:** [`results/f1-results.md`](results/f1-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/mcp_sprawl_poc/results/f1-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `blind-rerun-2026-10-01`, declared in `evidence/published.json`; live local model, recorded.
- **Evidence integrity:** VERIFIED. 10 of 10 verification sections pass.
- **Findings:** 24 claims: 12 supported, 3 implementation, 3 not_established, 3 limitation, 2 contradicted, 1 control; check findings: 2 NOT SUPPORTED, 1 NOT ESTABLISHED, 1 NOT OBSERVED, 1 LIMITATION OBSERVED, 1 EXPECTED FAILURE.
- **Checks:** PASS 58, FAIL 5, EXPECTED_FAILURE 1 (`evidence/runs/blind-rerun-2026-10-01/checks.jsonl`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the environment (Python and the pinned dependencies, uv) |
| `make test` | the deterministic unit tests: real MCP server processes, no model |
| `make verify` | PROOF VERIFICATION of the published run: reads the shipped evidence, no model (seconds) |
| `make replay` | replay recorded rows through the real stack without the model, and classify them against the run |
| `make demo` | no single-scenario demo here: make replay replays recorded rows through the real stack |

Author only: `make negative-control` rewrites published evidence, so it refuses unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `evidence/` | the proof pack of the published run |
| `proof/` | preregistration, freeze and claim definitions |
| `experiment/` | experiment definitions, recorded runs and analysis |
| `runner/` | the experiment runner |
| `docker/` | the container the runner can use |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `evidence/evidence.json (facts)` of run `blind-rerun-2026-10-01`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
