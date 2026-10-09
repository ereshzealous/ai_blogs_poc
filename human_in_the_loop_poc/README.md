# T3 · Human-in-the-Loop

*What exactly did the human approve, and is that approval still valid now?*

Production AI Engineering · T3 · Trust & Security · chapter 8 of 15

## Read it

- **Medium edition:** [`medium/human-in-the-loop-medium.md`](medium/human-in-the-loop-medium.md), and the paste-ready page [`medium/human-in-the-loop-medium.html`](medium/human-in-the-loop-medium.html)
- **Technical deep dive:** [`technical/human-in-the-loop-technical.pdf`](technical/human-in-the-loop-technical.pdf)
- **Results:** [`results/t3-results.md`](results/t3-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/t3-results.html))
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
| `make docs` | both editions and the three results documents as Markdown, standalone HTML and PDF |
| `make qa` | rendered checks at desktop/tablet/mobile + screenshots -> qa/ |

Author only: `make freeze`, `make proof` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `hitl_poc/` | the proof of concept and its recorded runs |
| `medium/` | the Medium edition: Markdown, and the paste-ready standalone page |
| `qa/` | rendered-page checks and screenshots |
| `research/` | sources and reading notes |
| `results/` | the common results page and the detailed evidence pages |
| `storyboard/` | storyboards for the figures |
| `technical/` | the technical deep dive (Markdown, HTML, PDF) |
| `tools/` | the chapter's build tools |
| `vendor/` | vendored libraries (evidence-kit) |
| `Makefile` | the standard commands (`make help` lists them) |
| `QA.md` | publication checks |

## Provenance

Every measured number in the editions comes from `hitl_poc/evidence/runs/2026-10-03-protocol/facts.json` of run `2026-10-03-protocol`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
