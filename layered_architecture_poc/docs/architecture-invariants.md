# F2 architecture invariants

The properties this POC claims a layered platform can hold, each with a stable id, the mechanism that is supposed to
hold it, and what actually enforces it in this repository. Ids never change: a claim, a test or a figure may cite
`L7` for the life of the series.

`docs/invariants.yaml` is the machine-readable form. `tests/architecture/test_invariant_coverage.py` fails if an
invariant has no enforcement listed, if a listed test does not exist, or if a listed facts path is absent from the
published run — so this document cannot drift from the code.

Enforcement kinds, strongest first:

| Kind | Meaning |
|---|---|
| **static** | Proved on the source itself (AST import rules, name checks). No run needed. |
| **test** | A deterministic test, no model involved. |
| **experiment** | Measured in the recorded run, with raw ledgers behind it. |
| **recomputed** | An experiment result independently recomputed from the raw ledgers by `scripts/recompute.py`. |
| **not enforced** | Stated in prose only. Named here so it cannot masquerade as proven. |

A logical layer here is a responsibility, dependency, contract, ownership, test and change boundary. It is **not** a
deployment boundary: this POC runs all six layers in one Python process, which is the point of `L13`.

---

## L1 — Functional capability is preserved

The layered platform solves the same business task as the monolith: diagnose INC-4917, propose the runbook
remediation, obtain approval, roll back once, verify recovery and record the incident.

- **Mechanism:** the same scenario, runbooks, tool semantics, scorer and approver for both architectures.
- **Enforcement:** experiment `E1` (6 scenarios, both architectures, seeds 7/11/13), recomputed check
  `E1 checks recomputed from the world ledger`; `tests/integration/test_platform_over_mcp.py`.
- **Facts:** `E1.monolith.runs_all_checks`, `E1.layered.runs_all_checks`, `E1.*.check_pass_counts.*`.
- **Does not show:** that either architecture solves a second incident, or that three runs estimate reliability.

## L2 — Experience does not own intelligence or runtime behaviour

Channel adapters translate transport in and rendering out. They do not hold workflow truth, durable state, provider
SDK calls or enterprise action execution.

- **Mechanism:** `layered_platform/experience/` may call only the composition root's service facade.
- **Enforcement:** static — `tests/architecture/test_import_rules.py` rule `experience` forbids imports of
  orchestration, runtime, tools, models, context, memory, policy, storage, `mcp`, `httpx`, `sqlite3`.
- **Facts:** `E9.change.layered.concerns_by_file.layered_platform/experience/cli.py` (the dry-run change did reach
  Experience, legitimately, through a contract change — see `L15`).

## L3 — Orchestration owns workflow progression

Which step runs next, and whether the workflow is waiting, is decided in orchestration and persisted, not inferred
from conversation text.

- **Mechanism:** `layered_platform/orchestration/incident_workflow.py` plus durable workflow events and checkpoints.
- **Enforcement:** static (rule `orchestration`); `tests/unit/test_idempotency_and_checkpoints.py`; recomputed check
  `workflow progression comes from workflow events`.
- **Facts:** `E7.layered.completed_steps_survive`, `E7.layered.steps_rerun`.

## L4 — Agent Runtime owns the execution lifecycle

Retry, checkpointing, resume and bounded repair of structured output live in runtime code, not in prompt wording.

- **Mechanism:** `layered_platform/runtime/{agent_loop,checkpoints,executor}.py`.
- **Enforcement:** static (rule `runtime`); `tests/unit/test_idempotency_and_checkpoints.py`;
  experiment `E5`; facts `*.structured_output_repairs`.
- **Does not show:** that every failure mode is recoverable — only the injected ones.

## L5 — Authoritative execution state exists outside the model context

A restarted process reconstructs completed work from storage, not from conversation history.

- **Mechanism:** SQLite workflow events, checkpoints and approvals; `layered_platform/storage/db.py`.
- **Enforcement:** experiments `E5` and `E7`, recomputed check
  `no model call repeats work completed before the kill`.
- **Facts:** `E5.layered.median_tokens_after_crash`, `E7.layered.approval_state_survives`,
  `E7.monolith.approval_state_survives`.
