# F3 · Headless AI · Results

*How should many consumers use the same AI intelligence safely?*

Production AI Engineering · F3 · Foundation

## The run

- **Published run:** `2026-10-05-recorded` (declared in `headless_ai_poc/runs/PUBLISHED`)
- **How it ran:** deterministic reasoner over simulated systems
- **Numbers come from:** `headless_ai_poc/runs/2026-10-05-recorded/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. 6 of 6 sections pass (manifest, integrity, checks, claims, replay, scan). Source: `headless_ai_poc/runs/verification/2026-10-05-recorded.json`
- **Findings:** no separate findings verdict: all 30 experiment checks passed. Source: `headless_ai_poc/runs/2026-10-05-recorded/checks.json`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `x1.heads` | **8** | `X1.json` |
| `x1.A.native` | **1** | `X1.json` |
| `x1.A.credentials_in_agent_process` | **6** | `X1.json` |
| `x1.alert_invoker_in_B` | **bot.alerts** | `X1.json` |
| `x1.B.bridged` | **7** | `X1.json` |
| `x2.executions_for_investigation` | **1** | `X2.json` |
| `x2.distinct_assessments` | **1** | `X2.json` |
| `x2.incidents_created` | **1** | `X2.json` |
| `x2.rollbacks` | **1** | `X2.json` |
| `x4.refused_attempts` | **4** | `X4.json` |
| `x3.deliveries_same_event` | **3** | `X3.json` |
| `x3.executions` | **1** | `X3.json` |
| `x3.incidents_created` | **1** | `X3.json` |
| `x3.rollbacks` | **1** | `X3.json` |
| `x5.spans` | **28** | `X5.json` |
| `x5.answered` | **7** | `X5.json` |
| `x5.audit_records` | **20** | `X5.json` |
| `x7.heads` | **8** | `X7.json` |
| `x7.systems` | **6** | `X7.json` |
| `x7.per_head` | **48** | `X7.json` |
| `x7.capability_layer` | **6** | `X7.json` |
| `x4.compromised.denied` | **4** | `X4.json` |
| `x4.compromised.proposals` | **5** | `X4.json` |
| `x4.compromised.executed` | **0** | `X4.json` |
| `checks.total` | **30** | `checks.json` |

## The checks

Source: `headless_ai_poc/runs/2026-10-05-recorded/checks.json`. PASS: 30

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `1` | X1 | headless serves every head natively | PASS |  |
| `2` | X1 | headless records the true invoker for every head | PASS |  |
| `3` | X1 | chat-centric serves only chat natively | PASS |  |
| `4` | X1 | layered-chat bridging loses the alert's invoker | PASS |  |
| `5` | X2 | all investigation heads share one execution | PASS |  |
| `6` | X2 | all investigation heads see one assessment | PASS |  |
| `7` | X2 | one incident for eight heads | PASS |  |
| `8` | X2 | sweep reads the same leading hypothesis | PASS |  |
| `9` | X2 | sweep cannot write | PASS |  |
| `10` | X2 | CI and agent consumers block on the same finding | PASS |  |
| `11` | X2 | one rollback after one approval | PASS |  |
| `12` | X3 | duplicate deliveries flagged | PASS |  |
| `13` | X3 | re-fired alert joins the open execution | PASS |  |
| `14` | X3 | one execution, one incident, one rollback | PASS |  |
| `15` | X3 | a replayed approval is refused | PASS |  |
| `16` | X3 | poison messages dead-lettered | PASS |  |
| `17` | X4 | event execution holds no rollback scope | PASS |  |
| `18` | X4 | viewer cannot invoke | PASS |  |
| `19` | X4 | four invalid approvals refused | PASS |  |
| `20` | X4 | no rollback before a valid approval | PASS |  |
| `21` | X4 | audit names the approver and the invoker | PASS |  |
| `22` | X4 | compromised reasoner executes nothing | PASS |  |
| `23` | X5 | audit answers all seven questions | PASS |  |
| `24` | X5 | audit chain intact; tamper detected | PASS |  |
| `25` | X6 | read timeout retried | PASS |  |
| `26` | X6 | lost response: one physical rollback | PASS |  |
| `27` | X6 | crash: no completed step repeated | PASS |  |
| `28` | X6 | approval timeout escalates, changes nothing | PASS |  |
| `29` | X6 | expired token re-exchanged, not extended | PASS |  |
| `30` | X6 | revoked credential rejected at ingress | PASS |  |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python 3.12, pydantic, pyyaml, pytest)
make test    # POC tests (no model, no network)
make verify    # PROOF VERIFICATION of the published run, read-only (hai verify --check; no model)
make replay    # the byte-for-byte replay of the published run in a temp folder (part of hai verify --check; read-only)
make demo    # one monitoring event, end to end
make docs    # both editions as Markdown, standalone HTML and PDF
make qa    # rendered checks at desktop/tablet/mobile + screenshots -> qa/
```

## More detail

- [The technical deep dive (PDF)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/headless_ai_poc/technical/headless-ai-technical.pdf)

*Built by `series-start-here/tools/series_edition.py results F3` from the files named above. It computes nothing new.*
