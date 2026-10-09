# recovery_poc · failure classification, execution certainty and recovery evals

*R1 + R2 · Evals, Observability & Production Reliability · Production AI Engineering*
*Rendered from `README.template.md` by `tools/build_readme.py`; every number is a fact of run `{{run.id}}`.*

## Purpose

When an agent step fails, which recovery should the runtime invoke? This POC injects {{scenarios}} preregistered faults
into one agent workflow and runs each through three runtimes that differ **only** in their recovery layer:

- **A0 naive:** `catch Exception → retry` the step, then fail the run.
- **A1 idempotent retry:** the same, with a stable operation id per write sent as `Idempotency-Key` (the mechanism F2 and T5 measured).
- **A2 classified:** evidence → failure class → **execution certainty** (`NOT_EXECUTED` / `EXECUTED` / `UNKNOWN`) + the tool’s
  side-effect contract + persisted state → a frozen, deterministic **recovery matrix** → one of nine actions.

Then it breaks A2 on purpose ({{mut.total}} mutants) to show the eval suite catches it, gates a deterministic model change,
and measures two real local models against the same output contract.

## Proof at a glance (run `{{run.id}}`)

| | A0 naive | A1 idempotent retry | A2 classified |
|---|---|---|---|
| scenarios with a duplicate external effect | {{A0.dup_scenarios}} | {{A1.dup_scenarios}} | **{{A2.dup_scenarios}}** |
| correct outcome (of {{scenarios}}) | {{A0.outcome_correct}} | {{A1.outcome_correct}} | **{{A2.outcome_correct}}** |
| false claims in the final answer | {{A0.false_claims}} | {{A1.false_claims}} | **{{A2.false_claims}}** |
| retries of refusals | {{A0.terminal_retries}} | {{A1.terminal_retries}} | **{{A2.terminal_retries}}** |
| runs split across traces | {{A0.trace_split}} | {{A1.trace_split}} | **{{A2.trace_split}}** |
| reconciliation queries (the cost) | {{A0.status_queries}} | {{A1.status_queries}} | {{A2.status_queries}} |

- A2’s decisions equal the preregistered oracle in **{{A2.re1_pass}} of {{scenarios}}** scenarios.
- Mutants caught by the eval suite: **{{mut.detected}} of {{mut.total}}**. Negative control (no reconciliation): duplicates in {{nc.dup_scenarios}} scenarios.
- Model change: `scripted-v2` **{{mc.v2.gate}}** by the offline gate; through A2 it executed {{mc.runtime.A2.credits}} credits.
- Real models: {{ms.qwen.model}} **{{ms.qwen.gate}}**, {{ms.llama.model}} **{{ms.llama.gate}}**; unsafe proposals that would have executed: **{{ms.unsafe_executed_total}}**.
- Real model end to end (qwen3:8b deciding, {{live.model.calls}} calls): duplicates {{live.A0.dup_scenarios}} / {{live.A1.dup_scenarios}} / **{{live.A2.dup_scenarios}}**, A2 decisions = oracle {{live.A2.re1_pass}} of {{scenarios}}, unsafe credits {{live.A2.unsafe_credits}}.
- Replay: **{{replay.level}}**, {{replay.identical}} of {{replay.files}} files byte-identical; the real-model run replays from its tapes ({{live.replay.files}} files). Tests: {{tests.passed}} of {{tests.total}} passed.
- Proof pack: {{proof.experiments}} experiments, {{proof.checks}} checks ({{proof.pass}} pass, {{proof.limitation}} declared limitations, {{proof.expected_failure}} expected failure).

## Architecture

```text
                      worker process (python -m recovery.runtime)                    simulated enterprise (world.py, HTTP)
 retrieve ─ lookup ─ decide ─ validate ─ authorize ─ credit ─ ticket ─ notify ─ answer      KB · CRM · model gateway
     │         │        │                               │        │        │                 credits  (key 24 h, query by op id)
     └─────────┴────────┴──── toolclient: Evidence ─────┴────────┴────────┘ ── HTTP ───▶   tickets  (no key, search by reference)
                                     │                                                     messages (no key, no query)
                         classify.py: class + certainty (C1–C11)                            each with its own ledger
                                     │
                         policy.py: recovery matrix (config/recovery-matrix.toml, M01–M99)
                                     │
        journal.py (SQLite): intent before dispatch · result after outcome · events · checkpoints · trace id
        telemetry.py: OTel-shaped spans (gen_ai.* + recovery.*), link on resume, value redaction
        evals.py: I1–I12 · RE1–RE4 · TR1 · OE1 over a run directory
```

