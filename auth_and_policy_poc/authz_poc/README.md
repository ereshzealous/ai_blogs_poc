# authz_poc: policy before every tool call

The POC for **T2 · Authorization & Policy for AI Agents** (Production AI Engineering, part 5). Same incident as the
Headless AI and Agent Identity POCs: at 14:02 a Datadog monitor fires for payment-service (14% errors against a 1% SLO,
`v4.18.0` shipped 13 minutes earlier), and `incident-agent-prod`, acting for `sre-team`, investigates and remediates
INC-4471 (SEV-1). This time every tool call goes through a policy enforcement point before it can reach a tool.

```text
Datadog event → incident agent → identity → gateway (PEP) → policy (PDP + PIP)
             → ALLOW / ALLOW_WITH_CONSTRAINTS / ALLOW_WITH_APPROVAL / DENY
             → execution-time re-check → one-call credential → tool → audit receipt
```

Standard library only (Python 3.11+ for `tomllib`). No network, no Kubernetes, no model: the agent is scripted, because
the POC is about the policy boundary, not about reasoning. The clock is the scenario's, so everything is deterministic.

## Run it

```bash
cd authz_poc
python3 -m authz.run                       # the incident, the sweep, the invariants → runs/2026-09-29-recorded/
python3 -m unittest discover -s tests -v   # every test, four layers (L1–L4)
python3 -m authz.verify                    # one JSON summary: invariants, layers, replay, audit chain, determinism
```

`authz.verify` evaluates the 14 invariants against today's code, runs the suite twice and compares the results, replays
the scenario into a fresh directory and compares every output byte for byte with the recorded run, re-hashes the audit
chain from the file alone, and exits non-zero if anything fails. It also writes `tests.json`, `manifest.json` and
`verification.json` into the run directory. From the article folder, `python3 tools/build_lab_console.py` rebuilds the
Lab Console (`results/lab-console.html`) and `python3 tools/verify_publication.py` checks that both articles print the
recorded values.

## What it proves

Within the modeled architecture, and tested:

- **Identity is not authorization.** One identity, ten proposed calls, four kinds of answer.
- **Tool access is not action permission.** Reaching the Kubernetes tool authorizes nothing by itself.
- **RBAC sets the ceiling, ReBAC finds the authority, ABAC applies the moment.** Context only ever restricts; delegation
  is an intersection, never a union, and can't manufacture ownership (the confused deputy is denied).
- **The agent never grades its own homework.** Every attribute that can loosen a decision comes from a system of record
  or the platform's evidence evaluator; asserted confidence, urgency or a claimed evidence score changes nothing.
- **Unknown context fails closed**, including a failing or nonsensical policy engine.
- **Constraints are enforced by the gateway.** Restart three pods, get one; query restricted logs, get them redacted.
- **Authorization is not approval.** Production rollback returns ALLOW_WITH_APPROVAL; approval opens only for that,
  is bound to the exact call, the incident, the policy version and a deadline, is single-use, can't be given by the
  requester, and is followed by an execution-time re-check. An approval can never turn a DENY into anything.
- **Non-bypassability, credential half.** Tools refuse any call without a single-use credential the broker issued for
  exactly that call after a permitting decision.
- **Every decision is reconstructable and the run is replayable**, from a hash-chained log whose tampering is evident.

## What it deliberately does not prove

- **The network half of non-bypassability.** That the runtime has no route to the real APIs is a deployment property.
- **A real model, IdP, token exchange or system of record.** The broker signs with a fixed key; the incident system,
  change calendar, catalog, Kubernetes, logs and dashboards are simulated.
- **That the evidence weights are right for your systems**, or performance, scale and concurrency.
- **A protected audit store.** The chain is in process: tamper-evident, not immutable. Production must ship or anchor it.
- **Human-in-the-loop.** The approval gate is deliberately thin; escalation, reminders, quorum, timeouts and intervention
  are the next article's (T3).

## The test model

| Layer | File | What it proves |
|---|---|---|
| L1 Policy unit tests | `tests/test_l1_policy.py` | The PDP alone: decision table, freeze case, combining precedence, condition semantics, evidence evaluator, fingerprint, caller view |
| L2 Authorization invariants | `tests/test_l2_invariants.py` | The 14 named invariants below, one test each, one subtest per named case |
| L3 Gateway integration tests | `tests/test_l3_gateway.py` | The real enforcement path with counting tools: denied calls never execute, constraints are applied, approvals wait, stale authority is re-checked, receipts are written, tools can't be reached around the gateway, PDP failure means DENY |
| L4 Recorded replay | `tests/test_l4_replay.py` | The incident re-run and compared byte for byte with the recorded run; the published facts re-derived from the artifacts |

