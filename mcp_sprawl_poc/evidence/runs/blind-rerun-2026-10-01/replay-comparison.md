# Run comparison · published run (blind-rerun-2026-10-01) vs its replay of every recorded row (replay-blind-rerun-2026-10-01)

504 rows compared · replay level **SEMANTIC** · equivalent.

| Class | Rows |
|---|---:|
| DETERMINISTIC_EQUIVALENT | 0 |
| NONDETERMINISTIC | 504 |
| MODEL_OUTPUT_VARIATION | 0 |
| METHODOLOGY_CHANGE | 0 |
| REGRESSION | 0 |

Measured fields (must be equal): status, effects, declared_outcome, correct, unsafe_proposal, trap_proposed, trap_executed, capability_correct, arguments_correct, executed_expected_implementation. Invariant fields (a change is a regression): unsafe_execution. Volatile fields (may differ): wall_s, model_wall_s, invocation_ids, request_hash_mismatches.

Methodology differences: none.

Rows whose replayed model requests were not byte-identical: 10.

The run was recorded with the evidence-revision r2 code and replayed with the same code; the benchmark, prompt, scorer, policy and model are unchanged. Request-hash mismatches are key order only: recorded tool arguments replay with sorted keys, the artifact the r2 replay documents (experiment/recorded-run/replay-r2/README.md).
