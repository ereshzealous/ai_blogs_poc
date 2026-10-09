# T1 run 2026-10-03-recorded

**41/41 checks passed.** Deterministic run: simulated directory, workloads, tools and clock; real token exchange, delegation, attestation checks, broker, gateway, approvals, audit chain and revocation.

## The nine questions, answered from each record

| Mode | Platform record | Tool's own log | Kubernetes saw |
|---|---|---|---|
| shared_sa | 3/9 | 2/9 | `system:serviceaccount:platform:ai-automation` |
| impersonation | 4/9 | 3/9 | `maya@company.com` |
| chain | 9/9 | 2/9 | `system:serviceaccount:payments:incident-remediator` |

## Revocation drill (5 concurrent executions, revoked at minute 5)

| Layer | Executions affected | Max minutes to effect |
|---|---|---|
| delegation | E2, E5 | 10 |
| invoker_credential | E1 | 10 |
| agent | E1, E2, E4, E5 | 0 |
| workload | E1, E2, E4, E5 | 0 |
| tool_identity | E5 | 0 |
| shared account rotation | E1, E2, E3, E4, E5 | 0 |

## Checks

| Id | Check | Result |
|---|---|---|
| I1-01 | the rollback executed once in every mode (invariant, arm ABC) | pass |
| I1-02 | chain: the platform record answers all nine questions (invariant, arm C) | pass |
| I1-03 | every mode: the tool log answers at most three (invariant, arm ABC) | pass |
| I1-04 | shared account: Kubernetes sees one principal for three agents (control, arm A) | pass |
| I1-05 | shared account: no agent attributable from the platform record (control, arm A) | pass |
| I1-06 | chain: all three agents attributable from the platform record (invariant, arm C) | pass |
| I1-07 | audit chain intact; an edited approver breaks it at that row (invariant, arm C) | pass |
| I2-01 | chain: the deputy request is denied before any approval (invariant, arm C) | pass |
| I2-02 | chain: the callee's scopes narrowed (invariant, arm C) | pass |
| I2-03 | chain: an undeclared agent -> agent edge is refused (invariant, arm C) | pass |
| I2-04 | shared account: the deputy rollback executes and hides its originator (control, arm A) | pass |
| I3-01 | control: nothing stops without a revocation (invariant, arm C) | pass |
| I3-02 | delegation: only Maya's executions stop, within one token lifetime (qualified, arm C) | pass |
| I3-03 | invoker credential: new executions from that head refused (invariant, arm C) | pass |
| I3-04 | agent: every execution running that agent stops at its next call (invariant, arm C) | pass |
| I3-05 | workload: executions on the other runtime keep running (invariant, arm C) | pass |
| I3-06 | tool identity: one capability of one execution stops (invariant, arm C) | pass |
| I3-07 | shared account rotation stops all five executions (control, arm A) | pass |
| I4-01 | execution token replayed from another workload is rejected (invariant, arm C) | pass |
| I4-02 | privileged write replayed from another workload is rejected with no side effect (invariant, arm C) | pass |
| I4-03 | expired execution token is rejected (invariant, arm C) | pass |
| I4-04 | tool credential rejected by a system it was not minted for (invariant, arm C) | pass |
| I4-05 | stolen tool credential dies with its ten minutes (qualified, arm C) | pass |
| I4-06 | shared secret still works from anywhere a day later (control, arm A) | pass |
| I5-01 | impersonation: agent action identical to Maya's own in Kubernetes' log (control, arm B) | pass |
| I5-02 | delegation: agent action distinguishable from Maya's own (invariant, arm C) | pass |
| I5-03 | impersonation loses the agent and the actor chain (invariant, arm BC) | pass |
| I6-01 | shared account holds more than any tool identity (invariant, arm AC) | pass |
| I7-01 | re-exchange after the pause: revoked delegation stays revoked (invariant, arm C) | pass |
| I7-02 | extending instead of re-exchanging lets the rollback through (control, arm C) | pass |
| G01 | delegation never widens authority (the callee's scopes are within the caller's after every hop) (invariant, arm C) | pass |
| G02 | a delegated write whose originator lacks the authority is denied, not silently executed (invariant, arm C) | pass |
| G03 | a credential replayed from the wrong workload causes no privileged side effect (invariant, arm C) | pass |
| G04 | a revoked identity cannot mint new execution authority (invariant, arm C) | pass |
| G05 | unrelated executions survive every targeted revocation (invariant, arm C) | pass |
| G06 | rotating the shared account stops more executions than any targeted lever (invariant, arm AC) | pass |
| G07 | agent identity and runtime identity stay distinct in the record (invariant, arm C) | pass |
| G08 | impersonation does not pass for delegation provenance (invariant, arm C) | pass |
| G09 | no tool log is complete upstream provenance (every tool log answers fewer than nine questions) (invariant, arm ABC) | pass |
| G10 | the platform record reconstructs the whole identity chain (nine of nine) (invariant, arm C) | pass |
| G11 | tampering with the platform audit is detected at the edited row (invariant, arm C) | pass |