- **Exposure:** only the E5 scenarios that reached the injected SIGKILL count (see `docs/exposure.md`).

## L6 — Model provider details stay behind Model Services

Changing the model or the provider does not require editing workflow, tool, policy or experience code.

- **Mechanism:** `layered_platform/models/{gateway,ollama}.py`; model choice in `config/models.yaml`.
- **Enforcement:** static — rule `models`, plus `test_only_the_provider_adapter_speaks_http` and
  `test_no_provider_or_model_names_outside_config`; experiment `E2`.
- **Facts:** `E2.change.layered.concerns_touched_n`, `E2.change.layered.review_surface_concerns_n`,
  `E2.change.monolith.review_surface_concerns_n`.
- **Does not show:** provider independence. Both models are local Ollama models behind one adapter; a different wire
  API was not tested.

## L7 — Tool implementation details stay behind Tools + Actions

An enterprise action adapter can be replaced while its logical capability contract holds, without touching reasoning
or workflow code.

- **Mechanism:** `layered_platform/tools/{registry,adapters,gateway}.py`, capability contracts in
  `config/capabilities.yaml`.
- **Enforcement:** static (rule `tools`, `test_only_the_mcp_client_speaks_mcp`,
  `test_only_the_gateway_reaches_the_mcp_client`); experiment `E3`.
- **Facts:** `E3.change.layered.spill_over_n`, `E3.change.monolith.spill_over_n`, `E3.*.v2_rollback_gated`.

## L8 — Side effects carry stable operation identity

Two ambiguous attempts at the same logical operation must not become two physical writes.

- **Mechanism:** `layered_platform/tools/idempotency.py` — an operation id derived from the workflow, step, tool and
  canonical arguments, sent as the backend's idempotency key.
- **Enforcement:** `tests/unit/test_idempotency_and_checkpoints.py`; experiment `E4`; recomputed check
  `physical writes per operation id, from the backend ledger`.
- **Facts:** `headline.e4_duplicate_rollbacks.*`, `E4.*.client_rollback_attempts`,
  `E4.*.backend_rollback_requests`, `E4.*.backend_idempotent_replays`.
- **Does not claim:** exactly-once networking. The property is that a retry of the same logical operation does not
  duplicate the physical effect.

## L9 — Authorization is deterministic and outside model reasoning

Model output may propose an action. It cannot grant the authority to execute one.

- **Mechanism:** `layered_platform/policy/{engine,approvals,identity}.py`, evaluated by the action gateway before
  execution.
- **Enforcement:** `tests/unit/test_policy.py`, `tests/unit/test_approvals.py`,
  `tests/architecture/test_authority_rules.py` (no authority from prompt text); experiment `E6`.
- **Facts:** `E6.monolith_probes_executed_writes`, `E6.layered_probes_executed_writes`,
  `E6.adversarial.*.restarts_executed`.

## L10 — Approval is durable workflow state

A workflow waiting for a human survives a restart, and the approval it was given is still the approval it executes
under.

- **Mechanism:** approvals persisted with the workflow; the gateway re-checks before execution.
- **Enforcement:** `tests/unit/test_approvals.py`; experiment `E7`; recomputed check
  `approval precedes every production write`.
- **Facts:** `E7.*.approval_state_survives`, `E1.*.check_pass_counts.approval_before_write`.

## L11 — Trace correlation spans the whole workflow

Request → workflow → model → policy → tool → checkpoint → result is reconstructable, across process restarts.

- **Mechanism:** `layered_platform/telemetry/tracing.py`; spans written as they end.
- **Enforcement:** experiment `E8` (scorer revision `r2`), recomputed check
  `one workflow trace across the processes of a crash run`.
- **Facts:** `E8.layered.median_score`, `E8.monolith.median_score`,
  `E8.layered.crash_runs_single_trace_across_processes`, `E8.layered.crash_runs`.
- **Does not show:** that a collector or a production tracing backend would preserve this; spans are written to JSONL.

## L12 — Dependency direction is enforceable

The layer boundaries are checked on the source, not asserted in a diagram.

