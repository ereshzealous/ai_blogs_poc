# F3 · Headless AI

*How should many consumers use the same AI intelligence safely?*

Production AI Engineering · F3 · Foundation · chapter 3 of 15

## Read it

- **The article:** "F3 · Headless AI", on Medium
- **Results:** [`results/f3-results.md`](results/f3-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/headless_ai_poc/results/f3-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-05-recorded`, declared in `headless_ai_poc/runs/PUBLISHED`; deterministic reasoner over simulated systems.
- **Evidence integrity:** VERIFIED. 6 of 6 sections pass (manifest, integrity, checks, claims, replay, scan).
- **Findings:** no separate findings verdict: all 30 experiment checks passed.
- **Checks:** PASS 30 (`headless_ai_poc/runs/2026-10-05-recorded/checks.json`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12, pydantic, pyyaml, pytest) |
| `make test` | POC tests (no model, no network) |
| `make verify` | PROOF VERIFICATION of the published run, read-only (hai verify --check; no model) |
| `make replay` | the byte-for-byte replay of the published run in a temp folder (part of hai verify --check; read-only) |
| `make demo` | one monitoring event, end to end |

Author only: `make run` rewrites published evidence, so it refuses unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `headless_ai_poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `headless_ai_poc/runs/2026-10-05-recorded/facts.json` of run `2026-10-05-recorded`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
