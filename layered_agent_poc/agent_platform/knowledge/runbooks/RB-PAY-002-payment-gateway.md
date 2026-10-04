# RB-PAY-002 · payment-gateway runbook

Owner: payments-platform · Tier 1 · SLO p95 ≤ 600 ms.

## Is payment-gateway the cause?
Check payment-gateway's own p95 first. A payment-gateway canary that leaves its p95 flat is unlikely to explain
latency in a caller such as checkout-api. Card-processor incidents show as declines, not as slow checkouts.
