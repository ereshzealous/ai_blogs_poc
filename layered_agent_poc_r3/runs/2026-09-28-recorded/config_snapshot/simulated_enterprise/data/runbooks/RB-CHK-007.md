# RB-CHK-007 · Checkout API latency or 5xx in production

## Symptoms
p95 latency of checkout-api above the 400 ms SLO, rising 5xx on POST /v1/checkout, alerts from latency-slo.

## Triage
1. List checkout-api production releases from the last few hours; a release shortly before the alert is the first suspect.
2. Compare latency_p95_ms, error_rate_pct and db_pool_wait_ms.  A high db_pool_wait_ms with flat CPU points at database
   connection-pool exhaustion, not load.
3. Search the logs for "HikariPool" or "connection-acquire-timeout" and check the configured maximumPoolSize.
4. Rule out dependencies: payment-gateway and inventory-api latency should be within their SLOs.

## Remediation
- If a recent release changed the pool or the ORM and the symptoms match, roll back checkout-api to the release that ran
  before it.  A production rollback needs approval from the incident commander.
- Do not restart checkout-api: a restart keeps the bad pool configuration and drops in-flight payments.
- Do not scale checkout-api up: more replicas multiply connections against orders-db, which is capped.

## Verification
The mitigation holds when latency_p95_ms has been below 400 ms for the last 3 minutes.

## Record
Set the incident to "mitigated" with a note: root cause, action taken, verification result.
