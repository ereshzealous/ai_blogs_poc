# T3 Real vs Simulated

*Which parts of the Human-in-the-Loop POC are real control logic, which stand in for an external system, what was injected on purpose, and what was not built.*

Production AI Engineering · T3 · Evidence · Real vs simulated · 2026-10-03

## Why this page exists

A claim about a control is only as strong as the part of the system that was real when it was tested. This page draws that line for every component of the run behind the [Evidence Check](human-in-the-loop-evidence.html). No simulated system is presented as a real integration.

## Real code and control logic

These ran as written and are what the experiments test.

| Component | Where | Exercised by |
|---|---|---|
| Approval artifact and its fields (no secrets) | `hitl/contracts.py` ApprovalArtifact | H9, every B/C scenario |
| Action digest: SHA-256 over canonical JSON of capability, target, arguments, preconditions, policy version, risk | `hitl/contracts.py` Action.digest | H1, H2 |
| Approver authentication from the credential or a linked chat user; eligibility (role, request chain, deployment author); two-person quorum | `hitl/approvals.py` | H4, H6d |
| Expiry at decision time and at resume; escalation as a recorded transition | `hitl/approvals.py`, `hitl/gate.py` | H8 |
| State machine with compare-and-set transitions; single-use consumption on entering REVALIDATING | `hitl/approvals.py` | H3, H7, CS |
| Revalidation on resume: agent enabled, runtime registered, delegation active, expiry, digest, policy version and requirement, resource state, approver eligibility; request binding | `hitl/gate.py` | H3, H5, H6 |
| Idempotency key per approval, execution record, reconciliation after a crash | `hitl/gate.py` | H7c |
| Credential minted only after revalidation (an id, an audience, an expiry; no secret) | `hitl/gate.py` | H9 |
| Hash-chained audit and the 16-question reconstruction | `hitl/base.py`, `hitl/scenarios.py` | H9, every scenario |
| The three approval protocols (A, B, C) and the policy-enforcing gateway they share | `hitl/arms.py`, `hitl/gate.py` | all |
| Policy decision point with decision ids, ALLOW / DENY / REQUIRE_APPROVAL, fail closed | `hitl/policy.py` | H1b, H6c, CS |
| HTTP API and approval inbox (stdlib) driven over real HTTP | `hitl/api.py` | API |

## Simulated

Faithful local substitutes. Each row says what the substitution means for the claims.

| Real system | In the POC | What that means |
|---|---|---|
| Datadog | one fixed event (`dd-evt-88121`) | Ingest and de-duplication are exercised; alert quality is not |
| Kubernetes | `hitl/enterprise.py`: rolls back to the requested version whatever is running, like `kubectl rollout undo --to-revision` [38]; a rollback to the version already running changes nothing; writes accept an idempotency key; an effects ledger | The H5 and H6 stale rollbacks really changed state in the simulator. The idempotency key is a simulator feature real Kubernetes lacks; a production gateway must reconcile by reading the rollout instead |
| Slack / Teams approval channel | messages and button clicks as function calls; chat user ids linked to principals in `config/principals.yaml` | Mapping a click to a principal is real; Slack request signing and interactivity are not |
| Enterprise IdP and the identity context | `config/principals.yaml`: people, roles, the agent, its runtimes, the delegation and their status | Revocation and disabling are state flips the resume reads; token exchange and attestation (Agent Identity) are consumed as inputs, not re-implemented |
| Human waiting | the clock advances only when a scenario moves it | A 37-minute pause costs nothing; no durable workflow engine ran |
| Humans | scripted clicks, the same in every arm | Decision quality, fatigue and rubber-stamping are not measured |
| The production incident and the agent's reasoning | a deterministic evidence correlator and a fixed plan | No model is called; the claims are about the protocol, which must hold whatever a model proposes |

## Injected on purpose

| Condition | Scenarios |
|---|---|
| A different or mutated action presented on resume | H1, H2 |
| The same approval presented again, by the same workflow, a second instance and a new incident | H3 |
| A guest click, a read-only engineer, the agent approving itself, the release author, one approver twice under a two-person rule | H4 |
| A hotfix, a manual rollback, a revoked delegation, a disabled agent, a policy change, an approver losing the role, during the pause | H5, H6 |
| A double click, a duplicate webhook, a worker crash after the write, two racing workers (deterministically interleaved, not threads) | H7 |
| A deny, silence, a late approval, a resume after expiry, an escalation | H8 |
| Approval service down, policy engine down, a rollout failure, a lost response | CS (conformance suite) |

## Not built

Described in the editions, not exercised: a durable workflow engine (Temporal, Step Functions), out-of-band approver authentication (OIDC CIBA [13]) and step-up, signed approval records, multi-agent approval chains, and the AI control plane that would run all of this for every agent.

## Reproduce

```bash
cd hitl_poc && uv sync --group dev && uv run hitl verify 2026-10-03-protocol
```

---

**Series.** Foundation: [Headless AI](../../headless_ai/medium/headless-ai-medium.html) · Before this: [Agent Identity](../../agent_identity/medium/agent-identity-medium.html) · Before this: [Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · Current: Human-in-the-Loop · Next: [AI Control Plane](../../ai_control_plane/medium/ai-control-plane-medium.html). Also: [Medium edition](../medium/human-in-the-loop-medium.md) · [Technical deep dive](../technical/human-in-the-loop-technical.md) · [Evidence Check](../results/human-in-the-loop-evidence.md). Every measured number is substituted from `hitl_poc/evidence/runs/2026-10-03-protocol/results.json` (Proof Contract v1).
