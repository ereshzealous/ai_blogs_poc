# T5 · Observability & Governance · Results

*Can you prove what an agent did, and on whose authority?*

Production AI Engineering · T5 · Trust & Security

## The run

- **Published run:** `2026-09-30-recorded` (declared in `observability_governance_poc/runs/PUBLISHED`)
- **How it ran:** recorded with a live local model
- **Numbers come from:** `observability_governance_poc/runs/2026-09-30-recorded/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. 15 of 15 scenario evidence chains intact; replay all identical: True. Source: `observability_governance_poc/runs/2026-09-30-recorded/evidence/evidence-verification.json, reports/replay-comparison.json`
- **Findings:** 7 of 7 preregistered predictions held; 68 of 68 expectations held. Source: `observability_governance_poc/runs/2026-09-30-recorded/reports/predictions.json`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `e01_rev_before` | **184** | `scenarios/e01-success/evidence/audit-events.jsonl` |
| `e01_rev_after` | **185** | `scenarios/e01-success/evidence/audit-events.jsonl` |
| `scenarios` | **15** | `reports/results.json` |
| `experiments` | **12** | `experiments/preregistration.toml` |
| `L0_correct_total` | **149** | `reports/comparison.json` |
| `answers_per_layer` | **195** | `reports/comparison.json` |
| `L1_correct_total` | **149** | `reports/comparison.json` |
| `L0_heuristic_joins_total` | **15** | `reports/comparison.json` |
| `L1_heuristic_joins_total` | **0** | `reports/comparison.json` |
| `L2_correct_total` | **195** | `reports/comparison.json` |
| `e12a_exec_id` | **exec-106b857f** | `scenarios/e12a-lost-response/evidence/audit-events.jsonl` |
| `e12a_action_id` | **act-7b7550b9** | `scenarios/e12a-lost-response/evidence/audit-events.jsonl` |
| `e12a_txn` | **dtx-886a012833** | `scenarios/e12a-lost-response/evidence/audit-events.jsonl` |
| `e11_claimed_status` | **ROLLED_BACK** | `scenarios/e11-false-success/evidence/audit-events.jsonl` |
| `e11_ver_after` | **v4.18.0** | `scenarios/e11-false-success/evidence/audit-events.jsonl` |
| `e11_rev_after` | **184** | `scenarios/e11-false-success/evidence/audit-events.jsonl` |
| `e12a_timeout_ms` | **1503** | `scenarios/e12a-lost-response/evidence/audit-events.jsonl` |
| `e12a_requests_reaching_api` | **2** | `scenarios/e12a-lost-response/world/external-transactions.json` |
| `e12a_mutations` | **1** | `scenarios/e12a-lost-response/truth.json` |
| `e12b_mutations` | **2** | `scenarios/e12b-lost-response-no-key/truth.json` |
| `e12b_rev_before` | **184** | `scenarios/e12b-lost-response-no-key/evidence/audit-events.jsonl` |
| `e12b_rev_after` | **186** | `scenarios/e12b-lost-response-no-key/evidence/audit-events.jsonl` |
| `e12b_ver_after` | **v4.17.2** | `scenarios/e12b-lost-response-no-key/evidence/audit-events.jsonl` |
| `e05b_attempts` | **1** | `scenarios/e05b-crash-after-dispatch/truth.json` |
| `e05b_mutations` | **1** | `scenarios/e05b-crash-after-dispatch/truth.json` |
| `orphan_spans_total` | **13** | `reports/telemetry.json` |
| `metric_dumps_lost` | **2** | `reports/telemetry.json` |
| `sampled_10pct` | **1** | `reports/telemetry.json` |
| `canary_hits` | **0** | `reports/telemetry.json` |
| `files_scanned` | **225** | `reports/telemetry.json` |
| `e01_model` | **qwen3:8b** | `scenarios/e01-success/evidence/audit-events.jsonl` |
| `e01_prompt_template` | **incident-remediation@17** | `scenarios/e01-success/evidence/audit-events.jsonl` |
| `e01_agent_config` | **incident-agent-prod@8** | `scenarios/e01-success/evidence/audit-events.jsonl` |
| `e12a_rev_before` | **184** | `scenarios/e12a-lost-response/evidence/audit-events.jsonl` |
| `e12a_rev_after` | **185** | `scenarios/e12a-lost-response/evidence/audit-events.jsonl` |
| `x.replay.answers` | **60** | `observability_governance_poc/runs/2026-09-30-recorded/reports/replay-comparison.json` |
| `x.replay.misses` | **0** | `observability_governance_poc/runs/2026-09-30-recorded/reports/replay-comparison.json` |
| `x.run.id` | **2026-09-30-recorded** | `observability_governance_poc/runs/2026-09-30-recorded/manifest.json` |

## The checks

Source: `observability_governance_poc/runs/2026-09-30-recorded/checks.json`. PASS: 7

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `C1` |  | every scenario ran to completion (no ERROR outcome, no process that exited abnormally other than SIGKILL) | PASS |  |
| `C2` |  | every scenario's evidence chain and anchors verify | PASS |  |
| `C3` |  | tampering T1–T3 is detected | PASS |  |
| `C4` |  | the restricted-data canary appears in no model request, log, span or evidence event | PASS |  |
| `C5` |  | the deploy-api credential appears in no log, span, tape or evidence event | PASS |  |
| `C6` |  | no metric attribute carries an execution, action, attempt or trace id | PASS |  |
| `C7` |  | every scenario has exactly one target execution in its evidence | PASS |  |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python 3.12, OpenTelemetry SDK, pytest)
make test    # POC tests with the model unreachable (unit, real processes, end-to-end scenarios) -> results/tests.json
make verify    # recompute every evidence chain of the published run and check it against the witness anchors
make replay    # every published scenario rerun from the tapes in a throwaway copy of the POC (no model) and compared with the published run
make demo    # the flagship lost-response scenario from the published tape, then its evidence, event by event
make docs    # both editions and the three evidence documents (run report, evidence check, real vs simulated) as Markdown, standalone HTML and PDF
make qa    # rendered checks at desktop/tablet/mobile + screenshots -> qa/
```

## More detail

- [The technical deep dive (PDF)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/governance_for_ai_agents_poc/technical/observability-governance-technical.pdf)
- [Evidence](https://github.com/ereshzealous/ai_blogs_poc/blob/main/governance_for_ai_agents_poc/results/observability-governance-evidence.md)
- [Report](https://github.com/ereshzealous/ai_blogs_poc/blob/main/governance_for_ai_agents_poc/results/observability-governance-report.md)
- [Real vs simulated](https://github.com/ereshzealous/ai_blogs_poc/blob/main/governance_for_ai_agents_poc/results/observability-governance-real-vs-simulated.md)
- [Lab (an HTML page: open results/lab-console.html after cloning)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/governance_for_ai_agents_poc/results/lab-console.html)

*Built by `series-start-here/tools/series_edition.py results T5` from the files named above. It computes nothing new.*
