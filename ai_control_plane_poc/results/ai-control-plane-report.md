# T4 Run Report: AI Control Plane

*Every observed value, every assertion and every recorded step of the published run, generated from the run directory.*

Production AI Engineering · T4 · Run report · Run report · 2026-10-03

## Run

| Field | Value |
|---|---|
| Run | `2026-10-03-recorded` |
| Python | 3.12.13 |
| Agents | fixed deterministic plans; no LLM |
| Agent code sha256 | `677bca2acd667671b4677ac380745c7925a124e478e69a0e2af107b42323200c` |
| Scenarios | 15 across 12 proofs |
| Scenario assertions | 100 of 100 passed |
| Proof checks (pae-proof/v1) | 79: 73 pass, 2 fail (LIMITATION OBSERVED), 4 expected failure (negative control) |
| Hash chains verified | 28 |
| Ledger rows | 653 (every recorded event, `evidence/runs/2026-10-03-recorded/ledger.jsonl`) |
| Real | separate long-lived runtime processes (subprocess, JSON lines); control-plane versioning, signing (HMAC-SHA256), pointer, rollout; change authorization, validation, hash-chained change log; decision function and enforcement points; hash-chained runtime audit; code hashing of agent sources; file-based state shared between processes |
| Simulated | enterprise systems (deploy, billing, support, observability) and their MCP servers; model endpoints (deterministic text, token counts); network partition, lagging replica and in-transit tampering (flags in state/network/); credential broker (in-process minting); logical clock (ticks) |

Three counts, never merged: *scenario assertions* are the checks each scenario makes on its own record; *proof checks* are the pae-proof/v1 comparisons over facts (`proof/experiments.toml`); unit tests are counted by `make test`.

### Frozen configuration

| File | sha256 |
|---|---|
| `config/admins.yaml` | `d50ac188b5e93ba1…` |
| `config/changes.yaml` | `c361eea5eea4b33f…` |
| `config/desired-state.yaml` | `fefd01cba34f58e4…` |
| `config/embedded-changes.yaml` | `af9f2ccd574f84e8…` |
| `config/signing.key` | `23212547394f7b71…` |

## P2 · before → after

The core proof, with the three things it holds fixed. P2 fails if any of them changes (`control_plane_poc/tests/test_cheating.py`).

|  | Before | After |
|---|---|---|
| Agent source sha256 | `677bca2acd66` | `677bca2acd66` |
| Runtime process | `rt-a/pid-1` | `rt-a/pid-1` |
| Request hash | `cb0531217710` | `cb0531217710` |
| Control plane version | `v1` | `v2` |
| Decision | ALLOW | APPROVAL_REQUIRED |
| Deploy system: restarts | 1 | 1 |
| Agent edits · redeploys |  | 0 · 0 |

## Scenarios

| Group | Scenario | Outcome | Assertions | Observed |
|---|---|---|---|---|
| CORE | `P1-C-baseline` | HELD | 6/6 | executed under v1; restarts=1 |
| CORE | `P2-C-central-change` | HELD | 9/9 | v1 executed → v2 pending_approval; restarts=1 |
| CAPABILITY | `P3-C-approval` | HELD | 9/9 | before approval 0; after 1; duplicate resume ALREADY_EXECUTED |
| CAPABILITY | `P4-C-suspend` | HELD | 8/8 | 0 of 2 in-flight calls executed after suspension; new run AGENT_SUSPENDED |
| CAPABILITY | `P5-C-budgets` | HELD | 7/7 | call 3 TOOL_CALL_BUDGET_EXCEEDED; run-003 DAILY_BUDGET_EXHAUSTED |
| CAPABILITY | `P6-C-revoke-mcp` | HELD | 7/7 | 0 observability calls after revoke; 3 calls denied |
| CAPABILITY | `P7-C-models` | HELD | 7/7 | fast-model → large-model; confidential under v3: DENIED NO_ALLOWED_MODEL_FOR_DATA_CLASS |
| CAPABILITY | `P8-C-canary` | HELD | 6/6 | canary 4/20; rollback 0/20; promoted 10/10 |
| BOUNDARIES | `P9-C-outage` | QUALIFIED | 6/6 | mutation CONTROL_PLANE_UNREACHABLE; 3 calls ran after the suspension was published |
| BOUNDARIES | `P9-C-tampered-bundle` | HELD | 3/3 | 5 rejections; applied v1 |
| BOUNDARIES | `P9-C-broker-down` | HELD | 3/3 | all tool calls denied CREDENTIAL_UNAVAILABLE |
| BOUNDARIES | `P10-C-drift` | QUALIFIED | 7/7 | 2 drift findings; 1 mutation under a superseded version |
| NEGATIVE CONTROL | `P11-E-embedded` | BROKEN — expected negative control | 4/4 | 7 edits, 7 redeploys; old process still restarted |
| NEGATIVE CONTROL | `P11-C-control-plane` | HELD | 5/5 | 4 versions; 0 edits; 0 redeploys |
| GOVERN THE GOVERNOR | `P12-C-governing-the-control-plane` | HELD | 13/13 | 3 accepted, 7 rejected, all 11 on a verifying chain |

### P1-C-baseline

*CORE · under v1 the protected action is allowed, executed once and attributed to v1*

**Question.** Under v1, does the incident agent's production restart run, and is it attributed to v1?

**Expected.** ALLOW, executed once, attributed to v1  
**Observed.** executed under v1; restarts=1  
**Outcome.** HELD

