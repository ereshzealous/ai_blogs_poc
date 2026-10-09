# F3 POC architecture

```text
 heads: event · chat · web · api · workflow · scheduler · cicd · agent
   │  native payload + channel-bound credential
   ▼
 HeadlessIngress (hai/ingress/gateway.py)
   authenticate ─▶ adapter.translate ─▶ authorize invocation ─▶ dedupe (source, event_id) ─▶ join by fingerprint
   │            └─ poison ─▶ dead_letters                                        │
   ▼ InvocationEnvelope                                                          └─▶ ExecutionView (joined)
 HeadlessRuntime (hai/runtime/service.py)
   identity (token exchange) → health → logs → traces → deployments → known → assess
   → incident → recommend → approve [pause] → execute → verify → record → notify
   │ every step: checkpoint                       │ reasoner proposes; never executes
   ▼ CapabilityCall                               ▼
 CapabilityGateway (hai/capabilities/gateway.py)  ◀── PolicyEngine (PDP), Approvals, Directory
   identity valid → registered → schema → policy → approval digest → idempotency key → execute (timeout, retries) → audit
   ▼
 World (hai/world.py): monitoring · logs · traces · deploy · itsm · chat · effects ledger
```

## Decisions

1. **The runtime knows no channel.** Adapters translate and renderers render; both import only `hai.contracts`
   (`tests/test_architecture.py`). A new head is an adapter, a renderer entry and a `consumers.yaml` line.
2. **The invoker is the credential's principal.** Payloads cannot name their own invoker. Credentials are bound to
   their channel.
3. **Two kinds of authority.** `scopes` of a principal decide what it may *invoke* (`incident:investigate`);
   `delegable` decides what an execution it starts may *do*. The execution's scopes are
   `delegable(subject) ∩ delegable(invoking workload, if acting for a human) ∩ scopes(agent)`.
4. **The fingerprint is the situation, not the delivery.** `degradation:{service}:{environment}` for every
   investigating head, so chat, web, API and workflow requests join an open investigation.
5. **One digest, two uses.** `sha256(execution, capability, arguments)` is both the approval binding and the write's
   idempotency key: an approval authorizes exactly one call, and that call can execute at most once.
6. **State is split.** Business truth (incidents, releases) lives in the world; execution state, approvals, inbox,
   idempotency records and audit live in `platform.db`.
7. **Budgets live in the gateway.** A per-execution call budget stops runaway loops regardless of the reasoner.

## Not implemented (described in the technical edition)

Leases and cancellation, circuit breakers, multi-tenancy, egress/data-classification policy, a real identity provider
and RFC 8693 wire format, concurrent evidence reads, a model-backed reasoner, streaming to human heads.
