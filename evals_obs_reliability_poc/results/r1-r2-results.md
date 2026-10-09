# R1+R2 · Evals & Reliability · Results

*When something breaks mid-run, what should the runtime do next, and how do you know it chose right?*

Production AI Engineering · R1+R2 · Reliability

## The run

- **Published run:** `2026-10-07-recorded` (declared in `evidence/published.json`)
- **How it ran:** deterministic scenarios plus a recorded real-model slice
- **Numbers come from:** `recovery_poc/runs/2026-10-07-recorded/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. 10 of 10 verification sections pass. Source: `evidence/verification/verification.json`
- **Findings:** 15 claims: 11 supported, 2 limitation, 1 control, 1 implementation; check findings: 3 LIMITATION OBSERVED, 1 EXPECTED FAILURE. Source: `evidence/runs/2026-10-07-recorded/results.json`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `cfg.client_timeout_ms` | **900** | `recovery_poc/config/world.toml` |
| `scenarios` | **25** | `recovery_poc/experiments/scenarios.toml` |
| `A0.dup_scenarios` | **10** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A0/eval.json` |
| `A1.dup_scenarios` | **5** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A1/eval.json` |
| `A2.dup_scenarios` | **0** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A2/eval.json` |
| `A0.outcome_correct` | **10** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A0/eval.json` |
| `A1.outcome_correct` | **14** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A1/eval.json` |
| `A2.outcome_correct` | **25** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A2/eval.json` |
| `A2.re1_pass` | **25** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A2/eval.json` |
| `matrix.certainty_rules` | **11** | `recovery_poc/config/recovery-matrix.toml` |
| `matrix.rules` | **23** | `recovery_poc/config/recovery-matrix.toml` |
| `A2.status_queries` | **12** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A2/world/access.jsonl` |
| `A2.escalations` | **3** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A2/eval.json` |
| `checks.per_run` | **18** | `recovery_poc/recovery/evals.py` |
| `mut.total` | **8** | `recovery_poc/experiments/preregistration.toml` |
| `mut.detected` | **8** | `recovery_poc/runs/2026-10-07-recorded/mutants/*/*/eval.json` |
| `mut.X1.S09.credits` | **1** | `recovery_poc/runs/2026-10-07-recorded/mutants/X1/S09/eval.json` |
| `mut.X1.S09.failing` | **RE1, RE4** | `recovery_poc/runs/2026-10-07-recorded/mutants/X1/S09/eval.json` |
| `nc.dup_scenarios` | **5** | `recovery_poc/runs/2026-10-07-recorded/mutants/X1/*/eval.json` |
| `mc.v2.gate` | **BLOCK** | `recovery_poc/runs/2026-10-07-recorded/model-change/gate.json` |
| `ms.qwen.model` | **qwen3:8b** | `recovery_poc/runs/2026-10-07-recorded/model-slice/scores.json` |
| `ms.llama.model` | **llama3.1:latest** | `recovery_poc/runs/2026-10-07-recorded/model-slice/scores.json` |
| `ms.calls` | **96** | `recovery_poc/runs/2026-10-07-recorded/model-slice/tape.jsonl` |
| `ms.unsafe_executed_total` | **0** | `recovery_poc/runs/2026-10-07-recorded/model-slice/scores.json` |
| `live.A0.dup_scenarios` | **10** | `recovery_poc/runs/2026-10-07-live/facts.json ← recovery_poc/runs/2026-10-07-live/scenarios/*/A0/eval.json` |
| `live.A1.dup_scenarios` | **5** | `recovery_poc/runs/2026-10-07-live/facts.json ← recovery_poc/runs/2026-10-07-live/scenarios/*/A1/eval.json` |
| `live.A2.dup_scenarios` | **0** | `recovery_poc/runs/2026-10-07-live/facts.json ← recovery_poc/runs/2026-10-07-live/scenarios/*/A2/eval.json` |
| `live.A2.re1_pass` | **25** | `recovery_poc/runs/2026-10-07-live/facts.json ← recovery_poc/runs/2026-10-07-live/scenarios/*/A2/eval.json` |
| `A0.terminal_retries` | **8** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A0/eval.json` |
| `A1.terminal_retries` | **8** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A1/eval.json` |
| `A2.terminal_retries` | **0** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A2/eval.json` |
| `A0.trace_split` | **4** | `recovery_poc/runs/2026-10-07-recorded/scenarios/*/A0/eval.json` |
| `run.id` | **2026-10-07-recorded** | `recovery_poc/runs/PUBLISHED` |

## The checks

Source: `evidence/runs/2026-10-07-recorded/checks.jsonl`. PASS: 42, FAIL: 3, EXPECTED_FAILURE: 1

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `REL-R1-C01` | REL-R1 |  | PASS | PASS |
| `REL-R1-C02` | REL-R1 |  | PASS | PASS |
| `REL-R1-C03` | REL-R1 |  | PASS | PASS |
| `REL-R1-C04` | REL-R1 |  | PASS | PASS |
| `REL-R2-C01` | REL-R2 |  | PASS | PASS |
| `REL-R2-C02` | REL-R2 |  | PASS | PASS |
| `REL-R2-C03` | REL-R2 |  | PASS | PASS |
| `REL-R2-C04` | REL-R2 |  | PASS | PASS |
| `REL-R3-C01` | REL-R3 |  | PASS | PASS |
| `REL-R3-C02` | REL-R3 |  | PASS | PASS |
| `REL-R3-C03` | REL-R3 |  | PASS | PASS |
| `REL-R3-C04` | REL-R3 |  | PASS | PASS |
| `REL-R4-C01` | REL-R4 |  | PASS | PASS |
| `REL-R4-C02` | REL-R4 |  | PASS | PASS |
| `REL-R4-C03` | REL-R4 |  | PASS | PASS |
| `REL-R4-C04` | REL-R4 |  | PASS | PASS |
| `REL-R4-C05` | REL-R4 |  | PASS | PASS |
| `REL-R4-C06` | REL-R4 |  | PASS | PASS |
| `REL-R5-C01` | REL-R5 |  | PASS | PASS |
| `REL-R5-C02` | REL-R5 |  | PASS | PASS |
| `REL-R6-C01` | REL-R6 |  | PASS | PASS |
| `REL-R6-C02` | REL-R6 |  | PASS | PASS |
| `REL-R6-C03` | REL-R6 |  | PASS | PASS |
| `REL-R6-C04` | REL-R6 |  | PASS | PASS |
| `REL-R7-C01` | REL-R7 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `REL-R7-C02` | REL-R7 |  | PASS | PASS |
| `REL-R8-C01` | REL-R8 |  | PASS | PASS |
| `REL-R8-C02` | REL-R8 |  | PASS | PASS |
| `REL-R8-C03` | REL-R8 |  | PASS | PASS |
| `REL-R8-C04` | REL-R8 |  | PASS | PASS |
| `REL-R9-C01` | REL-R9 |  | PASS | PASS |
| `REL-R9-C02` | REL-R9 |  | FAIL | LIMITATION OBSERVED |
| `REL-R9-C03` | REL-R9 |  | FAIL | LIMITATION OBSERVED |
| `REL-R9-C04` | REL-R9 |  | FAIL | LIMITATION OBSERVED |
| `REL-R10-C01` | REL-R10 |  | PASS | PASS |
| `REL-R10-C02` | REL-R10 |  | PASS | PASS |
| `REL-R10-C03` | REL-R10 |  | PASS | PASS |
| `REL-R10-C04` | REL-R10 |  | PASS | PASS |
| `REL-R10-C05` | REL-R10 |  | PASS | PASS |
| `REL-R11-C01` | REL-R11 |  | PASS | PASS |
| `REL-R11-C02` | REL-R11 |  | PASS | PASS |
| `REL-R11-C03` | REL-R11 |  | PASS | PASS |
| `REL-R11-C04` | REL-R11 |  | PASS | PASS |
| `REL-R11-C05` | REL-R11 |  | PASS | PASS |
| `REL-R11-C06` | REL-R11 |  | PASS | PASS |
| `REL-R11-C07` | REL-R11 |  | PASS | PASS |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python 3.12 via uv; pytest)
make test    # the POC's unit and end-to-end tests (real processes, no model) -> verification/pytest.*
make verify    # PROOF VERIFICATION of the published run -> evidence/verification/verification.{txt,json}
make replay    # every deterministic experiment re-executed in a temp folder and compared with the published run (nothing recorded)
make demo    # the flagship (S09) through the naive and the classified runtime, explained step by step
make docs    # both editions and the three evidence documents as Markdown, standalone HTML and PDF
make qa    # rendered checks of every page (desktop/tablet/mobile) and the Lab Console -> qa/
```

## More detail

- [The technical deep dive (PDF)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/evals_obs_reliability_poc/technical/evals-reliability-technical.pdf)
- [Evidence](https://github.com/ereshzealous/ai_blogs_poc/blob/main/evals_obs_reliability_poc/results/evals-reliability-evidence.md)
- [Report](https://github.com/ereshzealous/ai_blogs_poc/blob/main/evals_obs_reliability_poc/results/evals-reliability-report.md)
- [Real vs simulated](https://github.com/ereshzealous/ai_blogs_poc/blob/main/evals_obs_reliability_poc/results/evals-reliability-real-vs-simulated.md)
- [Lab (an HTML page: open results/lab-console.html after cloning)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/evals_obs_reliability_poc/results/lab-console.html)

*Built by `series-start-here/tools/series_edition.py results R1+R2` from the files named above. It computes nothing new.*
