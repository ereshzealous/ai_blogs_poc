| Context | Decision | Rule | Reason |
|---|---|---|---|
| staging | **ALLOW** | `-` | incident-responder permits kubernetes.rollbackDeployment |
| production, SEV-1, evidence 0.94 | **ALLOW_WITH_APPROVAL** | `A1-production-rollback` | Production rollback requires SRE approval |
| production, evidence 0.62 (before staging validation) | **DENY** | `F2-insufficient-evidence-high-risk-write` | High-risk production writes need a diagnosis evidence score of at least 0.80 |
| production, SEV-3, during change freeze | **DENY** | `F3-change-freeze` | Change freeze: only SEV-1 remediation may write to production |
| production, SEV-1, during change freeze | **ALLOW_WITH_APPROVAL** | `A1-production-rollback` | Production rollback requires SRE approval |
| production, incident resolved | **DENY** | `rebac.delegation-inactive` | Delegation dlg-sre-incident-2026q4 applies only while an incident on payment-service is open |
| production, no acting-for principal | **DENY** | `rebac.no-principal` | Writes need an acting-for principal; the agent has no write authority of its own |
| production, checkout-service (not owned) | **DENY** | `rebac.not-owner` | sre-team does not own checkout-service, so it cannot lend authority over it |
