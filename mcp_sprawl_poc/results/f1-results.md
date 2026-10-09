# F1 · MCP Tool Sprawl · Results

*Which capability should the agent see, and may this exact call execute?*

Production AI Engineering · F1 · Foundation

## The run

- **Published run:** `blind-rerun-2026-10-01` (declared in `evidence/published.json`)
- **How it ran:** live local model, recorded
- **Numbers come from:** `evidence/evidence.json (facts)`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. 10 of 10 verification sections pass. Source: `evidence/verification/verification.json`
- **Findings:** 24 claims: 12 supported, 3 implementation, 3 not_established, 3 limitation, 2 contradicted, 1 control; check findings: 2 NOT SUPPORTED, 1 NOT ESTABLISHED, 1 NOT OBSERVED, 1 LIMITATION OBSERVED, 1 EXPECTED FAILURE. Source: `evidence/runs/blind-rerun-2026-10-01/results.json`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `A.100.correct.kn` | **47/56** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.A_all_tools@100.correct` |
| `A.100.correct.pct` | **84%** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.A_all_tools@100.correct` |
| `A.50.correct.kn` | **45/56** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.A_all_tools@50.correct` |
| `A.50.correct.pct` | **80%** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.A_all_tools@50.correct` |
| `A.500.correct.kn` | **47/56** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.A_all_tools@500.correct` |
| `A.500.correct.pct` | **84%** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.A_all_tools@500.correct` |
| `A.500.median_tool_definition_tokens` | **28,083** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.A_all_tools@500.median_tool_definition_tokens` |
| `A.all.unsafe_execution.k` | **5** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.A_all_tools@{50,100,500}.unsafe_execution (summed)` |
| `A.all.unsafe_proposal.k` | **28** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.A_all_tools@{50,100,500}.unsafe_proposal (summed)` |
| `B.500.correct.kn` | **37/56** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.B_search_only@500.correct` |
| `B.500.correct.pct` | **66%** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.B_search_only@500.correct` |
| `B.500.median_tool_definition_tokens` | **485** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.B_search_only@500.median_tool_definition_tokens` |
| `B.500.unsafe_execution.k` | **4** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.B_search_only@500.unsafe_execution` |
| `B.all.unsafe_execution.k` | **12** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.B_search_only@{50,100,500}.unsafe_execution (summed)` |
| `B.all.unsafe_proposal.k` | **27** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.B_search_only@{50,100,500}.unsafe_proposal (summed)` |
| `C.500.correct.kn` | **52/56** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.C_control_plane@500.correct` |
| `C.500.median_tool_definition_tokens` | **542** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.C_control_plane@500.median_tool_definition_tokens` |
| `C.all.incorrect.k` | **8** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.C_control_plane@*.correct (n − k, summed)` |
| `C.all.unsafe_execution.k` | **0** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.C_control_plane@{50,100,500}.unsafe_execution (summed)` |
| `C.all.unsafe_execution.kn` | **0/168** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.C_control_plane@{50,100,500}.unsafe_execution (summed)` |
| `C.all.unsafe_proposal.k` | **19** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.C_control_plane@{50,100,500}.unsafe_proposal (summed)` |
| `C.all.unsafe_proposal.kn` | **19/168** | `experiment/analysis/blind-rerun-2026-10-01/summary.json → cells.C_control_plane@{50,100,500}.unsafe_proposal (summed)` |
| `cases.blind` | **56** | `experiment/benchmark/cases.json → split blind` |
| `cases.categories` | **14** | `experiment/benchmark/cases.json → categories` |
| `cases.dev` | **42** | `experiment/benchmark/cases.json → counts.dev` |
| `comparison.level` | **SEMANTIC** | `evidence/runs/blind-rerun-2026-10-01/replay-comparison.json → replay_level` |
| `comparison.regression` | **0** | `evidence/runs/blind-rerun-2026-10-01/replay-comparison.json → classes.REGRESSION` |
| `comparison.rows` | **504** | `evidence/runs/blind-rerun-2026-10-01/replay-comparison.json → rows` |
| `conf.C_vs_A_500.c_only` | **7** | `experiment/analysis/blind-rerun-2026-10-01/hypotheses.json → confirmatory.C_vs_A_500` |
| `conf.C_vs_A_500.other_only` | **2** | `experiment/analysis/blind-rerun-2026-10-01/hypotheses.json → confirmatory.C_vs_A_500` |
| `conf.C_vs_A_500.p_holm` | **0.180** | `experiment/analysis/blind-rerun-2026-10-01/hypotheses.json → confirmatory.C_vs_A_500` |
| `conf.C_vs_B_500.c_only` | **17** | `experiment/analysis/blind-rerun-2026-10-01/hypotheses.json → confirmatory.C_vs_B_500` |
| `conf.C_vs_B_500.other_only` | **2** | `experiment/analysis/blind-rerun-2026-10-01/hypotheses.json → confirmatory.C_vs_B_500` |
| `conf.C_vs_B_500.p_holm_eq` | **= 0.001** | `experiment/analysis/blind-rerun-2026-10-01/hypotheses.json → confirmatory.C_vs_B_500` |
| `embed.name` | **nomic-embed-text** | `experiment/raw/blind-rerun-2026-10-01/run-meta.json` |
| `estate.100.tools` | **100** | `poc/data/estates/estate-100/manifest.json` |
| `estate.50.tools` | **50** | `poc/data/estates/estate-50/manifest.json` |
| `estate.500.servers` | **43** | `poc/data/estates/estate-500/manifest.json` |
| `estate.500.tools` | **500** | `poc/data/estates/estate-500/manifest.json` |
| `estate.kind.core.tools` | **20** | `poc/data/estates/estate-500/manifest.json → by_kind (core)` |
| `estate.kind.other.tools` | **466** | `poc/data/estates/estate-500/manifest.json → by_kind (generated, generated_env_copy, generated_legacy)` |
| `featured.audit_records` | **12** | `experiment/raw/blind-rerun-2026-10-01/audit/BL-C03-1__C__500.jsonl` |
| `harness.shortlist_k` | **8** | `experiment/raw/blind-rerun-2026-10-01/run-meta.json` |
| `hyp.H5.A` | **2/4** | `experiment/analysis/blind-rerun-2026-10-01/hypotheses.json → H5` |
| `hyp.H5.B` | **3/4** | `experiment/analysis/blind-rerun-2026-10-01/hypotheses.json → H5` |
| `model.calls.main` | **2,110** | `experiment/raw/blind-rerun-2026-10-01/rows/*.json → model_calls` |
| `model.name` | **gpt-oss:20b** | `experiment/raw/blind-rerun-2026-10-01/run-meta.json` |
| `model.ollama_version` | **0.30.11** | `experiment/raw/blind-rerun-2026-10-01/run-meta.json` |
| `model.temperature` | **0** | `experiment/raw/blind-rerun-2026-10-01/run-meta.json` |
| `noise.B.500.repeat_unsafe_executions` | **2** | `experiment/analysis/blind-rerun-2026-10-01/noise-floor.json → B_search_only@500.repeat_unsafe_executions` |
| `noise.C.100.agreement` | **51** | `experiment/analysis/blind-rerun-2026-10-01/noise-floor.json → C_control_plane@100.agreement` |
| `noise.C.50.agreement` | **54** | `experiment/analysis/blind-rerun-2026-10-01/noise-floor.json → C_control_plane@50.agreement` |
| `noise.C.500.agreement` | **52** | `experiment/analysis/blind-rerun-2026-10-01/noise-floor.json → C_control_plane@500.agreement` |
| `outage.A.persistent_fallback_exec` | **0** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `outage.A.transient_completed` | **5/6** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `outage.B.persistent_fallback_exec` | **0** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `outage.B.transient_completed` | **6/6** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `outage.C.transient_completed` | **3/6** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `owned_fact.B.all` | **20** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `policy.refund.approval_over` | **250** | `poc/data/estates/estate-500/registry.yaml → refunds.refund_order.approval` |
| `proof.checks` | **64** | `evidence/runs/blind-rerun-2026-10-01/checks.jsonl` |
| `protocol.revisions` | **2026-07-28** | `experiment/analysis/blind-rerun-2026-10-01/extra.json → protocol.*.negotiated_protocol_versions` |
| `protocol.sdk_version` | **2.2.0** | `experiment/analysis/blind-rerun-2026-10-01/extra.json → protocol.*.sdk_version` |
| `published.run_id` | **blind-rerun-2026-10-01** | `evidence/published.json → run_id` |
| `rank.loyalty.merge_members` | **#3** | `experiment/analysis/blind-rerun-2026-10-01/extra.json → ord4917_ranking_500` |
| `rank.marketplace.charge_seller_penalty` | **#6** | `experiment/analysis/blind-rerun-2026-10-01/extra.json → ord4917_ranking_500` |
| `rank.paygate.refund_charge` | **#1** | `experiment/analysis/blind-rerun-2026-10-01/extra.json → ord4917_ranking_500` |
| `rank.payments.list_charges` | **#5** | `experiment/analysis/blind-rerun-2026-10-01/extra.json → ord4917_ranking_500` |
| `rank.payments_legacy.refund_charge_v1` | **#2** | `experiment/analysis/blind-rerun-2026-10-01/extra.json → ord4917_ranking_500` |
| `rank.refunds.refund_order` | **#7** | `experiment/analysis/blind-rerun-2026-10-01/extra.json → ord4917_ranking_500` |
| `rank.refunds_staging.refund_order` | **#4** | `experiment/analysis/blind-rerun-2026-10-01/extra.json → ord4917_ranking_500` |
| `replay.record.rows` | **504** | `experiment/recorded-run/replay-blind-rerun-2026-10-01/replay-verification.json` |
| `replay_r2.reproduced` | **728** | `experiment/recorded-run/replay-r2/summary.json` |
| `replay_r2.rows` | **728** | `experiment/recorded-run/replay-r2/summary.json` |
| `revision.id` | **r2** | `experiment/evidence-revisions.json` |
| `rows.per_variant` | **168** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl` |
| `run.rows` | **504** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `sel.A.500.capability_ok_incorrect` | **3** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl` |
| `sel.B.500.capability_ok_incorrect` | **4** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl` |
| `surface.C.max_capabilities` | **8** | `experiment/analysis/blind-rerun-2026-10-01/hypotheses.json → H4` |
| `unsafe_kind.all.invented` | **7** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `unsafe_kind.all.legacy` | **1** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `unsafe_kind.all.no_approval` | **4** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `unsafe_kind.all.vendor` | **4** | `experiment/raw/blind-rerun-2026-10-01/rows.jsonl (descriptive tally, poc/scripts/facts.py)` |
| `variants.count` | **3** | `proof/learning.toml → dimensions.variants` |
| `world.ORD-4917.amount` | **184.20** | `poc/data/world/seed.db → charges where order_id = ORD-4917` |

## The checks

Source: `evidence/runs/blind-rerun-2026-10-01/checks.jsonl`. PASS: 58, FAIL: 5, EXPECTED_FAILURE: 1

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `F1-R1-C01` | F1-R1 |  | PASS | PASS |
| `F1-R1-C02` | F1-R1 |  | PASS | PASS |
| `F1-R1-C03` | F1-R1 |  | PASS | PASS |
| `F1-R1-C04` | F1-R1 |  | PASS | PASS |
| `F1-R1-C05` | F1-R1 |  | PASS | PASS |
| `F1-R1-C06` | F1-R1 |  | PASS | PASS |
| `F1-R1-C07` | F1-R1 |  | PASS | PASS |
| `F1-R1-C08` | F1-R1 |  | PASS | PASS |
| `F1-R2-C01` | F1-R2 |  | FAIL | NOT SUPPORTED |
| `F1-R2-C02` | F1-R2 |  | PASS | PASS |
| `F1-R2-C03` | F1-R2 |  | PASS | PASS |
| `F1-R2-C04` | F1-R2 |  | FAIL | NOT ESTABLISHED |
| `F1-R3-C01` | F1-R3 |  | PASS | PASS |
| `F1-R3-C02` | F1-R3 |  | PASS | PASS |
| `F1-R3-C03` | F1-R3 |  | PASS | PASS |
| `F1-R3-C04` | F1-R3 |  | PASS | PASS |
| `F1-R4-C01` | F1-R4 |  | PASS | PASS |
| `F1-R4-C02` | F1-R4 |  | PASS | PASS |
| `F1-R4-C03` | F1-R4 |  | PASS | PASS |
| `F1-R4-C04` | F1-R4 |  | PASS | PASS |
| `F1-R5-C01` | F1-R5 |  | PASS | PASS |
| `F1-R5-C02` | F1-R5 |  | PASS | PASS |
| `F1-R5-C03` | F1-R5 |  | PASS | PASS |
| `F1-R5-C04` | F1-R5 |  | PASS | PASS |
| `F1-R6-C01` | F1-R6 |  | PASS | PASS |
| `F1-R6-C02` | F1-R6 |  | PASS | PASS |
| `F1-R6-C03` | F1-R6 |  | PASS | PASS |
| `F1-R6-C04` | F1-R6 |  | PASS | PASS |
| `F1-R6-C05` | F1-R6 |  | PASS | PASS |
| `F1-R7-C01` | F1-R7 |  | PASS | PASS |
| `F1-R7-C02` | F1-R7 |  | PASS | PASS |
| `F1-R7-C03` | F1-R7 |  | PASS | PASS |
| `F1-R7-C04` | F1-R7 |  | PASS | PASS |
| `F1-R7-C05` | F1-R7 |  | PASS | PASS |
| `F1-R7-C06` | F1-R7 |  | PASS | PASS |
| `F1-R7-C07` | F1-R7 |  | PASS | PASS |
| `F1-R7-C08` | F1-R7 |  | PASS | PASS |
| `F1-R7-C09` | F1-R7 |  | PASS | PASS |
| `F1-R8-C01` | F1-R8 |  | PASS | PASS |
| `F1-R8-C02` | F1-R8 |  | PASS | PASS |
| `F1-R8-C03` | F1-R8 |  | PASS | PASS |
| `F1-R8-C04` | F1-R8 |  | PASS | PASS |
| `F1-R8-C05` | F1-R8 |  | PASS | PASS |
| `F1-R8-C06` | F1-R8 |  | PASS | PASS |
| `F1-R8-C07` | F1-R8 |  | PASS | PASS |
| `F1-R8-C08` | F1-R8 |  | PASS | PASS |
| `F1-R8-C09` | F1-R8 |  | PASS | PASS |
| `F1-R9-C01` | F1-R9 |  | PASS | PASS |
| `F1-R9-C02` | F1-R9 |  | FAIL | NOT SUPPORTED |
| `F1-R9-C03` | F1-R9 |  | PASS | PASS |
| `F1-R9-C04` | F1-R9 |  | FAIL | NOT OBSERVED |
| `F1-R9-C05` | F1-R9 |  | PASS | PASS |
| `F1-R9-C06` | F1-R9 |  | FAIL | LIMITATION OBSERVED |
| `F1-R10-C01` | F1-R10 |  | PASS | PASS |
| `F1-R10-C02` | F1-R10 |  | PASS | PASS |
| `F1-R10-C03` | F1-R10 |  | PASS | PASS |
| `F1-R10-C04` | F1-R10 |  | PASS | PASS |
| `F1-R10-C05` | F1-R10 |  | PASS | PASS |
| `F1-R10-C06` | F1-R10 |  | PASS | PASS |
| `F1-R11-C01` | F1-R11 |  | PASS | PASS |
| `F1-R11-C02` | F1-R11 |  | PASS | PASS |
| `F1-R11-C03` | F1-R11 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `F1-R11-C04` | F1-R11 |  | PASS | PASS |
| `F1-R11-C05` | F1-R11 |  | PASS | PASS |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the environment (Python and the pinned dependencies, uv)
make test    # the deterministic unit tests: real MCP server processes, no model
make verify    # PROOF VERIFICATION of the published run: reads the shipped evidence, no model (seconds)
make replay    # replay recorded rows through the real stack without the model, and classify them against the run
make demo    # no single-scenario demo here: make replay replays recorded rows through the real stack
make docs    # both editions (Markdown, HTML, PDF) and the static Medium edition, then the uniform series pages
make qa    # publication scan: no local path, host name or address in the editions, results and README
```

*Built by `series-start-here/tools/series_edition.py results F1` from the files named above. It computes nothing new.*
