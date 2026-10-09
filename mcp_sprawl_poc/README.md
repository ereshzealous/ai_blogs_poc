# F1 · MCP Tool Sprawl

*Which capability should the agent see, and may this exact call execute?*

Production AI Engineering · F1 · Foundation · chapter 1 of 15

## Read it

- **Medium edition:** [`medium/static/mcp-tool-sprawl-medium-static.md`](medium/static/mcp-tool-sprawl-medium-static.md), and the paste-ready page [`medium/mcp-tool-sprawl-medium.html`](medium/mcp-tool-sprawl-medium.html)
- **Technical deep dive:** [`technical/mcp-tool-sprawl-technical.pdf`](technical/mcp-tool-sprawl-technical.pdf)
- **Results:** [`results/f1-results.md`](results/f1-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/f1-results.html))
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
| `make docs` | both editions (Markdown, HTML, PDF) and the static Medium edition, then the uniform series pages |
| `make qa` | publication scan: no local path, host name or address in the editions, results and README |

Author only: `make negative-control` rewrites published evidence, so it refuses unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `evidence/` | the proof pack of the published run |
| `experiment/` | experiment definitions and analysis |
| `medium/` | the Medium edition: Markdown, and the paste-ready standalone page |
| `poc/` | the proof of concept and its recorded runs |
| `proof/` | preregistration, freeze and claim definitions |
| `research/` | sources and reading notes |
| `results/` | the common results page and the detailed evidence pages |
| `runner/` | the experiment runner |
| `technical/` | the technical deep dive (Markdown, HTML, PDF) |
| `tools/` | the chapter's build tools |
| `vendor/` | vendored libraries (evidence-kit) |
| `Makefile` | the standard commands (`make help` lists them) |
| `QA.md` | publication checks |

## Provenance

Every measured number in the editions comes from `evidence/evidence.json (facts)` of run `blind-rerun-2026-10-01`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
