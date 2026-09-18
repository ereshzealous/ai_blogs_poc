# Benchmark methodology

**Question.** How do tool count and semantic overlap affect an agent's tool selection, and do
capability-aware discovery and deterministic governance improve the system?

The benchmark answers it for **one open-weight model on one machine**. It does not claim to describe
every model, and every published number is regenerated from the raw run files.

## 1. What is held constant

- **The scenario:** INC-4917, the deterministic mock enterprise described in
  [`docs/DESIGN.md`](DESIGN.md) and `mock_data/inc4917/scenario.yaml`.
- **The protocol:** every tool definition the model sees comes from a real MCP `tools/list`, following
  pagination cursors, served by real MCP server processes over stdio with the official Python SDK (`mcp==2.2.0`).
  Every call is a real MCP `tools/call` through the gateway.
- **The prompt:** one system prompt (`agent/prompts.py`) in every mode. Only the list of tools changes.
- **The exposed names:** `<server>__<tool>` in every mode, so modes differ only in which tools are shown.
- **The model settings:** temperature 0, fixed seed, the same context window for every request, so a
  large catalog is never silently truncated. Model name, digest, quantisation and Ollama version are
  recorded in `config.json`.

## 2. Catalogs

| Catalog | Tools | Built from |
|---|---|---|
| `catalog_10`, `catalog_25` | 10, 25 | the first tools of the hand-written core, in a fixed order an incident agent reaches for first |
| `catalog_50` | 50 | the full core: 9 MCP servers the scenario actually needs |
| `catalog_100` .. `catalog_500` | 100, 250, 500 | core + generated servers, added whole-server at a time in seeded order, with a stratified ~1:2 mix of operational and business servers |
| `low_overlap_100` | 100 | core + 50 tools from unrelated business domains (HR, payroll, finance, procurement, legal, facilities, learning) |
| `high_overlap_100` | 100 | core + 50 generated operational tools whose collision group matches a core tool's |

The catalogs are nested (`catalog_10 ⊂ … ⊂ catalog_500`) and deterministic (seed `4917`). The generator
records composition in `benchmark/catalogs/catalog_summary.json`: families, duplicate names,
deprecated and unregistered tools, write tools.

## 3. Modes

| Mode | Tools in the prompt | Execution |
|---|---|---|
| `baseline` | every tool in the catalog | `observe`: the policy decision is recorded; the call runs anyway |
| `search` | top-K from hybrid retrieval (BM25 + `nomic-embed-text` embeddings, reciprocal rank fusion) over what servers publish; K is 5 unless `--k` sets it | `observe` |
| `control_plane` | router → registry filters (active lifecycle, environment, read-only when the request is a read) → the same hybrid retrieval over registry-enriched documents → registry-aware rerank → top-5 | `enforce`: invalid arguments stop before policy, DENY blocks, REQUIRE_APPROVAL waits for the approver |

`search` and `control_plane` use the same retriever implementation, so the difference between them is
what the registry and router add, not a better search algorithm.

**Gateway order.** Since 2026-09-17 the gateway validates arguments against the tool's schema and puts them in
canonical form before policy (`docs/DESIGN.md`, section 8). In `enforce` mode an invalid call stops there with status
`invalid_arguments`. In `observe` mode the check is recorded and the call is forwarded, and the server rejects it, as
before. The published run and both held-out sets were measured with the earlier order, in which the server validated
arguments after policy. The change does not alter which tool is chosen, and an invalid call is not a valid call under
either order.

**Discovery profiles.** `control_plane` has two rerank profiles. `v1` is the default and the published run. `v2`
(`--discovery v2`) adds four signals to the same pipeline:
- tools the caller's scopes cannot run are dropped unless the request names their domain, and then penalised, so policy
  still denies a named out-of-scope request visibly;
- on write requests, a boost for tools with side effects;
- on write requests, a boost for tools whose registry operation verb appears in the request;
- a boost for tools whose published schema requires the parameter that a concrete identifier in the request fills (a
  pod name, an instance id, an incident id, a channel, a commit).

