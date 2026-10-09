# T1 · Agent Identity

*When an agent acts, whose authority is actually being used?*

Production AI Engineering · T1 · Trust & Security · chapter 6 of 15

## Read it

- **Medium edition:** [`medium/agent-identity-medium.md`](medium/agent-identity-medium.md), and the paste-ready page [`medium/agent-identity-medium.html`](medium/agent-identity-medium.html)
- **Technical deep dive:** [`technical/agent-identity-technical.pdf`](technical/agent-identity-technical.pdf)
- **Results:** [`results/t1-results.md`](results/t1-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/t1-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-03-recorded`, declared in `agent_identity_poc/runs/PUBLISHED`; deterministic run.
- **Evidence integrity:** not recorded as a separate verdict; `make verify` checks it.
- **Findings:** no separate findings verdict: all 41 checks passed.
- **Checks:** PASS 41 (`agent_identity_poc/runs/2026-10-03-recorded/checks.json`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12, pydantic, pyyaml, pytest) |
| `make test` | POC tests (no model, no network) |
| `make verify` | rerun the experiments into a fresh copy of the POC and compare with the published run, byte for byte |
| `make replay` | the same as make verify: the experiments rerun in a fresh copy of the POC and compared byte for byte |
| `make demo` | the 14:09 rollback, with every identity in the chain printed |
| `make docs` | both editions and the three evidence documents (results/) as Markdown, standalone HTML and PDF |
| `make qa` | rendered checks at desktop/tablet/mobile + screenshots -> qa/ |

Author only: `make run` rewrites published evidence, so it refuses unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `agent_identity_poc/` | the proof of concept and its recorded runs |
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `medium/` | the Medium edition: Markdown, and the paste-ready standalone page |
| `qa/` | rendered-page checks and screenshots |
| `research/` | sources and reading notes |
| `results/` | the common results page and the detailed evidence pages |
| `technical/` | the technical deep dive (Markdown, HTML, PDF) |
| `tools/` | the chapter's build tools |
| `vendor/` | vendored libraries (evidence-kit) |
| `Makefile` | the standard commands (`make help` lists them) |
| `QA.md` | publication checks |

## Provenance

Every measured number in the editions comes from `agent_identity_poc/runs/2026-10-03-recorded/facts.json` of run `2026-10-03-recorded`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
