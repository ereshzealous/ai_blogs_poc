# Run report: every scenario, every arm

*The recorded run, scenario by scenario: the naive arm, the controlled arm, and what each one cost. Simulation units.*

Production AI Engineering · O1 + O2 · Run report · 2026-10-08

## The run

Ten scenarios and a negative control, recorded once from the frozen preregistration (seed 4917), replayed byte for byte. Every row below is aggregated from the run's raw telemetry rows (`ops_poc/runs/2026-10-08-recorded/scenarios/`).

## E1 · Admission (Black Friday surge)

| | open admission | bounded admission |
|---|---|---|
| support requests | 2,640 | 2,640 |
| attempts, retries included | 7,430 | 4,564 |
| attempts per request | 2.8 | 1.7 |
| max work in system | 5,791 | 128 |
| max queued | 5,759 | 96 |
| queue delay p50 (sim-ms) | 365,808 | 11,589 |
| queue delay p99 (sim-ms) | 686,675 | 14,027 |
| latency p95, successes (sim-ms) | 683,415 | 23,374 |
| refused explicitly | 0 | 1,405 |
| served while the client waited | 245 | 1,200 |
| goodput (%) | 9.3 | 45.5 |
| cost on attempts nobody waited for (%) | 97.4 | 57.9 |
| total cost (cu) | 111,168.4 | 27,966.3 |

## E2 · Tenant fairness (support + a finance batch)

| | one global FIFO | fair scheduling + bulkhead |
|---|---|---|
| support served in time (%) | 3.6 | 100 |
| support queue delay p99 (sim-ms) | 351,027 | 499 |
| support attempts per request | 2.9 | 1 |
| finance items completed | 3,000 | 3,000 |
| finance makespan (sim-s) | 168.1 | 374.9 |
| finance running at once, max | 32 | 16 |
| support running at once, max | 32 | 29 |

## E3 · Bounded concurrency and deadlines

| | unbounded | slots + bounded queue + deadlines |
|---|---|---|
| running at once, max | 1,227 | 32 |
| goodput (%) | 44.2 | 84.4 |
| latency p95, successes (sim-ms) | 251,507 | 16,388 |
| cost on attempts nobody waited for (%) | 95.2 | 7.8 |
| dropped at dequeue (deadline) | 0 | 36 |
| cancelled at the deadline | 0 | 1 |
| refused explicitly | 0 | 132 |
| started after the client's deadline | 0 | 0 |

## E4 · Workflow resource envelopes

| | no budget | per-agent budgets | propagated envelope |
|---|---|---|---|
| runaway refund: result | HARNESS_GUARD | BUDGET_EXCEEDED | BUDGET_EXCEEDED |
| runaway refund: steps | 400 | 12 | 12 |
| runaway refund: cost (cu) | 18,960.3 | 150 | 150 |
| coordinator + 3 sub-agents: result | HARNESS_GUARD | BUDGET_EXCEEDED | BUDGET_EXCEEDED |
| coordinator: model calls, children included | 205 | 11 | 9 |
| coordinator: cost (cu) | 16,735.1 | 153.1 | 127.6 |
| coordinator: stopped on | none | wall_ms | fanout |
| legitimate workflows cut | 0 | 4 | 4 |

Cut by the envelope: delivery-change (steps); dispute-investigation (wall_ms) (4 of them had re-run after a wrong answer). The envelope (refund dispute): 18 steps, 8 model calls, 5 tool calls, 184.7 cu; coordinator: 10 model calls.

## E5 · Routing inside an eligibility contract

| | all-large | all-small | routed | routed, any fallback |
|---|---|---|---|---|
| success (%) | 96.4 | 98 | 99.1 | 100 |
| first answer wrong (caught) | 30 | 81 | 33 | 33 |
| escalated | 0 | 16 | 0 | 0 |
| deferred during the throttle | 29 | 0 | 7 | 0 |
| cost per request (cu) | 24 | 2.5 | 9.9 | 10.3 |
| cost per success (cu) | 24.9 | 2.6 | 10 | 10.3 |
| … with escalations at 60 cu | 24.9 | 3.8 | 10 | 10.3 |
| calls below the capability tier | 0 | 516 | 0 | 0 |
| calls breaking the data policy | 0 | 0 | 0 | 18 |
| fallbacks | 0 | 0 | 0 | 18 |
| latency p95 (sim-ms) | 11,404 | 4,691 | 11,404 | 11,404 |

Break-even: all-small stays cheaper per success than routed unless one escalation costs more than 364 cu (under this declared contract and success table).

## E6 · Context budgets and cache scope

| | naive | bounded |
|---|---|---|
| context tokens per query (mean) | 34,716 | 5,982 |
| chunks retrieved (12 queries) | 960 | 96 |
| source queries | 48 | 24 |
| required evidence ids missing | 0 | 0 |
| retrieval cost (cu) | 2.9 | 0.7 |

| cache | lookups | hits | served across principals | served stale |
|---|---|---|---|---|
| keyed by query text | 24 | 15 | 5 | 5 |
| scoped key | 24 | 7 | 0 | 0 |

