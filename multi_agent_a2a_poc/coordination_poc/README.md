# C1 POC · One agent, a workflow with agents, or multiple agents over A2A?

*Production AI Engineering · Coordination track · C1.* The POC behind
*Do You Actually Need Multiple Agents?* ·
technical edition.

**Question.** On the same headless capability, the same model, tools, policy and budget, does splitting one reasoning
component into several autonomous ones produce a better production system? And what does an A2A boundary cost on its
own?

## Results (blind set, recorded run `2026-10-08-blind`)

Eight blind incidents × three architectures × three repeats = 72 runs, local `gpt-oss:20b`, strictly serial.

| | A · One agent | B · Workflow + selective agents | C · Multi-agent over A2A |
|---|---|---|---|
| task success (of 24) | **9** (21–57%) | **16** (47–82%) | **12** (31–69%) |
| · simple incidents (of 9) | 6 | 5 | 4 |
| · complex incidents (of 9) | 0 | 6 | 4 |
| median latency | 30.2 s | 11.3 s | 141.2 s |
| median tokens | 25536.5 | 5253.0 | 63108.0 |
| median model calls | 10.0 | 2.0 | 35.0 |
| median tool calls | 8.0 | 9.0 | 16.0 |
| median duplicate tool calls | 0.0 | 0.0 | 5.0 |
| median handoffs | 0.0 | 2.0 | 5.0 |
| state conflicts (claims the ledger contradicts) | 2 | 0 | 0 |
| prohibited actions requested | 0 | 0 | 0 |

Preregistered hypotheses: H1 SUPPORTED · H2 NOT SUPPORTED · H3 SUPPORTED · H4 SUPPORTED · H5 SUPPORTED · H6 SUPPORTED · H7 SUPPORTED · H8 SUPPORTED · H9 NOT SUPPORTED
(definitions in [`experiments/preregistration.toml`](experiments/preregistration.toml)).

Per incident: B had more successes than C on 3 of 8 incidents, fewer on 1, the
same on 4; C used more tokens than B on 8 and more time on 8. The Wilson intervals above are
over runs; the three repeats of an incident share its fixture and are not independent incident samples.

A2A boundary on its own (E7, scripted model, same agent code, loopback HTTP on one machine, no TLS):
3.81 ms in-process vs 9.17 ms over A2A per delegation (median).

Post-run fix (DEVIATIONS D3): the blind run found a fail-open fallback in C's execute delegations (an authorized
execution without a proposal got every eligible write scope, 1 of 16);
the post-run correction changed it to fail closed. Published numbers come from the code as it ran
(`experiments/as-run/`, still matching `FROZEN.sha256`); `coord.freeze check` lists the two changed files.

Replay: all 72 blind workflows re-executed from the model tape, with no model: **REPLAY IDENTICAL**.

No number in this README is typed by hand: each is substituted from `runs/2026-10-08-blind/facts.json`, which
`coord/analysis.py` computes from the recorded rows.

## What is in here

```text
coord/            the system: world, mcp_servers, gateway, identity, policy, store, models, tape, telemetry, agent_loop,
                  runtime (the headless capability), arch_a, arch_b, arch_c, specialists, a2a_server, a2a_link, supervisor,
                  evaluate, metrics, bench, exp_failure (E6), exp_boundary (E7), analysis, verify_replay
config/           capabilities, principals (scopes, delegation edges), policies, model profile, limits, agents (A2A ports)
fixtures/         12 simulated incidents (D1-D4 dev, B1-B8 blind) + the shared runbooks
groundtruth/      labels.yaml: read only by coord/evaluate.py
experiments/      preregistration.toml, FROZEN.sha256, label-review.md, tuning-log.md, DEVIATIONS.md,
                  POST-RUN-CHANGES.sha256 + as-run/ (the D3 fix: what changed after the run, and the files as they ran)
tests/            64 tests, no model: identity, policy, gateway over real MCP, runtime termination, real A2A processes,
                  fail-closed execute delegation (DEVIATIONS D3)
runs/<run>/       rows.jsonl, manifest.json, facts.json, tape/, session/{platform.db, world.db, traces/, logs/}
```

## Run it

Python 3.12, uv, [Ollama](https://ollama.com) with `gpt-oss:20b` for live runs (tests and E7 need no model).

```bash
uv sync --group dev
uv run pytest                                                     # 64 tests, no model, ~40 s
uv run python -m coord.bench run --run-id try --fixture B1 --arch C --scripted        # one workflow, no model
uv run python -m coord.bench run --run-id try-live --fixture B1 --arch A              # one workflow, live
uv run python -m coord.bench matrix --run-id my-blind --fixtures B1,B2,B3,B4,B5,B6,B7,B8 --archs A,B,C --repeats 3 --tape record
uv run python -m coord.exp_failure --run-id my-e6            # E6: SIGKILL an agent process mid-task
uv run python -m coord.exp_boundary --run-id my-e7           # E7: the same agent in-process vs over A2A
uv run python -m coord.bench matrix --run-id my-e8 --fixtures B1,B2,B3,B4,B5,B6,B7,B8 --archs C --repeats 1 \
    --overrides '{"ablation": true, "workflow": {"max_total_tokens": 600000}}'                  # E8
uv run python -m coord.report my-blind                       # console summary
uv run python -m coord.bench matrix --run-id my-blind ... --tape replay && uv run python -m coord.verify_replay my-blind
# a run recorded before the D3 fix replays with: --overrides '{"multi_agent_c": {"execute_without_proposal": "all_writes"}}'
```

## What is real and what is simulated

**Real:** model inference (local Ollama); MCP stdio servers (official SDK `mcp==2.2.0`); A2A v1.0 over JSON-RPC between
OS processes (official `a2a-sdk==1.2.2`); SIGKILL and restart; retries; OpenTelemetry traces across processes; token
counts; wall-clock latency on one machine. **Simulated:** checkout-api and every enterprise system; every remediation;
the token service (HMAC tokens, not OAuth); the incident commander's approval. Latency is comparative on one Apple M5 Pro
(24 GB), serial, and does not generalise.
