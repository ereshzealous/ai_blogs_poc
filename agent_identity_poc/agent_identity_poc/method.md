# Method: the controlled comparison behind T1

## Question

If the same privileged rollback is executed through different identity models, what identity, authority, attribution,
revocation and replay properties survive?

## Arms

| Arm | Identity model | What reaches Kubernetes |
|---|---|---|
| A | one shared service account | `system:serviceaccount:platform:ai-automation`, whatever agent acted |
| B | the user's token handed to the agent (impersonation) | the user, as the cluster reads the token (here the email claim, display metadata, not the `(iss, sub)` identity) |
| C | an explicit delegation chain | a broker-minted credential for one capability class; the chain stays in the platform record |

**Held constant:** the incident (payment-service, 14% errors, Datadog event `dd-evt-771204`), the rollback, the agents'
plans, the policy fixture, the approval fixture, the tool simulators, the run configuration, the scenarios and the nine
questions. **The only variable:** identity propagation and credential architecture. **Randomness:** none.

## The nine attribution questions (declared in `proof/preregistration.toml`)

A1 which logical agent acted · A2 who or what invoked it · A3 on whose behalf · A4 with what delegated authority (scopes) ·
A5 on which runtime workload · A6 which edge credential reached the tool · A7 what exact action, with which arguments, on
which resource · A8 who approved it · A9 can each part be revoked independently. A question counts only when the record
states the true value. These are the POC's existing canonical definitions (`aid/experiments.py` `QUESTIONS`). The trigger
and invoker sit in A2, policy and approval in A8, the edge principal and action in A6 and A7. Agent version is not a
separate question.

## Experiments

I1 attribution completeness · I2 confused deputy · I3 revocation granularity · I4 replay and workload binding · I5
impersonation provenance loss · I6 privilege build-up (derived from configuration) · I7 long approval pause. Each records
one folder per scenario under `runs/<id>/scenarios/` with the platform audit chain and every tool's own log.

## Declared criteria and the freeze

41 checks are declared in `proof/preregistration.toml`: 30 experiment checks (`I1-01` … `I7-02`) and 11 global
assertions (`G01` … `G11`), each with a kind:

- **invariant**: a property the delegation chain must hold;
- **control**: a weak model is predicted to lose the property, and passing means it did;
- **qualified**: holds only within a stated bound (`I3-02`: revocation within one token lifetime; `I4-05`: a stolen tool
  credential dies when it expires).

History, stated plainly: 29 of the experiment checks were written with the POC, and their results were known from run
`2026-09-29-recorded`. This pass kept them unchanged, added `I4-02` (an approved rollback's token replayed from another
workload, with no side effect) and G01–G11, declared all 41, and froze them with every config file and the criteria code
(`uv run aid freeze`) before the final recorded run `2026-10-03-recorded`. `aid experiments` refuses to run when a frozen
file changed, or when the checks it evaluates differ from the declared list. Changes after the freeze are logged in
`proof/DEVIATIONS.md`.

## Determinism and verification

Simulated clock, directory, attestation and tools; deterministic agent plans. `make verify` (in the package root) re-runs
the experiments into a fresh copy and compares every file byte for byte. The one exception is `recorded.json`, which says
when the run was recorded and under which freeze.