## E7 · The tool gateway

| | direct calls | gateway | gateway + fair scheduling |
|---|---|---|---|
| payments calls in flight, max | 16 | 8 | 8 |
| 503s | 237 | 0 | 0 |
| 429s | 5,932 | 0 | 0 |
| attempts per logical call | 2.8 | 1 | 1 |
| workflows completed | 911 | 3,584 | 2,222 |
| workflows failed on the tool | 1,311 | 0 | 0 |
| support served in time (%) | 99.2 | 5.3 | 100 |
| finance items completed | 195 | 1,500 | 1,500 |
| finance makespan (sim-s) | 31.8 | 157.6 | 161.2 |

## E8 · The behavioural release (same code, seven releases)

| release | changed artifact | release id | tool calls/wf | input tokens/wf | cost/wf (cu) |
|---|---|---|---|---|---|
| R41 | (production) | rel-c084dffaf6c9 | 1.1 | 8,580 | 15.1 |
| R42-e | prompt | rel-0e00bddbbffb | 1.1 | 7,789 | 14 |
| R42-a | tools.orders.lookup | rel-ec085ba7c34e | 1.9 | 8,876 | 15.2 |
| R42-topk | retrieval | rel-550efbb7626c | 1.1 | 12,020 | 20.5 |
| R42-kb | knowledge | rel-3b3cce63002f | 1.1 | 8,580 | 15.1 |
| R42-policy | authz_policy | rel-91e7d99815c9 | 1.1 | 8,580 | 15.1 |
| R42-routing | routing | rel-d540123fc17c | 1.1 | 8,562 | 18.5 |

Image digest, all seven: img-b07d496787c0. Telemetry rows with a release id: 58,573 of 58,573.

## E9 · The offline gate (40 cases)

| candidate | task success | data policy | approval bypass | envelope | cost Δ (%) | gate |
|---|---|---|---|---|---|---|
| R42-a | 1 | 0 | 0 | 0 | 0.7 | none |
| R42-b | 1 | 21 | 0 | 0 | -15.7 | invariant data_policy: 21 |
| R42-c | 1 | 0 | 4 | 0 | 0 | invariant approval_bypass: 4 |
| R42-d | 1 | 0 | 0 | 1 | 0 | invariant envelope_unenforceable: 1 |
| R42-e | 1 | 0 | 0 | 0 | -7.2 | none |

## E10 · The canary

| analysis | decision | windows | at (sim-s) | last window: tool calls Δ (%) | cost/success Δ (%) | error Δ (pp) | breaches |
|---|---|---|---|---|---|---|---|
| R42-a.mix-adjusted | ROLLBACK | 1 | 132.7 | 88.9 | -0.1 | 0 | tool_calls_pct |
| R42-e.mix-adjusted | PROMOTE | 4 | 320.6 | 4.4 | -5.9 | 0 | none |
| R42-e.raw | ROLLBACK | 3 | 297.8 | 8.8 | 21 | 0 | cost_per_success_pct |

R42-a: replies sent before the rollback 60, undone 0; requests to R42-a after the decision 0.

## Negative control

E1's controlled arm without the admission bound: max work in system 5,791 against a bound of 128; the check OPS-NC-C01 failed, as it must.

Raw files: `ops_poc/runs/2026-10-08-recorded/` · every recorded decision explained: `uv run agentops explain E10-canary` (and E1-surge, E4-runaway, E5-routing, E8-release, E9-gate).

---

**Series.** [F1 · MCP Tool Sprawl](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html) · [F2 · Layered Architecture](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html) · [F3 · Headless AI](../../headless_ai/medium/headless-ai-medium.html) · [T2 · Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · [T3 · Human-in-the-Loop](../../human_in_the_loop/medium/human-in-the-loop-medium.html) · [T5 · Observability & Governance](../../governance_for_ai_agents/medium/observability-governance-medium.html) · [T4 · AI Control Plane](../../ai_control_plane/medium/ai-control-plane-medium.html) · [S1 · Memory, Context & State](../../memory_context_state/article/memory-context-state.html) · [T1 · Agent Identity](../../agent_identity/medium/agent-identity-medium.html) · [T6 · Agent, Tool & MCP Security](../../securing_tools_mcp/medium/securing-agents-tools-mcp-medium.html) · [R1 + R2 · Evals, Observability & Reliability](../../evals_obs_reliability/medium/evals-reliability-medium.html) · [P1 · The Agent Is Not the Architecture](../../ai_architecture/medium/production-agentic-ai-platform-medium.html) · [C1 · Do You Actually Need Multiple Agents?](../../multi_agent_a2a/medium/multi-agent-a2a-medium.html) · Current: O1 + O2 · Operating AI Agents at Scale. Companions: [Medium edition](../medium/operating-ai-agents-medium.md) · [Technical deep dive](../technical/operating-ai-agents-technical.md) · [Evidence Check](../results/operating-ai-agents-evidence.md). Every measured number is substituted from `ops_poc/runs/2026-10-08-recorded/facts.json`.
