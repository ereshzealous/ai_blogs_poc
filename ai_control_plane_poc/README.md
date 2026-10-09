# T4 · AI Control Plane

*How do you change what many agents may do without editing or redeploying any of them?*

Production AI Engineering · T4 · Trust & Security · chapter 9 of 15

## Read it

- **Medium edition:** [`medium/ai-control-plane-medium.md`](medium/ai-control-plane-medium.md), and the paste-ready page [`medium/ai-control-plane-medium.html`](medium/ai-control-plane-medium.html)
- **Technical deep dive:** [`technical/ai-control-plane-technical.pdf`](technical/ai-control-plane-technical.pdf)
- **Results:** [`results/t4-results.md`](results/t4-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/t4-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-03-recorded`, declared in `control_plane_poc/runs/PUBLISHED`; deterministic: agents follow fixed plans, no model.
- **Evidence integrity:** VERIFIED. 10 of 10 verification sections pass.
- **Findings:** 21 claims: 13 supported, 4 limitation, 2 contradicted, 1 control, 1 implementation; check findings: 4 EXPECTED FAILURE, 2 LIMITATION OBSERVED.
- **Checks:** PASS 73, EXPECTED_FAILURE 4, FAIL 2 (`evidence/runs/2026-10-03-recorded/checks.jsonl`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12, pyyaml, pytest, ruff) |
| `make test` | POC tests: architecture (agents hold no governance), decisions, every proof (no model, no network) |
| `make verify` | rerun every proof into a fresh copy of the POC and compare with the published run (pids masked, nothing else) |
| `make replay` | the same as make verify: every proof rerun in a fresh copy of the POC and compared |
| `make demo` | P2 only: one central change, same agent code, same runtime process, different behaviour |
| `make docs` | both editions and the three evidence documents (results/) as Markdown, standalone HTML and PDF |
| `make qa` | rendered checks at desktop/tablet/mobile (editions, evidence documents, Lab Console) + screenshots -> qa/ |

Author only: `make run`, `make pack` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `control_plane_poc/` | the proof of concept and its recorded runs |
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `evidence/` | the proof pack of the published run |
| `medium/` | the Medium edition: Markdown, and the paste-ready standalone page |
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

Every measured number in the editions comes from `control_plane_poc/runs/2026-10-03-recorded/facts.json` of run `2026-10-03-recorded`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
