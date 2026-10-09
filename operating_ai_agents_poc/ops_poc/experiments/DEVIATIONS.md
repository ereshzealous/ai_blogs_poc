# Deviations and the pre-freeze design log

The preregistration was frozen on the date in `FROZEN.at`, before the recorded run. A change **after** the freeze is a
deviation and is listed under "After the freeze", beside the as-recorded result. Changes made **before** the freeze,
after a development run, are not deviations, but they are listed here because they were informed by development output.

## Before the freeze (development run D1, `runs/dev-1`, deleted after the freeze)

| # | What changed | Why | Effect on the claims |
|---|---|---|---|
| P1 | E4's calibration and blind samples gained 30 finance reconciliation checks each | bug: without them `recon-check` had no envelope, so E9's invariant "every workflow type has an enforceable envelope" failed for **every** release, R41 included, and E10's canary could never receive traffic | E9 and E10 became testable; no threshold changed |
| P2 | `release.artifacts_changed` names a tool by its full name | bug: `orders.lookup` was split at its dot and reported as `tools.orders` | E8's diff text only |
| P3 | E7 gained a third arm, `composed` (gateway + E2's fair scheduling), and two statements in H7 | D1 showed the gateway on a single FIFO queue protecting the API while support goodput collapsed: finance workflows held every runtime slot while they waited at the gateway. The original two arms stay; the third shows the controls composing | adds a result; removes none |
| P4 | E10's controller compares candidate and baseline per workflow type, weighted by the baseline's mix; the raw comparison is kept as a third analysis (`R42-e:raw`) with one statement in H10 | D1's raw controller rolled back the clean R42-e: a 60-workflow window happened to hold more refund disputes than the baseline did | the raw controller's false rollback becomes a recorded result instead of being hidden |
| P5 | E10's last stage (100 %) is the promotion itself; a window is evaluated only once the baseline has at least one window of completions in the same period | D1: at 100 % there is no baseline left to compare against, and at 50 % a fixed comparison period could never fill | none |
| P6 | E4's child (sub-agent) envelope is calibrated from recorded child rows, like every other workflow type | a hand-typed child envelope was replaced by the calibration rule | none |

No hypothesis threshold, gate threshold or guardrail was changed after D1.

## After the freeze

| # | What changed | Why | Effect on the claims |
|---|---|---|---|
| A1 | `agentops/run.py` (aggregation): two list facts (`e4.<arm>.legit_cut_ids`, `…_reasons`) are stored as text; `agentops/cli.py`: a display format | the proof kit's formatter cannot print an empty list (no workflow was cut in the no-budget arm) | none: no frozen file changed, and the run was re-recorded from the same frozen inputs (it is deterministic); the raw scenario files are byte-identical to the first recording, only `manifest.json` (source hashes) and `facts.json` differ, which `make replay` and `make verify` check against the current source |
| A2 | `proof/experiments.toml`: OPS-E8-C04 reclassified from *hypothesis* to *implementation*; claim OPS-C08's statement reworded | independent review: the check reads a behaviour the scripted agent is declared to have (it follows tool descriptions literally), so it cannot fail and is not a hypothesis. The preregistration's H8 statement is unchanged; the editions now say that the size of R42-a's effect is a modelling assumption | the proof pack's counts are unchanged (it still passes, now as an implementation check); no run file changed |

