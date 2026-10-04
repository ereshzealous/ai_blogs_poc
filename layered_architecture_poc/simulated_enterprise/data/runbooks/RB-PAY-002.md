# RB-PAY-002 · Payment Gateway authorisation errors

## Symptoms
Card authorisation 5xx above 1 %, p95 above 600 ms.

## Triage
Check the card network status page and the threeds2 feature flags; 3DS2 challenge changes raise latency for EU cards only.

## Remediation
Turn the feature flag off.  Do not roll back payment-gateway without payments-platform on the call.
