# Real vs simulated

The published, linked version is `results/agent-identity-real-vs-simulated.html` (built from
`docs/source/real-vs-simulated.src.md`). This is the short form for the POC.

| Real code and logic (exercised by the run) | Simulated (deterministic substitutes) | Not built |
|---|---|---|
| Identity chain representation (subject, actor chain, provenance) · delegation derivation and scope intersection at every hop · execution-token and credential generation · token broker (per capability class, one audience, minutes) · capability gateway · workload-binding and audience checks against replay · revocation levers · approvals bound to one call · hash-chained audit · the three identity models · the 41 declared checks, the freeze and the byte-for-byte replay | Datadog (one monitor event) · the enterprise IdP and directory (`config/principals.yaml`) · workload attestation (SVIDs issued from configuration, no SPIRE) · Kubernetes, Jira, Slack, telemetry and their own logs (`aid/tools.py`) · the approval system's human (scripted) · the clock and human waiting | RFC 8693 wire format · DPoP or mTLS-bound tool credentials · Kubernetes impersonation headers · transaction tokens · token introspection · a commercial authorization platform (the next note) |

The hash-chained audit is tamper-evident application audit, not an independently anchored ledger. The tools authenticate
the edge credential only; no simulated tool understands actor claims.
