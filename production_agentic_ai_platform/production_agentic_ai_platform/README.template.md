# Production Agentic AI Platform POC

This POC follows one consequential production action through identity, context, model routing, MCP discovery,
deterministic policy, exact human approval, scoped execution authority, durability and causal evidence, and then tries to
break each of those boundaries on purpose.

> **The agent proposes. The platform decides what reaches production.**

It is the proof of concept of the capstone of the *Production AI Engineering* series, **The Agent Is Not the
Architecture** (technical edition: *Production Agentic AI Platform: The Final Reference Architecture*), packaged under the
series' **Production AI Engineering Proof Contract v1** (`{{proof.schema}}`, {{proof.kit}}). Its article id in the
contract is `P1`.

## Proof at a glance

| | |
|---|---|
| Scenario | INC-4917: `checkout-api` in production, p95 {{r1_slo}} ms SLO breached after v4.17; the governed remediation rolls back to v4.16 |
| Published run | `{{run_id}}` ({{run.finished_at}}), named by `evidence/published.json` |
| Runtime mode | deterministic and offline: no model download, no network, no API key |
| MCP | {{env_mcp_transport}}, SDK {{env_mcp_sdk}} |
| State | {{env_checkpoint_store}} checkpoints, action journal and budget ledger |
| Models | recorded providers A and B (tapes); no live model |
| Proof experiments | {{proof.experiments}} (P1-R1 … P1-R14) |
| Proof checks | {{proof.checks}}: {{proof.pass}} pass, {{proof.fail}} fail, {{proof.expected_failure}} expected failure (controls that broke as intended) |
| Claims | {{proof.claims}} in `proof/claims.toml`, each verdict tested against its checks |
| Unit tests | {{unit_tests_passed}}/{{unit_tests}} (implementation tests, counted apart from proof checks) |
| Replay | {{replay.level}}: {{replay_checks_identical}}/{{replay_checks_compared}} harness assertions and {{replay_ids_identical}}/{{replay_ids_compared}} content-derived ids identical on a second run |
| Negative control | approval requirement removed: {{neg_checks_failed}} of {{neg_checks}} harness assertions fail in {{neg_experiments_failed}} experiments; {{neg_harness_exceptions}} harness exceptions |
| Crash injection | real `SIGKILL` of separate runtime processes: {{raw.sigkills}} killed |
| Tracing | OpenTelemetry SDK {{env_opentelemetry_sdk}}; one trace and one hash-chained audit record per action |
| Source | SHA-256 `{{env_source_sha256}}` over {{env_source_files}} files (`uv run python run_proof.py --source-digest`) |
| Proof schema | {{proof.schema}}; verification: `make verify` |

## What this POC proves

In one deterministic vertical slice, with real MCP processes, real SQLite state and real process kills:

- a model's proposal does not authorize anything: the rollback runs only through policy, an approval of its exact digest
  and a capability bound to that digest (P1-R1, P1-R2);
- effective authority is the intersection of user, agent, delegation, workload and environment permissions (P1-R2);
- an approval covers one canonical invocation; a changed, rewritten, replayed or self-granted approval is refused (P1-R3);
- discovery and execution are separate controls (P1-R4); the resource verifies a capability scoped to one call (P1-R5);
- budgets, model fallback and context filtering are runtime controls, not prompts (P1-R6, P1-R7, P1-R8);
- crashes and lost responses do not repeat the human decision or the side effect (P1-R9, P1-R10);
- one control-plane change stops the action without touching the agent, even after approval (P1-R11);
- a guardrail that misses an injection does not grant authority (P1-R12);
- the action can be reconstructed from one causal evidence chain (P1-R13); and the proof fails when a safeguard is removed (P1-R14).

## What it does not prove

- Not a production cloud deployment, not multi-region, not hyperscale: one service, one incident, one tenant pair.
- Not enterprise IAM: the identity provider and workload attestation are YAML and a signed document, not SSO or SPIRE.
- Not a production secret manager: the capability is an illustrative HMAC-signed token with a per-run key.
- Not model quality, and not a benchmark of LLM vendors: the models are recorded tapes.
- Not a production policy language: the engine is deterministic Python over YAML, not OPA or Cedar.
- The enterprise systems (release pipeline, ITSM, metrics, logs) are simulated in SQLite.
- Wall-clock times ({{wall_clock_s}} s for the published run) vary by machine and are not a performance claim.

## What actually runs

<!-- proof:reality -->

## Architecture of the POC

```
 pager (sre.alice) ─▶ request boundary ─▶ durable orchestration ─▶ agent (reasons, proposes; holds no execution capability)
                      identity, delegation   checkpoints, journal      │            ▲
                      effective authority    (SQLite WAL)              ▼            │
                                                 context gateway   model gateway (recorded A/B, fallback, fail closed)
                                                 (predicates in SQL)
                      proposal ─▶ policy (P01–P13) ─▶ approval (digest) ─▶ capability broker ─▶ MCP gateway ─▶ release server (MCP, stdio)
                                  ALLOW / DENY /       ic.bob, HMAC          one call, 120 s        traceparent    verifies the capability
                                  REQUIRE_APPROVAL                                                   in _meta        itself, idempotency key
                      control plane: signed bundle (registry, policy, budgets, models, guardrails), re-read before every decision
                      evidence: OpenTelemetry spans + hash-chained audit + policy, approval and capability records, one trace id
```

