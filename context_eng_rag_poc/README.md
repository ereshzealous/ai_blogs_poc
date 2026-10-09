# S2 · Enterprise Knowledge & RAG

*How does an agent retrieve valid enterprise evidence without dumping the company into the prompt?*

Production AI Engineering · S2 · State & Knowledge · chapter 5 of 15

## Read it

- **Medium edition:** [`medium/enterprise-knowledge-rag-medium.md`](medium/enterprise-knowledge-rag-medium.md), and the paste-ready page [`medium/enterprise-knowledge-rag-medium.html`](medium/enterprise-knowledge-rag-medium.html)
- **Technical deep dive:** [`technical/enterprise-knowledge-rag-technical.pdf`](technical/enterprise-knowledge-rag-technical.pdf)
- **Results:** [`results/s2-results.md`](results/s2-results.md), every number the Medium edition uses with its source file, the checks and the two verdicts ([HTML](results/s2-results.html))
- **Series:** [Start Here](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), the map of all 15 chapters

## What the run showed

- **Published run:** `2026-10-08-heldout`, declared in `enterprise_knowledge_rag_poc/runs/PUBLISHED`; live local model on the held-out split.
- **Evidence integrity:** VERIFIED. frozen inputs: FROZEN CHECK OK (41 of 41 files unchanged); replay: REPLAY IDENTICAL.
- **Findings:** 17 preregistered hypotheses: 13 SUPPORTED, 4 NOT SUPPORTED; the evidence check's 1 FAIL line(s) report a finding (governed-arm invariants I4, I6 do not hold), not an integrity failure.
- **Checks:** PASS 12, FAIL 1 (`verification/evidence-check.txt`).

## Run it yourself

From this folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

| Command | What it does |
|---|---|
| `make setup` | the POC environment (Python 3.12 via uv; pytest) |
| `make test` | unit, integration and regression tests (no model, no Ollama) -> verification/pytest.* |
| `make verify` | frozen inputs, an independent recomputation of the headline numbers, replay, tests -> verification/ |
| `make replay` | replay the published run from its tapes into runs/<run>-replay and compare byte for byte (no model) |
| `make demo` | INC-4917 through the naive and the governed pipeline, from the published tape (no model) |
| `make docs` | both editions and the run report as Markdown, standalone HTML and PDF |
| `make qa` | rendered checks of the pages at desktop, tablet and mobile widths -> qa/ |

Author only: `make index`, `make facts`, `make exploratory` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `diagrams/` | figures and the cover (Excalidraw sources, SVG, PNG) |
| `docs/` | edition sources and build notes; docs/archive/ keeps replaced originals |
| `enterprise_knowledge_rag_poc/` | the proof of concept and its recorded runs |
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

Every measured number in the editions comes from `enterprise_knowledge_rag_poc/runs/2026-10-08-heldout/facts.json` of run `2026-10-08-heldout`. This README, the results page and the Medium edition's top and end are written by `series-start-here/tools/series_edition.py` from `series-start-here/series.json` and the chapter's own files; the previous README is kept in `docs/archive/README-original.md`.
