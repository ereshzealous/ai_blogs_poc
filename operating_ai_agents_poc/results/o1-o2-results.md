# O1+O2 · Operating at Scale · Results

*What changes at production volume, and how do changes ship safely?*

Production AI Engineering · O1+O2 · Scale & Operations

## The run

- **Published run:** `2026-10-08-recorded` (declared in `evidence/published.json`)
- **How it ran:** deterministic discrete-event simulation, no model
- **Numbers come from:** `ops_poc/runs/2026-10-08-recorded/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. 11 of 11 verification sections pass. Source: `evidence/verification/verification.json`
- **Findings:** 14 claims: 10 supported, 3 limitation, 1 control; check findings: 1 LIMITATION OBSERVED, 1 EXPECTED FAILURE. Source: `evidence/runs/2026-10-08-recorded/results.json`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `amp.model_calls` | **2** | `scenarios/E8/rows/R41.jsonl` |
| `amp.input_tokens` | **8580** | `scenarios/E8/rows/R41.jsonl` |
| `amp.retrieval_calls` | **1.4** | `scenarios/E8/rows/R41.jsonl` |
| `amp.tool_calls` | **1.1** | `scenarios/E8/rows/R41.jsonl` |
| `amp.coord.model_calls` | **8.4** | `scenarios/E4/none/rows.jsonl` |
| `amp.single.model_calls` | **3.1** | `scenarios/E4/none/rows.jsonl` |
| `e1.naive.goodput_pct` | **9.3** | `scenarios/E1/naive/requests.jsonl` |
| `e1.controlled.goodput_pct` | **45.5** | `scenarios/E1/controlled/requests.jsonl` |
| `e10.R42-a.mix-adjusted.last.tool_calls_pct` | **88.9** | `scenarios/E10/R42-a__mix-adjusted/canary.json` |
| `e1.naive.retry_amplification` | **2.81** | `scenarios/E1/naive/rows.jsonl` |
| `e1.naive.wasted_cu_pct` | **97.4** | `scenarios/E1/naive/rows.jsonl` |
| `e1.controlled.refused_pct` | **53.2** | `scenarios/E1/controlled/requests.jsonl` |
| `cfg.e2_finance_items` | **3000** | `experiments/scenarios.toml` |
| `e2.naive.support.goodput_pct` | **3.6** | `scenarios/E2/naive/requests.jsonl` |
| `e2.controlled.support.goodput_pct` | **100** | `scenarios/E2/controlled/requests.jsonl` |
| `e2.controlled.finance.completed` | **3000** | `scenarios/E2/controlled/requests.jsonl` |
| `e2.makespan_ratio` | **2.23** | `scenarios/E2/*/requests.jsonl` |
| `e3.naive.max_active` | **1227** | `scenarios/E3/naive/stats.json` |
| `e3.naive.goodput_pct` | **44.2** | `scenarios/E3/naive/requests.jsonl` |
| `e3.controlled.goodput_pct` | **84.4** | `scenarios/E3/controlled/requests.jsonl` |
| `e4.none.runaway.cost_cu` | **18960.3** | `scenarios/E4/none/rows.jsonl` |
| `e4.envelope.runaway.cost_cu` | **150** | `scenarios/E4/envelope/rows.jsonl` |
| `e4.per-agent.coord.model_calls` | **11** | `scenarios/E4/per-agent/rows.jsonl` |
| `e4.limit.dispute-investigation.model_calls` | **10** | `scenarios/E4/limits.json` |
| `e4.envelope.coord.model_calls` | **9** | `scenarios/E4/envelope/rows.jsonl` |
| `e5.routed_vs_large_pct` | **59.9** | `scenarios/E5/*/rows.jsonl` |
| `e5.all-small.capability_violations` | **516** | `scenarios/E5/all-small/rows.jsonl` |
| `e5.routed-any-fallback.data_violations` | **18** | `scenarios/E5/routed-any-fallback/rows.jsonl` |
| `e5.routed.deferred` | **7** | `scenarios/E5/routed/rows.jsonl` |
| `e6.token_reduction_pct` | **82.8** | `scenarios/E6/retrieval.jsonl` |
| `e6.required_ids` | **15** | `scenarios/E6/retrieval.jsonl` |
| `e6.cache.query-text.cross_principal` | **5** | `scenarios/E6/cache.jsonl` |
| `e6.cache.query-text.stale` | **5** | `scenarios/E6/cache.jsonl` |
| `cfg.payments_capacity` | **8** | `config/tools.toml` |
| `cfg.e7_slots` | **64** | `experiments/scenarios.toml` |
| `e7.naive.http_503` | **237** | `scenarios/E7/naive/stats.json` |
| `e7.naive.attempts_per_call` | **2.81** | `scenarios/E7/naive/rows.jsonl` |
| `e7.controlled.http_503` | **0** | `scenarios/E7/controlled/stats.json` |
| `e7.controlled.support_goodput_pct` | **5.3** | `scenarios/E7/controlled/requests.jsonl` |
| `e7.composed.support_goodput_pct` | **100** | `scenarios/E7/composed/requests.jsonl` |
| `amp.coord.component_sum_s` | **29** | `scenarios/E4/none/rows.jsonl` |
| `amp.coord.wall_s` | **16** | `scenarios/E4/none/rows.jsonl` |
| `lat.queue_share_pct` | **70.6** | `scenarios/E1/controlled/rows.jsonl` |
| `e8.distinct_release_ids` | **7** | `scenarios/E8/releases/*.json` |
| `e9.R42-a.tool_calls_delta_pct` | **32.7** | `scenarios/E9/evals/*.json` |
| `e8.R42-a.tool_calls_delta_pct` | **71.3** | `scenarios/E8/rows/*.jsonl` |
| `e9.R42-b.task_success_pct` | **100** | `ops_poc/runs/2026-10-08-recorded/scenarios/E9/evals/R42-b.json` |
| `e9.R42-b.inv.data_policy` | **21** | `scenarios/E9/evals/R42-b.json` |
| `e9.R42-c.inv.approval_bypass` | **4** | `scenarios/E9/evals/R42-c.json` |
| `e10.R42-a.mix-adjusted.last.error_pp` | **0** | `scenarios/E10/R42-a__mix-adjusted/canary.json` |
| `e10.R42-a.mix-adjusted.last.cost_per_success_pct` | **-0.1** | `scenarios/E10/R42-a__mix-adjusted/canary.json` |
| `cfg.guardrail.tool_calls_delta_max_pct` | **25** | `experiments/preregistration.toml` |
| `e10.R42-e.mix-adjusted.windows` | **4** | `scenarios/E10/R42-e__mix-adjusted/canary.json` |
| `e10.R42-a.mix-adjusted.effects_before_decision` | **60** | `scenarios/E10/R42-a__mix-adjusted/canary.json` |
| `e10.R42-a.mix-adjusted.effects_reverted` | **0** | `scenarios/E10/R42-a__mix-adjusted/canary.json` |
| `replay.identical` | **99** | `evidence/runs/2026-10-08-recorded/replay.json` |
| `replay.files` | **99** | `evidence/runs/2026-10-08-recorded/replay.json` |
| `tests.scenarios` | **10** | `verification/pytest.junit.xml` |
| `proof.claims_tested` | **10** | `evidence/runs/2026-10-08-recorded/results.json → claims` |
| `proof.claims_qualified` | **1** | `evidence/runs/2026-10-08-recorded/results.json → claims` |
| `proof.checks` | **65** | `evidence/runs/2026-10-08-recorded/results.json → check_counts` |
| `proof.pass` | **63** | `evidence/runs/2026-10-08-recorded/results.json → check_counts` |
| `proof.expected_failure` | **1** | `evidence/runs/2026-10-08-recorded/results.json → check_counts` |
| `proof.fail` | **1** | `evidence/runs/2026-10-08-recorded/results.json → check_counts` |
| `e4.envelope.legit_cut` | **4** | `scenarios/E4/envelope/rows.jsonl` |
| `e4.envelope.legit_n` | **350** | `scenarios/E4/envelope/rows.jsonl` |
| `e4.envelope.legit_cut_rerun` | **4** | `scenarios/E4/envelope/rows.jsonl` |
| `run.id` | **2026-10-08-recorded** | `manifest.json` |

## The checks

Source: `evidence/runs/2026-10-08-recorded/checks.jsonl`. PASS: 63, FAIL: 1, EXPECTED_FAILURE: 1

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `OPS-E1-C01` | OPS-E1 |  | PASS | PASS |
| `OPS-E1-C02` | OPS-E1 |  | PASS | PASS |
| `OPS-E1-C03` | OPS-E1 |  | PASS | PASS |
| `OPS-E1-C04` | OPS-E1 |  | PASS | PASS |
| `OPS-E1-C05` | OPS-E1 |  | PASS | PASS |
| `OPS-E1-C06` | OPS-E1 |  | PASS | PASS |
| `OPS-E1-C07` | OPS-E1 |  | PASS | PASS |
| `OPS-E2-C01` | OPS-E2 |  | PASS | PASS |
| `OPS-E2-C02` | OPS-E2 |  | PASS | PASS |
| `OPS-E2-C03` | OPS-E2 |  | PASS | PASS |
| `OPS-E2-C04` | OPS-E2 |  | PASS | PASS |
| `OPS-E2-C05` | OPS-E2 |  | PASS | PASS |
| `OPS-E2-C06` | OPS-E2 |  | PASS | PASS |
| `OPS-E3-C01` | OPS-E3 |  | PASS | PASS |
| `OPS-E3-C02` | OPS-E3 |  | PASS | PASS |
| `OPS-E3-C03` | OPS-E3 |  | PASS | PASS |
| `OPS-E3-C04` | OPS-E3 |  | PASS | PASS |
| `OPS-E3-C05` | OPS-E3 |  | PASS | PASS |
| `OPS-E3-C06` | OPS-E3 |  | PASS | PASS |
| `OPS-E4-C01` | OPS-E4 |  | PASS | PASS |
| `OPS-E4-C02` | OPS-E4 |  | PASS | PASS |
| `OPS-E4-C03` | OPS-E4 |  | PASS | PASS |
| `OPS-E4-C04` | OPS-E4 |  | PASS | PASS |
| `OPS-E4-C05` | OPS-E4 |  | FAIL | LIMITATION OBSERVED |
| `OPS-E5-C01` | OPS-E5 |  | PASS | PASS |
| `OPS-E5-C02` | OPS-E5 |  | PASS | PASS |
| `OPS-E5-C03` | OPS-E5 |  | PASS | PASS |
| `OPS-E5-C04` | OPS-E5 |  | PASS | PASS |
| `OPS-E5-C05` | OPS-E5 |  | PASS | PASS |
| `OPS-E5-C06` | OPS-E5 |  | PASS | PASS |
| `OPS-E5-C07` | OPS-E5 |  | PASS | PASS |
| `OPS-E5-C08` | OPS-E5 |  | PASS | PASS |
| `OPS-E6-C01` | OPS-E6 |  | PASS | PASS |
| `OPS-E6-C02` | OPS-E6 |  | PASS | PASS |
| `OPS-E6-C03` | OPS-E6 |  | PASS | PASS |
| `OPS-E6-C04` | OPS-E6 |  | PASS | PASS |
| `OPS-E6-C05` | OPS-E6 |  | PASS | PASS |
| `OPS-E6-C06` | OPS-E6 |  | PASS | PASS |
| `OPS-E6-C07` | OPS-E6 |  | PASS | PASS |
| `OPS-E7-C01` | OPS-E7 |  | PASS | PASS |
| `OPS-E7-C02` | OPS-E7 |  | PASS | PASS |
| `OPS-E7-C03` | OPS-E7 |  | PASS | PASS |
| `OPS-E7-C04` | OPS-E7 |  | PASS | PASS |
| `OPS-E7-C05` | OPS-E7 |  | PASS | PASS |
| `OPS-E7-C06` | OPS-E7 |  | PASS | PASS |
| `OPS-E7-C07` | OPS-E7 |  | PASS | PASS |
| `OPS-E7-C08` | OPS-E7 |  | PASS | PASS |
| `OPS-E7-C09` | OPS-E7 |  | PASS | PASS |
| `OPS-E8-C01` | OPS-E8 |  | PASS | PASS |
| `OPS-E8-C02` | OPS-E8 |  | PASS | PASS |
| `OPS-E8-C03` | OPS-E8 |  | PASS | PASS |
| `OPS-E8-C04` | OPS-E8 |  | PASS | PASS |
| `OPS-E8-C05` | OPS-E8 |  | PASS | PASS |
| `OPS-E9-C01` | OPS-E9 |  | PASS | PASS |
| `OPS-E9-C02` | OPS-E9 |  | PASS | PASS |
| `OPS-E9-C03` | OPS-E9 |  | PASS | PASS |
| `OPS-E9-C04` | OPS-E9 |  | PASS | PASS |
| `OPS-E10-C01` | OPS-E10 |  | PASS | PASS |
| `OPS-E10-C02` | OPS-E10 |  | PASS | PASS |
| `OPS-E10-C03` | OPS-E10 |  | PASS | PASS |
| `OPS-E10-C04` | OPS-E10 |  | PASS | PASS |
| `OPS-E10-C05` | OPS-E10 |  | PASS | PASS |
| `OPS-E10-C06` | OPS-E10 |  | PASS | PASS |
| `OPS-E10-C07` | OPS-E10 |  | PASS | PASS |
| `OPS-NC-C01` | OPS-NC |  | EXPECTED_FAILURE | EXPECTED FAILURE |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python 3.12 via uv; pytest)
make test    # the POC's tests (10 scenario tests + unit tests) -> verification/pytest.*
make verify    # PROOF VERIFICATION of the published run -> evidence/verification/verification.{txt,json}
make replay    # every scenario rerun from source in a temp folder and compared with the published run (nothing recorded)
make demo    # the surge with and without admission, then the canary, narrated
make docs    # both editions and the evidence documents as Markdown, standalone HTML and PDF
make qa    # rendered checks of every page (desktop/tablet/mobile) -> qa/
```

*Built by `series-start-here/tools/series_edition.py results O1+O2` from the files named above. It computes nothing new.*
