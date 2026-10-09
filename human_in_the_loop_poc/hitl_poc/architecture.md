# T3 POC architecture

The POC is a thin extension of the incident system from Headless AI, Agent Identity and Authorization & Policy. It
consumes identity and policy as inputs and adds the approval protocol in three interchangeable forms. The figure
`tech-poc-architecture` in the technical edition draws this page.

```text
 monitor event ──▶ Platform.receive (dedupe on source+id, join on fingerprint)
                        │
                        ▼  automatic, through the gateway (policy ALLOW)
              reads · correlateIncidentEvidence · createIncident · recommendRollback
                        │
                        ▼  Platform.propose
              ActionProposal ── action_digest = sha256(canonical(capability, target, arguments, preconditions, policy, risk))
                        │      incident_id · delegation_chain_ref · policy decision id · expires_at (TTL 60 min)
              PolicyEngine.evaluate ──▶ DENY → REJECTED │ ALLOW → execute │ REQUIRE_APPROVAL → PENDING_APPROVAL
                        │
              the approval request goes out over the chat channel (Arm.request: what the human is shown)
                        │
   ┌────────────────────┼──────────────────────────────────────────────────────────────────────────────┐
   │ A · NaiveBoolean   │ store[request] = {approved, clicked_by: chat handle}; resume runs the agent's    │
   │                    │ pending action if approved is true (policy still enforced per call)              │
   │ B · ActionBound    │ ApprovalService.decide_as(principal from credential or linked chat user):        │
   │                    │   digest · expiry · eligibility (role, request chain, deployment author) · quorum │
   │                    │ resume: approved · request binding · digest · not expired · not used → call →    │
   │                    │   mark used (no compare-and-set, no idempotency key)                             │
   │ C · Revalidated    │ B's decision path; resume through ExecutionGate.execute:                          │
   │                    │   request binding → CAS APPROVED → REVALIDATING (consume) → revalidate all of:    │
   │                    │   agent enabled · runtime registered · delegation active · not expired · digest · │
   │                    │   policy version · policy still requires it · resource state · approver eligible  │
   │                    │   → REJECTED | EXPIRED | REAPPROVAL_REQUIRED | EXECUTING                          │
   │                    │   → mint a narrow credential → CapabilityGateway.invoke(idempotency key)          │
   └────────────────────┴──────────────────────────────────────────────────────────────────────────────┘
                        │
              Enterprise (simulated Kubernetes, ITSM) → effects ledger (who wrote, from → to, changed?)
              AuditLog (hash chain) · transitions table · each arm's own records
```

## Modules

| File | Owns |
|---|---|
| `hitl/contracts.py` | `Action` and its digest, `ActionProposal`, `ApprovalDecision`, `ApprovalArtifact` (the POC's approval contract; no secrets) |
| `hitl/policy.py` | the policy decision point: ALLOW · DENY · REQUIRE_APPROVAL, decision ids, the two-person rule (v8), fail closed |
| `hitl/approvals.py` | the state machine (compare-and-set), eligibility, quorum, escalation, expiry, arm B's `mark_used` |
| `hitl/gate.py` | arm C's execution gate: request binding, atomic consume, revalidation, credential minting, reconciliation; the capability gateway |
| `hitl/arms.py` | the three protocols behind one interface: `request`, `click`, `api_decide`, `resume`, `sweep`, `records` |
| `hitl/platform.py` | ingress, the incident workflow, `propose`, `presented_action` (what the agent presents on resume) |
| `hitl/enterprise.py` | the simulated systems and the effects ledger |
| `hitl/base.py` | the clock, the directory (identity context), the hash-chained audit |
| `hitl/scenarios.py` | the 30 preregistered scenarios, the step recorder, the oracle scoring and the 16-question reconstruction |
| `hitl/proofpack.py` · `freeze.py` · `verify.py` | facts, checks, story, manifest; the freeze guard; byte-for-byte verification |
| `hitl/suite.py` | the arm-C conformance suite (30 regression tests) |
| `hitl/api.py` · `inbox.html` | the HTTP surface and the approval inbox |

## Decisions

1. **The proposal is the unit of approval.** It is created once and never edited. A different action is a different
   request with a different digest: arm C turns a mutated presentation into `REAPPROVAL_REQUIRED` plus a new request.
2. **The digest covers the side effect, not the story.** Reason and evidence inform the human; they are not hashed.
3. **The approver comes from the credential or a linked chat identity.** A click from an unlinked chat user is nobody.
   A claimed identity is recorded as `approval.claim_ignored`.
4. **The state machine is a table plus compare-and-set.** Entering `REVALIDATING` is the single use: one worker wins.
5. **Resume re-derives everything.** The gate reads the approval store, the directory, the policy and the live system;
   it never reads model output or trusts a stored boolean.
6. **Fail closed.** No policy answer, no approval service, unknown capability, expired, revoked: no execution.
7. **Deterministic by construction.** Fake clock, derived ids, scripted humans, simulated systems: replay is byte for byte.

## Not implemented (described in the technical edition)

A durable workflow engine for long waits (a pause is a clock advance), out-of-band (CIBA) or step-up approver
authentication, signed approval records, real Slack request signing, leases for in-flight executions, multi-agent
approval chains and a model-backed reasoner.
