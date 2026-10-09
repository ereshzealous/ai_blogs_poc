# Method: how the protocol experiments were designed, frozen and run

## Question

How do we pause an autonomous action, obtain an accountable decision from an authorized human, bind it to exactly what
was reviewed, and resume without stale authority or stale world state?

## Design

Three approval protocols run the same scripts on the same fixtures (`proof/preregistration.toml` → `[arms]`):

| Arm | Protocol | Role |
|---|---|---|
| A | Naive boolean: `approved = true`, the click is the decision, no digest, expiry or single use | the anti-pattern and the control |
| B | Action-bound artifact: digest, authenticated eligible approver, expiry, single use marked after the call | the common first fix |
| C | Revalidated protocol: B + atomic consume, revalidation on resume, idempotency key, credential after revalidation | the production pattern under test |

**Held constant:** the incident, the proposed action, the simulated Kubernetes, the identity chain, the policy fixture,
the human decisions and their minutes, the workflow inputs, the scenarios and the evidence questions.
**The only variable:** the approval protocol and its resume behaviour.

## Scenarios and oracle

Thirty scenarios in nine experiments (H1 exact action binding · H2 mutation · H3 replay · H4 eligibility and separation
of duties · H5 stale world · H6 identity or policy change · H7 duplicates · H8 deny, timeout, expiry, escalation · H9
audit reconstruction). Each scenario declares, before the run:

- `class`, which global metric its excess writes count toward (mutation, replay, eligibility, stale, duplicate, expiry,
  deny, audit);
- `max_legit_writes`, how many writes may legitimately happen;
- `legit_resumes`, which resume steps may legitimately write;
- `ineligible`, which decision steps are made by an ineligible approver.

A *write* is a call that reached a Kubernetes write API during a step. `excess = writes at non-legit steps + max(0,
writes at legit steps − max_legit_writes)`. Out-of-band human changes (a hotfix, a manual rollback) are not writes.

## Metrics and the fixed global assertions

`unauthorized_executions` (all excess), `mutated_action_bypasses` (mutation), `successful_approval_replays` (replay),
`duplicate_external_side_effects` (duplicate), `expired_approval_executions` (expiry), `executions_after_deny_or_timeout`
(deny), `ineligible_approver_acceptances` (accepted decisions at ineligible steps), `silent_stale_context_resumes`
(stale) and `audit_reconstruction_gaps` (executed writes whose records answer fewer than 16 questions). Eight of them
must be 0 under arm C: these are the fixed global assertions, pass criteria written before the run.

## Checks

`scripts/gen_experiments.py` turns every hypothesis into a pae-proof/v1 check in `proof/experiments.toml`:

- **invariant**: must hold; a FAIL is a broken guarantee (every arm-C criterion);
- **hypothesis**: a prediction; a FAIL is reported as NOT SUPPORTED (the predictions about B, including that it breaks);
- **control**: declares an invariant and predicts that it breaks under that arm; EXPECTED_FAILURE when it does (arm A).

Ids follow the contract (H<n> is T3-R<n>; GA, CS, API are T3-R10, T3-R11, T3-R12); each check keeps a readable label
(`H5-B01`: H5, arm B, prediction 1).

## Freeze and deviations

`uv run hitl freeze` hashes the preregistration, the checks, every config file and the scenario fixture into
`proof/FREEZE.json`. The first freeze was written at 2026-10-03T17:45:00Z, before any scenario ran. `hitl proof` refuses
to run when a guarded file changed. Every later change is logged in `proof/DEVIATIONS.md` with its time, reason and
effect on a check; a re-freeze keeps the earlier freezes in `history`.

## Reconstruction (H9)

For every executed write, an automated reconstructor answers 16 questions from the shared platform audit plus the arm's
own records (A: its boolean store and application log; B: the artifact and its execution log; C: the hash-chained audit
with revalidation, credential and result records). A question counts only when the record states the true value.

## Determinism and verification

No model, network or randomness. `uv run hitl verify` re-runs every scenario and the conformance suite in a temporary
directory and compares every raw file byte for byte, then checks schemas, the freeze, the claims, integrity hashes and
the facts the articles print.

## Adding a scenario

Add it to `proof/preregistration.toml` (with its oracle and any hypothesis), write its script in `hitl/scenarios.py`,
regenerate the checks, log the change in `proof/DEVIATIONS.md` if a freeze exists, `uv run hitl freeze`, then
`uv run hitl proof`.
