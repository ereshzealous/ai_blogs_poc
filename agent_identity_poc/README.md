# T1 · Agent Identity

*When an agent acts, whose authority is actually being used?*

Production AI Engineering · T1 · Trust & Security · chapter 6 of 15

## Read it

- **The article:** "T1 · Agent Identity", on Medium
- **Results:** [`results/t1-results.md`](results/t1-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/agent_identity_poc/results/t1-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-03-recorded`, declared in `agent_identity_poc/runs/PUBLISHED`; deterministic run.
- **Evidence integrity:** not recorded as a separate verdict; `make verify` checks it.
- **Findings:** no separate findings verdict: all 41 checks passed.
- **Checks:** PASS 41 (`agent_identity_poc/runs/2026-10-03-recorded/checks.json`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12, pydantic, pyyaml, pytest) |
| `make test` | POC tests (no model, no network) |
| `make verify` | rerun the experiments into a fresh copy of the POC and compare with the published run, byte for byte |
| `make replay` | the same as make verify: the experiments rerun in a fresh copy of the POC and compared byte for byte |
| `make demo` | the 14:09 rollback, with every identity in the chain printed |

Author only: `make run` rewrites published evidence, so it refuses unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `agent_identity_poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `tools/` | the scripts `make test` and `make verify` run |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `agent_identity_poc/runs/2026-10-03-recorded/facts.json` of run `2026-10-03-recorded`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
