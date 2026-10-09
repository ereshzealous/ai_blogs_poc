# T1 Real vs Simulated

*Which parts of the Agent Identity POC are real code on the claim's path, which are simulated systems of record, and what each choice means for the evidence.*

Production AI Engineering · T1 · Evidence · Real vs simulated · 2026-10-03

## The rule

*Implemented · Simulated: agent_identity_poc/runs/2026-10-03-recorded/manifest.json lists the same split*

Everything a claim depends on is real code, exercised by the run. Everything that only produces or records inputs (the enterprise systems, the identity provider, the clock) is simulated, deterministic, and shaped like its real counterpart. The agents follow fixed plans on purpose: T1's claims are about who acts and with what authority, and they have to hold whatever a model proposes.

## Component by component

| Component | Status | Where | What it means for the evidence |
|---|---|---|---|
| Ingress authentication of each head (webhook, console, workflow, CI) | Real | `aid/directory.py`, `aid/platform.py` | Who invoked is established by code, not asserted |
| Token exchange, delegation, scope intersection, narrowing, depth limit, declared edges | Real | `aid/trust.py` | I1, I2 and I5 test the actual narrowing and actor-chain logic |
| Workload attestation check at the gateway (`cnf` against the presenter's SPIFFE id) | Real | `aid/trust.py`, `aid/attestation.py` | I4's replay rejection is the real check |
| SVID issuance and the attestation authority | Simulated | `aid/attestation.py` | No SPIRE; identities are issued from configuration |
| Capability gateway: registration, scope check, approval requirement | Real | `aid/gateway.py` | I2's DENY and every executed call go through it |
| Approvals bound to one call digest | Real | `aid/approvals.py` | Approval grants `deploy:rollback` once, for one call |
| Token broker: per capability class, audience-bound, 10-minute credentials | Real | `aid/broker.py`, `config/tool_identities.yaml` | I4's audience and expiry results come from it |
| Hash-chained platform audit with revocation handles | Real | `aid/audit.py` | I1's nine answers and the tamper test read it. Tamper-evident application audit, not an independently anchored ledger |
| Replay checks: execution token bound to the attested workload; tool credential bound to one audience and an expiry | Real | `aid/trust.py`, `aid/broker.py`, `aid/tools.py` | I4, including the approved rollback replayed from another workload (G03) |
| Evidence assertions: the 41 declared checks, the freeze and the byte-for-byte replay | Real | `aid/experiments.py`, `aid/freeze.py`, `tools/verify_run.py` | The run refuses to start if a declared criterion changed |
| Revocation levers (delegation, invoker credential, agent, workload, tool identity, shared account) | Real | `aid/directory.py`, `aid/platform.py` | I3 pulls each lever against running executions |
| The three identity models | Real | `aid/platform.py` (chain), `aid/baselines.py` (shared account, user token) | The shared account and user token are implemented, not described |
| Datadog (the monitor event) | Simulated | `aid/experiments.py` (`dd-evt-771204`) | Provenance is recorded as data; the integration is not exercised |
| Directory and enterprise identity provider | Simulated | `config/principals.yaml` | Principals, roles and delegations come from configuration; OIDC subjects are `(iss, sub)` pairs in the fixture, not a live IdP |
| Commercial authorization platform | Not used | `config/policies.yaml` | The gateway applies a minimal rule list; authorization is the next note |
| Enterprise approval system | Simulated | `aid/approvals.py` called by the experiments | The approver's decision is scripted; the binding to one call digest is real |
| Kubernetes, Jira, Slack, telemetry, and their own logs | Simulated | `aid/tools.py` | Each keeps its own log of exactly what it was shown; the Kubernetes entry mirrors the audit-event fields that matter here |
| Clock and human waiting | Simulated | `aid/config.py` | Pauses and expiry are exact and repeatable; the 37-minute wait costs nothing |
| Agents | Fixed plans | `aid/agents.py` | No model; the same calls in every run and every mode |

## Not implemented

Discussed in the technical edition, not exercised by the POC: a real identity provider and the RFC 8693 wire format, SPIRE attestation, DPoP or mTLS-bound tool credentials, Kubernetes impersonation headers, transaction tokens across services, token introspection for immediate revocation of self-contained tokens, and the authorization and policy engine the next note is about.

## What would change with real systems

- **Latency and availability.** The broker and the exchange sit on the request path. The POC does not measure either; a production design needs caching of execution identities and a failure mode for the broker (fail closed for writes).
- **Revocation.** Real deployments can shorten the qualified window in the [Evidence Check](agent-identity-evidence.html) with introspection or sender-constrained tool credentials, where the tool supports them.
- **Logs.** Real tool logs carry more fields than the simulated ones, but not the chain: Kubernetes records the authenticated principal and the request, not the invoker, the agent or the approval behind it.

---

**Series.** Foundation: [F1 · MCP Tool Sprawl](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html) · [F2 · Layered Architecture](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html) · Previous: [F3 · Headless AI](../../headless_ai/medium/headless-ai-medium.html) · Current: T1 · Agent Identity · Next: Authorization & Policy (planned). Companions: [Medium edition](../medium/agent-identity-medium.md) · [Technical deep dive](../technical/agent-identity-technical.md) · [Evidence Check](../results/agent-identity-evidence.md). Every measured number is substituted from `agent_identity_poc/runs/2026-10-03-recorded/facts.json`.
