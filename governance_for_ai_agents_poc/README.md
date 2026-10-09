# T5 · Observability & Governance

*Can you prove what an agent did, and on whose authority?*

Production AI Engineering · T5 · Trust & Security · chapter 10 of 15

## Read it

- **The article:** "T5 · Observability & Governance", on Medium
- **Results:** [`results/t5-results.md`](results/t5-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/governance_for_ai_agents_poc/results/t5-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-09-30-recorded`, declared in `observability_governance_poc/runs/PUBLISHED`; recorded with a live local model.
- **Evidence integrity:** VERIFIED. 15 of 15 scenario evidence chains intact; replay all identical: True.
- **Findings:** 7 of 7 preregistered predictions held; 68 of 68 expectations held.
- **Checks:** PASS 7 (`observability_governance_poc/runs/2026-09-30-recorded/checks.json`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12, OpenTelemetry SDK, pytest) |
| `make test` | POC tests with the model unreachable (unit, real processes, end-to-end scenarios) -> results/tests.json |
| `make verify` | recompute every evidence chain of the published run and check it against the witness anchors |
| `make replay` | every published scenario rerun from the tapes in a throwaway copy of the POC (no model) and compared with the published run |
| `make demo` | the flagship lost-response scenario from the published tape, then its evidence, event by event |

Author only: `make replay-record` rewrites published evidence, so it refuses unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `observability_governance_poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `verification/` | the latest verification outputs |
| `tools/` | the scripts `make test` and `make verify` run |
| `docs/` | derived facts and the evidence documents the article cites |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `observability_governance_poc/runs/2026-09-30-recorded/facts.json` of run `2026-09-30-recorded`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
