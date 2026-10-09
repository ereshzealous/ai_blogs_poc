# T2 · Authorization & Policy · Results

*For every tool call: may this agent do this, on this resource, in this context, on whose authority?*

Production AI Engineering · T2 · Trust & Security

## The run

- **Published run:** `2026-09-29-recorded` (declared in `authz_poc/authz/run.py (RUN_ID)`)
- **How it ran:** deterministic, simulated systems of record
- **Numbers come from:** `authz_poc/runs/2026-09-29-recorded/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. replay PASS, audit chain PASS, deterministic True. Source: `authz_poc/runs/2026-09-29-recorded/verification.json`
- **Findings:** 14 of 14 invariants hold. Source: `authz_poc/runs/2026-09-29-recorded/invariants.json`

## The run's facts (the Medium edition's numbers among them)

The article's numbers are typed into its text and checked against these facts by tools/verify_publication.py.

| Key | Value | Source |
|---|---|---|
| `run_id` | **2026-09-29-recorded** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `policy_version` | **authz-2026-09-29.2** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `tool_calls_proposed` | **10** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `decisions_total` | **11** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `decisions_by_type.ALLOW` | **4** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `decisions_by_type.ALLOW_WITH_CONSTRAINTS` | **2** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `decisions_by_type.DENY` | **3** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `decisions_by_type.ALLOW_WITH_APPROVAL` | **1** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `executed` | **7** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `blocked` | **3** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `credentials_issued` | **7** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `approvals_requested` | **1** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `approvals_rejected` | **1** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `approvals_granted` | **1** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `evidence_weights.release_correlation` | **0.35** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `evidence_weights.error_signature` | **0.27** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `evidence_weights.staging_validation` | **0.22** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `evidence_weights.staging_recovery` | **0.1** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `production_rollback_attempts` | **[{"time": "2026-09-29T14:05:10Z", "evidence": 0.62, "signals": ["release_correlation", "error_signature"], "decision": "** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `audit_records` | **23** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `audit_chain_valid` | **True** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `tamper_detected` | **True** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `sweep_cases` | **8** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `sweep_decisions.ALLOW` | **1** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `sweep_decisions.ALLOW_WITH_APPROVAL` | **2** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `sweep_decisions.DENY` | **5** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `invariants_total` | **14** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `invariants_passed` | **14** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `namespaces_after_run` | **["payments", "payments-canary", "payments-staging"]** | `authz_poc/runs/2026-09-29-recorded/facts.json` |
| `payment_service_production_version` | **v4.17.2** | `authz_poc/runs/2026-09-29-recorded/facts.json` |

## The checks

Source: `authz_poc/runs/2026-09-29-recorded/invariants.json`. PASS: 14

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `AUTHZ-INV-01` |  | Deny by default | PASS |  |
| `AUTHZ-INV-02` |  | Role ceiling cannot be exceeded | PASS |  |
| `AUTHZ-INV-03` |  | Tool access is not action permission | PASS |  |
| `AUTHZ-INV-04` |  | Resource authority is required | PASS |  |
| `AUTHZ-INV-05` |  | Delegation is an intersection, never a union | PASS |  |
| `AUTHZ-INV-06` |  | Delegation scope and lifetime are enforced | PASS |  |
| `AUTHZ-INV-07` |  | Context may restrict, never manufacture authority | PASS |  |
| `AUTHZ-INV-08` |  | Agent assertions never loosen authorization | PASS |  |
| `AUTHZ-INV-09` |  | Missing or unknown security context fails closed | PASS |  |
| `AUTHZ-INV-10` |  | Same identity may produce different contextual decisions | PASS |  |
| `AUTHZ-INV-11` |  | Production rollback cannot silently auto-execute | PASS |  |
| `AUTHZ-INV-12` |  | Approval cannot widen DENY | PASS |  |
| `AUTHZ-INV-13` |  | Authorization is rechecked at time of use | PASS |  |
| `AUTHZ-INV-14` |  | Every decision is reconstructable and replayable | PASS |  |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # nothing to install: authz_poc uses the Python standard library (the docs build uses uv)
make test    # the four test layers, L1 to L4 (L4 replays the run into a temp folder)
make verify    # PROOF VERIFICATION: the deterministic run re-executed in a throwaway copy, byte for byte against the published run
make replay    # the deterministic run re-executed in a throwaway copy of the POC and compared byte for byte with the published run
make demo    # no single-scenario demo here: make replay re-executes the whole recorded run
make docs    # both editions as standalone HTML, the Medium image kit, then the uniform series pages
make qa    # the Medium edition's checks: what Medium cannot show, relative links, stale wording
```

## More detail

- [The technical deep dive (PDF)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/auth_and_policy_poc/authorization-and-policy-for-ai-agents.pdf)
- [Lab (an HTML page: open results/lab-console.html after cloning)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/auth_and_policy_poc/results/lab-console.html)

*Built by `series-start-here/tools/series_edition.py results T2` from the files named above. It computes nothing new.*
