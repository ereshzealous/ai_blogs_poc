# RB-CHK-007 · checkout-api runbook

Owner: checkout-engineering · Tier 1 · SLO p95 ≤ 400 ms · Deployed by the GitOps release pipeline.

## Latency regression after a release
If p95 latency rises within minutes of a checkout-api production release, treat the release as the prime suspect.
Compare production with staging on the same version, read the release diff, and check the orders-db connection pool
(`database.get_connection_pool_stats`). Pool exhaustion shows as `ConnectionPoolTimeoutError` and long `db.pool.acquire` spans.

## Rolling back checkout-api
checkout-api is managed by the GitOps release pipeline. Roll back with `source_control.rollback_release`
(service, environment, target_version = the previous release). Do not use `kubectl rollout undo` or
`kubernetes.rollback_deployment`: the GitOps controller re-applies the desired revision within minutes.
A production rollback needs approval from the incident commander.

## After a rollback
Verify p95 with `observability.query_latency` before updating the incident. Record cause, action and verification.
