# T3 Evidence Check: Human-in-the-Loop

*Each claim in the two editions, traced to the experiment and the recorded evidence behind it, with a status: supported, qualified, contradicted or not tested.*

Production AI Engineering · T3 · Evidence · Evidence Check · 2026-10-03

## 01 · The question we tested

How do we pause an autonomous action, obtain an accountable decision from an authorized human, bind it to exactly what was reviewed, and resume without stale authority or stale world state? The POC answers by running the same production incident through three approval protocols and trying to break each one, 30 ways.

## 02 · What ran

![The same incident fixture and proposed action feed an approval model switch (A naive boolean, B action-bound, C revalidated), then the approval orchestrator, request store, Slack simulator and audit, then the execution gate, a Kubernetes simulator and an evidence recorder. A side panel lists what was held constant; the only change is the approval protocol.](../diagrams/premium/png/poc-testbed.png)

*Figure 1. The testbed: one incident, three approval protocols, everything else held constant.* · Implemented + measured: the testbed of hitl_poc; counts from the run · run 2026-10-03-protocol

The approval protocol code is real: the approval artifact, digest binding, eligibility and separation of duties, quorum, expiry, single-use consumption, revalidation, idempotency keys, the state machine and the hash-chained audit. Datadog, Kubernetes, Slack, the identity provider, the humans and the clock are simulated and deterministic. [Real vs simulated](human-in-the-loop-real-vs-simulated.html) itemises the split. Every observed value is in the [Run Report](human-in-the-loop-report.html).

## 03 · Method

**Held constant.** The incident (payment-service at 14% errors after `v4.18.0`), the proposed action (`rollbackDeployment v4.18.0 → v4.17.2`), the agent and its identity chain, the policy fixture (prod-change-policy v7, or v8 where a scenario changes it), the simulated Kubernetes, the human decisions and the minutes at which they happen, the workflow inputs, the scenarios and the 16 evidence questions.

**The only variable.** The approval protocol and its resume behaviour: **A** naive boolean (`approved = true`), **B** action-bound approval artifact (digest, eligible approver, expiry, single use marked after the call), **C** revalidated protocol (B plus atomic consume, revalidation of identity, delegation, policy, resource state and approver on resume, an idempotency key, a credential minted after revalidation).

**Preregistered and frozen.** The arms, the 30 scenarios with their oracles (which resume may legitimately write, which decision is ineligible), the metric definitions, 8 fixed global assertions and every hypothesis were written in `proof/preregistration.toml`. The 79 checks were generated from it, and both were frozen with `hitl freeze` before the first scenario ran. The freeze timestamp and the hash of every frozen file are in the run manifest. A run refuses to start if a frozen file changed.

**Deviations.** Three changes were made after the freeze, all logged in `proof/DEVIATIONS.md` and copied into the run. (1) The fact builder did not compute the per-experiment class metrics that H8's hypotheses name, so the first run stopped before writing anything; the builder was fixed. (2) A code review against the preregistered arm definition ("C is everything in B, plus revalidation") found that C's gate lacked B's request-binding check. In the recorded run C had refused both cross-workflow replays only because the approval was already consumed. The check was added. (3) The proof contract's schema rejected the first ids, so experiments and checks were renamed to its pattern (H<n> is T3-R<n>, GA is T3-R10, CS is T3-R11, API is T3-R12) and the checks file was re-frozen. Each check keeps a readable label (`H5-B01`: H5, arm B, prediction 1), and this page uses the labels. None of the three changes altered a scenario, an oracle, a metric or a check outcome.

## 04 · Results at a glance

![A table of H1 to H9 with the headline metric per arm (A, B, C) and the preregistered check counts, and a total row of unauthorized executions across all thirty scenarios.](../diagrams/premium/png/tech-scorecard.png)

*Figure 2. The headline metric of each experiment under the three arms, read from the run.* · Measured: headline metric per experiment and arm; checks.jsonl · run 2026-10-03-protocol

| Fixed global assertion (must be 0 under C) | A | B | C |
|---|---|---|---|
| unauthorized executions | 26 | 9 | 0 |
| mutated-action bypasses | 4 | 0 | 0 |
| successful approval replays | 3 | 0 | 0 |
| duplicate external side effects | 4 | 2 | 0 |
| expired approval executions | 2 | 0 | 0 |
| ineligible approver acceptances | 4 | 0 | 0 |
| silent stale-context resumes | 7 | 7 | 0 |
| audit reconstruction gaps | 36 | 19 | 0 |
| legitimate executions (not a criterion; for scale) | 10 | 10 | 10 |

