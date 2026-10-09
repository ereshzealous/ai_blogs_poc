# T3 · Human-in-the-Loop · proof summary

Run `2026-10-03-protocol` · Production AI Engineering Proof Contract v1 (`pae-proof/v1`).

12 experiments · 79 checks: 70 pass, 0 fail, 9 expected failure (a negative control that broke as intended).

A FAIL is a reported result, not an error: a preregistered hypothesis or comparison that the evidence did not
bear out stays a FAIL. Unit tests are counted separately; they are not proof checks.

| Experiment | Question | Result | Checks |
|---|---|---|---|
| T3-R1 · H1 · Exact action binding | Does an approval authorize only the exact action the human reviewed? | EXPECTED_FAILURE | 3 pass · 0 fail · 1 expected failure |
| T3-R2 · H2 · Mutation after approval | What happens if the action changes after approval? | EXPECTED_FAILURE | 4 pass · 0 fail · 1 expected failure |
| T3-R3 · H3 · Approval replay | Can an old approval be replayed? | EXPECTED_FAILURE | 3 pass · 0 fail · 1 expected failure |
| T3-R4 · H4 · Approver eligibility and separation of duties | Can the wrong human approve? | EXPECTED_FAILURE | 4 pass · 0 fail · 1 expected failure |
| T3-R5 · H5 · Stale world state after a 37-minute pause | Does the system blindly resume after the world changed? | EXPECTED_FAILURE | 2 pass · 0 fail · 1 expected failure |
| T3-R6 · H6 · Identity or policy change during the pause | Is the approval still executable after identity or policy changed? | EXPECTED_FAILURE | 2 pass · 0 fail · 1 expected failure |
| T3-R7 · H7 · Duplicate callback and concurrent resume | Can one approval produce two side effects? | EXPECTED_FAILURE | 4 pass · 0 fail · 1 expected failure |
| T3-R8 · H8 · Deny, timeout, expiry and escalation | Does silence, a deny or an expired approval ever execute? | EXPECTED_FAILURE | 5 pass · 0 fail · 1 expected failure |
| T3-R9 · H9 · Audit reconstruction | Can the records alone reconstruct who, what, on whose authority, approved by whom, revalidated how, with what effect? | EXPECTED_FAILURE | 3 pass · 0 fail · 1 expected failure |
| T3-R10 · GA · Fixed global assertions (arm C) | Across every hardened scenario, does anything unsafe happen at all? | PASS | 8 pass · 0 fail · 0 expected failure |
| T3-R11 · CS · Arm C conformance suite (30 regression tests) | Does the revalidated protocol keep its routing, lifecycle, identity, duplicate, fail-closed and audit guarantees, test by test? | PASS | 30 pass · 0 fail · 0 expected failure |
| T3-R12 · API · Implementation: the HTTP surface and approval inbox | Does the same boundary hold through the real HTTP API a person or a client would use? | PASS | 2 pass · 0 fail · 0 expected failure |
