# T4 · AI Control Plane · proof of run 2026-10-03-recorded

Run `2026-10-03-recorded` · Production AI Engineering Proof Contract v1 (`pae-proof/v1`).

13 experiments · 79 checks: 73 pass, 2 fail, 4 expected failure (a negative control that broke as intended).

A FAIL is a reported result, not an error: a preregistered hypothesis or comparison that the evidence did not
bear out stays a FAIL. Unit tests are counted separately; they are not proof checks.

| Experiment | Question | Result | Checks |
|---|---|---|---|
| T4-R1 · P1 · Baseline: the control plane allows | Under v1, does the incident agent's production restart run, and is it attributed to v1? | PASS | 4 pass · 0 fail · 0 expected failure |
| T4-R2 · P2 · One central change, same agent | Change only the control plane. Does the same process, with the same code and request, now stop for approval? | PASS | 10 pass · 0 fail · 0 expected failure |
| T4-R3 · P3 · Approval, then exactly one execution | Does the held action stay unexecuted until an eligible human approves, and then run exactly once? | PASS | 5 pass · 0 fail · 0 expected failure |
| T4-R4 · P4 · Suspend: the kill switch | Does a central suspension stop new runs and a run already in flight, and only that agent? | PASS | 5 pass · 0 fail · 0 expected failure |
| T4-R5 · P5 · Budgets and quotas | Does a central quota stop the third tool call, and an exhausted budget stop the next run? | PASS | 3 pass · 0 fail · 0 expected failure |
| T4-R6 · P6 · Revoke one MCP server for every agent | Does disabling one server centrally stop every agent that uses it, and no other? | PASS | 4 pass · 0 fail · 0 expected failure |
| T4-R7 · P7 · Model governance | Can the control plane move the default model and withdraw a model without an agent naming one? | PASS | 4 pass · 0 fail · 0 expected failure |
| T4-R8 · P8 · Staged rollout and rollback | Does a canary reach only its bucket of runs, and does rollback return every run to the stable version? | PASS | 4 pass · 0 fail · 0 expected failure |
| T4-R9 · P9 · When the control plane is unreachable | What does the runtime do without its control plane: for reads, mutations, stale policy, tampered bundles? | FAIL | 7 pass · 1 fail · 0 expected failure |
| T4-R10 · P10 · Desired vs observed state | Can the control plane see a runtime that is quietly running an old version, and what it did meanwhile? | FAIL | 4 pass · 1 fail · 0 expected failure |
| T4-R11 · P11 · Negative control: governance inside every agent | Without a control plane, what does the same set of governance changes cost, and when do they take effect? | EXPECTED_FAILURE | 4 pass · 0 fail · 4 expected failure |
| T4-R12 · P12 · Governing the control plane itself | Who may change the control plane, and is every change, accepted or rejected, on the record? | PASS | 11 pass · 0 fail · 0 expected failure |
| T4-R13 · Evidence integrity and replay | Does the recorded evidence hold together: chains, signatures, credentials, processes, code and request hashes, and a rerun from source? | PASS | 8 pass · 0 fail · 0 expected failure |