## The 14 named production authorization invariants (`authz/invariants.py`)

| Id | Invariant |
|---|---|
| AUTHZ-INV-01 | Deny by default |
| AUTHZ-INV-02 | Role ceiling cannot be exceeded |
| AUTHZ-INV-03 | Tool access is not action permission |
| AUTHZ-INV-04 | Resource authority is required |
| AUTHZ-INV-05 | Delegation is an intersection, never a union |
| AUTHZ-INV-06 | Delegation scope and lifetime are enforced |
| AUTHZ-INV-07 | Context may restrict, never manufacture authority |
| AUTHZ-INV-08 | Agent assertions never loosen authorization |
| AUTHZ-INV-09 | Missing or unknown security context fails closed |
| AUTHZ-INV-10 | Same identity may produce different contextual decisions |
| AUTHZ-INV-11 | Production rollback cannot silently auto-execute |
| AUTHZ-INV-12 | Approval cannot widen DENY |
| AUTHZ-INV-13 | Authorization is rechecked at time of use |
| AUTHZ-INV-14 | Every decision is reconstructable and replayable |

The count is fixed at 14; cases under an invariant may grow. AUTHZ-INV-02, 05 and 07 are deliberate mutation tests
(context rules removed, delegation widened, permissive rules injected) showing the boundary is layered.

## The policy files that matter

| File | Layer | What it holds |
|---|---|---|
| `config/principals.toml` | RBAC | Agents, humans and roles. An action no role lists is never allowed |
| `config/relationships.toml` | ReBAC | Who owns what, and the bounded, expiring, revocable team → agent delegation |
| `config/policy.toml` | ABAC | Versioned guard rules (`authz-2026-09-29.2`): DENY, ALLOW_WITH_APPROVAL, ALLOW_WITH_CONSTRAINTS; each with an audit reason and a caller-safe code, message and next step |
| `config/catalog.toml` | Catalog | Actions (kind, risk), resources (tier, data classification), the environments and severities the PDP recognises |
| `scenario.toml` | Scenario | The incident, the ten proposed calls, the approvals and the context sweep, each with its expected outcome |

## Code

| Path | Role |
|---|---|
| `authz/model.py` | The `Request` (principal, acting-for, action, resource, environment, context, arguments) and the `Decision` |
| `authz/pip.py` | Policy information point: attributes from the systems that own them, with their sources |
| `authz/evidence.py` | Diagnosis evidence score, computed from platform-observed signals only |
| `authz/pdp.py` | Policy decision point: default-deny, RBAC → ReBAC → ABAC, fail-closed combining |
| `authz/pep.py` | Policy enforcement point, the tool gateway: constraints, approvals, binding checks, re-checks, fail-closed on PDP error |
| `authz/broker.py` | Credential broker: single-use credentials for one call, only after a permitting decision |
| `authz/tools.py` | Simulated Kubernetes, logs and dashboards behind credential-checking endpoints. They know nothing about policy |
| `authz/approvals.py` | The thin approval gate |
| `authz/audit.py` | Hash-chained decision log |
| `authz/run.py` · `invariants.py` · `record_tests.py` · `verify.py` | The run, the 14 invariants, the test recorder, the verifier |

## Recorded artifacts (`runs/2026-09-29-recorded/`)

| File | What it is |
|---|---|
| `decisions.jsonl` | The hash-chained audit log: every decision (with arguments, delegation chain, attribute sources, audit reason and caller view), approval and execution (with its credential) |
| `receipt.json` | The production rollback, reconstructed from the log |
| `timeline.json` / `.md`, `sweep.json` / `.md`, `transcript.txt` | The ten calls, the context sweep, the run as printed |
| `expectations.json` | Every recorded outcome against the scenario's `expect` |
| `invariants.json` | The 14 invariants and their named cases |
| `facts.json` | Every number the articles use, derived from the log |
| `tests.json`, `manifest.json`, `verification.json` | Written by `authz.verify`: every test and subtest by layer, the input hashes, the verification summary |

## How figures are tied to the run

The POC figures (decision board, timeline, receipt, sweep, replay, three cases, provenance) are generated from these
artifacts by `../diagrams/build_*.py`; nothing measured is typed into them. `../docs/TRACEABILITY.md` maps every
article claim to its code, test, artifact and figure.
