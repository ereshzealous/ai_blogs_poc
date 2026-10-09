# Evidence Check: every claim, traced to its proof

*Each claim of the O1 + O2 editions: the scenario, the mechanism, the checks behind it, what the run observed, and the class a reader should give it.*

Production AI Engineering · O1 + O2 · Evidence Check · 2026-10-08

## How to read this

Every claim is stated without its numbers; the numbers are the checks' observed values, substituted from the published run. A check compares a recorded fact with a preregistered value or with the other arm. **SUPPORTED** means every check held; **QUALIFIED** means it held, with a limitation the run observed (a check marked LIMITATION OBSERVED); **NEGATIVE CONTROL** means a property broke on purpose when its safeguard was removed; **ARGUED** and **NOT TESTED** are reasoned or out of scope.

All values are **simulation units** (simulated milliseconds, cost units). They show that a mechanism behaves as claimed under a declared workload; they are not benchmarks of any real provider, model or platform.

The proof pack: 11 experiments, 65 checks (63 pass, 1 fail as a recorded limitation, 1 expected failure), 14 claims. Replay EXACT: 99 of 99 files byte-identical. The same mapping, machine-readable: `results/claim-evidence.json`.

## OPS-C01 · SUPPORTED

**Capacity should be enforced before unlimited work enters the runtime: bounding work in system kept the surge out of the runtime, and open admission turned timeouts into retries and an unbounded queue.**

*Scenario:* OPS-E1 · Admission before execution. Black Friday surge: support requests at a multiple of capacity for 120 s, then the evening; same clients in both arms (they give up after 20 s and retry).

*Mechanism (the only variable):* Admission: open (unbounded queue) vs bounded work in system with a capacity error and Retry-After.

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-E1-C01 | Bounded admission: work in system never exceeded slots + queue bound | 128 | PASS |
| OPS-E1-C02 | Open admission: the queue grew past the queue bound | 5,759 | PASS |
| OPS-E1-C03 | Retry amplification is higher with open admission | 2.8 | PASS |
| OPS-E1-C04 | Goodput with bounded admission is at least goodput with open admission | 45.5 | PASS |
| OPS-E1-C05 | Bounded admission: p99 queue delay of admitted attempts is below the client timeout | 14,027 | PASS |
| OPS-E1-C06 | Bounded admission refuses some requests explicitly (the cost of control) | 1,405 | PASS |
| OPS-E1-C07 | Recomputed from the raw rows: work in system under bounded admission stays within the bound | 128 | PASS |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C02 · SUPPORTED

**Multi-tenant agent platforms need tenant-aware resource controls, not only global limits: under one global FIFO the finance run starved support; with weighted fair scheduling and a bulkhead, support was served and the batch still completed, later.**

*Scenario:* OPS-E2 · Tenant fairness: the noisy neighbour is your own finance team. Support at a steady rate; finance submits its reconciliation run in ten seconds; same 32 slots.

*Mechanism (the only variable):* Scheduling: one global FIFO vs weighted fair scheduling with a finance bulkhead.

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-E2-C01 | Fair scheduling: at least 99 % of support requests served within the client timeout | 100 | PASS |
| OPS-E2-C02 | Global FIFO serves fewer support requests within the timeout | 3.6 | PASS |
| OPS-E2-C03 | Fair scheduling: finance never ran more than its bulkhead at once | 16 | PASS |
| OPS-E2-C04 | Fair scheduling: every finance item still completed | 3,000 | PASS |
| OPS-E2-C05 | Fair scheduling: the finance batch finished within its deadline | 374.9 | PASS |
| OPS-E2-C06 | The batch took longer under fair scheduling (the cost of control) | 374.9 | PASS |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C03 · SUPPORTED

**Concurrency must be bounded independently of incoming request volume: unbounded concurrency slowed every workflow and spent most of its cost on attempts nobody was waiting for; slots, a bounded queue and deadline-aware dequeue kept goodput up.**

*Scenario:* OPS-E3 · Bounded concurrency, backpressure and deadlines. Overload at 1.5x capacity for 60 s, then light load; same clients.

