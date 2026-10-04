# F3 run 2026-10-05-recorded

**30/30 checks passed.** Deterministic run: simulated enterprise, clock and identity provider; real ingress, runtime, gateway, policy, approvals, audit chain and spans.

| Exp | Check | Result |
|---|---|---|
| X1 | headless serves every head natively | pass |
| X1 | headless records the true invoker for every head | pass |
| X1 | chat-centric serves only chat natively | pass |
| X1 | layered-chat bridging loses the alert's invoker | pass |
| X2 | all investigation heads share one execution | pass |
| X2 | all investigation heads see one assessment | pass |
| X2 | one incident for eight heads | pass |
| X2 | sweep reads the same leading hypothesis | pass |
| X2 | sweep cannot write | pass |
| X2 | CI and agent consumers block on the same finding | pass |
| X2 | one rollback after one approval | pass |
| X3 | duplicate deliveries flagged | pass |
| X3 | re-fired alert joins the open execution | pass |
| X3 | one execution, one incident, one rollback | pass |
| X3 | a replayed approval is refused | pass |
| X3 | poison messages dead-lettered | pass |
| X4 | event execution holds no rollback scope | pass |
| X4 | viewer cannot invoke | pass |
| X4 | four invalid approvals refused | pass |
| X4 | no rollback before a valid approval | pass |
| X4 | audit names the approver and the invoker | pass |
| X4 | compromised reasoner executes nothing | pass |
| X5 | audit answers all seven questions | pass |
| X5 | audit chain intact; tamper detected | pass |
| X6 | read timeout retried | pass |
| X6 | lost response: one physical rollback | pass |
| X6 | crash: no completed step repeated | pass |
| X6 | approval timeout escalates, changes nothing | pass |
| X6 | expired token re-exchanged, not extended | pass |
| X6 | revoked credential rejected at ingress | pass |
