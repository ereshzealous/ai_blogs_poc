# T1 · Agent Identity · Results

*When an agent acts, whose authority is actually being used?*

Production AI Engineering · T1 · Trust & Security

## The run

- **Published run:** `2026-10-03-recorded` (declared in `agent_identity_poc/runs/PUBLISHED`)
- **How it ran:** deterministic run
- **Numbers come from:** `agent_identity_poc/runs/2026-10-03-recorded/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** not recorded as a separate verdict. Run the verify command below.
- **Findings:** no separate findings verdict: all 41 checks passed. Source: `agent_identity_poc/runs/2026-10-03-recorded/checks.json`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `checks.experiment` | **30** | `checks.json` |
| `checks.global` | **11** | `checks.json` |
| `i1.shared_sa.platform_answers` | **3** | `I1.json` |
| `i1.impersonation.platform_answers` | **4** | `I1.json` |
| `i1.chain.platform_answers` | **9** | `I1.json` |
| `i1.questions` | **9** | `I1.json` |
| `i1.shared_sa.tool_log_answers` | **2** | `I1.json` |
| `i1.shared_sa.tool_principal` | **system:serviceaccount:platform:ai-automation** | `I1.json` |
| `i1.impersonation.tool_log_answers` | **3** | `I1.json` |
| `i1.impersonation.tool_principal` | **maya@company.com** | `I1.json` |
| `i1.chain.tool_log_answers` | **2** | `I1.json` |
| `i1.chain.tool_principal` | **system:serviceaccount:payments:incident-remediator** | `I1.json` |
| `i2.chain.first_decision` | **DENY** | `I2.json` |
| `i2.chain.rollbacks` | **0** | `I2.json` |
| `i2.shared_sa.approver_saw` | **agent.incident-intel** | `I2.json` |
| `i1.shared_sa.k8s_actions` | **5** | `I1.json` |
| `i1.shared_sa.k8s_principals` | **1** | `I1.json` |
| `i6.shared_account_permissions` | **20** | `I6.json` |
| `i6.excess_permissions` | **14** | `I6.json` |
| `i3.shared_sa.affected` | **5** | `I3.json` |
| `i3.executions` | **5** | `I3.json` |
| `i5.fields_lost` | **13** | `I5.json` |
| `i5.impersonation.permissions` | **5** | `I5.json` |
| `i5.chain.permissions` | **3** | `I5.json` |
| `i3.token_ttl_min` | **15** | `I3.json` |
| `i3.delegation.affected` | **2** | `I3.json` |
| `i3.delegation.max_minutes` | **10** | `I3.json` |
| `i3.invoker_credential.affected` | **1** | `I3.json` |
| `i3.invoker_credential.max_minutes` | **10** | `I3.json` |
| `i3.agent.affected` | **4** | `I3.json` |
| `i3.workload.affected` | **4** | `I3.json` |
| `i3.tool_identity.affected` | **1** | `I3.json` |
| `i7.pause_min` | **37** | `I7.json` |
| `i7.revoked_at_min` | **10** | `I7.json` |
| `i7.chain_reexchange.final` | **REJECTED** | `I7.json` |
| `i7.chain_extend.rollbacks` | **1** | `I7.json` |
| `i4.write_replay_status` | **REJECTED** | `I4.json` |
| `i4.write_replay_rollbacks` | **0** | `I4.json` |
| `i4.write_replay_legit_after` | **EXECUTED** | `I4.json` |
| `i4.wrong_audience_status` | **401** | `I4.json` |
| `i4.shared_secret_day_later_status` | **200** | `I4.json` |
| `i6.permissions_the_platform_needs` | **6** | `I6.json` |
| `i6.max_permissions_per_tool_identity` | **3** | `I6.json` |
| `checks.passed` | **41** | `checks.json` |
| `checks.total` | **41** | `checks.json` |
| `checks.failed` | **0** | `checks.json` |
| `i4.stolen_within_ttl_status` | **200** | `I4.json` |
| `i4.tool_credential_ttl_min` | **10** | `I4.json` |
| `i4.stolen_after_ttl_status` | **401** | `I4.json` |
| `i5.platform_record_fields` | **26** | `I5.json` |
| `i1.chain.credential_ttl_min` | **10** | `I1.json` |

## The checks

Source: `agent_identity_poc/runs/2026-10-03-recorded/checks.json`. PASS: 41

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `I1-01` | I1 | ABC · invariant · the rollback executed once in every mode | PASS |  |
| `I1-02` | I1 | C · invariant · chain: the platform record answers all nine questions | PASS |  |
| `I1-03` | I1 | ABC · invariant · every mode: the tool log answers at most three | PASS |  |
| `I1-04` | I1 | A · control · shared account: Kubernetes sees one principal for three agents | PASS |  |
| `I1-05` | I1 | A · control · shared account: no agent attributable from the platform record | PASS |  |
| `I1-06` | I1 | C · invariant · chain: all three agents attributable from the platform record | PASS |  |
| `I1-07` | I1 | C · invariant · audit chain intact; an edited approver breaks it at that row | PASS |  |
| `I2-01` | I2 | C · invariant · chain: the deputy request is denied before any approval | PASS |  |
| `I2-02` | I2 | C · invariant · chain: the callee's scopes narrowed | PASS |  |
| `I2-03` | I2 | C · invariant · chain: an undeclared agent -> agent edge is refused | PASS |  |
| `I2-04` | I2 | A · control · shared account: the deputy rollback executes and hides its originator | PASS |  |
| `I3-01` | I3 | C · invariant · control: nothing stops without a revocation | PASS |  |
| `I3-02` | I3 | C · qualified · delegation: only Maya's executions stop, within one token lifetime | PASS |  |
| `I3-03` | I3 | C · invariant · invoker credential: new executions from that head refused | PASS |  |
| `I3-04` | I3 | C · invariant · agent: every execution running that agent stops at its next call | PASS |  |
| `I3-05` | I3 | C · invariant · workload: executions on the other runtime keep running | PASS |  |
| `I3-06` | I3 | C · invariant · tool identity: one capability of one execution stops | PASS |  |
| `I3-07` | I3 | A · control · shared account rotation stops all five executions | PASS |  |
| `I4-01` | I4 | C · invariant · execution token replayed from another workload is rejected | PASS |  |
| `I4-02` | I4 | C · invariant · privileged write replayed from another workload is rejected with no side effect | PASS |  |
| `I4-03` | I4 | C · invariant · expired execution token is rejected | PASS |  |
| `I4-04` | I4 | C · invariant · tool credential rejected by a system it was not minted for | PASS |  |
| `I4-05` | I4 | C · qualified · stolen tool credential dies with its ten minutes | PASS |  |
| `I4-06` | I4 | A · control · shared secret still works from anywhere a day later | PASS |  |
| `I5-01` | I5 | B · control · impersonation: agent action identical to Maya's own in Kubernetes' log | PASS |  |
| `I5-02` | I5 | C · invariant · delegation: agent action distinguishable from Maya's own | PASS |  |
| `I5-03` | I5 | BC · invariant · impersonation loses the agent and the actor chain | PASS |  |
| `I6-01` | I6 | AC · invariant · shared account holds more than any tool identity | PASS |  |
| `I7-01` | I7 | C · invariant · re-exchange after the pause: revoked delegation stays revoked | PASS |  |
| `I7-02` | I7 | C · control · extending instead of re-exchanging lets the rollback through | PASS |  |
| `G01` | GA | C · invariant · delegation never widens authority (the callee's scopes are within the caller's after every hop) | PASS |  |
| `G02` | GA | C · invariant · a delegated write whose originator lacks the authority is denied, not silently executed | PASS |  |
| `G03` | GA | C · invariant · a credential replayed from the wrong workload causes no privileged side effect | PASS |  |
| `G04` | GA | C · invariant · a revoked identity cannot mint new execution authority | PASS |  |
| `G05` | GA | C · invariant · unrelated executions survive every targeted revocation | PASS |  |
| `G06` | GA | AC · invariant · rotating the shared account stops more executions than any targeted lever | PASS |  |
| `G07` | GA | C · invariant · agent identity and runtime identity stay distinct in the record | PASS |  |
| `G08` | GA | C · invariant · impersonation does not pass for delegation provenance | PASS |  |
| `G09` | GA | ABC · invariant · no tool log is complete upstream provenance (every tool log answers fewer than nine questions) | PASS |  |
| `G10` | GA | C · invariant · the platform record reconstructs the whole identity chain (nine of nine) | PASS |  |
| `G11` | GA | C · invariant · tampering with the platform audit is detected at the edited row | PASS |  |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python 3.12, pydantic, pyyaml, pytest)
make test    # POC tests (no model, no network)
make verify    # rerun the experiments into a fresh copy of the POC and compare with the published run, byte for byte
make replay    # the same as make verify: the experiments rerun in a fresh copy of the POC and compared byte for byte
make demo    # the 14:09 rollback, with every identity in the chain printed
make docs    # both editions and the three evidence documents (results/) as Markdown, standalone HTML and PDF
make qa    # rendered checks at desktop/tablet/mobile + screenshots -> qa/
```

## More detail

- [The technical deep dive (PDF)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/agent_identity_poc/technical/agent-identity-technical.pdf)
- [Evidence](https://github.com/ereshzealous/ai_blogs_poc/blob/main/agent_identity_poc/results/agent-identity-evidence.md)
- [Report](https://github.com/ereshzealous/ai_blogs_poc/blob/main/agent_identity_poc/results/agent-identity-report.md)
- [Real vs simulated](https://github.com/ereshzealous/ai_blogs_poc/blob/main/agent_identity_poc/results/agent-identity-real-vs-simulated.md)
- [Lab (an HTML page: open results/lab-console.html after cloning)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/agent_identity_poc/results/lab-console.html)

*Built by `series-start-here/tools/series_edition.py results T1` from the files named above. It computes nothing new.*