*Mechanism (the only variable):* Unbounded concurrency vs slots + bounded queue + deadline-aware dequeue + cancellation.

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-E3-C01 | Bounded: running attempts never exceeded the slots | 32 | PASS |
| OPS-E3-C02 | Unbounded: running attempts exceeded the runtime's capacity | 1,227 | PASS |
| OPS-E3-C03 | Deadline-aware dequeue: no attempt started after its client's deadline | 0 | PASS |
| OPS-E3-C04 | Less cost spent on attempts nobody was waiting for | 7.8 | PASS |
| OPS-E3-C05 | Higher goodput with the controls | 84.4 | PASS |
| OPS-E3-C06 | Recomputed from the raw rows: running attempts never exceeded the slots | 32 | PASS |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C04 · QUALIFIED

**Production agents need explicit execution budgets, propagated to child workflows: the envelope stopped a runaway loop and bounded a coordinator with sub-agents, where per-agent budgets did not; calibrated on a development sample, it also stopped some legitimate workflows of the blind sample.**

*Scenario:* OPS-E4 · Workflow resource envelopes, propagated to children. A refund whose payment never settles; a coordinator with three sub-agents, one stuck, re-delegated; 350 calibrated normal workflows.

*Mechanism (the only variable):* Budgets: none vs per-agent vs a propagated envelope.

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-E4-C01 | Envelope: the runaway refund stopped with BUDGET_EXCEEDED | BUDGET_EXCEEDED | PASS |
| OPS-E4-C02 | No budget: the runaway ran until the simulator's harness guard | 400 | PASS |
| OPS-E4-C03 | Propagated envelope: the coordinator's model calls (children included) stayed within its envelope | 9 | PASS |
| OPS-E4-C04 | Per-agent budgets: the coordinator's total model calls exceeded its envelope | 11 | PASS |
| OPS-E4-C05 | The calibrated envelope stopped no legitimate workflow of the blind sample | 4 | LIMITATION OBSERVED |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C05 · SUPPORTED

**Model routing should optimise within a declared quality/policy contract, not cost alone: inside the contract, routing cost less per successful workflow than all-large with no violation, deferring explicitly during a throttle; optimising cost alone (all-small, any fallback) left the contract.**

*Note:* Synthetic eligibility contract and success table: no statement about the quality of any real model.

*Scenario:* OPS-E5 · Routing inside an eligibility contract. 800 workflows (support mix + finance), the EU private deployment throttled for 30 s.

*Mechanism (the only variable):* All-large vs all-small vs routed vs routed with any fallback.

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-E5-C01 | Routed costs less per successful workflow than all-large | 10 | PASS |
| OPS-E5-C02 | Routed: no model call below the task's capability tier | 0 | PASS |
| OPS-E5-C03 | Routed: no payment data on a profile not allowed to process it, throttle included | 0 | PASS |
| OPS-E5-C04 | Routed success rate within 1 percentage point of all-large (or better) | 2.7 | PASS |
| OPS-E5-C05 | All-small costs less per request than routed | 2.5 | PASS |
| OPS-E5-C06 | All-small succeeds less often than routed | 98 | PASS |
| OPS-E5-C07 | Routed with any fallback put payment data on a global profile during the throttle | 18 | PASS |
| OPS-E5-C08 | Routed deferred explicitly during the throttle instead of crossing the policy | 7 | PASS |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C06 · SUPPORTED

**Context and retrieval need resource controls like model execution: bounded retrieval kept every declared required evidence id with far fewer tokens, and a cache keyed by tenant, principal scope and versions hit without leaking or going stale, unlike a query-text cache.**

*Scenario:* OPS-E6 · Context budgets and cache scope. 12 fixture queries with declared required evidence ids; a 24-lookup cache sequence with a knowledge and a policy version change.

*Mechanism (the only variable):* Naive vs bounded retrieval; query-text vs scoped cache key.

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-E6-C01 | Bounded retrieval kept every required evidence id of every query | 0 | PASS |
| OPS-E6-C02 | Bounded retrieval used fewer context tokens per query | 5,982 | PASS |
| OPS-E6-C03 | Scoped cache: no personal answer served to another customer | 0 | PASS |
| OPS-E6-C04 | Scoped cache: no entry from an older knowledge or policy version served | 0 | PASS |
| OPS-E6-C05 | Query-text cache served a personal answer to another customer | 5 | PASS |
| OPS-E6-C06 | Query-text cache served stale entries after a version change | 5 | PASS |
| OPS-E6-C07 | The scoped cache still hit on shared questions | 7 | PASS |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C07 · SUPPORTED

