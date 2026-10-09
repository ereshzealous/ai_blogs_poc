# T2 · Authorization & Policy

*For every tool call: may this agent do this, on this resource, in this context, on whose authority?*

Production AI Engineering · T2 · Trust & Security · chapter 7 of 15

## Read it

- **The article:** "T2 · Authorization & Policy", on Medium
- **Results:** [`results/t2-results.md`](results/t2-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/auth_and_policy_poc/results/t2-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-09-29-recorded`, declared in `authz_poc/authz/run.py (RUN_ID)`; deterministic, simulated systems of record.
- **Evidence integrity:** VERIFIED. replay PASS, audit chain PASS, deterministic True.
- **Findings:** 14 of 14 invariants hold.
- **Checks:** PASS 14 (`authz_poc/runs/2026-09-29-recorded/invariants.json`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | nothing to install: authz_poc uses the Python standard library (the docs build uses uv) |
| `make test` | the four test layers, L1 to L4 (L4 replays the run into a temp folder) |
| `make verify` | PROOF VERIFICATION: the deterministic run re-executed in a throwaway copy, byte for byte against the published run |
| `make replay` | the deterministic run re-executed in a throwaway copy of the POC and compared byte for byte with the published run |
| `make demo` | no single-scenario demo here: make replay re-executes the whole recorded run |

Author only: `make run`, `make record-tests` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `authz_poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `authz_poc/runs/2026-09-29-recorded/facts.json` of run `2026-09-29-recorded`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
