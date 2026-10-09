# F3 POC · Headless incident intelligence

The proof of concept for **F3 · Headless AI** (*Your AI Shouldn't Live Inside the UI*) in the Production AI Engineering
series. It continues the payment-service incident and hands off to the next chapter, **T3 · Human-in-the-Loop**.

## What Headless AI means

Intelligence that does not belong to one user interface. The same incident-intelligence runtime is invoked by a
monitoring **event**, **chat**, a **web** console, an **API** client, a **workflow** engine, a **scheduler**, a **CI/CD**
gate and another **agent**. Every one of them is a *head*: it adapts its channel to one contract and renders the result
in its own shape. None of them owns business logic, credentials or execution state.

```text
Event · Chat · Web · API · Workflow · Scheduler · CI/CD · Agent      (eight heads)
                              │  one contract (InvocationEnvelope → ExecutionView)
                              ▼
               Headless runtime: one execution, one assessment
                              │  business capabilities only, through one gateway
                              ▼
       Capability layer: registry · policy · approvals · idempotency · audit
                              │
                              ▼
     Enterprise systems (simulated): monitoring · logs · traces · deploy · ITSM · chat
```

## The scenario

At 14:02 UTC **payment-service** (production) fails **14%** of requests against a 1% SLO. Release `v4.18.0` shipped 13
minutes earlier and switched card tokenization to a token-vault client with an 800 ms timeout. A monitoring alert, not a
person, starts the investigation. The runtime correlates the evidence, opens one incident and proposes:

```text
rollbackDeployment(payment-service, production, from_version=v4.18.0, to_version=v4.17.2)
policy: APPROVAL_REQUIRED (P3-high-risk-production-write, role incident-commander)
```

It does **not** execute that rollback on its own. The execution waits (`WAITING_APPROVAL`) until an authorized human
approves that exact call; the deploy system also refuses a rollback whose `from_version` is no longer running. How such
an approval is designed and made safe is the next chapter's question (T3 · Human-in-the-Loop).

## The ten properties and where each is proven

| # | Property | Proven by |
|---|---|---|
| 1 | An event invokes the runtime with no chat and no human | X1; `tests/test_boundary.py::test_event_invokes_without_a_human` |
| 2 | Many consumers use the same intelligence | X2: investigation heads join one execution and see one assessment |
| 3 | Heads and renderers own no business logic | `tests/test_architecture.py` (adapters and renderers import only contracts; the runtime knows no channel) |
| 4 | Enterprise systems are reached only through the capability layer | `tests/test_architecture.py::test_only_the_gateway_touches_backends`; X4 (no raw tools) |
| 5 | Execution state does not depend on chat history | X2 (chat joins the running investigation); X6 (crash resumes from checkpoints) |
| 6 | Duplicates and retries create no duplicate business effect | X3; X6 (lost response: one physical rollback) |
| 7 | Policy does not change with the head that invoked | `tests/test_governance.py::test_policy_does_not_depend_on_the_invoking_head` |
| 8 | The audit names the invocation source and the execution | X1 (true invoker), X4 (invoker and approver), X5 (seven audit questions) |
| 9 | Machine clients consume the structured result, not prose | X2: the CI/CD gate and another agent block on the same structured verdict |
| 10 | The flow stops at the approval boundary | X4 (no rollback before a valid approval); `tests/test_authority.py` |

## What it demonstrates

| Concept | Where | Experiment |
|---|---|---|
| Event-driven invocation, no human trigger | `hai/ingress/` | X1, X2 |
| One contract for every head; heads never call a model, a capability or the state store | `hai/contracts.py`, `hai/ingress/adapters.py`, `hai/heads/render.py` | X1, X2, architecture tests |
| Correlation, causation, `(source, event_id)` dedupe, fingerprint join | `hai/ingress/gateway.py` | X3 |
| Poison messages to dead letters | `hai/ingress/gateway.py` | X3 |
| Execution identity by token exchange; scopes as an intersection | `hai/control/identity.py` | X4, X6 |
| Invocation authority separate from action authority | `config/principals.yaml`, `hai/control/policy.py` | X4 |
| Business capabilities in a registry; scoped discovery; no raw tools | `config/capabilities.yaml`, `hai/capabilities/registry.py` | X4 |
| Policy decision point + enforcement point on every call | `hai/control/policy.py`, `hai/capabilities/gateway.py` | X4 |
| Approvals bound to the exact call's digest, human-only, role-checked, consumed once, with a deadline | `hai/control/approvals.py` | X4, X3, X6 |
| Idempotency keys on writes; lost-response retry without a double effect | `hai/capabilities/gateway.py`, `hai/world.py` | X6 |
| Durable execution: checkpoints, pause for approval, resume after a crash | `hai/runtime/service.py` | X6 |
| Hash-chained audit that answers seven questions; tamper detection | `hai/control/audit.py` | X5 |
| Spans on one trace id per situation | `hai/control/telemetry.py` | X5 |
| A compromised reasoner cannot act | `hai/runtime/reasoner.py` (`CompromisedReasoner`) | X4 |

## Real and simulated

| Real code | Simulated |
|---|---|
| Ingress, 8 head adapters, contracts, runtime and orchestrator, capability registry and gateway, policy engine, approvals, idempotency, audit chain, spans, SQLite state | Enterprise systems (`hai/world.py`), the identity provider (`config/principals.yaml`), the clock, injected faults, the reasoner (deterministic `EvidenceReasoner`) |

The reasoner is deterministic **on purpose**. F3's claims are about the boundary (who can invoke, with what authority,
what is recorded, what survives failure), not about how well a model diagnoses incidents. F2 measured a live model in
a layered runtime. A model-backed reasoner plugs into the same `Reasoner` port.