**Tool capacity must be governed independently of model capacity: the gateway held the payments API inside its capacity with no 503s and far fewer attempts; alone on a FIFO queue it moved the wait into the runtime's slots, and composed with fair scheduling it served support too.**

*Scenario:* OPS-E7 · A tool gateway in front of a constrained downstream. Payments-status API (capacity 8, connection limit 16, 20 rps) behind a 64-slot runtime; a finance run and support traffic.

*Mechanism (the only variable):* Direct calls with immediate retries vs the gateway vs the gateway composed with fair scheduling.

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-E7-C01 | Gateway: calls in flight never exceeded the API's capacity | 8 | PASS |
| OPS-E7-C02 | Gateway: the API returned no 503 | 0 | PASS |
| OPS-E7-C03 | Direct calls reached the API's connection limit | 16 | PASS |
| OPS-E7-C04 | More downstream attempts per logical call with direct calls | 2.8 | PASS |
| OPS-E7-C05 | At least as many workflows completed with the gateway | 3,584 | PASS |
| OPS-E7-C06 | Gateway on one FIFO queue: support goodput fell below direct calls (the wait moved into the runtime's slots) | 5.3 | PASS |
| OPS-E7-C07 | Gateway + fair scheduling: support goodput at least that of direct calls | 100 | PASS |
| OPS-E7-C08 | Gateway + fair scheduling: the API returned no 503 | 0 | PASS |
| OPS-E7-C09 | Gateway + fair scheduling: every finance item completed | 1,500 | PASS |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C08 · SUPPORTED

**Behaviourally relevant non-code changes must create a distinguishable agent release: six single-artifact changes produced six new release ids under one unchanged image digest, and every telemetry row is attributable to its release. (The behaviour a tool description causes is declared in the scripted agent.)**

*Scenario:* OPS-E8 · The behavioural release. R41 and six candidates, each changing one artifact; the same 300-workflow Cyber Monday sample replayed under each.

*Mechanism (the only variable):* One artifact per candidate.

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-E8-C01 | The image digest is identical across the seven releases | 1 | PASS |
| OPS-E8-C02 | Seven releases, seven release ids | 7 | PASS |
| OPS-E8-C03 | Every candidate differs from R41 in exactly one artifact | 1 | PASS |
| OPS-E8-C04 | The declared behavioural model is wired: a tool description alone changes tool calls per workflow on the same workload (scripted, so it cannot fail; reclassified after the freeze, DEVIATIONS.md A2) | 1.9 | PASS |
| OPS-E8-C05 | Every telemetry row of the run carries a release id | 58,573 | PASS |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C09 · SUPPORTED

**Behavioural releases should pass machine-checkable gates before receiving production traffic: three candidates with good averages and one broken invariant each were blocked and granted no traffic.**

*Scenario:* OPS-E9 · Offline evals and invariant gates. A 40-case offline suite (historical, adversarial, synthetic) under R41 and five candidates.

*Mechanism (the only variable):* The candidate release.

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-E9-C01 | The gate blocked exactly R42-b, R42-c and R42-d | R42-b, R42-c, R42-d | PASS |
| OPS-E9-C02 | No traffic was granted to a blocked candidate | 0 | PASS |
| OPS-E9-C03 | R42-b's average task success met the threshold (the average looked fine) | 1 | PASS |
| OPS-E9-C04 | R42-a and R42-e passed the gate | R42-a, R42-e | PASS |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C10 · SUPPORTED

**Agent releases require behavioural canaries and rollback on operational evidence, not process health: a release that passed the offline gate and kept its error rate rolled back on tool-call amplification; a clean one was promoted; a raw-average comparison would have rolled the clean one back; the rollback did not undo replies already sent.**

*Scenario:* OPS-E10 · A behavioural canary, promotion and rollback. Cyber Monday support traffic; 10 / 50 / 100 % stages; windows of 60 candidate workflows; frozen guardrails.

*Mechanism (the only variable):* The candidate (R42-a, R42-e) and the comparison (mix-adjusted, raw).

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-E10-C01 | The canary rolled R42-a back | ROLLBACK | PASS |
| OPS-E10-C02 | R42-a's error rate stayed within 1 pp of R41 in every window (healthy by status code) | 0 | PASS |
| OPS-E10-C03 | After the rollback no request reached R42-a | 0 | PASS |
| OPS-E10-C04 | The canary promoted the clean R42-e | PROMOTE | PASS |
| OPS-E10-C05 | Replies sent by R42-a's canary workflows before the rollback | 60 | PASS |
| OPS-E10-C06 | None of them was undone by the rollback | 0 | PASS |
| OPS-E10-C07 | A raw-average comparison rolled the clean R42-e back | ROLLBACK | PASS |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C11 · NEGATIVE CONTROL

**The proof can fail: with the admission bound removed, the E1 invariant check breaks.**

*Scenario:* OPS-NC · Negative control: admission removed. E1's controlled arm, identical except that the admission bound is removed.

*Mechanism (the only variable):* The admission bound.

| Check | What must hold | Observed | Result |
|---|---|---|---|
| OPS-NC-C01 | Without the bound, work in system exceeds slots + queue bound | 5,791 | EXPECTED FAILURE |

*Raw evidence:* `ops_poc/runs/2026-10-08-recorded/` (see each check's `evidence` in `evidence/runs/2026-10-08-recorded/checks.jsonl`).

## OPS-C12 · ARGUED

**Autoscaling helps but does not remove provider quotas, downstream limits, budgets or tenant fairness; a queue absorbs imbalance, it does not create capacity.**

*Rests on:* research/sources.md: k8s-hpa, sre-overload, aws-queue-backlogs, aws-load-shedding; OPS-E1 and OPS-E7 as illustrations, not tests of autoscaling.

## OPS-C13 · ARGUED

**Rollback across a stateful agent platform is harder than rolling back a stateless binary: indexes, memory, migrations and external side effects need compatible versions or reconciliation.**

*Rests on:* research/sources.md: aws-rollback-safety, sre-release-engineering, flagger-strategies, istio-mirroring; OPS-E10-C06 shows only the side-effect half.

## OPS-C14 · NOT TESTED

**Real provider latency, quotas and prices; real model quality; human approval capacity; shadow traffic; real tool limits. Every number in this POC is a simulation unit.**

*Rests on:* ops_poc/config/*.toml (declared parameters); proof/manifest.toml [[reality]] ARCHITECTURE.

---

**Series.** [F1 · MCP Tool Sprawl](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html) · [F2 · Layered Architecture](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html) · [F3 · Headless AI](../../headless_ai/medium/headless-ai-medium.html) · [T2 · Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · [T3 · Human-in-the-Loop](../../human_in_the_loop/medium/human-in-the-loop-medium.html) · [T5 · Observability & Governance](../../governance_for_ai_agents/medium/observability-governance-medium.html) · [T4 · AI Control Plane](../../ai_control_plane/medium/ai-control-plane-medium.html) · [S1 · Memory, Context & State](../../memory_context_state/article/memory-context-state.html) · [T1 · Agent Identity](../../agent_identity/medium/agent-identity-medium.html) · [T6 · Agent, Tool & MCP Security](../../securing_tools_mcp/medium/securing-agents-tools-mcp-medium.html) · [R1 + R2 · Evals, Observability & Reliability](../../evals_obs_reliability/medium/evals-reliability-medium.html) · [P1 · The Agent Is Not the Architecture](../../ai_architecture/medium/production-agentic-ai-platform-medium.html) · [C1 · Do You Actually Need Multiple Agents?](../../multi_agent_a2a/medium/multi-agent-a2a-medium.html) · Current: O1 + O2 · Operating AI Agents at Scale. Companions: [Medium edition](../medium/operating-ai-agents-medium.md) · [Technical deep dive](../technical/operating-ai-agents-technical.md). Every measured number is substituted from `ops_poc/runs/2026-10-08-recorded/facts.json`.
