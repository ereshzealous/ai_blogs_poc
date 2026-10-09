# S1 · Memory, Context & State

*What should an agent remember, what should expire, and what is authoritative?*

Production AI Engineering · S1 · State & Knowledge · chapter 4 of 15

## Read it

- **Medium edition:** [`article/memory-context-state.md`](article/memory-context-state.md), and the paste-ready page [`article/memory-context-state.html`](article/memory-context-state.html)
- **Technical deep dive:** [`memory-context-state-poc/docs/S1-technical-reference.pdf`](memory-context-state-poc/docs/S1-technical-reference.pdf)
- **Results:** [`results/s1-results.md`](results/s1-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/s1-results.html))
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
| `make docs` | the technical edition as standalone HTML and PDF, then the uniform series pages |
| `make qa` | the Medium edition's checks: what Medium cannot show, relative links, stale wording |

Author only: `make fill` rewrites published evidence, so it refuses unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `article/` | both editions (this chapter keeps them together) |
| `assets/` | images used by the editions |
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `memory-context-state-poc/` | the proof of concept and its recorded runs |
| `results/` | the common results page and the detailed evidence pages |
| `tools/` | the chapter's build tools |
| `Makefile` | the standard commands (`make help` lists them) |
| `QA.md` | publication checks |

## Provenance

Every measured number in the editions comes from `memory-context-state-poc/runs/2026-09-18-recorded/summary.json` of run `2026-09-18-recorded`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files.
