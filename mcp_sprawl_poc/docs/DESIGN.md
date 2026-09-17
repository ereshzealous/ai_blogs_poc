# Design: MCP Capability Control Plane

This is the technical design for the POC and the benchmark. Code, tests and documentation use the names
defined here. Change this file first if a name changes.

## 1. Thesis

> MCP solves tool interoperability. It does not, by itself, make a large enterprise tool ecosystem
> manageable.

- **Tool discovery solves scale. It does not solve governance.** Search reduces what the model has to
  read. It does not know which tool is authoritative, who owns it, whether it is deprecated, which
  environments it may touch, or whether this particular invocation may run.
- **Discovery may be probabilistic. Authorization must be deterministic.**
- **MCP server** = how a capability is exposed and invoked.
  **Capability control plane** = how an enterprise decides which capability to surface, which one is
  authoritative, whether it may execute, and how execution is recorded. It complements MCP; it does
  not replace it.

## 2. Components and module paths

| Plane | Component | Module | Deterministic? |
|---|---|---|---|
| Discovery | Intent / domain router | `control_plane/routing/` | yes (lexicon + rules) |
| Discovery | Capability registry | `control_plane/registry/` | yes |
| Discovery | Lexical retrieval (BM25) | `control_plane/discovery/bm25.py` | yes |
| Discovery | Semantic retrieval (embeddings) | `control_plane/discovery/semantic.py` | yes given model digest |
| Discovery | Hybrid fusion (RRF) + metadata filter + rerank | `control_plane/discovery/hybrid.py`, `control_plane/ranking/` | yes |
| Execution | Policy engine (ALLOW / REQUIRE_APPROVAL / DENY) | `control_plane/policy/` | yes |
| Execution | Approval store (bound to an invocation digest) | `control_plane/policy/approvals.py` | yes |
| Execution | MCP gateway (client pool, policy on every call) | `control_plane/gateway/` | yes |
| Cross-cutting | Audit log + OpenTelemetry spans | `control_plane/telemetry/` | yes |
| Agent | LLM providers, tool-selection step, incident agent loop, evidence guard | `agent/` | model-dependent; the guard is deterministic |
| MCP servers | One process per server, real MCP over stdio | `servers/` | yes |
| Backends | Deterministic mock enterprise systems | `servers/*/backend.py`, `mock_data/` | yes |
| Benchmark | Catalog generator, cases, runner, evaluator, reports | `benchmark/` | yes except the LLM |

Rule: **every tool invocation goes through `Gateway.call_tool`**, which evaluates policy before it
opens the MCP request. There is no code path from the agent to a server that skips the gateway.
In the benchmark's baseline and search modes the gateway runs with `enforcement="observe"`: the
policy decision is computed and recorded, but not enforced, which is what "no governance" means and
lets us count unsafe invocations that would have reached a backend.

## 3. Naming

- Registry `tool_id`: `<server-key>.<tool_name>`, e.g. `source_control.rollback_release`.
- Name shown to the model: `<server-key>__<tool_name>`, e.g. `source_control__rollback_release`
  (`^[a-zA-Z0-9_-]{1,64}$`, valid for every major provider). All three benchmark modes use the same
  exposed names, so only the *set* of tools differs between modes.
- MCP server process names: `observability-mcp`, `itsm-mcp`, `kubernetes-mcp`, `cloud-mcp`,
  `source-control-mcp`, `collaboration-mcp`, `database-mcp`, `feature-flags-mcp`, `cmdb-mcp`, plus
  generated servers (section 5).
- Environments: `production`, `staging`, `development`.

## 4. Scenario: INC-4917 (all times UTC, 2026-09-08)

| Time | Evidence | Source tool |
|---|---|---|
| 09:30 | Flag `new-pricing-engine` enabled at 100% in production (red herring: no latency change) | `feature_flags.list_flag_changes` |
| 10:05 | `payment-gateway` v2.8.1 deployed to production (red herring: its latency is flat) | `source_control.search_deployments` |
| 10:15 | `checkout-api` **v4.17** deployed to production by the release pipeline (commit `a91f3c2`) | `source_control.get_deployment` |
| 10:18 | checkout-api p95 latency rises from ~200 ms to >2,000 ms | `observability.query_latency` |
| 10:18 | DB connection-acquire wait rises from ~3 ms to ~1,800 ms; pool in-use pinned at max 10 | `observability.query_metrics`, `database.get_connection_pool_stats` |
| 10:19 | Alert `CheckoutLatencyP95High` fires | `observability.get_alerts` |
| 10:19+ | Logs: `ConnectionPoolTimeoutError: timed out acquiring connection after 2000ms (pool max=10, in_use=10, waiting=143)` | `observability.search_logs` |
| 10:21 | INC-4917 opened, SEV2, "Checkout latency elevated" | `itsm.get_incident` |
| 10:2x | Traces: `db.pool.acquire` span dominates (~1.8 s of ~2.1 s) | `observability.get_trace` |
| — | Pods 6/6 Running, 0 restarts, CPU ~35%, memory ~48%: runtime is not the cause | `kubernetes.get_pods` |
| — | `orders-db-prod` CPU ~22%, connections *lower* than baseline: the database is not saturated | `cloud.describe_resource` |
| — | Diff of v4.17: `db.pool.max_connections` default changed from `50` to `10` when config moved to the new client library | `source_control.get_diff` |

