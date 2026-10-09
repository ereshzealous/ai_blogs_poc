The first negative control (2026-09-30), kept unchanged. It was run by hand in a scratch copy with the same mutation as
`../mutation.diff`. Its failures were real (the proof exited 1) but seven of its eight failed experiments stopped on an
exception (`IndexError`, `KeyError`, `APPROVAL_UNKNOWN`) where the harness expected approval evidence that no longer
existed, instead of reporting an assertion. The harness now reads that evidence defensively, and `negative_control.py`
reproduces the control; its evidence is one folder up.
