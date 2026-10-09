# T1 run 2026-09-29-recorded

**29/29 checks passed.** Deterministic run: simulated directory, workloads, tools and clock; real token exchange, delegation, attestation checks, broker, gateway, approvals, audit chain and revocation.

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

| Exp | Check | Result |
|---|---|---|
| I1 | the rollback executed once in every mode | pass |
| I1 | chain: the platform record answers all nine questions | pass |
| I1 | every mode: the tool log answers at most three | pass |
| I1 | shared account: Kubernetes sees one principal for three agents | pass |
| I1 | shared account: no agent attributable from the platform record | pass |
| I1 | chain: all three agents attributable from the platform record | pass |
| I1 | audit chain intact; an edited approver breaks it at that row | pass |
| I2 | chain: the deputy request is denied before any approval | pass |
| I2 | chain: the callee's scopes narrowed | pass |
| I2 | chain: an undeclared agent -> agent edge is refused | pass |
| I2 | shared account: the deputy rollback executes and hides its originator | pass |
| I3 | control: nothing stops without a revocation | pass |
| I3 | delegation: only Maya's executions stop, within one token lifetime | pass |
| I3 | invoker credential: new executions from that head refused | pass |
| I3 | agent: every execution running that agent stops at its next call | pass |
| I3 | workload: executions on the other runtime keep running | pass |
| I3 | tool identity: one capability of one execution stops | pass |
| I3 | shared account rotation stops all five executions | pass |
| I4 | execution token replayed from another workload is rejected | pass |
| I4 | expired execution token is rejected | pass |
| I4 | tool credential rejected by a system it was not minted for | pass |
| I4 | stolen tool credential dies with its ten minutes | pass |
| I4 | shared secret still works from anywhere a day later | pass |
| I5 | impersonation: agent action identical to Maya's own in Kubernetes' log | pass |
| I5 | delegation: agent action distinguishable from Maya's own | pass |
| I5 | impersonation loses the agent and the actor chain | pass |
| I6 | shared account holds more than any tool identity | pass |
| I7 | re-exchange after the pause: revoked delegation stays revoked | pass |
| I7 | extending instead of re-exchanging lets the rollback through | pass |
