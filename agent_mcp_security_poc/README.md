# T6 · Securing Agents & MCP

*If the model is fooled, can the unsafe action still happen?*

Production AI Engineering · T6 · Trust & Security · chapter 11 of 15

## Read it

- **The article:** "T6 · Securing Agents & MCP", on Medium
- **Results:** [`results/t6-results.md`](results/t6-results.md), every number the article uses with its source file, the checks and the two verdicts ([rendered page](https://ereshzealous.github.io/ai_blogs_poc/agent_mcp_security_poc/results/t6-results.html))
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

Author only: `make freeze`, `make proof` rewrite published evidence, so they refuse unless run with `REWRITE_PUBLISHED=yes`.

## Layout

| Path | What is there |
|---|---|
| `redteam_poc/` | the proof of concept and its recorded runs |
| `results/` | the results page and the detailed evidence pages |
| `Makefile` | the commands above (`make help` lists them) |

## Provenance

Every measured number comes from `redteam_poc/evidence/runs/2026-10-07-recorded/facts.json` of run `2026-10-07-recorded`. This README and the results page are generated from the chapter's own files; nothing in them is typed by hand.
