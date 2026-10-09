# F2 · Layered Agent Platform · Results

*Which production responsibility belongs where, and what survives failure?*

Production AI Engineering · F2 · Foundation

## The run

- **Published run:** `2026-09-28-recorded` (declared in `layered_architecture_poc/runs/PUBLISHED`)
- **How it ran:** recorded: live local models, real MCP servers, real SIGKILLs
- **Numbers come from:** `layered_architecture_poc/runs/2026-09-28-recorded/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. 36 of 36 checks pass, 12 recomputed from raw evidence. Source: `layered_architecture_poc/runs/2026-09-28-recorded/verification.json`
- **Findings:** 17 claims: 8 SUPPORTED, 4 QUALIFIED, 3 UNSUPPORTED, 2 CONTRADICTED; scenario outcomes: 0 ERROR, 8 FAILURE, 1 NOT_EXPOSED, 23 SUCCESS. Source: `layered_architecture_poc/docs/claims.yaml`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `headline.e1_runs_all_checks.monolith` | **3/3** | `summary.json` |
| `headline.e1_runs_all_checks.layered` | **3/3** | `summary.json` |
| `models.A` | **gpt-oss:20b** | `summary.json` |
| `E2.change.monolith.review_surface_concerns_n` | **10** | `summary.json → experiments` |
| `integrity.scenarios_expected` | **32** | `summary.json` |
| `integrity.scenarios_present` | **32** | `summary.json` |
| `models.B` | **qwen3:8b** | `summary.json` |
| `integrity.sigkills` | **7** | `summary.json` |
| `replay.model_calls_served_from_tape` | **366** | `summary.json` |
| `headline.tests` | **67/71** | `summary.json` |
| `headline.e4_duplicate_rollbacks.monolith` | **3** | `summary.json` |
| `E4.monolith.runs` | **3** | `summary.json → experiments` |
| `E4.monolith.physical_rollbacks_total` | **6** | `summary.json → experiments` |
| `headline.e4_duplicate_rollbacks.layered` | **0** | `summary.json` |
| `E4.layered.physical_rollbacks_total` | **3** | `summary.json → experiments` |
| `E4.layered.client_rollback_attempts` | **2, 2, 2** | `summary.json → experiments` |
| `E4.layered.backend_idempotent_replays` | **1, 1, 1** | `summary.json → experiments` |
| `E5.monolith.median_model_calls_after_crash` | **11** | `summary.json → experiments` |
| `headline.e5_median_tokens_after_crash.monolith` | **27723** | `summary.json` |
| `headline.e5_physical_rollbacks_total.monolith` | **6** | `summary.json` |
| `E5.monolith.runs` | **3** | `summary.json → experiments` |
| `E5.layered.median_model_calls_after_crash` | **0** | `summary.json → experiments` |
| `headline.e5_median_tokens_after_crash.layered` | **0** | `summary.json` |
| `E5.layered.sigkills` | **2** | `summary.json → experiments` |
| `headline.e5_physical_rollbacks_total.layered` | **2** | `summary.json` |
| `E5.layered.runs` | **3** | `summary.json → experiments` |
| `E5.layered.lease_takeovers` | **2** | `summary.json → experiments` |
| `E5.layered.median_wall_s_after_crash` | **1.4** | `summary.json → experiments` |
| `E5.layered.runs_all_checks` | **2** | `summary.json → experiments` |
| `E5.layered.checks_passed` | **20** | `summary.json → experiments` |
| `E5.layered.checks_total` | **24** | `summary.json → experiments` |
| `E5.layered.physical_rollbacks_total` | **2** | `summary.json → experiments` |
| `headline.e6_probe_writes_executed.monolith` | **2** | `summary.json` |
| `E6.monolith_probes_asked_human` | **2** | `summary.json → experiments` |
| `E6.monolith_probes_not_expressible` | **2** | `summary.json → experiments` |
| `headline.e6_probe_writes_executed.layered` | **0** | `summary.json` |
| `E6.layered_probes_blocked` | **6** | `summary.json → experiments` |
| `E6.adversarial.monolith.restarts_executed` | **1** | `summary.json → experiments` |
| `E6.adversarial.layered.restarts_executed` | **0** | `summary.json → experiments` |
| `E7.layered.model_calls_after_crash` | **0** | `summary.json → experiments` |
| `E7.layered.checks_passed` | **8** | `summary.json → experiments` |
| `E7.layered.checks_total` | **8** | `summary.json → experiments` |
| `E7.monolith.model_calls_after_crash` | **9** | `summary.json → experiments` |
| `E7.monolith.tokens_after_crash` | **12826** | `summary.json → experiments` |
| `E7.monolith.checks_passed` | **5** | `summary.json → experiments` |
| `E7.monolith.checks_total` | **8** | `summary.json → experiments` |
| `E8.monolith.runs` | **6** | `summary.json → experiments` |
| `headline.e8_median_trace_score.monolith` | **7.0/10** | `summary.json` |
| `E8.monolith.missing_in_any_run` | **workflow, checkpoint, action_attributable** | `summary.json → experiments` |
| `headline.e8_median_trace_score.layered` | **10.0/10** | `summary.json` |
| `E8.layered.crash_runs` | **3** | `summary.json → experiments` |
| `headline.e2_concerns_touched.monolith` | **1** | `summary.json` |
| `E2.change.monolith.files_changed` | **1** | `summary.json → experiments` |
| `headline.review_surface.E2.monolith` | **10** | `summary.json` |
| `headline.review_surface.E2.layered` | **1** | `summary.json` |
| `E2.monolith.runs_all_checks` | **3** | `summary.json → experiments` |
| `E2.monolith.runs` | **3** | `summary.json → experiments` |
| `headline.e3_concerns_touched.monolith` | **2** | `summary.json` |
| `headline.e3_concerns_touched.layered` | **1** | `summary.json` |
| `E3.change.layered.files_changed` | **3** | `summary.json → experiments` |
| `E3.change.monolith.files_changed` | **2** | `summary.json → experiments` |
| `headline.e9_files_changed.monolith` | **1** | `summary.json` |
| `headline.e9_files_changed.layered` | **4** | `summary.json` |
| `headline.spill_over.E9.monolith` | **2** | `summary.json` |
| `headline.spill_over.E9.layered` | **3** | `summary.json` |
| `headline.review_surface.E9.layered` | **4** | `summary.json` |
| `headline.review_surface.E9.monolith` | **10** | `summary.json` |
| `revisions` | **r2** | `summary.json` |
| `replay.fresh_model_calls` | **0** | `summary.json` |
| `tests.total` | **71** | `summary.json` |
| `tests.passed` | **67** | `summary.json` |
| `tests.failed` | **0** | `summary.json` |
| `tests.skipped` | **4** | `summary.json` |
| `manifest.cpu` | **Apple M5 Pro** | `manifest.json` |
| `manifest.ollama_version` | **0.30.11** | `manifest.json` |
| `manifest.mcp_sdk` | **2.2.0** | `manifest.json` |
| `E5.monolith.sigkills` | **3** | `summary.json → experiments` |
| `E6.monolith_probes_executed_writes` | **2** | `summary.json → experiments` |
| `run_id` | **2026-09-28-recorded** | `summary.json` |
| `verify.passed` | **36** | `runs/2026-09-28-recorded/verification.json` |
| `verify.total` | **36** | `runs/2026-09-28-recorded/verification.json` |
| `verify.recomputed` | **12** | `runs/2026-09-28-recorded/verification.json` |

## The checks

Source: `layered_architecture_poc/runs/2026-09-28-recorded/verification.json`. PASS: 36

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `1` |  | manifest exists | PASS |  |
| `2` |  | experiment plan hash matches the plan on disk | PASS |  |
| `3` |  | frozen inputs unchanged since the run (or changed only by a declared evidence revision) | PASS |  |
| `4` |  | declared revisions still match their files | PASS |  |
| `5` |  | summary.json exists | PASS |  |
| `6` |  | every preregistered scenario ran | PASS | [] |
| `7` |  | no replay tape misses | PASS |  |
| `8` |  | tests: zero failures | PASS | 67/71 |
| `9` |  | every scenario has score, process log, world ledger and model-call ledger | PASS |  |
| `10` |  | raw/model_calls.jsonl present and non-empty | PASS |  |
| `11` |  | raw/tool_calls.jsonl present and non-empty | PASS |  |
| `12` |  | raw/workflow_events.jsonl present and non-empty | PASS |  |
| `13` |  | raw/policy_events.jsonl present and non-empty | PASS |  |
| `14` |  | raw/checkpoints.jsonl present and non-empty | PASS |  |
| `15` |  | raw/traces.jsonl present and non-empty | PASS |  |
| `16` |  | raw/backend_executions.jsonl present and non-empty | PASS |  |
| `17` |  | E6 probe results present | PASS |  |
| `18` |  | diff for E2_model_swap-monolith | PASS |  |
| `19` |  | diff for E2_model_swap-layered | PASS |  |
| `20` |  | diff for E3_tool_v2-monolith | PASS |  |
| `21` |  | diff for E3_tool_v2-layered | PASS |  |
| `22` |  | diff for E9_dry_run-monolith | PASS |  |
| `23` |  | diff for E9_dry_run-layered | PASS |  |
| `24` |  | summary.json rebuilds identically from the run's files | PASS |  |
| `25` |  | every scenario has an outcome class | PASS | 32 scenario(s): ERROR 0, FAILURE 8, NOT_EXPOSED 1, SUCCESS 23 |
| `26` |  | E1 outcome checks recomputed from the world ledger | PASS | 6 E1 scenario(s): every outcome check agrees with the world database and the tapes |
| `27` |  | physical writes per operation id, from the backend ledger | PASS | E4 physical rollbacks per scenario: layered-s11 1 (keys 1, unkeyed 0, replays 1), layered- |
| `28` |  | no model call after the kill repeats work completed before it | PASS | 7 exposed scenario(s): E5-layered-s11 0→0 calls; E5-layered-s13 0→0 calls; E5-monolith-s11 |
| `29` |  | every executed write had a policy allow and an approval | PASS | 30 layered write(s), each with a policy decision; monolith writes with no authorization re |
| `30` |  | approval precedes every production write | PASS | 29 scenario(s) with a production rollback, each approved first |
| `31` |  | one workflow trace across the processes of a crash run | PASS | 3 of 3 exposed layered crash run(s) kept one workflow trace across their processes |
| `32` |  | change scope recomputed from the diffs and the concern map | PASS | E2 monolith 1 file(s) +2/-2; E2 layered 1 file(s) +6/-2; E3 monolith 2 file(s) +7/-6; E3 l |
| `33` |  | the dry-run change crosses layers through the contract module | PASS | 4 file(s): layered_platform/contracts.py, layered_platform/experience/cli.py, layered_plat |
| `34` |  | tests recounted from the JUnit file | PASS | 67 passed, 0 failed, 4 skipped, 71 cases |
| `35` |  | the replay's facts match the recorded run | PASS | 477 measured fact(s) identical under replay; timings, ids, the replay's own test pass and  |
| `36` |  | fault claims carry their exposure denominator | PASS | E5 layered: 2 of 3 planned reached the kill; E5 monolith: 3 of 3 planned reached the kill; |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # install the POC environment (Python 3.12, mcp 2.2.0); no model needed (make models checks Ollama)
make test    # every test except the live-model ones (no model needed)
make verify    # the published run's evidence verified in a throwaway copy of the POC: 36 checks, 12 recomputed from raw evidence
make replay    # the published run replayed from its model tape in a throwaway copy of the POC (no model, nothing written to the run)
make demo    # no single-scenario demo here: make replay replays the published run from its model tape
make docs    # the three publications as Markdown, standalone HTML and PDF, plus the claim/evidence matrix
make qa    # publication checks: no hand-typed number in a publication, and the figures agree with the run
```

*Built by `series-start-here/tools/series_edition.py results F2` from the files named above. It computes nothing new.*
