# S1 · Memory, Context & State

*What should an agent remember, what should expire, and what is authoritative?*

Production AI Engineering · S1 · State & Knowledge · chapter 4 of 15

## Read it

- **The article:** "S1 · Memory, Context & State", on Medium
- **Results:** [`results/s1-results.md`](results/s1-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/memory_context_state_poc/results/s1-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-09-18-recorded`, declared in `tools/fill_article.py (ARTICLE_RUN)`; recorded with a live local model.
- **Evidence integrity:** not recorded as a separate verdict; `make verify` checks it.
- **Findings:** 10 of 10 invariants hold.
- **Checks:** PASS 28 (`memory-context-state-poc/runs/2026-09-18-recorded/summary.json`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python via uv, from uv.lock) |
| `make test` | the POC's tests and its layer contracts (no model) |
| `make verify` | frozen inputs unchanged (s1 check), then the tests; reads the published run, never writes it |
| `make replay` | the published run replayed from its tape in a throwaway copy of the POC (the published run is not written) |
| `make demo` | no single-scenario demo here: make replay replays the published run from its tape |

Author only: `make fill` rewrites published evidence, so it refuses unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `memory-context-state-poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `memory-context-state-poc/runs/2026-09-18-recorded/summary.json` of run `2026-09-18-recorded`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
