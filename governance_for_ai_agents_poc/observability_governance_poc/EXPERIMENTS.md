# Experiments

Preregistered in `experiments/preregistration.toml` (digest frozen in each run's `manifest.json`). Every scenario runs the
target execution and a concurrent background execution. Results: `runs/2026-09-30-recorded/reports/results.md`.

| Group | Scenario | Injected | Expected (preregistered) |
|---|---|---|---|
| happy path | e01-success | nothing | mitigated, 1 change, 1 attempt |
| runtime failures | e02-tool-failure | 503 before commit ×3 | not mitigated, 0 changes, 3 attempts |
| governance failures | e03-policy-denial | severity SEV-3 | DENY, 0 attempts |
| governance failures | e04-human-rejection | incident commander rejects | 0 attempts |
| runtime failures | e05a-crash-awaiting-approval | SIGKILL while waiting | 2 processes, 1 change |
| runtime failures | e05b-crash-after-dispatch | SIGKILL after the response arrived | 2 processes, 1 change, 1 attempt |
| side-effect ambiguity | e06-duplicate-delivery | tool step delivered twice | 2 attempts, 1 change |
| governance failures | e07-unexpected-capability | compromised plan: scale to zero + direct gateway call | DENY, 0 attempts |
| version drift | e08a-policy-v41 | policy v41 | 1 approval |
| version drift | e08b-policy-v42 | policy v42 | 2 approvals |
| version drift | e09-config-v9 | agent config v9 | config recorded |
| governance failures | e10-restricted-data | request for PCI data | denied, 0 canary leaks, mitigated |
| side-effect ambiguity | e11-false-success | 200 OK, never applied | not mitigated, 0 changes, not verified |
| side-effect ambiguity | e12a-lost-response | response dropped after commit | 2 attempts, 1 change, 1 timeout |
| side-effect ambiguity | e12b-lost-response-no-key | same, no idempotency key (control) | 2 attempts, 2 changes |

Reconstruction predictions P1–P7 are in the same file and are evaluated in `reports/predictions.json`.
In the recorded run: 68/68 expectations and 7/7 predictions held; 7/7 checks passed.

**D1 · drift probe** (`lineage/drift.py`, `config/drift.toml`): ten incidents × configurations v8 and v9, one call each;
`reports/drift.json`.

**Tamper experiment** (in `lineage/aggregate.py`): on a copy of e01's evidence: T1 edit in place, T2 edit and recompute the
chain, T3 truncate, T4 recompute chain and anchor; `reports/tamper.json`.
