# T5 Run Report: Observability & Governance

*Every observed value of the recorded run, with where it comes from. Generated from the run directory; nothing typed.*

Production AI Engineering · T5 · Run report · Run report · 2026-09-30

## Run

| | |
|---|---|
| run | `observability_governance_poc/runs/2026-09-30-recorded` · preregistration `sha256:08cc152fc873…` |
| scenarios · experiments | 15 scenarios covering 12 experiments, each with a concurrent background execution |
| model | qwen3:8b via Ollama 0.30.11; 30 calls in the scenarios, 20 in the drift probe; median 10.9 s |
| environment | Python 3.12.13 · OpenTelemetry SDK 1.45.0 |
| processes | 62 started (32 agent runtimes), 2 killed with SIGKILL |
| records | 605 application log lines · 573 spans · 399 evidence events · 32 requests to the deployment API |
| checks | 7/7 (`checks.json`) |
| expectations · predictions | 68/68 · 7/7 (missed: none) |
| replay (`2026-09-30-recorded-replay`, model unreachable) | 60 answers from tape, 0 misses, identical: yes; drift identical: yes |
| tests | 31/31 |

## Outcomes per scenario

| Scenario | Recorded outcome | Production changes | Attempts reaching the API | Agent processes | Evidence events (both executions) | L0 | L1 | L2 |
|---|---|---|---|---|---|---|---|---|
| e01-success | MITIGATED | 1 | 1 | 1 | 27 | 10 | 10 | 13 |
| e02-tool-failure | FAILED_NO_EFFECT | 0 | 3 | 1 | 31 | 10 | 10 | 13 |
| e03-policy-denial | DENIED | 0 | 0 | 1 | 20 | 10 | 10 | 13 |
| e04-human-rejection | REJECTED | 0 | 0 | 1 | 22 | 10 | 10 | 13 |
| e05a-crash-awaiting-approval | MITIGATED | 1 | 1 | 2 | 28 | 10 | 10 | 13 |
| e05b-crash-after-dispatch | MITIGATED | 1 | 1 | 2 | 28 | 10 | 10 | 13 |
| e06-duplicate-delivery | MITIGATED | 1 | 2 | 1 | 29 | 10 | 10 | 13 |
| e07-unexpected-capability | DENIED | 0 | 0 | 1 | 21 | 10 | 10 | 13 |
| e08a-policy-v41 | MITIGATED | 1 | 1 | 1 | 26 | 10 | 10 | 13 |
| e08b-policy-v42 | MITIGATED | 1 | 1 | 1 | 27 | 10 | 10 | 13 |
| e09-config-v9 | MITIGATED | 1 | 1 | 1 | 27 | 10 | 10 | 13 |
| e10-restricted-data | MITIGATED | 1 | 1 | 1 | 28 | 10 | 10 | 13 |
| e11-false-success | EFFECT_NOT_OBSERVED | 0 | 1 | 1 | 27 | 9 | 9 | 13 |
| e12a-lost-response | MITIGATED | 1 | 2 | 1 | 29 | 10 | 10 | 13 |
| e12b-lost-response-no-key | MITIGATED | 2 | 2 | 1 | 29 | 10 | 10 | 13 |

