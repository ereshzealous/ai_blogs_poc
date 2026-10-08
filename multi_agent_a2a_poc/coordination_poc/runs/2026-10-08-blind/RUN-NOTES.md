# Run notes · 2026-10-08-blind (E1) and companions

- **E1** `2026-10-08-blind`: 8 blind fixtures × A, B, C × repeats 1–3 (seeds 7, 11, 13), live `gpt-oss:20b`, strictly
  serial, architecture order rotated per (fixture, repeat). 72 rows, no runner crash, no anomaly re-run.
  Frozen inputs checked before and after (`coord.freeze check`: OK, 51 files, frozen 2026-10-08T01:38:01+0530).
- **E6** `2026-10-08-e6`: K1, K2, K2-neg × 3 on B1 (INC-4917), architecture C. K2 repeat 3 ended before any write
  (model-server error), so its kill never fired.
- **E7** `2026-10-08-e7`: 100 delegations per mode, interleaved, scripted model (`summary.json`).
- **E8** `2026-10-08-e8`: B1–B8 × C, seed 7, limits `{"ablation": true, "workflow": {"max_total_tokens": 600000}}`.
- **Replay**: E1 re-executed from `tape/` with no model → `replay/verification.json`: REPLAY IDENTICAL (72 of 72).

Anomalies and the one analysis correction are listed in `experiments/DEVIATIONS.md` (D1, O1–O4). Every number in the
editions comes from `facts.json` (`coord/analysis.py`); `SHA256SUMS` fixes the files it was computed from.

## Post-publication additions (2026-10-08)

- `facts.json` gained 29 descriptive incident-level facts (`e1.incidents`, `inc.*`: per-incident comparisons between
  architectures) after a review asked for a per-incident view; `coord/analysis.py` (post-hoc, not frozen) computes
  them from the same `rows.jsonl`. All 358 earlier facts are byte-identical; `SHA256SUMS` was updated for `facts.json`
  only.
- `replay/` was regenerated under the fail-closed fix of DEVIATIONS D3 with
  `--overrides '{"multi_agent_c": {"execute_without_proposal": "all_writes"}}'` (the as-run behaviour):
  REPLAY IDENTICAL, 72 of 72. The positive control under the new default is in `../verification/d3-control.txt` (package root).
