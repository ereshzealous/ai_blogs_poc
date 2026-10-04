# POC design — Capability Control Plane over real MCP

Learning 01 · ORD-4917 · design as frozen for the blind benchmark. See
`experiment/design-iterations.md` for how it got here (development set only).

## 1. What is real and what is simulated

| Real | Simulated (deterministic, labelled) |
|---|---|
| MCP servers: official Python SDK `mcp` 2.2.0, low-level `Server`, one stdio OS process per server | The enterprise systems of record: orders, payments, refunds (US + EU), shipping, CRM, promotions, helpdesk, and other business units' systems (one SQLite world) |
| MCP client: `mcp.Client(StdioServerParameters, mode="auto", cache=None)`; `server/discover` → negotiated revision measured per server | Users and roles (tier-1 / tier-2 representatives) |
| `tools/list` (paged) and `tools/call` with `_meta` | Approver: approvals are requested, never granted, in benchmark rows |
| Model: `gpt-oss:20b` via Ollama `/api/chat` with native tool calling, `truncate:false` | Background customers and orders (fixed RNG) |
| Embeddings: `nomic-embed-text` via Ollama | |
| Retrieval, registry, binding, provenance, policy, approval digests, HMAC gateway tokens, audit chain, effects ledger, scoring | |

Why simulate the systems of record? Repeatability, known expected state, fault
injection, side-effect counting, and offline replay. Nothing here claims to be an
enterprise deployment.

## 2. The estate

`poc/src/sprawl_poc/catalog/` builds three nested estates (50 ⊂ 100 ⊂ 500 tools on
17 / 21 / 43 servers). Counts by kind are in each `manifest.json`.

- **Authoritative core.** orders, payments, refunds (US), promotions, shipping, crm, helpdesk.
- **Regional implementation.** `refunds_eu`, authoritative for EU orders only.
- **Environment copies.** `refunds_staging`, `orders_staging`: same published text as
  prod; act on staging data.
- **Retired but running.** `payments_legacy.refund_charge_v1` still moves money,
  `carrier_legacy` returns stale tracking, `helpdesk_legacy` writes to a system nobody
  reads.
- **Vendor duplicates.** `paygate.refund_charge` refunds at the processor (the order
  ledger never hears about it); `shipfast.track_package`.
- **Shadow.** `marketing_ops.bulk_goodwill_refund`: reachable, never registered.
- **Other business units.** Near-miss money tools (refund a subscription invoice, a
  marketplace order or a gift card, issue a B2B credit note) and unrelated tools (HR, IT,
  procurement…), including one retired copy and one staging copy.

The handlers do **not** check authority, lifecycle, environment or approval. A retired
tool that is still running will still move money. Those are platform questions.

## 3. Capability → implementation → invocation

- **Capability:** the business job (`order.refund`). It lives in the registry.
- **Implementation:** one MCP tool that can do it (`refunds.refund_order`,
  `refunds_eu.refund_order`, …).
- **Invocation:** implementation + canonical arguments + context (requester, agent,
  environment, request id). Policy, approval and the gateway only ever see invocations.

## 4. Governance registry and trust model

`registry.yaml` per estate is platform-owned. It holds capabilities (description, owner,
authoritative implementation per region, entity type, requester-owned fields) and, per
implementation: capability, owner, lifecycle, replacement, environment, region,
side-effect class, risk, required scopes, approval rule and binding profile. Roles and
agent scope ceilings are also here.

Servers never see it. MCP annotations are recorded but never used for decisions: the
spec says annotations from untrusted servers are hints. Schemas are the exception. They
are validated against what the server declares.

Mutation happens only through a reviewed commit. The SHA-256 is pinned in the estate
manifest and the runner refuses to start on a mismatch. Who may change the registry,
and how that is audited, is organisational process; the POC shows only the pin.

## 5. The two sides of the proposal boundary

```
PROBABILISTIC / HEURISTIC (discovery)          DETERMINISTIC / AUDITABLE (governance)
 entity resolution*  ── from systems of record    bind authoritative values (binder)
 intent phrases       ── 1 model call             provenance of requester-owned values
 hybrid retrieval     ── BM25 + embeddings, RRF   schema (server-declared inputSchema)
 capability collapse  ── registry                 ordered policy P1..P9
 model selects/proposes                           approval bound to invocation digest
                    ─── proposal boundary ───     gateway: HMAC-signed tools/call
                                                  append-only hash-chained audit
                                                  ledger = execution truth
```

\* Entity resolution is itself deterministic. It sits before discovery because
discovery uses its output.

### Discovery (arm C)

1. **Entity resolution.** Order, customer, payment and ticket ids, plus emails, are
   extracted by shape and resolved through the gateway (audited `context_read`). The
   model receives a factual context block: which entities exist, their status and
   region, and the charges on an order.
2. **Intent.** One structured-output call produces 1–3 action phrases. These can only
   add retrieval queries.
3. **Retrieval.** The same hybrid index as arm B (BM25 with a light stemmer, plus
   `nomic-embed-text`, fused with RRF k=60), over what servers publish.
