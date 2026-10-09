# O1+O2 · Operating at Scale

*What changes at production volume, and how do changes ship safely?*

Production AI Engineering · O1+O2 · Scale & Operations · chapter 14 of 15

## Read it

- **The article:** "O1+O2 · Operating at Scale", on Medium
- **Results:** [`results/o1-o2-results.md`](results/o1-o2-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/operating_ai_agents_poc/results/o1-o2-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-08-recorded`, declared in `evidence/published.json`; deterministic discrete-event simulation, no model.
- **Evidence integrity:** VERIFIED. 11 of 11 verification sections pass.
- **Findings:** 14 claims: 10 supported, 3 limitation, 1 control; check findings: 1 LIMITATION OBSERVED, 1 EXPECTED FAILURE.
- **Checks:** PASS 63, FAIL 1, EXPECTED_FAILURE 1 (`evidence/runs/2026-10-08-recorded/checks.jsonl`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12 via uv; pytest) |
| `make test` | the POC's tests (10 scenario tests + unit tests) -> verification/pytest.* |
| `make verify` | PROOF VERIFICATION of the published run -> evidence/verification/verification.{txt,json} |
| `make replay` | every scenario rerun from source in a temp folder and compared with the published run (nothing recorded) |
| `make demo` | the surge with and without admission, then the canary, narrated |

Author only: `make replay-record`, `make pack` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `ops_poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `evidence/` | the proof pack of the published run |
| `proof/` | preregistration, freeze and claim definitions |
| `verification/` | the latest verification outputs |
| `tools/` | the scripts `make test` and `make verify` run |
| `vendor/` | the evidence kit the verification imports |
| `docs/` | derived facts and the evidence documents the article cites |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `ops_poc/runs/2026-10-08-recorded/facts.json` of run `2026-10-08-recorded`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
