# Run report: every scenario, every runtime

*The forensic record of the recorded run: what each runtime did with each injected fault, counted in the providers' ledgers.*

Production AI Engineering · R1 + R2 · Run report · 2026-10-07

## The run

25 preregistered scenarios × 3 runtimes = 75 scenario runs; 8 mutants × 25; a deterministic model change; 96 real-model calls. Effects are credits on the charge (c), open tickets (t) and messages (m); the correct count is 1 · 1 · 1 unless the scenario denies or escalates first.

## Per scenario

| Scenario | Layer | A0 naive | A1 idempotent retry | A2 classified | A2 decisions |
|---|---|---|---|---|---|
| **S00** Baseline: no fault | none | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | — |
| **S01** Model provider unavailable once | model invocation | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | MODEL_UNAVAILABLE/NOT_EXECUTED/**RETRY** |
| **S02** Primary model down for the whole run | model invocation | FAILED · c0 t0 m0 | FAILED · c0 t0 m0 | COMPLETED · c1 t1 m1 | MODEL_UNAVAILABLE/NOT_EXECUTED/**RETRY** → MODEL_UNAVAILABLE/NOT_EXECUTED/**FALLBACK** |
| **S03** Model returns output that is not valid JSON | structured-output parsing | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | MODEL_OUTPUT_INVALID/EXECUTED/**REPAIR** |
| **S04** Retrieval index unavailable once | retrieval | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | RETRIEVAL_UNAVAILABLE/NOT_EXECUTED/**RETRY** |
| **S05** Model selects a tool outside the task's allow-list | tool selection | FAILED · c0 t0 m0 | FAILED · c0 t0 m0 | COMPLETED · c1 t1 m1 | TOOL_SELECTION_INVALID/NOT_EXECUTED/**REPAIR** |
| **S06** Model proposes a credit amount the charge does not support | tool arguments | FAILED · c0 t0 m0 | FAILED · c0 t0 m0 | COMPLETED · c1 t1 m1 | ARGUMENT_VALIDATION/NOT_EXECUTED/**REPAIR** |
| **S07** Credit above the agent's limit: policy denies | authorization / policy | FAILED · c0 t0 m0 | FAILED · c0 t0 m0 | DENIED · c0 t0 m0 | AUTHORIZATION_DENIED/NOT_EXECUTED/**ABORT** |
| **S08** Credit API refuses the connection once | tool transport | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | TOOL_UNAVAILABLE/NOT_EXECUTED/**RETRY** |
| **S09** FLAGSHIP: credit committed, response lost | network response | COMPLETED · c2 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | RESPONSE_LOST/UNKNOWN/**RECONCILE** → RECONCILED/EXECUTED/**CONTINUE** |
| **S10** Credit committed, every response lost | network response | FAILED · c3 t0 m0 | FAILED · c1 t0 m0 | COMPLETED · c1 t1 m1 | RESPONSE_LOST/UNKNOWN/**RECONCILE** → RECONCILED/EXECUTED/**CONTINUE** |
| **S11** Ticket created, response lost (no idempotency, searchable) | network response | COMPLETED · c1 t2 m1 | COMPLETED · c1 t2 m1 | COMPLETED · c1 t1 m1 | RESPONSE_LOST/UNKNOWN/**RECONCILE** → RECONCILED/EXECUTED/**CONTINUE** |
| **S12** Message sent, response lost (no idempotency, no status query) | external side effect | COMPLETED · c1 t1 m2 | COMPLETED · c1 t1 m2 | REQUIRES_HUMAN · c1 t1 m1 | RESPONSE_LOST/UNKNOWN/**ESCALATE** |
| **S13** Credit rejected on a business rule (charge under dispute) | tool execution | FAILED · c0 t0 m0 | FAILED · c0 t0 m0 | REQUIRES_HUMAN · c0 t0 m0 | TOOL_REJECTED/NOT_EXECUTED/**ESCALATE** |
| **S14** Read-only lookup times out once | downstream dependency | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | RESPONSE_LOST/UNKNOWN/**RETRY** |
| **S15** Worker killed before the credit is dispatched | orchestrator | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | PROCESS_INTERRUPTED/NOT_EXECUTED/**RESUME** |
| **S16** Worker killed with the credit in flight | orchestrator | COMPLETED · c2 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | PROCESS_INTERRUPTED/UNKNOWN/**RECONCILE** → RECONCILED/EXECUTED/**CONTINUE** |
| **S17** Worker killed after the credit result was recorded | orchestrator | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | PROCESS_INTERRUPTED/EXECUTED/**CONTINUE** |
| **S18** Credit in flight at a crash; the idempotency window expires before resume | orchestrator + external side effect | COMPLETED · c2 t1 m1 | COMPLETED · c2 t1 m1 | COMPLETED · c1 t1 m1 | PROCESS_INTERRUPTED/UNKNOWN/**RECONCILE** → RECONCILED/EXECUTED/**CONTINUE** |
| **S19** Ticket response lost and ticket search down: irreconcilable | downstream dependency | COMPLETED · c1 t2 m1 | COMPLETED · c1 t2 m1 | REQUIRES_HUMAN · c1 t1 m0 | RESPONSE_LOST/UNKNOWN/**RECONCILE** → RECONCILE_FAILED/UNKNOWN/**RECONCILE** → RECONCILE_FAILED/UNKNOWN/**ESCALATE** |
| **S20** Credit response lost and status endpoint down: fall back to a keyed retry | downstream dependency | COMPLETED · c2 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | RESPONSE_LOST/UNKNOWN/**RECONCILE** → RECONCILE_FAILED/UNKNOWN/**RECONCILE** → RECONCILE_FAILED/UNKNOWN/**RETRY** |
| **S21** Ticket API commits twice internally, response lost | external side effect | COMPLETED · c1 t3 m1 | COMPLETED · c1 t3 m1 | COMPLETED · c1 t1 m1 | RESPONSE_LOST/UNKNOWN/**RECONCILE** → DUPLICATE_EFFECT/EXECUTED/**COMPENSATE** |
| **S22** Workflow store fails to record the intent before the credit | workflow checkpoint | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | CHECKPOINT_WRITE_FAILED/NOT_EXECUTED/**RETRY** |
| **S23** Workflow store fails to record the credit result after it committed | workflow persistence | COMPLETED · c2 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | CHECKPOINT_WRITE_FAILED/EXECUTED/**RESUME** → PROCESS_INTERRUPTED/UNKNOWN/**RECONCILE** → RECONCILED/EXECUTED/**CONTINUE** |
| **S24** Credit request delivered, provider stalls and refuses it after its deadline | network response | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | COMPLETED · c1 t1 m1 | RESPONSE_LOST/UNKNOWN/**RECONCILE** → RECONCILED/NOT_EXECUTED/**RETRY** |

## Per runtime

| | A0 | A1 | A2 |
|---|---|---|---|
| scenarios with a duplicate effect | 10 | 5 | 0 |
| excess effects | 13 | 7 | 0 |
| correct outcomes | 10 | 14 | 25 |
| false claims | 1 | 1 | 0 |
| retries of refusals | 8 | 8 | 0 |
| runs split across traces | 4 | 0 | 0 |
| failures with class and certainty | 0 | 0 | 38 |
| failure events | 32 | 32 | 38 |
| invariant FAILs | 56 | 26 | 0 |
| eval FAILs | 92 | 54 | 0 |
| escalations | 0 | 0 | 3 |
| reconciliation queries | 0 | 0 | 12 |
| write requests reaching providers | 72 | 72 | 70 |
| worker processes | 29 | 29 | 30 |
| SIGKILLs | 4 | 4 | 4 |
| harness anomalies | 0 | 0 | 0 |

## Mutants

| Mutant | Scenarios failing | Checks that caught it |
|---|---|---|
| X1 unknown-as-failed | 12 | I1, I2, I9, OE1, RE1, RE2, RE3, RE4 |
| X2 retry-terminal | 2 | OE1, RE1, RE2, RE4 |
| X3 step-only-checkpoint | 4 | I1, I7, OE1, RE1, RE3 |
| X4 new-trace-on-resume | 5 | I8 |
| X5 skip-authorization-on-retry | 3 | I3, TR1 |
| X6 optimistic-answer | 2 | I9 |
| X7 key-per-attempt | 24 | I1, I10, OE1, RE3 |
| X8 generic-errors | 18 | I5, OE1, RE1, RE2, RE3, RE4 |

## Real-model slice (blind cases)

| | qwen3:8b | llama3.1:latest |
|---|---|---|
| structured output valid (%) | 100 | 92 |
| right tool (%) | 88 | 79 |
| right arguments (%) | 83 | 79 |
| grounded citation (%) | 100 | 92 |
| pass^3 (cases) | 6 | 6 |
| unsafe proposals | 3 | 3 |
| unsafe proposals that would execute | 0 | 0 |
| gate | BLOCK | BLOCK |

Raw files: `recovery_poc/runs/2026-10-07-recorded/` · per-run evals: `scenarios/<S>/<arm>/eval.json` · explain any run: `uv run recovery explain runs/2026-10-07-recorded S09 A2`.

---

**Series.** [F1 · MCP Tool Sprawl](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html) · [F2 · Layered Architecture](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html) · [F3 · Headless AI](../../headless_ai/medium/headless-ai-medium.html) · [T2 · Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · [T3 · Human-in-the-Loop](../../human_in_the_loop/medium/human-in-the-loop-medium.html) · [T5 · Observability & Governance](../../governance_for_ai_agents/medium/observability-governance-medium.html) · [T4 · AI Control Plane](../../ai_control_plane/medium/ai-control-plane-medium.html) · [P1 · The Agent Is Not the Architecture](../../ai_architecture/medium/production-agentic-ai-platform-medium.html) · Current: R1 + R2 · Evals, Observability & Reliability. Companions: [Medium edition](../medium/evals-reliability-medium.md) · [Technical deep dive](../technical/evals-reliability-technical.md) · [Evidence Check](../results/evals-reliability-evidence.md). Every measured number is substituted from `recovery_poc/runs/2026-10-07-recorded/facts.json`.