## The governed request path (P1-R1)

`request → identity → context → discovery → model → proposal → policy (REQUIRE_APPROVAL) → approval (digest
{{r1_digest_short}}…) → capability ({{r1_cap_ttl_s}} s, `{{r1_jti}}`) → MCP execute → verify (v4.16, p95 {{r1_p95_after}} ms) → memory →
evaluation ({{r1_eval_passed}}/{{r1_eval_total}})`, one trace `{{r1_trace_id}}`, {{r1_audit_events}} audit events.

## Experiments

<!-- proof:experiments -->

## Run it

```bash
cd production_agentic_ai_platform
uv sync                       # Python 3.12, mcp {{env_mcp_sdk}}, OpenTelemetry SDK, pyyaml, pytest
make verify                   # PROOF VERIFICATION of the published run: reads the shipped evidence (fastest)
make test                     # the unit tests
make replay                   # replay the published run into evidence/local/ and classify it against the recorded run
make negative-control         # remove the approval requirement (into evidence/local/): the proof must fail cleanly
make proof RUN_ID=my-run      # a fresh proof into evidence/runs/my-run/: run, replay, negative control, pack, verify
make lab                      # the Proof Lab of the published run: lab/index.html
make package                  # the publication package: dist/, redacted and scanned
```

Every target calls `uv run pap <command>` (`runner/pap_cli/cli.py`). A recorded run is never overwritten, and the
published run changes only through `uv run pap promote <run> --reason … --note …`, which refuses unless the run's pack
is current, its replay is equivalent, its negative control broke cleanly, it verifies, and a proof-refresh delta names it.

## Claim → evidence, one example

<!-- proof:claim-example -->

## Where the evidence lives

```
evidence/published.json                    the published run (the only pointer the documents read)
evidence/runs/<run>/manifest.json          what ran: environment, source digest, execution profile, provenance
evidence/runs/<run>/results.json           every experiment, check, claim and fact (pae-proof/v1)
evidence/runs/<run>/checks.jsonl           one line per check: fact, comparison, expected, actual, status, evidence
evidence/runs/<run>/summary.{json,md}      the scorecard
evidence/runs/<run>/replay.json            the replay comparison (SEMANTIC)
evidence/runs/<run>/negative-control/      results.json (the control's verdict) and raw/ (the mutated run, kept whole)
evidence/runs/<run>/raw/                   what run_proof.py wrote, never edited: results.json, traces, audit, policy,
                                           approvals, capabilities, pytest, experiments/R1 … R13 (world.db, platform.db, …)
evidence/runs/<run>/proof/                 the proof definitions the pack was built with
evidence/runs/<run>/SHA256SUMS             every file above (shasum -a 256 -c, from this folder)
evidence/verification/verification.json   the last PROOF VERIFICATION
evidence/RELOCATION.json                   runs made before this layout, moved byte for byte (every SHA-256 identical)
```

## Published run, replay and negative control

<!-- proof:history -->

**Replay ({{replay.level}}).** A second run of the same code from a fresh start (`replay/raw/`) reproduces every harness
assertion's verdict and observed value ({{replay_checks_identical}}/{{replay_checks_compared}}) and every content-derived identifier
({{replay_ids_identical}}/{{replay_ids_compared}}); trace ids, timestamps, process ids and wall-clock time differ and are listed.

**Negative control (P1-R14).** `negative_control.py` copies this POC, removes the approval requirement (three
configuration lines, `negative-control/raw/mutation.diff`) and runs the same proof. Policy returns ALLOW, the rollback
runs before any human decision, {{neg_checks_failed}} of {{neg_checks}} harness assertions fail as explicit expected-versus-actual
results in {{neg_failed_experiments|p1}}, the proof exits non-zero, and no experiment stops on an exception
({{neg_harness_exceptions}}). The other {{neg_experiments_passed}} experiments do not depend on approval and pass.

## Repository structure

```
run_proof.py  negative_control.py  compare_runs.py     the proof, its negative control, a two-run comparison
src/agentic_platform/                                   runtime, agent, identity, context, models, tools, policy, approval,
                                                        capability, budget, control plane, observability, experiments
src/mcp_servers/  src/simulated_systems/                three MCP servers; the simulated release pipeline, ITSM, metrics, logs
config/  scenarios/inc_4917/                            the control plane (signed per run) and the incident fixture and tapes
tests/                                                  unit tests
proof/                                                  manifest.toml, experiments.toml (generated), claims.toml, hygiene.toml
tools/                                                  proof_facts, proof_pack, replay_compare, verify_evidence, build_readme,
                                                        gen_experiments, package_proof
runner/  Makefile                                       the pap command line (experiment-runner) and the make targets
lab/                                                    the Proof Lab and its builder
vendor/evidence_kit/                                    evidence-kit 5.2.0 (the Proof Contract and its library)
```

## Limitations

The models are recorded tapes; proposal quality and live provider behaviour are not measured. HMAC with a per-run key
stands in for asymmetric signing and a secrets manager. Policy is a deterministic Python engine over YAML. The prompt
injection guard is pattern-based and its miss is simulated. Runtimes re-read a local bundle; fleet propagation is not
tested. The audit chain is tamper-evident, not tamper-proof. One service, one incident: architectural properties, not
scale or latency.
