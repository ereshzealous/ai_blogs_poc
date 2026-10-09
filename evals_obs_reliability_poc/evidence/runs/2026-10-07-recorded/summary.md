# R1 + R2 · Evals, Observability & Reliability · proof of run 2026-10-07-recorded

Run `2026-10-07-recorded` · Production AI Engineering Proof Contract v1 (`pae-proof/v1`).

11 experiments · 46 checks: 42 pass, 3 fail, 1 expected failure (a negative control that broke as intended).

A FAIL is a reported result, not an error: a preregistered hypothesis or comparison that the evidence did not
bear out stays a FAIL. Unit tests are counted separately; they are not proof checks.

| Experiment | Question | Result | Checks |
|---|---|---|---|
| REL-R1 · Duplicate external effects across 25 injected faults (H1–H3) | Which runtime commits an external effect more than once when a write loses its outcome? | PASS | 4 pass · 0 fail · 0 expected failure |
| REL-R2 · The flagship: the credit committed, the response was lost (S09) | With the same fault, how many credits does each runtime commit, and does the classified runtime send again? | PASS | 4 pass · 0 fail · 0 expected failure |
| REL-R3 · Recovery decisions equal the preregistered oracle (H4) | Does the classified runtime choose the preregistered (class, certainty, action) sequence in every scenario? | PASS | 4 pass · 0 fail · 0 expected failure |
| REL-R4 · The cost of caution: completion, escalation, truthfulness (H5, H6) | Does evidence-driven recovery give up on recoverable work, escalate when it need not, or tell the user something false? | PASS | 6 pass · 0 fail · 0 expected failure |
| REL-R5 · Trace continuity across retries, SIGKILL and resume (H7) | Does a run stay one trace across worker processes? | PASS | 2 pass · 0 fail · 0 expected failure |
| REL-R6 · Evals detect a broken recovery layer (H8) | Does each preregistered mutant of the recovery layer fail at least one eval check, while the unmodified runtime fails none? | PASS | 4 pass · 0 fail · 0 expected failure |
| REL-R7 · Negative control: reconciliation removed (X1, timeout treated as a failed call) | If the safeguard (UNKNOWN → reconcile) is removed, does the invariant it protects break, and does the harness still complete? | EXPECTED_FAILURE | 1 pass · 0 fail · 1 expected failure |
| REL-R8 · A model change: the gate blocks it, the invariants hold (H9) | Does the offline suite block a deterministic behaviour regression, and does the runtime stay safe if it ships anyway? | PASS | 4 pass · 0 fail · 0 expected failure |
| REL-R9 · The real-model slice (H10, H11) | How do two local models do on the decision, and does any unsafe proposal get past the runtime's gates? | FAIL | 1 pass · 3 fail · 0 expected failure |
| REL-R10 · The evidence itself | Does the published run replay, are its facts recomputable, and does its telemetry keep secrets out? | PASS | 5 pass · 0 fail · 0 expected failure |
| REL-R11 · Real model end to end: the 25 faults with qwen3:8b deciding | With a real model making every decision instead of the scripted one, do the reliability results hold? | PASS | 7 pass · 0 fail · 0 expected failure |
