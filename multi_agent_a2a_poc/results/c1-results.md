# C1 · Multi-Agent & A2A · Results

*When does one agent become several, and when does an agent deserve A2A?*

Production AI Engineering · C1 · Coordination

## The run

- **Published run:** `2026-10-08-blind` (declared in `coordination_poc/runs/PUBLISHED`)
- **How it ran:** live local model, recorded tape
- **Numbers come from:** `coordination_poc/runs/2026-10-08-blind/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. REPLAY IDENTICAL: 72 of 72 workflows; FROZEN CHECK OK (51 files, frozen at 2026-10-08T01:38:01+0530; 49 unchanged, 2 changed after the run and recorded in DEVIATIONS.md). Source: `verification/replay-check.json, verification/frozen-check.txt`
- **Findings:** 9 preregistered hypotheses: 7 SUPPORTED, 2 NOT SUPPORTED. Source: `coordination_poc/runs/2026-10-08-blind/facts.json (H1–H9)`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `e1.runs` | **72** | `runs/2026-10-08-blind/rows.jsonl: blind rows` |
| `e1.A.success` | **9** | `runs/2026-10-08-blind/rows.jsonl: eval.success, arch=A` |
| `e1.A.n` | **24** | `runs/2026-10-08-blind/rows.jsonl: arch=A` |
| `e1.B.success` | **16** | `runs/2026-10-08-blind/rows.jsonl: eval.success, arch=B` |
| `e1.B.n` | **24** | `runs/2026-10-08-blind/rows.jsonl: arch=B` |
| `e1.C.success` | **12** | `runs/2026-10-08-blind/rows.jsonl: eval.success, arch=C` |
| `e1.C.n` | **24** | `runs/2026-10-08-blind/rows.jsonl: arch=C` |
| `tax.C_over_B_tokens_ratio` | **12** | `e1 medians` |
| `tax.C_over_B_latency_ratio` | **12.5** | `e1 medians` |
| `e1.C.llm_calls_total` | **849** | `runs/2026-10-08-blind/rows.jsonl: metrics.llm_calls sum` |
| `e1.B.llm_calls_total` | **44** | `runs/2026-10-08-blind/rows.jsonl: metrics.llm_calls sum` |
| `c.boundary_ms_per_delegation` | **19** | `runs/2026-10-08-blind/rows.jsonl: sum boundary_overhead_ms / completed delegation attempts, arch C (prereg definition)` |
| `c.boundary_share_of_latency_pct` | **0.07** | `runs/2026-10-08-blind/rows.jsonl: sum boundary_overhead_ms / sum latency_ms, arch C (text, 2 decimals)` |
| `e1.B.latency_median_s` | **11.3** | `runs/2026-10-08-blind/rows.jsonl: metrics.latency_ms median` |
| `e1.B.tokens_total_median` | **5253** | `runs/2026-10-08-blind/rows.jsonl: metrics.tokens_total median` |
| `e1.C.complex.success` | **4** | `runs/2026-10-08-blind/rows.jsonl: subset complex` |
| `e1.B.complex.success` | **6** | `runs/2026-10-08-blind/rows.jsonl: subset complex` |
| `e1.A.simple.success` | **6** | `runs/2026-10-08-blind/rows.jsonl: subset simple` |
| `e1.A.simple.n` | **9** | `runs/2026-10-08-blind/rows.jsonl: subset simple` |
| `e1.B.simple.success` | **5** | `runs/2026-10-08-blind/rows.jsonl: subset simple` |
| `e1.A.complex.success` | **0** | `runs/2026-10-08-blind/rows.jsonl: subset complex` |
| `e1.A.complex.n` | **9** | `runs/2026-10-08-blind/rows.jsonl: subset complex` |
| `e1.A.complex.right_outcome_no_evidence` | **7** | `runs/2026-10-08-blind/rows.jsonl: A complex runs with the right outcome and write but without the required evidence` |
| `e1.A.right_outcome_no_evidence` | **10** | `runs/2026-10-08-blind/rows.jsonl: expected outcome reached without the required evidence` |
| `e1.A.multi_write_runs` | **4** | `runs/2026-10-08-blind/rows.jsonl: runs with two or more executed production writes` |
| `e1.C.failed_by_model_error` | **4** | `runs/2026-10-08-blind/rows.jsonl: runs ended FAILED by a model-server error` |
| `c.coord_model_errors` | **4** | `coordinator model calls that failed after the provider's attempts` |
| `c.coord_model_calls` | **206** | `model calls by the coordinator, arch C` |
| `c.specialist_model_errors` | **1** | `specialist model calls that failed` |
| `c.specialist_model_calls` | **643** | `model calls by the four specialists` |
| `e1.A.llm_calls_total` | **245** | `runs/2026-10-08-blind/rows.jsonl: metrics.llm_calls sum` |
| `inc.B_gt_C` | **3** | `runs/2026-10-08-blind/rows.jsonl: incidents where B had more successes (of 3) than C` |
| `e1.incidents` | **8** | `runs/2026-10-08-blind/rows.jsonl: distinct blind fixtures` |
| `inc.C_gt_B` | **1** | `runs/2026-10-08-blind/rows.jsonl: incidents where C had more successes (of 3) than B` |
| `inc.B_eq_C` | **4** | `runs/2026-10-08-blind/rows.jsonl: incidents where B and C tied` |
| `inc.C_tokens_gt_B` | **8** | `runs/2026-10-08-blind/rows.jsonl: incidents where C's median tokens_total exceeded B's` |
| `inc.C_latency_gt_B` | **8** | `runs/2026-10-08-blind/rows.jsonl: incidents where C's median latency_ms exceeded B's` |
| `inc.C_over_B_tokens_min_ratio` | **7.1** | `runs/2026-10-08-blind/rows.jsonl: smallest per-incident ratio of C's to B's median tokens_total` |
| `H1` | **SUPPORTED** | `prereg H1 test on e1 simple subset` |
| `H2` | **NOT SUPPORTED** | `prereg H2 test on e1 complex subset` |
| `H3` | **SUPPORTED** | `prereg H3 test on e1 simple subset` |
| `H4` | **SUPPORTED** | `prereg H4 test on e1 medians` |
| `H5` | **SUPPORTED** | `prereg H5 test on e1 totals` |
| `H6` | **SUPPORTED** | `prereg H6 test on e6` |
| `H7` | **SUPPORTED** | `prereg H7 test on e6` |
| `H8` | **SUPPORTED** | `prereg H8 test` |
| `H9` | **NOT SUPPORTED** | `prereg H9 test on e8 (safety cap OR an identical delegation >= 3 times)` |
| `e7.a2a_minus_inproc_median_ms` | **5.36** | `runs/2026-10-08-e7/summary.json` |
| `e1.C.coordination_token_share_pct` | **26** | `runs/2026-10-08-blind/rows.jsonl: sum tokens_coordination / sum tokens_total` |
| `e1.C.duplicate_cross_component_median` | **5** | `runs/2026-10-08-blind/rows.jsonl: metrics.duplicate_cross_component median` |
| `e1.C.review_rejections_total` | **7** | `runs/2026-10-08-blind/rows.jsonl: metrics.review_rejections sum` |
| `e6.K1.get_task_after_restart` | **TaskNotFoundError** | `runs/2026-10-08-e6/rows.jsonl` |
| `e6.K2.max_executions_same_write` | **1** | `runs/2026-10-08-e6/rows.jsonl: world executions per killed run (one write kind per run)` |
| `e6.K2-neg.max_executions_same_write` | **2** | `runs/2026-10-08-e6/rows.jsonl: world executions per killed run (one write kind per run)` |
| `e8.runs` | **8** | `runs/2026-10-08-e8/rows.jsonl` |
| `e8.handoffs_max` | **10** | `runs/2026-10-08-e8/rows.jsonl` |
| `c.delegations_completed` | **119** | `runs/2026-10-08-blind/rows.jsonl: completed delegation attempts, arch C` |
| `c.delegations_total` | **120** | `runs/2026-10-08-blind/rows.jsonl: metrics.delegation_attempts sum, arch C` |
| `c.execute_all_writes` | **1** | `execute delegations that fell back to every eligible write scope (no proposal passed)` |
| `c.execute_delegations` | **16** | `runs/2026-10-08-blind/session/platform.db: delegations mode=execute` |
| `run.id` | **2026-10-08-blind** | `the published E1 run` |

