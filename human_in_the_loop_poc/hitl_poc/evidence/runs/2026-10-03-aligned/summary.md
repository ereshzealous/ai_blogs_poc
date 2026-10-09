# T3 · Human-in-the-Loop · proof summary

Run `2026-10-03-aligned` · Production AI Engineering Proof Contract v1 (`pae-proof/v1`).

8 experiments · 36 checks: 33 pass, 0 fail, 3 expected failure (a negative control that broke as intended).

A FAIL is a reported result, not an error: a preregistered hypothesis or comparison that the evidence did not
bear out stays a FAIL. Unit tests are counted separately; they are not proof checks.

| Experiment | Question | Result | Checks |
|---|---|---|---|
| T3-R1 · Risk-based routing | Does policy route each action by risk: automatic below the line, a human at the line, never above it? | PASS | 5 pass · 0 fail · 0 expected failure |
| T3-R2 · Exact-action binding | Does an approval authorize exactly one action and nothing adjacent to it? | PASS | 5 pass · 0 fail · 0 expected failure |
| T3-R3 · Approval lifecycle | Does the approval behave as a strict state machine? | PASS | 5 pass · 0 fail · 0 expected failure |
| T3-R4 · Identity and separation of duties | Can only an independent, authorized human approve? | PASS | 5 pass · 0 fail · 0 expected failure |
| T3-R5 · Duplicates, idempotency and concurrency | Do duplicates, retries and races produce exactly one business effect? | PASS | 5 pass · 0 fail · 0 expected failure |
| T3-R6 · Fail-closed, adversarial and audit | Does the boundary hold when parts fail or the input is hostile, and can every action be reconstructed? | PASS | 5 pass · 0 fail · 0 expected failure |
| T3-R7 · Negative controls | Do the canonical tests notice when a safeguard is removed? | EXPECTED_FAILURE | 1 pass · 0 fail · 3 expected failure |
| T3-R8 · Implementation: the HTTP surface and approval inbox | Does the same boundary hold through the real HTTP API a person or a client would use? | PASS | 2 pass · 0 fail · 0 expected failure |