## Run it

Python 3.12 and [uv](https://docs.astral.sh/uv/). No model, no API key, no network, no Docker.

```bash
uv sync --group dev
uv run hai demo            # the incident end to end, printed step by step (about a second)
uv run pytest              # 27 tests: architecture, boundary, authority, governance, reliability, evidence
uv run hai experiments     # the seven experiments -> runs/<run named in runs/PUBLISHED>/
uv run hai verify          # EVIDENCE VERIFICATION of the published run; exit 1 unless VERIFIED
```

## The evidence

The published run is `runs/2026-10-05-recorded/` (named in `runs/PUBLISHED`): `summary.md` (30 architecture checks),
`checks.json`, `facts.json` (every number the articles print), `X1…X7.json`, `audit.jsonl`, `traces.jsonl`,
`effects.json`, `manifest.json` (config hashes) and `SHA256SUMS`. `proof/claims.toml` maps each claim the articles make
to the checks it rests on, the facts it prints and what it does **not** show.

`uv run hai verify` checks, without trusting the published files: the manifest against this folder's config; every
hash in `SHA256SUMS`; that every check passed; that every claim rests on passing checks and recorded facts; that the
seven experiments, re-run into a temporary folder, reproduce every file byte for byte; and that the run holds no
credential and no local path. Its last report is in `runs/verification/`.

X1 to X6 are measurements of this implementation. X7 (integration counts) is arithmetic over `config/*.yaml`, not a
measurement, and is labelled that way in the articles.

`2026-10-05-recorded` supersedes `2026-09-29-recorded`: the rollback proposal now carries `from_version` (checked by
the deploy system at the time of use) and the policy outcome is named `APPROVAL_REQUIRED`, as in T3. All 58 recorded
facts kept the same values.

## What this POC does not prove

- **Reasoning quality.** The reasoner is deterministic; the checks evaluate the architecture, not a model.
- **Production reliability.** One process, SQLite, a simulated clock; no load, no multi-region failover.
- **Live system safety.** Kubernetes, monitoring, logs, traces, ITSM, chat and the identity provider are simulated.
- **Approval design.** It shows that the flow stops at the approval boundary; how that approval is made safe is T3.

## Layout

```text
config/            principals (identities, credentials), capabilities (registry), policies (PDP rules), consumers (heads)
hai/contracts.py   InvocationEnvelope, ExecutionIdentity, CapabilityCall/Result, PolicyDecision, ExecutionView …
hai/ingress/       adapters (one per head) and the ingress gateway
hai/runtime/       HeadlessRuntime (facade + durable orchestrator) and the reasoners
hai/capabilities/  registry and gateway (PEP)
hai/control/       identity, policy (PDP), approvals, audit, telemetry
hai/heads/         renderers: each head's shape of the same ExecutionView
hai/baselines/     version A (chat-centric) and version B (layered, chat-first)
hai/world.py       the simulated enterprise and its effects ledger
hai/experiments.py X1–X7 and the facts the articles read
hai/verify.py      EVIDENCE VERIFICATION (`uv run hai verify`)
proof/claims.toml  each published claim → checks, facts, what it does not show
tests/             architecture, boundary, authority, governance, reliability, evidence
```

See `architecture.md` for the design. The articles (a Medium edition and a technical edition) explain the architecture in full.
