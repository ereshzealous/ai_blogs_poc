# T6 red-team assurance harness

A defensive lab that demonstrates **model manipulated ≠ system compromised**. A worst-case-compliant scripted model
proposes whatever synthetic hostile content asks for; a trusted registry, identity/delegation service, policy decision
point, approval service, MCP gateway and egress boundary decide what executes. Everything runs against local test
doubles (`store_world`, seed 4917) with external networking disabled.

> Synthetic data only. One fake secret value `SYNTHETIC_SECRET_12345`; `.invalid` mock destinations reached through an
> in-memory transport that records bytes and sends nothing. No real system is targeted, scanned or exfiltrated.

## Proof at a glance (run `2026-10-07-recorded`)

- 19 attacks across 8 classes + 3 controls; every attack manipulates the model
  (19/19).
- System compromised — A: **19/19**, B: **13/19**, C: **0/19**.
- Controls complete in every arm. Ablation: registry alone contains 15/19; binding is the sole
  line for 4.
- `redteam verify` replays the run byte for byte (EXACT) and recomputes every check.

## Commands

```bash
uv sync --group dev
uv run redteam scenarios     # the corpus across arms A/B/C
uv run redteam matrix        # the manipulated-vs-compromised headline
uv run redteam demo          # the legitimate task + one contained attack
uv run redteam ablation      # each control's standalone reach + sole-line attacks
uv run redteam freeze "why"  # freeze the preregistration/corpus/config before a run
uv run redteam proof         # record a run under pae-proof/v1
uv run redteam verify        # EXACT replay + integrity + checks -> VERIFIED
uv run pytest                # the import contract, the invariants, the end-to-end assertions
```

## Layout

```
redteam/
  corpus.py       load/validate the synthetic corpus (only the model and runner import it)
  model.py        the worst-case-compliant scripted model (the only reader of the corpus)
  registry.py     trusted capability + MCP registry (allowlist, metadata pinning)   I-CAP, I-META
  identity.py     identity & delegation; peer-claim verification                    I-DELEG
  policy.py       the policy decision point                                          I-AUTHZ
  approvals.py    approval records bound to an action digest                         I-APPROVAL
  gateway.py      argument binding, egress, secrets, data labels                     I-ARG, I-EGRESS, I-SECRET
  enterprise.py   mock systems over store_world; the ledger and canaries
  transport.py    the in-memory sink the oracle inspects
  guard.py        arm B's imperfect classifier (defense in depth, not the boundary)
  oracle.py       judges system_compromised from effects (cannot import the corpus)
  runtime.py      the agent loop and the three arms
  runner.py       run the corpus across arms + the ablation
  proofpack.py    record and verify a pae-proof/v1 run
config/           principals, capabilities, registry, policy, egress, guard (all guarded by the freeze)
corpus/           scenarios.yaml (the synthetic assurance corpus)
proof/            preregistration.toml, claims.toml, FREEZE.json, DEVIATIONS.md
evidence/         runs/<run>/ and published.json
tests/            test_import_contract.py, test_units.py, test_scenarios.py
```

## How the three arms differ

- **A** executes the model's proposed tool calls directly — the vulnerable toy.
- **B** runs a keyword classifier over the untrusted content first; a flag blocks the turn, a miss behaves exactly like
  A. The classifier is in front of an unrestricted path, so it is defense in depth, never the boundary. On synthetic
  markers its hit/miss split is illustrative and is not reported as a detection rate.
- **C** runs the full deterministic chain. The model is still manipulated; the action is still proposed; it does not
  execute.

## Reproducibility

The run is deterministic: no model, no network, a fixed clock. `uv run redteam verify` re-runs the harness, compares
`results.json` byte for byte, recomputes the checks against the preregistered hypotheses, and verifies the SHA256SUMS.
A change to a guarded file (the preregistration, the corpus, any config) stops a new run until it is logged in
`proof/DEVIATIONS.md` and re-frozen.
