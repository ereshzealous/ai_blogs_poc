# Run 2026-09-17-recorded

Generated 2026-09-17 16:33 UTC from the files in `runs/2026-09-17-recorded/`. Open `report/index.html` for everything.

## Stages

| Stage | Duration | Result |
|---|---|---|
| tests | 316 s | OK |
| faults | 74 s | OK |
| crash | 71 s | OK |
| monolith | 108 s | OK |
| workflow | 374 s | OK |
| change | 1 s | OK |
| export | 0 s | OK |

## Tests

- 33 passed (29 fast, 4 against local models)

## Platform runs

| Model | Completed | All 8 checks | Median to approval | Median after approval | Median tokens | Model calls |
|---|---|---|---|---|---|---|
| gpt-oss:20b | 3/3 | 3/3 | 44.5 s | 4.9 s | 24,002 | 12 |
| qwen3:8b | 3/3 | 3/3 | 68.1 s | 3.9 s | 15,131 | 7 |

- Remediation answers repaired after failing validation: 4 of 6 runs.

## Crash and resume

- 3 processes; status after the first kill `WAITING_APPROVAL`; final `COMPLETED`.
- Backend rollbacks: 1; remediation replayed: true.
- Tokens before the first kill: 18,231; after it: 912.

## Faults

- Lost rollback response: 2 attempts, backend executions 1, replays 1.
- Latency read succeeded on attempt 3. Workflow COMPLETED, evals 8/8.

## Monolith

- 3 runs: median 24.7 s and 14,614 tokens; direct Kubernetes rollbacks: 0.
- Lost rollback response: 2 rollbacks executed.
- SIGKILL while waiting: 13.4 s into the run; state left behind: none.

## Requirement changes

| Change | Monolith | Layered |
|---|---|---|
| Add a Teams-style chat channel | 3 files, +63/−14, channel, session, workflow, prompt | 3 files, +60/−0, channel, config |
| Swap gpt-oss:20b for qwen3:8b | 2 files, +6/−3, model, reasoning, channel | 1 files, +1/−1, config |
| Change freeze needs a change manager | 3 files, +24/−11, policy, workflow, channel | 2 files, +6/−0, policy, config |