Sources: `scenarios/*/result.json`, `truth.json` (the deployment API's revisions and requests), `reconstruction.json`. L0–L2: correct answers of 13.

## Reconstruction by question

Scenarios answered correctly, of 15.

| | Question | L0 · logs | L1 · + traces | L2 · lineage |
|---|---|---|---|---|
| Q1 | What triggered the execution? | 15 | 15 | 15 |
| Q2 | Which principal initiated it, and for whom? | 0 | 0 | 15 |
| Q3 | Which agent and version acted? | 15 | 15 | 15 |
| Q4 | Which model and configuration produced the proposal? | 0 | 0 | 15 |
| Q5 | Which policy and version evaluated it? | 15 | 15 | 15 |
| Q6 | Was approval required? | 15 | 15 | 15 |
| Q7 | Who approved or rejected it? | 15 | 15 | 15 |
| Q8 | Which capability and arguments reached production? | 15 | 15 | 15 |
| Q9 | How many attempts reached the production API? | 15 | 15 | 15 |
| Q10 | Did the side effect occur? | 15 | 15 | 15 |
| Q11 | How many times did production change? | 15 | 15 | 15 |
| Q12 | Was the incident actually mitigated? | 14 | 14 | 15 |
| Q13 | Can the evidence's integrity be verified? | 0 | 0 | 15 |

| Totals | L0 | L1 | L2 |
|---|---|---|---|
| correct | 149/195 | 149/195 | 195/195 |
| wrong · partial · not recorded · ambiguous | 1 · 30 · 15 · 0 | 1 · 30 · 15 · 0 | 0 · 0 · 0 · 0 |
| key joins · timestamp joins (all scenarios) | 60 · 15 | 75 · 0 | 25 · 0 |
| most sources in one scenario | 6 | 6 | 3 |

Source: `reports/comparison.json`. Every answer, its truth and its verdict is in the Lab Console.

## Side effects in the ambiguity scenarios

| | e06 duplicate delivery | e11 false success | e12a lost response | e12b no key |
|---|---|---|---|---|
| requests reaching the API | 2 | 1 | 2 | 2 |
| timeouts · replays · responses dropped | 0 · 1 · 0 | 0 · 0 · 0 | 1 · 1 · 1 | 1 · 0 · 1 |
| revision before → after | 184 → 185 | 184 → 184 | 184 → 185 | 184 → 186 |
| version after | v4.17.2 | v4.18.0 | v4.17.2 | v4.17.2 |
| verified by read-back | yes | no | yes | yes |
| transactions for the key | 1 | 1 | 1 | 0 |
| production changes (truth) | 1 | 0 | 1 | 2 |

e12a: action `act-7b7550b9`, transaction `dtx-886a012833`, timeout after 1,503 ms, execution `exec-106b857f`, 16 evidence events for the execution, 12.6 s from start to completion; the retry followed the timeout by 208 ms. e05b (crash after dispatch): 1 attempt reconciled by lookup, 1 attempt reaching the API, 1 change. e11: the tool claimed `ROLLED_BACK`.

## Governance lineage

| | |
|---|---|
| e03 policy decision · severity | DENY · SEV-3 |
| e07 capability · gateway refusals | `deployment.scale` · 1 |
| e08a policy | v41 `sha256:6ce10d562f22…` · quorum 1 · verify obligation no · 1 approval |
| e08b policy | v42 `sha256:24395a0d4331…` · quorum 2 · verify obligation yes · 2 approvals |
| e01 model and configuration | qwen3:8b `sha256:500a1f067a9f…` · `incident-remediation@17` · `incident-agent-prod@8` · temperature 0 · 576+159 tokens · proposal `deployment.rollback payment-service v4.17.2` |
| e09 model and configuration | qwen3:8b `sha256:500a1f067a9f…` · `incident-remediation@18` · `incident-agent-prod@9` · temperature 0.3 · 575+145 tokens · proposal `deployment.rollback payment-service v4.17.2` |
| e10 restricted data | `payments.customer_transactions` (RESTRICTED) denied |

## Integrity, privacy and telemetry

| | |
|---|---|
| evidence chains and anchors intact | 15/15 · 399 events |
| tamper T1 edit in place | chain ok no · anchor ok yes · detected yes |
| tamper T2 recompute chain | chain ok yes · anchor ok no · detected yes |
| tamper T3 truncate | chain ok yes · anchor ok no · detected yes |
| tamper T4 recompute chain and anchor | chain ok yes · anchor ok yes · detected no |
| files scanned · canary hits · credential hits | 225 · 0 · 0 |
| spans · orphaned by SIGKILL (e05a · e05b) | 573 · 13 (5 · 8) |
| agent metric dumps lost to SIGKILL | 2 |
| head sampling of the 15 target traces: kept at 25% · 10% · 1% | 4 · 1 · 0 |
| metric series | 19 |
| retention (config, illustrative): debug logs · ops telemetry · audit evidence | 7 · 30 · 400 days |

Sources: `reports/tamper.json`, `reports/telemetry.json`, `evidence/evidence-verification.json`, `config/retention.toml`.

## Metrics (processes that exited cleanly, both executions)

| Series | Value |
|---|---|
| `lineage.tool.attempts` result COMMITTED · REPLAYED · TIMEOUT · UNAVAILABLE | 24 · 2 · 2 · 3 |
| `lineage.tool.unknown_outcomes` | 2 |
| `lineage.effects.unverified` | 2 |

Source: `telemetry/metrics.json`. Counts include the concurrent background executions; the two SIGKILLed processes' metrics are missing, which is the point of the telemetry row above.

## Drift probe (D1)

| | rollback | restart | diagnostics | no action |
|---|---|---|---|---|
| config v8 | 7 | 2 | 0 | 1 |
| config v9 | 0 | 4 | 6 | 0 |

8 of 10 incidents changed action; 3 rollback proposals denied by policy; D01: v8 `deployment.rollback`, v9 `pods.restart`. Source: `reports/drift.json`.

## Predictions

| | Prediction | Result | Evidence |
|---|---|---|---|
| P1 | L2 answers all 13 questions correctly in every scenario. | held | L2 below 13/13 in: none |
| P2 | L0 cannot verify evidence integrity (Q13) in any scenario. | held | L0 verified integrity in: none |
| P3 | L0 reports the wrong final outcome (Q12) in e11-false-success. | held | L0 Q12 verdict in e11-false-success: WRONG |
| P4 | L1 (logs + traces) needs fewer heuristic joins than L0 in every scenario. | held | L1 not fewer heuristic joins in: none |
| P5 | L0 cannot say which prompt template or agent configuration produced the proposal (Q4) in any scenario. | held | L0 answered Q4 in: none |
| P6 | The e12b control mutates production twice; e12a mutates it once. | held | mutations e12a=1, e12b=2 |
| P7 | The restricted-data canary appears in no model request, span, log line or evidence event, in any scenario. | held | canary found in: none |

Source: `reports/predictions.json`, checked mechanically against `experiments/preregistration.toml`.

---

**Series.** Foundation: [F1 · MCP Tool Sprawl](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html) · [F2 · Layered Architecture](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html) · [F3 · Headless AI](../../headless_ai/medium/headless-ai-medium.html) · Trust: [T1 · Agent Identity](../../agent_identity/medium/agent-identity-medium.html) · [T2 · Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · [T3 · Human-in-the-Loop](../../human_in_loop/medium/hitl-medium.html) · Previous: AI Control Plane (in progress) · Current: T5 · Observability & Governance · Next: Production Agent Platform (planned). Companions: [Medium edition](../medium/observability-governance-medium.md) · [Technical deep dive](../technical/observability-governance-technical.md) · [Evidence Check](../results/observability-governance-evidence.md). Every measured number is substituted from `observability_governance_poc/runs/2026-09-30-recorded/facts.json`.
