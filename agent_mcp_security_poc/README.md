# T6 · Securing Agents & MCP

*If the model is fooled, can the unsafe action still happen?*

Production AI Engineering · T6 · Trust & Security · chapter 11 of 15

## Read it

- **Medium edition:** [`medium/securing-agents-tools-mcp-medium.md`](medium/securing-agents-tools-mcp-medium.md), and the paste-ready page [`medium/securing-agents-tools-mcp-medium.html`](medium/securing-agents-tools-mcp-medium.html)
- **Technical deep dive:** [`technical/securing-agents-tools-mcp-technical.pdf`](technical/securing-agents-tools-mcp-technical.pdf)
- **Results:** [`results/t6-results.md`](results/t6-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/t6-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-07-recorded`, declared in `redteam_poc/evidence/published.json`; deterministic, scripted worst-case model, no network.
- **Evidence integrity:** VERIFIED. integrity, exact replay and the check recompute, as last recorded by the publication gate.
- **Findings:** 7 claims: 6 SUPPORTED, 1 LIMITATION; check findings: 2 EXPECTED FAILURE, 1 LIMITATION OBSERVED.
- **Checks:** PASS 11, EXPECTED_FAILURE 2, FAIL 1 (`redteam_poc/evidence/runs/2026-10-07-recorded/checks.jsonl`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | create the POC environment (uv, Python 3.12) |
| `make test` | pytest: import contract, unit invariants, end-to-end scenarios |
| `make verify` | PROOF VERIFICATION of the published run (EXACT replay + integrity + checks) |
| `make replay` | the same as make verify: the published run replayed in memory, exact, as part of PROOF VERIFICATION |
| `make demo` | the legitimate task and one contained attack, narrated |
| `make docs` | both editions + results pages as Markdown, standalone HTML and PDF |
| `make qa` | rendered checks of the pages, when the chapter has them; make gate runs the publication gate |

Author only: `make freeze`, `make proof` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `medium/` | the Medium edition: Markdown, and the paste-ready standalone page |
| `qa/` | rendered-page checks and screenshots |
| `redteam_poc/` | the proof of concept and its recorded runs |
| `research/` | sources and reading notes |
| `results/` | the common results page and the detailed evidence pages |
| `technical/` | the technical deep dive (Markdown, HTML, PDF) |
| `tools/` | the chapter's build tools |
| `Makefile` | the standard commands (`make help` lists them) |
| `QA.md` | publication checks |

## Provenance

Every measured number in the editions comes from `redteam_poc/evidence/runs/2026-10-07-recorded/facts.json` of run `2026-10-07-recorded`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
