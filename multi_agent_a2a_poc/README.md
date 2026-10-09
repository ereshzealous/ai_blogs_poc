# C1 · Multi-Agent & A2A

*When does one agent become several, and when does an agent deserve A2A?*

Production AI Engineering · C1 · Coordination · chapter 13 of 15

## Read it

- **Medium edition:** [`medium/multi-agent-a2a-medium.md`](medium/multi-agent-a2a-medium.md), and the paste-ready page [`medium/multi-agent-a2a-medium.html`](medium/multi-agent-a2a-medium.html)
- **Technical deep dive:** [`technical/multi-agent-a2a-technical.pdf`](technical/multi-agent-a2a-technical.pdf)
- **Results:** [`results/c1-results.md`](results/c1-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/c1-results.html))
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
| `make docs` | both editions and the evidence documents as Markdown, standalone HTML and PDF (figures pending -> placeholders) |
| `make qa` | the Medium edition's checks: what Medium cannot show, relative links, stale wording |

## Layout

| Path | What is there |
|---|---|
| `coordination_poc/` | the proof of concept and its recorded runs |
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `medium/` | the Medium edition: Markdown, and the paste-ready standalone page |
| `research/` | sources and reading notes |
| `results/` | the common results page and the detailed evidence pages |
| `technical/` | the technical deep dive (Markdown, HTML, PDF) |
| `tools/` | the chapter's build tools |
| `vendor/` | vendored libraries (evidence-kit) |
| `verification/` | the latest verification outputs |
| `Makefile` | the standard commands (`make help` lists them) |
| `QA.md` | publication checks |

## Provenance

Every measured number in the editions comes from `coordination_poc/runs/2026-10-08-blind/facts.json` of run `2026-10-08-blind`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
