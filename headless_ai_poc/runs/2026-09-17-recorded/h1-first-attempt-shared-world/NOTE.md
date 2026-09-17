First H1 attempt (kept for the record). The three channels ran against one simulated enterprise without a reset, so
after the CLI run's rollback the REST run investigated an already-fixed system and named the rollback deployment
(DEP-90001) as the suspect; Part 2's `correct_deployment` eval failed (7/8). This was a harness bug, not a channel
effect. The scenario now resets the enterprise before each channel; `../h1/` is the re-run.
