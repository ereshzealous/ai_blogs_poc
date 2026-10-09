# Run notes · 2026-10-07-recorded

- The recording (`python -m recovery.run record --run-id 2026-10-07-recorded --live`, log in `../record-2026-10-07.log`)
  completed every deterministic experiment and all 96 real-model calls, then stopped in the slice **scorer**: a response
  that failed to parse returned its score without the `correct` field (`KeyError: 'correct'`).
- Fix: `recovery/modelslice.py` `score_row` initialises `correct = False`. No recorded file changed: the slice was
  re-scored from its tape (`python -m recovery.run score-slice --run-id 2026-10-07-recorded`), no model was called again,
  and `manifest.json` was written afterwards, so its source hashes include the fixed scorer.
- After the run, invariant I7's evaluator was corrected (DEVIATIONS.md D3) and every `eval.json` recomputed from the recorded files with `python -m recovery.run reevaluate`; no worker, provider or model was run again.
- After the run, `recovery/` gained the live-model mode (world.live_decide, runtime --live, harness live=, run record-live). `python3 tools/verify_run.py` re-ran this published run with the new source: 1,958 files byte-identical, so the addition changes no recorded behaviour.
