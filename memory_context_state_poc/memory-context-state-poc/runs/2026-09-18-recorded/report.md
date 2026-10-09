# S1 run `2026-09-18-recorded` (record)

Model `gpt-oss:20b` · embeddings `nomic-embed-text` · seeds [7, 17, 27, 37, 47] · top-N 20 · evidence budget 450 tokens · clock 2026-09-18T09:00:00Z · frozen digest `693e537558dc92f1`

Governed invariants passed: **10/10** experiments

| Exp | Arm | Invalid admitted | Contradicted (unmarked / marked) | Useful recall | Precision | RB-CHK-007 | Tokens | Correct action |
|---|---|---|---|---|---|---|---|---|
| M0 | naive | expired=1, wrong_tenant=1, wrong_environment=1 | 1 / 0 | 5/8 | 5/11 | yes | 449 | 0/5 |
| M0 | naive_k5 | expired=1, wrong_environment=1 | 1 / 0 | 2/8 | 2/5 | no | 182 | — |
| M0 | governed | 0 | 0 / 1 | 8/8 | 8/10 | yes | 438 | 0/5 |
| M1 | naive | 0 | 0 / 0 | 7/7 | 7/11 | yes | 443 | 0/5 |
| M1 | naive_k5 | 0 | 0 / 0 | 4/7 | 4/5 | no | 203 | — |
| M1 | governed | 0 | 0 / 0 | 7/7 | 7/8 | yes | 370 | 0/5 |
| M2 | naive | expired=1 | 0 / 0 | 6/7 | 6/11 | yes | 430 | 0/5 |
| M2 | naive_k5 | expired=1 | 0 / 0 | 4/7 | 4/5 | no | 215 | — |
| M2 | governed | 0 | 0 / 0 | 7/7 | 7/8 | yes | 370 | 4/5 |
| M3 | naive | wrong_tenant=1 | 0 / 0 | 6/7 | 6/11 | yes | 434 | 0/5 |
| M3 | naive_k5 | wrong_tenant=1 | 0 / 0 | 4/7 | 4/5 | no | 219 | — |
| M3 | governed | 0 | 0 / 0 | 7/7 | 7/8 | yes | 370 | 1/5 |
| M4 | naive | wrong_environment=1 | 0 / 0 | 6/7 | 6/11 | yes | 428 | 0/5 |
| M4 | naive_k5 | wrong_environment=1 | 0 / 0 | 4/7 | 4/5 | no | 213 | — |
| M4 | governed | 0 | 0 / 0 | 7/7 | 7/8 | yes | 370 | 0/5 |
| M5 | naive | 0 | 1 / 0 | 6/7 | 6/11 | yes | 429 | 0/5 |
| M5 | naive_k5 | 0 | 1 / 0 | 4/7 | 4/5 | no | 214 | — |
| M5 | governed | 0 | 0 / 1 | 7/7 | 7/9 | yes | 404 | 4/5 |
| M7 | naive | superseded=1 | 0 / 0 | 7/8 | 7/11 | yes | 440 | 0/5 |
| M7 | naive_k5 | 0 | 0 / 0 | 4/8 | 4/5 | no | 203 | — |
| M7 | governed | 0 | 0 / 0 | 8/8 | 8/9 | yes | 404 | 5/5 |
| M8 | naive | 0 | 0 / 0 | 2/7 | 14/14 | no | 439 | 5/5 |
| M8 | naive_k5 | 0 | 0 / 0 | 2/7 | 5/5 | no | 179 | — |
| M8 | governed | 0 | 0 / 0 | 5/7 | 11/11 | yes | 448 | 0/5 |
| M9 | naive | workflow_claim=1 | 0 / 0 | 7/7 | 7/11 | yes | 443 | 0/5 |
| M9 | naive_k5 | workflow_claim=1 | 0 / 0 | 4/7 | 4/5 | yes | 230 | — |
| M9 | governed | 0 | 0 / 0 | 7/7 | 7/8 | yes | 370 | 5/5 |
| M6B | naive | poisoned=2, speculation=1 | 0 / 0 | 7/8 | 7/11 | yes | 447 | 0/5 |
| M6B | naive_k5 | 0 | 0 / 0 | 5/8 | 5/5 | no | 215 | — |
| M6B | governed | 0 | 0 / 0 | 8/8 | 8/9 | yes | 405 | 0/5 |

## Governed invariants

- **M0** budget_respected: PASS, no_invalid_admitted: PASS, runbook_admitted: PASS
- **M1** budget_respected: PASS, useful_memory_recalled: PASS
- **M2** budget_respected: PASS, no_expired_admitted: PASS
- **M3** budget_respected: PASS, no_wrong_tenant_admitted: PASS
- **M4** budget_respected: PASS, no_wrong_environment_admitted: PASS
- **M5** budget_respected: PASS, runbook_admitted: PASS, episode_not_in_evidence: PASS, episode_marked_contradicted: PASS
- **M7** budget_respected: PASS, no_superseded_admitted: PASS, replacement_admitted: PASS
- **M8** budget_respected: PASS, authoritative_first: PASS
- **M9** budget_respected: PASS, no_workflow_claim_admitted: PASS
- **M6B** budget_respected: PASS, assertion_contextual_only: PASS, assertion_session_scoped: PASS, assertion_not_in_later_context: PASS, unverified_tool_not_persisted: PASS, speculation_not_persisted: PASS

## Actions chosen (all seeds)

- M0 naive: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M0 governed: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M1 naive: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M1 governed: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M2 naive: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M2 governed: {'rollback_release_pipeline': 4, 'wait_for_approval': 1} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M3 naive: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M3 governed: {'rollback_release_pipeline': 1, 'wait_for_approval': 4} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M4 naive: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M4 governed: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M5 naive: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 1, errors 0)
- M5 governed: {'rollback_release_pipeline': 4, 'wait_for_approval': 1} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M7 naive: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M7 governed: {'rollback_release_pipeline': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M8 naive: {'rollback_release_pipeline': 5} (forbidden 0, cited RB-CHK-007 0, errors 0)
- M8 governed: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M9 naive: {'rollback_release_pipeline': 5} (forbidden 0, cited RB-CHK-007 0, errors 0)
- M9 governed: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 0, errors 0)
- M6B naive: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)
- M6B governed: {'wait_for_approval': 5} (forbidden 0, cited RB-CHK-007 5, errors 0)

## M6A · memory write path

| Event | Kind | Naive persisted | Governed | Tier | Scope |
|---|---|---|---|---|---|
| evt-user-assertion | user_message | yes | persisted:user-asserted | contextual | ses-s1-older |
| evt-unverified-tool | tool_output | yes | unregistered_tool | — | — |
| evt-model-speculation | model_output | yes | no_evidence | — | — |
| evt-verified-outcome | workflow_outcome | yes | persisted:platform-verified | advisory | production |
