# ops_poc · an agent-operations simulator (O1 + O2)

*Production AI Engineering · Scale & Operations · the POC behind “Operating AI Agents at Scale — Cost, Latency, Scale & Lifecycle”*

**Question.** When usage becomes large and the system keeps changing, which platform controls keep an agent platform
inside its operating envelope, and what do they cost?

**Answer, in this simulator:** two control loops. Admission, fair scheduling, bounded concurrency, workflow envelopes,
routing inside an eligibility contract, context budgets and a tool gateway govern demand and resources (the runtime
loop). A behavioural release manifest, invariant gates and a behavioural canary govern change (the change loop).

> **Simulation units only.** Every number here is in simulated milliseconds (sim-ms) and cost units (cu), from a
> deterministic simulation. These results show how architectural mechanisms behave under a declared workload. They are
> not performance benchmarks of any real LLM provider, model or platform.

## Results (run `{{run.id}}`, no number typed by hand)

| # | Claim | Naive arm | Controlled arm | Result |
|---|---|---|---|---|
| 1 | Capacity is enforced before unlimited work enters the runtime | work in system {{e1.naive.max_work_in_system}}, goodput {{e1.naive.goodput_pct}} % | {{e1.controlled.max_work_in_system}} (bound {{cfg.work_in_system_bound}}), goodput {{e1.controlled.goodput_pct}} % | SUPPORTED |
| 2 | Tenant-aware controls, not only global limits | support in time {{e2.naive.support.goodput_pct}} % | {{e2.controlled.support.goodput_pct}} %, finance completes in {{e2.controlled.finance.makespan_s}} s | SUPPORTED |
| 3 | Concurrency bounded independently of demand | running max {{e3.naive.max_active}}, goodput {{e3.naive.goodput_pct}} % | {{e3.controlled.max_active}}, goodput {{e3.controlled.goodput_pct}} % | SUPPORTED |
| 4 | Explicit execution budgets, propagated to children | runaway {{e4.none.runaway.cost_cu}} cu | {{e4.envelope.runaway.cost_cu}} cu; legitimate cut {{e4.envelope.legit_cut}} of {{e4.envelope.legit_n}} | QUALIFIED |
| 5 | Routing within a quality/policy contract | all-large {{e5.all-large.cost_per_success}} cu/success | routed {{e5.routed.cost_per_success}} cu/success, {{e5.routed.data_violations}} violations | SUPPORTED |
| 6 | Context and retrieval need resource controls | {{e6.naive.context_tokens_mean}} tokens/query, cache leaks {{e6.cache.query-text.cross_principal}} | {{e6.bounded.context_tokens_mean}}, required ids missing {{e6.bounded.missing_required}}, leaks {{e6.cache.scoped.cross_principal}} | SUPPORTED |
| 7 | Tool capacity governed independently | {{e7.naive.http_503}} 503s, {{e7.naive.attempts_per_call}} attempts/call | {{e7.controlled.http_503}} 503s; composed: support {{e7.composed.support_goodput_pct}} % | SUPPORTED |
| 8 | Non-code changes create a distinguishable release | {{e8.distinct_image_digests}} image digest | {{e8.distinct_release_ids}} release ids, every row attributable | SUPPORTED |
| 9 | Machine-checkable gates before traffic | — | traffic to blocked candidates {{e9.blocked_weight_granted}} % | SUPPORTED |
| 10 | Behavioural canaries and rollback | error delta {{e10.R42-a.mix-adjusted.last.error_pp}} pp | tool calls {{e10.R42-a.mix-adjusted.last.tool_calls_pct}} % → {{e10.R42-a.mix-adjusted.decision}} | SUPPORTED |

Proof pack: {{proof.experiments}} experiments (ten scenarios and the negative control), {{proof.checks}} checks ({{proof.pass}} pass, {{proof.fail}} recorded
limitation, {{proof.expected_failure}} negative control). Tests: {{tests.passed}} of {{tests.total}} pass
({{tests.scenarios_passed}} of {{tests.scenarios}} scenario tests). Replay: {{replay.level}}, {{replay.identical}} of
{{replay.files}} files byte-identical.

**What did not hold, or surprised us.** The envelope, calibrated on a development sample, stopped
{{e4.envelope.legit_cut}} legitimate workflows that had re-run after a wrong answer (a LIMITATION OBSERVED). The tool
gateway alone protected the API and starved support ({{e7.controlled.support_goodput_pct}} % served), which is why E7 has a
composed arm. A canary comparing raw window averages rolled back the clean release R42-e (recorded decision: {{e10.R42-e.raw.decision}}). Under
the declared success table, all-small was cheaper per success than routing, and it broke the capability contract
{{e5.all-small.capability_violations}} times.

