# Run notes · 2026-10-07-live (real-model end-to-end)

- Recorded with `python -m recovery.run record-live --run-id 2026-10-07-live` (log: `../record-2026-10-07-live.log`):
  every scenario × runtime with **qwen3:8b** making the decision step through Ollama (temperature 0, seed 1, JSON mode),
  **llama3.1:latest** as the fallback model. Faults, providers, crashes and the recovery layer are those of the published
  run; only the model is real.
- Every model answer is in `scenarios/<S>/<arm>/model-tape.jsonl` with the prompt's hash. Runs without a tape made no
  model call (S02 under A0 and A1: the model was down for the whole run and those runtimes have no fallback).
- Replay: `python3 tools/verify_live.py --record` re-executes every run from the tapes in a scratch copy, with no model,
  and compares the files byte for byte (`evidence/runs/2026-10-07-live/replay.json`).
- The oracle in `experiments/scenarios.toml` was written for the scripted model; this run is evaluated against the same
  oracle, so a decision difference caused by the real model would show as an RE1 miss (`facts.json → A2.re1_miss_list`).
- Run ids and trace ids are derived from the scenario and the runtime, so they are the same strings as in the published run `2026-10-07-recorded`; the run directory is what distinguishes the two runs.
