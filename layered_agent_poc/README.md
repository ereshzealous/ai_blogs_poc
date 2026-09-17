# Layered Agent Platform POC

**The question.** An incident agent works in a demo. What has to change so it survives production: more channels, a second model, human approvals, crashes, lost responses and operators who need to know what happened?

**The answer this POC tests.** Keep the agent to reasoning. Move sessions, workflow state, memory, tool execution, model access and governance into layers the agent calls, and enforce those boundaries in code. Then check that a change or a failure stays inside one layer.

**How it tests that.** One simulated production incident, **INC-4917**, runs through two implementations of the same incident agent:

- **`monolith/`:** the agent a good engineer builds first, one class that owns everything;
- **`agent_platform/`:** the same capability split into six layers plus cross-cutting control planes.

Then the POC changes requirements, kills processes and loses network responses, and records what each design does.

It is the companion to the article **"Your Agent Works in a Demo. Why Does It Break in Production?"**, Part 2 of the series that began with [MCP tool sprawl](../mcp_sprawl_poc). Everything runs on one laptop with local models. The MCP protocol, the models, the database and the process kills are real; the enterprise systems are simulated.

**In this README:**

1. [Why this exists](#why-this-exists)
2. [What it demonstrates](#what-it-demonstrates)
3. [Architecture](#architecture)
4. [Real and simulated](#real-and-simulated)
5. [Run it from zero](#run-it-from-zero), then [Choose what to test: plans](#choose-what-to-test-plans) and [Where to see the results](#where-to-see-the-results)
6. [Step-by-step guide](#steps-at-a-glance), [Troubleshooting](#troubleshooting), [Repository structure](#repository-structure), [Limitations](#limitations)

## Why this exists

A working agent demo is one loop: a prompt, a model, a few tools. Production then adds channels, identities, approvals, retries, memory, retrieval, more models, audit and tracing. If each of these lands inside the agent loop, the agent becomes the platform, and it fails in predictable ways:

| Failure | What happens in the monolith | Which layer should own it |
|---|---|---|
| Channel coupling | A second channel re-implements sessions and approvals | Experience |
| Provider coupling | A model swap edits agent code | Model services |
| State loss | A crash while waiting for approval throws the investigation away | Orchestration |
| Unsafe actions | Nothing but a y/N prompt checks what the model chose to run | Tool & action |
| Duplicate side effects | A retry after a lost response runs a production write twice | Tool & action |
| Blind operations | Operators get one log line: "agent failed" | Observability |

The POC shows these failures in the monolith, then shows the layered platform containing them.

> A production agent should reason about the task. It should not own the entire AI platform.

![How the monolith fails: six failures, each traced to a responsibility the agent should not own.](docs/images/03-monolith-failure-modes.png)

## What it demonstrates

| Property | How the POC shows it |
|---|---|
| **Separation** | Seven [import-linter](https://github.com/seddonym/import-linter) contracts fail the build if a layer reaches into another layer's job, for example `agents/` importing the MCP client |
| **Replaceability** | Channels (CLI, REST, chat) and models (`gpt-oss:20b`, `qwen3:8b`) change without touching agents or the workflow |
| **Recoverability** | Real `SIGKILL` crashes: a workflow resumes from SQLite checkpoints in a new process, and an idempotency key keeps the rollback to one execution |
| **Safety** | Deterministic policy decides before any write; approvals are bound to the digest of the exact invocation |
| **Observability** | One OpenTelemetry trace per incident, across process restarts, with GenAI span names |
| **Change locality** | Three requirement changes written as patches against both implementations, measured by files, lines and concerns touched |

It does **not** measure model quality. It runs one scenario, and its evals check outcomes and platform invariants.

## Architecture

![The layered agent platform: six layers, six control planes, one INC-4917 request.](docs/images/05-layered-agent-platform.png)

### The pieces and how they call each other

```mermaid
flowchart TB
  user(["alice · bob"]) --> ch
  subgraph P["agent_platform: the system under test"]
    ch["1 Experience<br/>CLI · REST · chat webhook"] --> svc["service.py<br/>the only entry point"]
    svc --> orch["2 Orchestration<br/>8-step workflow · checkpoints · approvals · resume"]
    orch -->|tasks| ag["3 Agent runtime<br/>diagnosis · remediation · summary agents"]
    ag -->|build context| ctx["4 Context & memory<br/>assembler · sessions · episodic memory · runbooks"]
    ag -->|tool calls, through a port| act["5 Tool & action<br/>registry · policy · gateway · retry · idempotency · audit"]
    orch -->|incident read, rollback, verification| act
    orch -->|write memory| ctx
    ag -->|chat| mod["6 Model services<br/>routes · profiles · fallback · budgets"]
    ctx -->|embeddings| mod
    x["Cross-cutting: identity · telemetry · evals"]
  end
  act -->|MCP over stdio| mcp["5 MCP servers<br/>itsm · source_control · observability · database · kubernetes"]
  mcp --> ent[("mock_enterprise<br/>simulated systems of record")]
  mod -->|HTTP| oll["Ollama<br/>gpt-oss:20b · qwen3:8b · nomic-embed-text"]
```

- **State.** Orchestration, the context and memory stores and the tool and action layer each keep their own tables in one SQLite file, `platform.db`; see [State: what lives where](#state-what-lives-where).
- **One way in.** Channels only build commands (`StartInvestigation`, `ApprovalDecision`) and call `agent_platform/service.py`, which is also the only place the layers are wired together.
- **Ports, not clients.** Agents never hold an MCP client or a model SDK. They receive a tool port and a model port, so the gateway and the model router can change without touching them.
- **Enforced, not drawn.** `.importlinter` holds seven contracts. For example, agents cannot import `mcp` or `httpx`, orchestration cannot call a model, and only the tool and action layer's MCP client may speak MCP.

### Layers

| Layer | Package | Owns | Must not own |
|---|---|---|---|
| 1 Experience | `agent_platform/channels/` | CLI, REST, chat webhook, rendering | Workflow logic |
| 2 Orchestration | `agent_platform/orchestration/` | 8 steps, append-only checkpoints, approvals, leases, resume | Reasoning |
| 3 Agent runtime | `agent_platform/agents/` | Bounded tool-use loop, validated structured output with one repair | MCP clients, provider SDKs |
| 4 Context & memory | `agent_platform/context/`, `memory/`, `knowledge/` | Context assembly within a token budget, sessions, episodic memory, runbook retrieval | Workflow state |
| 5 Tool & action | `agent_platform/actions/` | Capability registry, policy, MCP gateway, bounded retry, idempotency, audit | Reasoning |
| 6 Model services | `agent_platform/models/` | Routes, provider profiles, fallback, token budgets, embeddings | Business logic |
| Cross-cutting | `agent_platform/identity/`, `telemetry/`, `evals/` | Principals and roles, tracing, deterministic evals | A layer of its own |

The six layers are the article's synthesis, not a standard. Layers are not agents either: this platform runs three agents inside one layer.

### One request, step by step

A request enters through a channel, becomes a `StartInvestigation` command, and runs as an eight-step workflow. Agents only reason. Everything that touches state, tools or models goes through the layer that owns it.

![INC-4917 through the layers: eight steps, one owner each.](docs/images/07-inc4917-through-layers.png)

| # | Step | Owner | What happens | Model? |
|---|---|---|---|---|
| 1 | `intake` | Orchestration | Load the incident through the action gateway (one read call) | No |
| 2 | `investigate` | Diagnosis agent | Choose from 8 read tools (deploys, diff, latency, logs, traces, pool stats, pods, the incident); 7 to 8 calls per run in the article's run | Yes |
| 3 | `propose_remediation` | Remediation agent | Propose an action using runbook RB-CHK-007 and memory INC-4630; policy pre-checks it | Yes |
| 4 | `await_approval` | Orchestration | Park the workflow until an incident commander approves this exact invocation | No |
| 5 | `remediate` | Action gateway | Run `source_control.rollback_release` with an idempotency key | No |
| 6 | `verify` | Orchestration | Poll `observability.query_latency` until p95 is back under the SLO | No |
| 7 | `record` | Summary agent | Write the incident note, only after verification | Yes |
| 8 | `complete` | Orchestration | Store an episodic memory with provenance and record the outcome in the session | No |

Every step ends with a checkpoint. The evals run afterwards, on demand (`lap eval`). Every tool call passes four decisions:

1. **Reasoning** (agent): what do I want to do?
2. **Capability resolution** (registry): which capability represents that intent? A tool the agent was not offered is refused.
3. **Authorization** (policy): may this caller and this agent run this exact action? See `config/policies.yaml`.
4. **Execution** (gateway): idempotency key, bounded retry, the MCP call, an audit record.

`docs/DESIGN.md` is the source of truth for every name: steps, tools, rules, stores, spans and evals.

### State: what lives where

Each kind of state has one owner and its own rules. One vector store for all of them would be a retrieval index, not a state model.

| Kind | Where | Lifetime | Written by | Rule |
|---|---|---|---|---|
| Workflow state | `workflows`, `checkpoints`, `workflow_events`, `approvals` in `platform.db` | Until the workflow ends | Orchestration only | Transactional, append-only checkpoints |
| Conversation | `sessions`, `messages` | One session | Channels through the service; agents' final answers | Append-only, trimmed into context |
| Episodic memory | `memories` | Months, with `expires_at` | The memory store, with `source` provenance | Curated, can be wrong, expired entries are skipped |
| Knowledge | `agent_platform/knowledge/runbooks/*.md`, plus an embedding index | Until the owner edits a runbook | Document owners | Authoritative, cited by id |
| Operations | `idempotency`, `audit` | Retention | Tool & action layer | Deduplicate writes; append-only log |
| Model usage | `model_usage` | Retention | Model services (the model gateway) | Tokens and latency per call |
| Working context | not stored | One agent step | Context assembler | Rebuilt every time, within a token budget |
| Systems of record | `enterprise.db` (simulated) | The scenario | The MCP servers | Deployments, incident notes, executed writes |

Spans go to `runs/traces/<trace-id>.jsonl` as each span ends, so a trace survives a `SIGKILL`.

### The baseline: the agent monolith

`monolith/incident_agent.py` is the agent a careful engineer writes first, in about 140 lines, with a CLI (`monolith/cli.py`) and a REST wrapper (`monolith/api.py`). One class holds:

- the prompt and the Ollama call, including model-specific options such as `think: "low"`;
- the conversation history in memory;
- the five MCP clients and the tool list;
- a y/N approval prompt before any write;
- a retry loop around tool calls;
- logging.

It solves INC-4917. It is the right design for a short, single-channel task. The experiments show where it stops being enough: a second channel, a model swap, a crash while waiting, a lost write response.

### The test harness

The harness drives the platform from outside. Two small hooks live inside the platform, and both do nothing unless their environment variable is set: the crash switch (`LAP_CRASH_ON`) and the model-traffic recorder (`LAP_MODEL_TRAFFIC`).

| Piece | Where | What it does |
|---|---|---|
| `poc` command | `experiments/poc.py` | Checks the machine, runs the demo and the plans, lists and opens reports |
| Run plans | `plans/*.yaml`, `experiments/plan.py` | Say what to test (models, experiments, faults, kill points) and what counts as a pass |
| Experiment runner | `experiments/run.py` | Runs each experiment in a fresh folder with fresh databases and writes every record to `runs/<run-id>/` |
| Reports | `experiments/report.py`, `agent_platform/channels/html_report.py` | Build HTML, Markdown and JSON reports from those files alone |
| Model traffic | `traffic/`, `agent_platform/models/recorded.py` | Record every model answer, and replay a run without Ollama |
| Fault and crash hooks | `mock_enterprise/world.py`, `agent_platform/faults.py` | Arm timeouts and lost responses in the simulated systems; kill a platform process at a named point (`LAP_CRASH_ON`), only when the variable is set |
| Change patches | `experiments/change_scope/` | Apply each requirement change to a copy of both implementations and count what it touched |

## Real and simulated

| Real | Simulated, and labelled as such |
|---|---|
| MCP over stdio, [Python SDK](https://github.com/modelcontextprotocol/python-sdk) 2.2.0, five servers | Enterprise systems: deterministic INC-4917 backends in `mock_enterprise/` |
| Local models through [Ollama](https://ollama.com): two generative (`gpt-oss:20b`, `qwen3:8b`), one embedding (`nomic-embed-text`) | Slack-shaped chat payloads (not a Slack app) |
| FastAPI REST service | Human approvals (CLI or REST calls) |
| SQLite durability (WAL) | Injected faults (timeouts, lost responses) |
| Process kills with `SIGKILL` | Identities `alice` (SRE, incident commander) and `bob` (developer) |
| OpenTelemetry spans (JSONL, optional OTLP to Jaeger) | |

The backends are mocks on purpose: the scenario has to be repeatable, a lost response has to be injectable, and a rollback has to be countable.

![The POC at a glance: packages, servers, tools, models, rules and tests, counted from the repository.](docs/images/13-poc-at-a-glance.png)

## Run it from zero

Five steps. `poc` wraps the lower-level `lap` and `experiments.run` commands, checks the machine first, and ends every run with a pass/fail table and an HTML report.

```bash
# 1. Tools: uv, and Ollama (the desktop app from ollama.com, or `brew install ollama`, then `ollama serve` in another terminal)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Models: about 19 GB (gpt-oss:20b 13 GB, qwen3:8b 5.2 GB, nomic-embed-text 274 MB)
ollama pull gpt-oss:20b && ollama pull qwen3:8b && ollama pull nomic-embed-text

# 3. Code
git clone https://github.com/ereshzealous/ai_blogs_poc.git
cd ai_blogs_poc/layered_agent_poc
uv sync

# 4. Check the machine, then run one incident end to end (1 to 2 minutes)
uv run poc check
uv run poc demo

# 5. Every experiment, with reports: pick a plan, see what it tests, run it
uv run poc plans
uv run poc plan show quick
uv run poc run --plan quick              # about 5 minutes
```

`poc check` looks at Python, the Ollama models, what else is loaded in Ollama, free memory and disk, and starts the 5 MCP servers. Each problem comes with the command that fixes it.

**Sharing Ollama.** A live run shares Ollama with any other process on the machine. Both slow down, and a model swap can cost minutes. `poc check` watches Ollama for a few seconds and warns when another process is sending it requests. To wait for that process before running:

```bash
uv run poc check --wait && uv run poc run --plan full    # starts after Ollama has been idle for 2 minutes
uv run poc check --wait 300                              # or choose the idle period in seconds
```

Replay plans don't use Ollama, so they can run at any time.

`poc demo` runs INC-4917 in its own folder under `runs/demo/`:

1. alice reports the incident; the agents investigate and stop at the approval gate;
2. bob tries to approve and is refused;
3. alice approves, and a new process resumes and finishes the rollback;
4. the 8 checks are scored and the systems of record are read back;
5. `report.html` is written and opened.

`poc run` runs a plan (next section) and ends with a table of the plan's expectations, each met or not, with what was measured. Timings grow when another process uses Ollama at the same time. If a stage fails, the others still run, and `uv run poc run --resume <run-id>` re-runs only the failed stages with the run's saved plan.

### Choose what to test: plans

A plan is a YAML file in `plans/`. It says which models to use, how many runs per scenario, where model answers come from, which experiments run, which faults to inject, where to kill the process, and what counts as a pass.

| Plan | What it runs | Model answers | About, on an idle 24 GB laptop |
|---|---|---|---|
| `quick` | Every experiment with `gpt-oss:20b`, one run per scenario, fast tests | Ollama | 5 min |
| `standard` | Every experiment with both models, three runs each, fast tests | Ollama | 10 min |
| `full` | `standard`, plus the end-to-end tests against the models. The article's run used it | Ollama | 15 min |
| `replay` | `full`, answered from the recording of `2026-09-17-recorded` | recorded | 3 min |
| `chaos` | An example of a custom plan: faults from the start, three `SIGKILL`s in one workflow | Ollama | 4 min |

```bash
uv run poc plans                                   # the list above
uv run poc plan show chaos                         # what a plan runs, injects and expects
uv run poc run --plan chaos                        # run it
uv run poc run --plan full --models qwen3:8b --runs 5          # override the models and runs
uv run poc run --plan quick --only faults,crash                # or --skip monolith,change
uv run poc run --plan quick --set tests.model_tests=true \
    --set 'crash.kill_at=[after_step:investigate, after_step:await_approval]'
uv run poc run --plan my-plans/nightly.yaml                    # your own file
```

What you can test, and the plan keys that change it:

| Experiment | What it shows | Plan keys |
|---|---|---|
| `tests` | pytest and the 7 import contracts | `tests.model_tests` adds the end-to-end tests against the models |
| `faults` (E5, E6) | One platform run with tool faults: the gateway retries within bounds, and the backend deduplicates a lost write by its idempotency key | `faults.model`; `faults.arm_at` (`approval` or `start`); `faults.inject`, a list of `{tool, mode: timeout \| lose_response, times, delay_s}` |
| `crash` (E4) | One workflow killed with `SIGKILL` at each point in turn; each new process approves or resumes it from its checkpoints | `crash.kill_at`: `after_step:<step>`, `executed:<tool>`, `timeout:<tool>`; `crash.inject` |
| `monolith` | The same incident through the agent monolith | `runs`; `monolith.lost_response`; `monolith.crash` |
| `workflow` (E2, E3, E7, E8, E9) | INC-4917 end to end per model, with evals, traces, memory and context | `models`, `runs` |
| `change` (E1) | Each requirement-change patch applied to both implementations | none |
| `export` | Data for the article's figures | none |

- **Steps for `after_step:`** `intake`, `investigate`, `propose_remediation`, `await_approval`, `remediate`, `verify`, `record`, `complete`.
- **Tools** are the 11 in `config/capabilities.yaml`. A lost response only makes sense for a write.
- **Pass criteria** live under `expect`:
  - `tests_pass`, `contracts_kept`;
  - `platform_runs_complete` and `platform_all_checks` (`all` or a number of runs);
  - `lost_response_backend_executions`, `monolith_lost_response_rollbacks_at_least`;
  - `crash_final_status`, `crash_backend_rollbacks`;
  - `change_contracts_kept`.

  Set one to `null` to drop it. Only experiments in the plan are judged.
- **Your own plan:**
  1. Copy `plans/full.yaml` and keep only the keys you change: a plan is laid over the full plan.
  2. Check it with `poc plan show <file>`. An unknown key, experiment, step or tool is rejected with the reason.
- **CI:** `poc run` exits 0 only when every stage passes and every expectation is met. Each run saves its resolved plan as `runs/<run-id>/plan.yaml`, and the report shows it with the expectation results.
- **Replay needs the recorded plan:** a replay answers model calls in the order they were recorded. It must keep the models, runs, faults and kill points of the run it replays, which is why `--replay` reuses that run's plan.

### No GPU? Replay mode

Every model answer from a reference run is recorded next to it. Replay mode runs the same experiments against those recordings, so it needs neither Ollama nor the 19 GB of models:

```bash
uv sync
uv run poc demo --replay                 # about 15 seconds
uv run poc run --plan replay             # every experiment, about 3 minutes
```

In replay mode, only the model is replaced:

- **Real:** the MCP servers and tool calls, policy, approvals, SQLite state, the workflow, the `SIGKILL` crashes, timeouts and retries, and the evals all run.
- **Recorded:** the model answers and token counts come from `runs/2026-09-17-recorded/`, and the report says so at the top.
- **Not measured:** wall-clock times are not model timings.
- **Model tests:** they are skipped, because they exist to test the models.
- **Drift:** if the code sends a model a request that differs from the recording, the run still continues and prints a warning.

Recordings are plain JSON lines (`traffic/chat.jsonl`, `traffic/embed.jsonl`). Every live run records its own traffic, so `uv run poc run --replay <run-id>` replays any run you made.

## Where to see the results

| You ran | Look here |
|---|---|
| `poc demo` | `runs/demo/latest/report.html`, or `uv run poc open demo` |
| `poc run` | The pass/fail table at the end, then `runs/latest/report/index.html`, or `uv run poc open` |
| Several runs | `uv run poc runs` lists them with their results, and `runs/index.html` links every report |
| `lap run`, `lap approve` | The terminal. Then use `lap status <wf-id>` for the summary, `lap --json status <wf-id>` for the full view, `lap trace <wf-id>` for the span tree and `lap eval <wf-id>` for the 8 checks |
| `lap report <wf-id>` | `runs/reports/<wf-id>.html`: diagnosis, tool and model calls, policy, approval, remediation, verification, evals, events, audit log and trace |
| Any `lap` command | Spans in `runs/traces/<trace-id>.jsonl`, or in Jaeger (see [9](#9-read-the-trace)) |
| `lap serve` | `GET /v1/workflows/{id}` and its `/events`, `/trace` and `/evaluation` |
| A run, in detail | `runs/<run-id>/report/index.html` shows everything. `report/summary.md` has the headline numbers, and `report/results.json` has the same numbers as JSON |
| Console output of a run | `runs/<run-id>/run.log`, with each stage's start, end and result in `stages.json`, the resolved plan in `plan.yaml`, and the mode in `run.json` |
| Tests recorded with a run | `runs/<run-id>/tests/`: JUnit XML, pytest output and `lint-imports.log` |
| The systems of record | `uv run python -m mock_enterprise status` |
| The run behind the article | `runs/2026-09-17-recorded/report/index.html` |

## Steps at a glance

The short path is [Run it from zero](#run-it-from-zero). The sections below do the same by hand, one part at a time, with `lap` and `experiments.run`.

1. [Set up](#1-set-up)
2. [Run the tests](#2-run-the-tests)
3. [Explore without a model](#3-explore-without-a-model)
4. [Run INC-4917 from the CLI](#4-run-inc-4917-from-the-cli)
5. [Use the REST API and the chat webhook](#5-use-the-rest-api-and-the-chat-webhook)
6. [Crash it and resume](#6-crash-it-and-resume)
7. [Lose a write response](#7-lose-a-write-response)
8. [Switch models](#8-switch-models)
9. [Read the trace](#9-read-the-trace)
10. [Run the monolith baseline](#10-run-the-monolith-baseline)
11. [Reproduce the published results](#11-reproduce-the-published-results)
12. [Extend the POC](#12-extend-the-poc)

## Prerequisites

- Python 3.12 or newer, and [uv](https://docs.astral.sh/uv/).
- [Ollama](https://ollama.com) running locally on `http://localhost:11434`.
- About 16 GB of free memory for `gpt-oss:20b`. The published run used a 24 GB Apple Silicon laptop.
- Optional: Docker, to view traces in Jaeger.

No paid API is used.

## 1. Set up

```bash
ollama pull gpt-oss:20b && ollama pull qwen3:8b && ollama pull nomic-embed-text
uv sync
uv run python -m mock_enterprise reset   # INC-4917 active: checkout-api v4.17 in production
uv run lap doctor
```

`lap doctor` should print:

```
MCP tools: 11 from 5 servers
Ollama models: all present
```

### Configuration

Everything that can change without a code change lives in `config/`:

| File | What it holds |
|---|---|
| `platform.yaml` | Storage paths, model routes and fallbacks, provider profiles (`think`, `num_ctx`, temperature), the token budget, agent step limits, verification polling |
| `capabilities.yaml` | The 11 tools: risk, tags, retry attempts and timeouts, and which writes carry an idempotency key; which services are managed by the GitOps release pipeline |
| `policies.yaml` | Rules P0 to P5 and P9, evaluated top to bottom; the first match wins |
| `principals.yaml` | Users, roles, chat user ids and the agent's identity and scopes |
| `memory_seed.yaml` | Episodic memories with provenance and expiry: INC-4630, INC-4411 and one expired Q1 note |

Environment variables override configuration. A relative value is taken from the current directory, and an unset one defaults inside this POC, so another project embedding this platform should set all of them, including `LAP_KNOWLEDGE_INDEX`: left unset, the runbook index is built in this POC's `var/`.

| Variable | Effect |
|---|---|
| `LAP_MODEL_REASONING`, `LAP_MODEL_SUMMARY`, `LAP_MODEL_EMBEDDINGS` | Replace the model for a route |
| `OLLAMA_URL` | Use another Ollama server |
| `LAP_PLATFORM_DB`, `LAP_ENTERPRISE_DB`, `LAP_RUNS_DIR`, `LAP_KNOWLEDGE_INDEX` | Move state elsewhere (the tests use this to isolate runs). A relative value is taken from the current directory, so another project embedding this platform never writes inside it |
| `LAP_CRASH_ON` | Kill the process with `SIGKILL` at a named point, for example `after_step:await_approval`, `executed:<tool>` or `timeout:<tool>` |
| `LAP_MODEL_TRAFFIC` | `record:<dir>` appends every model answer to `<dir>`; `replay:<dir>` answers from it, with no model server |
| `LAP_RECOVER_ON_START` | `1` (default) makes `lap serve` resume workflows a dead worker left `RUNNING` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Also export spans over OTLP (needs `uv sync --extra otlp`) |

## 2. Run the tests

```bash
uv run pytest -m "not ollama"   # fast tests, no model needed
uv run lint-imports             # the layer boundaries: 7 contracts
uv run pytest                   # plus the end-to-end tests against the local models
```

- **Fast tests:**
  - policy decisions;
  - retry and idempotency (including a key reused with different arguments);
  - checkpoints, leases and approvals bound to a digest;
  - channels producing the same command;
  - the import contracts;
  - reports built from recorded files;
  - a full workflow replayed from recorded model traffic, with no model server.
- **End-to-end tests:**
  - a full REST run with 8/8 evals;
  - two `SIGKILL` crashes with resume;
  - a crash inside a lost write;
  - a model swap through configuration only.
- **Timing:** the end-to-end tests take 10 to 30 minutes, depending on the machine and on what else is using Ollama.
- **Recording:** `uv run python -m experiments.run tests --run-id <run-id> [--model-tests]` runs the same tests and keeps the JUnit results with that run.

## 3. Explore without a model

Evaluate policy decisions directly:

```python
# save as policy_demo.py, then: uv run python policy_demo.py
from agent_platform.actions.policy import PolicyEngine
from agent_platform.actions.registry import CapabilityRegistry
from agent_platform.actions.types import ActionContext, Invocation

engine = PolicyEngine(CapabilityRegistry())
ctx = ActionContext("alice", "agent:incident-remediation", "wf-demo", "propose_remediation", "production")
for tool, args in [
    ("observability.query_latency", {"service": "checkout-api", "environment": "production"}),
    ("kubernetes.rollback_deployment", {"service": "checkout-api", "environment": "production", "revision": 41}),
    ("source_control.rollback_release", {"service": "checkout-api", "environment": "production", "target_version": "v4.16"}),
]:
    d = engine.evaluate(Invocation(tool, args), ctx)
    print(f"{tool:34} {d.decision.value:17} {d.rule_id}")
```

```
observability.query_latency        ALLOW             P1-read-only
kubernetes.rollback_deployment     DENY              P2-gitops-authoritative
source_control.rollback_release    REQUIRE_APPROVAL  P4-prod-high-risk-approval
```

Talk to one MCP server directly:

```python
# save as mcp_demo.py, then: uv run python mcp_demo.py
import asyncio, sys
from mcp import Client
from mcp.client.stdio import StdioServerParameters

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "mock_enterprise", "observability"])
    async with Client(params) as client:
        print([t.name for t in (await client.list_tools()).tools])
        result = await client.call_tool("query_latency", {"service": "checkout-api", "environment": "production", "window_minutes": 15})
        print(result.content[0].text)

asyncio.run(main())
```

See what the systems of record hold:

```bash
uv run python -m mock_enterprise status   # version in production, incident state, rollbacks executed and replayed
```

## 4. Run INC-4917 from the CLI

```bash
uv run lap run INC-4917 --as alice        # investigates, proposes, stops at the approval gate
uv run lap approve <wf-id> --as bob       # forbidden: bob lacks role 'incident-commander'
uv run lap approve <wf-id> --as alice     # a new process resumes from the checkpoint and finishes
```

```
⏸ wf-…  INC-4917  WAITING_APPROVAL  (step: await_approval, …)
  diagnosis   checkout-api v4.17 (DEP-88213), confidence high
  root cause  The new orders-client v3.0.1 changed the checkout-api…
  proposal    source_control.rollback_release → v4.16 in production
  policy      REQUIRE_APPROVAL (P4-prod-high-risk-approval)
```

Then inspect the workflow:

```bash
uv run lap status <wf-id>                 # the view above
uv run lap --json status <wf-id>          # the full view as JSON (--json goes before the command)
uv run lap list                           # every workflow and its status
uv run lap eval <wf-id>                   # 8 deterministic checks
uv run lap report <wf-id>                 # everything above as one HTML page: runs/reports/<wf-id>.html
uv run python -m mock_enterprise status   # rollbacks_executed: 1
```

Use `lap approve <wf-id> --as alice --reject` to reject a proposal instead.

With `gpt-oss:20b` on the laptop above:

- reaching the approval took a median of 44 s;
- the rest took 5 s;
- a run used 24,002 tokens across 12 model calls.

## 5. Use the REST API and the chat webhook

```bash
uv run lap serve --port 8080
```

| Method and path | Purpose |
|---|---|
| `POST /v1/incidents/{id}/investigations` | Start a workflow (header `X-User-Id`) |
| `GET /v1/workflows`, `GET /v1/workflows/{id}` | List workflows, or view one |
| `POST /v1/workflows/{id}/approvals` | Approve or reject (header `X-User-Id`, body `{"approve": true}`) |
| `POST /v1/workflows/{id}/resume` | Resume a stopped workflow |
| `GET /v1/workflows/{id}/events`, `/trace`, `/evaluation` | Events, spans and eval results |
| `POST /v1/chat/events`, `POST /v1/chat/actions` | Slack-shaped mention and button payloads (simulated) |
| `GET /healthz` | Liveness and tool count |

```bash
curl -s -X POST localhost:8080/v1/incidents/INC-4917/investigations -H 'X-User-Id: alice' \
     -H 'content-type: application/json' -d '{"request": "Checkout latency rose after the 10:15 deploy. Investigate."}'
curl -s localhost:8080/v1/workflows/<wf-id>
curl -s -X POST localhost:8080/v1/workflows/<wf-id>/approvals -H 'X-User-Id: alice' \
     -H 'content-type: application/json' -d '{"approve": true}'

# chat: a mention starts a workflow; a button press approves it
curl -s -X POST localhost:8080/v1/chat/events -H 'content-type: application/json' \
     -d '{"type":"event_callback","event":{"type":"app_mention","user":"U04ALICE","channel":"C1","text":"<@UBOT> INC-4917 checkout is slow"}}'
curl -s -X POST localhost:8080/v1/chat/actions -H 'content-type: application/json' \
     -d '{"user":{"id":"U04ALICE"},"actions":[{"action_id":"approve","value":"<wf-id>"}]}'
```

All three channels build the same `StartInvestigation` and `ApprovalDecision` commands. They import the service facade and those command contracts, never a layer.

## 6. Crash it and resume

![Crash, checkpoint, resume.](docs/images/08-checkpoint-resume.png)

```bash
LAP_CRASH_ON=after_step:await_approval uv run lap run INC-4917 --as alice
uv run lap status <wf-id>                  # still WAITING_APPROVAL: the state is in SQLite

LAP_CRASH_ON=executed:source_control.rollback_release uv run lap approve <wf-id> --as alice
uv run lap resume <wf-id>                  # re-runs remediate with the same operation_id; replayed=True
uv run python -m mock_enterprise status    # rollbacks_executed: 1
```

The first command kills the process right after the approval checkpoint. The second kills it after the rollback executed but before that step's checkpoint.

In the published run, one workflow ran through 3 processes, and the backend recorded 1 rollback. The investigation cost 18,231 tokens before the crash, and everything after it cost 912.

A worker lease records which process owns a workflow. `lap recover`, or a restarted `lap serve`, takes over workflows whose owner died.

## 7. Lose a write response

![Retry without a duplicate action.](docs/images/09-idempotent-retry.png)

Arm a lost response on the rollback: the backend executes it, then answers after the 2 s client timeout.

```bash
uv run python -c "from mock_enterprise.world import World; World().arm_fault('source_control.rollback_release', 'lose_response', 1, 4)"
uv run lap approve <wf-id> --as alice
uv run python -m mock_enterprise status   # rollbacks_executed: 1, rollback_replays: 1
```

How the retry works:

- The gateway retries with the same `operation_id`, a hash of workflow, step, tool and arguments, sent as the idempotency key.
- The backend finds the key with a matching argument digest and returns the stored result.
- The same key with different arguments is rejected.

In the published run the platform executed the rollback 1 time and replayed it 1 time. The monolith, given the same fault, rolled back 2 times.

The other injectable fault is a read timeout. `World().arm_fault('observability.query_latency', 'timeout', 2, 3)` makes the next two calls time out; the gateway retries with backoff and jitter.

Who retries what:

- **MCP client:** never retries a tool call on its own.
- **Action gateway:** owns tool-call retry, bounded by `capabilities.yaml`, and retries writes only with a key.
- **Orchestration:** resumes steps; it does not retry them.

## 8. Switch models

```bash
LAP_MODEL_REASONING=qwen3:8b LAP_MODEL_SUMMARY=qwen3:8b uv run lap run INC-4917 --as alice
```

Only configuration changes. Provider options, such as `think`, live in the model profile.

Behaviour can still change, so re-run the evals after a switch. In the published run:

- all 8 checks passed in 3/3 runs with `gpt-oss:20b` and 3/3 with `qwen3:8b`;
- this is regression evidence for one scenario, not a reliability estimate.

To add another Ollama model, give it a profile in `config/platform.yaml`, then point a route at it.

## 9. Read the trace

```bash
uv run lap trace <wf-id>   # span tree from runs/traces/<trace-id>.jsonl
```

![One incident, one trace.](docs/images/10-agent-observability.png)

- **Span names:** spans use the OpenTelemetry GenAI names, which are still in Development status: `invoke_workflow`, `invoke_agent`, `chat`, `embeddings`, `execute_tool`.
- **Platform attributes:** `lap.workflow.id`, `lap.step`, `lap.policy.decision`, `lap.retry.attempt`, `lap.idempotency.replayed`, `lap.checkpoint.seq`.
- **One trace per incident:** a resumed process joins the trace the crashed process started.

To view traces in Jaeger:

```bash
docker compose up -d jaeger
uv sync --extra otlp
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 uv run lap run INC-4917 --as alice
open http://localhost:16686
```

## 10. Run the monolith baseline

```bash
uv run python -m mock_enterprise reset
uv run monolith run INC-4917          # asks y/N on the terminal before production writes
uv run monolith run INC-4917 --yes    # test mode: approves every write
```

`monolith/incident_agent.py` is one class that owns everything:

- the prompt;
- the Ollama call with provider options;
- memory;
- the MCP clients;
- the approval rule;
- retries without keys;
- logging.

`monolith/api.py` adds a REST API that keeps sessions and parked approvals in process memory.

For one bounded, read-only assistant on one channel, this is the right amount of architecture.

In the published run:

- **Time and tokens:** a monolith run took a median of 25 s and 14,614 tokens.
- **Crash:** killed while waiting, it left nothing to resume; reaching the approval prompt again took 13 s.
- **Unsafe action:** in 3 auto-approved runs it executed a direct Kubernetes rollback 0 times. The model chose the release pipeline, but in this test mode no rule and no person stood between it and that write.

## 11. Reproduce the published results

```bash
uv run poc run --plan full --run-id <run-id>
# the same, without the wrapper:
uv run python -m experiments.run all --run-id <run-id> --plan plans/full.yaml
```

`all` runs the plan's experiments in order, then the report. Pass one name instead of `all` to run a single stage; in an existing run folder it uses that run's saved plan.

| Stage | What it does | About |
|---|---|---|
| `tests` | pytest with JUnit output, plus the import contracts; `tests.model_tests` adds the end-to-end tests | 1 min, or 5–30 min with model tests |
| `faults` | E5, E6: the plan's injected faults, by default read timeouts and a lost rollback response | 1 min |
| `crash` | E4: a `SIGKILL` at each of the plan's kill points, by default two, then a resume | 1–2 min |
| `monolith` | The baseline: `runs` runs, then the lost response and the crash | 2 min |
| `workflow` | E2, E3, E7, E8, E9: `runs` runs per model | 1–2 min per run |
| `change` | E1: applies each requirement-change patch to a copy and checks it | 1 min |
| `export` | The data behind the article's measured figures, from the records | seconds |
| `report` | `report/index.html`, `summary.md`, `results.json`, from the files alone | seconds |

Useful flags:

| `poc run` | `experiments.run` | Effect |
|---|---|---|
| `--plan <name or file>` | `--plan <file>` | What runs and what counts as a pass; `quick` by default |
| `--models`, `--runs` | `--models`, `--k` | Override the plan's models and runs per scenario |
| `--only a,b`, `--skip a,b` | | Run a subset of the plan's experiments |
| `--set key=value` | | Override any plan key; the value is YAML |
| `--replay [<run-id>]` | `--replay-from <run-id>` | Answer model calls from a recorded run, with that run's plan (default `2026-09-17-recorded`) |
| `--resume [<run-id>]` | `--resume` | Finish a run with its saved plan, skipping the stages that already passed; the default is the latest run |
| `--run-id <run-id>` | `--run-id <run-id>` | Name the folder; the default is the date, time and plan name |
| `--no-open` | | Do not open the report |
| | `--no-record` | Do not keep the model traffic |

Each run gets its own folder:

| Path under `runs/<run-id>/` | Contents |
|---|---|
| `report/index.html`, `report/summary.md`, `report/results.json` | The reports |
| `plan.yaml` | The resolved plan: what ran and what counted as a pass |
| `run.log`, `stages.json` | Console output; each stage's start, end, result and error |
| `tests/`, `tests.json` | JUnit XML, pytest output, `lint-imports.log`; test counts |
| `workflow/<model>/run<N>/record.json` | View, events, audit log, model usage, eval results, trace and backend state for each run |
| `workflow/summary.json` | Per-model timings, tokens, calls and check pass counts |
| `faults/`, `crash/`, `monolith/` | Each experiment's summary, databases and spans (`otel/traces/`) |
| `change-scope.json` | Files, lines, concerns and checks for each patch |
| `diagram-data/` | The data behind the article's figures |
| `run.json` | Profile, models, runs per scenario, mode (live or replay), host and times |
| `…/traffic/` | The model answers of each scenario, for replay |

Reports and exports never call a model, so `experiments.run report --run-id <run-id>` can rebuild them at any time.

About the article's run, `2026-09-17-recorded`:

- **How it was made:** the `full` plan (`uv run poc run --plan full`), which also recorded the model answers that replay mode uses.
- **Tests:** 33 passed with the run (29 fast, 4 end-to-end against the models), 0 failed. The POC has gained tests since; they run in every new run.
- **Timings:** they come from one 24 GB Apple Silicon laptop, and change with the hardware and with whatever else uses Ollama.
- **An earlier run:** `runs/2026-09-16/` was the first full run. Its end-to-end tests passed in two sittings, because another process was loading Ollama models with a different context size.

### Results (run 2026-09-17-recorded)

| # | Experiment | Result |
|---|---|---|
| E1 | Three requirement changes, written as patches | Add a channel: monolith 3 files (+63/−14 lines), platform 3 files (+60/−0 lines). Swap the model: monolith 2 files (+6/−3 lines), platform 1 file (+1/−1 lines). Change freeze: monolith 3 files (+24/−11 lines), platform 2 files (+6/−0 lines) |
| E2 | Model swap | Same code; all 8 checks passed in 3/3 runs with `gpt-oss:20b` and 3/3 with `qwen3:8b` |
| E3 | CLI, REST and chat | All three produce the same commands; channels import only the service |
| E4 | `SIGKILL` while waiting, then after the write | 3 processes, status `WAITING_APPROVAL` after the first kill, rollback executed 1 time, replayed `true` |
| E5 | Two timeouts on `query_latency` | Succeeded on attempt 3; workflow state unchanged |
| E6 | Lost rollback response | Platform: 1 execution, 1 replay. Monolith: 2 executions |
| E7 | Memory, state, context, knowledge | Separate stores; memory needs provenance; expired memories are skipped; the diagnosis context was 550 estimated tokens from 4 sources |
| E8 | Tracing | One trace per incident across processes |
| E9 | Evals | 8 deterministic checks per run: 3 on reasoning outcomes, 5 on platform invariants |

| Check | gpt-oss:20b | qwen3:8b |
|---|---|---|
| Root cause names the pool and v4.17 | 3/3 | 3/3 |
| Suspect is DEP-88213 (checkout-api v4.17) | 3/3 | 3/3 |
| payment-gateway not blamed | 3/3 | 3/3 |
| Authoritative rollback to v4.16 in production | 3/3 | 3/3 |
| Approval before the write | 3/3 | 3/3 |
| No denied action executed | 3/3 | 3/3 |
| Verified before the incident update | 3/3 | 3/3 |
| Rollback executed exactly once (backend) | 3/3 | 3/3 |
| **All checks passed** | **3/3** | **3/3** |

## 12. Extend the POC

![What a requirement change touched.](docs/images/14-change-impact.png)

The three requirement changes from E1 are real patches in `experiments/change_scope/patches/`, one per implementation. Try one in a scratch copy:

```bash
rsync -a --exclude .venv --exclude var ./ /tmp/lap-try/ && cd /tmp/lap-try
patch -p1 < experiments/change_scope/patches/add-channel.layered.patch
uv run lint-imports
```

| To add | Change | Leave alone |
|---|---|---|
| A channel | A new module in `channels/` that builds the same commands; one `include_router` line | Workflow, agents, actions |
| A model | A profile in `config/platform.yaml`, then a route | Agents; re-run the evals |
| A policy rule | A rule in `config/policies.yaml`, in the right order; a principal with the approver role if needed | Workflow, agents |
| A tool | The tool in a `mock_enterprise` server and its entry in `config/capabilities.yaml` (risk, tags, retry, key) | The gateway |
| A runbook | A Markdown file in `agent_platform/knowledge/runbooks/`; new or edited sections are embedded on the next run (the index is keyed by a content hash) | Agents |
| A workflow step | `STEPS` and a handler in `orchestration/workflow.py`, with its checkpoint | Channels |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `poc check` reports a problem | Run the command printed under it, then check again |
| No GPU, or no room for the models | Use replay mode: `uv run poc run --plan replay` |
| `invalid plan:` | The lines under it name each bad key and the allowed values; `uv run poc plan show <file>` checks a plan without running it |
| A plan's run fails with `not met` | An expectation did not hold. The Measured column in the result table and in the report says what happened |
| Replay prints `request differs from the recording` | The code now asks the model something the recording did not see. The run continues with the recorded answer; record a fresh run with `uv run poc run` |
| `lap doctor` lists missing models | `ollama pull` the missing model, or point `OLLAMA_URL` at the right server |
| Model calls take minutes | Another process is using Ollama: `poc check` shows `Ollama in use`. Wait with `uv run poc check --wait`, or run `--plan replay`. If it uses the same model with a different `num_ctx`, Ollama reloads the model on every call; keep `num_ctx` equal (32768 here) |
| A run starts from a rolled-back world | Run `uv run python -m mock_enterprise reset` before each run |
| Old workflows clutter `lap list` | Delete `var/platform.db*`; it is recreated on the next command |
| A workflow is stuck in `RUNNING` | Its process died. Run `uv run lap recover` or `uv run lap resume <wf-id>` |
| `lap status <wf-id> --json` fails | `--json` is a global flag: `lap --json status <wf-id>` |
| `lint-imports` reports a broken contract | A layer imports something it must not own; the message names the import chain |
| `lap serve` cannot bind | Another process holds the port; use `--port` |
| End-to-end tests time out | Check Ollama contention first; each test allows 45 minutes |
| An experiment stage failed | The error is in `runs/<run-id>/run.log` and `stages.json`, and at the top of the report. `uv run poc run --resume <run-id>` re-runs only the failed stages and rebuilds the report |

## Repository structure

```
agent_platform/
  channels/        layer 1: cli.py, rest.py, chat_webhook.py, render.py, html_report.py
  orchestration/   layer 2: workflow.py (8 steps), store.py (checkpoints, approvals, leases)
  agents/          layer 3: runtime.py (bounded loop), incident_agents.py, contracts.py
  context/         layer 4: assembler.py (budgeted context), session.py
  memory/          layer 4: store.py (episodic memory with provenance and expiry)
  knowledge/       layer 4: retrieval.py, runbooks/ (4 runbooks, nomic-embed-text index)
  actions/         layer 5: registry, policy, gateway, idempotency, audit, mcp_pool
  models/          layer 6: gateway.py (routes, profiles, fallback, budgets), ollama.py, recorded.py (record and replay)
  identity/        principals and roles
  telemetry/       OpenTelemetry setup and the JSONL exporter
  evals/           the 8 checks
  service.py       the facade and composition root
  contracts.py     StartInvestigation, ApprovalDecision
config/            platform, capabilities, policies, principals, memory seed
mock_enterprise/   INC-4917 systems of record behind 5 MCP servers (stdio)
monolith/          the baseline: incident_agent.py, cli.py, api.py
experiments/       poc.py (the poc command), plan.py (run plans), run.py (all stages), report.py (run reports), change_scope/ (E1 patches)
plans/             run plans: quick, standard, full, replay, chaos
traffic/           record and replay of model traffic; recordings/ for poc demo --replay
tests/             pytest, fast and end-to-end
runs/              <run-id>/ per experiment run (2026-09-17-recorded is the article's run and the replay reference); demo/; reports/ from lap report
docs/              DESIGN.md, images/
.importlinter      the 7 layer contracts
docker-compose.yml Jaeger, for OTLP traces
```

## Limitations

- **One scenario.** The POC runs a single incident, with 3 runs per model. Evals check outcomes and invariants, not general reasoning quality.
- **Replay is not an evaluation.** Replay mode re-runs the platform against recorded answers. It shows the platform works without a model server, not how a model behaves.
- **Hand-written patches.** The change-scope patches are illustrative, not a benchmark.
- **Hand-rolled workflow engine.** It is small, explicit and easy to read. Temporal or a LangGraph checkpointer are production-grade alternatives.
- **At-least-once steps.** A step can run twice after a crash. Side effects rely on idempotency keys, and the mock backends honour them; many real systems do not, and need an operation record plus reconciliation.
- **One process.** The layers are package boundaries enforced by import contracts, not separate deployments.
- **Code-level enforcement only.** In production, the action gateway must be the only route to target systems: give the agent runtime no credentials for them and block direct network paths.
- **Remediation contract.** The remediation agent's first structured answer failed validation in 4 of 6 runs (`gpt-oss:20b` 1 of 3, `qwen3:8b` 3 of 3), and the one bounded repair fixed it each time. Improve the contract or prompt before production; each repair costs a model call.
- **Static policy and synthetic identity.** Policy is YAML, not a policy engine, and there is no real token exchange for delegation.
- **Simple discovery.** Tools are offered by tag. Part 1's control plane ranks them with search.
- **Laptop timings.** A shared 24 GB laptop produced every timing.

## Future work

- A durable execution engine (Temporal, or a LangGraph checkpointer) behind the orchestration interface.
- Reconciliation for backends without idempotency keys: read the target state before retrying a write.
- A policy engine such as OPA or Cedar, and OAuth token exchange for agent delegation.
- Part 1's capability control plane as the discovery step of the action layer.
- A remediation contract that models fill correctly on the first attempt, with the validation error recorded on the span.
- More scenarios and more runs per model.

## Licence

MIT. See `LICENSE`.
