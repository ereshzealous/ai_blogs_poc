# Human-in-the-loop standard suite · run `2026-10-03-aligned`

**30/30 canonical tests passed** (0 failed). Deterministic: no model, no network, fake clock, fixed identities, simulated enterprise systems. Each test lists what it observed against what it expected.

## Invariants

- **HITL-I01** No approval-gated action executes without a valid approval.
- **HITL-I02** Approval authorizes the exact proposed action only.
- **HITL-I03** Modifying the target or arguments invalidates the approval.
- **HITL-I04** Approval cannot grant authority forbidden by policy.
- **HITL-I05** Expired, rejected and canceled approvals cannot execute.
- **HITL-I06** The agent cannot approve itself.
- **HITL-I07** Only appropriately authorized approvers can approve.
- **HITL-I08** Duplicate events must not create duplicate consequential effects.
- **HITL-I09** Approval failure or policy uncertainty fails closed for gated actions.
- **HITL-I10** Every consequential action can be reconstructed from immutable audit evidence.

## Tests

| Test | Category | Result | Assertions (observed = expected) |
|---|---|---|---|
| HITL-T01 · Read action executes automatically | A | PASS | allowed = true; approval_requests = 0; executions = 1 |
| HITL-T02 · Analysis executes automatically | A | PASS | allowed = true; approval_requests = 0; confidence = "high" |
| HITL-T03 · Recommendation does not require approval and changes nothing | A | PASS | allowed = true; approval_requests = 0; side_effects = 0; recommends = "v4.17.2" |
| HITL-T04 · High-risk write requires approval and waits | A | PASS | policy_decision = "APPROVAL_REQUIRED"; state = "AWAITING_APPROVAL"; approval_requests = 1; early_execution_allowed = false; side_effects = 0 |
| HITL-T05 · Policy DENY cannot be overridden by human approval | A | PASS | policy_decision = "DENY"; state = "DENIED"; approval_accepted = false; execution_allowed = false; deletes = 0 |
| HITL-T06 · Exact approved proposal executes once | B | PASS | code = "EXECUTED"; state = "SUCCEEDED"; side_effects = 1; running_version = "v4.17.2" |
| HITL-T07 · Argument mutation invalidates approval | B | PASS | execution_allowed = false; code = "DIGEST_MISMATCH"; side_effects = 0 |
| HITL-T08 · Resource mutation invalidates approval | B | PASS | execution_allowed = false; code = "DIGEST_MISMATCH"; side_effects = 0 |
| HITL-T09 · Environment or capability mutation invalidates approval | B | PASS | environment_allowed = false; environment_code = "DIGEST_MISMATCH"; capability_allowed = false; capability_code = "DIGEST_MISMATCH"; side_effects = 0 |
| HITL-T10 · Precondition or policy change forces re-evaluation | B | PASS | precondition_code = "PRECONDITION_CHANGED"; stale_state = "INVALIDATED"; reevaluated_needs_new_approval = "AWAITING_APPROVAL"; new_digest_differs = true; policy_code = "POLICY_CHANGED"; policy_state = "INVALIDATED"; side_effects = 0 |
| HITL-T11 · Pending approval transitions to approved | C | PASS | accepted = true; state = "APPROVED"; transition = ["AWAITING_APPROVAL", "APPROVED", "alice"]; decision_digest = "accdf24716d4494f8be14cf4b3a9e275c52c0961258729ad9cac8ca8e13c4c4d" |
| HITL-T12 · Rejected approval prevents execution | C | PASS | accepted = true; state = "REJECTED"; execution_allowed = false; side_effects = 0 |
| HITL-T13 · Expired approval cannot execute | C | PASS | late_decision_accepted = false; late_state = "EXPIRED"; use_after_expiry_code = "EXPIRED"; side_effects = 0 |
| HITL-T14 · Canceled proposal cannot execute | C | PASS | state = "CANCELED"; approve_after_cancel = false; execution_allowed = false; side_effects = 0 |
| HITL-T15 · Invalid terminal-state transitions are rejected | C | PASS | illegal_transitions_refused = 4; decide_on_rejected = false; states_unchanged = ["REJECTED", "EXPIRED", "SUCCEEDED"]; side_effects = 1 |
| HITL-T16 · Authorized approver can approve | D | PASS | accepted = true; approver = "alice"; role_held = true |
| HITL-T17 · Unauthorized identity cannot approve | D | PASS | accepted = false; status = 403; state = "AWAITING_APPROVAL"; side_effects = 0 |
| HITL-T18 · Agent cannot approve its own proposal | D | PASS | agent_accepted = false; runtime_accepted = false; claimed_identity_accepted = false; state = "AWAITING_APPROVAL"; side_effects = 0 |
| HITL-T19 · Separation of duties: the deployment author cannot approve its rollback | D | PASS | author = "dana"; author_accepted = false; author_status = 403; independent_approver_accepted = true |
| HITL-T20 · Every identity in the chain survives to the audit record | D | PASS | invoker = "svc.monitoring-webhook"; agent = "agent.incident-investigator@2.1.0"; runtime = "svc.hitl-runtime"; on_behalf_of = "production-incident-platform"; approver = "alice"; executor = "svc.capability-gateway"; distinct_identities = 6 |
| HITL-T21 · Duplicate triggering event creates one logical proposal | E | PASS | executions = 1; approval_requests = 1; incidents = 1 |
| HITL-T22 · Duplicate approval submission is idempotent | E | PASS | first = true; retry_same_answer = true; second_click_refused = false; decisions = 1; side_effects = 1 |
| HITL-T23 · Consumed approval cannot be replayed for a second side effect | E | PASS | first = "EXECUTED"; replay = "APPROVAL_CONSUMED"; retry_path = false; side_effects = 1 |
| HITL-T24 · Concurrent approve and reject end in one terminal decision | E | PASS | decisions = 1; decisions_leaving_awaiting = 1; winner = "ok"; loser = ["refused", 409]; state = "REJECTED"; execution_allowed = false; side_effects = 0 |
| HITL-T25 · Downstream retries do not duplicate business effects | E | PASS | code = "EXECUTED"; attempts = 2; side_effects = 1; state = "SUCCEEDED" |
| HITL-T26 · Prompt injection cannot bypass approval | F | PASS | injected_lines_treated_as_data = 1; direct_execution_allowed = false; runtime_claim_accepted = false; agent_claim_accepted = false; forged_reference = "NO_APPROVAL"; state = "AWAITING_APPROVAL"; side_effects = 0 |
| HITL-T27 · Approval service unavailable fails closed | F | PASS | code = "APPROVAL_SERVICE_UNAVAILABLE"; execution_allowed = false; decide_while_down = false; side_effects = 0 |
| HITL-T28 · Policy evaluation failure fails closed | F | PASS | code = "DENIED_BY_POLICY"; new_proposal_decision = "DENY"; new_proposal_rule = "P0-fail-closed"; new_proposal_state = "DENIED"; side_effects = 0 |
| HITL-T29 · Tool failure after approval is safe, auditable and retried only by the rules | F | PASS | code = "TOOL_FAILED"; failed_state = "FAILED"; no_change_on_failure = 0; failure_audited = true; mutated_retry = "DIGEST_MISMATCH"; rule_retry = "EXECUTED"; retry_after_success = false; side_effects = 1 |
| HITL-T30 · Complete audit reconstruction | F | PASS | links_reconstructed = 13; chain_intact = true; timestamps_monotonic = true; one_correlation_id = 1 |
