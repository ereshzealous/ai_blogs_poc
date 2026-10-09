# Deviations from the preregistration

Frozen 2026-10-07T15:18:39Z (experiments/FROZEN.at). Every change to a frozen file after that moment is listed here with its reason and
whether it was made before or after any recorded run. The hashes in FROZEN.sha256 are updated only together with an entry here.

## D1 · the payment-like effect is an account credit, not a card refund (before any run)

*When:* 2026-10-07T15:19:29Z, during implementation, before the first development run and before any recorded run.

*What:* the write tool `issue_refund` became `issue_credit` (an account-balance credit) in every frozen file; the KB
documents, the policy, the prompt and the oracle's effect counter (`refunds` → `credits`) follow. Customer messages
still say "refund", as customers do. Decisions, statuses, effect counts and hypotheses are unchanged.

*Why:* real card-refund APIs cap the refunded total at the charge amount, so a second full refund of the same charge is
rejected by the provider's own business rule and the duplicate this experiment measures could not occur. That would
have made the naive arm look worse than a real one. Account credits, payouts, transfers and messages have no such
cap, so the duplicate is a real risk for them. The article states the distinction.

## D2 · the candidate model's local tag is llama3.1:latest (before any recorded run)

*When:* 2026-10-07T15:39:45Z, before the recorded run.

*What:* preregistration.toml names the candidate `llama3.1:8b`. On this machine the same model is installed under the
tag `llama3.1:latest` (the 8B instruct build); the run calls that tag and records its digest in
`runs/<run>/model-slice/models.json`. Nothing else changes. The frozen file is not edited; this entry is the record.

## Observation, not a change: the frozen retriever misses the needed document in 3 of 16 slice cases

Found while checking the slice wiring, before the recorded run: for MS-02, MS-05 and MS-06 the document the label
cites is not in the retriever's top 3. The retriever, the knowledge base and the labels are frozen and are **not**
tuned; the miss is reported as a measured retrieval-eval result (recall@3), and a grounded citation is impossible for
those cases by construction.

## D3 · invariant I7's evaluator corrected after the recorded run (analysis only)

*When:* 2026-10-07T16:11:09Z, after the recorded run `2026-10-07-recorded`, while writing the technical edition.

*What:* the first I7 implementation compared each dispatch with the journal's `result` row. A re-dispatch overwrites that
row (`insert or replace`), so a re-dispatch after a recorded result could not be seen: the X3 mutant re-dispatched
S17's already-recorded credit and only RE1 caught it. I7 now reads the append-only event sequence: a write step whose
dispatch got its outcome (no outcome failure and no in-flight crash before the next dispatch) must not be dispatched
again. The run was **not** re-executed: every `eval.json` was recomputed from the recorded files
(`python -m recovery.run reevaluate --run-id 2026-10-07-recorded`).

*Effect:* X3 now also fails I7 in S17. No result of A0, A1 or A2 changed (A2: 0 eval failures before and after); the
mutant count detected is unchanged (8 of 8). The invariant's wording in the preregistration is unchanged.

