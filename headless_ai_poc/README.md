# F3 · Headless AI

*How should many consumers use the same AI intelligence safely?*

Production AI Engineering · F3 · Foundation · chapter 3 of 15

## Read it

- **Medium edition:** [`medium/headless-ai-medium.md`](medium/headless-ai-medium.md), and the paste-ready page [`medium/headless-ai-medium.html`](medium/headless-ai-medium.html)
- **Technical deep dive:** [`technical/headless-ai-technical.pdf`](technical/headless-ai-technical.pdf)
- **Results:** [`results/f3-results.md`](results/f3-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/f3-results.html))
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
| `make docs` | both editions as Markdown, standalone HTML and PDF |
| `make qa` | rendered checks at desktop/tablet/mobile + screenshots -> qa/ |

Author only: `make run` rewrites published evidence, so it refuses unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `headless_ai_poc/` | the proof of concept and its recorded runs |
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

Every measured number in the editions comes from `headless_ai_poc/runs/2026-10-05-recorded/facts.json` of run `2026-10-05-recorded`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
