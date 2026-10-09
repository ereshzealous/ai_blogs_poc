# T4 · AI Control Plane · Results

*How do you change what many agents may do without editing or redeploying any of them?*

Production AI Engineering · T4 · Trust & Security

## The run

- **Published run:** `2026-10-03-recorded` (declared in `control_plane_poc/runs/PUBLISHED`)
- **How it ran:** deterministic: agents follow fixed plans, no model
- **Numbers come from:** `control_plane_poc/runs/2026-10-03-recorded/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. 10 of 10 verification sections pass. Source: `evidence/verification/verification.json`
- **Findings:** 21 claims: 13 supported, 4 limitation, 2 contradicted, 1 control, 1 implementation; check findings: 4 EXPECTED FAILURE, 2 LIMITATION OBSERVED. Source: `evidence/runs/2026-10-03-recorded/results.json`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `p2.before_version` | **v1** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P2-C-central-change/scenario.json → measures` |
| `p2.after_version` | **v2** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P2-C-central-change/scenario.json → measures` |
| `p11.embedded.files_edited` | **7** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P11-E-embedded/scenario.json → measures` |
| `p11.embedded.lines_changed` | **17** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P11-E-embedded/scenario.json → measures` |
| `p11.embedded.redeploys` | **7** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P11-E-embedded/scenario.json → measures` |
| `p11.cp.bundle_versions` | **4** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P11-C-control-plane/scenario.json → measures` |
| `p11.cp.files_edited` | **0** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P11-C-control-plane/scenario.json → measures` |
| `p11.cp.redeploys` | **0** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P11-C-control-plane/scenario.json → measures` |
| `p2.agent_sha_before` | **677bca2acd66** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P2-C-central-change/scenario.json → measures` |
| `p2.agent_sha_after` | **677bca2acd66** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P2-C-central-change/scenario.json → measures` |
| `p2.runtime_pid_before` | **rt-a/pid-1** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P2-C-central-change/scenario.json → measures` |
| `p2.request_hash_before` | **cb0531217710** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P2-C-central-change/scenario.json → measures` |
| `p2.restarts_after_v1` | **1** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P2-C-central-change/scenario.json → measures` |
| `p2.restarts_after_v2` | **1** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P2-C-central-change/scenario.json → measures` |
| `p2.acp_files_changed` | **0** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P2-C-central-change/scenario.json → measures` |
| `p2.control_plane_files_changed` | **4** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P2-C-central-change/scenario.json → measures` |
| `p4.inflight_executed_after_suspension` | **0** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P4-C-suspend/scenario.json → measures` |
| `p4.inflight_calls_after_suspension` | **2** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P4-C-suspend/scenario.json → measures` |
| `p5.max_tool_calls` | **2** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P5-C-budgets/scenario.json → measures` |
| `p7.v1_incident_model` | **fast-model** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P7-C-models/scenario.json → measures` |
| `p7.v2_incident_model` | **large-model** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P7-C-models/scenario.json → measures` |
| `p7.model_names_in_agent_code` | **0** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P7-C-models/scenario.json → measures` |
| `p8.canary_percent` | **25** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P8-C-canary/scenario.json → measures` |
| `p8.canary_runs_on_new` | **4** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P8-C-canary/scenario.json → measures` |
| `p8.canary_runs` | **20** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P8-C-canary/scenario.json → measures` |
| `checks.passed` | **100** | `control_plane_poc/runs/2026-10-03-recorded/checks.json` |
| `checks.total` | **100** | `control_plane_poc/runs/2026-10-03-recorded/checks.json` |
| `outcome.held` | **12** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/*/scenario.json → outcome` |
| `outcome.qualified` | **2** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/*/scenario.json → outcome` |
| `outcome.broken` | **1** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/*/scenario.json → outcome` |
| `p12.own_scope_restriction` | **accepted** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P12-C-governing-the-control-plane/scenario.json → measures` |
| `p12.plaintext_credential` | **rejected** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P12-C-governing-the-control-plane/scenario.json → measures` |
| `p12.attempts` | **10** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P12-C-governing-the-control-plane/scenario.json → measures` |
| `p12.accepted` | **3** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P12-C-governing-the-control-plane/scenario.json → measures` |
| `p12.rejected` | **7** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P12-C-governing-the-control-plane/scenario.json → measures` |
| `p9.outage.calls_executed_after_suspension_published` | **3** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P9-C-outage/scenario.json → measures` |
| `p10.drift_findings` | **2** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P10-C-drift/scenario.json → measures` |
| `p10.stale_after_reconcile` | **0** | `control_plane_poc/runs/2026-10-03-recorded/scenarios/P10-C-drift/scenario.json → measures` |
| `run.id` | **2026-10-03-recorded** | `control_plane_poc/runs/2026-10-03-recorded/manifest.json` |

## The checks

Source: `evidence/runs/2026-10-03-recorded/checks.jsonl`. PASS: 73, EXPECTED_FAILURE: 4, FAIL: 2

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `T4-R1-C01` | T4-R1 |  | PASS | PASS |
| `T4-R1-C02` | T4-R1 |  | PASS | PASS |
| `T4-R1-C03` | T4-R1 |  | PASS | PASS |
| `T4-R1-C04` | T4-R1 |  | PASS | PASS |
| `T4-R2-C01` | T4-R2 |  | PASS | PASS |
| `T4-R2-C02` | T4-R2 |  | PASS | PASS |
| `T4-R2-C03` | T4-R2 |  | PASS | PASS |
| `T4-R2-C04` | T4-R2 |  | PASS | PASS |
| `T4-R2-C05` | T4-R2 |  | PASS | PASS |
| `T4-R2-C06` | T4-R2 |  | PASS | PASS |
| `T4-R2-C07` | T4-R2 |  | PASS | PASS |
| `T4-R2-C08` | T4-R2 |  | PASS | PASS |
| `T4-R2-C09` | T4-R2 |  | PASS | PASS |
| `T4-R2-C10` | T4-R2 |  | PASS | PASS |
| `T4-R3-C01` | T4-R3 |  | PASS | PASS |
| `T4-R3-C02` | T4-R3 |  | PASS | PASS |
| `T4-R3-C03` | T4-R3 |  | PASS | PASS |
| `T4-R3-C04` | T4-R3 |  | PASS | PASS |
| `T4-R3-C05` | T4-R3 |  | PASS | PASS |
| `T4-R4-C01` | T4-R4 |  | PASS | PASS |
| `T4-R4-C02` | T4-R4 |  | PASS | PASS |
| `T4-R4-C03` | T4-R4 |  | PASS | PASS |
| `T4-R4-C04` | T4-R4 |  | PASS | PASS |
| `T4-R4-C05` | T4-R4 |  | PASS | PASS |
| `T4-R5-C01` | T4-R5 |  | PASS | PASS |
| `T4-R5-C02` | T4-R5 |  | PASS | PASS |
| `T4-R5-C03` | T4-R5 |  | PASS | PASS |
| `T4-R6-C01` | T4-R6 |  | PASS | PASS |
| `T4-R6-C02` | T4-R6 |  | PASS | PASS |
| `T4-R6-C03` | T4-R6 |  | PASS | PASS |
| `T4-R6-C04` | T4-R6 |  | PASS | PASS |
| `T4-R7-C01` | T4-R7 |  | PASS | PASS |
| `T4-R7-C02` | T4-R7 |  | PASS | PASS |
| `T4-R7-C03` | T4-R7 |  | PASS | PASS |
| `T4-R7-C04` | T4-R7 |  | PASS | PASS |
| `T4-R8-C01` | T4-R8 |  | PASS | PASS |
| `T4-R8-C02` | T4-R8 |  | PASS | PASS |
| `T4-R8-C03` | T4-R8 |  | PASS | PASS |
| `T4-R8-C04` | T4-R8 |  | PASS | PASS |
| `T4-R9-C01` | T4-R9 |  | PASS | PASS |
| `T4-R9-C02` | T4-R9 |  | PASS | PASS |
| `T4-R9-C03` | T4-R9 |  | PASS | PASS |
| `T4-R9-C04` | T4-R9 |  | PASS | PASS |
| `T4-R9-C05` | T4-R9 |  | PASS | PASS |
| `T4-R9-C06` | T4-R9 |  | PASS | PASS |
| `T4-R9-C07` | T4-R9 |  | PASS | PASS |
| `T4-R9-C08` | T4-R9 |  | FAIL | LIMITATION OBSERVED |
| `T4-R10-C01` | T4-R10 |  | PASS | PASS |
| `T4-R10-C02` | T4-R10 |  | PASS | PASS |
| `T4-R10-C03` | T4-R10 |  | PASS | PASS |
| `T4-R10-C04` | T4-R10 |  | PASS | PASS |
| `T4-R10-C05` | T4-R10 |  | FAIL | LIMITATION OBSERVED |
| `T4-R11-C01` | T4-R11 |  | PASS | PASS |
| `T4-R11-C02` | T4-R11 |  | PASS | PASS |
| `T4-R11-C03` | T4-R11 |  | PASS | PASS |
| `T4-R11-C04` | T4-R11 |  | PASS | PASS |
| `T4-R11-C05` | T4-R11 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T4-R11-C06` | T4-R11 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T4-R11-C07` | T4-R11 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T4-R11-C08` | T4-R11 |  | EXPECTED_FAILURE | EXPECTED FAILURE |
| `T4-R12-C01` | T4-R12 |  | PASS | PASS |
| `T4-R12-C02` | T4-R12 |  | PASS | PASS |
| `T4-R12-C03` | T4-R12 |  | PASS | PASS |
| `T4-R12-C04` | T4-R12 |  | PASS | PASS |
| `T4-R12-C05` | T4-R12 |  | PASS | PASS |
| `T4-R12-C06` | T4-R12 |  | PASS | PASS |
| `T4-R12-C07` | T4-R12 |  | PASS | PASS |
| `T4-R12-C08` | T4-R12 |  | PASS | PASS |
| `T4-R12-C09` | T4-R12 |  | PASS | PASS |
| `T4-R12-C10` | T4-R12 |  | PASS | PASS |
| `T4-R12-C11` | T4-R12 |  | PASS | PASS |
| `T4-R13-C01` | T4-R13 |  | PASS | PASS |
| `T4-R13-C02` | T4-R13 |  | PASS | PASS |
| `T4-R13-C03` | T4-R13 |  | PASS | PASS |
| `T4-R13-C04` | T4-R13 |  | PASS | PASS |
| `T4-R13-C05` | T4-R13 |  | PASS | PASS |
| `T4-R13-C06` | T4-R13 |  | PASS | PASS |
| `T4-R13-C07` | T4-R13 |  | PASS | PASS |
| `T4-R13-C08` | T4-R13 |  | PASS | PASS |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python 3.12, pyyaml, pytest, ruff)
make test    # POC tests: architecture (agents hold no governance), decisions, every proof (no model, no network)
make verify    # rerun every proof into a fresh copy of the POC and compare with the published run (pids masked, nothing else)
make replay    # the same as make verify: every proof rerun in a fresh copy of the POC and compared
make demo    # P2 only: one central change, same agent code, same runtime process, different behaviour
make docs    # both editions and the three evidence documents (results/) as Markdown, standalone HTML and PDF
make qa    # rendered checks at desktop/tablet/mobile (editions, evidence documents, Lab Console) + screenshots -> qa/
```

## More detail

- [The technical deep dive (PDF)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/ai_control_plane_poc/technical/ai-control-plane-technical.pdf)
- [Evidence](https://github.com/ereshzealous/ai_blogs_poc/blob/main/ai_control_plane_poc/results/ai-control-plane-evidence.md)
- [Report](https://github.com/ereshzealous/ai_blogs_poc/blob/main/ai_control_plane_poc/results/ai-control-plane-report.md)
- [Real vs simulated](https://github.com/ereshzealous/ai_blogs_poc/blob/main/ai_control_plane_poc/results/ai-control-plane-real-vs-simulated.md)
- [Lab (an HTML page: open results/lab-console.html after cloning)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/ai_control_plane_poc/results/lab-console.html)

*Built by `series-start-here/tools/series_edition.py results T4` from the files named above. It computes nothing new.*