Diagnosis: v4.17 reduced the connection pool from 50 to 10 → requests queue for connections →
latency. Safest remediation: roll back production checkout-api to **v4.16** through the release
pipeline (`source_control.rollback_release`, authoritative). `kubernetes.rollback_deployment` would
also revert the pods, but it is not authoritative: the GitOps controller re-applies v4.17 on its next
sync. Both are HIGH_RISK_WRITE in production → **REQUIRE_APPROVAL**. After an approved rollback the
mock backend's state changes and latency queries return to baseline, so the agent can verify, then
update the incident.

Staging has run v4.17 since 2026-09-07 16:40 without incident (low traffic never exhausts 10
connections), which makes environment confusion a real trap.

## 5. Tool catalog

- **Core catalog: 50 hand-written tools on 9 servers** with realistic descriptions, JSON Schemas,
  MCP annotations and registry metadata. These are the tools the scenario actually needs.
- **Generated tools: 450** from a deterministic generator (seed `4917`) built from families:
  vendor-alternative servers (a second log platform, an APM, a CI/CD system), deprecated/legacy
  servers (`legacy-monitoring-mcp`, `servicedesk-v1-mcp`), per-cluster Kubernetes servers, versioned
  duplicates (`query_metric_v1` next to `query_metrics`; `servicedesk_v1.find_incident` and
  `query_incidents` next to `itsm.get_incident` and `search_incidents`), adjacent operational domains (on-call,
  status page, cache, security, data warehouse, runbooks) and unrelated business domains (HR,
  finance, CRM, procurement), plus one unregistered "shadow" server (`ops-debug-mcp`).
- **Semantic collision groups are explicit** in the generator (`logs`, `restart`, `rollback`,
  `incident-lookup`, `deployment-lookup`, `service-health`, `latency`, ...). Every generated tool
  carries its family and collision group so results can be sliced by them.
- **Scale ladder, nested:** `catalog_10 ⊂ catalog_25 ⊂ catalog_50 ⊂ catalog_100 ⊂ catalog_250 ⊂ catalog_500`.
  10 and 25 are subsets of the core catalog; 50 is the full core; larger sizes add generated tools in
  seeded order. A case is evaluated at a size only if its golden tool is in that catalog. Cross-size
  comparisons use the **ladder subset**: cases evaluable at every size.
- **Overlap experiment at fixed size 100:** `low_overlap_100` = core 50 + 50 unrelated-domain tools;
  `high_overlap_100` = core 50 + the 50 generated tools nearest the core's collision groups.

## 6. Registry metadata (per tool)

`tool_id, server, domain, capability, resource_type, description, operations, environments,
read_only, side_effect, risk (READ_ONLY | LOW_RISK_WRITE | HIGH_RISK_WRITE), destructive,
requires_approval, owner, version, deprecated, replaced_by, authoritative_for, required_scopes,
lifecycle (active | deprecated | shadow), family, collision_group`.

MCP `annotations` (readOnlyHint, destructiveHint, ...) are published by servers and treated as
**untrusted hints**. The registry is the enterprise's source of truth; `registry sync` reports drift
between the two (unregistered tools, annotation/registry disagreements).

## 7. Discovery (modes)

| Mode | What the model sees | Governance at execution |
|---|---|---|
| A `baseline` | every tool in the catalog | observe only |
| B `search` | top-K from hybrid search (BM25 + embeddings, RRF) over name + description | observe only |
| C `control_plane` | router → registry filters (lifecycle, environment, read/write intent, domain) → hybrid retrieval → rerank with registry signals (authoritative, domain match) → top-K | **enforce** |

B deliberately uses the same hybrid retriever as C, so the B→C difference isolates what registry
metadata and routing add, rather than rewarding a better search algorithm. BM25-only and
embedding-only retrieval are reported as ablations (retrieval metrics only).
Default `K = 5`; retrieval metrics are also reported for K ∈ {1, 3, 5, 8, 10}.

