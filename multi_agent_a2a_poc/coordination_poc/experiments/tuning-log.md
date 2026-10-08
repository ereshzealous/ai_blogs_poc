# Dev tuning log (dev fixtures D1–D4 only)

Rule (spec §11): at most 3 prompt revisions per architecture, each logged with the dev evidence that motivated it.
Platform fixes (contracts, plumbing) apply to every architecture identically and are logged separately.
Blind fixtures B1–B8 are never run before the preregistration is frozen.

## Platform fixes

| # | When | What | Why (dev evidence) | Applies to |
|---|---|---|---|---|
| F1 | dev-smoke-1 | `RemediationProposal` / `RemediationResult`: `decision=remediate` now requires a non-null `action` (pydantic validator → the agent loop's one repair turn) | D1-B: planner returned remediate with `action: null` (workflow escalated); D1-C: remediation proposal had `action: null`, review rejected, nothing was ever authorized, coordinator still finished "remediated" (runtime recorded the state conflict) | B, C (A has no proposal contract; it writes by tool call) |
| F3 | dev-smoke-2 | Remediation contracts: `tool` (write tool or `none`) and `args` are required top-level fields; `action` is derived | With F1 the model still omitted the optional nested `action` object even after the repair turn (D1-B: `answer did not match`); constrained decoding fills required keys, drops optional ones | B, C |
| F4 | dev-smoke-3 | Tool-less planners get the action catalog (tool names, parameter names and descriptions; information only, no authority): B's diagnosis/review get the read catalog, B's planner and C's remediation agent the write catalog | D1-B: planner proposed `rollback_release(release=...)`; it had never seen the tool's parameters (A and C's agents see tool definitions natively; B's agents and C's propose-mode remediation agent hold no tools) | B, C |
| F5 | dev-smoke-3 | B's workflow validates a proposal's arguments against the tool schema; on a problem it asks the planner once more with the problems, then escalates | same run: the bad argument reached the MCP server and failed there | B (workflow-owned check) |
| F6 | dev-smoke-4 | `get_dependencies` reports the service's current replica count; `scale_service` is described as an absolute count, not a delta | D4-B: the planner set inventory-api to 2 replicas (from 4) believing it added one; no read tool exposed the current count, which the runbook's scaling rule needs | A, B, C (tool surface) |
| F7 | dev-smoke-5 | Claim-vs-ledger check at the end of a run, once: if the final answer claims a remediation and the ledger has no executed write, the component is told so (A: the agent, with up to 4 more tool turns; C: the coordinator's `finish` is refused once). Firing counted as `claim_checks` | A (dev-smoke-4 D1) and C (dev-smoke-4 D3, dev-smoke-5 D3) both claimed remediations that never executed; B cannot (its code executes) | A, C |
| F8 | dev-smoke-5 | C's remediation agent gets `read:telemetry` and the `query_metrics` / `get_dependencies` tools (current CPU and replica count) | D4-C: it planned a scale-out without being able to read CPU or the current replica count and set the count it already had (4); B's planner receives this state in its evidence bundle | C (tool partition) |
| F9 | dev-smoke-6 | Runbooks state the scaling maxima the labels already used (inventory-api ≤ 16, session-cache ≤ 12) | D4-C scaled to 20: the bound was real in the labels but invisible to every agent (label-review item 12) | A, B, C (fixture text) |
| F10 | replay check of dev-smoke-6 | C serializes artifacts into prompts with sorted keys (coordinator tool results, specialist input artifacts) | Tape replay of C missed: A2A carries data parts as protobuf `Struct`, whose map order is not preserved across the wire, so the same artifact produced differently ordered prompt text in record and replay (A and B replayed identically) | C (serialization only; reasoning unaffected) |
| F2 | dev-smoke-1 | `artifacts` primary key is (workflow_id, artifact_id) | artifact ids `art-N` collided across workflows in the shared store | C |

## Prompt revisions

| Arch | # | What | Why |
|---|---|---|---|
| shared | S1 | Category boundaries sharpened: dependency_degradation (a service it CALLS, not a dependency's release, not a client's load), db_saturation (no triggering release/change), resource_exhaustion (not traffic), capacity_surge (request volume) | dev-smoke-4: A named D2 (batch client) dependency_degradation and D4 (traffic) resource_exhaustion; C named D2 capacity_surge | A, B, C (shared block) |
| A | 1 | Investigation checklist (shared `INVESTIGATE` block) + "execute the change with the write tool before your final answer" | dev-smoke-4 D1-A: concluded from metrics without releases/changes (wrong category) and reported a flag change it never executed (state conflict) | A |
| C | 1 | Same `INVESTIGATE` block for the evidence and diagnosis agents; diagnosis "verify the leading hypothesis yourself"; coordinator "finish remediated only after a remediation artifact reports executed=true" | dev-smoke-4 D2-C: evidence agent never read orders-db logs, diagnosis accepted it; D3-C: approved proposal, coordinator finished "remediated" without the execute delegation | C |
| B | — | no prompt revision (B's evidence recipe is code; its failure D4-B was the tool-surface gap fixed by F6) | — | — |
| C | 2 | Coordinator: the execute mechanism spelled out (delegate remediation again with authorize_execution=true and the approved proposal's artifact id); remediation in propose mode: "still propose the concrete change ... just do not call a write tool" | dev-smoke-5 D2-C: propose-mode remediation answered no_action because "execution is NOT authorized"; D3-C: coordinator re-delegated remediation without authorize_execution and finished "remediated" | C |
| A | 2 | "Make at most ONE production change per incident: if it does not recover the service, escalate instead of trying another change" | dev-smoke-5 D4-A: four production changes in one incident (an unrelated config revert, two scale-outs, a failed rollback); B and C execute exactly one approved change by construction | A |