Of 79 checks, 70 passed, 9 were arm A's controls breaking as predicted, and 0 failed. 0 hypotheses were not supported.

## 05 · Claim → evidence

Status. **Supported**: the recorded run shows it and a frozen check asserts it. **Qualified**: the run shows it holds only within a stated bound. **Contradicted**: a preregistered hypothesis failed. **Not tested**: the POC was not built to show it. Paths are relative to `hitl_poc/evidence/runs/2026-10-03-protocol/`.

| # | Claim | Experiment | Evidence path | Status | Notes |
|---|---|---|---|---|---|
| 1 | A boolean approval acts as ambient permission. | H1–H9, arm A | `raw/scenarios/*/A/`; checks H1-A01 … H9-A01 | Supported | By construction: A is the control. 26 unauthorized executions across the run |
| 2 | Binding an approval to an action digest stops a different or mutated action. | H1, H2 | `raw/scenarios/H1*`, `H2*`; H1-B01, H1-C01, H2-B01, H2-C01 | Supported | 0 bypasses under B and 0 under C; C opened 3 new requests in H2 |
| 3 | An approval cannot turn a policy DENY into ALLOW. | H1b, CS-T05 | `raw/scenarios/H1b/*/`; H1-A02 | Supported | Only because policy is enforced on every call, in every arm (0 writes even under A) |
| 4 | Request binding and single use stop replays, even of an identical action. | H3 | `raw/scenarios/H3*`; H3-B01, H3-C01, H3-C02 | Supported | 0 replays under C; the legitimate first execution still ran (3) |
| 5 | Only an authenticated, eligible, independent human can approve; a two-person rule needs two distinct approvers. | H4 | `raw/scenarios/H4*`; H4-B01, H4-C01, H4-C02, H4-C03 | Supported | 0 ineligible acceptances under C, 4 under A |
| 6 | Binding is not revalidation: an action-bound, unexpired approval still resumes against a changed context. | H5, H6 | `raw/scenarios/H5*/B/`, `H6*/B/`; H5-B01, H6-B01 | Supported | 7 stale resumes under B |
| 7 | Revalidation on resume stops stale resumes: world, identity, delegation, policy, approver. | H5, H6 | `raw/scenarios/H5*/C/`, `H6*/C/`; H5-C01, H6-C01, GA-07 | Supported | 0 under C; each stopped with a named reason |
| 8 | One approval produces at most one side effect only if consumption is atomic and recorded before the call. | H7 | `raw/scenarios/H7*`; H7-B01, H7-B02, H7-C01, H7-C02, GA-04 | Supported | B duplicated 2 times on a crash or a race, 0 on clicks and webhooks; C 0 |
| 9 | Deny and silence never execute; expiry stops late approvals; escalation is a recorded transition. | H8 | `raw/scenarios/H8*`; H8-A01, H8-B01, H8-C01, H8-C02, H8-C03 | Supported | Even A never executed after a deny or silence (0); A executed 2 expired approvals |
| 10 | C's records reconstruct every executed privileged action. | H9 | `raw/scenarios/H9a/*/scenario.json` → reconstruction; H9-C01, H9-C02, GA-08 | Supported | 16/16 under C, 15 under B, 10 under A; 0 gaps over 10 writes |
| 11 | C held every fixed global assertion while executing every legitimate action. | all | `experiments.json` → arms.C.global; GA-01 … GA-08 | Supported | 10 legitimate executions, the same as A and B |
| 12 | Revalidation re-checks the action and the authority, not every fact the human saw. | H5c | `story.json` → not_revalidated | **Qualified** | Severity rose SEV2 → SEV1 during the pause; no check covered it (1) |
| 13 | Expiry protects against stale approvals. | H5, H6 | `raw/scenarios/H5*/B/`, `H6*/B/` | **Qualified** | It bounds staleness; it does not detect it. Every stale approval arrived inside its 60-minute expiry |
| 14 | Crash recovery is exactly-once. | H7c | `raw/scenarios/H7c/C/` | **Qualified** | Only because the simulated Kubernetes honours an idempotency key (RECONCILED); real Kubernetes has none |
| 15 | B's duplicates were harmless. | H7c, H7d | `raw/scenarios/H7c/B/`, `H7d/B/` | **Qualified** | 2 and 2 writes, 1 and 1 state changes: the target was already running. A non-idempotent action would not be absorbed (reasoned) |
| 16 | Requiring a human approval reduces the risk of an autonomous action. | H5, H6 | `raw/scenarios/H5*/B/`, `H6*/B/` | **Qualified** | Humans approved 7 requests whose context had changed; only revalidation stopped them |
| 17 | Nothing can change between the last revalidation check and the write. | none | none | Not tested | Revalidation and the write ran in one synchronous step; CWE-367 [18] |
| 18 | A better evidence card produces better human decisions. | none | none | Not tested | The humans are scripted |
| 19 | The protocol holds with real Slack, a real IdP, a real cluster and a durable workflow engine. | none | none | Not tested | All simulated |
| 20 | The approval path is fast and available enough for incident response. | none | none | Not tested | No latency or availability measured |
| 21 | The same boundary holds test by test and through the real HTTP surface. | CS, API | `test-report.json`, `raw/api.json`; CS-*, API-01, API-02 | Supported (implementation) | 30/30 conformance tests; 9/9 HTTP calls as expected, 1 rollback |

