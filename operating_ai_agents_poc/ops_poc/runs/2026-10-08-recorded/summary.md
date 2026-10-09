# O1 + O2 · run 2026-10-08-recorded

Simulation units: simulated milliseconds and cost units (cu). Not a benchmark of any real system.

| Scenario | Naive / baseline | Controlled |
|---|---|---|
| E1 admission | goodput 9.3 %, work in system max 5791, retry x2.81 | goodput 45.5 %, work in system max 128, refused 53.2 % |
| E2 fairness | support goodput 3.6 % | support goodput 100.0 %, finance makespan 374.9 s |
| E3 concurrency | max running 1227, goodput 44.2 % | max running 32, goodput 84.4 % |
| E4 envelope | runaway 18960.3 cu (HARNESS_GUARD) | runaway 150.0 cu (BUDGET_EXCEEDED); legit cut 4 |
| E5 routing | all-large 24.92 cu/success | routed 10.0 cu/success, violations 0 |
| E6 context | 34716 tokens/query | 5982 tokens/query, missing required 0 |
| E7 tool gateway | max in flight 16, 503 237 | max in flight 8, 503 0 |
| E8 release | image digests 1 | release ids 7 |
| E9 gate | blocked R42-b, R42-c, R42-d | passed R42-a, R42-e |
| E10 canary | R42-a: ROLLBACK | R42-e: PROMOTE (raw comparison: ROLLBACK) |

579 facts, every one recomputed from the raw files of this run.
