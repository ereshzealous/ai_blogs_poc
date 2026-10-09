# P1 · The Reference Architecture · Results

*How do all these boundaries fit into one production platform, and does the assembly hold?*

Production AI Engineering · P1 · Capstone

## The run

- **Published run:** `2026-10-04-proof` (declared in `production_agentic_ai_platform/evidence/published.json`)
- **How it ran:** proof run: real processes, simulated systems, recorded model calls
- **Numbers come from:** `docs/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. 14 of 14 verification sections pass. Source: `production_agentic_ai_platform/evidence/verification/verification.json`
- **Findings:** 19 claims: 13 supported, 4 limitation, 1 control, 1 implementation; check findings: 9 EXPECTED FAILURE. Source: `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/results.json`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `run_id` | **2026-10-04-proof** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → run_id` |
| `proof.experiments` | **14** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/results.json → check_counts.experiments` |
| `proof.checks` | **140** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/results.json → check_counts.checks` |
| `proof.pass` | **131** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/results.json → check_counts.pass` |
| `proof.expected_failure` | **9** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/results.json → check_counts.expected_failure` |
| `proof.fail` | **0** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/results.json → check_counts.fail` |
| `r2_user_perms` | **18** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R2.facts.layers.user` |
| `r2_effective` | **2** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R2.facts.effective` |
| `r5_denied` | **11** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R5.facts.cases` |
| `r5_cases` | **12** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R5.facts.cases` |
| `r1_cap_ttl_s` | **120** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R1.facts.cap_ttl_s` |
| `r6_cap` | **6** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R6.facts.error.cap` |
| `r13_questions` | **17** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R13.facts.questions` |
| `r11_after` | **prod-agent-platform@18** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R11.facts.bundle_after` |
| `r11_before` | **prod-agent-platform@17** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R11.facts.bundle_before` |
| `r1_model_calls` | **4** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R1.facts.model_calls` |
| `r10_naive_rollbacks` | **2** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R10.facts.naive.rollbacks` |
| `r2_user_rollback` | **6** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → R2.facts.user_rollback` |
| `replay.level` | **SEMANTIC** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/replay.json` |
| `replay_checks_compared` | **133** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/replay.json → groups.checks` |
| `neg_checks_failed` | **28** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/negative-control/raw/results.json → totals.failed` |
| `neg_checks` | **133** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/negative-control/raw/results.json → totals.checks` |
| `neg_experiments_failed` | **7** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/negative-control/raw/results.json → experiments[].status` |
| `neg_experiments_passed` | **6** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/negative-control/raw/results.json → totals.experiments_passed` |
| `run_date` | **2026-10-04** | `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/raw/results.json → finished_at` |

## The checks

Source: `production_agentic_ai_platform/evidence/runs/2026-10-04-proof/checks.jsonl`. PASS: 131, EXPECTED_FAILURE: 9

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `P1-R1-C01` | P1-R1 |  | PASS | PASS |
| `P1-R1-C02` | P1-R1 |  | PASS | PASS |
| `P1-R1-C03` | P1-R1 |  | PASS | PASS |
| `P1-R1-C04` | P1-R1 |  | PASS | PASS |
| `P1-R1-C05` | P1-R1 |  | PASS | PASS |
| `P1-R1-C06` | P1-R1 |  | PASS | PASS |
| `P1-R1-C07` | P1-R1 |  | PASS | PASS |
| `P1-R1-C08` | P1-R1 |  | PASS | PASS |
| `P1-R1-C09` | P1-R1 |  | PASS | PASS |
| `P1-R1-C10` | P1-R1 |  | PASS | PASS |
| `P1-R1-C11` | P1-R1 |  | PASS | PASS |
| `P1-R1-C12` | P1-R1 |  | PASS | PASS |
| `P1-R1-C13` | P1-R1 |  | PASS | PASS |
| `P1-R1-C14` | P1-R1 |  | PASS | PASS |
| `P1-R1-C15` | P1-R1 |  | PASS | PASS |
| `P1-R1-C16` | P1-R1 |  | PASS | PASS |
| `P1-R1-C17` | P1-R1 |  | PASS | PASS |
| `P1-R1-C18` | P1-R1 |  | PASS | PASS |
| `P1-R2-C01` | P1-R2 |  | PASS | PASS |
| `P1-R2-C02` | P1-R2 |  | PASS | PASS |
| `P1-R2-C03` | P1-R2 |  | PASS | PASS |
| `P1-R2-C04` | P1-R2 |  | PASS | PASS |
| `P1-R2-C05` | P1-R2 |  | PASS | PASS |
| `P1-R2-C06` | P1-R2 |  | PASS | PASS |
| `P1-R2-C07` | P1-R2 |  | PASS | PASS |
| `P1-R2-C08` | P1-R2 |  | PASS | PASS |
| `P1-R2-C09` | P1-R2 |  | PASS | PASS |
| `P1-R3-C01` | P1-R3 |  | PASS | PASS |
| `P1-R3-C02` | P1-R3 |  | PASS | PASS |
| `P1-R3-C03` | P1-R3 |  | PASS | PASS |
| `P1-R3-C04` | P1-R3 |  | PASS | PASS |
| `P1-R3-C05` | P1-R3 |  | PASS | PASS |
| `P1-R3-C06` | P1-R3 |  | PASS | PASS |
| `P1-R3-C07` | P1-R3 |  | PASS | PASS |
| `P1-R3-C08` | P1-R3 |  | PASS | PASS |
| `P1-R3-C09` | P1-R3 |  | PASS | PASS |
| `P1-R4-C01` | P1-R4 |  | PASS | PASS |
| `P1-R4-C02` | P1-R4 |  | PASS | PASS |
| `P1-R4-C03` | P1-R4 |  | PASS | PASS |
| `P1-R4-C04` | P1-R4 |  | PASS | PASS |
| `P1-R4-C05` | P1-R4 |  | PASS | PASS |
| `P1-R4-C06` | P1-R4 |  | PASS | PASS |
| `P1-R4-C07` | P1-R4 |  | PASS | PASS |
| `P1-R4-C08` | P1-R4 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `P1-R4-C09` | P1-R4 |  | PASS | PASS |
| `P1-R4-C10` | P1-R4 |  | PASS | PASS |
| `P1-R4-C11` | P1-R4 |  | PASS | PASS |
| `P1-R5-C01` | P1-R5 |  | PASS | PASS |
| `P1-R5-C02` | P1-R5 |  | PASS | PASS |
| `P1-R5-C03` | P1-R5 |  | PASS | PASS |
| `P1-R5-C04` | P1-R5 |  | PASS | PASS |
| `P1-R5-C05` | P1-R5 |  | PASS | PASS |
| `P1-R5-C06` | P1-R5 |  | PASS | PASS |
| `P1-R5-C07` | P1-R5 |  | PASS | PASS |
| `P1-R5-C08` | P1-R5 |  | PASS | PASS |
| `P1-R5-C09` | P1-R5 |  | PASS | PASS |
| `P1-R5-C13` | P1-R5 |  | PASS | PASS |
| `P1-R5-C14` | P1-R5 |  | PASS | PASS |
| `P1-R5-C10` | P1-R5 |  | PASS | PASS |
| `P1-R5-C11` | P1-R5 |  | PASS | PASS |
| `P1-R5-C12` | P1-R5 |  | PASS | PASS |
| `P1-R6-C01` | P1-R6 |  | PASS | PASS |
| `P1-R6-C02` | P1-R6 |  | PASS | PASS |
| `P1-R6-C03` | P1-R6 |  | PASS | PASS |
| `P1-R6-C04` | P1-R6 |  | PASS | PASS |
| `P1-R6-C05` | P1-R6 |  | PASS | PASS |
| `P1-R6-C06` | P1-R6 |  | PASS | PASS |
| `P1-R6-C07` | P1-R6 |  | PASS | PASS |
| `P1-R7-C01` | P1-R7 |  | PASS | PASS |
| `P1-R7-C02` | P1-R7 |  | PASS | PASS |
| `P1-R7-C03` | P1-R7 |  | PASS | PASS |
| `P1-R7-C04` | P1-R7 |  | PASS | PASS |
| `P1-R7-C05` | P1-R7 |  | PASS | PASS |
| `P1-R7-C06` | P1-R7 |  | PASS | PASS |
| `P1-R7-C07` | P1-R7 |  | PASS | PASS |
| `P1-R7-C08` | P1-R7 |  | PASS | PASS |
| `P1-R8-C01` | P1-R8 |  | PASS | PASS |
| `P1-R8-C02` | P1-R8 |  | PASS | PASS |
| `P1-R8-C03` | P1-R8 |  | PASS | PASS |
| `P1-R8-C04` | P1-R8 |  | PASS | PASS |
| `P1-R8-C05` | P1-R8 |  | PASS | PASS |
| `P1-R8-C06` | P1-R8 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `P1-R8-C07` | P1-R8 |  | PASS | PASS |
| `P1-R8-C08` | P1-R8 |  | PASS | PASS |
| `P1-R8-C09` | P1-R8 |  | PASS | PASS |
| `P1-R9-C01` | P1-R9 |  | PASS | PASS |
| `P1-R9-C02` | P1-R9 |  | PASS | PASS |
| `P1-R9-C03` | P1-R9 |  | PASS | PASS |
| `P1-R9-C04` | P1-R9 |  | PASS | PASS |
| `P1-R9-C05` | P1-R9 |  | PASS | PASS |
| `P1-R9-C06` | P1-R9 |  | PASS | PASS |
| `P1-R9-C07` | P1-R9 |  | PASS | PASS |
| `P1-R9-C09` | P1-R9 |  | PASS | PASS |
| `P1-R9-C08` | P1-R9 |  | PASS | PASS |
| `P1-R10-C01` | P1-R10 |  | PASS | PASS |
| `P1-R10-C02` | P1-R10 |  | PASS | PASS |
| `P1-R10-C03` | P1-R10 |  | PASS | PASS |
| `P1-R10-C04` | P1-R10 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `P1-R10-C05` | P1-R10 |  | PASS | PASS |
| `P1-R11-C01` | P1-R11 |  | PASS | PASS |
| `P1-R11-C02` | P1-R11 |  | PASS | PASS |
| `P1-R11-C03` | P1-R11 |  | PASS | PASS |
| `P1-R11-C04` | P1-R11 |  | PASS | PASS |
| `P1-R11-C05` | P1-R11 |  | PASS | PASS |
| `P1-R11-C06` | P1-R11 |  | PASS | PASS |
| `P1-R11-C07` | P1-R11 |  | PASS | PASS |
| `P1-R12-C01` | P1-R12 |  | PASS | PASS |
| `P1-R12-C02` | P1-R12 |  | PASS | PASS |
| `P1-R12-C03` | P1-R12 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `P1-R12-C04` | P1-R12 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `P1-R12-C05` | P1-R12 |  | PASS | PASS |
| `P1-R12-C06` | P1-R12 |  | PASS | PASS |
| `P1-R13-C01` | P1-R13 |  | PASS | PASS |
| `P1-R13-C02` | P1-R13 |  | PASS | PASS |
| `P1-R13-C03` | P1-R13 |  | PASS | PASS |
| `P1-R13-C04` | P1-R13 |  | PASS | PASS |
| `P1-R13-C05` | P1-R13 |  | PASS | PASS |
| `P1-R13-C06` | P1-R13 |  | PASS | PASS |
| `P1-R13-C07` | P1-R13 |  | PASS | PASS |
| `P1-R13-C08` | P1-R13 |  | PASS | PASS |
| `P1-R13-C09` | P1-R13 |  | PASS | PASS |
| `P1-R13-C10` | P1-R13 |  | PASS | PASS |
| `P1-R13-C11` | P1-R13 |  | PASS | PASS |
| `P1-R13-C12` | P1-R13 |  | PASS | PASS |
| `P1-R13-C13` | P1-R13 |  | PASS | PASS |
| `P1-R13-C14` | P1-R13 |  | PASS | PASS |
| `P1-R13-C15` | P1-R13 |  | PASS | PASS |
| `P1-R13-C16` | P1-R13 |  | PASS | PASS |
| `P1-R13-C17` | P1-R13 |  | PASS | PASS |
| `P1-R13-C18` | P1-R13 |  | PASS | PASS |
| `P1-R13-C19` | P1-R13 |  | PASS | PASS |
| `P1-R13-C20` | P1-R13 |  | PASS | PASS |
| `P1-R13-C21` | P1-R13 |  | PASS | PASS |
| `P1-R14-C01` | P1-R14 |  | PASS | PASS |
| `P1-R14-C02` | P1-R14 |  | PASS | PASS |
| `P1-R14-C03` | P1-R14 |  | PASS | PASS |
| `P1-R14-C04` | P1-R14 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `P1-R14-C05` | P1-R14 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `P1-R14-C06` | P1-R14 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `P1-R14-C07` | P1-R14 |  | EXPECTED_FAILURE | EXPECTED FAILURE |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python 3.12, mcp 2.2.0, OpenTelemetry SDK, pyyaml, pytest)
make test    # the unit tests (implementation tests, not proof checks)
make verify    # PROOF VERIFICATION of the published run, the README, the Lab and both articles -> POC evidence/verification/
make replay    # replay the published run into scratch (evidence/local/) and classify it against the recorded run
make demo    # no single-scenario demo here: make replay replays the published run into scratch
make docs    # both editions as Markdown, standalone HTML and PDF, and the Medium image pack
make qa    # rendered checks at desktop/tablet/mobile + screenshots -> qa/
```

*Built by `series-start-here/tools/series_edition.py results P1` from the files named above. It computes nothing new.*
