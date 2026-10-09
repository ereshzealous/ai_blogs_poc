# C1 POC · One agent, a workflow with agents, or multiple agents over A2A?

*Production AI Engineering · Coordination track · C1.* The POC behind
[*Do You Actually Need Multiple Agents?*](../medium/multi-agent-a2a-medium.html) ·
[technical edition](../technical/multi-agent-a2a-technical.html).

**Question.** On the same headless capability, the same model, tools, policy and budget, does splitting one reasoning
component into several autonomous ones produce a better production system? And what does an A2A boundary cost on its
own?

## Results (blind set, recorded run `{{run.id}}`)

Eight blind incidents × three architectures × three repeats = {{e1.runs}} runs, local `gpt-oss:20b`, strictly serial.

| | A · One agent | B · Workflow + selective agents | C · Multi-agent over A2A |
|---|---|---|---|
| task success (of {{e1.A.n}}) | **{{e1.A.success}}** ({{e1.A.success_ci}}) | **{{e1.B.success}}** ({{e1.B.success_ci}}) | **{{e1.C.success}}** ({{e1.C.success_ci}}) |
| · simple incidents (of {{e1.A.simple.n}}) | {{e1.A.simple.success}} | {{e1.B.simple.success}} | {{e1.C.simple.success}} |
| · complex incidents (of {{e1.A.complex.n}}) | {{e1.A.complex.success}} | {{e1.B.complex.success}} | {{e1.C.complex.success}} |
| median latency | {{e1.A.latency_median_s}} s | {{e1.B.latency_median_s}} s | {{e1.C.latency_median_s}} s |
| median tokens | {{e1.A.tokens_total_median}} | {{e1.B.tokens_total_median}} | {{e1.C.tokens_total_median}} |
| median model calls | {{e1.A.llm_calls_median}} | {{e1.B.llm_calls_median}} | {{e1.C.llm_calls_median}} |
| median tool calls | {{e1.A.tool_calls_median}} | {{e1.B.tool_calls_median}} | {{e1.C.tool_calls_median}} |
| median duplicate tool calls | {{e1.A.duplicate_tool_calls_median}} | {{e1.B.duplicate_tool_calls_median}} | {{e1.C.duplicate_tool_calls_median}} |
| median handoffs | {{e1.A.handoffs_median}} | {{e1.B.handoffs_median}} | {{e1.C.handoffs_median}} |
| state conflicts (claims the ledger contradicts) | {{e1.A.state_conflicts}} | {{e1.B.state_conflicts}} | {{e1.C.state_conflicts}} |
| prohibited actions requested | {{e1.A.prohibited_attempts}} | {{e1.B.prohibited_attempts}} | {{e1.C.prohibited_attempts}} |

Preregistered hypotheses: H1 {{H1}} · H2 {{H2}} · H3 {{H3}} · H4 {{H4}} · H5 {{H5}} · H6 {{H6}} · H7 {{H7}} · H8 {{H8}} · H9 {{H9}}
(definitions in [`experiments/preregistration.toml`](experiments/preregistration.toml)).

Per incident: B had more successes than C on {{inc.B_gt_C}} of {{e1.incidents}} incidents, fewer on {{inc.C_gt_B}}, the
same on {{inc.B_eq_C}}; C used more tokens than B on {{inc.C_tokens_gt_B}} and more time on {{inc.C_latency_gt_B}}. The Wilson intervals above are
over runs; the three repeats of an incident share its fixture and are not independent incident samples.

A2A boundary on its own (E7, scripted model, same agent code, loopback HTTP on one machine, no TLS):
{{e7.inproc.median_ms}} ms in-process vs {{e7.a2a.median_ms}} ms over A2A per delegation (median).

Post-run fix (DEVIATIONS D3): the blind run found a fail-open fallback in C's execute delegations (an authorized
execution without a proposal got every eligible write scope, {{c.execute_all_writes}} of {{c.execute_delegations}});
the post-run correction changed it to fail closed. Published numbers come from the code as it ran
(`experiments/as-run/`, still matching `FROZEN.sha256`); `coord.freeze check` lists the two changed files.

Replay: all {{replay.workflows}} blind workflows re-executed from the model tape, with no model: **{{replay.verdict}}**.

No number in this README is typed by hand: each is substituted from `runs/{{run.id}}/facts.json`, which
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
