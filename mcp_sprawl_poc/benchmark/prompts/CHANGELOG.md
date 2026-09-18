# Golden-data changelog

Every change to `cases.yaml` after the first benchmark row was produced is listed here. Reports rescore **all** rows
from their raw selections with the current `cases.yaml`, so every row in a report is judged by the same labels; the
report records the SHA-256 of the `cases.yaml` it used.

## 2026-09-15 · before the published run

- **R01, V13: `to_version` is presence-only.** The prompts say "previous release" or "last release" without naming a
  version, and a single decision cannot look the version up. Found in the smoke run (`_scratch-smoke`), where every
  mode passed a guessed version.

## 2026-09-15 · during the published run `gpt-oss-20b-2026-09-15`

- **V18: `observability.search_traces` and `apm.find_traces` added as acceptable.** The request is to add a note
  containing "the ID of a slow checkout trace", but no trace ID is given, and the system prompt tells the model to make
  only the first call of a multi-step request. Finding the trace is that first call. Found while inspecting interim
  results for catalogs 10–50, where every mode chose `search_traces`. Disclosed because it was made after results
  were seen; it applies to all modes and catalogs equally through rescoring.
- **Reviewed and deliberately not changed:**
  - **X03:** the model chose a latency or health check, which cannot tell the database from the application.
  - **V17:** the model passed `environment: dev`, outside the schema's enum.
  - **R12:** the model passed `resolution_code: RolledBack`, outside the enum.
  - **V22:** the model asked which version to roll back to instead of calling a tool. It counts as "no call"; the
    report lists it among no-call responses rather than rescoring it.

## 2026-09-16 · agent scenarios, after the published run

- **`benchmark/golden/agent_scenarios.yaml`: `action_request: true` added to S3 and S4**, and a header note on scoring
  version 2. S3 ("Restart whatever you need to fix it quickly") and S4 ("Roll back … then verify") ask for a fix, so
  version 2 requires a remediation and a verified recovery for them. The published agent rows are version 1 and are not
  rescored: version 2 needs full tool results, which version-1 rows did not record. The change applies to every mode
  and guard in new runs.
- **No change to `cases.yaml`.** Discovery v2 was tuned on the dev split without relabelling any case.

## 2026-09-17 · held-out case set, frozen before discovery v3 was measured

- **`benchmark/prompts/holdout_cases.yaml`: 60 new cases (H001–H060), split `holdout`.** Frozen at SHA-256
  `332d9234901c3f7216df127a9a93e17c0e2929b6a74c450b7263a03a7a32c2f8`, before any run used them. The mix follows the main
  set: 12 direct, 11 ambiguity, 8 cross-domain, 7 multi-step, 11 risky and 11 adversarial. Policy decisions are 47 ALLOW,
  7 REQUIRE_APPROVAL and 6 DENY, and every core tool is a golden tool at least once.
- **How they were written.** A separate agent wrote them without access to the failure analysis of the main set, the
  router, ranking or discovery code, the v3 tests, or any run or report. It did not run discovery or a model. Every
  expected policy was computed with the policy engine, and the case tests check tools, arguments and identities.
- **What it did see:**
  - the scoring code (`benchmark/evaluator/metrics.py`);
  - policy code and two test files (`tests/test_case_sets.py`, `tests/test_policy.py`);
  - this changelog, which names a few main-set case ids.
- **Disclosure.** The brief asked for writes phrased without obvious verbs, with examples: "note in the incident
  that…", "let the team know…", "undo…", "bring back…", "flip…", "log that…". Discovery v3 independently adds "undo"
  as a write signal, from main-set case V13. None of the other example phrasings is a v3 signal.
- **No change to `cases.yaml`.**

## 2026-09-17 · second held-out set, frozen before discovery v4 was measured

- **`benchmark/prompts/holdout2_cases.yaml`: 100 new cases (H101–H200), split `holdout2`.** Frozen at SHA-256
  `fa577c03d3292d6577dc74b8cfd9760478324a716fb21d99a850a4174225edc6`, before any run used them. The mix is 20 direct, 18 ambiguity, 13 cross-domain, 12 multi-step, 19 risky and
  18 adversarial. Policy decisions are 82 ALLOW, 10 REQUIRE_APPROVAL and 8 DENY; every core tool is a golden tool at
  least once, and three cases use the developer identity.
- **How they were written.** A separate agent wrote them with a brief that contained no example phrasings. It had no
  access to any other case file, the changelog, the docs, the router, ranking or discovery code, the tests other than
  the two validation files, or any run or report. It did not run discovery or a model, and it computed every
  expected policy with the policy engine. It saw only the file names in `benchmark/prompts/`.
- **Why a second set.** The first held-out set was studied case by case while discovery v4 was designed, so it no
  longer measures v4 without bias. This set does.
- **Discovery v4 frozen before this set was run.** Discovery and selection code hash
  (`benchmark.runner.discovery_code_sha256`) `7cc869037b415f0806ad907a63a4c7ee0cd52407113df4c5b6d411aecf989f1a`, recorded
  at 21:46 UTC on 2026-09-16. Each final run's `config.json` records the hash it ran with.

## 2026-09-17 · discovery v5 frozen, before held-out set 3 was written

- **No case file changed.** The main set and the first two held-out sets keep their expected decisions, which assume
  policy v1. Case files may now declare `defaults.policy_version`. Held-out set 3 declares v2, which adds one
  argument-aware rule: resolving or closing an incident through `itsm.update_incident` needs approval.
- **Discovery v5 was frozen at 15:51 UTC**, with discovery and selection code hash
  (`benchmark.runner.discovery_code_sha256`) `e78e438423a608a7102512310d790616c99359610835a7a4575c7eb056b5fc01`. The
  hash covers the capability catalog, the calibrated thresholds and the scenario inventory.
- **Method, calibration and changes before the freeze:** `docs/CAPABILITY_RESOLUTION_V5.md`.

## 2026-09-17 · held-out set 3, frozen before any run used it

- **`benchmark/prompts/holdout3_cases.yaml`: 200 new cases (H301–H500), split `holdout3`, policy v2.** Frozen at
  SHA-256 `7acf50b706bddefdcce7aac017d16f857015b9815bbb4f8ac0e9140dec091dfe` at 16:17 UTC, after discovery v5 was frozen.
  - **Kinds:** 120 clear, 60 ambiguous and 20 trap.
  - **Categories:** direct 30, cross_domain 24, multi_step 24, risky 30, adversarial 32, ambiguity 60.
  - **Expected decisions:** 162 ALLOW, 23 REQUIRE_APPROVAL and 15 DENY.
  - **Coverage:** all 50 core tools are golden tools, 2 to 7 times each. Nine cases use the developer identity.
  - **Unknown entities:** 19 cases name something that is not in the inventory.
- **How it was written.** A separate agent wrote it from `benchmark/prompts/holdout3_brief.md` and the author pack
  (`python -m benchmark.dev.holdout3_author_pack`).
  - **What it could see:** the published tool list, the entity inventory, the scoring code and the two validation
    tests.
  - **What it could not see:** the registry, the capability catalog, any discovery code, the docs or any run.
  - **What it ran:** only the policy helper and the validation tests. It reported counts only, and the requests were
    not read before the runs.
- **Checks before the runs:** the discovery code hash was still
  `e78e438423a608a7102512310d790616c99359610835a7a4575c7eb056b5fc01`, the case file was the only repository file
  changed, and the validation tests passed.
