# T5 Real vs Simulated: Observability & Governance POC

*What in the POC is real, what is simulated, and what is recorded, so every number can be weighed for what it is.*

Production AI Engineering · T5 · Real vs simulated · Real vs simulated · 2026-09-30

## Real

| Component | What is real about it |
|---|---|
| Processes | Every agent runtime, the deployment API and the approvers run as separate OS processes (62 in the run). |
| Crashes | `SIGKILL` sent by the process to itself at a named point (2 in the run); no cleanup runs; the harness restarts it. |
| Network | HTTP over localhost sockets; the lost response is a real client socket timeout after 1,503 ms. |
| Durability | SQLite with WAL for workflow checkpoints, approvals, evidence and the deployment API's records; the evidence store uses `synchronous=FULL`. |
| Idempotency | The deployment API stores responses by `Idempotency-Key` and replays them; 409 and 422 behaviour is implemented and tested. |
| Retries | The gateway retries on timeout, 503 and 409 with the same key; attempts are numbered durably. |
| OpenTelemetry | The OpenTelemetry Python SDK 1.45.0: real spans, W3C `traceparent` propagation into the deployment API, log correlation, metrics. |
| Evidence integrity | SHA-256 hash chain across concurrent writers; witness anchors; verification and four tampering attempts. |
| Policy and approvals | Deterministic versioned policy engine with document digests; HMAC-signed, action-bound approval decisions with eligibility checks. |
| Model | qwen3:8b served by Ollama 0.30.11, 30 calls in the scenarios plus 20 in the drift probe, recorded on tape. |
| Tests | 31 of 31 pass, including end-to-end scenario tests with real processes. |

## Simulated

| Component | How it is simulated | What that does not show |
|---|---|---|
| Deployment API | A small HTTP service with revision numbers, idempotency and fault injection | asynchronous rollouts, partial application, eventual consistency of reads |
| Faults | Injected from a per-scenario fault script: reject before commit, acknowledge without applying, drop the response after commit | the variety and timing of real failures |
| The incident | INC-4471 and INC-4472, with fixed signals | real telemetry, real diagnosis |
| People | A scripted operator process approves or rejects after 0.4 s | approval latency, fatigue, human error |
| Identities and credentials | Configured principals, a static bearer credential, SPIFFE-shaped names | real token exchange (T1 covers that) |
| Compromised plan (E7) | The proposal is replaced by a scale-to-zero request and a direct gateway call | how a real model gets compromised |
| Duplicate delivery (E6) | The runtime invokes the tool step a second time after its first completion | a real queue's redelivery timing |
| External witness | A separate file | WORM storage, a transparency log, separate control |
| Retention and access control | Declared per event type in config; not enforced by a store | enforcement, deletion, access audit |

## Recorded

| What | Where | Replay |
|---|---|---|
| Every model call's request hash and full response | `scenarios/<scenario>/tape/<role>/model_tape.jsonl` | `lineage run replay 2026-09-30-recorded`: 60 answers, 0 misses, identical yes |
| The model server's model list, including the digest | the same tapes (`/api/tags`) | replayed with the calls |
| The drift probe's calls | `drift/tape/model_tape.jsonl` | replayed identically: yes |

Everything that isn't the model is re-executed on replay: processes, HTTP, SQLite, OpenTelemetry, hashing, scoring. The replay is a rerun with the model's answers held fixed, not a playback of results.

---

**Series.** Foundation: [F1 · MCP Tool Sprawl](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html) · [F2 · Layered Architecture](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html) · [F3 · Headless AI](../../headless_ai/medium/headless-ai-medium.html) · Trust: [T1 · Agent Identity](../../agent_identity/medium/agent-identity-medium.html) · [T2 · Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · [T3 · Human-in-the-Loop](../../human_in_loop/medium/hitl-medium.html) · Previous: AI Control Plane (in progress) · Current: T5 · Observability & Governance · Next: Production Agent Platform (planned). Companions: [Medium edition](../medium/observability-governance-medium.md) · [Technical deep dive](../technical/observability-governance-technical.md) · [Evidence Check](../results/observability-governance-evidence.md). Every measured number is substituted from `observability_governance_poc/runs/2026-09-30-recorded/facts.json`.
