# Proof refresh delta

The original publication baseline (`original-publication-baseline.json`, run `2026-09-30-proof-2`) against the proof pack of run `2026-10-04-proof`. 97 metrics; 33 changed. Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json).

| Metric | Previous | New | Change | Reason |
|---|---:|---:|---|---|
| run_id | 2026-09-30-proof-2 | 2026-10-04-proof | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| proof schema | none | pae-proof/v1 | changed | the Production AI Engineering Proof Contract v1, evidence-kit 5.2.0 vendored |
| published pointer | production_agentic_ai_platform/evidence/runs/PUBLISHED | production_agentic_ai_platform/evidence/published.json | changed | evidence/published.json (pae-proof/v1), written only by promote; the plain-text pointer is kept in step |
| experiments | 13 | 14 | changed | the negative control is an experiment of its own (P1-R14) under the contract |
| checks | 125 | 140 | changed | the contract counts proof checks: each harness assertion becomes one check evaluated by evidence_kit.proof from the recorded facts (obs.<check>), plus the negative control's checks (P1-R14); harness assertions are reported separately; 8 new cases from the standardization brief: R2 staging and environment layers, R4 trusted tool, wrong environment and a write through the read path, R5 capabilities for another tool and another operation, R9 one human decision |
| checks passed | 125 | 131 | changed | in-experiment controls (R4 bypass, R8 relevance-only ranking, R10 fresh key per attempt, R12 guard missed) are control checks: the safeguard's invariant breaks as intended, EXPECTED_FAILURE, not PASS |
| checks failed | 0 | 0 | same |  |
| expected failures (controls) | not reported | 9 | changed | control checks: 5 in-experiment controls and 4 of the negative control's checks; a control that broke as intended |
| harness assertions | 125/125 | 133/133 | changed | what run_proof.py itself records; 8 new cases from the standardization brief: R2 staging and environment layers, R4 trusted tool, wrong environment and a write through the read path, R5 capabilities for another tool and another operation, R9 one human decision |
| claims | not mapped | 19 | changed | proof/claims.toml: every material claim mapped to experiments and checks, each verdict tested against the checks |
| unit tests | 12/12 | 13/13 | changed | R5's new case found that the release server did not compare a capability's operation; capability.verify now does (tests/test_units.py::test_capability_operation_must_match_the_call) |
| wall-clock seconds | 34.3 | 34.6 | changed | not a performance claim: varies between runs |
| SIGKILLed processes | 4 | 5 | changed | recomputed from the raw events (processes that started and neither finished nor parked); results.json recorded 4 because R9's tampered-checkpoint kill was never written into its facts |
| replay level | not declared | SEMANTIC | changed | declared under the contract; the published comparison already showed identical checks and ids with volatile values differing |
| replay checks identical | 125/125 | 133/133 | changed | every harness check of the new run replayed identically |
| replay ids identical | 11/11 | 11/11 | same |  |
| negative control: checks failed | 25/125 | 28/133 | changed | the new cases that depend on approval break too (R4: the trusted tool's REQUIRE_APPROVAL, a write through the read path; R9: one human decision); still 0 harness exceptions |
| negative control: harness exceptions | 0 | 0 | same |  |
| MCP | stdio (real subprocesses, official Python SDK) · SDK 2.2.0 | stdio (real subprocesses, official Python SDK) · SDK 2.2.0 | same |  |
| checkpoints | SQLite (WAL) | SQLite (WAL) | same |  |
| models | deterministic recorded providers (RecordedModelA/B tapes), offline | deterministic recorded providers (RecordedModelA/B tapes), offline | same |  |
| tracing | OpenTelemetry SDK -> JSONL exporter 1.45.0 | OpenTelemetry SDK -> JSONL exporter 1.45.0 | same |  |
| source SHA-256 | 9349873fa4fab95e52e913b122498707685c0a3d4e321b4e6a01c824fc82f9f4 | d1206dc11530f4289d6006d76a36c9743ee5991e56cea0f5d8b9c3216111f732 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |

## Facts the articles print

| Fact | Previous | New | Change | Reason |
|---|---:|---:|---|---|
| `count_audit` | 372 | 375 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `env_mcp_sdk` | "2.2.0" | "2.2.0" | same |  |
| `env_opentelemetry_sdk` | "1.45.0" | "1.45.0" | same |  |
| `neg_checks` | 125 | 133 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `neg_checks_failed` | 25 | 28 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `neg_experiments_failed` | 6 | 7 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `neg_experiments_passed` | 7 | 6 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `neg_failed_experiments` | "R1, R2, R3, R9, R10, R11" | "R1, R2, R3, R4, R9, R10, R11" | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `neg_harness_exceptions` | 0 | 0 | same |  |
| `prev_checks_compared` | 125 | 125 | same |  |
| `prev_checks_different` | "R11.agent_same, R7.same_agent" | "none" | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `prev_checks_identical` | 123 | 125 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `prev_ids_identical` | 11 | 11 | same |  |
| `prev_run` | "2026-09-30-proof" | "2026-09-30-proof-2" | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `r10_lookup_rollbacks` | 1 | 1 | same |  |
| `r10_naive_rollbacks` | 2 | 2 | same |  |
| `r10_resend_rollbacks` | 1 | 1 | same |  |
| `r11_after` | "prod-agent-platform@18" | "prod-agent-platform@18" | same |  |
| `r11_before` | "prod-agent-platform@17" | "prod-agent-platform@17" | same |  |
| `r13_questions` | 17 | 17 | same |  |
| `r1_agent_sha_short` | "110215aae880" | "110215aae880" | same |  |
| `r1_approval_id` | "apr-93193a7d73d9" | "apr-93193a7d73d9" | same |  |
| `r1_approver` | "ic.bob" | "ic.bob" | same |  |
| `r1_audit_events` | 27 | 27 | same |  |
| `r1_bundle_version` | "prod-agent-platform@17" | "prod-agent-platform@17" | same |  |
| `r1_cap_ttl_s` | 120 | 120 | same |  |
| `r1_cost_units` | 21 | 21 | same |  |
| `r1_decision_id` | "pd-fee3f803b6ff" | "pd-fee3f803b6ff" | same |  |
| `r1_digest_short` | "d8e6803bc0a91ede" | "d8e6803bc0a91ede" | same |  |
| `r1_eval_passed` | 11 | 11 | same |  |
| `r1_eval_total` | 11 | 11 | same |  |
| `r1_excluded` | 4 | 4 | same |  |
| `r1_exposed` | 10 | 10 | same |  |
| `r1_idempotency_key` | "idem-d8e6803bc0a91ede1db8ce9804c30b4d" | "idem-d8e6803bc0a91ede1db8ce9804c30b4d" | same |  |
| `r1_jti` | "cap-bc044ce57985528b" | "cap-bc044ce57985528b" | same |  |
| `r1_model` | "recorded-model-a" | "recorded-model-a" | same |  |
| `r1_model_calls` | 4 | 4 | same |  |
| `r1_offered` | 7 | 7 | same |  |
| `r1_p95_after` | 200 | 200 | same |  |
| `r1_policy_version` | "prod-actions@42" | "prod-actions@42" | same |  |
| `r1_rollback_id` | "RB-00001" | "RB-00001" | same |  |
| `r1_selected` | 2 | 2 | same |  |
| `r1_slo` | 400 | 400 | same |  |
| `r1_spans` | 39 | 39 | same |  |
| `r1_tool_calls` | 8 | 8 | same |  |
| `r1_trace_id` | "f672f41c56031bb74f39c422ae90bcca" | "a7a74509d35a0d9273bde8a243546df8" | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `r1_workflow_id` | "wf-0b8f8afa01" | "wf-0b8f8afa01" | same |  |
| `r1_workflow_steps` | 11 | 11 | same |  |
| `r2_effective` | 2 | 2 | same |  |
| `r2_user_perms` | 18 | 18 | same |  |
| `r2_user_rollback` | 6 | 6 | same |  |
| `r4_exposed` | 10 | 10 | same |  |
| `r4_offered` | 7 | 7 | same |  |
| `r5_cases` | 10 | 12 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `r5_denied` | 9 | 11 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `r6_cap` | 6 | 6 | same |  |
| `r6_limit` | "max_model_calls" | "max_model_calls" | same |  |
| `r6_max_cost` | 60 | 60 | same |  |
| `r6_max_steps` | 16 | 16 | same |  |
| `r6_max_tool_calls` | 12 | 12 | same |  |
| `r6_model_calls` | 6 | 6 | same |  |
| `r8_excluded` | 4 | 4 | same |  |
| `r8_selected` | 2 | 2 | same |  |
| `r9_processes` | 3 | 3 | same |  |
| `replay_checks_compared` | 125 | 133 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `replay_checks_identical` | 125 | 133 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `replay_ids_compared` | 11 | 11 | same |  |
| `replay_ids_identical` | 11 | 11 | same |  |
| `run_id` | "2026-09-30-proof-2" | "2026-10-04-proof" | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `total_checks` | 125 | 133 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `total_experiments` | 13 | 13 | same |  |
| `total_passed` | 125 | 133 | changed | Phase C: a fresh run of the standardized code, with the brief's 8 missing cases and the release server's operation check that R5's new case exposed; the 125 checks the two runs share are identical (previous-run-comparison.json). |
| `x_chains` | 18 | 18 | same |  |
| `x_prompts` | 56 | 56 | same |  |
