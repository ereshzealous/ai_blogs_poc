# Deviations from the preregistration

`proof/preregistration.toml` and the checks generated from it (`proof/experiments.toml`) were frozen with
`uv run hitl freeze` before the first run of any H1–H9 scenario (`proof/FREEZE.json` records when, and the hash of every
guarded file). Before the freeze, only the pre-existing arm-C conformance suite (30 regression tests) and the unit tests
had been run, to check the shared approval service and gate after the state names were aligned with the article.

**Freeze record.** The first freeze was written at **2026-10-03T17:45:00Z**, before any H1–H9 scenario ran, with these hashes:
`proof/preregistration.toml` f575e67d867bd0a5…, `proof/experiments.toml` 0a632e4364e2a900…, `config/policy.yaml` c15b1e5a93f8c397…,
`config/policy-v8.yaml` 1b626f48a0d181a9…, `config/principals.yaml` 5cc22667674795878…, `config/capabilities.yaml` 3511137a967fa82c…,
scenario fixture 671b15051992a359…. Deviation 3 renamed check ids, so `proof/experiments.toml` was re-frozen; `proof/FREEZE.json`
holds that re-freeze (its `note` names the first one), and from then on `hitl freeze` keeps every earlier freeze in `history`.
The preregistration itself and every config file kept the hashes above.

Every change made after the freeze to a guarded file, or to code that changes what a scenario does, is listed here with
its reason, in order. A change that only fixes a crash is listed too.

| # | When (UTC) | What changed | Why | Effect on a check |
|---|---|---|---|---|
| 1 | 2026-10-03T17:45:30Z | `hitl/proofpack.py`: the fact builder now also sums each class metric (e.g. `executions_after_deny_or_timeout`) per experiment and arm | The first `hitl proof` stopped with `check H8-A01: unknown fact(s) ['H8.A.executions_after_deny_or_timeout']`: H8's preregistered hypotheses name per-experiment class metrics the builder only computed globally. No scenario, oracle, metric definition or check changed. | None: the facts follow the preregistered metric definitions |
| 2 | 2026-10-03T17:46:14Z | `hitl/gate.py`, `hitl/arms.py`: arm C's gate now checks request binding (the approval presented belongs to the resuming workflow's request) before consuming it | Code review against the preregistered arm definition after the first recorded run: C is B plus revalidation, and B's resume checks request binding; C's gate did not. In that run C refused both cross-workflow replays (H3b, H3c) only because the approval was already consumed; with an unconsumed, unexpired approval and an identical action, C would have accepted it. | None: H3 under C stays at 0 replays; H3b and H3c now stop at REQUEST_MISMATCH instead of APPROVAL_CONSUMED |
| 3 | 2026-10-03T18:17:06Z | `scripts/gen_experiments.py` → `proof/experiments.toml`: experiment and check ids renamed to the pae-proof/v1 id pattern (H<n> → T3-R<n>, GA → T3-R10, CS → T3-R11, API → T3-R12; checks T3-R<n>-C<kk>), each check keeping its readable label (H5-B01) | `hitl verify` rejected the ids `H1`, `H1-C01` against the contract schema (`^[A-Z][0-9]+-R[0-9]+(-C[0-9]{2})?$`). Re-frozen after the rename. | None: the same 79 checks with the same facts, operators, values, kinds and expectations; only ids changed |
