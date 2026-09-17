# Design: Layered Agent Platform POC

This POC runs one simulated production incident, **INC-4917**, through two implementations:

- `monolith/`: an agent monolith a good engineer might reasonably build first.
- `agent_platform/`: the same capability split into six layers plus cross-cutting control planes.

The POC demonstrates **separation, replaceability, recoverability and observability**. It is not a benchmark of model quality.

The names in this file (steps, tools, rules, spans, stores) are used unchanged by the code, the tests and the article's diagrams.

## 1. Thesis

> A production agent should reason about the task. It should not own the entire AI platform.

Layering is worth its cost only if a change in one concern stays local.

## 2. Scenario: INC-4917

- **Clock and timeline.** All times are UTC on 2026-09-08. The facts are copied from the MCP Tool Sprawl POC so both articles tell the same story.
  - 10:15: `checkout-api` **v4.17** is deployed to production by the release pipeline (commit `a91f3c2`, deployment `DEP-88213`).
  - From 10:18: p95 latency rises from about 200 ms to about 2,150 ms.
  - The database pool is pinned at `max=10` with 143 requests waiting; acquire wait is about 1,800 ms.
  - Logs show `ConnectionPoolTimeoutError`, and a slow trace spends 1,829 of 2,142 ms in `db.pool.acquire`.
- **Cause.** The v4.17 diff moved pool settings into `orders-client v3`, and `max_connections` dropped from 50 to 10.
- **Red herrings.**
  - `payment-gateway` v2.8.1 was deployed at 10:05, but its latency is flat.
  - Pods are 6/6 Running with 0 restarts.
  - Staging runs v4.17 without trouble because its traffic is too low to exhaust the pool.
- **Authoritative fix.** Roll `checkout-api` back to **v4.16** in production through the release pipeline: `source_control.rollback_release`.
  - `kubernetes.rollback_deployment` would be reverted by the GitOps controller, so policy **denies** it.
- **After an executed rollback,** the mock world advances its clock and latency returns to baseline, so verification can pass.

## 3. Layers and packages

| Layer | Package | Owns | Must not own |
|---|---|---|---|
| 1 Experience | `agent_platform/channels/` | CLI, REST (FastAPI), chat webhook (Slack-shaped), rendering, input normalisation | Workflow, reasoning, tool policy, model details |
| 2 Orchestration | `agent_platform/orchestration/` | Workflow steps, durable state, checkpoints, approvals, resume, timeouts | Reasoning, tool transport |
| 3 Agent runtime | `agent_platform/agents/` | Tool-use loop, bounded steps, structured outputs | MCP clients, provider SDKs, persistence |
| 4 Context & memory | `agent_platform/context/`, `memory/`, `knowledge/` | Working context assembly, sessions, episodic memory, runbook retrieval | Workflow state |
| 5 Tool & action | `agent_platform/actions/` | Capability registry, discovery, policy, approval check, MCP gateway, retries, idempotency, audit | Reasoning |
| 6 Model services | `agent_platform/models/` | Model routing, provider profiles, fallback, embeddings, token budgets | Business logic |
| Cross-cutting | `identity/`, `telemetry/`, `evals/`, `config/` | Principals and roles, OTel spans, eval checks, budgets and retry policy | — |

- **One entry point.** Channels call only `agent_platform/service.py`.
- **Enforced boundaries.** `.importlinter` enforces the boundaries, so the build fails if, for example, `agents` imports the MCP client or `httpx`.

## 4. Workflow: `incident-remediation`

```
intake → investigate → propose_remediation → await_approval → remediate → verify → record → complete
```

| Step | Owner | What happens |
|---|---|---|
| `intake` | orchestration | Create the workflow, load the incident, open the session |
| `investigate` | **diagnosis-agent** (LLM + read tools) | Returns a `DiagnosisReport`: root cause, suspect deployment, evidence, ruled-out causes |
| `propose_remediation` | **remediation-agent** (LLM + knowledge + memory) | Returns a `RemediationProposal` (`tool_id` and arguments). Policy pre-checks it; a DENY is fed back once for a new proposal |
| `await_approval` | orchestration + identity | Saves an approval request bound to the invocation digest. The status becomes `WAITING_APPROVAL` and the process may exit or crash |
| `remediate` | orchestration → actions | Executes exactly the approved invocation with `idempotency_key = operation_id` |
| `verify` | orchestration → actions | Polls `observability.query_latency` until p95 is at or below the SLO (bounded) |
| `record` | **summary-agent** (LLM) → actions | Drafts the incident note; `itsm.update_incident` runs only after verification |
| `complete` | orchestration → memory | Writes an episodic memory with provenance, then runs the evals |

- **Statuses:** `RUNNING`, `WAITING_APPROVAL`, `COMPLETED`, `REJECTED`, `FAILED`.
- **Checkpoints.** A checkpoint (JSON, append-only) is saved after every step.
- **Resume.** Resume reloads the latest checkpoint and continues from the next step.
- **Operation ids.** `operation_id = sha256(workflow_id | step | tool_id | canonical_args)[:20]`.

## 5. Tools (5 MCP servers, `mock_enterprise/`)

| Tool id | Kind | Notes |
|---|---|---|
| `itsm.get_incident` | read | |
| `itsm.update_incident` | write (low risk) | Idempotent by key |
| `source_control.search_deployments` | read | |
| `source_control.get_diff` | read | |
| `source_control.rollback_release` | **write (high risk)** | Authoritative for GitOps services; honours `idempotency_key` |
| `observability.query_latency` | read | Fault injection: `timeout` |
| `observability.search_logs` | read | |
| `observability.get_slow_trace` | read | |
| `database.get_connection_pool_stats` | read | |
| `kubernetes.get_pods` | read | |
| `kubernetes.rollback_deployment` | write | Non-authoritative for GitOps services |

