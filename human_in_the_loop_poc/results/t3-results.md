# T3 · Human-in-the-Loop · Results

*What exactly did the human approve, and is that approval still valid now?*

Production AI Engineering · T3 · Trust & Security

## The run

- **Published run:** `2026-10-03-protocol` (declared in `hitl_poc/evidence/published.json`)
- **How it ran:** deterministic: no model, no network
- **Numbers come from:** `hitl_poc/evidence/runs/2026-10-03-protocol/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. 10 of 10 verification sections pass. Source: `hitl_poc/evidence/verification/verification.json`
- **Findings:** 21 claims: 10 supported, 9 limitation, 1 control, 1 implementation; check findings: 9 EXPECTED FAILURE. Source: `hitl_poc/evidence/runs/2026-10-03-protocol/results.json`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `story.approval_wait_minutes` | **37** | `evidence/runs/2026-10-03-protocol/story.json#approval_wait_minutes` |
| `design.scenarios` | **30** | `proof/preregistration.toml#experiments.scenarios` |
| `design.global_assertions` | **8** | `proof/preregistration.toml#global` |
| `design.scenario_runs` | **90** | `evidence/runs/2026-10-03-protocol/experiments.json` |
| `global.A.mutated_action_bypasses` | **4** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.A.global.mutated_action_bypasses` |
| `global.C.mutated_action_bypasses` | **0** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.C.global.mutated_action_bypasses` |
| `H2.C.reapproval_requests` | **3** | `evidence/runs/2026-10-03-protocol/raw/scenarios/ → H2*/C metrics.reapproval_requests (summed)` |
| `H1b.A.writes` | **0** | `evidence/runs/2026-10-03-protocol/raw/scenarios/H1b/A/scenario.json → metrics.writes` |
| `global.A.successful_approval_replays` | **3** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.A.global.successful_approval_replays` |
| `global.C.successful_approval_replays` | **0** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.C.global.successful_approval_replays` |
| `global.A.ineligible_approver_acceptances` | **4** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.A.global.ineligible_approver_acceptances` |
| `global.C.ineligible_approver_acceptances` | **0** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.C.global.ineligible_approver_acceptances` |
| `design.request_ttl_min` | **60** | `proof/preregistration.toml#design.request_ttl_min` |
| `global.B.silent_stale_context_resumes` | **7** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.B.global.silent_stale_context_resumes` |
| `global.C.silent_stale_context_resumes` | **0** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.C.global.silent_stale_context_resumes` |
| `story.failed_checks` | **2** | `evidence/runs/2026-10-03-protocol/story.json#revalidation` |
| `story.checks` | **9** | `evidence/runs/2026-10-03-protocol/story.json#revalidation` |
| `story.C.final_code` | **DELEGATION_REVOKED** | `evidence/runs/2026-10-03-protocol/story.json#outcome.C.code` |
| `global.A.duplicate_external_side_effects` | **4** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.A.global.duplicate_external_side_effects` |
| `global.B.duplicate_external_side_effects` | **2** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.B.global.duplicate_external_side_effects` |
| `global.C.duplicate_external_side_effects` | **0** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.C.global.duplicate_external_side_effects` |
| `global.A.executions_after_deny_or_timeout` | **0** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.A.global.executions_after_deny_or_timeout` |
| `global.A.expired_approval_executions` | **2** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.A.global.expired_approval_executions` |
| `H8.C.escalations_recorded` | **1** | `evidence/runs/2026-10-03-protocol/raw/scenarios/ → H8*/C metrics.escalations_recorded (summed)` |
| `global.C.unauthorized_executions` | **0** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.C.global.unauthorized_executions` |
| `global.B.unauthorized_executions` | **9** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.B.global.unauthorized_executions` |
| `global.A.unauthorized_executions` | **26** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.A.global.unauthorized_executions` |
| `global.C.legit_executions` | **10** | `evidence/runs/2026-10-03-protocol/experiments.json → arms.C.global.legit_executions` |
| `checks.total` | **79** | `evidence/runs/2026-10-03-protocol/checks.jsonl` |
| `checks.pass` | **70** | `evidence/runs/2026-10-03-protocol/checks.jsonl` |
| `checks.expected_failure` | **9** | `evidence/runs/2026-10-03-protocol/checks.jsonl` |
| `checks.fail` | **0** | `evidence/runs/2026-10-03-protocol/checks.jsonl` |
| `H9a.C.questions_answered` | **16** | `evidence/runs/2026-10-03-protocol/raw/scenarios/H9a/C/scenario.json → metrics.questions_answered` |
| `design.questions` | **16** | `hitl/scenarios.py QUESTIONS` |
| `H9a.B.questions_answered` | **15** | `evidence/runs/2026-10-03-protocol/raw/scenarios/H9a/B/scenario.json → metrics.questions_answered` |
| `H9a.A.questions_answered` | **10** | `evidence/runs/2026-10-03-protocol/raw/scenarios/H9a/A/scenario.json → metrics.questions_answered` |

## The checks

