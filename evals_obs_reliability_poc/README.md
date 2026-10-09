# R1+R2 · Evals & Reliability

*When something breaks mid-run, what should the runtime do next, and how do you know it chose right?*

Production AI Engineering · R1+R2 · Reliability · chapter 12 of 15

## Read it

- **The article:** "R1+R2 · Evals & Reliability", on Medium
- **Results:** [`results/r1-r2-results.md`](results/r1-r2-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/evals_obs_reliability_poc/results/r1-r2-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-07-recorded`, declared in `evidence/published.json`; deterministic scenarios plus a recorded real-model slice.
- **Evidence integrity:** VERIFIED. 10 of 10 verification sections pass.
- **Findings:** 15 claims: 11 supported, 2 limitation, 1 control, 1 implementation; check findings: 3 LIMITATION OBSERVED, 1 EXPECTED FAILURE.
- **Checks:** PASS 42, FAIL 3, EXPECTED_FAILURE 1 (`evidence/runs/2026-10-07-recorded/checks.jsonl`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12 via uv; pytest) |
| `make test` | the POC's unit and end-to-end tests (real processes, no model) -> verification/pytest.* |
| `make verify` | PROOF VERIFICATION of the published run -> evidence/verification/verification.{txt,json} |
| `make replay` | every deterministic experiment re-executed in a temp folder and compared with the published run (nothing recorded) |
| `make demo` | the flagship (S09) through the naive and the classified runtime, explained step by step |

Author only: `make replay-live`, `make replay-record`, `make pack` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `recovery_poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `evidence/` | the proof pack of the published run |
| `proof/` | preregistration, freeze and claim definitions |
| `verification/` | the latest verification outputs |
| `runner/` | the experiment runner |
| `tools/` | the scripts `make test` and `make verify` run |
| `vendor/` | the evidence kit the verification imports |
| `docs/` | derived facts and the evidence documents the article cites |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `recovery_poc/runs/2026-10-07-recorded/facts.json` of run `2026-10-07-recorded`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
