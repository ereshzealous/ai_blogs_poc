# P1 · The Reference Architecture

*How do all these boundaries fit into one production platform, and does the assembly hold?*

Production AI Engineering · P1 · Capstone · chapter 15 of 15

## Read it

- **The article:** "P1 · The Reference Architecture", on Medium
- **Results:** [`results/p1-results.md`](results/p1-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/production_agentic_ai_platform/results/p1-results.html))
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

## Layout

| Path | What is there |
|---|---|
| `production_agentic_ai_platform/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `docs/` | derived facts and the evidence documents the article cites |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `docs/facts.json` of run `2026-10-04-proof`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
