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

## Results (run `2026-10-08-recorded`, no number typed by hand)

| # | Claim | Naive arm | Controlled arm | Result |
|---|---|---|---|---|
| 1 | Capacity is enforced before unlimited work enters the runtime | work in system 5,791, goodput 9.3 % | 128 (bound 128), goodput 45.5 % | SUPPORTED |
| 2 | Tenant-aware controls, not only global limits | support in time 3.6 % | 100 %, finance completes in 374.9 s | SUPPORTED |
| 3 | Concurrency bounded independently of demand | running max 1,227, goodput 44.2 % | 32, goodput 84.4 % | SUPPORTED |
| 4 | Explicit execution budgets, propagated to children | runaway 18,960.3 cu | 150 cu; legitimate cut 4 of 350 | QUALIFIED |
| 5 | Routing within a quality/policy contract | all-large 24.9 cu/success | routed 10 cu/success, 0 violations | SUPPORTED |
| 6 | Context and retrieval need resource controls | 34,716 tokens/query, cache leaks 5 | 5,982, required ids missing 0, leaks 0 | SUPPORTED |
| 7 | Tool capacity governed independently | 237 503s, 2.8 attempts/call | 0 503s; composed: support 100 % | SUPPORTED |
| 8 | Non-code changes create a distinguishable release | 1 image digest | 7 release ids, every row attributable | SUPPORTED |
| 9 | Machine-checkable gates before traffic | — | traffic to blocked candidates 0 % | SUPPORTED |
| 10 | Behavioural canaries and rollback | error delta 0 pp | tool calls 88.9 % → ROLLBACK | SUPPORTED |

Proof pack: 11 experiments (ten scenarios and the negative control), 65 checks (63 pass, 1 recorded
limitation, 1 negative control). Tests: 23 of 23 pass
(10 of 10 scenario tests). Replay: EXACT, 99 of
99 files byte-identical.

**What did not hold, or surprised us.** The envelope, calibrated on a development sample, stopped
4 legitimate workflows that had re-run after a wrong answer (a LIMITATION OBSERVED). The tool
gateway alone protected the API and starved support (5.3 % served), which is why E7 has a
composed arm. A canary comparing raw window averages rolled back the clean release R42-e (recorded decision: ROLLBACK). Under
the declared success table, all-small was cheaper per success than routing, and it broke the capability contract
516 times.

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

`experiments/preregistration.toml` (frozen, `FROZEN.sha256`) → `runs/2026-10-08-recorded/` (raw rows, requests, timelines,
counters, manifests, decisions) → `runs/2026-10-08-recorded/facts.json` (aggregated from the files) → `../proof/*.toml` →
`../evidence/runs/2026-10-08-recorded/` (checks, results, negative control, replay, SHA256SUMS) and `../results/claim-evidence.json`
(claim → scenario → mechanism → evidence → result) → every fact token in both editions and this README. Changes made
before and after the freeze are in `experiments/DEVIATIONS.md`.

## Layout

```text
agentops/        sim, platform, runtime, budget, agent, router, retrieval, tools, release, scenarios, run, cli, common
config/          platform, models (contract + outcome table), tools, workflows, releases     (frozen)
experiments/     preregistration.toml, scenarios.toml, fixtures/{knowledge,eval_suite}.json, FROZEN.*, DEVIATIONS.md
scripts/         make_fixtures.py (how the two fixtures were generated, seed 4917)
tests/           test_scenarios.py (the ten), test_units.py
runs/            PUBLISHED, 2026-10-08-recorded/
```

Northwind Goods, its customers and its systems are fictional. MIT licence.