**Step ledger** (9 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 6c3980d85a57 |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.applied |  |  |  | d481f9e5b6d2 |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 05a8e36204d2 |
| 5 · t11 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 8e37890d977c |
| 6 · t12 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 777b1356bc92 |
| 7 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0982 | model gateway fast-model · 491 tokens | db644edeed8a |
| 8 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.restart_service[1] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | 0642969a757e |
| 9 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0982 |  | 1424e2cbb21c |

**Measures**

| Measure | Value |
|---|---|
| config_version | `v1` |
| decision | `ALLOW` |
| restarts | `1` |
| rule | `agents.incident-agent.tools.restart_service[1]` |

**Assertions** (6/6)

| Assertion | Result |
|---|---|
| restart_service decided under v1 | pass |
| restart_service executed (decision allow) | pass |
| deploy system of record shows exactly 1 restart | pass |
| audit event names the config version and the rule | pass |
| the system saw a short-lived, tool-scoped credential, not a static secret | pass |
| agent code unchanged, one runtime process | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P1 — BASELINE: THE CONTROL PLANE ALLOWS                                        │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              incident-agent                                              │
│ Agent code         sha256 677bca2acd66…                                        │
│ Request            restart_service payment-service production                  │
│ Policy version     v1                                                          │
│ Rule               agents.incident-agent.tools.restart_service[1]              │
│ Decision           ALLOW                                                       │
│ Executed           YES · 1 restart in the deploy system                        │
│ Credential         minted for restart_service only, 5-tick TTL                 │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ restart_service decided under v1
  ✓ restart_service executed (decision allow)
  ✓ deploy system of record shows exactly 1 restart
  ✓ audit event names the config version and the rule
  ✓ the system saw a short-lived, tool-scoped credential, not a static secret
  ✓ agent code unchanged, one runtime process

  PROOF P1: PASS
  Test assertions: 6/6 passed
```

### P2-C-central-change

*CORE · behaviour changes centrally with agent code, runtime process and request held fixed*

**Question.** Change only the control plane. Does the same process, with the same code and request, now stop for approval?

**Expected.** same process, same code, same request: v1 executes, v2 holds for approval  
**Observed.** v1 executed → v2 pending_approval; restarts=1  
**Outcome.** HELD

**Step ledger** (18 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 6c3980d85a57 |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.applied |  |  |  | d481f9e5b6d2 |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 05a8e36204d2 |
| 5 · t11 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 8e37890d977c |
| 6 · t12 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 777b1356bc92 |
| 7 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0982 | model gateway fast-model · 491 tokens | db644edeed8a |
| 8 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.restart_service[1] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | 0642969a757e |
| 9 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0982 |  | 1424e2cbb21c |
| 10 · t20 | control plane |  | v2 | change.published restart-requires-approval | PUBLISHED |  |  | 47e044be3e2c |
| 11 · t30 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 7a977da5750b |
| 12 · t30 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v2 | config.applied |  |  |  | 85b99c8a5c9e |
| 13 · t30 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 9a0d6dc1ee91 |
| 14 · t31 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 0069b4ad7bc2 |
| 15 · t32 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 7af844eac71f |
| 16 · t33 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0982 | model gateway fast-model · 491 tokens | e629babd3ff0 |
| 17 · t34 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.tools.restart_service[1] | approval.requested · restart_service | APPROVAL_REQUIRED · POLICY_APPROVAL_REQUIRED | approval-001 | no call reached a system | c18bf7ebf551 |
| 18 · t34 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0982 |  | 522696c72fc1 |

**Measures**

| Measure | Value |
|---|---|
| before_version | `v1` |
| before_decision | `ALLOW` |
| before_executed | `yes` |
| after_version | `v2` |
| after_decision | `APPROVAL_REQUIRED` |
| after_executed | `no` |
| approval_id | `approval-001` |
| acp_files_changed | `0` |
| control_plane_files_changed | `4` |
| restarts | `1` |
| agent_code_sha256 | `677bca2acd66` |
| agent_sha_before | `677bca2acd66` |
| agent_sha_after | `677bca2acd66` |
| runtime_pid_before | `rt-a/pid-1` |
| runtime_pid_after | `rt-a/pid-1` |
| request_hash_before | `cb0531217710` |
| request_hash_after | `cb0531217710` |
| restarts_after_v1 | `1` |
| restarts_after_v2 | `1` |
| side_effect_delta | `0` |
| agent_edits | `0` |
| redeploys | `0` |

**Assertions** (9/9)

| Assertion | Result |
|---|---|
| same request: request hash cb0531217710 before and after | pass |
| same runtime process: rt-a/pid-1 answered both requests, never restarted | pass |
| same agent code: sha256 677bca2acd66 before, at import and after | pass |
| files changed under acp/ by the policy change: 0 | pass |
| control plane store changed (new bundle, signature, pointer, changelog) | pass |
| before: v1 ALLOW, executed | pass |
| after: v2 APPROVAL_REQUIRED, not executed | pass |
| deploy system still shows 1 restart (the side effect did not happen) | pass |
| approval request emitted and pending | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P2 — CENTRAL POLICY CHANGE                                                     │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              incident-agent                                              │
│ Agent code         sha256 677bca2acd66…  UNCHANGED                             │
│ Runtime process    started once · SAME process for both requests               │
│ Request            restart_service payment-service production (identical)      │
│ Before             v1 → ALLOW → executed                                       │
│ Central change     v2 · restart-requires-approval · platform.admin             │
│ After              v2 → APPROVAL_REQUIRED → NOT executed                       │
│ Approval           approval-001 (pending)                                      │
│ Files changed      acp/: 0 · control plane store: 4                            │
│ BEFORE → AFTER                                                                 │
│   agent SHA        677bca2acd66 → 677bca2acd66  (same)                         │
│   runtime PID      rt-a/pid-1 → rt-a/pid-1  (same process)                     │
│   request hash     cb0531217710 → cb0531217710  (same)                         │
│   control plane    v1 → v2                                                     │
│   decision         ALLOW → APPROVAL_REQUIRED                                   │
│   restarts         1 → 1  (no new side effect)                                 │
│   agent edits      0 · redeploys 0                                             │
│ Audit              action.executed (v1) → approval.requested (v2)              │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ same request: request hash cb0531217710 before and after
  ✓ same runtime process: rt-a/pid-1 answered both requests, never restarted
  ✓ same agent code: sha256 677bca2acd66 before, at import and after
  ✓ files changed under acp/ by the policy change: 0
  ✓ control plane store changed (new bundle, signature, pointer, changelog)
  ✓ before: v1 ALLOW, executed
  ✓ after: v2 APPROVAL_REQUIRED, not executed
  ✓ deploy system still shows 1 restart (the side effect did not happen)
  ✓ approval request emitted and pending

  PROOF P2: PASS
  Test assertions: 9/9 passed
```

### P3-C-approval

*CAPABILITY · a held action stays unexecuted until an eligible approver approves, then runs exactly once*

**Question.** Does the held action stay unexecuted until an eligible human approves, and then run exactly once?

**Expected.** 0 restarts until ic.dev approves; then exactly 1  
**Observed.** before approval 0; after 1; duplicate resume ALREADY_EXECUTED  
**Outcome.** HELD

**Step ledger** (13 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t5 | control plane |  | v2 | change.published restart-requires-approval | PUBLISHED |  |  | 01f93e2d06fc |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 6c3980d85a57 |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v2 | config.applied |  |  |  | a9dab0e7ea81 |
| 5 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | ef412081d7f3 |
| 6 · t11 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | d7a47623e5cc |
| 7 · t12 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 9fa17f926671 |
| 8 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0982 | model gateway fast-model · 491 tokens | 9fbbb56c0eb9 |
| 9 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.tools.restart_service[1] | approval.requested · restart_service | APPROVAL_REQUIRED · POLICY_APPROVAL_REQUIRED | approval-001 | no call reached a system | 40a30c29e525 |
| 10 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0982 |  | d64a8649dbd1 |
| 11 · t16 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 | resume.refused | APPROVAL_PENDING | approval-001 |  | 427a4ec9ea7f |
| 12 · t22 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.tools.restart_service[1] | action.executed · restart_service | APPROVAL_REQUIRED · POLICY_APPROVAL_REQUIRED | approval-001 | deploy-mcp restart_service → 200 | 691c9950cb33 |
| 13 · t24 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 | resume.refused | ALREADY_EXECUTED | approval-001 |  | ec9d0278532a |

**Measures**

| Measure | Value |
|---|---|
| approval_id | `approval-001` |
| restarts_before_approval | `0` |
| refused_approvers | `2` |
| approved_by | `ic.dev` |
| restarts_after | `1` |
| duplicate_resume | `ALREADY_EXECUTED` |

**Assertions** (9/9)

| Assertion | Result |
|---|---|
| held action not executed before approval (resume refused, 0 restarts) | pass |
| the agent cannot approve its own action | pass |
| an ineligible principal cannot approve | pass |
| the eligible incident commander's approval is accepted | pass |
| resume after approval executes under the current policy | pass |
| a second resume does not execute again (ALREADY_EXECUTED) | pass |
| deploy system shows exactly 1 restart | pass |
| the executed event carries the approval id | pass |
| agent code unchanged, one runtime process | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P3 — APPROVAL, THEN EXACTLY ONE EXECUTION                                      │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              incident-agent                                              │
│ Policy version     v2 (restart requires approval)                              │
│ Held action        approval-001 · restart_service payment-service production   │
│ Before approval    resume → APPROVAL_PENDING · restarts 0                      │
│ incident-agent     approve → an agent cannot approve its own action            │
│ support.lead       approve → support.lead is not an eligible approver for      │
│                    restart_service                                             │
│ ic.dev             approve → approved                                          │
│ Resume             APPROVED_AND_EXECUTED · restarts 1                          │
│ Resume again       ALREADY_EXECUTED · restarts still 1                         │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ held action not executed before approval (resume refused, 0 restarts)
  ✓ the agent cannot approve its own action
  ✓ an ineligible principal cannot approve
  ✓ the eligible incident commander's approval is accepted
  ✓ resume after approval executes under the current policy
  ✓ a second resume does not execute again (ALREADY_EXECUTED)
  ✓ deploy system shows exactly 1 restart
  ✓ the executed event carries the approval id
  ✓ agent code unchanged, one runtime process

  PROOF P3: PASS
  Test assertions: 9/9 passed
```

### P4-C-suspend

*CAPABILITY · a central suspension stops new and in-flight runs of one agent, and only that agent*

**Question.** Does a central suspension stop new runs and a run already in flight, and only that agent?

**Expected.** every later call of the in-flight run denied; new runs denied; other agents untouched; restore needs two people  
**Observed.** 0 of 2 in-flight calls executed after suspension; new run AGENT_SUSPENDED  
**Outcome.** HELD

**Step ledger** (29 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 6c3980d85a57 |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.applied |  |  |  | d481f9e5b6d2 |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 05a8e36204d2 |
| 5 · t11 | control plane |  | v2 | change.published suspend-incident-agent | PUBLISHED |  |  | 58bb72a4b931 |
| 6 · t11 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 8e37890d977c |
| 7 · t12 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v2 | config.applied |  |  |  | 557b95e33c87 |
| 8 · t12 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.status | action.denied · query_metrics | DENY · AGENT_SUSPENDED |  | no call reached a system | f494236ff60e |
| 9 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.status | model.denied | DENY · AGENT_SUSPENDED |  | no call reached a model | 7556b165302a |
| 10 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0 |  | 11a092df86f5 |
| 11 · t20 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 737adf991bb5 |
| 12 · t20 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.status | run.decision | DENY · AGENT_SUSPENDED |  |  | 29e87ce88139 |
| 13 · t30 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 |  | run.requested |  |  |  | 7ca491717e66 |
| 14 · t30 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v2 · agents.support-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 9498cf523f01 |
| 15 · t31 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v2 · agents.support-agent.tools.read_case | tool.executed · read_case | ALLOW · POLICY_ALLOW |  | support-mcp read_case → 200 | 9796435432a0 |
| 16 · t32 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v2 · agents.support-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 2a2f51b37429 |
| 17 · t33 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v2 · models.profiles.standard.confidential | model.called · private-model | ALLOW · MODEL_RESOLVED | $0.3552 | model gateway private-model · 444 tokens | 2668bec2a1fe |
| 18 · t34 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v2 · agents.support-agent.tools.refund_customer[0] | action.executed · refund_customer | ALLOW · POLICY_ALLOW |  | billing-mcp refund_customer → 200 | 15318b7bf324 |
| 19 · t34 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 |  | run.finished |  | $0.3552 |  | 30b783e50db1 |
| 20 · t40 | control plane |  |  | change.rejected restore-incident-agent | REJECTED · a widening change needs a second approver |  |  | 5531db673501 |
| 21 · t41 | control plane |  | v3 | change.published restore-incident-agent | PUBLISHED |  |  | 6246203928ce |
| 22 · t50 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.requested |  |  |  | c53656d327ff |
| 23 · t50 | runtime rt-a · rt-a/pid-1 | req 86b8cd1d4a74 | v3 | config.applied |  |  |  | 51aa9d8936d2 |
| 24 · t50 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v3 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | f0c231227185 |
| 25 · t51 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v3 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 7817a313c22a |
| 26 · t52 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v3 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 55576cb32cbe |
| 27 · t53 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v3 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0976 | model gateway fast-model · 488 tokens | 371841369dbf |
| 28 · t54 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v3 · agents.incident-agent.tools.restart_service[0] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | d08e4052d8a9 |
| 29 · t54 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.finished |  | $0.0976 |  | d27b0af9e9c8 |

**Measures**

| Measure | Value |
|---|---|
| suspend_version | `v2` |
| inflight_calls_after_suspension | `2` |
| inflight_executed_after_suspension | `0` |
| new_run | `denied AGENT_SUSPENDED` |
| other_agent_calls_executed | `4` |
| restore_alone | `rejected` |
| restore_version | `v3` |

**Assertions** (8/8)

| Assertion | Result |
|---|---|
| in-flight run: every call after the suspension was denied (0 executed) | pass |
| in-flight run: denial reason is AGENT_SUSPENDED under the new version | pass |
| new run denied at start: 0 tool calls, 0 model calls | pass |
| no production restart happened | pass |
| support-agent unaffected (every call executed) | pass |
| restoring needs a second person: oncall.ic alone rejected | pass |
| restore with sre.lead as second approver works at the next run | pass |
| agent code unchanged, one runtime process | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P4 — SUSPEND: THE KILL SWITCH                                                  │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              incident-agent · status active → suspended                  │
│ Central change     v2 · suspend-incident-agent · oncall.ic (break-glass)       │
│ Run in flight      run-001 paused after query_logs; 2 later calls → 0 executed │
│ New run            run-002 → DENIED AGENT_SUSPENDED · 0 tool calls · 0 model   │
│                    calls                                                       │
│ Other agents       support-agent run-003 → every call executed                 │
│ Restore alone      oncall.ic → REJECTED (widening needs a second approver)     │
│ Restore            v3 · oncall.ic + sre.lead → run-004 executes                │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ in-flight run: every call after the suspension was denied (0 executed)
  ✓ in-flight run: denial reason is AGENT_SUSPENDED under the new version
  ✓ new run denied at start: 0 tool calls, 0 model calls
  ✓ no production restart happened
  ✓ support-agent unaffected (every call executed)
  ✓ restoring needs a second person: oncall.ic alone rejected
  ✓ restore with sre.lead as second approver works at the next run
  ✓ agent code unchanged, one runtime process

  PROOF P4: PASS
  Test assertions: 8/8 passed
```

### P5-C-budgets

*CAPABILITY · a central quota and budget stop the run at the configured limit*

**Question.** Does a central quota stop the third tool call, and an exhausted budget stop the next run?

**Expected.** call 3 denied with TOOL_CALL_BUDGET_EXCEEDED; next run denied with DAILY_BUDGET_EXHAUSTED  
**Observed.** call 3 TOOL_CALL_BUDGET_EXCEEDED; run-003 DAILY_BUDGET_EXHAUSTED  
**Outcome.** HELD

**Step ledger** (22 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 |  | run.requested |  |  |  | 61e922723293 |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | req 74f87bdd5059 | v1 | config.applied |  |  |  | 2bd967bfce17 |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v1 · agents.support-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 5702b943e04f |
| 5 · t11 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v1 · agents.support-agent.tools.read_case | tool.executed · read_case | ALLOW · POLICY_ALLOW |  | support-mcp read_case → 200 | bfabdc9749c5 |
| 6 · t12 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v1 · agents.support-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | c9f0aaf54103 |
| 7 · t13 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v1 · models.profiles.standard.confidential | model.called · private-model | ALLOW · MODEL_RESOLVED | $0.3552 | model gateway private-model · 444 tokens | 492022580cba |
| 8 · t14 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v1 · agents.support-agent.tools.refund_customer[0] | action.executed · refund_customer | ALLOW · POLICY_ALLOW |  | billing-mcp refund_customer → 200 | 8e718894db3f |
| 9 · t14 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 |  | run.finished |  | $0.3552 |  | d24d25023c3e |
| 10 · t20 | control plane |  | v2 | change.published support-tool-call-budget | PUBLISHED |  |  | b51b4bc962a9 |
| 11 · t30 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 |  | run.requested |  |  |  | ecd2c80190cd |
| 12 · t30 | runtime rt-a · rt-a/pid-1 | req 74f87bdd5059 | v2 | config.applied |  |  |  | 3f12476b769c |
| 13 · t30 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v2 · agents.support-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | d2ea148e4867 |
| 14 · t31 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v2 · agents.support-agent.tools.read_case | tool.executed · read_case | ALLOW · POLICY_ALLOW |  | support-mcp read_case → 200 | 9455fac4ff28 |
| 15 · t32 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v2 · agents.support-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 352c29e278d2 |
| 16 · t33 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v2 · models.profiles.standard.confidential | model.called · private-model | ALLOW · MODEL_RESOLVED | $0.3552 | model gateway private-model · 444 tokens | 17fbbcfd57ca |
| 17 · t34 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v2 · agents.support-agent.limits.max_tool_calls | action.denied · refund_customer | DENY · TOOL_CALL_BUDGET_EXCEEDED |  | no call reached a system | 2d881b9bb674 |
| 18 · t34 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 |  | run.finished |  | $0.3552 |  | 50b5a79431e7 |
| 19 · t40 | control plane |  | v3 | change.published support-daily-budget-exhausted | PUBLISHED |  |  | 7cab5fe2ac6c |
| 20 · t50 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 |  | run.requested |  |  |  | b26a94f51ae3 |
| 21 · t50 | runtime rt-a · rt-a/pid-1 | req 74f87bdd5059 | v3 | config.applied |  |  |  | f60083fb4ceb |
| 22 · t50 | runtime rt-a · rt-a/pid-1 | support-agent · req 74f87bdd5059 | v3 · agents.support-agent.limits.daily_budget | run.decision | DENY · DAILY_BUDGET_EXHAUSTED |  |  | 05121457fd5a |

**Measures**

| Measure | Value |
|---|---|
| quota_version | `v2` |
| max_tool_calls | `2` |
| call_3 | `denied TOOL_CALL_BUDGET_EXCEEDED` |
| refunds | `1` |
| budget_version | `v3` |
| spent_usd | `0.7104` |
| run_after_budget | `denied DAILY_BUDGET_EXHAUSTED` |

**Assertions** (7/7)

| Assertion | Result |
|---|---|
| before the quota: 3 tool calls executed, 1 refund | pass |
| call 1 ALLOW, call 2 ALLOW | pass |
| call 3 DENY TOOL_CALL_BUDGET_EXCEEDED | pass |
| billing system shows 1 refund (the capped run refunded nothing) | pass |
| exhausted daily budget: next run denied at start | pass |
| the budget is metered centrally (shared spend meter), not per process | pass |
| agent code unchanged, one runtime process | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P5 — BUDGETS AND QUOTAS                                                        │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              support-agent                                               │
│ Central change     v2 · max_tool_calls = 2 · support.lead                      │
│ CALL 1             read_case → EXECUTED                                        │
│ CALL 2             query_logs → EXECUTED                                       │
│ CALL 3             refund_customer → DENY · TOOL_CALL_BUDGET_EXCEEDED          │
│ Refunds            1 (from run-001, before the quota)                          │
│ Central change     v3 · daily budget below today's spend ($0.7104)             │
│ Next run           run-003 → DENIED DAILY_BUDGET_EXHAUSTED                     │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ before the quota: 3 tool calls executed, 1 refund
  ✓ call 1 ALLOW, call 2 ALLOW
  ✓ call 3 DENY TOOL_CALL_BUDGET_EXCEEDED
  ✓ billing system shows 1 refund (the capped run refunded nothing)
  ✓ exhausted daily budget: next run denied at start
  ✓ the budget is metered centrally (shared spend meter), not per process
  ✓ agent code unchanged, one runtime process

  PROOF P5: PASS
  Test assertions: 7/7 passed
```

### P6-C-revoke-mcp

*CAPABILITY · disabling one MCP server centrally stops every agent that uses it, and no other*

**Question.** Does disabling one server centrally stop every agent that uses it, and no other?

**Expected.** both dependent agents denied, finance untouched, 0 calls reach the server  
**Observed.** 0 observability calls after revoke; 3 calls denied  
**Outcome.** HELD

**Step ledger** (41 rows; the first 40 shown, all in `ledger.jsonl`)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.requested |  |  |  | d2226771cf55 |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | req 86b8cd1d4a74 | v1 | config.applied |  |  |  | 73b6632535e3 |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | a120b8415855 |
| 5 · t11 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | a7d191300c9f |
| 6 · t12 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 40cc7aee1d48 |
| 7 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0976 | model gateway fast-model · 488 tokens | 26958344e51f |
| 8 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.restart_service[0] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | d0aad90898e3 |
| 9 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.finished |  | $0.0976 |  | 4e3a6a988174 |
| 10 · t15 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 |  | run.requested |  |  |  | d49c1e62fd9b |
| 11 · t15 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v1 · agents.support-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | f989bc3b7868 |
| 12 · t16 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v1 · agents.support-agent.tools.read_case | tool.executed · read_case | ALLOW · POLICY_ALLOW |  | support-mcp read_case → 200 | 2aff01fb8a5b |
| 13 · t17 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v1 · agents.support-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 8e177893de6e |
| 14 · t18 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v1 · models.profiles.standard.confidential | model.called · private-model | ALLOW · MODEL_RESOLVED | $0.3552 | model gateway private-model · 444 tokens | 4146739e47a4 |
| 15 · t18 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 |  | run.finished |  | $0.3552 |  | 2cb86d4be416 |
| 16 · t20 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.requested |  |  |  | cfc3c03dc939 |
| 17 · t20 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · agents.finance-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 729b1b3591f2 |
| 18 · t21 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · agents.finance-agent.tools.read_ledger | tool.executed · read_ledger | ALLOW · POLICY_ALLOW |  | billing-mcp read_ledger → 200 | e38c458416d4 |
| 19 · t22 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · agents.finance-agent.tools.flag_transaction | action.executed · flag_transaction | ALLOW · POLICY_ALLOW |  | billing-mcp flag_transaction → 200 | e84b0cd5bbbe |
| 20 · t23 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0894 | model gateway fast-model · 447 tokens | ba263284f62d |
| 21 · t23 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.finished |  | $0.0894 |  | 0f6cf29d9e19 |
| 22 · t30 | control plane |  | v2 | change.published revoke-observability-mcp | PUBLISHED |  |  | 6fc6ad4cadfa |
| 23 · t40 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.requested |  |  |  | 9645924d3910 |
| 24 · t40 | runtime rt-a · rt-a/pid-1 | req 86b8cd1d4a74 | v2 | config.applied |  |  |  | e0e0898e67b5 |
| 25 · t40 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 7acd68b401ae |
| 26 · t41 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · mcp_servers.observability-mcp.status | action.denied · query_logs | DENY · MCP_SERVER_DISABLED |  | no call reached a system | 57599d100072 |
| 27 · t42 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · mcp_servers.observability-mcp.status | action.denied · query_metrics | DENY · MCP_SERVER_DISABLED |  | no call reached a system | 0ada73b5c55e |
| 28 · t43 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0832 | model gateway fast-model · 416 tokens | dbfdc041e2fb |
| 29 · t43 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.finished |  | $0.0832 |  | 04a59146fca0 |
| 30 · t45 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 |  | run.requested |  |  |  | fde79e257367 |
| 31 · t45 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v2 · agents.support-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | eaf745c97023 |
| 32 · t46 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v2 · agents.support-agent.tools.read_case | tool.executed · read_case | ALLOW · POLICY_ALLOW |  | support-mcp read_case → 200 | 28a4ce4dcd6f |
| 33 · t47 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v2 · mcp_servers.observability-mcp.status | action.denied · query_logs | DENY · MCP_SERVER_DISABLED |  | no call reached a system | f3af068df029 |
| 34 · t48 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v2 · models.profiles.standard.confidential | model.called · private-model | ALLOW · MODEL_RESOLVED | $0.3552 | model gateway private-model · 444 tokens | 0adb615cad2a |
| 35 · t48 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 |  | run.finished |  | $0.3552 |  | f601adb8eb63 |
| 36 · t50 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.requested |  |  |  | d098bb77511e |
| 37 · t50 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 71159e13219c |
| 38 · t51 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.read_ledger | tool.executed · read_ledger | ALLOW · POLICY_ALLOW |  | billing-mcp read_ledger → 200 | ac38f8212fa6 |
| 39 · t52 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.flag_transaction | action.executed · flag_transaction | ALLOW · POLICY_ALLOW |  | billing-mcp flag_transaction → 200 | 3b8e2c0d9529 |
| 40 · t53 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0894 | model gateway fast-model · 447 tokens | 20b5f0e49bba |

**Measures**

| Measure | Value |
|---|---|
| revoke_version | `v2` |
| observability_calls_before | `3` |
| observability_calls_after | `0` |
| calls_denied_mcp_disabled | `3` |
| agents_affected | `2` |
| agents_unaffected | `1` |

**Assertions** (7/7)

| Assertion | Result |
|---|---|
| before: incident-agent query_logs ALLOW | pass |
| before: support-agent query_logs ALLOW | pass |
| after: incident-agent query_logs DENY MCP_SERVER_DISABLED | pass |
| after: support-agent query_logs DENY MCP_SERVER_DISABLED | pass |
| observability-mcp received 0 calls after the revocation | pass |
| finance-agent (no observability tools) unaffected | pass |
| one central change, 0 agent files changed | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P6 — REVOKE ONE MCP SERVER FOR EVERY AGENT                                     │
├────────────────────────────────────────────────────────────────────────────────┤
│ Shared tool        query_logs (observability-mcp)                              │
│ Before             incident-agent → ALLOW · support-agent → ALLOW              │
│ Central change     v2 · observability-mcp = disabled · platform.admin (break-  │
│                    glass)                                                      │
│ After              incident-agent → DENY · support-agent → DENY                │
│                    (MCP_SERVER_DISABLED)                                       │
│ Unaffected         finance-agent → every call executed                         │
│ observability-mcp  3 calls before · 0 after                                    │
│ Agent code         UNCHANGED · 0 files edited · 0 redeploys                    │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ before: incident-agent query_logs ALLOW
  ✓ before: support-agent query_logs ALLOW
  ✓ after: incident-agent query_logs DENY MCP_SERVER_DISABLED
  ✓ after: support-agent query_logs DENY MCP_SERVER_DISABLED
  ✓ observability-mcp received 0 calls after the revocation
  ✓ finance-agent (no observability tools) unaffected
  ✓ one central change, 0 agent files changed

  PROOF P6: PASS
  Test assertions: 7/7 passed
```

### P7-C-models

*CAPABILITY · the model is chosen by the control plane, by data class, never named by the agent*

**Question.** Can the control plane move the default model and withdraw a model without an agent naming one?

**Expected.** default moves with no agent change; confidential data never falls back to an uncleared model  
**Observed.** fast-model → large-model; confidential under v3: DENIED NO_ALLOWED_MODEL_FOR_DATA_CLASS  
**Outcome.** HELD

**Step ledger** (45 rows; the first 40 shown, all in `ledger.jsonl`)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.requested |  |  |  | d2226771cf55 |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | req 86b8cd1d4a74 | v1 | config.applied |  |  |  | 73b6632535e3 |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | a120b8415855 |
| 5 · t11 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | a7d191300c9f |
| 6 · t12 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 40cc7aee1d48 |
| 7 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0976 | model gateway fast-model · 488 tokens | 26958344e51f |
| 8 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.restart_service[0] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | d0aad90898e3 |
| 9 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.finished |  | $0.0976 |  | 4e3a6a988174 |
| 10 · t15 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 |  | run.requested |  |  |  | d49c1e62fd9b |
| 11 · t15 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v1 · agents.support-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | f989bc3b7868 |
| 12 · t16 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v1 · agents.support-agent.tools.read_case | tool.executed · read_case | ALLOW · POLICY_ALLOW |  | support-mcp read_case → 200 | 2aff01fb8a5b |
| 13 · t17 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v1 · agents.support-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 8e177893de6e |
| 14 · t18 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v1 · models.profiles.standard.confidential | model.called · private-model | ALLOW · MODEL_RESOLVED | $0.3552 | model gateway private-model · 444 tokens | 4146739e47a4 |
| 15 · t18 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 |  | run.finished |  | $0.3552 |  | 2cb86d4be416 |
| 16 · t20 | control plane |  | v2 | change.published migrate-default-model | PUBLISHED |  |  | 30a121e74fdd |
| 17 · t30 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.requested |  |  |  | ec43de6b06f9 |
| 18 · t30 | runtime rt-a · rt-a/pid-1 | req 86b8cd1d4a74 | v2 | config.applied |  |  |  | ce3c56b8065a |
| 19 · t30 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | f8ae7eafc05c |
| 20 · t31 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 200405629783 |
| 21 · t32 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 93c2e3eec8a4 |
| 22 · t33 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · models.profiles.standard.default | model.called · large-model | ALLOW · MODEL_RESOLVED | $0.732 | model gateway large-model · 488 tokens | c1501822c248 |
| 23 · t34 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · agents.incident-agent.tools.restart_service[0] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | 314533c321cf |
| 24 · t34 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.finished |  | $0.732 |  | 60581e977a7a |
| 25 · t35 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 |  | run.requested |  |  |  | 1986edd96f78 |
| 26 · t35 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v2 · agents.support-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 31ab1cd926ba |
| 27 · t36 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v2 · agents.support-agent.tools.read_case | tool.executed · read_case | ALLOW · POLICY_ALLOW |  | support-mcp read_case → 200 | bf0199f613b6 |
| 28 · t37 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v2 · agents.support-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 6a06069d509c |
| 29 · t38 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 | v2 · models.profiles.standard.confidential | model.called · private-model | ALLOW · MODEL_RESOLVED | $0.3552 | model gateway private-model · 444 tokens | 4087a23a34b7 |
| 30 · t38 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 |  | run.finished |  | $0.3552 |  | 305ee15e7bb2 |
| 31 · t40 | control plane |  | v3 | change.published withdraw-private-model | PUBLISHED |  |  | 10b43b5373d5 |
| 32 · t50 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.requested |  |  |  | 2981827083c1 |
| 33 · t50 | runtime rt-a · rt-a/pid-1 | req 86b8cd1d4a74 | v3 | config.applied |  |  |  | 64e3779363b0 |
| 34 · t50 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v3 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | cb2003fd9eb0 |
| 35 · t51 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v3 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | f91876d97eb0 |
| 36 · t52 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v3 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | dcd295ddc29d |
| 37 · t53 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v3 · models.profiles.standard.default | model.called · large-model | ALLOW · MODEL_RESOLVED | $0.732 | model gateway large-model · 488 tokens | 05c85c298f4f |
| 38 · t54 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v3 · agents.incident-agent.tools.restart_service[0] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | 72d01aada315 |
| 39 · t54 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.finished |  | $0.732 |  | 600be19d40be |
| 40 · t55 | runtime rt-a · rt-a/pid-1 | support-agent · req 4fb91f8387b3 |  | run.requested |  |  |  | 52078916b6a9 |

**Measures**

| Measure | Value |
|---|---|
| v1_incident_model | `fast-model` |
| v2_incident_model | `large-model` |
| v3_support_model | `DENIED NO_ALLOWED_MODEL_FOR_DATA_CLASS` |
| confidential_calls | `2` |
| model_names_in_agent_code | `0` |

**Assertions** (7/7)

| Assertion | Result |
|---|---|
| agent source names no model (0 catalog names in acp/agents/) | pass |
| v1: incident-agent served by fast-model | pass |
| v2: incident-agent served by large-model, agent unchanged | pass |
| confidential data always served by private-model while it is allowed | pass |
| v3: private-model withdrawn → confidential call DENIED, no fallback to a public model | pass |
| no confidential prompt ever reached a model without confidential clearance | pass |
| agent code unchanged, one runtime process | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P7 — MODEL GOVERNANCE                                                          │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agents             incident-agent (internal data) · support-agent              │
│                    (confidential case)                                         │
│ Agent code         names no model: 0 catalog names in acp/agents/              │
│ v1                 incident → fast-model · support → private-model             │
│ Central change     v2 · default model → large-model (platform.admin + ml.lead) │
│ v2                 incident → large-model · support → private-model            │
│ Central change     v3 · private-model withdrawn (break-glass)                  │
│ v3                 incident → large-model · support → DENIED (no fallback to a │
│                    public model)                                               │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ agent source names no model (0 catalog names in acp/agents/)
  ✓ v1: incident-agent served by fast-model
  ✓ v2: incident-agent served by large-model, agent unchanged
  ✓ confidential data always served by private-model while it is allowed
  ✓ v3: private-model withdrawn → confidential call DENIED, no fallback to a
    public model
  ✓ no confidential prompt ever reached a model without confidential clearance
  ✓ agent code unchanged, one runtime process

  PROOF P7: PASS
  Test assertions: 7/7 passed
```

### P8-C-canary

*CAPABILITY · a canary reaches only its bucket; rollback returns every run to stable*

**Question.** Does a canary reach only its bucket of runs, and does rollback return every run to the stable version?

**Expected.** a deterministic ~quarter of runs on the canary; none after rollback; all after promotion  
**Observed.** canary 4/20; rollback 0/20; promoted 10/10  
**Outcome.** HELD

**Step ledger** (312 rows; the first 40 shown, all in `ledger.jsonl`)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t5 | control plane |  | v2 | change.published migrate-default-model | PUBLISHED |  |  | fdcf08f0513e |
| 3 · t6 | control plane |  | v2 | change.rollout | ROLLOUT |  |  | ca8b6543d0f0 |
| 4 · t15 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.requested |  |  |  | db19d14e9742 |
| 5 · t15 | runtime rt-a · rt-a/pid-1 | req bcc78da5ba13 | v1 | config.applied |  |  |  | f0b80f21bbb6 |
| 6 · t15 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · agents.finance-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 400d36f35829 |
| 7 · t16 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · agents.finance-agent.tools.read_ledger | tool.executed · read_ledger | ALLOW · POLICY_ALLOW |  | billing-mcp read_ledger → 200 | 429231b95454 |
| 8 · t17 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · agents.finance-agent.tools.flag_transaction | action.executed · flag_transaction | ALLOW · POLICY_ALLOW |  | billing-mcp flag_transaction → 200 | 4994f2bf9f9a |
| 9 · t18 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0894 | model gateway fast-model · 447 tokens | 0eeb183db16e |
| 10 · t18 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.finished |  | $0.0894 |  | 136d95f5c24e |
| 11 · t20 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.requested |  |  |  | 0e57c99100c8 |
| 12 · t20 | runtime rt-a · rt-a/pid-1 | req bcc78da5ba13 | v2 | config.applied |  |  |  | 1b410509add1 |
| 13 · t20 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 1820673179e4 |
| 14 · t21 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.read_ledger | tool.executed · read_ledger | ALLOW · POLICY_ALLOW |  | billing-mcp read_ledger → 200 | 2435c181c552 |
| 15 · t22 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.flag_transaction | action.executed · flag_transaction | ALLOW · POLICY_ALLOW |  | billing-mcp flag_transaction → 200 | ccb017c3ffb1 |
| 16 · t23 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · models.profiles.standard.default | model.called · large-model | ALLOW · MODEL_RESOLVED | $0.6705 | model gateway large-model · 447 tokens | 2dce519d3683 |
| 17 · t23 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.finished |  | $0.6705 |  | e814f8811c51 |
| 18 · t25 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.requested |  |  |  | e0728020301a |
| 19 · t25 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 3253debe7b43 |
| 20 · t26 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.read_ledger | tool.executed · read_ledger | ALLOW · POLICY_ALLOW |  | billing-mcp read_ledger → 200 | 2e510055947b |
| 21 · t27 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.flag_transaction | action.executed · flag_transaction | ALLOW · POLICY_ALLOW |  | billing-mcp flag_transaction → 200 | 8cb0cd4975bf |
| 22 · t28 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · models.profiles.standard.default | model.called · large-model | ALLOW · MODEL_RESOLVED | $0.6705 | model gateway large-model · 447 tokens | 4465aa6479a5 |
| 23 · t28 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.finished |  | $0.6705 |  | 706a25214710 |
| 24 · t30 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.requested |  |  |  | 0ca8b2e99a78 |
| 25 · t30 | runtime rt-a · rt-a/pid-1 | req bcc78da5ba13 | v1 | config.applied |  |  |  | 1f41af8687b9 |
| 26 · t30 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · agents.finance-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 75ea0491f8c9 |
| 27 · t31 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · agents.finance-agent.tools.read_ledger | tool.executed · read_ledger | ALLOW · POLICY_ALLOW |  | billing-mcp read_ledger → 200 | 1075181428db |
| 28 · t32 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · agents.finance-agent.tools.flag_transaction | action.executed · flag_transaction | ALLOW · POLICY_ALLOW |  | billing-mcp flag_transaction → 200 | 37ba9aca0e38 |
| 29 · t33 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0894 | model gateway fast-model · 447 tokens | 9e69469b19ac |
| 30 · t33 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.finished |  | $0.0894 |  | 63dbccb873ce |
| 31 · t35 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.requested |  |  |  | 2fecfc9f4abc |
| 32 · t35 | runtime rt-a · rt-a/pid-1 | req bcc78da5ba13 | v2 | config.applied |  |  |  | 2689b35f6adb |
| 33 · t35 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | c15e737fed6b |
| 34 · t36 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.read_ledger | tool.executed · read_ledger | ALLOW · POLICY_ALLOW |  | billing-mcp read_ledger → 200 | 255f7a0cf1e7 |
| 35 · t37 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.flag_transaction | action.executed · flag_transaction | ALLOW · POLICY_ALLOW |  | billing-mcp flag_transaction → 200 | 245d7bcf4280 |
| 36 · t38 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · models.profiles.standard.default | model.called · large-model | ALLOW · MODEL_RESOLVED | $0.6705 | model gateway large-model · 447 tokens | fb619bcd75b0 |
| 37 · t38 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.finished |  | $0.6705 |  | 1383d9250a99 |
| 38 · t40 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.requested |  |  |  | 1f1b23e2b98b |
| 39 · t40 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 8983a6f06fbc |
| 40 · t41 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.read_ledger | tool.executed · read_ledger | ALLOW · POLICY_ALLOW |  | billing-mcp read_ledger → 200 | d57088f048f4 |

**Measures**

| Measure | Value |
|---|---|
| canary_version | `v2` |
| canary_percent | `25` |
| canary_runs | `20` |
| canary_runs_on_new | `4` |
| rollback_runs_on_new | `0` |
| promoted_runs_on_new | `10` |

**Assertions** (6/6)

| Assertion | Result |
|---|---|
| canary reached some but not all runs | pass |
| canary membership = deterministic bucket < 25 | pass |
| every run used exactly one version, and its model matches it | pass |
| after rollback: 0 runs on the canary version | pass |
| after promote: every run on the new version | pass |
| agent code unchanged, one runtime process | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P8 — STAGED ROLLOUT AND ROLLBACK                                               │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              finance-agent (20 + 20 + 10 runs)                           │
│ Change             v2 · default model → large-model, published inactive        │
│ Canary 25%         4 of 20 runs on v2 (large-model) · rest on v1               │
│ Rollback           0 of 20 runs on v2                                          │
│ Promote            10 of 10 runs on v2                                         │
│ Agent code         UNCHANGED · no redeploy at any step                         │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ canary reached some but not all runs
  ✓ canary membership = deterministic bucket < 25
  ✓ every run used exactly one version, and its model matches it
  ✓ after rollback: 0 runs on the canary version
  ✓ after promote: every run on the new version
  ✓ agent code unchanged, one runtime process

  PROOF P8: PASS
  Test assertions: 6/6 passed
```

### P9-C-outage

*BOUNDARIES · without the control plane, reads continue within a staleness bound and mutations fail closed*

**Question.** What does the runtime do without its control plane: for reads, mutations, stale policy, tampered bundles?

**Expected.** reads on last-known-good, mutations fail closed, everything denied past the staleness bound  
**Observed.** mutation CONTROL_PLANE_UNREACHABLE; 3 calls ran after the suspension was published  
**Outcome.** QUALIFIED · config.unreachable: a suspension cannot reach a partitioned runtime; exposure bounded by max_staleness and fail-closed mutations

**Step ledger** (40 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 6c3980d85a57 |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.applied |  |  |  | d481f9e5b6d2 |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 05a8e36204d2 |
| 5 · t11 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 8e37890d977c |
| 6 · t12 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 777b1356bc92 |
| 7 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0982 | model gateway fast-model · 491 tokens | db644edeed8a |
| 8 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.restart_service[1] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | 0642969a757e |
| 9 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0982 |  | 1424e2cbb21c |
| 10 · t20 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 724cdda17baa |
| 11 · t20 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | 211a152d1710 |
| 12 · t20 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 797edb73a411 |
| 13 · t21 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | f5f4ca001873 |
| 14 · t21 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | b3b36b6d0439 |
| 15 · t22 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | 2e05a652a265 |
| 16 · t22 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 3cb333b92ce1 |
| 17 · t23 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | a7704ec108e1 |
| 18 · t23 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0982 | model gateway fast-model · 491 tokens | 176e261e686c |
| 19 · t24 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | 9f9422522f53 |
| 20 · t24 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · failure_policy.unreachable.mutation | action.denied · restart_service | DENY · CONTROL_PLANE_UNREACHABLE |  | no call reached a system | 48d437bfc40f |
| 21 · t24 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0982 |  | 2409f328a236 |
| 22 · t25 | control plane |  | v2 | change.published suspend-incident-agent | PUBLISHED |  |  | 4d7e9100ed45 |
| 23 · t30 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 0f04af881538 |
| 24 · t30 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | 4ff71bd2c36b |
| 25 · t30 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | ae012f93128c |
| 26 · t31 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | eb3b70134557 |
| 27 · t31 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | e50dec2cead7 |
| 28 · t32 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | 4811a619f226 |
| 29 · t32 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 5846c0bcb48c |
| 30 · t33 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | d766104d2e83 |
| 31 · t33 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0982 | model gateway fast-model · 491 tokens | 9c3bf8cc9655 |
| 32 · t34 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | 2328f6200dd7 |
| 33 · t34 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · failure_policy.unreachable.mutation | action.denied · restart_service | DENY · CONTROL_PLANE_UNREACHABLE |  | no call reached a system | 276711cf836b |
| 34 · t34 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0982 |  | 95e443c7f7d7 |
| 35 · t60 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 9974f4b26841 |
| 36 · t60 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.unreachable | control plane unreachable from rt-a |  |  | 07975283c354 |
| 37 · t60 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · failure_policy.max_staleness_ticks | run.decision | DENY · POLICY_STALE |  |  | e6856aa30619 |
| 38 · t70 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 2c4ba796305e |
| 39 · t70 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v2 | config.applied |  |  |  | f3abd75274d9 |
| 40 · t70 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.status | run.decision | DENY · AGENT_SUSPENDED |  |  | 814ea315bd0e |

**Measures**

| Measure | Value |
|---|---|
| lkg_version | `v1` |
| reads_on_lkg | `4` |
| mutation_during_outage | `CONTROL_PLANE_UNREACHABLE` |
| calls_executed_after_suspension_published | `3` |
| max_staleness_ticks | `30` |
| stale_run | `POLICY_STALE` |
| recovered_run | `AGENT_SUSPENDED` |

**Assertions** (6/6)

| Assertion | Result |
|---|---|
| reads during the outage ran on the last-known-good bundle (v1) | pass |
| production mutation during the outage failed closed (CONTROL_PLANE_UNREACHABLE) | pass |
| deploy system: only the warm run's restart (1) | pass |
| QUALIFIED: the suspension could not reach a partitioned runtime; reads continued under v1 | pass |
| beyond max_staleness every run is denied (POLICY_STALE) | pass |
| after recovery the suspension lands at the next enforcement point | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P9a — CONTROL PLANE UNREACHABLE                                                │
├────────────────────────────────────────────────────────────────────────────────┤
│ Runtime            rt-a · last-known-good v1 cached                            │
│ Read (query_logs)  ALLOW from last-known-good v1                               │
│ Mutation (restart) DENY · CONTROL_PLANE_UNREACHABLE (fail closed)              │
│ Suspension         v2 published during the partition                           │
│ …after it          3 read/model calls still executed on v1  ← QUALIFIED        │
│ Past staleness     DENY · POLICY_STALE for everything                          │
│ Partition heals    next run → DENY · AGENT_SUSPENDED                           │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ reads during the outage ran on the last-known-good bundle (v1)
  ✓ production mutation during the outage failed closed
    (CONTROL_PLANE_UNREACHABLE)
  ✓ deploy system: only the warm run's restart (1)
  ✓ QUALIFIED: the suspension could not reach a partitioned runtime; reads
    continued under v1
  ✓ beyond max_staleness every run is denied (POLICY_STALE)
  ✓ after recovery the suspension lands at the next enforcement point

  PROOF P9a: QUALIFIED · held within the stated bound (max staleness, fail-closed mutations)
  Test assertions: 6/6 passed
```

### P9-C-tampered-bundle

*BOUNDARIES · without the control plane, reads continue within a staleness bound and mutations fail closed*

**Question.** What does the runtime do without its control plane: for reads, mutations, stale policy, tampered bundles?

**Expected.** rejected; last-known-good kept; mutation fails closed  
**Observed.** 5 rejections; applied v1  
**Outcome.** HELD

**Step ledger** (22 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.requested |  |  |  | d2226771cf55 |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | req 86b8cd1d4a74 | v1 | config.applied |  |  |  | 73b6632535e3 |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | a120b8415855 |
| 5 · t11 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | a7d191300c9f |
| 6 · t12 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 40cc7aee1d48 |
| 7 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0976 | model gateway fast-model · 488 tokens | 26958344e51f |
| 8 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.restart_service[0] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | d0aad90898e3 |
| 9 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.finished |  | $0.0976 |  | 4e3a6a988174 |
| 10 · t20 | control plane |  | v2 | change.published restart-requires-approval | PUBLISHED |  |  | 47e044be3e2c |
| 11 · t30 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 13656f975e3b |
| 12 · t30 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.rejected | bundle v2 failed signature verification |  |  | e8d24402c4e0 |
| 13 · t30 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | ba3d3f356d06 |
| 14 · t31 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.rejected | bundle v2 failed signature verification |  |  | 0a5f98926ea4 |
| 15 · t31 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 75a5d5e3187e |
| 16 · t32 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.rejected | bundle v2 failed signature verification |  |  | 70a990d7a0e5 |
| 17 · t32 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | d6990d59764d |
| 18 · t33 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.rejected | bundle v2 failed signature verification |  |  | 129da53f0929 |
| 19 · t33 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0982 | model gateway fast-model · 491 tokens | 957002e5f45b |
| 20 · t34 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.rejected | bundle v2 failed signature verification |  |  | 7a2c72b7fffe |
| 21 · t34 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · failure_policy.unreachable.mutation | action.denied · restart_service | DENY · BUNDLE_REJECTED |  | no call reached a system | ea852e79ccc7 |
| 22 · t34 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0982 |  | 79567b268730 |

**Measures**

| Measure | Value |
|---|---|
| rejected_events | `5` |
| applied_version | `v1` |
| restart_decision | `BUNDLE_REJECTED` |

**Assertions** (3/3)

| Assertion | Result |
|---|---|
| the altered bundle failed signature verification and was not applied | pass |
| the mutation failed closed while no verified current bundle was available (BUNDLE_REJECTED) | pass |
| deploy system: no production restart, no deletion | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P9b — TAMPERED BUNDLE IN TRANSIT                                               │
├────────────────────────────────────────────────────────────────────────────────┤
│ Attack             v2 altered to allow delete_resource and production restarts │
│ Runtime            signature check FAILED → 5 config.rejected events           │
│ Applied            v1 (last-known-good); the altered bundle never applied      │
│ Mutation           restart_service → DENY · BUNDLE_REJECTED (fail closed)      │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ the altered bundle failed signature verification and was not applied
  ✓ the mutation failed closed while no verified current bundle was available
    (BUNDLE_REJECTED)
  ✓ deploy system: no production restart, no deletion

  PROOF P9b: PASS
  Test assertions: 3/3 passed
```

### P9-C-broker-down

*BOUNDARIES · without the control plane, reads continue within a staleness bound and mutations fail closed*

**Question.** What does the runtime do without its control plane: for reads, mutations, stale policy, tampered bundles?

**Expected.** no credential, no call  
**Observed.** all tool calls denied CREDENTIAL_UNAVAILABLE  
**Outcome.** HELD

**Step ledger** (8 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 6c3980d85a57 |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v1 | config.applied |  |  |  | d481f9e5b6d2 |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 05a8e36204d2 |
| 5 · t11 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_logs | action.failed · query_logs | ALLOW · POLICY_ALLOW |  | no call reached a system | da7ec6eaaa98 |
| 6 · t12 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_metrics | action.failed · query_metrics | ALLOW · POLICY_ALLOW |  | no call reached a system | a1aaa34d6499 |
| 7 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0832 | model gateway fast-model · 416 tokens | ae0b0ed75c5e |
| 8 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0832 |  | c93bf638bcb3 |

**Measures**

| Measure | Value |
|---|---|
| tool_calls_denied | `2` |

**Assertions** (3/3)

| Assertion | Result |
|---|---|
| every tool call denied CREDENTIAL_UNAVAILABLE (policy allowed them) | pass |
| no system received a call without a credential | pass |
| deploy system: 0 restarts | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P9c — CREDENTIAL BROKER DOWN                                                   │
├────────────────────────────────────────────────────────────────────────────────┤
│ Policy             v1 · query_logs, query_metrics ALLOW                        │
│ Broker             unavailable                                                 │
│ Result             every tool call → DENY · CREDENTIAL_UNAVAILABLE             │
│ Systems            0 calls received · 0 restarts                               │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ every tool call denied CREDENTIAL_UNAVAILABLE (policy allowed them)
  ✓ no system received a call without a credential
  ✓ deploy system: 0 restarts

  PROOF P9c: PASS
  Test assertions: 3/3 passed
```

### P10-C-drift

*BOUNDARIES · the control plane observes a runtime that has drifted from desired state, and what it did meanwhile*

**Question.** Can the control plane see a runtime that is quietly running an old version, and what it did meanwhile?

**Expected.** the control plane detects rt-b's stale version and the action it executed under it  
**Observed.** 2 drift findings; 1 mutation under a superseded version  
**Outcome.** QUALIFIED · distribution: a lagging replica served v1 without error; policy did not prevent the restart, observation caught it

**Step ledger** (41 rows; the first 40 shown, all in `ledger.jsonl`)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.requested |  |  |  | c9752a9e5c06 |
| 3 · t10 | runtime rt-a · rt-a/pid-1 | req 86b8cd1d4a74 | v1 | config.applied |  |  |  | 5164df3b7dee |
| 4 · t10 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 8b7a7431a130 |
| 5 · t11 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | f1c69380729f |
| 6 · t12 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | d7b2e8c7bfef |
| 7 · t12 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.requested |  |  |  | 5f76b2f09529 |
| 8 · t12 | runtime rt-b · rt-b/pid-1 | req 86b8cd1d4a74 | v1 | config.applied |  |  |  | fb3dd2f49ac7 |
| 9 · t12 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 90446525808e |
| 10 · t13 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0976 | model gateway fast-model · 488 tokens | db09c81f2c12 |
| 11 · t13 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | ad923a275ea3 |
| 12 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.restart_service[0] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | 97e42e9e51bc |
| 13 · t14 | runtime rt-a · rt-a/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.finished |  | $0.0976 |  | 730e722d4a7f |
| 14 · t14 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 5d6be7ead872 |
| 15 · t15 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0976 | model gateway fast-model · 488 tokens | 40367059c2b0 |
| 16 · t16 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 | v1 · agents.incident-agent.tools.restart_service[0] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | a9de1ed09a79 |
| 17 · t16 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.finished |  | $0.0976 |  | 901fa09008ac |
| 18 · t20 | control plane |  | v2 | change.published restart-requires-approval | PUBLISHED |  |  | 47e044be3e2c |
| 19 · t30 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 1c6c586b84f8 |
| 20 · t30 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v2 | config.applied |  |  |  | 27b802a2aab0 |
| 21 · t30 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 5a455e632719 |
| 22 · t31 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 8ad32a897a16 |
| 23 · t32 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | cbcddc95c9ae |
| 24 · t32 | runtime rt-b · rt-b/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 3f45ff67ba63 |
| 25 · t32 | runtime rt-b · rt-b/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 4bc77f767843 |
| 26 · t33 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0982 | model gateway fast-model · 491 tokens | 1d61f6a650ac |
| 27 · t33 | runtime rt-b · rt-b/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 8508e183b8de |
| 28 · t34 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v2 · agents.incident-agent.tools.restart_service[1] | approval.requested · restart_service | APPROVAL_REQUIRED · POLICY_APPROVAL_REQUIRED | approval-001 | no call reached a system | 875ddb6e86ae |
| 29 · t34 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0982 |  | b1f6ded0dd37 |
| 30 · t34 | runtime rt-b · rt-b/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | df8f024f540f |
| 31 · t35 | runtime rt-b · rt-b/pid-1 | incident-agent · req cb0531217710 | v1 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0982 | model gateway fast-model · 491 tokens | 520daf77fd30 |
| 32 · t36 | runtime rt-b · rt-b/pid-1 | incident-agent · req cb0531217710 | v1 · agents.incident-agent.tools.restart_service[1] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | b9b5021e9865 |
| 33 · t36 | runtime rt-b · rt-b/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.0982 |  | 3d4145f2f9c2 |
| 34 · t50 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 |  | run.requested |  |  |  | 266dadd8cb6d |
| 35 · t50 | runtime rt-b · rt-b/pid-1 | req 86b8cd1d4a74 | v2 | config.applied |  |  |  | 7054ea13472a |
| 36 · t50 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 470b78d4d2b5 |
| 37 · t51 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | ac1e66fd9d6d |
| 38 · t52 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | 9c80faa388aa |
| 39 · t53 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · models.profiles.standard.default | model.called · fast-model | ALLOW · MODEL_RESOLVED | $0.0976 | model gateway fast-model · 488 tokens | 8b583a6e2ef0 |
| 40 · t54 | runtime rt-b · rt-b/pid-1 | incident-agent · req 86b8cd1d4a74 | v2 · agents.incident-agent.tools.restart_service[0] | action.executed · restart_service | ALLOW · POLICY_ALLOW |  | deploy-mcp restart_service → 200 | 7d875d86dd13 |

**Measures**

| Measure | Value |
|---|---|
| desired | `v2` |
| observed_rt_a | `v2` |
| observed_rt_b | `v1` |
| drift_findings | `2` |
| executed_under_superseded | `1` |
| stale_after_reconcile | `0` |

**Assertions** (7/7)

| Assertion | Result |
|---|---|
| rt-a applied v2 and held the restart for approval | pass |
| rt-b, behind the lagging replica, executed the restart under v1 | pass |
| drift detected: rt-b observed v1 while desired is v2 | pass |
| drift detected: a mutation executed under a superseded version | pass |
| re-evaluated under the desired version, that action required approval | pass |
| after reconcile: no instance on a stale version | pass |
| agent code unchanged; both runtime processes never restarted | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P10 — DESIRED VS OBSERVED STATE                                                │
├────────────────────────────────────────────────────────────────────────────────┤
│ Desired            v2 (restart requires approval)                              │
│ rt-a observed      v2 → restart held for approval                              │
│ rt-b observed      v1 → restart EXECUTED (lagging replica, no error)           │
│ Drift              2 findings · stale_config rt-b ·                            │
│                    executed_under_superseded_config                            │
│ Under desired      that restart → APPROVAL_REQUIRED                            │
│ Reconcile          replica fixed · stale instances 0                           │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ rt-a applied v2 and held the restart for approval
  ✓ rt-b, behind the lagging replica, executed the restart under v1
  ✓ drift detected: rt-b observed v1 while desired is v2
  ✓ drift detected: a mutation executed under a superseded version
  ✓ re-evaluated under the desired version, that action required approval
  ✓ after reconcile: no instance on a stale version
  ✓ agent code unchanged; both runtime processes never restarted

  PROOF P10: QUALIFIED · drift detected, not prevented
  Test assertions: 7/7 passed
```

### P11-E-embedded

*NEGATIVE CONTROL · governance embedded in agents: the property is broken by design*

**Question.** Without a control plane, what does the same set of governance changes cost, and when do they take effect?

**Expected.** a governance change is a code edit that takes effect only after a redeploy  
**Observed.** 7 edits, 7 redeploys; old process still restarted  
**Outcome.** BROKEN — expected negative control · agent code: the running process kept its embedded rule until redeployed

**Step ledger** (12 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t10 | embedded embedded-old · embedded-old/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · query_logs | EXECUTED |  | observability-mcp query_logs → 200 |  |
| 2 · t10 | embedded embedded-old · embedded-old/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · query_metrics | EXECUTED |  | observability-mcp query_metrics → 200 |  |
| 3 · t10 | embedded embedded-old · embedded-old/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · fast-model | EXECUTED |  |  |  |
| 4 · t10 | embedded embedded-old · embedded-old/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · restart_service | EXECUTED |  | deploy-mcp restart_service → 200 |  |
| 5 · t30 | embedded embedded-old · embedded-old/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · query_logs | EXECUTED |  | observability-mcp query_logs → 200 |  |
| 6 · t30 | embedded embedded-old · embedded-old/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · query_metrics | EXECUTED |  | observability-mcp query_metrics → 200 |  |
| 7 · t30 | embedded embedded-old · embedded-old/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · fast-model | EXECUTED |  |  |  |
| 8 · t30 | embedded embedded-old · embedded-old/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · restart_service | EXECUTED |  | deploy-mcp restart_service → 200 |  |
| 9 · t40 | embedded embedded-new · embedded-new/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · query_logs | EXECUTED |  | observability-mcp query_logs → 200 |  |
| 10 · t40 | embedded embedded-new · embedded-new/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · query_metrics | EXECUTED |  | observability-mcp query_metrics → 200 |  |
| 11 · t40 | embedded embedded-new · embedded-new/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · fast-model | EXECUTED |  |  |  |
| 12 · t40 | embedded embedded-new · embedded-new/pid-1 | incident-agent · req cb0531217710 | embedded in agent code | none (no runtime audit in the baseline) · restart_service | PENDING_APPROVAL |  |  |  |

**Measures**

| Measure | Value |
|---|---|
| files_edited | `7` |
| lines_changed | `17` |
| redeploys | `7` |
| static_credential_literals | `8` |
| restart_before_redeploy | `executed` |
| restart_after_redeploy | `pending_approval` |
| restart-requires-approval.files | `1` |
| revoke-observability-mcp.files | `2` |
| suspend-incident-agent.files | `1` |
| migrate-default-model.files | `3` |

**Assertions** (4/4)

| Assertion | Result |
|---|---|
| before the edit the embedded agent restarts production | pass |
| BROKEN: after the edit, the running process still restarts production (no central change is possible) | pass |
| only a redeployed process (new code hash) holds the restart | pass |
| the embedded agents hold long-lived static credentials in code | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P11a — NEGATIVE CONTROL: GOVERNANCE INSIDE EVERY AGENT                         │
├────────────────────────────────────────────────────────────────────────────────┤
│ Change             production restarts need approval                           │
│ Edit               incident_agent.py · sha256 aae655907550… → 3a424afcaad3…    │
│ Running process    after the edit → restart EXECUTED  ← policy not in effect   │
│ Redeployed process restart → PENDING_APPROVAL                                  │
│ All four changes   7 file edits · 17 lines · 7 agent redeploys                 │
│ Credentials        8 static credential literals in agent code                  │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ before the edit the embedded agent restarts production
  ✓ BROKEN: after the edit, the running process still restarts production (no
    central change is possible)
  ✓ only a redeployed process (new code hash) holds the restart
  ✓ the embedded agents hold long-lived static credentials in code

  PROOF P11a: NEGATIVE CONTROL · property broken by design
  Test assertions: 4/4 passed
```

### P11-C-control-plane

*NEGATIVE CONTROL · governance embedded in agents: the property is broken by design*

**Question.** Without a control plane, what does the same set of governance changes cost, and when do they take effect?

**Expected.** each change takes effect at the next run with no code change  
**Observed.** 4 versions; 0 edits; 0 redeploys  
**Outcome.** HELD

**Step ledger** (30 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | control plane |  | v2 | change.published migrate-default-model | PUBLISHED |  |  | 1705d6b8cc8d |
| 3 · t12 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.requested |  |  |  | 731c3218e08d |
| 4 · t12 | runtime rt-a · rt-a/pid-1 | req bcc78da5ba13 | v2 | config.applied |  |  |  | 488fe9ae5d11 |
| 5 · t12 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 7190ad6dab8a |
| 6 · t13 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.read_ledger | tool.executed · read_ledger | ALLOW · POLICY_ALLOW |  | billing-mcp read_ledger → 200 | 68d912e5b534 |
| 7 · t14 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · agents.finance-agent.tools.flag_transaction | action.executed · flag_transaction | ALLOW · POLICY_ALLOW |  | billing-mcp flag_transaction → 200 | 5517abfba0b3 |
| 8 · t15 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 | v2 · models.profiles.standard.default | model.called · large-model | ALLOW · MODEL_RESOLVED | $0.6705 | model gateway large-model · 447 tokens | aef000f491ac |
| 9 · t15 | runtime rt-a · rt-a/pid-1 | finance-agent · req bcc78da5ba13 |  | run.finished |  | $0.6705 |  | 8a68c2de86b8 |
| 10 · t20 | control plane |  | v3 | change.published restart-requires-approval | PUBLISHED |  |  | 176a3b7a3f1b |
| 11 · t22 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 665037c53b83 |
| 12 · t22 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v3 | config.applied |  |  |  | 531d356c7475 |
| 13 · t22 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v3 · agents.incident-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | 24b1071addbc |
| 14 · t23 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v3 · agents.incident-agent.tools.query_logs | tool.executed · query_logs | ALLOW · POLICY_ALLOW |  | observability-mcp query_logs → 200 | 385caf33776b |
| 15 · t24 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v3 · agents.incident-agent.tools.query_metrics | tool.executed · query_metrics | ALLOW · POLICY_ALLOW |  | observability-mcp query_metrics → 200 | b7fff58b9814 |
| 16 · t25 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v3 · models.profiles.standard.default | model.called · large-model | ALLOW · MODEL_RESOLVED | $0.7365 | model gateway large-model · 491 tokens | 398a064f9074 |
| 17 · t26 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v3 · agents.incident-agent.tools.restart_service[1] | approval.requested · restart_service | APPROVAL_REQUIRED · POLICY_APPROVAL_REQUIRED | approval-001 | no call reached a system | a9c2ca179c77 |
| 18 · t26 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.finished |  | $0.7365 |  | 4308d628d0ad |
| 19 · t30 | control plane |  | v4 | change.published revoke-observability-mcp | PUBLISHED |  |  | 3ed722cb4652 |
| 20 · t32 | runtime rt-a · rt-a/pid-1 | support-agent · req afd77e0ac798 |  | run.requested |  |  |  | 0c9665aac554 |
| 21 · t32 | runtime rt-a · rt-a/pid-1 | req afd77e0ac798 | v4 | config.applied |  |  |  | 2f125360d729 |
| 22 · t32 | runtime rt-a · rt-a/pid-1 | support-agent · req afd77e0ac798 | v4 · agents.support-agent.status | run.decision | ALLOW · AGENT_ACTIVE |  |  | abb03ece52f6 |
| 23 · t33 | runtime rt-a · rt-a/pid-1 | support-agent · req afd77e0ac798 | v4 · agents.support-agent.tools.read_case | tool.executed · read_case | ALLOW · POLICY_ALLOW |  | support-mcp read_case → 200 | 6885c846a2ae |
| 24 · t34 | runtime rt-a · rt-a/pid-1 | support-agent · req afd77e0ac798 | v4 · mcp_servers.observability-mcp.status | action.denied · query_logs | DENY · MCP_SERVER_DISABLED |  | no call reached a system | 317c147bebc1 |
| 25 · t35 | runtime rt-a · rt-a/pid-1 | support-agent · req afd77e0ac798 | v4 · models.profiles.standard.confidential | model.called · private-model | ALLOW · MODEL_RESOLVED | $0.3552 | model gateway private-model · 444 tokens | 1379e3fa8365 |
| 26 · t35 | runtime rt-a · rt-a/pid-1 | support-agent · req afd77e0ac798 |  | run.finished |  | $0.3552 |  | 2c796c00598b |
| 27 · t40 | control plane |  | v5 | change.published suspend-incident-agent | PUBLISHED |  |  | eed8e302e34c |
| 28 · t42 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 |  | run.requested |  |  |  | 5c0b69675dac |
| 29 · t42 | runtime rt-a · rt-a/pid-1 | req cb0531217710 | v5 | config.applied |  |  |  | bf69cb01a895 |
| 30 · t42 | runtime rt-a · rt-a/pid-1 | incident-agent · req cb0531217710 | v5 · agents.incident-agent.status | run.decision | DENY · AGENT_SUSPENDED |  |  | 9183d46bc13b |

**Measures**

| Measure | Value |
|---|---|
| files_edited | `0` |
| lines_changed | `0` |
| redeploys | `0` |
| bundle_versions | `4` |
| static_credential_literals | `0` |

**Assertions** (5/5)

| Assertion | Result |
|---|---|
| default model moved at the next run (large-model) | pass |
| restart held for approval at the next run | pass |
| observability tools denied at the next run | pass |
| incident-agent denied at the next run | pass |
| 0 agent files edited, 0 processes restarted, 4 bundle versions | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P11b — THE SAME FOUR CHANGES THROUGH THE CONTROL PLANE                         │
├────────────────────────────────────────────────────────────────────────────────┤
│ Changes            model default · restart approval · revoke MCP · suspend     │
│ Published          v2 … v5 · 4 signed bundle versions                          │
│ Agent code         0 files edited · 0 redeploys · one runtime process          │
│                    throughout                                                  │
│ Effect             each change applied at the next enforcement point           │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ default model moved at the next run (large-model)
  ✓ restart held for approval at the next run
  ✓ observability tools denied at the next run
  ✓ incident-agent denied at the next run
  ✓ 0 agent files edited, 0 processes restarted, 4 bundle versions

  PROOF P11b: PASS
  Test assertions: 5/5 passed
```

### P12-C-governing-the-control-plane

*GOVERN THE GOVERNOR · the control plane's own changes are authorized, validated and on a tamper-evident log*

**Question.** Who may change the control plane, and is every change, accepted or rejected, on the record?

**Expected.** illegitimate changes rejected and logged; legitimate ones versioned and signed  
**Observed.** 3 accepted, 7 rejected, all 11 on a verifying chain  
**Outcome.** HELD

**Step ledger** (11 rows)

| Step · tick | Source · process | Agent · request | Version · rule | Event | Decision | Approval · cost | System of record | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 · t0 | control plane |  | v1 | change.published seed | PUBLISHED |  |  | 82d854efd2e3 |
| 2 · t10 | control plane |  |  | change.rejected self-grant | REJECTED · incident-agent is not a control-plane administrator |  |  | 0db9c1f11d0d |
| 3 · t11 | control plane |  |  | change.rejected cross-team | REJECTED · support.lead has no scope over incident-agent |  |  | aed0abf8a8ed |
| 4 · t12 | control plane |  | v2 | change.published own-scope | PUBLISHED |  |  | d0469f2c0541 |
| 5 · t13 | control plane |  |  | change.rejected widen-alone | REJECTED · a widening change needs a second approver |  |  | fa0cdfc812a1 |
| 6 · t14 | control plane |  |  | change.rejected widen-self-approved | REJECTED · the second approver must be a different person |  |  | 0ecebcee2104 |
| 7 · t15 | control plane |  |  | change.rejected glass-widen | REJECTED · a break-glass change may only restrict behaviour |  |  | ff7b6fae9f60 |
| 8 · t16 | control plane |  |  | change.rejected plaintext-cred | REJECTED · invalid desired state: tool restart_service: credential must be a secret:// reference, never a value |  |  | 0698d074c6b4 |
| 9 · t17 | control plane |  | v3 | change.published suspend-incident-agent | PUBLISHED |  |  | bcb87d04386c |
| 10 · t18 | control plane |  |  | change.rejected restore-incident-agent | REJECTED · a widening change needs a second approver |  |  | e412d4eb18d4 |
| 11 · t19 | control plane |  | v4 | change.published restore-incident-agent | PUBLISHED |  |  | 0488748c3181 |

**Measures**

| Measure | Value |
|---|---|
| attempts | `10` |
| accepted | `3` |
| rejected | `7` |
| changelog_rows | `11` |
| versions | `4` |
| agent_self_grant | `rejected` |
| cross_team_change | `rejected` |
| own_scope_restriction | `accepted` |
| widening_alone | `rejected` |
| self_approval | `rejected` |
| break_glass_widening | `rejected` |
| plaintext_credential | `rejected` |
| break_glass_suspension | `accepted` |
| restore_with_second_person | `accepted` |
| changelog_verifies | `yes` |
| tampered_changelog_verifies | `no` |

**Assertions** (13/13)

| Assertion | Result |
|---|---|
| an agent cannot change the control plane (not an administrator) | pass |
| scope: a team lead cannot change another team's agent | pass |
| scope: a team lead may restrict its own agent alone | pass |
| two-person rule: a widening change needs a second approver | pass |
| two-person rule: the second approver must be a different person | pass |
| break-glass may only restrict | pass |
| validation: a plaintext credential never becomes a version | pass |
| break-glass suspension accepted from one on-call person | pass |
| restoring (widening) needs a second person | pass |
| every attempt is on the change log, accepted or rejected | pass |
| the change log is hash-chained and verifies | pass |
| editing one change-log row breaks the chain | pass |
| every version is signed; no bundle contains a plaintext credential | pass |

**Proof card**

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P12 — GOVERNING THE CONTROL PLANE ITSELF                                       │
├────────────────────────────────────────────────────────────────────────────────┤
│ incident-agent     grant itself delete_resource → REJECTED · incident-agent is │
│                    not a control-plane administrator                           │
│ support.lead       raise incident-agent's tool quota → REJECTED · support.lead │
│                    has no scope over incident-agent                            │
│ support.lead       lower support-agent's tool quota (own scope) → ACCEPTED ·   │
│                    v2                                                          │
│ platform.admin     widen incident-agent's tools alone → REJECTED · a widening  │
│                    change needs a second approver                              │
│ platform.admin     platform.admin as its own second approver → REJECTED · the  │
│                    second approver must be a different person                  │
│ oncall.ic          raise a quota via break-glass → REJECTED · a break-glass    │
│                    change may only restrict behaviour                          │
│ platform.admin     a plaintext credential in the registry (with sre.lead) →    │
│                    REJECTED · tool restart_service: credential must be a       │
│                    secret:// reference, never a value                          │
│ oncall.ic          suspend incident-agent (break-glass) → ACCEPTED · v3        │
│ oncall.ic          restore incident-agent alone → REJECTED · a widening change │
│                    needs a second approver                                     │
│ oncall.ic          restore incident-agent with sre.lead → ACCEPTED · v4        │
│ Change log         11 rows, hash-chained · verifies; one edited row → chain    │
│                    broken · tamper-evident local log under POC assumptions     │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ an agent cannot change the control plane (not an administrator)
  ✓ scope: a team lead cannot change another team's agent
  ✓ scope: a team lead may restrict its own agent alone
  ✓ two-person rule: a widening change needs a second approver
  ✓ two-person rule: the second approver must be a different person
  ✓ break-glass may only restrict
  ✓ validation: a plaintext credential never becomes a version
  ✓ break-glass suspension accepted from one on-call person
  ✓ restoring (widening) needs a second person
  ✓ every attempt is on the change log, accepted or rejected
  ✓ the change log is hash-chained and verifies
  ✓ editing one change-log row breaks the chain
  ✓ every version is signed; no bundle contains a plaintext credential

  PROOF P12: PASS
  Test assertions: 13/13 passed
```

## Reproduce

```bash
make verify       # rerun every proof from source; identical to this run (process ids masked)
make evidence     # PROOF VERIFICATION of the published run
make verify-all   # the final gate
make console      # the Lab Console
```

---

**Series.** Foundation: [F1 · MCP Tool Sprawl](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html) · [F2 · Layered Architecture](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html) · [F3 · Headless AI](../../headless_ai/medium/headless-ai-medium.html) · Trust: [T1 · Agent Identity](../../agent_identity/medium/agent-identity-medium.html) · [T2 · Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · Previous: [T3 · Human-in-the-Loop](../../human_in_the_loop/medium/human-in-the-loop-medium.html) · Current: T4 · AI Control Plane · Next: [T5 · Observability & Governance](../../governance_for_ai_agents/medium/observability-governance-medium.html). Companions: [Medium edition](../medium/ai-control-plane-medium.md) · [Technical deep dive](../technical/ai-control-plane-technical.md) · [Evidence Check](../results/ai-control-plane-evidence.md). Every measured number is substituted from `control_plane_poc/runs/2026-10-03-recorded/facts.json`.
