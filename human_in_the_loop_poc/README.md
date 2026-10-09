# T3 · Human-in-the-Loop

*What exactly did the human approve, and is that approval still valid now?*

Production AI Engineering · T3 · Trust & Security · chapter 8 of 15

## Read it

- **The article:** "T3 · Human-in-the-Loop", on Medium
- **Results:** [`results/t3-results.md`](results/t3-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/human_in_the_loop_poc/results/t3-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-03-protocol`, declared in `hitl_poc/evidence/published.json`; deterministic: no model, no network.
- **Evidence integrity:** VERIFIED. 10 of 10 verification sections pass.
- **Findings:** 21 claims: 10 supported, 9 limitation, 1 control, 1 implementation; check findings: 9 EXPECTED FAILURE.
- **Checks:** PASS 70, EXPECTED_FAILURE 9 (`hitl_poc/evidence/runs/2026-10-03-protocol/checks.jsonl`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12, pydantic, pyyaml, pytest) |
| `make test` | pytest: the conformance suite (30 tests) + the implementation tests |
| `make verify` | PROOF VERIFICATION of the published run (pae-proof/v1) |
| `make replay` | the published run replayed in a temp folder, as part of PROOF VERIFICATION (writes only the verification report) |
| `make demo` | the incident end to end |

Author only: `make freeze`, `make proof` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `hitl_poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `vendor/` | the evidence kit the verification imports |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `hitl_poc/evidence/runs/2026-10-03-protocol/facts.json` of run `2026-10-03-protocol`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
