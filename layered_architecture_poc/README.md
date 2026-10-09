# F2 · Layered Agent Platform

*Which production responsibility belongs where, and what survives failure?*

Production AI Engineering · F2 · Foundation · chapter 2 of 15

## Read it

- **Medium edition:** [`docs/publish/medium/layered-production-ai-architecture-medium.md`](docs/publish/medium/layered-production-ai-architecture-medium.md), and the paste-ready page [`docs/publish/medium/layered-production-ai-architecture-medium.html`](docs/publish/medium/layered-production-ai-architecture-medium.html)
- **Technical deep dive:** [`docs/publish/technical/layered-production-ai-architecture-technical.pdf`](docs/publish/technical/layered-production-ai-architecture-technical.pdf)
- **Results:** [`results/f2-results.md`](results/f2-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/f2-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-09-28-recorded`, declared in `layered_architecture_poc/runs/PUBLISHED`; recorded: live local models, real MCP servers, real SIGKILLs.
- **Evidence integrity:** VERIFIED. 36 of 36 checks pass, 12 recomputed from raw evidence.
- **Findings:** 17 claims: 8 SUPPORTED, 4 QUALIFIED, 3 UNSUPPORTED, 2 CONTRADICTED; scenario outcomes: 0 ERROR, 8 FAILURE, 1 NOT_EXPOSED, 23 SUCCESS.
- **Checks:** PASS 36 (`layered_architecture_poc/runs/2026-09-28-recorded/verification.json`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | install the POC environment (Python 3.12, mcp 2.2.0); no model needed (make models checks Ollama) |
| `make test` | every test except the live-model ones (no model needed) |
| `make verify` | the published run's evidence verified in a throwaway copy of the POC: 36 checks, 12 recomputed from raw evidence |
| `make replay` | the published run replayed from its model tape in a throwaway copy of the POC (no model, nothing written to the run) |
| `make demo` | no single-scenario demo here: make replay replays the published run from its model tape |
| `make docs` | the three publications as Markdown, standalone HTML and PDF, plus the claim/evidence matrix |
| `make qa` | publication checks: no hand-typed number in a publication, and the figures agree with the run |

Author only: `make verify-evidence`, `make outcomes`, `make standardize`, `make verify-all` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `layered_architecture_poc/` | the proof of concept and its recorded runs |
| `results/` | the common results page and the detailed evidence pages |
| `tools/` | the chapter's build tools |
| `vendor/` | vendored libraries (evidence-kit) |
| `verification/` | the latest verification outputs |
| `Makefile` | the standard commands (`make help` lists them) |
| `QA.md` | publication checks |

## Provenance

Every measured number in the editions comes from `layered_architecture_poc/runs/2026-09-28-recorded/facts.json` of run `2026-09-28-recorded`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
