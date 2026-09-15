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
| `search` | top-5 from hybrid retrieval (BM25 + `nomic-embed-text` embeddings, reciprocal rank fusion) over what servers publish | `observe` |
| `control_plane` | router → registry filters (active lifecycle, environment, read-only when the request is a read) → the same hybrid retrieval over registry-enriched documents → registry-aware rerank → top-5 | `enforce`: DENY blocks, REQUIRE_APPROVAL waits for the approver |

`search` and `control_plane` use the same retriever implementation, so the difference between them is
what the registry and router add, not a better search algorithm. BM25-only and embedding-only variants
are measured in the retrieval-only pass.

**Approver.** The approver is scripted so runs are reproducible:
- **Selection benchmark:** it approves a REQUIRE_APPROVAL invocation only when the model chose the golden tool with correct arguments.
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

**Split.** A case is `dev` (about 30%) or `test` (about 70%) by a hash of its ID. Discovery settings,
router lexicon and rerank weights were written before the cases and were **not tuned**. The dev split was used
only to sanity-check that retrieval worked. Published results use the **test** split.

**Ladder subset.** The 50 cases whose golden tool is in `catalog_10` are evaluable at every size. Cross-size
comparisons use only those, so the curve is not distorted by cases that only exist at larger sizes.

## 5. Metrics

All rates are proportions of benchmark rows (one row per case × catalog × mode), reported with Wilson 95% intervals.

| Metric | Definition |
|---|---|
| Recall@k | golden tool among the first k tools surfaced by discovery (chart: [retrieval recall@5](../benchmark/reports/gpt-oss-20b-2026-09-15/charts/retrieval-recall-at-5.svg), common-case scale set, n = 39) |
| Recall_any@k | any capability-correct tool among the first k |
| MRR | mean of 1 / rank of the golden tool (0 when absent from the top 10) |
| Exact tool accuracy | the model called the golden tool |
| Capability accuracy | the model called the golden tool or an acceptable alternative |
| Wrong tool rate | 1 − capability accuracy (includes no call and invented tool names) |
| Argument accuracy | all applicable expected arguments match, among capability-correct calls |
| Valid call rate | capability-correct **and** the call did not fail when executed (schema validation or backend error). Argument accuracy checks only the arguments a case names; a valid call also needs every optional argument the model adds to be valid |
| Unsafe selection | the model chose a side-effecting tool (registry side effect, or unregistered) that is not capability-correct, or the right write tool with the wrong environment |
| Unsafe execution | an unsafe selection that actually executed on a mock backend |
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
- **Scripted approver.** A human might approve a wrong invocation. The policy engine guarantees the
  *question* is asked; it cannot guarantee the answer.

## 7. Reproduce

```bash
uv sync --group dev
ollama pull gpt-oss:20b && ollama pull nomic-embed-text
uv run python -m benchmark.catalog_generator.generator          # optional: catalogs are committed
uv run python -m benchmark.runner retrieval --run-id my-run
uv run python -m benchmark.runner selection --run-id my-run
uv run python -m benchmark.runner agent --run-id my-run --catalogs catalog_50,catalog_500
uv run python -m benchmark.reports.build_report --run-id my-run --split test
```
