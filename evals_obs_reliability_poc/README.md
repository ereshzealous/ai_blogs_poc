# R1+R2 · Evals & Reliability

*When something breaks mid-run, what should the runtime do next, and how do you know it chose right?*

Production AI Engineering · R1+R2 · Reliability · chapter 12 of 15

## Read it

- **Medium edition:** [`medium/evals-reliability-medium.md`](medium/evals-reliability-medium.md), and the paste-ready page [`medium/evals-reliability-medium.html`](medium/evals-reliability-medium.html)
- **Technical deep dive:** [`technical/evals-reliability-technical.pdf`](technical/evals-reliability-technical.pdf)
- **Results:** [`results/r1-r2-results.md`](results/r1-r2-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/r1-r2-results.html))
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
| `make docs` | both editions and the three evidence documents as Markdown, standalone HTML and PDF |
| `make qa` | rendered checks of every page (desktop/tablet/mobile) and the Lab Console -> qa/ |

Author only: `make replay-live`, `make replay-record`, `make pack` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `evidence/` | the proof pack of the published run |
| `medium/` | the Medium edition: Markdown, and the paste-ready standalone page |
| `proof/` | preregistration, freeze and claim definitions |
| `qa/` | rendered-page checks and screenshots |
| `recovery_poc/` | the proof of concept and its recorded runs |
| `research/` | sources and reading notes |
| `results/` | the common results page and the detailed evidence pages |
| `runner/` | the experiment runner |
| `technical/` | the technical deep dive (Markdown, HTML, PDF) |
| `tools/` | the chapter's build tools |
| `vendor/` | vendored libraries (evidence-kit) |
| `verification/` | the latest verification outputs |
| `Makefile` | the standard commands (`make help` lists them) |
| `QA.md` | publication checks |

## Provenance

Every measured number in the editions comes from `recovery_poc/runs/2026-10-07-recorded/facts.json` of run `2026-10-07-recorded`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