**Contradicted: none.** No preregistered hypothesis failed. Every prediction about arm B held, including the ones that predicted it would break. That says something about this design and these scenarios. It is not a measurement of how often such failures happen in the world.

## 06 · What the POC qualified

*Measured · Reasoned: from H5c, H5, H6 and H7; each bound is stated*

- **Revalidation is only as wide as its checks.** C re-checked identity, runtime, delegation, expiry, digest, policy version and requirement, resource state and approver eligibility. The severity shown on the card was not among them, and it changed.
- **Expiry is a bound, not a detector.** A 60-minute expiry let a 37-minute-old approval through under B every time. Shortening it narrows the window and adds expired requests. It does not tell you the world changed.
- **Exactly-once leaned on the simulator.** C reconciled the crashed attempt by calling Kubernetes again with the approval's idempotency key. Real Kubernetes has no such key, so a production gateway must reconcile by reading the rollout's state.
- **Absorbed is not prevented.** B's duplicate rollbacks changed nothing only because the target version was already running. A restart, a payment or a ticket would have happened twice.
- **A human is not a safety guarantee.** In the stale scenarios, eligible humans approved requests whose context had changed. The control that caught them was deterministic revalidation, not the person.

## 07 · What this evidence does not show

- **The check-to-write window.** Revalidation and the write ran in one synchronous step. A change landing between them was not injected (CWE-367 [18]).
- **Real integrations.** Slack interactivity and signing, an enterprise IdP, a real cluster and a durable workflow engine are simulated. A pause is a clock advance.
- **Human behaviour.** The clicks are scripted. Nothing here measures rubber-stamping, alert fatigue or whether a better card changes decisions [34].
- **Performance and availability.** Nothing measures the latency or the availability of the approval path.
- **One deterministic run.** Repetition adds no statistical weight; the evidence is the frozen checks, not a distribution.

## 08 · Reproduce and verify

```bash
cd hitl_poc && uv sync --group dev
uv run pytest                                          # conformance, unit and H1–H9 tests
uv run hitl proof --run-id 2026-10-03-protocol         # refuses to run if a frozen file changed
uv run hitl verify 2026-10-03-protocol                 # schemas, freeze, replay byte for byte, integrity, claims
uv run hitl scenarios H5c                              # the opening story under A, B and C
```

---

**Series.** Foundation: [Headless AI](../../headless_ai/medium/headless-ai-medium.html) · Before this: [Agent Identity](../../agent_identity/medium/agent-identity-medium.html) · Before this: [Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · Current: Human-in-the-Loop · Next: [AI Control Plane](../../ai_control_plane/medium/ai-control-plane-medium.html). Also: [Medium edition](../medium/human-in-the-loop-medium.md) · [Technical deep dive](../technical/human-in-the-loop-technical.md). Every measured number is substituted from `hitl_poc/evidence/runs/2026-10-03-protocol/results.json` (Proof Contract v1).
