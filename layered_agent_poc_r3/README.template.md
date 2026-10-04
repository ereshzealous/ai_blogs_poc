# Layered agent platform — the same incident agent, built twice

**What this POC tests.** One simulated production incident, INC-4917, solved by two designs, then broken on purpose in
the same places:

- an **agent monolith** — `monolith/incident_agent.py`, one class and one `run()` loop holding the prompt, the model
  client, the tools, the approval callback, the sessions and the logging;
- a **layered platform** — `layered_platform/`, the same capability split across six logical layers with explicit
  contracts between them.

**The architectural question.** Where should production AI responsibilities live, so that a failure or a change does
not propagate through unrelated concerns?

**What it is not.** Not a benchmark, not a throughput study, and not an argument that layering is always better. Two
of its published claims are contradicted by its own evidence; they are kept.

Cited run **`{{run_id}}`** · evidence revision **r3** · {{integrity.scenarios_expected}} preregistered scenarios ·
run verifier **{{verify.passed}}/{{verify.total}}**, {{verify.recomputed}} checks recomputed from raw evidence.

## What the run found

| Question | Monolith | Layered |
|---|---|---|
| Runs passing all eight outcome checks (E1) | {{headline.e1_runs_all_checks.monolith}} | {{headline.e1_runs_all_checks.layered}} |
| Runs with a duplicate physical rollback after a lost reply (E4) | {{headline.e4_duplicate_rollbacks.monolith}} | {{headline.e4_duplicate_rollbacks.layered}} |
| Median tokens spent again after a SIGKILL (E5) | {{headline.e5_median_tokens_after_crash.monolith}} | {{headline.e5_median_tokens_after_crash.layered}} |
| Deterministic write probes that executed (E6) | {{headline.e6_probe_writes_executed.monolith}} | {{headline.e6_probe_writes_executed.layered}} |
| Median trace completeness out of 10 (E8) | {{headline.e8_median_trace_score.monolith}} | {{headline.e8_median_trace_score.layered}} |
| Files changed by a cross-cutting dry-run requirement (E9) | {{headline.e9_files_changed.monolith}} | {{headline.e9_files_changed.layered}} |

The last row contradicts the easy story: the layered implementation changed **more** files. What layering changed is
that the crossing is explicit — the diff goes through the request contract, so every layer that had to agree is named
in it. `docs/published/change-surface.md` explains why a file count alone is the wrong measure.

Layering also did not prevent a model mistake. In one scenario the model proposed an invalid release identifier and
the tool contract refused it: `docs/published/experiment-inventory.md` has that case, and it is classified
`NOT_EXPOSED` rather than counted as crash recovery, because its injected SIGKILL never fired.

## How the evidence works

Four files per run, and nothing else is a source of a published number:

| File | What it holds |
|---|---|
| `runs/<id>/manifest.json` + `source_hashes.json` | the hash of every input the run depended on: plan, prompts, policy, capabilities, runbooks, scenario data, source tree, lockfile |
| `runs/<id>/facts.json` | every measured value the run supports, and nothing it does not |
| `runs/<id>/verification.json` | those values **recomputed from the raw records** — each scenario's own `world.db`, the approval and process logs, the model tapes, the ledgers, the traces, the patch text and the JUnit file |
| `runs/<id>/outcomes.json` | every scenario as `SUCCESS`, `FAILURE`, `ERROR` or `NOT_EXPOSED`, with the exposure denominator for each fault |

`docs/published/claim-evidence-matrix.md` maps every published claim to its facts path, the check that recomputes it,
the raw files, the tests, and what the evidence does **not** show. `docs/architecture-invariants.md` states the
fifteen properties the architecture claims (`L1`–`L15`) and six it explicitly does not (`N1`–`N6`);
`docs/invariants.yaml` is the machine-readable form, checked against this repository by
`tests/architecture/test_invariant_coverage.py`.

## Check it yourself

```bash
uv sync                                                   # Python 3.12, mcp==2.2.0
uv run pytest -m "not model"                              # the suite; no model, no network
uv run python scripts/verify_evidence.py runs/{{run_id}}
uv run python scripts/classify_outcomes.py runs/{{run_id}}
```