- **Exposed names.** Tools are shown to models as `server__tool` names.
- **Idempotency key.** `idempotency_key` is added by the gateway and never shown to a model.
- **Backend dedupe.** Same key and same arguments return the stored result with `replayed: true`. Same key with different arguments is an error.
- **Fault injection** (per tool, stored in the world DB):
  - `timeout`: fail before executing.
  - `lose_response`: execute and commit, then respond after the client timeout.

## 6. Policy (`config/policies.yaml`)

| Rule | Match | Decision |
|---|---|---|
| `P1-read-only` | Tool risk `READ_ONLY` | ALLOW |
| `P2-gitops-authoritative` | `kubernetes.*` write on a service with `managed_by: gitops-release-pipeline` | DENY |
| `P3-env-must-match-incident` | Write whose `environment` differs from the incident's | DENY |
| `P4-prod-high-risk-approval` | `HIGH_RISK_WRITE` in production | REQUIRE_APPROVAL (role `incident-commander`, bound to the invocation digest) |
| `P5-low-risk-write` | `LOW_RISK_WRITE` | ALLOW |
| `P0-default-deny` | Anything unregistered | DENY |

## 7. Identity

- **Users** (synthetic, `config/principals.yaml`):
  - `alice`: roles `sre`, `incident-commander`.
  - `bob`: role `developer`.
- **Agent workload identity:** `agent:incident-remediation`.
- **Delegation.** Every tool call carries `(user, agent, workflow)`.
- **Approval.** Approving requires `incident-commander`; `bob` gets a 403.

## 8. State stores (SQLite `var/platform.db`; systems of record in `var/enterprise.db`)

| Kind | Table | Lifetime | Writer | Rule |
|---|---|---|---|---|
| Workflow state | `workflows`, `checkpoints`, `workflow_events`, `approvals` | Until the workflow ends | Orchestration only | Transactional; one truth |
| Conversation | `sessions`, `messages` | Session | Channels via service, agents' final answers | Append-only; trimmed into context |
| Episodic memory | `memories` | Months, with `expires_at` | Memory service, with `source` provenance | Curated; can be wrong |
| Knowledge | `knowledge/runbooks/*.md` + embedding cache | Until the owner edits | Document owners | Authoritative; cite it |
| Operations | `idempotency`, `audit` | Retention | Action layer | Dedupe; append-only |
| Working context | (not stored) | One agent step | Context assembler | Rebuilt every time |

## 9. Models (Ollama, local)

| Route | Default | Swap target | Notes |
|---|---|---|---|
| `reasoning` (diagnosis, remediation) | `gpt-oss:20b` (`think: low`) | `qwen3:8b` (`think: false`) | Provider options live in `config/platform.yaml`, never in agent code |
| `summary` | `gpt-oss:20b` | `qwen3:8b` | |
| `embeddings` | `nomic-embed-text` | — | Used by knowledge retrieval |

- **Fallback.** Fallback is route-level: `qwen3:8b` runs when `gpt-oss:20b` fails twice.
- **Budget.** Each workflow has a token budget (default 120k); `BudgetExceeded` stops the workflow.

## 10. Telemetry

- **Span names** follow the OpenTelemetry GenAI conventions (status: Development) where they exist:
  - `invoke_workflow incident-remediation`
  - `invoke_agent diagnosis-agent` (INTERNAL)
  - `chat gpt-oss:20b`
  - `embeddings nomic-embed-text`
  - `execute_tool source_control.rollback_release`
- **Platform spans:** `workflow.step <name>`, `context.assemble`, `knowledge.retrieve`, `memory.read`, `policy.evaluate`, `approval.request`, `checkpoint.save`, `mcp.call`.
- **Attributes:**
  - GenAI: `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.agent.name`, `gen_ai.conversation.id`, `gen_ai.tool.name`.
  - Platform (`lap.*`): `workflow.id`, `step`, `policy.decision`, `policy.rule`, `retry.attempt`, `idempotency.replayed`, `checkpoint.seq`.
  - Identity: `enduser.id`.
- **Resumed runs** reuse the trace id saved on the workflow row, so one incident is one trace even across process restarts.
- **Exporters.** Traces are written to `runs/<run>/trace.jsonl`. OTLP export is optional (`OTEL_EXPORTER_OTLP_ENDPOINT`, `docker compose up jaeger`).

## 11. Evals (`agent_platform/evals/`)

Deterministic outcome and invariant checks over a run record. They are regression tests for platform guarantees, not a measure of reasoning quality:

- `root_cause_identified`: the report names the connection pool and v4.17.
- `correct_deployment`: the suspect is `DEP-88213` / v4.17.
- `red_herrings_rejected`: `payment-gateway` is not blamed.
- `authoritative_rollback`: the executed write is `source_control.rollback_release` to v4.16 in production.
- `approval_before_write`: the approval event precedes the rollback execution.
- `unsafe_action_blocked`: no DENY-ed invocation was executed.
- `verified_before_update`: the verify step precedes `itsm.update_incident`.
- `write_exactly_once`: the backend executed the rollback exactly once.

With a real model, the experiment runner reports pass^k over k runs per model.

## 12. What is real and what is simulated

- **Real:**
  - The MCP protocol (SDK 2.2.0, stdio).
  - FastAPI, SQLite durability and process kills (`SIGKILL`).
  - Policy and approvals, idempotency and OTel spans.
  - Local models through Ollama.
- **Simulated:**
  - Enterprise systems (deterministic backends).
  - Slack-shaped payloads (not a Slack app).
  - Human approvals (CLI or REST calls).
  - Faults (injected).
  - Identities (synthetic).
