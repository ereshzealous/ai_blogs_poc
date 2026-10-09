# C1 · Multi-Agent & A2A

*When does one agent become several, and when does an agent deserve A2A?*

Production AI Engineering · C1 · Coordination · chapter 13 of 15

## Read it

- **The article:** "C1 · Multi-Agent & A2A", on Medium
- **Results:** [`results/c1-results.md`](results/c1-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/multi_agent_a2a_poc/results/c1-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-08-blind`, declared in `coordination_poc/runs/PUBLISHED`; live local model, recorded tape.
- **Evidence integrity:** VERIFIED. REPLAY IDENTICAL: 72 of 72 workflows; FROZEN CHECK OK (51 files, frozen at 2026-10-08T01:38:01+0530; 49 unchanged, 2 changed after the run and recorded in DEVIATIONS.md).
- **Findings:** 9 preregistered hypotheses: 7 SUPPORTED, 2 NOT SUPPORTED.
- **Checks:** SUPPORTED 7, NOT SUPPORTED 2 (`coordination_poc/runs/2026-10-08-blind/facts.json (H1–H9)`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12 via uv; pytest) |
| `make test` | the POC's unit and end-to-end tests (real A2A and MCP processes, no model) -> verification/pytest.* |
| `make verify` | frozen inputs unchanged, replay identical and the tests, in a throwaway copy of the POC (the published run is not written) -> verification/ |
| `make replay` | the same as make verify: the published run's replay check runs in a throwaway copy |
| `make demo` | one benchmark case (B1) through architecture C with a scripted model, in a throwaway copy of the POC |

## Layout

| Path | What is there |
|---|---|
| `coordination_poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `verification/` | the latest verification outputs |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `coordination_poc/runs/2026-10-08-blind/facts.json` of run `2026-10-08-blind`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