| Module | Role |
|---|---|
| `recovery/world.py` | providers, ledgers, idempotency windows, deadlines, provider-side faults |
| `recovery/toolclient.py` | one HTTP call → `Evidence` (sent, transport, received, status) |
| `recovery/classify.py` | evidence → `FailureEvent` (class, layer, certainty, rule) |
| `recovery/policy.py` | situation → matrix rule → action |
| `recovery/journal.py` | the workflow store; injectable write failures |
| `recovery/runtime.py` | the agent and the three recovery layers; crash points |
| `recovery/telemetry.py` | spans, links, redaction |
| `recovery/evals.py` | the eval suite |
| `recovery/modelslice.py` | Ollama calls, tape, deterministic scoring, release gate |
| `recovery/harness.py` · `run.py` · `cli.py` | one scenario run · the recorded run and its facts · the command line |

## Prerequisites

- macOS or Linux, Python 3.12 and [uv](https://docs.astral.sh/uv/). No other dependency (the POC is standard library; pytest for tests).
- For a **new** recording only: [Ollama](https://ollama.com) with `qwen3:8b` and `llama3.1` pulled. Everything else runs without a model.
- For figures and PDFs: Google Chrome (headless).

## Run

From the package root (`evals_obs_reliability/`):

```bash
make setup                      # uv sync
make demo                       # S09, the flagship, through A0 and A2, explained
make scenario S=S16 A=A2        # any scenario, any runtime (S00–S24; A0, A1, A2)
make demo-mutant X=X1 S=S11     # a scenario under a mutant of the recovery layer
make test                       # unit + end-to-end tests (real processes, no model)
make prereg-check               # the frozen files are unchanged
make replay                     # re-execute every deterministic experiment and compare byte for byte
make verify                     # PROOF VERIFICATION of the published run
make console                    # the Lab Console (results/lab-console.html)
make record ID=<new-id>         # a new recorded run, including the real-model slice
```

Or directly: `cd recovery_poc && uv run recovery demo`, `uv run recovery list`, `uv run recovery explain runs/{{run.id}} S16 A2`.

## Real-model end-to-end run: run it and capture it

The fault scenarios use a scripted decision step so that the recovery layer is the only variable. The real-model run
repeats every scenario through every runtime with **qwen3:8b** making every decision (Ollama, temperature 0, seed 1,
JSON mode) and **llama3.1** as the fallback model. Faults, providers, crashes and recovery layers are unchanged.

**Published result** (run `{{live.run.id}}`, {{live.model.calls}} model calls):

| | A0 naive | A1 idempotent retry | A2 classified |
|---|---|---|---|
| scenarios with a duplicate effect (scripted → real model) | {{A0.dup_scenarios}} → {{live.A0.dup_scenarios}} | {{A1.dup_scenarios}} → {{live.A1.dup_scenarios}} | {{A2.dup_scenarios}} → **{{live.A2.dup_scenarios}}** |
| correct outcomes, real model (of {{scenarios}}) | {{live.A0.outcome_correct}} | {{live.A1.outcome_correct}} | **{{live.A2.outcome_correct}}** |
| unsafe credits committed, real model | {{live.A0.unsafe_credits}} | {{live.A1.unsafe_credits}} | **{{live.A2.unsafe_credits}}** |

A2's decisions equal the preregistered oracle in {{live.A2.re1_pass}} of {{scenarios}}. The model proposed a 480.00 credit
although its prompt sets a 200.00 limit; policy denied it. Identical prompts got identical answers
({{live.model.prompts_with_varying_output}} of {{live.model.distinct_prompts}} prompts varied).

**Prerequisites.** Ollama running locally with both models:

```bash
ollama pull qwen3:8b && ollama pull llama3.1
ollama list                                   # both must be listed
```

**One scenario, live, explained** (≈ 5–10 s per model call):

```bash
make live-scenario S=S09 A=A2                 # or: cd recovery_poc && uv run recovery scenario S09 --arm A2 --live
```

It prints the operator's view (model call, proposal, gates, failure classification, certainty, recovery decision,
ledgers, every eval check) and tapes the model's answer to `var/demo/S09/A2-live/model-tape.jsonl`.

**The full run, recorded** (75 runs, about 15 minutes on an Apple-silicon laptop):

```bash
make record-live ID=2026-10-08-live           # or: uv run python -m recovery.run record-live --run-id 2026-10-08-live
```

**What it captures**, under `recovery_poc/runs/<ID>/`:

| File | What it holds |
|---|---|
| `scenarios/<S>/<arm>/model-tape.jsonl` | every model answer: model, prompt sha256, whether it was a repair, the raw content, token counts |
| `scenarios/<S>/<arm>/events.jsonl` | the run's facts: proposals, gates, policy decisions, dispatches, failure events, recovery decisions, the answer |
| `scenarios/<S>/<arm>/world/ledger.json`, `access.jsonl` | the providers' own records: credits, tickets, messages, every request that reached them |
| `scenarios/<S>/<arm>/telemetry/spans.jsonl` | OTel-shaped spans, one trace per run |
| `scenarios/<S>/<arm>/eval.json` | all {{checks.per_run}} eval checks for that run |
| `scenarios/<S>/<arm>/volatile/model-ms.json` | model latency per call (wall time; never compared) |
| `facts.json`, `summary.md`, `reports/scenarios.json` | the aggregated results per runtime and what the model did |

**Inspect and verify:**

```bash
cd recovery_poc
uv run recovery explain runs/{{live.run.id}} S07 A2     # the over-limit credit the model proposed, and the policy denial
cat runs/{{live.run.id}}/summary.md
cd .. && make replay-live                                # replay from the tapes, no model: byte-identical or it fails
```

A new live run re-asks the model, so its answers can differ from the published tape (another model version, another
machine). The deterministic part cannot; `make replay` checks it.

## Failure scenarios

`experiments/scenarios.toml` (frozen) defines each fault and the oracle. Faults are injected by the providers
(`lost_response`, `stall_then_refuse`, `lost_response_dup`, `unavailable`), by the client (`refused`: a real closed port),
by the journal (`write_fails`) and by the harness (`process:…:sigkill`, `clock:advance_before_resume`). No source edit is
needed to switch faults: a scenario id selects them.

| | Fault | | Fault |
|---|---|---|---|
| S00 | none | S13 | credit rejected (dispute) |
| S01, S02 | model 503 once / all run | S14 | read-only lookup times out |
| S03 | model output not JSON | S15–S17 | SIGKILL before dispatch / in flight / after result |
| S04 | retrieval 503 | S18 | SIGKILL in flight + 25 h of provider time |
| S05, S06 | wrong tool / wrong amount | S19 | ticket lost + ticket search down |
| S07 | credit over the agent’s limit | S20 | credit lost + status query down |
| S08 | refused connection | S21 | provider commits a ticket twice, response lost |
| **S09** | **credit committed, response lost** | S22, S23 | intent write fails / result write fails after commit |
| S10–S12 | every response lost / ticket lost / message lost | S24 | provider stalls, refuses after its deadline |

## Tests

`make test` runs {{tests.total}} tests: {{tests.unit}} unit tests (certainty rules, classes, the matrix, gates, scripted models,
redaction, provider idempotency windows) and {{tests.e2e}} end-to-end tests through real worker processes, including the ten
the brief asked for (safe retry, lost response, reconciliation, idempotency, crash + resume, authorization, argument
validation, trace continuity, eval catches a regression, a model change cannot violate invariants).

## Evals

`recovery/evals.py` scores any run directory with {{checks.per_run}} deterministic checks: invariants I1–I12, recovery evals
RE1–RE4, the trajectory eval TR1 and the outcome eval OE1. The real-model slice adds schema validity, tool selection,
argument accuracy, grounding, unsafe proposals and pass^3, scored against exact labels. No LLM judge is used.

## Expected results

Running `make replay` re-executes every deterministic experiment and must report the published files byte-identical.
`make demo` prints, for S09, two credits under A0 and one under A2, with A2’s `RESPONSE_LOST / UNKNOWN / RECONCILE` and
`RECONCILED / EXECUTED / CONTINUE` decisions. A new live recording re-asks the models, so the slice’s numbers may differ;
the deterministic part may not.

## What this POC proves

- A generic failure signal duplicates external effects and retries refusals; classification plus certainty does not.
- Execution certainty changes the correct action, and a deterministic matrix can pick it in every preregistered scenario.
- An idempotency key is necessary and not sufficient (ignored keys, missing keys, expired keys, lost-outcome reporting).
- Reconciliation by operation id after the request deadline resolves UNKNOWN outcomes (found, absent, duplicate, unavailable).
- Checkpoints must hold intent and result per operation; a step position is not enough.
- One trace survives retries, a SIGKILL and resume when its identity lives in the journal.
- Recovery evals catch bugs an outcome check cannot (X1 in S09).

## What it does NOT prove

- Production failure rates: each scenario ran once, deterministically; this is coverage, not a distribution.
- Behaviour under load, eventual consistency of status queries, partial success, clock skew.
- Anything about model quality beyond two local 8B-class models on sixteen cases, and one model (qwen3:8b) end to end, which on these three cases made the same decisions as the scripted stand-in.
- Exactly-once execution. It shows effectively-once business effects in the measured scenarios, and S12 is the case the runtime cannot rule out and escalates.

## Troubleshooting

- **`make record` fails on the model slice:** `ollama list` must show `qwen3:8b` and `llama3.1:latest`; a remote server can be used with `OLLAMA_HOST`.
- **Spurious timeouts on a loaded machine:** the client timeout is {{cfg.client_timeout_ms}} ms and a lost response is held {{cfg.lost_response_hold_ms}} ms (`config/world.toml`); `make replay` reports any file that differs.
- **`prereg-check` fails:** a frozen file changed; record the change in `experiments/DEVIATIONS.md` before re-freezing.
- **Figures or PDFs fail to build:** headless Chrome must be at `/Applications/Google Chrome.app`; the export loads `@excalidraw/excalidraw` from esm.sh.
