# Run 2026-09-30-recorded-replay

15 scenarios (12 experiments), each with a concurrent background execution, observed three ways from the same run.

## Reconstruction (13 questions per scenario)

| layer | correct | scenarios fully answered | wrong | partial | not recorded | key joins | heuristic joins |
|---|---|---|---|---|---|---|---|
| L0 · Application logs | 149/195 | 0/15 | 1 | 30 | 15 | 60 | 15 |
| L1 · Logs + traces | 149/195 | 0/15 | 1 | 30 | 15 | 75 | 0 |
| L2 · Execution lineage | 195/195 | 15/15 | 0 | 0 | 0 | 25 | 0 |

## Scenarios

| scenario | group | outcome | production changes | attempts reaching the API | agent processes | evidence events | L0 | L1 | L2 |
|---|---|---|---|---|---|---|---|---|---|
| e01-success | happy path | MITIGATED | 1 | 1 | 1 | 27 | 10/13 | 10/13 | 13/13 |
| e02-tool-failure | runtime failures | FAILED_NO_EFFECT | 0 | 3 | 1 | 31 | 10/13 | 10/13 | 13/13 |
| e03-policy-denial | governance failures | DENIED | 0 | 0 | 1 | 20 | 10/13 | 10/13 | 13/13 |
| e04-human-rejection | governance failures | REJECTED | 0 | 0 | 1 | 22 | 10/13 | 10/13 | 13/13 |
| e05a-crash-awaiting-approval | runtime failures | MITIGATED | 1 | 1 | 2 | 28 | 10/13 | 10/13 | 13/13 |
| e05b-crash-after-dispatch | runtime failures | MITIGATED | 1 | 1 | 2 | 28 | 10/13 | 10/13 | 13/13 |
| e06-duplicate-delivery | side-effect ambiguity | MITIGATED | 1 | 2 | 1 | 29 | 10/13 | 10/13 | 13/13 |
| e07-unexpected-capability | governance failures | DENIED | 0 | 0 | 1 | 21 | 10/13 | 10/13 | 13/13 |
| e08a-policy-v41 | version drift | MITIGATED | 1 | 1 | 1 | 26 | 10/13 | 10/13 | 13/13 |
| e08b-policy-v42 | version drift | MITIGATED | 1 | 1 | 1 | 27 | 10/13 | 10/13 | 13/13 |
| e09-config-v9 | version drift | MITIGATED | 1 | 1 | 1 | 27 | 10/13 | 10/13 | 13/13 |
| e10-restricted-data | governance failures | MITIGATED | 1 | 1 | 1 | 28 | 10/13 | 10/13 | 13/13 |
| e11-false-success | side-effect ambiguity | EFFECT_NOT_OBSERVED | 0 | 1 | 1 | 27 | 9/13 | 9/13 | 13/13 |
| e12a-lost-response | side-effect ambiguity | MITIGATED | 1 | 2 | 1 | 29 | 10/13 | 10/13 | 13/13 |
| e12b-lost-response-no-key | side-effect ambiguity | MITIGATED | 2 | 2 | 1 | 29 | 10/13 | 10/13 | 13/13 |

## Checks

- PASS C1: every scenario ran to completion (no ERROR outcome, no process that exited abnormally other than SIGKILL)
- PASS C2: every scenario's evidence chain and anchors verify
- PASS C3: tampering T1–T3 is detected
- PASS C4: the restricted-data canary appears in no model request, log, span or evidence event
- PASS C5: the deploy-api credential appears in no log, span, tape or evidence event
- PASS C6: no metric attribute carries an execution, action, attempt or trace id
- PASS C7: every scenario has exactly one target execution in its evidence

## Predictions

- held P1: L2 answers all 13 questions correctly in every scenario. (L2 below 13/13 in: none)
- held P2: L0 cannot verify evidence integrity (Q13) in any scenario. (L0 verified integrity in: none)
- held P3: L0 reports the wrong final outcome (Q12) in e11-false-success. (L0 Q12 verdict in e11-false-success: WRONG)
- held P4: L1 (logs + traces) needs fewer heuristic joins than L0 in every scenario. (L1 not fewer heuristic joins in: none)
- held P5: L0 cannot say which prompt template or agent configuration produced the proposal (Q4) in any scenario. (L0 answered Q4 in: none)
- held P6: The e12b control mutates production twice; e12a mutates it once. (mutations e12a=1, e12b=2)
- held P7: The restricted-data canary appears in no model request, span, log line or evidence event, in any scenario. (canary found in: none)

Per-scenario expectations: 68/68 held; missed: none.

## Tamper experiment (copy of e01's evidence)

- T1_edit_in_place: approval.decided seq 15: approver ic.sam -> eng.lee, hashes untouched → chain BROKEN, anchors ok
- T2_rewrite_chain: the same edit, every later hash recomputed so the chain is self-consistent → chain ok, anchors MISMATCH
- T3_truncate: the last three events deleted → chain ok, anchors MISMATCH
- T4_rewrite_chain_and_anchor: T2, and the witness rewritten too: the case an anchor under the same control cannot catch → chain ok, anchors ok
