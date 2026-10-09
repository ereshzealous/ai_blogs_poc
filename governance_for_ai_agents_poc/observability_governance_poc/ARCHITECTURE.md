# Architecture of the T5 POC

## Processes per scenario

```text
harness (lineage.run) ── starts, supervises, restarts after SIGKILL, collects, scores
 ├── deploy API       (lineage.deploysvc)  HTTP 127.0.0.1:<port>, deploy/deploy.db, fault script
 ├── approvers        (lineage.operator)   answers approval requests through the approval service
 ├── agent · target   (lineage.runtime target)      INC-4471 payment-service
 └── agent · background (lineage.runtime background) INC-4472 checkout-service, concurrent
```

## One execution

```text
trigger ─► context ─► model ─► policy ─► approval ─► tool ─► verify ─► complete
   │          │          │        │          │          │        │         │
   └──────────┴──────────┴────────┴──────────┴──────────┴────────┴─────────┘
       every step: checkpoint (state/workflow.db) · app log · spans · evidence event(s)
```

| Step | Evidence events | Notes |
|---|---|---|
| trigger | `execution.started` | trigger, invoker, on_behalf_of, agent version, workload, pins with digests |
| context | `context.accessed` per dataset | ALLOW/DENY by data scope; content digest only |
| model | `model.invoked`, `decision.proposed` | provider, model, model digest, template + digest, config, options, input digest, tokens, structured output; no reasoning |
| policy | `policy.evaluated` | id, version, document digest, rule, obligations, attributes, action digest |
| approval | `approval.requested`, `approval.decided` × n | action digest, eligibility, quorum; signature and digest checks |
| tool | `action.authorized`, `attempt.started`/`finished` × n, `attempt.reconciled`, `gateway.denied` | action id = idempotency key; attempt ids durable; before-state checkpointed |
| verify | `effect.verified` | read-back of version, revision, health; transactions for the key |
| complete | `execution.completed` + witness anchor | outcome, reason, attempts, mutations observed |
| (restart) | `workflow.resumed` | from step, previous pid, restored trace, in-flight attempts |

## Correlation keys

`execution_id` (checkpoint) · `trace_id` (W3C traceparent; restored from checkpoint after restart) · `workflow_id` ·
`policy_evaluation_id` · `approval_id` · `action_id` (= `Idempotency-Key`) · `attempt_id` (`<action>.a<n>`, numbered in
workflow.db) · `external_transaction_id` (deployment API; looked up by key).

## Stores

| Store | Owner | Holds |
|---|---|---|
| `state/workflow.db` | runtime | executions, steps, attempts |
| `state/approvals.db` | approval service | requests, signed decisions |
| `state/evidence.db` + `witness/anchors.jsonl` | evidence store | the hash chain; anchors written at each completion |
| `deploy/deploy.db` | deployment API | deployment, revisions, idempotency records, every request received (ground truth) |
| `logs/*.log`, `telemetry/spans-*.jsonl`, `telemetry/metrics-*.json` | each process | L0/L1 material |

## What differs between L0, L1 and L2

Nothing in the execution. Log lines carry `profile`: `common` (any runtime writes it), `baseline` (the outcome a runtime that
trusts the tool response declares), `governed` (the verification's conclusion). L0/L1 read common + baseline lines; L2 reads
evidence only. See `lineage/investigate.py` for the investigators' rules.
