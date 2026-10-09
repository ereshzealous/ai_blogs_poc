# Changes made after the recorded run

The preregistration (`EXPERIMENTS.md`), the scenarios, the policies and every file that defines the experiment are
unchanged since `FROZEN.json` was written. `s1 run --replay` verifies this against `runs/<run-id>/hashes.json`.

| When | File | Change | Can it change a result? |
|---|---|---|---|
| after `2026-09-18-recorded` | `src/s1_experiments/cli.py` | The replay check compared an in-memory summary (tuples) with JSON from disk (lists), so it reported "REPLAY DIFFERS" when the content was identical. It now compares both as JSON and also checks the per-file hashes of experiment-defining files. | No: presentation only |
| after `2026-09-18-recorded` | `src/s1_experiments/freeze.py` | `cli.py`, `report.py` and `freeze.py` were marked as presentation files, so a fix to them does not invalidate a recorded run. | No |

Nothing in the corpus, labels, prompt, authority policy, write rules, gates, ranking, budget, seeds or scorer changed
after the results were seen.
