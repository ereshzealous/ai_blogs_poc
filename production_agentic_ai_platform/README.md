# P1 · The Reference Architecture

*How do all these boundaries fit into one production platform, and does the assembly hold?*

Production AI Engineering · P1 · Capstone · chapter 15 of 15

## Read it

- **Medium edition:** [`medium/production-agentic-ai-platform-medium.md`](medium/production-agentic-ai-platform-medium.md), and the paste-ready page [`medium/production-agentic-ai-platform-medium.html`](medium/production-agentic-ai-platform-medium.html)
- **Technical deep dive:** [`technical/production-agentic-ai-platform-final-reference-architecture.pdf`](technical/production-agentic-ai-platform-final-reference-architecture.pdf)
- **Results:** [`results/p1-results.md`](results/p1-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/p1-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-04-proof`, declared in `production_agentic_ai_platform/evidence/published.json`; proof run: real processes, simulated systems, recorded model calls.
- **Evidence integrity:** VERIFIED. 14 of 14 verification sections pass.
- **Findings:** 19 claims: 13 supported, 4 limitation, 1 control, 1 implementation; check findings: 9 EXPECTED FAILURE.
- **Checks:** PASS 131, EXPECTED_FAILURE 9 (`production_agentic_ai_platform/evidence/runs/2026-10-04-proof/checks.jsonl`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12, mcp 2.2.0, OpenTelemetry SDK, pyyaml, pytest) |
| `make test` | the unit tests (implementation tests, not proof checks) |
| `make verify` | PROOF VERIFICATION of the published run, the README, the Lab and both articles -> POC evidence/verification/ |
| `make replay` | replay the published run into scratch (evidence/local/) and classify it against the recorded run |
| `make demo` | no single-scenario demo here: make replay replays the published run into scratch |
| `make docs` | both editions as Markdown, standalone HTML and PDF, and the Medium image pack |
| `make qa` | rendered checks at desktop/tablet/mobile + screenshots -> qa/ |

## Layout

| Path | What is there |
|---|---|
| `assets/` | images used by the editions |
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `medium/` | the Medium edition: Markdown, and the paste-ready standalone page |
| `production_agentic_ai_platform/` | the proof of concept and its recorded runs |
| `qa/` | rendered-page checks and screenshots |
| `research/` | sources and reading notes |
| `results/` | the common results page and the detailed evidence pages |
| `technical/` | the technical deep dive (Markdown, HTML, PDF) |
| `tools/` | the chapter's build tools |
| `vendor/` | vendored libraries (evidence-kit) |
| `Makefile` | the standard commands (`make help` lists them) |
| `QA.md` | publication checks |

## Provenance

Every measured number in the editions comes from `docs/facts.json` of run `2026-10-04-proof`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
