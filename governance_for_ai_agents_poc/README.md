# T5 · Observability & Governance

*Can you prove what an agent did, and on whose authority?*

Production AI Engineering · T5 · Trust & Security · chapter 10 of 15

## Read it

- **Medium edition:** [`medium/observability-governance-medium.md`](medium/observability-governance-medium.md), and the paste-ready page [`medium/observability-governance-medium.html`](medium/observability-governance-medium.html)
- **Technical deep dive:** [`technical/observability-governance-technical.pdf`](technical/observability-governance-technical.pdf)
- **Results:** [`results/t5-results.md`](results/t5-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/t5-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-09-30-recorded`, declared in `observability_governance_poc/runs/PUBLISHED`; recorded with a live local model.
- **Evidence integrity:** VERIFIED. 15 of 15 scenario evidence chains intact; replay all identical: True.
- **Findings:** 7 of 7 preregistered predictions held; 68 of 68 expectations held.
- **Checks:** PASS 7 (`observability_governance_poc/runs/2026-09-30-recorded/checks.json`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12, OpenTelemetry SDK, pytest) |
| `make test` | POC tests with the model unreachable (unit, real processes, end-to-end scenarios) -> results/tests.json |
| `make verify` | recompute every evidence chain of the published run and check it against the witness anchors |
| `make replay` | every published scenario rerun from the tapes in a throwaway copy of the POC (no model) and compared with the published run |
| `make demo` | the flagship lost-response scenario from the published tape, then its evidence, event by event |
| `make docs` | both editions and the three evidence documents (run report, evidence check, real vs simulated) as Markdown, standalone HTML and PDF |
| `make qa` | rendered checks at desktop/tablet/mobile + screenshots -> qa/ |

Author only: `make replay-record` rewrites published evidence, so it refuses unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `medium/` | the Medium edition: Markdown, and the paste-ready standalone page |
| `observability_governance_poc/` | the proof of concept and its recorded runs |
| `qa/` | rendered-page checks and screenshots |
| `research/` | sources and reading notes |
| `results/` | the common results page and the detailed evidence pages |
| `technical/` | the technical deep dive (Markdown, HTML, PDF) |
| `tools/` | the chapter's build tools |
| `vendor/` | vendored libraries (evidence-kit) |
| `verification/` | the latest verification outputs |
| `Makefile` | the standard commands (`make help` lists them) |
| `QA.md` | publication checks |

## Provenance

Every measured number in the editions comes from `observability_governance_poc/runs/2026-09-30-recorded/facts.json` of run `2026-09-30-recorded`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
