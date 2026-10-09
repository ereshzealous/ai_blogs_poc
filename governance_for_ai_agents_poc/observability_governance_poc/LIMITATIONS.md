# Limitations

- The deployment API is simulated. Real controllers are asynchronous, can apply partially, and have eventual-consistency
  windows; "accepted, applied later" and "partial mutation" are named and not tested.
- The evidence store is SQLite with a hash chain; the external witness is a file. T4 in the tamper experiment shows the limit:
  an attacker who controls the anchor too is not detected. Not a recommendation for SQLite, not a regulated audit system.
- One incident, one service, one concurrent execution on another service: a gentle test for timestamp joins. Concurrency that
  would make L0's joins ambiguous was argued, not measured.
- The baseline logging is generous (incident ids everywhere, request ids propagated, a policy decision log with bundle
  revision). Other estates would do worse, or better on specific questions.
- L2's 13/13 is by construction: its schema was designed around the thirteen questions.
- People are scripted and answer in under a second; approval latency and human error are not measured.
- One local model (qwen3:8b), temperature 0 (0.3 in v9), one seed. The drift probe is twenty calls.
- The verifier marks a duplicate rollout (E12b) MITIGATED while recording two mutations; production should alert on it.
- Retention classes are declared, not enforced; no field-level encryption, access control or deletion.
- Nothing here establishes legal or regulatory compliance.
- Not an argument to store every prompt: the POC stores digests only.