## The checks

Source: `coordination_poc/runs/2026-10-08-blind/facts.json (H1–H9)`. SUPPORTED: 7, NOT SUPPORTED: 2

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `H1` |  | prereg H1 test on e1 simple subset | SUPPORTED |  |
| `H2` |  | prereg H2 test on e1 complex subset | NOT SUPPORTED |  |
| `H3` |  | prereg H3 test on e1 simple subset | SUPPORTED |  |
| `H4` |  | prereg H4 test on e1 medians | SUPPORTED |  |
| `H5` |  | prereg H5 test on e1 totals | SUPPORTED |  |
| `H6` |  | prereg H6 test on e6 | SUPPORTED |  |
| `H7` |  | prereg H7 test on e6 | SUPPORTED |  |
| `H8` |  | prereg H8 test | SUPPORTED |  |
| `H9` |  | prereg H9 test on e8 (safety cap OR an identical delegation >= 3 times) | NOT SUPPORTED |  |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python 3.12 via uv; pytest)
make test    # the POC's unit and end-to-end tests (real A2A and MCP processes, no model) -> verification/pytest.*
make verify    # frozen inputs unchanged, replay identical and the tests, in a throwaway copy of the POC (the published run is not written) -> verification/
make replay    # the same as make verify: the published run's replay check runs in a throwaway copy
make demo    # one benchmark case (B1) through architecture C with a scripted model, in a throwaway copy of the POC
make docs    # both editions and the evidence documents as Markdown, standalone HTML and PDF (figures pending -> placeholders)
make qa    # the Medium edition's checks: what Medium cannot show, relative links, stale wording
```

*Built by `series-start-here/tools/series_edition.py results C1` from the files named above. It computes nothing new.*