Source: `hitl_poc/evidence/runs/2026-10-03-protocol/checks.jsonl`. PASS: 70, EXPECTED_FAILURE: 9

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `T3-R1-C01` | T3-R1 |  | PASS | PASS |
| `T3-R1-C02` | T3-R1 |  | PASS | PASS |
| `T3-R1-C03` | T3-R1 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T3-R1-C04` | T3-R1 |  | PASS | PASS |
| `T3-R2-C01` | T3-R2 |  | PASS | PASS |
| `T3-R2-C02` | T3-R2 |  | PASS | PASS |
| `T3-R2-C03` | T3-R2 |  | PASS | PASS |
| `T3-R2-C04` | T3-R2 |  | PASS | PASS |
| `T3-R2-C05` | T3-R2 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T3-R3-C01` | T3-R3 |  | PASS | PASS |
| `T3-R3-C02` | T3-R3 |  | PASS | PASS |
| `T3-R3-C03` | T3-R3 |  | PASS | PASS |
| `T3-R3-C04` | T3-R3 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T3-R4-C01` | T3-R4 |  | PASS | PASS |
| `T3-R4-C02` | T3-R4 |  | PASS | PASS |
| `T3-R4-C03` | T3-R4 |  | PASS | PASS |
| `T3-R4-C04` | T3-R4 |  | PASS | PASS |
| `T3-R4-C05` | T3-R4 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T3-R5-C01` | T3-R5 |  | PASS | PASS |
| `T3-R5-C02` | T3-R5 |  | PASS | PASS |
| `T3-R5-C03` | T3-R5 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T3-R6-C01` | T3-R6 |  | PASS | PASS |
| `T3-R6-C02` | T3-R6 |  | PASS | PASS |
| `T3-R6-C03` | T3-R6 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T3-R7-C01` | T3-R7 |  | PASS | PASS |
| `T3-R7-C02` | T3-R7 |  | PASS | PASS |
| `T3-R7-C03` | T3-R7 |  | PASS | PASS |
| `T3-R7-C04` | T3-R7 |  | PASS | PASS |
| `T3-R7-C05` | T3-R7 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T3-R8-C01` | T3-R8 |  | PASS | PASS |
| `T3-R8-C02` | T3-R8 |  | PASS | PASS |
| `T3-R8-C03` | T3-R8 |  | PASS | PASS |
| `T3-R8-C04` | T3-R8 |  | PASS | PASS |
| `T3-R8-C05` | T3-R8 |  | PASS | PASS |
| `T3-R8-C06` | T3-R8 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T3-R9-C01` | T3-R9 |  | PASS | PASS |
| `T3-R9-C02` | T3-R9 |  | PASS | PASS |
| `T3-R9-C03` | T3-R9 |  | PASS | PASS |
| `T3-R9-C04` | T3-R9 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T3-R10-C01` | T3-R10 |  | PASS | PASS |
| `T3-R10-C02` | T3-R10 |  | PASS | PASS |
| `T3-R10-C03` | T3-R10 |  | PASS | PASS |
| `T3-R10-C04` | T3-R10 |  | PASS | PASS |
| `T3-R10-C05` | T3-R10 |  | PASS | PASS |
| `T3-R10-C06` | T3-R10 |  | PASS | PASS |
| `T3-R10-C07` | T3-R10 |  | PASS | PASS |
| `T3-R10-C08` | T3-R10 |  | PASS | PASS |
| `T3-R11-C01` | T3-R11 |  | PASS | PASS |
| `T3-R11-C02` | T3-R11 |  | PASS | PASS |
| `T3-R11-C03` | T3-R11 |  | PASS | PASS |
| `T3-R11-C04` | T3-R11 |  | PASS | PASS |
| `T3-R11-C05` | T3-R11 |  | PASS | PASS |
| `T3-R11-C06` | T3-R11 |  | PASS | PASS |
| `T3-R11-C07` | T3-R11 |  | PASS | PASS |
| `T3-R11-C08` | T3-R11 |  | PASS | PASS |
| `T3-R11-C09` | T3-R11 |  | PASS | PASS |
| `T3-R11-C10` | T3-R11 |  | PASS | PASS |
| `T3-R11-C11` | T3-R11 |  | PASS | PASS |
| `T3-R11-C12` | T3-R11 |  | PASS | PASS |
| `T3-R11-C13` | T3-R11 |  | PASS | PASS |
| `T3-R11-C14` | T3-R11 |  | PASS | PASS |
| `T3-R11-C15` | T3-R11 |  | PASS | PASS |
| `T3-R11-C16` | T3-R11 |  | PASS | PASS |
| `T3-R11-C17` | T3-R11 |  | PASS | PASS |
| `T3-R11-C18` | T3-R11 |  | PASS | PASS |
| `T3-R11-C19` | T3-R11 |  | PASS | PASS |
| `T3-R11-C20` | T3-R11 |  | PASS | PASS |
| `T3-R11-C21` | T3-R11 |  | PASS | PASS |
| `T3-R11-C22` | T3-R11 |  | PASS | PASS |
| `T3-R11-C23` | T3-R11 |  | PASS | PASS |
| `T3-R11-C24` | T3-R11 |  | PASS | PASS |
| `T3-R11-C25` | T3-R11 |  | PASS | PASS |
| `T3-R11-C26` | T3-R11 |  | PASS | PASS |
| `T3-R11-C27` | T3-R11 |  | PASS | PASS |
| `T3-R11-C28` | T3-R11 |  | PASS | PASS |
| `T3-R11-C29` | T3-R11 |  | PASS | PASS |
| `T3-R11-C30` | T3-R11 |  | PASS | PASS |
| `T3-R12-C01` | T3-R12 |  | PASS | PASS |
| `T3-R12-C02` | T3-R12 |  | PASS | PASS |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python 3.12, pydantic, pyyaml, pytest)
make test    # pytest: the conformance suite (30 tests) + the implementation tests
make verify    # PROOF VERIFICATION of the published run (pae-proof/v1)
make replay    # the published run replayed in a temp folder, as part of PROOF VERIFICATION (writes only the verification report)
make demo    # the incident end to end
make docs    # both editions and the three results documents as Markdown, standalone HTML and PDF
make qa    # rendered checks at desktop/tablet/mobile + screenshots -> qa/
```

*Built by `series-start-here/tools/series_edition.py results T3` from the files named above. It computes nothing new.*
