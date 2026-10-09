# Run 2026-10-07-recorded

R1+R2 · Evals, Observability & Production Reliability · recovery_poc

25 scenarios × 3 runtimes = 75 deterministic runs; 8 mutants × 25; a deterministic model change; a real-model slice.

| | A0 naive | A1 idempotent-retry | A2 classified |
|---|---|---|---|
| scenarios with a duplicate effect | 10 | 5 | 0 |
| excess effects | 13 | 7 | 0 |
| false claims in the answer | 1 | 1 | 0 |
| completed (of 21) | 10 | 14 | 21 |
| escalations | 0 | 0 | 3 |
| retries of terminal refusals | 8 | 8 | 0 |
| runs split across traces | 4 | 0 | 0 |
| invariant FAILs | 56 | 26 | 0 |
| reconciliation queries | 0 | 0 | 12 |

A2 decisions equal to the oracle: 25 of 25.
Mutants detected: 8 of 8. Negative control (X1): duplicates in 5 scenarios (S11, S12, S18, S19, S21).

| scenario | A0 | A1 | A2 | A2 decisions |
|---|---|---|---|---|
| S00 Baseline: no fault | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | — |
| S01 Model provider unavailable once | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RETRY |
| S02 Primary model down for the whole run | FAILED c0/t0/n0 | FAILED c0/t0/n0 | COMPLETED c1/t1/n1 | RETRY → FALLBACK |
| S03 Model returns output that is not valid JSON | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | REPAIR |
| S04 Retrieval index unavailable once | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RETRY |
| S05 Model selects a tool outside the task's allow-list | FAILED c0/t0/n0 | FAILED c0/t0/n0 | COMPLETED c1/t1/n1 | REPAIR |
| S06 Model proposes a credit amount the charge does not support | FAILED c0/t0/n0 | FAILED c0/t0/n0 | COMPLETED c1/t1/n1 | REPAIR |
| S07 Credit above the agent's limit: policy denies | FAILED c0/t0/n0 | FAILED c0/t0/n0 | DENIED c0/t0/n0 | ABORT |
| S08 Credit API refuses the connection once | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RETRY |
| S09 FLAGSHIP: credit committed, response lost | COMPLETED c2/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RECONCILE → CONTINUE |
| S10 Credit committed, every response lost | FAILED c3/t0/n0 | FAILED c1/t0/n0 | COMPLETED c1/t1/n1 | RECONCILE → CONTINUE |
| S11 Ticket created, response lost (no idempotency, searchable) | COMPLETED c1/t2/n1 | COMPLETED c1/t2/n1 | COMPLETED c1/t1/n1 | RECONCILE → CONTINUE |
| S12 Message sent, response lost (no idempotency, no status query) | COMPLETED c1/t1/n2 | COMPLETED c1/t1/n2 | REQUIRES_HUMAN c1/t1/n1 | ESCALATE |
| S13 Credit rejected on a business rule (charge under dispute) | FAILED c0/t0/n0 | FAILED c0/t0/n0 | REQUIRES_HUMAN c0/t0/n0 | ESCALATE |
| S14 Read-only lookup times out once | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RETRY |
| S15 Worker killed before the credit is dispatched | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RESUME |
| S16 Worker killed with the credit in flight | COMPLETED c2/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RECONCILE → CONTINUE |
| S17 Worker killed after the credit result was recorded | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | CONTINUE |
| S18 Credit in flight at a crash; the idempotency window expires before resume | COMPLETED c2/t1/n1 | COMPLETED c2/t1/n1 | COMPLETED c1/t1/n1 | RECONCILE → CONTINUE |
| S19 Ticket response lost and ticket search down: irreconcilable | COMPLETED c1/t2/n1 | COMPLETED c1/t2/n1 | REQUIRES_HUMAN c1/t1/n0 | RECONCILE → RECONCILE → ESCALATE |
| S20 Credit response lost and status endpoint down: fall back to a keyed retry | COMPLETED c2/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RECONCILE → RECONCILE → RETRY |
| S21 Ticket API commits twice internally, response lost | COMPLETED c1/t3/n1 | COMPLETED c1/t3/n1 | COMPLETED c1/t1/n1 | RECONCILE → COMPENSATE |
| S22 Workflow store fails to record the intent before the credit | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RETRY |
| S23 Workflow store fails to record the credit result after it committed | COMPLETED c2/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RESUME → RECONCILE → CONTINUE |
| S24 Credit request delivered, provider stalls and refuses it after its deadline | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | COMPLETED c1/t1/n1 | RECONCILE → RETRY |