4. **Collapse.** Hits map to registry capabilities (unregistered hits are dropped).
   Ranks are fused across queries. An entity-type prior re-ranks: a directly referenced
   type gets more weight than an implied one. It never filters. The top 8 capabilities
   are surfaced as capability tools whose schema omits platform-bound values.

### Governance (gateway pipeline, `control_plane/gateway.py`)

0. The proposal must satisfy the capability's model-facing schema (types, enums).
1. **Bind** (`binder.py`). The authoritative implementation is chosen for the entity's
   region. Platform-owned values are bound from systems of record: the duplicate
   capture, the refundable amount, the order's customer, a single-item SKU. A
   requester's real-but-wrong value is not silently "corrected"; it goes on to policy.
   Entities that don't exist and duplicates that don't exist stop here.
2. **Provenance** (`provenance.py`). Requester-owned fields must be traceable to the
   request, or the gateway does not execute and tells the model to ask.
3. **Schema.** The canonical arguments are validated against the server-declared
   `inputSchema`. Servers validate again (the spec says servers MUST).
4. **Policy** (`policy.py`, first match wins):
   - P1 unregistered → DENY
   - P2 retired → DENY
   - P3 environment → DENY
   - P4 region → DENY
   - P5 not authoritative → DENY
   - P6 scope (user ∩ agent) → DENY
   - P7 approval rule → REQUIRE_APPROVAL
   - P8 → ALLOW
   - P9 → default DENY

   P7 also requires approval for a second distinct money-moving invocation within one
   request (an identical retry is an idempotent replay).
   Business invariant in binding: a `duplicate_charge` refund may only target a
   duplicate capture, never the original.
   The approval thresholds (refund > 250, credit > 100) were chosen to split everyday
   single-item refunds from large-ticket ones. The same refund figure appears in the
   historical work. That is a coincidence, noted here and not relied on.
5. **Approval** (`approval.py`). The digest covers implementation, canonical arguments,
   environment, requester, agent, request id and policy version. Approvals are
   single-use. The requester cannot approve their own invocation. Any change voids the
   approval.
6. **Execution.** An HMAC token is placed in `_meta["io.sprawl-poc/gateway"]`. Servers
   started with `--enforce-gateway-token` reject missing, forged, altered or replayed
   tokens (`tests/test_gateway_mcp.py`).
7. **Audit.** Every stage is appended to a hash-chained JSONL log. Tampering or deletion
   is detectable. It is tamper-evident, not tamper-proof.
8. **Next step.** Every result tells the model what the platform recorded and what it
   should do next. `finish(completed)` is rejected when the audit shows no executed
   write but a held or blocked one.

**Bypass.** In arm C the agent loop holds no MCP session. Bypass resistance is
demonstrated at the server (token verification), not assumed. The key is shared by
the gateway and the servers on one host. Key management and network isolation are
out of scope.

## 5b. Production behaviours at the tool layer

- **Clarification.** The model asks. Nothing executes: the provenance check blocks
  invented requester-owned values. The requester's answer then joins the grounding text
  for requester-owned values.
- **Correction.** For a wrong id, entity resolution reports DOES NOT EXIST. The corrected
  id in the requester's reply is resolved the same way before anything binds.
- **Human approval.** P7 creates an approval request bound to the invocation digest. The
  supervisor approves or rejects whatever is pending. A re-proposed invocation executes
  only if its digest matches an approved, unconsumed request (single-use). A rejected
  invocation stays rejected (`P7_APPROVAL_REJECTED`). The platform rejects
  `finish(needs_approval)` when no approval request exists, so "awaiting approval" is
  always backed by a real request.
- **Failure.** Side-effecting calls carry an idempotency key equal to the invocation
  digest; servers deduplicate on it. MCP calls time out after 30 s. A failing
  authoritative system never opens a side door: legacy, vendor, staging and shadow
  implementations stay denied by policy. Automatic retry and backoff are platform-layer
  (F2) concerns and are deliberately not implemented here.
- **What the benchmark simulates.** Requester replies, supervisor decisions and outages
  are written into each case before the blind run (`experiment/benchmark/cases.json`).
  The approver never reads labels.

## 6. Arms

See `experiment/preregistration.md` §3. Shared across all arms: model, playbook, finish
tool with self-validation, turn limit 10, two reminders, per-row nonce, fresh world.

## 7. Scoring

See `bench/evaluate.py` and the preregistration §5. The ledger is execution truth, and
model narration is used only for the declared outcome and read facts.

## 8. Replay

Every model request hash and raw response is stored per row. `runner --replay <dir>`
feeds the recorded responses back in order. Everything downstream of the model (MCP
servers, retrieval, binding, policy, gateway, simulated world) runs for real. Approval
ids are deterministic per row, so replayed requests match the recorded ones.

## 9. Limitations, by design

- Single-turn: clarifications are not answered, approvals are not granted.
- The provenance check is literal matching against the request text. A multi-turn
  system would ground against the transcript. It can reject a paraphrased value and
  can be fooled by a coincidental number in the text.
- One model, one machine, one simulated domain.
- Out of scope: security threats (prompt injection, compromised servers, credential
  handling).
