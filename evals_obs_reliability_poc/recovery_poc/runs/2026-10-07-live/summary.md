# Real-model end-to-end run 2026-10-07-live

75 runs (25 scenarios x 3 runtimes), qwen3:8b deciding, 78 model calls.

| | A0 | A1 | A2 |
|---|---|---|---|
| dup_scenarios | 10 | 5 | 0 |
| outcome_correct | 10 | 14 | 25 |
| false_claims | 1 | 1 | 0 |
| safety_failures | 11 | 6 | 0 |
| unsafe_credits | 0 | 0 | 0 |
| escalations | 0 | 0 | 3 |
| denied | 0 | 0 | 1 |
| trace_split | 4 | 0 | 0 |

A2 decisions equal to the scripted-model oracle: 25 of 25 (differ: none).
