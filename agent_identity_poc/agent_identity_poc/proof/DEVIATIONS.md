# Deviations from the declared criteria

`proof/preregistration.toml`, every config file and the criteria code were frozen with `uv run aid freeze` before the
final recorded run (`proof/FREEZE.json` records when, with every hash). Every change made after the freeze to a guarded
file, or to code that changes what a scenario does, is listed here in order, with its reason.

| # | When (UTC) | What changed | Why | Effect on a check |
|---|---|---|---|---|
| 1 | 2026-10-03T18:25:54Z | `aid/experiments.py` `collected_tests()`: read pytest's per-file `file: N` lines | Before the first run after the freeze, the manifest's test count came out as -1: `pytest --collect-only -q` prints per-file counts, not a total. Manifest metadata only. | None: no check reads it |
