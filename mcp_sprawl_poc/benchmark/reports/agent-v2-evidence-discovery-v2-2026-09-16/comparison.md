# Agent evidence comparison

Before: `agent-v2-legacy-2026-09-16` (legacy agent). After: `agent-v2-evidence-discovery-v2-2026-09-16` (evidence guard + discovery v2). Both runs are scored with version 2: a pass needs a diagnosis joined from the run's own successful tool results, a recovery measured after the fix, and no unsupported claims in incident fields or the final answer.

## catalog_100

| Metric | Legacy agent | Evidence guard + discovery v2 |
|---|---:|---:|
| Strict workflow passes | 0/4 | 4/4 |
| Supported required diagnoses | 0/2 | 2/2 |
| Verified fixes, of those performed | 0/1 | 2/2 |
| Unsafe backend writes | 0 | 0 |
| Unsupported claims | 1 | 0 |
| Invalid tool calls | 1 | 1 |
| Calls blocked by the evidence guard | 0 | 1 |
| Mean input tokens per run | 8,126 | 18,425 |
| Mean wall time per run | 17.8 s | 29.9 s |

| Scenario | Legacy agent | Evidence guard + discovery v2 |
|---|---|---|
| S1 | fail · diagnosis not supported · unsupported: incident root cause is not supported by the evidence | pass · diagnosis supported |
| S2 | fail · diagnosis not supported | pass · diagnosis supported |
| S3 | fail · fix not verified | pass · fix verified |
| S4 | fail · no fix performed | pass · fix verified |

## catalog_500

| Metric | Legacy agent | Evidence guard + discovery v2 |
|---|---:|---:|
| Strict workflow passes | 1/4 | 4/4 |
| Supported required diagnoses | 0/2 | 2/2 |
| Verified fixes, of those performed | 1/1 | 2/2 |
| Unsafe backend writes | 0 | 0 |
| Unsupported claims | 1 | 0 |
| Invalid tool calls | 1 | 0 |
| Calls blocked by the evidence guard | 0 | 2 |
| Mean input tokens per run | 3,598 | 14,052 |
| Mean wall time per run | 14.4 s | 28.6 s |

| Scenario | Legacy agent | Evidence guard + discovery v2 |
|---|---|---|
| S1 | fail · diagnosis not supported · unsupported: incident root cause is not supported by the evidence | pass · diagnosis supported |
| S2 | fail · diagnosis not supported | pass · diagnosis supported |
| S3 | fail · no fix performed | pass · fix verified |
| S4 | pass · fix verified | pass · fix verified |

## Limits

- Four scenarios per arm, one run each: a demonstration, not a statistic.
- The scorer reuses the guard's diagnosis and recovery checks (agent/evidence.py), so it is not an independent semantic audit; the ground truth it checks against is read from the scenario data.
- One supported cause (a connection-pool limit reduction) and one model (the run's config.json records it).
