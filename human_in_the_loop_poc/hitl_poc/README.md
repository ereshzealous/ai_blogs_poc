# T3 POC · Human-in-the-loop as a control protocol

*Production AI Engineering · T3 · rendered from the published run `2026-10-03-protocol` by `tools/render_readme.py`*

**The question.** How do we pause an autonomous action, obtain an accountable decision from an authorized human, bind
it to exactly what was reviewed, and resume without stale authority or stale world state?

**What this POC does.** It takes the incident from the earlier notes: payment-service at 14% errors after `v4.18.0`,
with the agent proposing `rollbackDeployment v4.18.0 → v4.17.2` at 14:09. It then runs that incident through three
approval protocols, on the same fixtures and with the same humans clicking at the same minutes:

| Arm | Protocol |
|---|---|
| A · naive boolean | `approved = true`; the click is the decision; no digest, expiry or single use (the control) |
| B · action-bound | an approval artifact bound to the action digest, an eligible approver, an expiry, single use |
| C · revalidated | B, plus revalidation of identity, delegation, policy, resource state and approver on resume, an atomic consume and an idempotency key |

## Result at a glance

| Fixed global assertion (must be 0 under C) | A | B | C |
|---|---|---|---|
| unauthorized executions | 26 | 9 | 0 |
| mutated-action bypasses | 4 | 0 | 0 |
| successful replays | 3 | 0 | 0 |
| duplicate side effects | 4 | 2 | 0 |
| expired approval executions | 2 | 0 | 0 |
| ineligible approvals accepted | 4 | 0 | 0 |
| silent stale-context resumes | 7 | 7 | 0 |
| audit reconstruction gaps | 36 | 19 | 0 |

30 preregistered scenarios × 3 arms. 79 checks: 70 pass,
9 expected failures (arm A, the control), 0 fail; 0
hypotheses not supported. Conformance suite: 30/30. HTTP round trip: 9/9
calls as expected.

**What it shows:** the control semantics of the approval protocol, and what each weaker design lets through.
**What it does not show:** real Slack, a real IdP, a real cluster or a durable workflow engine (all simulated), the
window between the last check and the write, or how people actually decide. See `real_vs_simulated.md`.

## Run it

Python 3.12 and [uv](https://docs.astral.sh/uv/). No model, no API key, no network.

```bash
uv sync --group dev
uv run pytest                              # conformance (30) + unit + H1–H9 tests
uv run hitl scenarios H5c                  # the opening story (14:09 → 14:46) under A, B and C, printed
uv run hitl scenarios                      # all 30 scenarios × 3 arms, printed (no evidence written)
uv run hitl proof --run-id <id>            # refuses to run if a frozen file changed; writes evidence/runs/<id>/
uv run hitl verify                         # PROOF VERIFICATION of the published run (replay byte for byte)
uv run hitl demo                           # the approval boundary in eight lines
uv run hitl serve                          # the approval inbox at http://127.0.0.1:8787/
```

To change the experiment, edit `proof/preregistration.toml` and run `uv run python scripts/gen_experiments.py`. Log the
change in `proof/DEVIATIONS.md`, then run `uv run hitl freeze --note "…"` before the next `hitl proof`.

## What is where

| Path | What |
|---|---|
| `architecture.md` · `method.md` · `real_vs_simulated.md` | the design, the experimental method, and the line between real and simulated |
| `proof/preregistration.toml` | arms, scenarios with their oracles, metrics, global assertions, hypotheses: written before the run |
| `proof/experiments.toml` · `FREEZE.json` · `DEVIATIONS.md` | the generated checks, the freeze hashes (with history), every post-freeze change |
| `proof/claims.toml` | each claim the articles make, its status (supported · qualified · contradicted · not tested) and evidence |
| `evidence/runs/2026-10-03-protocol/` | `manifest.json`, `facts.json`, `checks.jsonl`, `story.json`, `experiments.json`, `summary.md`, `prereg/`, `raw/scenarios/<sid>/<arm>/` |
| `hitl/` | `arms.py` (A/B/C), `gate.py` (revalidation), `approvals.py` (state machine), `contracts.py` (approval artifact), `scenarios.py` (H1–H9) |
| `tests/` | `test_h1_action_binding.py` … `test_h9_audit_reconstruction.py`, `test_canonical.py` (conformance), `test_units.py` |