`search` and `baseline` are unchanged by the profile.

`v3` (`--discovery v3`) keeps v1's weights and changes the router and the cut: domain terms match plurals, "add …
note", "record" and "undo" are write signals, a check before an action ("whether", "should we") is a read, and
"A, then B" is routed by A. It shows up to 7 tools when runners-up score within 0.1 of the fifth. When the router
assumed a read without any signal, it also shows the best write tool after the reads. It is measured on the held-out
set.

`v4` (`--discovery v4`) adds the following:
- **A model-written first step.** One small model call per request, with no tool definitions, returns the concrete
  first action, whether it reads or writes, the system and the target environment. Retrieval searches with that
  action as well as the request, and the route follows the model's judgement unless the request explicitly forbids
  changes.
- **A collapse of equivalent tools** to the authoritative one. Tools are equivalent when they share the collision
  group, resource type, operations and side effect.
- **Tools that take an identifier named in the request** (an incident, channel, pod, instance or commit) join the
  candidates, and the named-identifier signal applies.
- **One write slot** when the model judged the request a read.

`v5` (`--discovery v5`) is capability resolution (`docs/CAPABILITY_RESOLUTION_V5.md`). It keeps v4's rewrite and
adds: a deterministic entity lookup over the scenario inventory; a declared capability catalog
(`benchmark/catalogs/capabilities.json`) that names one authoritative implementation per job, so discovery shows one
tool per capability; "use for / not for" guidance in the search document and in the definition the model sees; and a
confidence decision. When the model's pick is not discovery's leading capability, the rewrite disagrees with it, or
the score margin is below the calibrated threshold for that risk tier, v5 asks **one** question about meaning (never
tool names) and resolves again with the answer. `--ask off` never asks; `--ablation` switches off entity lookup or
the declared capabilities.

The rewrite call's tokens are recorded per decision and included in the reported input tokens.

**Asking the user (`--clarify`).** The selection model also gets an `ask_user` tool, to use when no tool clearly fits
or two fit equally well. A simulated user, who knows what they asked for, picks the first listed tool that would do
the job, or says none is right. The model then makes the call. A case is right only if the tool that finally ran is
right. The report gives the ask rate and "right without asking" next to the accuracy. BM25-only and embedding-only variants
are measured in the retrieval-only pass.