## What this proves, and what it does not

**Proves (under the declared workload):** each control changes the modelled outcome in the direction its claim says,
the comparison arm really fails without it, and every number traces to raw rows that a rerun reproduces byte for byte.

**Does not prove:** real provider latency, quotas or prices; real model quality (the eligibility contract and success
table are declared assumptions); how much a prompt or tool-description change moves a real model (the scripted agent
follows descriptions literally, so R42-a's effect is declared); real tool limits; human approval capacity; shadow traffic; rollback of stateful
artifacts; how much any organisation will save.

## Architecture

```text
Synthetic workload (seeded arrivals, cases, clients that time out and retry)
        │
        ▼
Admission (open | bounded, 429 + Retry-After)         platform.py      C · Orchestration
        │
        ▼
Scheduler (FIFO | weighted fair + bulkheads), slots, deadline-aware dequeue, cancellation
        │
        ▼
Agent runtime: envelope ledger checked before each step     runtime.py, budget.py, agent.py   D · Agent runtime
        ├──► retrieval (bounded, scoped cache)               retrieval.py     E · Context
        ├──► model router + provider quotas + fallback        router.py        F · Model services
        └──► tool gateway → downstream simulator              tools.py         G · Tool & action
        │
        ▼
Telemetry rows (one per attempt) → facts.json → proof pack / canary decisions

Release manifest (content-addressed) → offline eval + invariant gate → registry → canary → promote | rollback
                                                                          release.py, scenarios.py
```

Engine: `sim.py`, a discrete-event simulator on a virtual integer clock. Python 3.12 standard library only for the
simulator; `uv` provides the environment and `pytest` the tests.

## Run it

```bash
uv sync --group dev                    # Python 3.12 via uv; pytest is the only dev dependency
uv run pytest                          # 10 scenario tests (one per claim) + unit tests, no network, no model
uv run agentops demo                   # the surge with and without admission, then the canary
uv run agentops scenario E2            # any of E1, E2, E3, E5, E7, every arm
uv run agentops explain E10-canary     # a recorded decision explained from the run's files
uv run agentops prereg-check           # the frozen preregistration is unchanged
uv run python -m agentops.run record --run-id my-run   # a new full run -> runs/my-run/ (about 25 s)
```

From the package root: `make test`, `make replay` (byte-for-byte rerun), `make pack`, `make verify`.

## The ten scenarios

| Scenario | Variable (the only thing that differs) | Test |
|---|---|---|
| E1 · admission | open queue vs bounded work in system + capacity error | `test_01` |
| E2 · fairness | one FIFO vs weighted fair scheduling + finance bulkhead | `test_02` |
| E3 · concurrency | unbounded vs slots + bounded queue + deadlines + cancellation | `test_03` |
| E4 · envelopes | none vs per-agent vs propagated envelope | `test_04` |
| E5 · routing | all-large vs all-small vs routed vs routed with any fallback | `test_05` |
| E6 · context | naive vs bounded retrieval; query-text vs scoped cache | `test_06` |
| E7 · tool gateway | direct calls vs gateway vs gateway + fair scheduling | `test_07` |
| E8 · release identity | R41 vs six one-artifact candidates | `test_08` |
| E9 · invariant gates | five candidates through the offline suite | `test_09` |
| E10 · canary | R42-a and R42-e at 10 / 50 / 100 %; mix-adjusted vs raw | `test_10` |

The negative control (admission removed) is in the proof pack, not an eleventh test.

## How the evidence maps to the article

`experiments/preregistration.toml` (frozen, `FROZEN.sha256`) → `runs/{{run.id}}/` (raw rows, requests, timelines,
counters, manifests, decisions) → `runs/{{run.id}}/facts.json` (aggregated from the files) → `../proof/*.toml` →
`../evidence/runs/{{run.id}}/` (checks, results, negative control, replay, SHA256SUMS) and `../results/claim-evidence.json`
(claim → scenario → mechanism → evidence → result) → every fact token in both editions and this README. Changes made
before and after the freeze are in `experiments/DEVIATIONS.md`.

## Layout

```text
agentops/        sim, platform, runtime, budget, agent, router, retrieval, tools, release, scenarios, run, cli, common
config/          platform, models (contract + outcome table), tools, workflows, releases     (frozen)
experiments/     preregistration.toml, scenarios.toml, fixtures/{knowledge,eval_suite}.json, FROZEN.*, DEVIATIONS.md
scripts/         make_fixtures.py (how the two fixtures were generated, seed 4917)
tests/           test_scenarios.py (the ten), test_units.py
runs/            PUBLISHED, {{run.id}}/
```

Northwind Goods, its customers and its systems are fictional. MIT licence.
