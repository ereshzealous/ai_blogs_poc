# RB-GEN-012 · Rollbacks for pipeline-managed services

## Authoritative rollback path
For every service with `managed_by: gitops-release-pipeline`, the release pipeline is the source of truth for what runs.
The only authoritative rollback is a release rollback (`source_control.rollback_release`). Direct cluster changes
(`kubernetes.rollback_deployment`, `kubectl rollout undo`) are overwritten on the next sync and are blocked by policy.

## Approvals
Production rollbacks are high-risk changes. The platform binds the approval to the exact invocation (service,
environment, target version). Changing any argument needs a new approval.
