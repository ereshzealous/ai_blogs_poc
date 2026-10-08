# Deviations from the preregistration

Each entry: D<n> · When (before/after the blind run) · What · Why · Effect on the as-recorded numbers.
Observations that are not deviations are listed separately at the end.

D1 · after the blind run, before publication · `coord/analysis.py` (post-hoc tooling, not frozen) first computed the E6
measure for H6 as "gateway calls of the same write that returned ok". That is not the preregistered measure: H6's test
counts **world executions** (physical side effects), and an idempotent replay also returns ok at the gateway. The
analysis was corrected to the preregistered measure before any edition used it. Both numbers are published
(`e6.*.max_executions_same_write` = world executions; `e6.*.gateway_ok_writes_max` = gateway calls returning ok). No
system-under-test file, label, prompt or limit changed (`coord.freeze check` passes).

D2 · found after the blind run · the model provider (`coord/models.py`, copied from F2, frozen) retries an HTTP error up
to three times inside one model call. The preregistration says a model error is "never silently retried". One call
(B6-C-r1, diagnosis agent) got an HTTP 500 on its first attempt and a valid answer on its second, so it counted as one
successful call; that is the 16th HTTP 500 on the tape. The five calls that failed all three attempts are counted as
failures (O1). Effect on the as-recorded numbers: none for E1's success counts (the retried call succeeded and the
workflow continued), but the retry is disclosed here rather than hidden.

D3 · after the blind run and publication review, a post-run code fix · `coord/arch_c.py`, `config/limits.yaml`. The
blind run found a fail-open fallback (O5): when the coordinator authorized an execution without handing the remediation
agent a `remediation_proposal` artifact, the runtime minted a token with **every** eligible write scope. The post-run
correction changed it to fail closed: such a delegation is now refused before any token is minted or agent called
(step `execute_refused`, an error returned to the coordinator), and without a proposal no write scope is ever granted.
Regression tests: `tests/test_runtime.py::test_execute_without_a_proposal_is_refused_fail_closed` and
`::test_scopes_without_a_proposal_never_include_a_write`. The as-run behaviour is kept behind
`multi_agent_c.execute_without_proposal: all_writes` for one purpose only, replaying runs recorded before the fix; the
default is `deny`. Effect on the as-recorded numbers: none. Every published number comes from the code as it ran; the
as-run files are kept in `experiments/as-run/` and still hash to `FROZEN.sha256`; the changed digests are in
`experiments/POST-RUN-CHANGES.sha256`; the blind run replays identically from its tape with `all_writes`
(`runs/2026-10-08-blind/replay/`). Positive control (`../verification/d3-control.txt`, at the package root): replaying B1-C-r1 alone under
the new default follows the tape through six delegations and refuses the seventh, the authorized execution that was
handed only a diagnosis artifact; the coordinator's next request is then not on the tape. As run, B1-C-r1 executed the
correct rollback and **is one of C's recorded successes**. Under the fixed code that execution would have been refused;
whether the coordinator would then have passed the proposal and still succeeded was not measured, so C's count under
the fixed code is unknown: between one fewer and unchanged.

## Observations (not deviations)

- O1 · E1: four architecture-C runs ended FAILED when the coordinator emitted a `delegate` call whose arguments the model
  server could not parse (HTTP 500 "error parsing tool call": prose, markdown or a truncated object in place of JSON);
  one more call, at the diagnosis agent (B4-C-r2), failed the same way and failed its delegation without ending the run.
  Each of these five calls failed after the provider's three HTTP attempts (15 of the tape's 16 HTTP 500 responses); the
  retries resend the identical request, and in two runs (B5-C-r1, B6-C-r1) a retry returned a different but still
  unparsable output. Recorded as failures, never re-run by the harness.
- O2 · E1: one architecture-B run (B7, repeat 2) ended FAILED when the workflow executed the planner's rollback to a
  release id that does not exist (schema-valid arguments, invalid value); the system of record refused it.
- O3 · E6: in K2 repeat 3 the same model-server error ended the run before any write, so the kill never fired; K2
  therefore has two runs where the kill fired, not three.
- O4 · E6: every run where a process was killed has a trace with orphaned spans (the killed process's open spans never
  end, so they are never exported); the trace is still correlated by its id across all processes.
- O5 · C's execute delegations: the runtime narrows an authorized execution to the write scope of the proposal artifact it
  is handed; when the coordinator authorized execution without passing a proposal, it fell back to every eligible write
  scope. That happened in 1 of 16 execute delegations in E1 (B1-C-r1) and in E8. Policy, approval and the gateway still
  applied. The fallback was a design gap, fixed after the run to fail closed (D3); the editions state both.
- O6 · H9's text says "no hop limit, no cycle check, no budget"; E8 as defined in `[experiments]` (and as run) tripled the
  budget instead of removing it, and kept the 900 s deadline and the coordinator's own turn cap. E8 ran as defined in
  `[experiments]`; the editions describe what was removed and what stayed.
- O7 · the POC's `GetTask` and `CancelTask` calls carry no `Authorization` header and the agent server does not check one
  on them (only task execution is authenticated). A2A v1.0.1 §7.4 says the server MUST authenticate every incoming
  request; recorded as a protocol deviation in `research/a2a-notes.md`.