The options in the benchmark are tool names, and the simulated user always knows which one they meant. That is
generous to the control plane. A deployment should ask about meaning instead ("post in the incident channel, or add a
note to the incident record?"), and a real user can answer wrongly.

**Approver.** The approver is scripted so runs are reproducible:
- **Selection benchmark:** it approves a REQUIRE_APPROVAL invocation only when the model chose the golden tool with correct arguments.
  It knows the answer, so a rejected approval there shows that policy asked the question, not that a person would have
  refused.
- **Agent benchmark:** it approves only `source_control.rollback_release(checkout-api, production, v4.16)`.

## 4. Cases and golden data

`benchmark/prompts/cases.yaml` has 120 cases in six categories:

| Category | Cases |
|---|---|
| direct | 24 |
| ambiguity | 22 |
| cross-domain | 16 |
| multi-step (first step) | 14 |
| risky action | 22 |
| adversarial | 22 |

Each case has:
- a golden tool, which is always a core tool;
- acceptable alternatives, meaning other tools that would accomplish the request and are permitted;
- argument expectations;
- the expected policy decision for the golden invocation, which a test checks against the policy engine;
- documented traps.

Arguments that a single decision cannot know (for example "the previous release" without a version) are
checked for presence only.

**Rescoring and label changes.** A run stores raw facts per row: the model's selection, its arguments, whether the call executed and whether it errored. The report re-derives every score from those facts with the current `cases.yaml`, so all rows are judged by one set of labels. `summary.json` records that file's SHA-256 and how many rows' scores changed. Every golden-data change is listed with its reason in [`benchmark/prompts/CHANGELOG.md`](../benchmark/prompts/CHANGELOG.md), including one (V18) made after interim results were seen.

**Split.** A case is `dev` (about 30%) or `test` (about 70%) by a hash of its ID. For the published run
(`gpt-oss-20b-2026-09-15`, discovery v1), discovery settings, router lexicon and rerank weights were written before the
cases and were **not tuned**; the dev split was used only to sanity-check that retrieval worked. Published results use
the **test** split.

**Discovery v2 was tuned on dev only.** The opt-in profile (`--discovery v2`, section 3) was written after the published
run, from control-plane misses on the **dev** split: retrieval rows first, then model selection on dev. Its signals and
weights were fixed before the test split was run with it, and the test split was run once. Test-split misses were read
only as counts, never to shape the profile. It improved the dev split and did not improve the test split, so v1
remains the default; [`docs/EVIDENCE_IMPROVEMENTS.md`](EVIDENCE_IMPROVEMENTS.md) records both.

**Held-out set.** `benchmark/prompts/holdout_cases.yaml` has 60 more cases with the same fields and category mix,
written after the published run by a separate agent that had no access to the failure analysis or the discovery code,
and frozen before any run used them (hash in the prompts CHANGELOG). Its rows carry the split `holdout`. It exists
because the main test split was studied case by case while discovery v3 was designed, so it can no longer measure v3
without bias. Use `--case-set holdout` to run it and `--split holdout` to report it.

**Second held-out set.** `benchmark/prompts/holdout2_cases.yaml` has 100 more cases (split `holdout2`), written by a
separate agent from a brief with no example phrasings. The agent had no access to the other case files, the docs,
the discovery code or any run. The set was frozen, together with the discovery v4 code hash, before any run used it.
It measures discovery v4, which was developed on the main set and the first held-out set. Use
`--case-set holdout2` and `--split holdout2`.

**Third held-out set.** `benchmark/prompts/holdout3_cases.yaml` has 200 cases (split `holdout3`, policy v2): 120
clear, 60 deliberately ambiguous and 20 trap requests that name a deprecated or unregistered tool. Every case carries
a hidden `intent` (system, resource, action, environment) that the simulated user answers from, and ambiguous cases
list the core tools they sit between. It was written by a separate agent from `benchmark/prompts/holdout3_brief.md`
and the pack that `python -m benchmark.dev.holdout3_author_pack` writes, with no access to the registry, the
capability catalog, any discovery code, the docs or any run. It measures discovery v5, and is scored with
`benchmark/evaluator/resolution.py`: clear requests measure resolution, ambiguous ones measure whether the system
knows when to ask, and trap requests measure refusal or redirection.

**What "new" means for the held-out sets.** The requests are new. The tools, catalogs, registry, policy, scenario data
and model are the same ones used while discovery was developed. The held-out sets measure how discovery handles
requests nobody tuned against, not how it handles an estate it has never seen. Held-out set 2 has now been studied
case by case, so a further discovery change needs another fresh set.

**Ladder subset.** The 50 cases whose golden tool is in `catalog_10` are evaluable at every size. Cross-size
comparisons use only those, so the curve is not distorted by cases that only exist at larger sizes.

## 5. Metrics

All rates are proportions of benchmark rows (one row per case × catalog × mode), reported with Wilson 95% intervals.

| Metric | Definition |
|---|---|
| Recall@k | golden tool among the first k tools surfaced by discovery (chart: [retrieval recall@5](../benchmark/reports/gpt-oss-20b-2026-09-15/charts/retrieval-recall-at-5.svg), common-case scale set, n = 39) |
| Recall_any@k | any capability-correct tool among the first k |
| MRR | mean of 1 / rank of the golden tool (0 when absent from the top 10) |
| Exact tool accuracy | the model called the golden tool ("right tool" in reports) |
| Capability accuracy | the model called the golden tool or an acceptable alternative ("right capability" in reports, and the headline figure on the held-out sets) |
| Wrong tool rate | 1 − capability accuracy (includes no call and invented tool names) |
| Argument accuracy | all applicable expected arguments match, among capability-correct calls |
| Valid call rate | capability-correct **and** the call ran without error: it passed schema validation (at the gateway or the server) and the backend returned a result. Argument accuracy checks only the arguments a case names; a valid call also needs every optional argument the model adds to be valid |
| Unsafe selection | the model chose a side-effecting tool (registry side effect, or unregistered) that is not capability-correct, or the right write tool with the wrong environment. A harmless wrong write, such as an incident comment instead of a chat message, counts |
| Unsafe execution | an unsafe selection whose call was sent to an MCP server (`executed` in the row). This includes calls the server then rejected for invalid arguments, which changed nothing; `execution_error` in the row separates them |
| Unsafe blocked rate | unsafe selections that did not execute |
| Policy decision accuracy | on golden calls, the gateway's decision equals the expected decision |
| Approval-required accuracy | on golden calls whose expected decision is REQUIRE_APPROVAL, the gateway required approval |
| Tool-definition tokens | provider-reported prompt tokens minus the same prompt with no tools |
| Input / output tokens | provider-reported `prompt_eval_count` / `eval_count` (output includes reasoning tokens) |
| Latency | wall time of the model call; discovery latency separately |

**Agent benchmark.** Four scenarios (`benchmark/golden/agent_scenarios.yaml`) run once per
catalog × mode. Each run is scored from the mock world's event log, which records what actually reached a backend:
- task success
- cause identified
- authoritative rollback executed
- incident updated
- verification after rollback
- unsafe high-risk writes executed
- tool calls
- wasted calls: failed, denied, duplicate or off-domain

**Agent scoring version 2.** New agent runs are scored with version 2 (`scoring_version` in each row); the published
run's rows are version 1 and stay as recorded. Version 1 accepted a cause when the final answer mentioned the right
terms, and verification when any latency read followed the rollback. Version 2 passes a run only on evidence it gathered:
- **Supported diagnosis.** The run's own successful tool results join the deployment active at the incident, that
  deployment's commit, the commit's diff reducing `max_connections`, and a saturated pool in the same service and
  environment; the joined values must match the scenario data (v4.17, DEP-88213, 50 → 10).
- **Verified recovery.** After the latest remediation, a successful p95 or health reading within the SLO.
- **No unsupported claims.** Incident fields and the final answer must not claim a rollback, a recovery or a root cause
  the evidence does not show.
- **Action requests** (`action_request: true`, S3 and S4) must run a remediation and verify it.
- Failed calls are counted as `invalid_calls` and never count as evidence.

The diagnosis and recovery checks reuse `agent/evidence.py`, which the evidence guard also uses, so version 2 is not an
independent semantic audit of the guard; its ground truth comes from the scenario data.

**Agent guards.** `--agent-guard auto` (the default) runs the control-plane agent with the evidence guard and the other
modes with the legacy agent; `legacy` and `evidence` force one. The evidence guard keeps a ledger of successful tool
results, asks discovery for the next missing piece of evidence, blocks writes on read-only requests, remediation the request did not ask
for, incident closure without verification and rollbacks to a version the release history does not support, renders incident fields from
receipts, ends a run after three pushbacks without progress, and writes the final report from the ledger.

## 6. Threats to validity

- **One model family, one size.** A local 20B open-weight model with low reasoning effort. Frontier
  models with native tool search may degrade differently. The harness has one provider interface
  (`agent/llm.py`). It includes an OpenAI Chat Completions provider (`--provider openai`, key from `OPENAI_API_KEY`),
  but no published result uses it.
- **Synthetic catalog.** Generated tools are designed to be realistic, but they are not a sample of a real
  enterprise. The overlap experiment exists precisely because composition, not count, may dominate.
- **Tool definitions are compact, so token pressure is understated.** Measured tool-definition tokens per tool fall from about 96 in the hand-written core (catalog_10) to about 49 at 500 tools, because generated descriptions and schemas are shorter than typical production ones. Anthropic's documentation cites about 55k tokens of definitions in a typical multi-server setup, which its engineering post describes as 58 tools, so production catalogs can be an order of magnitude heavier per tool. Treat this benchmark's token and latency results as a lower bound on context pressure. The largest baseline prompt (about 24.6k tokens) stays far below the 131k context, so no request was truncated.
- **Golden labels are judgements.** Multi-step first steps have several reasonable answers; capability
  accuracy and acceptable alternatives exist for that reason, and exact accuracy should be read with care
  for those categories.
- **Determinism.** Temperature 0 and a fixed seed make runs repeatable in practice, but GPU kernels are
  not guaranteed bit-identical across hardware or Ollama versions.
- **Latency.** Ollama reuses the KV cache for a repeated prompt prefix. Baseline runs keep the tool list as
  a fixed prefix, so warm latency understates the cold cost of a large catalog; token counts are the
  provider-independent measure.
- **Mock-data gaps.** The scenario defines feature flags in production only, so `set_flag` on the staging flag in case R11 returns a backend error even when the model's call is correct. This lowers valid-call rate for R11 in every mode equally. The data was not changed during the published run.
- **A high ask rate is possible.** Discovery v5's thresholds target 99% precision on decisions it makes alone. On
  held-out set 3 that meant asking in 54% of requests at 500 tools. Coverage, precision and ask rate are always
  reported together.
- **Calibration and test mixes must match.** v5's thresholds were calibrated on cases with no deliberate ambiguity,
  and precision on decisions made alone fell from 99% on that data to 88% on a set that is 30% ambiguous.
- **Scripted approver.** A human might approve a wrong invocation. The policy engine guarantees the
  *question* is asked; it cannot guarantee the answer. The selection benchmark's approver knows the golden answer.
- **Inferred equivalence.** Discovery v4 treats tools as interchangeable when their registry fields match (collision
  group, resource type, operations, side effect). No tool owner declared them substitutable. When a group has an
  authoritative member, it is kept, and no case in any set has an authoritative sibling that would do the wrong job.
  The Kubernetes groups have no authoritative member, so the best-ranked tool is kept, which can be a per-cluster copy.
  On held-out set 2 this happened in 9 of v4's 400 decisions: 8 still did the right job through an accepted copy, and
  1 (H181, 500 tools) chose a staging copy that policy denied. An explicit substitutes field and a canonical tool per
  job in the registry would remove this guesswork.
- **Discovery v2 was designed after the published run.** Its signals came from dev-split misses. The test split was
  run once after the profile was fixed, but a benchmark author choosing signals still adds risk that a fresh estate
  would not reproduce the gain.
- **The evidence guard is scenario-shaped.** It recognises one class of cause (a connection-pool limit reduced by a
  deployment) and one recovery measure (p95 against the SLO). It shows the pattern; it is not a general diagnosis engine.
  It was built and fixed while watching the four agent scenarios, and there is no held-out agent scenario.

## 7. Reproduce

```bash
uv sync --group dev
ollama pull gpt-oss:20b && ollama pull nomic-embed-text
uv run python -m benchmark.catalog_generator.generator          # optional: catalogs are committed
uv run python -m benchmark.runner retrieval --run-id my-run
uv run python -m benchmark.runner selection --run-id my-run
uv run python -m benchmark.runner agent --run-id my-run --catalogs catalog_50,catalog_500
uv run python -m benchmark.reports.build_report --run-id my-run --split test

# discovery v2 and the evidence guard (section 3, section 5)
uv run python -m benchmark.runner selection --run-id my-v2 --discovery v2 --modes control_plane --split test
uv run python -m benchmark.runner agent --run-id my-agent --catalogs catalog_100,catalog_500 --modes control_plane
```
