# O1 + O2 · Operating AI Agents at Scale · proof of run 2026-10-08-recorded

Run `2026-10-08-recorded` · Production AI Engineering Proof Contract v1 (`pae-proof/v1`).

11 experiments · 65 checks: 63 pass, 1 fail, 1 expected failure (a negative control that broke as intended).

A FAIL is a reported result, not an error: a preregistered hypothesis or comparison that the evidence did not
bear out stays a FAIL. Unit tests are counted separately; they are not proof checks.

| Experiment | Question | Result | Checks |
|---|---|---|---|
| OPS-E1 · Admission before execution | When offered demand exceeds capacity, does bounding work in system keep the overload out of the runtime? | PASS | 7 pass · 0 fail · 0 expected failure |
| OPS-E2 · Tenant fairness: the noisy neighbour is your own finance team | When one tenant floods the shared platform, do global limits alone protect the other tenant? | PASS | 6 pass · 0 fail · 0 expected failure |
| OPS-E3 · Bounded concurrency, backpressure and deadlines | Does bounding concurrency, independently of demand, protect the work the runtime does? | PASS | 6 pass · 0 fail · 0 expected failure |
| OPS-E4 · Workflow resource envelopes, propagated to children | Does an explicit envelope stop runaway execution, including across sub-agents, and what does it cut? | FAIL | 4 pass · 1 fail · 0 expected failure |
| OPS-E5 · Routing inside an eligibility contract | Can routing reduce modelled cost without leaving a declared capability and data-policy contract, including during a provider throttle? | PASS | 8 pass · 0 fail · 0 expected failure |
| OPS-E6 · Context budgets and cache scope | Can retrieval be bounded without losing the evidence a query needs, and can a cache help without leaking or going stale? | PASS | 7 pass · 0 fail · 0 expected failure |
| OPS-E7 · A tool gateway in front of a constrained downstream | Does governing a tool's capacity independently of the runtime protect the downstream, and what else does it need? | PASS | 9 pass · 0 fail · 0 expected failure |
| OPS-E8 · The behavioural release | If no code changes, does the platform still see a new release? | PASS | 5 pass · 0 fail · 0 expected failure |
| OPS-E9 · Offline evals and invariant gates | Do machine-checkable gates stop a release whose averages look fine but which breaks an invariant? | PASS | 4 pass · 0 fail · 0 expected failure |
| OPS-E10 · A behavioural canary, promotion and rollback | Does a canary that watches behaviour, not status codes, catch a release the offline gate passed, and leave a clean one alone? | PASS | 7 pass · 0 fail · 0 expected failure |
| OPS-NC · Negative control: admission removed | Can the proof fail? Remove the admission bound and the E1 invariant must break. | EXPECTED_FAILURE | 0 pass · 0 fail · 1 expected failure |
