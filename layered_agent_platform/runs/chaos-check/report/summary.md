# Run chaos-check

Generated 2026-09-17 16:33 UTC from the files in `runs/chaos-check/`. Open `report/index.html` for everything.

## Stages

| Stage | Duration | Result |
|---|---|---|
| tests | 55 s | OK |
| faults | 60 s | OK |
| crash | 70 s | OK |

## Tests

- 50 passed (50 fast, 0 against local models)

## Crash and resume

- 4 processes; status after the first kill `RUNNING`; final `COMPLETED`.
- Backend rollbacks: 1; remediation replayed: true.
- Tokens before the first kill: 19,468; after it: 2,336.

## Faults

- Lost rollback response: 2 attempts, backend executions 1, replays 1.
- Latency read succeeded on attempt 1. Workflow COMPLETED, evals 8/8.
