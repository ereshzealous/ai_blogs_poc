# Proof refresh delta · F1 Medium edition

Every distinct metric of the original publication baseline (`docs/proof-standardization/original-publication-baseline.json`, commit `09887e6`) against the
published run `blind-rerun-2026-10-01` on 2026-10-01 (the baseline cites `blind-main`). 67 metrics; 25 changed. Methodology: unchanged: the same frozen benchmark, scorer, prompts and model, run live again; fresh-live-run: the frozen blind benchmark run again live on 2026-10-01, promoted at the author's request so the articles cite the fresh measurements.

| Metric | Previous article | Published run | Change | Reason |
|---|---:|---:|---:|---|
| `estate.500.tools` | 500 | 500 | none | unchanged in blind-rerun-2026-10-01 |
| `estate.500.servers` | 43 | 43 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.paygate.refund_charge` | #1 | #1 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.payments_legacy.refund_charge_v1` | #2 | #2 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.refunds_staging.refund_order` | #4 | #4 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.refunds.refund_order` | #7 | #7 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.loyalty.merge_members|num` | 3 | 3 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.payments.list_charges|num` | 5 | 5 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.marketplace.charge_seller_penalty|num` | 6 | 6 | none | unchanged in blind-rerun-2026-10-01 |
| `policy.refund.approval_over` | 250 | 250 | none | unchanged in blind-rerun-2026-10-01 |
| `world.ORD-4917.amount` | 184.20 | 184.20 | none | unchanged in blind-rerun-2026-10-01 |
| `C.all.unsafe_proposal.k` | 15 | 19 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `C.all.unsafe_execution.k` | 0 | 0 | none | unchanged in blind-rerun-2026-10-01 |
| `rows.per_variant` | 168 | 168 | none | unchanged in blind-rerun-2026-10-01 |
| `A.500.median_tool_definition_tokens` | 28,083 | 28,083 | none | unchanged in blind-rerun-2026-10-01 |
| `B.500.median_tool_definition_tokens` | 486 | 485 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `C.500.correct.kn` | 54/56 | 52/56 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `A.500.correct.kn` | 48/56 | 47/56 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `conf.C_vs_A_500.p_holm` | 0.070 | 0.180 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `A.50.correct.pct` | 80% | 80% | none | unchanged in blind-rerun-2026-10-01 |
| `A.100.correct.pct` | 84% | 84% | none | unchanged in blind-rerun-2026-10-01 |
| `A.500.correct.pct` | 86% | 84% | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `cases.blind` | 56 | 56 | none | unchanged in blind-rerun-2026-10-01 |
| `estate.50.tools` | 50 | 50 | none | unchanged in blind-rerun-2026-10-01 |
| `estate.100.tools` | 100 | 100 | none | unchanged in blind-rerun-2026-10-01 |
| `variants.count` | 3 | 3 | none | unchanged in blind-rerun-2026-10-01 |
| `run.rows` | 504 | 504 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.paygate.refund_charge|num` | 1 | 1 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.payments_legacy.refund_charge_v1|num` | 2 | 2 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.refunds_staging.refund_order|num` | 4 | 4 | none | unchanged in blind-rerun-2026-10-01 |
| `rank.refunds.refund_order|num` | 7 | 7 | none | unchanged in blind-rerun-2026-10-01 |
| `unsafe_kind.all.vendor` | 6 | 4 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `unsafe_kind.all.legacy` | 1 | 1 | none | unchanged in blind-rerun-2026-10-01 |
| `harness.shortlist_k` | 8 | 8 | none | unchanged in blind-rerun-2026-10-01 |
| `C.500.median_tool_definition_tokens` | 541 | 542 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `B.all.unsafe_proposal.k` | 22 | 27 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `B.all.unsafe_execution.k` | 9 | 12 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `replay_r2.rows` | 728 | 728 | none | unchanged in blind-rerun-2026-10-01 |
| `replay_r2.reproduced` | 728 | 728 | none | unchanged in blind-rerun-2026-10-01 |
| `protocol.revisions` | 2026-07-28 | 2026-07-28 | none | unchanged in blind-rerun-2026-10-01 |
| `model.temperature` | 0 | 0 | none | unchanged in blind-rerun-2026-10-01 |
| `surface.C.max_capabilities` | 8 | 8 | none | unchanged in blind-rerun-2026-10-01 |
| `cases.categories` | 14 | 14 | none | unchanged in blind-rerun-2026-10-01 |
| `cases.dev` | 42 | 42 | none | unchanged in blind-rerun-2026-10-01 |
| `featured.audit_records` | 12 | 12 | none | unchanged in blind-rerun-2026-10-01 |
| `A.all.unsafe_proposal.k` | 32 | 28 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `A.all.unsafe_execution.k` | 8 | 5 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `conf.C_vs_A_500.c_only` | 7 | 7 | none | unchanged in blind-rerun-2026-10-01 |
| `conf.C_vs_A_500.other_only` | 1 | 2 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `B.500.correct.pct` | 68% | 66% | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `conf.C_vs_B_500.c_only` | 17 | 17 | none | unchanged in blind-rerun-2026-10-01 |
| `conf.C_vs_B_500.other_only` | 1 | 2 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `noise.C.50.agreement` | 52 | 54 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `noise.C.100.agreement` | 55 | 51 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `noise.C.500.agreement` | 54 | 52 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `noise.B.500.repeat_unsafe_executions` | 3 | 2 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `C.all.incorrect.k` | 7 | 8 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `outage.C.transient_completed` | 1/6 | 3/6 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `outage.A.transient_completed` | 6/6 | 5/6 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `outage.B.transient_completed` | 6/6 | 6/6 | none | unchanged in blind-rerun-2026-10-01 |
| `owned_fact.B.all` | 22 | 20 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `unsafe_kind.all.invented` | 7 | 7 | none | unchanged in blind-rerun-2026-10-01 |
| `unsafe_kind.all.no_approval` | 3 | 4 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `C.all.unsafe_execution.kn` | 0/168 | 0/168 | none | unchanged in blind-rerun-2026-10-01 |
| `C.all.unsafe_proposal.kn` | 15/168 | 19/168 | changed | re-measured: blind-rerun-2026-10-01 is a fresh live pass of the same frozen benchmark (evidence/published.json → note) |
| `A.50.correct.kn` | 45/56 | 45/56 | none | unchanged in blind-rerun-2026-10-01 |
| `A.100.correct.kn` | 47/56 | 47/56 | none | unchanged in blind-rerun-2026-10-01 |