- **Mechanism:** AST import rules over `layered_platform/`, with the composition root as the only wiring point.
- **Enforcement:** static — `tests/architecture/test_import_rules.py`, including
  `test_checker_catches_a_violation`, which proves the checker fails on a planted violation.
- **Facts:** `tests.by_category.architecture.passed`, `tests.by_category.architecture.failed`.

## L13 — A logical layer is not a deployment boundary

Six logical layers run in one process, one repository, one database file. The boundary is responsibility, not a
network hop.

- **Mechanism:** one `layered_platform` package, one composition root, one database file.
- **Enforcement:** `tests/architecture/test_single_process.py`. The platform imports no web server and binds no
  socket; no layer holds a network address except the model provider adapter; and in every layered E1 scenario of the
  published run **one OS process carries spans from all six layers** — `request` (Experience), `workflow.step`
  (Orchestration), `invoke_agent` (Runtime), `chat` (Model Services), `execute_tool` (Tools + Actions) and
  `policy.evaluate` (Policy).
- **Facts:** `E1.layered.runs`, the `processes` field of each `scenarios/*/score.json`.
- **What the recorded run actually shows about process counts.** A layered scenario used **one more OS process than
  the monolith** in every paired scenario (2 against 1; 3 against 2 once a kill was injected). That extra process is
  not a layer: the harness invokes the layered platform twice, `start` then `approve`, because the workflow stops at
  `WAITING_APPROVAL` and a *different process* picks it up again. The monolith needs one process because it blocks
  in-process waiting for its approval callback. So the extra process is evidence for `L10`, durable approval state,
  and the per-scenario count is explained by harness invocations plus one restart per SIGKILL —
  `test_processes_are_explained_by_harness_phases_not_by_layers` asserts exactly that.
- **Note:** the MCP servers are separate processes by protocol design, over stdio. That is a transport boundary of the
  tool layer, not a service-per-layer deployment.

## L14 — Change locality is measured by responsibility, not file count

A change may touch several files and stay inside one architectural concern; a one-file change may touch many.

- **Mechanism:** `experiments/scorers/change_scope.py` classifies each touched file's concerns from a concern map,
  and reports the home concern, spill-over beyond it, and the review surface (all concerns living in the touched
  files).
- **Enforcement:** `tests/unit/test_change_scope.py`; experiments `E2`, `E3`, `E9`.
- **Facts:** `headline.review_surface.*`, `headline.spill_over.*`, `*.change.*.concerns_touched_n`,
  `*.change.*.files_changed`.
- **Contradicts:** "layering always changes fewer files" — see `E9`, where the layered tree changed more files.

## L15 — Cross-cutting requirements may legitimately cross layers

Some requirements are not owned by one layer. The architecture's job is to make the crossing an explicit contract
change rather than hidden coupling.

- **Mechanism:** shared contracts in `layered_platform/contracts.py`, wired at `layered_platform/service.py`.
- **Enforcement:** experiment `E9` (the dry-run requirement), recomputed check
  `the dry-run change is a contract change, not a leak`; the diff artifacts in `diffs/E9_dry_run-*.diff`.
- **Facts:** `E9.change.layered.files_changed`, `E9.change.layered.concerns_touched`,
  `E9.change.layered.spill_over_n`, `E9.change.monolith.spill_over_n`.
- **Status:** this is the invariant that keeps the article honest. The layered implementation touched four files to
  the monolith's one, and both spilled beyond their home concern.

---

## Invariants this POC does not enforce

Named so that no reader mistakes them for results.

| Id | Statement | Why not enforced |
|---|---|---|
| **N1** | Layering reduces latency or token cost | Not measured as a goal; the layered platform spends more model calls by design in E1. One machine, one workload. |
| **N2** | Layering prevents model mistakes | **Contradicted** by E5 layered seed 7, where the model proposed an invalid release id. The boundary caught it; the mistake still happened. |
| **N3** | Six services are required | Deliberately refuted by `L13`. |
| **N4** | Two models prove provider independence | Both are Ollama models behind one adapter (`L6`). |
| **N5** | These timings generalize to production | Local laptop, simulated backends, no network. |
| **N6** | Cost, quota and multi-tenancy boundaries work | Not implemented in this POC. |
