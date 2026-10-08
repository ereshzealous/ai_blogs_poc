# "Real vs simulated: what actually ran"

*Which parts of the C1 POC exercised the real mechanism, which are faithful local substitutes, what was recorded, what was injected, and what is projected or argued rather than measured.*

Production AI Engineering · C1 · Real vs simulated · 2026-10-08

## Real

*the actual mechanism was exercised.*

- **Model inference**: `gpt-oss:20b` served locally by Ollama, for every reasoning component of every architecture (72 blind workflows, plus E6 and E8).
- **MCP**: four MCP stdio servers on the official Python SDK (`mcp==2.2.0`), started as separate processes by the host and by each agent process.
- **A2A**: agents as separate OS processes serving A2A v1.0 over JSON-RPC with the official `a2a-sdk` 1.2.2; Agent Card discovery at `/.well-known/agent-card.json`; `SendStreamingMessage` for every delegation (task lifecycle observed on the wire); `GetTask` and `CancelTask`.
- **Authentication across the boundary**: every A2A request carries a token in `Authorization: Bearer`, verified by the agent before any work (signature, audience, expiry, workflow, delegation).
- **Process failure**: SIGKILL of a live agent process (E6), restart by the supervisor, `GetTask` against the restarted server.
- **Retries, timeouts, idempotency keys** honoured by the system of record.
- **OpenTelemetry**: one trace per incident across host and agent processes via W3C `traceparent`.
- **Measurements**: token counts reported by the model server; wall-clock latency on one machine; bytes on the wire for every A2A delegation.

## Simulated

*a faithful local substitute for an external system.*

- checkout-api and every other enterprise system (incidents, deployments, configuration, flags, metrics, logs, runbooks), in one SQLite world with a simulated clock.
- Every remediation (rollbacks, restarts, scaling, config reverts, flag changes) and its effect on service health.
- The token service (HMAC-signed tokens with RFC 8693-style actor chains; not OAuth 2.0).
- The incident commander's approval (a simulated approver that approves whatever policy routes to approval, bound to a digest of the exact call).
- The external card-network provider and its status page (B3).

## Recorded

*captured model traffic, reused for deterministic re-execution.*

- Every model call of the blind run on an HTTP tape (`coordination_poc/runs/2026-10-08-blind/tape/`); `coord.verify_replay` re-executes the run from the tape with no model, across all processes, and compares outcomes and ledgers.

## Injected

*a failure introduced on purpose.*

- E6: a SIGKILL of the diagnosis agent mid-task (K1) and of the remediation agent after its write (K2, K2-neg).
- E8: removal of the termination owner (no hop limit, no cycle check, a budget three times larger; safety cap only).
- In the fixtures: distractor releases, coincident changes, an unsafe suggestion in an incident note (B7), an irreversible migration (B6), an already-recovered alert (B8).

## Scripted

*no model; used where removing model variance is the point.*

- E7 (A2A boundary cost) and the 64 tests use a deterministic stand-in model (`coord/scripted.py`). No headline number comes from it.

## Not measured

- Dollar cost: local inference has no API price; the article reports tokens only.
- Behaviour at production concurrency, TLS, multi-tenant agents, other models or other agent frameworks.
- Human approval latency (approval is synchronous and simulated).

---

**Series.** F1 · MCP Tool Sprawl · F2 · Layered Architecture · F3 · Headless AI · T2 · Authorization & Policy · T3 · Human-in-the-Loop · T5 · Observability & Governance · T4 · AI Control Plane · P1 · The Agent Is Not the Architecture · R1 + R2 · Evals, Observability & Reliability · Current: C1 · Multi-Agent Systems & A2A. Companions: Medium edition · Technical deep dive · [Run report](../results/multi-agent-a2a-report.md). Every measured number is substituted from `coordination_poc/runs/2026-10-08-blind/facts.json`.