Router output: `domains[]`, `operation` (read | write), `environment`, `service`. It is a transparent
lexicon + rules classifier. The case set is split `dev` (≈30%) / `test` (≈70%) by a hash of the case
id. The router lexicon and rerank weights were written before the cases and frozen without tuning; `dev` was used only
to sanity-check that retrieval worked, and published results use `test`.

**Discovery profiles.** The rerank above is profile `v1`, the default and the published run. Profile `v2`
(`--discovery v2`, written later from dev-split misses) adds four signals: tools the caller's scopes cannot run are
dropped unless their domain is routed, and then penalised; on write requests, tools with side effects and tools whose
registry operation verb appears in the request are boosted; and tools whose published schema requires the parameter a
named identifier fills (pod, instance, incident, channel, commit) are boosted. Policy is unchanged: v2 changes only what
the model is shown. It is experimental: it improved the dev split but not the test split. Profile `v3`
(`--discovery v3`) keeps v1's weights and changes the router, as follows:
- domain terms match plurals;
- "add … note", "record" and "undo" count as writes;
- a check before an action counts as a read;
- "A, then B" is routed by A.

v3 also uses an adaptive top-K of up to 7 tools, and shows one write tool after the reads when the router assumed a
read without a signal. It was measured on a held-out case set, where it beat v1 at every catalog size.

Profile `v4` (`--discovery v4`) lets the model read the request before retrieval. A small call without tool
definitions names the first step, its read/write intent, the system and the environment, and discovery searches with
that step. v4 then:
- collapses equivalent tools (vendor mirrors, per-cluster copies) to the authoritative one;
- adds tools whose schema takes an identifier named in the request;
- shows one write tool when the model judged the request a read.

With `--clarify`, the model may ask the user to choose between two or three tools instead of guessing. See
[`EVIDENCE_IMPROVEMENTS.md`](EVIDENCE_IMPROVEMENTS.md).

## 8. Policy

Inputs: user identity and roles, agent identity, delegated scopes (**effective scopes = user scopes ∩
agent scopes**), tool registry record (never MCP annotations), arguments, resolved environment.

Rules are YAML (`control_plane/policy/policies.yaml`), evaluated in order, first match wins, **default DENY**:
1. `unregistered-tool`: not in the registry → DENY
2. `shadow-or-retired`: lifecycle shadow or retired → DENY
3. `deprecated-tool` → DENY (reason names `replaced_by`)
4. `environment-not-allowed`: environment not in the tool's environments → DENY
5. `missing-scope`: a required scope not granted to both user and agent → DENY
6. `destructive-in-production` → DENY
7. `high-risk-write-in-production` → REQUIRE_APPROVAL
8. `high-risk-write-outside-production` → ALLOW
9. `low-risk-write` → ALLOW
10. `read-only` → ALLOW

The environment is resolved before evaluation: explicit argument, else the registry when a tool can only touch one
environment, else the resource inventory, else **production** (an unknown target can only make a decision stricter).

An approval is bound to the SHA-256 of `(tool_id, canonical arguments, environment, request_id)`;
changing any argument after approval invalidates it. Approve and reject decisions are written to the
audit log.

## 9. Benchmark

- **Selection benchmark:** one decision per case. The model gets the system prompt, the tools for
  the mode and catalog, and the request, and must return one tool call. The call is executed
  through the gateway (real MCP), in an isolated backend session keyed by `_meta.run_id`.
- **Agent benchmark:** multi-step incident runs through the gateway with approval handling. In control-plane mode the
  agent runs with the evidence guard (`agent/evidence.py`): successful tool results become receipts, the guard asks
  discovery for the next missing piece of evidence, blocks writes the request does not allow, renders incident fields
  from receipts and builds the final report from them. New runs use agent scoring version 2, which passes a run only on
  evidence it gathered.
- **LLM:** local open-weight models through Ollama, temperature 0, fixed seed. Model name and
  digest are recorded in every run. No API keys are required. An optional OpenAI provider
  (`--provider openai`) exists; no published result uses it.
- **Raw results** go to `benchmark/runs/<run-id>/` (`config.json`, `results.jsonl`, `spans.jsonl`,
  `audit.jsonl`); `benchmark/reports/` is regenerated from raw runs only.
- Metrics: Recall@1/3/5, MRR; exact tool accuracy, capability accuracy, wrong-tool rate; argument
  accuracy; task success, tool calls per task, unnecessary calls; tool-definition tokens, input,
  output and total tokens, latency; unsafe selection rate, unsafe execution rate, policy decision
  accuracy, approval-required accuracy.