The verifier is the one that matters: it reports {{verify.passed}}/{{verify.total}} and recomputes
{{verify.recomputed}} of those checks from the primary records rather than re-reading the file that produced them.

**Live run against replay.** A live run calls the local models, takes tens of minutes and produces a new run
directory; a replay serves every model answer from the recorded tape and calls nothing:

```bash
uv run python scripts/record_run.py                       # a new live run: needs ollama with gpt-oss:20b and qwen3:8b
uv run python scripts/replay_run.py runs/{{run_id}}       # deterministic: {{replay.model_calls_served_from_tape}} answers from tape, {{replay.fresh_model_calls}} fresh calls
```

Replaying reproduces the pipeline and the counts. It does not prove a live model would answer the same way again, and
it is not a second independent trial.

Four test populations, never added together:

| Population | Result |
|---|---|
| Tests during the cited run | {{accounting.cited_run.passed}} passed of {{accounting.cited_run.cases}} |
| Current repository suite | {{accounting.current.passed}} passed ({{accounting.current.model_tests_excluded}} live-model tests excluded) |
| Post-run evidence tests | {{accounting.post_run.passed}} passed |
| Run-verifier checks | {{accounting.verifier.passed}} of {{accounting.verifier.total}} |

## Where things are

```
layered_platform/      experience · orchestration · runtime · context · memory · tools · models · policy · telemetry · evals · storage
monolith/              the baseline: one class, one run() loop
mcp_servers/           real MCP servers over stdio (itsm, observability, deploy, deploy_v2)
simulated_enterprise/  the SQLite world behind them: INC-4917 data, runbooks, memory seed
recordreplay/          the model tape, at the Ollama HTTP boundary
crashpoints.py         named points where a process SIGKILLs itself (F2_CRASH_AT)
experiments/           preregistration/experiment_plan.yaml · changes/*.patch · runners/ · scorers/
scripts/               record_run · replay_run · build_summary · verify_evidence · recompute · classify_outcomes
tests/                 unit · contract · architecture · integration · fault_injection · model · evidence
docs/                  architecture-invariants.md · invariants.yaml · claims.yaml · published/
runs/{{run_id}}/       manifest · source_hashes · facts · verification · outcomes · summary · scenarios/* · raw/*.jsonl · experiments/E1..E9 · diffs/
```

Start here: **[the Evidence Check](docs/published/evidence-check.md)**, the reader-facing audit. Then
[the claim-evidence matrix](docs/published/claim-evidence-matrix.md),
[the run report](docs/published/run-report.md) (the forensic record),
[what was real and what was simulated](docs/published/real-vs-simulated.md),
[the monolith fairness review](docs/published/monolith-fairness-review.md),
[the standardization report](docs/published/standardization-report.md) and
[the immutability audit](docs/published/immutability-audit.md). The HTML and PDF editions of
the Evidence Check and the run report, the Lab Console and the figures are in the release bundle that accompanies the
article, not in this repository.

## Limitations

- One simulated incident. The enterprise systems, the identities, the approvals and the injected faults are
  simulated; MCP over stdio, the local models, SQLite durability, the process kills and the OpenTelemetry spans are
  real.
- Three seeds per cell at temperature 0, on one laptop. That is regression evidence, not a reliability estimate, and
  the timings are hardware-dependent.
- The approver is scripted. This POC tests authorization semantics, not human judgement.
- Two local Ollama models behind one adapter. That is not a provider-independence result.
- An architecture experiment, not a throughput or cost benchmark. The layered platform spends **more** model calls
  and tokens on the same incident, by design.
- It does not show that layering prevents model mistakes, that six deployed services are required — all six layers
  run in one process — or that any of this generalizes to production.

## What it does show

Specific production guarantees can have explicit owners: provider and model concerns in **Model Services**,
execution and recovery in **Runtime**, workflow progression in **Orchestration**, durable workflow truth in
**State**, execution contracts and operation identity in **Tools + Actions**, deterministic authorization in
**Policy**, and reconstruction in **Observability**. Cross-cutting requirements may still legitimately cross several
layers; what changes is that the crossing becomes a contract you can test.

**Layers isolate responsibility. Contracts make the isolation testable.**

MIT licensed (`LICENSE`).
