| # | Time | Agent proposes | Environment | Evidence | Decision | Why (audit view) |
|---|---|---|---|---|---|---|
| 1 | 14:03 | `kubernetes.readDeployment` payment-service | production | – | **ALLOW** | incident-responder permits kubernetes.readDeployment |
| 2 | 14:03 | `kubernetes.readPods` payment-service | production | – | **ALLOW** | incident-responder permits kubernetes.readPods |
| 3 | 14:04 | `logs.query` payment-service | production | – | **ALLOW_WITH_CONSTRAINTS** | Restricted logs are returned redacted |
| 4 | 14:04 | `kubernetes.deleteNamespace` payments-canary | production | – | **DENY** | No role held by incident-agent-prod grants kubernetes.deleteNamespace; sre-team has not delegated kubernetes.deleteNamespace to incident-agent-prod; Namespace deletion is never delegated to agents |
| 5 | 14:05 | `kubernetes.rollbackDeployment` payment-service | production | 0.62 | **DENY** | High-risk production writes need a diagnosis evidence score of at least 0.80 |
| 6 | 14:05 | `kubernetes.restartPod` payment-service | production | – | **ALLOW_WITH_CONSTRAINTS** | Production restarts are limited to one pod per call |
| 7 | 14:06 | `kubernetes.restartPod` payment-service | staging | – | **ALLOW** | incident-responder permits kubernetes.restartPod |
| 8 | 14:06 | `kubernetes.rollbackDeployment` payment-service | staging | 0.62 | **ALLOW** | incident-responder permits kubernetes.rollbackDeployment |
| 9 | 14:07 | `kubernetes.rollbackDeployment` checkout-service | production | 0 | **DENY** | sre-team does not own checkout-service, so it cannot lend authority over it; High-risk production writes need a diagnosis evidence score of at least 0.80 |
| 10 | 14:07 | `kubernetes.rollbackDeployment` payment-service | production | 0.94 | **ALLOW_WITH_APPROVAL** | Production rollback requires SRE approval |
