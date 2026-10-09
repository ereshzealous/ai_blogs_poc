# O1+O2 · Operating at Scale

*What changes at production volume, and how do changes ship safely?*

Production AI Engineering · O1+O2 · Scale & Operations · chapter 14 of 15

## Read it

- **Medium edition:** [`medium/operating-ai-agents-medium.md`](medium/operating-ai-agents-medium.md), and the paste-ready page [`medium/operating-ai-agents-medium.html`](medium/operating-ai-agents-medium.html)
- **Technical deep dive:** [`technical/operating-ai-agents-technical.pdf`](technical/operating-ai-agents-technical.pdf)
- **Results:** [`results/o1-o2-results.md`](results/o1-o2-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/o1-o2-results.html))
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
| `make docs` | both editions and the evidence documents as Markdown, standalone HTML and PDF |
| `make qa` | rendered checks of every page (desktop/tablet/mobile) -> qa/ |

Author only: `make replay-record`, `make pack` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `evidence/` | the proof pack of the published run |
| `medium/` | the Medium edition: Markdown, and the paste-ready standalone page |
| `ops_poc/` | the proof of concept and its recorded runs |
| `proof/` | preregistration, freeze and claim definitions |
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

Every measured number in the editions comes from `ops_poc/runs/2026-10-08-recorded/facts.json` of run `2026-10-08-recorded`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
