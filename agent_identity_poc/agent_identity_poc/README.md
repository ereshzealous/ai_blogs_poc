# T1 POC · Agent identity: the chain behind one agent action

The F3 incident again. At 14:02 UTC a Datadog monitor reports that **payment-service** (production) is failing **14%**
of requests against a 1% SLO. The incident agent investigates and proposes rolling `v4.18.0` back to `v4.17.2`. At
14:09 the rollback reaches Kubernetes. This POC asks one question of that moment, in three architectures: **who was
acting, and on whose authority?**

It is a thin, self-contained extension of the F3 headless runtime. It keeps F3's scenario and principals, drops
everything that is not about identity (reasoning, events, durability), and adds the identity chain: event provenance,
agent registry, delegation with narrowing, attested runtimes, a token broker, tool-facing identities, simulated tools
with their own audit logs, and a revocation lever per layer.

## What it demonstrates

| Concept | Where | Experiment |
|---|---|---|
| Invoker authenticated at ingress; event provenance recorded separately from the sender | `aid/directory.py`, `aid/contracts.py` (`EventProvenance`) | I1 |
| Delegation, not impersonation: subject + nested actor chain (RFC 8693 shape) | `aid/trust.py` | I1, I5 |
| Scopes are an intersection; every agent -> agent hop narrows again; declared edges; depth limit | `aid/trust.py`, `config/principals.yaml` | I2 |
| Non-delegable authority (`deploy:rollback`) reaches an execution only through an approval bound to one call | `aid/approvals.py`, `aid/gateway.py` | I1, I7 |
| Sender-constrained execution tokens (`cnf` = the runtime's SPIFFE id); workload attestation | `aid/trust.py`, `aid/attestation.py` | I3, I4 |
| Re-exchange (never extend) after a pause | `aid/trust.py`, `aid/platform.py` | I7 |
| Token broker: one tool identity per capability class, audience-bound, 10-minute credentials | `aid/broker.py`, `config/tool_identities.yaml` | I1, I4 |
| Each tool keeps its own audit log of only what it is shown | `aid/tools.py` | I1, I5 |
| Hash-chained platform audit with the whole chain and revocation handles; tamper detection | `aid/audit.py`, `aid/gateway.py` | I1 |
| A revocation lever per layer: delegation, invoker credential, agent, workload, tool identity | `aid/platform.py` | I3 |
| Baselines: one shared service account; the agent handed the user's token | `aid/baselines.py`, `config/shared_sa.yaml` | I1–I7 |

## The seven experiments

| Id | Question | What is counted |
|---|---|---|
| I1 | Attribution: can each record answer the nine audit questions? | Questions answered from the tool's own log and from the platform record, per mode; distinct Kubernetes principals for three agents; tamper detection |
| I2 | Confused deputy: release-guard asks incident-intel to roll back | Decision, physical rollbacks, whether the originator is visible, scope narrowing per hop |
| I3 | Revocation drill: five concurrent executions, one lever pulled at minute 5 | Executions affected, minutes to effect, per layer; shared-account rotation |
| I4 | Replay: tokens and credentials used from the wrong place or time | Accepted or rejected, and why |
| I5 | Impersonation vs delegation for the same action | Is the agent's action distinguishable from Maya's own? Identity fields lost |
| I6 | Privilege accumulation (derived from configuration, not measured) | Shared-account permissions vs per-capability identities |
| I7 | Pause and re-exchange: Maya's delegation revoked during an approval wait | Whether the approved rollback still runs, re-exchanged vs extended |

## Real and simulated

| Real code | Simulated |
|---|---|
| Ingress authentication, token exchange, delegation and narrowing, attestation checks, token broker, capability gateway, approvals, hash-chained audit, revocation levers, the three identity modes | The directory and identity provider (`config/principals.yaml`), SVID issuance, Kubernetes / Jira / Slack / telemetry and their logs (`aid/tools.py`), the clock, the agents' plans (`aid/agents.py`) |

The agents are deterministic plans **on purpose**. F3 covered reasoning; T1's claims are about who acts and with what
authority, which must hold whatever a model proposes. How each baseline records: the shared-account and impersonation
baselines write the identity their own model carries (the shared account, or the user's token subject), plus the action
and the approver. A richer application log is always possible; it is not an identity model, and nothing enforces it.

## Run it

Python 3.12 and [uv](https://docs.astral.sh/uv/). No model, no network, no Docker.

```bash
uv sync --group dev
uv run aid demo                                    # the rollback, with every identity in the chain printed
uv run pytest                                      # architecture, authority, revocation, audit, I1–I7 + G01–G11
uv run aid experiments --run-id 2026-10-03-recorded   # I1–I7 -> runs/<run-id>/ (refuses if a frozen file changed)
```

The published run is `runs/2026-10-03-recorded/` (named in `runs/PUBLISHED`): `summary.md`, `facts.json` (every number
the articles use), `I1…I7.json`, `checks.json` (41 declared checks with ids, kinds and arms), `recorded.json` (when, under which freeze), `audit.jsonl` (the chain-mode platform audit of I1), `tool-logs.json`
(what each tool recorded in that run), `story.json` (the article's 14:09 event-triggered rollback, recorded end to end; `aid demo`
prints the same run), `manifest.json` (config hashes) and `scenarios/`: one folder per scenario (30), each with
`scenario.json` (input, expected, observed, outcome, the checks it answers), `audit.jsonl` (that scenario's platform audit chain),
`tool-logs.json` (what each tool was shown) and `effects.json`. The Lab Console (`make console` in the package root,
`results/lab-console.html`) is generated from these folders. Running it twice produces byte-identical files (`make verify`).

## Method and evidence

`method.md` (the controlled comparison, the nine questions, the declared criteria and the freeze), `real_vs_simulated.md`,
`proof/preregistration.toml`, `proof/FREEZE.json`, `proof/DEVIATIONS.md`.

## Layout

```text
config/             principals (humans, heads, runtimes, agents), capabilities, tool identities, shared account, policies
aid/contracts.py    EventProvenance, Actor (act chain), ExecutionToken, ToolCredential, CapabilityCall, Decision
aid/directory.py    principals, ingress authentication, revocation state
aid/attestation.py  simulated SVIDs, rotation, quarantine
aid/trust.py        exchange, delegate, re-exchange, validate
aid/broker.py       per-capability, audience-bound, 10-minute tool credentials
aid/gateway.py      the only path to a tool; writes the chain into the audit
aid/tools.py        Kubernetes, Jira, Slack, telemetry, each with its own grants and log
aid/approvals.py    approvals bound to one call digest
aid/audit.py        hash-chained platform audit
aid/baselines.py    shared service account; user-token impersonation
aid/platform.py     composition root, runtime behaviour, revocation levers
aid/agents.py       deterministic agent plans (propose only)
aid/experiments.py  I1–I7, the per-scenario record, the 41 checks and the facts the articles read
aid/freeze.py       declared criteria and the freeze
tests/              architecture, authority, revocation, audit
```

See `architecture.md` for the design.
