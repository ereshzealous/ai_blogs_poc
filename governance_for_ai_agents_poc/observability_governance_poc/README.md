# observability_governance_poc · T5 POC

**The question it tests:** after an autonomous production action, can the platform reconstruct and prove the complete causal
chain from intent to physical side effect, and how much of that can application logs and distributed traces reconstruct on
their own?

One production rollback (INC-4471, payment-service v4.18.0 → v4.17.2) runs in 15 scenarios across 12 experiments (one of them the normal happy path), each with a
concurrent second agent execution (INC-4472, checkout-service). Every scenario runs **once** and is observed **three ways**:

| Layer | The investigator may read |
|---|---|
| L0 · application logs | each component's own log, trace ids removed, plus the approval service's tables |
| L1 · logs + traces | the same logs with trace context, plus every OpenTelemetry span of every process |
| L2 · execution lineage | the hash-chained evidence events, the witness anchors, and the deployment API's transaction lookup by idempotency key |

Thirteen questions (Q1–Q13) are answered from each layer alone and scored against ground truth taken from the systems of record
(`lineage/truth.py`), never from the layers under test.

## What is real, simulated, recorded

- **Real:** OS processes (two agent runtimes, the deployment API, the approvers, the harness); `SIGKILL` crashes and restarts;
  HTTP on localhost, including a real client socket timeout; SQLite durability; `Idempotency-Key` handling with stored
  responses, 409 and 422; retries; the OpenTelemetry Python SDK with W3C `traceparent` propagation across processes; SHA-256
  hash chain, witness anchors and verification; versioned policy documents with digests; HMAC-signed, action-bound approvals;
  the tests.
- **Simulated:** the deployment API and its faults (reject before commit, acknowledge without applying, drop the response after
  commit); the incident; the people (a scripted operator); identities and credentials; the compromised plan in E7; the
  duplicate delivery in E6; the external witness (a file).
- **Recorded:** every model call (qwen3:8b via Ollama) on a tape keyed by the sha256 of the exact request; replay needs no model.

Full detail: `../results/observability-governance-real-vs-simulated.md`.

## Requirements

Python 3.12 and [`uv`](https://docs.astral.sh/uv/) (it installs everything). No GPU, API key or network for replay and tests.
Live recording only: [Ollama](https://ollama.com) with `qwen3:8b` pulled.

## Commands

```bash
uv sync --group dev

# deterministic, no model
OLLAMA_URL=http://127.0.0.1:1 uv run pytest                  # 31 tests: unit, real-process, end-to-end scenarios
uv run lineage demo                                          # the flagship (lost response) from the published tape, then its evidence
uv run lineage run replay 2026-09-30-recorded --run-id my-replay   # every scenario again, model answers from the tapes
uv run lineage run smoke --only e11-false-success            # one scenario into runs/_smoke

# inspect
uv run lineage inspect e12a-lost-response                    # one execution, event by event, and what each layer could answer
uv run lineage verify-evidence                               # recompute every hash chain, check it against the witness anchors
open runs/2026-09-30-recorded/summary.md                     # the run in one page

# live (needs Ollama + qwen3:8b); never overwrites an existing run
uv run lineage run record --run-id <new-id>
uv run lineage drift record --run-id <new-id>
```

## Where the article's numbers come from

The published run is named in `runs/PUBLISHED`: **`2026-09-30-recorded`**.

| File | Holds |
|---|---|
| `runs/<run>/facts.json` | every measured number the articles cite, each with the file it was computed from |
| `runs/<run>/checks.json` | 7 publishability checks (all pass) |
| `runs/<run>/summary.md` | reconstruction totals, scenario table, checks, predictions, tamper results |
| `runs/<run>/reports/comparison.{json,md}` | every layer's answer to every question in every scenario, with truth, verdict and joins |
| `runs/<run>/reports/results.{json,md}` | outcome, production changes, attempts, processes, evidence events per scenario |
| `runs/<run>/reports/{tamper,telemetry,timeline,predictions,drift,replay-comparison}.json` | the tamper experiment, telemetry loss and sampling, E12's timeline, predictions and expectations, the drift probe, the replay comparison |
| `runs/<run>/scenarios/<scenario>/` | `spec.json`, `logs/`, `telemetry/` (spans, metrics), `evidence/` (export + verification), `world/` (before, after, the deployment API's request log), `truth.json`, `reconstruction.json`, `result.json`, `procs/`, `tape/` |
| `runs/<run>/{telemetry,evidence,state,model,commands}/` | run-level concatenations and the exact commands |

To reproduce a number: find its key in the article's source (`../docs/source/**`, e.g. `{{e12a_mutations}}`), look it up
in `facts.json` for its source file, and rerun `uv run lineage run replay 2026-09-30-recorded --run-id check` to regenerate
that file from the tapes.

## Layout

```text
lineage/
  runtime.py      the agent runtime: durable workflow, three records (logs, telemetry, evidence)
  gateway.py      the tool gateway: catalog + authorization check, action/attempt identity, idempotency, retries
  deploysvc.py    the simulated deployment API (separate process, HTTP, SQLite, faults)
  approval.py     the approval service: action-bound, signed decisions
  policy.py       versioned deterministic policy engine
  model.py        model gateway + record/replay tape; decision evidence, no reasoning
  evidence.py     hash-chained, schema-bound, anchored evidence store + verify()
  telemetry.py    OpenTelemetry setup, seeded ids, JSONL exporter, propagation
  semconv.py      the attribute names used, in one place
  operator.py     the scripted approvers
  run.py          the harness; collect.py, truth.py, investigate.py, aggregate.py score and report
  drift.py        the D1 drift probe; crash.py named SIGKILL points; cli.py
config/           world, control plane (agent configs, prompt templates, tool catalog), policies v41/v42, principals, data, retention, drift
experiments/      preregistration.toml (frozen; digest in each run manifest)
tests/            evidence, policy and approval binding, real deployment API process, ids and scoring, end-to-end scenarios
runs/             2026-09-30-recorded (published), 2026-09-30-recorded-replay
```

See also `ARCHITECTURE.md`, `EXPERIMENTS.md`, `LIMITATIONS.md`.
