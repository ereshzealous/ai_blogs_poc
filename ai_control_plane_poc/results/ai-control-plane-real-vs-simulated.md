# T4 Real vs Simulated: AI Control Plane

*What in the POC is real code really run, what is simulated, what a production deployment would substitute, and what was not exercised.*

Production AI Engineering · T4 · Real vs simulated · Real vs simulated · 2026-10-03

The POC intentionally compresses production components into a small deterministic implementation so it can isolate the architectural property under test. Every row below is one of three things: **REAL** (the mechanism itself ran, and a proof check shows it), **SIMULATED** (a faithful local substitute for a system the property does not depend on), or **NOT EXERCISED** (argued in the editions, not tested here). The **PRODUCTION SUBSTITUTE** column says what replaces each compressed piece.

## REAL

| Component | Where | What ran | Proof check | Production substitute |
|---|---|---|---|---|
| Separate, long-lived runtime processes | `acp/runtime/worker.py`, `acp/harness.py` | real OS subprocesses speaking JSON lines; 16 across the run, 0 restarted; every response carries its process id, recorded as a label (`rt-a/pid-1`) | `T4-R13-C05`, `T4-R2-C03` | the agent runtime fleet (containers, serverless workers) running the same SDK |
| Control-plane versioning, pointer, rollout, rollback | `acp/controlplane/store.py` | immutable `vN.json` bundles; 34 versions published across the run | `T4-R8-C04` | a versioned policy and configuration store with staged rollout |
| Bundle signing and verification | `acp/common.py`, `acp/runtime/services.py` | HMAC-SHA256 over each bundle's sha256; 34 signatures verified | `T4-R13-C03`, `T4-R9-C05` | asymmetric signatures, keys in a KMS or HSM; the runtime holds only the public key |
| Change governance | `acp/controlplane/admin.py`, `validate.py` | scopes, restricting vs widening, two-person rule, break-glass, plaintext-credential rejection | `T4-R12-C01`…`C08` | an IdP-backed change workflow with MFA and just-in-time elevation |
| Hash-chained change log and runtime audit | `acp/common.py` | every row carries the previous row's hash; 14 audit and 14 change-log chains recomputed | `T4-R13-C01`, `T4-R13-C02` | an append-only external audit store (WORM, transparency log); this is a tamper-evident local log under POC assumptions |
| Decision function and enforcement points | `acp/runtime/pdp.py`, `sdk.py` | every tool and model call decided against the current bundle, with the version and rule named | `T4-R1-C02`, `T4-R1-C03` | a policy engine (OPA/Cedar-style) embedded in the runtime SDK and the MCP gateway |
| Last-known-good cache and failure policy | `acp/runtime/sdk.py` | staleness bound, fail-closed mutations, rejected bundles | `T4-R9-C02`, `T4-R9-C03` | the same semantics, with staleness in seconds and freshness/revocation signals |
| Agent code and request hashing | `acp/common.py`, `acp/experiments.py` | sha256 over `acp/agents/*.py` before, at import and after; request hash of every run; 93 of 93 recomputed | `T4-R13-C06`, `T4-R13-C08` | build provenance (SBOM, signed images) and request tracing |
| Architecture rules | `tests/test_architecture.py`, `tests/test_invariants.py`, `tests/test_cheating.py` | agents import nothing and name no model; the runtime cannot reach the control plane's mutation API; execution only after a decision; P2 fails if code, process or request changes | `make test` | the same rules in CI |

## SIMULATED

| Component | Simulation | Production substitute |
|---|---|---|
| Agents' reasoning | fixed deterministic plans, no LLM, in the recorded run. The optional live mode (`make live`, L1–L3) lets a self-hosted model (Ollama: `qwen3:8b`) plan the incident agent's steps; **not exercised** in this evidence, illustrative only | a model-driven agent; the governance path is unchanged |
| Enterprise systems and MCP servers | `acp/systems.py`: deploy, billing, support, observability as in-process systems of record; side effects in `effects.json`, every call in `log.jsonl` | real services behind MCP servers with OAuth resource-server checks |
| Model endpoints | `ModelGateway`: deterministic text, token counts and cost | a model gateway enforcing the resolved model, data class and residency |
| Distribution channel | a shared directory read at each enforcement point | push or watch with acknowledgements, propagation delay and bundle expiry |
| Network partition, lagging replica, in-transit tampering | flags in `state/network/<instance>.json` (INJECTED) | real faults; chaos testing |
| Credential broker | in-process minting of audience-bound, short-lived credentials | a secrets manager issuing leased dynamic credentials to authenticated workloads; the control plane holds `secret://` references, never values |
| Approval service | a JSON store with eligibility and expiry | the durable approval gate from T3 |
| Spend meter | a shared JSON file | a budget service with atomic counters |
| Time | logical ticks | wall-clock time; staleness in seconds |
| Administrators | named principals in `config/admins.yaml` | IdP groups, MFA, just-in-time elevation |

## NOT EXERCISED

| Not exercised | Why it matters | Status in the Evidence Check |
|---|---|---|
| Real MCP protocol traffic and interoperability | P6 shows central revocation at a simulated boundary, not a working MCP deployment | Not tested (`T4-C20`) |
| Environment and tenant isolation, admin MFA, control-plane HA, backup and restore, real key management | the control plane becomes the most privileged system in the estate | Not tested (`T4-C21`) |
| Latency, throughput, availability | local decisions against a cached bundle are a design argument here, not a measurement | Argued (`T4-C19`) |
| Scale beyond three agents | the embedded baseline's edit counts are for three agents | Argued (`T4-C18`) |
| Real model behaviour | the recorded run has no model; the live mode is illustrative | not part of this evidence |

## Limitations

The POC intentionally compresses production components into a small deterministic implementation so it can isolate the architectural property under test. That choice buys exact replay (EXACT: a rerun from source differs only in masked process ids) and a clean causal story for P2, at the price of everything in the two tables above: the systems, models, distribution and time are simulated, and nothing here measures performance or proves a model will behave.

---

**Series.** Foundation: F1 · MCP Tool Sprawl · F2 · Layered Architecture · F3 · Headless AI · Trust: T1 · Agent Identity · T2 · Authorization & Policy · Previous: T3 · Human-in-the-Loop · Current: T4 · AI Control Plane · Next: T5 · Observability & Governance. Companions: Medium edition · Technical deep dive · [Evidence Check](../results/ai-control-plane-evidence.md). Every measured number is substituted from `control_plane_poc/runs/2026-10-03-recorded/facts.json`.
