# Real vs simulated: what actually ran

*Which parts of the R1 + R2 POC exercised the real mechanism, which are faithful local substitutes, what was recorded and what was injected.*

Production AI Engineering · R1 + R2 · Real vs simulated · 2026-10-07

## Real

*the actual mechanism was exercised.*

- Separate worker processes; 4 real SIGKILLs per runtime; a fail-stop and resume (check `REL-R5-C01`)
- HTTP over TCP to the providers, real socket timeouts, ECONNREFUSED on a closed port (check `REL-R2-C02`)
- A SQLite workflow journal with intent and result records (check `REL-R3-C01`)
- Provider-side idempotency windows, request deadlines and status queries (check `REL-R1-C03`)
- 96 calls to two local models through Ollama (check `REL-R9-C01`)
- A real-model end-to-end run: qwen3:8b deciding in every scenario x runtime, 78 calls, taped and replayed (check `REL-R11-C07`)

## Simulated

*a faithful local substitute for an external system.*

- The credit, ticket and message providers, the CRM and the knowledge base, each with its own ledger
- Provider time, advanced to expire idempotency keys (S18)
- A scripted model for the fault scenarios, so that the recovery layer is the only variable

## Recorded

*captured model traffic, reused for deterministic re-scoring.*

- The real-model tape (recovery_poc/runs/<run>/model-slice/tape.jsonl) (check `REL-R10-C01`)

## Injected

*a failure introduced on purpose.*

- 25 preregistered faults (experiments/scenarios.toml) (check `REL-R1-C01`)
- 8 mutants of the recovery layer; X1 is the negative control (check `REL-R7-C01`)

## Architecture

*design this POC does not exercise.*

- Load, backoff and retry budgets under contention; online evals on live traffic; a production escalation workflow
- Eventually consistent status queries; partial batch success; providers other than the four simulated

## What the simulation idealises

- Reconciliation queries are immediately consistent once the request deadline has passed.
- Providers have no rate limits on status queries, no partial batch success and no clock skew with the runtime.
- Each scenario runs once; results are coverage of named faults, not a distribution of production failures.

---

**Series.** [F1 · MCP Tool Sprawl](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html) · [F2 · Layered Architecture](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html) · [F3 · Headless AI](../../headless_ai/medium/headless-ai-medium.html) · [T2 · Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · [T3 · Human-in-the-Loop](../../human_in_the_loop/medium/human-in-the-loop-medium.html) · [T5 · Observability & Governance](../../governance_for_ai_agents/medium/observability-governance-medium.html) · [T4 · AI Control Plane](../../ai_control_plane/medium/ai-control-plane-medium.html) · [P1 · The Agent Is Not the Architecture](../../ai_architecture/medium/production-agentic-ai-platform-medium.html) · Current: R1 + R2 · Evals, Observability & Reliability. Companions: [Medium edition](../medium/evals-reliability-medium.md) · [Technical deep dive](../technical/evals-reliability-technical.md) · [Evidence Check](../results/evals-reliability-evidence.md). Every measured number is substituted from `recovery_poc/runs/2026-10-07-recorded/facts.json`.
