# T4 · AI Control Plane · run `2026-10-03-recorded`

100 of 100 checks passed across 15 scenarios. Agents follow fixed plans; enterprise systems and models are simulated; every runtime is a real, separate, long-lived process. Proof cards: `proof.txt`.

| Scenario | Outcome | Checks | Observed |
|---|---|---|---|
| `P1-C-baseline` | HELD | 6/6 | executed under v1; restarts=1 |
| `P2-C-central-change` | HELD | 9/9 | v1 executed → v2 pending_approval; restarts=1 |
| `P3-C-approval` | HELD | 9/9 | before approval 0; after 1; duplicate resume ALREADY_EXECUTED |
| `P4-C-suspend` | HELD | 8/8 | 0 of 2 in-flight calls executed after suspension; new run AGENT_SUSPENDED |
| `P5-C-budgets` | HELD | 7/7 | call 3 TOOL_CALL_BUDGET_EXCEEDED; run-003 DAILY_BUDGET_EXHAUSTED |
| `P6-C-revoke-mcp` | HELD | 7/7 | 0 observability calls after revoke; 3 calls denied |
| `P7-C-models` | HELD | 7/7 | fast-model → large-model; confidential under v3: DENIED NO_ALLOWED_MODEL_FOR_DATA_CLASS |
| `P8-C-canary` | HELD | 6/6 | canary 4/20; rollback 0/20; promoted 10/10 |
| `P9-C-outage` | QUALIFIED | 6/6 | mutation CONTROL_PLANE_UNREACHABLE; 3 calls ran after the suspension was published |
| `P9-C-tampered-bundle` | HELD | 3/3 | 5 rejections; applied v1 |
| `P9-C-broker-down` | HELD | 3/3 | all tool calls denied CREDENTIAL_UNAVAILABLE |
| `P10-C-drift` | QUALIFIED | 7/7 | 2 drift findings; 1 mutation under a superseded version |
| `P11-E-embedded` | BROKEN | 4/4 | 7 edits, 7 redeploys; old process still restarted |
| `P11-C-control-plane` | HELD | 5/5 | 4 versions; 0 edits; 0 redeploys |
| `P12-C-governing-the-control-plane` | HELD | 13/13 | 3 accepted, 7 rejected, all 11 on a verifying chain |

Outcomes: HELD = the governed property held; QUALIFIED = it held within a stated bound (see `where`); BROKEN = the baseline lost it, which is what the baseline is there to show.
