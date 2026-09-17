# Design

The names, states and rules drawn in the article's figures come from this file.

## The boundary

```text
Slack · Web · CLI · REST · Events   (channel adapters + renderers)
                 │  CapabilityRequest 1.0
                 ▼
   capability contract · identity resolution · interaction state      (this POC)
                 │  PlatformService (Part 2's facade)
                 ▼
   orchestration · agent runtime · context & memory · tool & action · model services   (Part 2, unchanged)
```

- The boundary validates, resolves identity, delegates and records interactions.
- It owns no workflow rule, no policy and no prompt.

## Capability

`incident.remediation`, version `1`. One capability, three operations:

| Operation | Needs | Does |
|---|---|---|
| `start` | `input.incident_id` | creates a workflow (`wf-…`) and runs it in the background, or awaits it (`wait=True`, used by the CLI and tests) |
| `get` | `workflow_id` | returns the current capability state and available actions |
| `act` | `workflow_id`, `action_id`, optional `binding` | takes an available action: `approve-remediation`, `reject-remediation`, `retry` |

### Statuses

`RUNNING` · `WAITING_APPROVAL` · `COMPLETED` · `REJECTED` · `FAILED`. They mirror the platform's workflow status; the
boundary invents none of them.

### Errors

`INVALID_REQUEST` · `UNSUPPORTED_VERSION` · `UNKNOWN_CAPABILITY` · `UNKNOWN_IDENTITY` · `FORBIDDEN` · `NOT_FOUND` ·
`CONFLICT`. Each adapter maps them to its own form (HTTP status, ephemeral Slack message, CLI exit code).

### Versioning

- `schema_version` is the envelope: `1.x` is served, a different major version is `UNSUPPORTED_VERSION`, checked before
  the shape.
- `capability_version` (`incident.remediation@1`) versions the meaning of `state` and `available_actions`.

## What a channel may and may not say

| The channel says | The boundary decides |
|---|---|
| `actor.channel` and `actor.channel_subject` (who it authenticated) | `principal_id` and the roles |
| `channel_context.thread_ref` (its own session) | `workflow_id` |
| `channel_context.idempotency_key` (its own retry key) | whether that key already has a workflow |
| `action_id` and the `binding` it displayed | whether that action is available, and to this principal |

Every contract model is `extra="forbid"`, so `approved: true`, `principal_id` or `roles` in a request is an
`INVALID_REQUEST`.

## Identity

| Channel | Subject it authenticates | Example |
|---|---|---|
| `slack` | Slack user id | `U04ALICE` → `alice` |
| `web` | OIDC subject | `oidc\|alice-92ab` → `alice` |
| `cli` | device-token subject | `alice@company.example` → `alice` |
| `rest` | OAuth subject | `api\|alice` → `alice` |
| `event` | event source acting for the on-call principal | `alertmanager` + service → `alice` |

Roles come from Part 2's principal directory (`alice`: `sre`, `incident-commander`; `bob`: `developer`).

## Interaction state (`interactions.py`)

| Table | Holds | Losing it means |
|---|---|---|
| `interactions` | every request: channel, subject, principal, operation, outcome, status, trace id | the audit of who looked, not the workflow |
| `idempotency` | channel + key → workflow | a retried webhook could start a second workflow |
| `subscriptions` | which channel address wants updates for a workflow | a channel stops being told |
| `outbox` | one queued notification per subscriber per status change, with attempts | an update is not delivered |

None of it is workflow state. The platform's SQLite database holds that.

## Notifications

Each server process delivers the channels it hosts, polling the outbox every 0.5 s. A failed delivery stays `PENDING`
and is retried (50 attempts). After any command the gateway *reconciles*: for every subscriber whose last seen status
differs from the workflow's, it queues one message.

## Experiments

`H1` same capability from CLI, REST, Slack · `H2` Slack → Web → CLI across processes · `H3` change scope ·
`H4` governance per channel and forged approvals · `H5` identity and authority · `H6` rendering purity ·
`H7` the Slack adapter is killed mid-workflow. See `experiments/scenarios.py`; each writes `runs/<run>/<h>/result.json`.
