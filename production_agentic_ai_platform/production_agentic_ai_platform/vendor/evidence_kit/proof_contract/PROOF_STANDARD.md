# Production AI Engineering Proof Contract v1

`pae-proof/v1` · shipped with evidence-kit 5 · first implemented by F1 · MCP Tool Sprawl

Every learning in the series makes architectural claims and backs them with a proof of concept. This contract fixes
how that backing is packaged, so a reader can go from any measured sentence to the run, the check and the file
behind it, and verify it without trusting prose or screenshots:

```
ARTICLE CLAIM → EXPERIMENT → CHECK / INVARIANT → OBSERVED RESULT → RAW EVIDENCE → INTEGRITY VERIFICATION → REPLAY
```

It is a contract, not a framework. A learning keeps its own benchmark, runner and row format, and adapts them to the
contract with an adapter. The kit (`evidence_kit.proof`) provides the generic parts: check evaluation, claim tracing,
results, hashes, schema validation, hygiene scans, run comparison and the verification report.

## 1. What every learning provides

| # | Deliverable | Where (recommended) |
|---|---|---|
| 1 | A README a developer understands in a minute: the question, *proof at a glance* from the published run, what it does and does not prove, what actually runs, how to verify | `README.md`, rendered from facts |
| 2 | The published run, named by an explicit pointer | `evidence/published.json` |
| 3 | An execution profile and a REAL / GENERATED / SIMULATED / RECORDED declaration, each REAL item backed by a check | `proof/manifest.toml` |
| 4 | A machine-readable run manifest | `evidence/runs/<run>/manifest.json` |
| 5 | Machine-readable results, checks and summary | `evidence/runs/<run>/{results.json, checks.jsonl, summary.json, summary.md}` |
| 6 | Experiments, each with checks | `proof/experiments.toml` |
| 7 | Claim → experiment → check mapping for every material measured claim | `proof/claims.toml` |
| 8 | The raw evidence the results were derived from, never edited after the run | the learning's recorded-run directory |
| 9 | One verification command | `make verify` / `uv run <runner> verify` |
| 10 | Integrity: SHA256SUMS over the canonical artifacts and the raw evidence | `evidence/runs/<run>/SHA256SUMS` |
| 11 | Limitations, stated where the claims are | README, article, Proof Lab |
| 12 | Reproduction and replay instructions | README |
| 13 | A Proof Lab: one offline page with every experiment, check and claim | the learning's Lab Console |

Where they apply: replay (recorded model traffic re-fed through the real stack), a negative control, a live-model
mode, fault injection, statistical tolerances, provenance hashes of the inputs.

## 2. Vocabulary

**Execution classes** (what actually ran):

| Class | Meaning |
|---|---|
| REAL | The actual mechanism was exercised (a protocol, a process, a policy engine) |
| SIMULATED | A faithful local substitute for an enterprise or external system |
| RECORDED | Captured model input and output, reused for deterministic replay |
| GENERATED | Synthetic content that creates scale or collision pressure while still running through real mechanisms |
| INJECTED | A failure or unsafe condition introduced on purpose |
| ARCHITECTURE | A design concept this POC does not exercise |

A REAL item names the check that shows it ran. A diagram saying so is not evidence.

**Badges** (what a section or figure rests on): ARCHITECTURE (design or synthesis; no run result claimed) ·
IMPLEMENTATION (what the POC contains; runtime topology) · VERIFIED (asserted by a deterministic test, not a run
statistic) · MEASURED (aggregated from the cited run) · RECORDED (one actual row or trace) · LIVE (a dependency
invoked in this run) · CONTROL (a comparison or negative control) · LIMITATION (a scope caveat). Use them sparingly.

**Counting.** Never merge these into one number: *unit tests* (implementation tests), *proof experiments*
(scenario-level architectural experiments), *proof checks* (evidence-backed invariants), *benchmark cases* (the
evaluation set) and *model runs* (actual or recorded model decisions). "500 tests passed" is not a sentence this
contract allows.

## 3. Experiments and checks

An experiment has an `id` (`<article>-R<n>`), `title`, `question`, `claim` (the architectural claim it tests),
`hypothesis`, `setup`, `variable` (or fault), `invariant` (what must hold), `limitations`, and one or more checks.

A check is a comparison over facts, never a typed observation:

```toml
[[experiments.checks]]
id = "F1-R7-C01"                       # <experiment>-C<nn>, stable once published
description = "No unsafe execution in the governed arm, at any catalog size"
kind = "invariant"                     # invariant | hypothesis | confirmatory | measurement | replay | control | implementation
fact = "C.all.unsafe_execution.k"      # the observed value is this fact's value
op = "=="                              # == != < <= > >= within in "not in"
value = 0                              # or ref = "<fact>" (with scale / tolerance)
threshold_source = "experiment/preregistration.md §6 H3"   # where a threshold comes from, when there is one
```

Status: **PASS** when the invariant held; **FAIL** when it did not (a failed preregistered hypothesis is a FAIL and
stays one); **EXPECTED_FAILURE** for a control check (`expect = "fail"`) whose invariant broke as intended when its
safeguard was removed. An experiment is FAIL if any check failed, else EXPECTED_FAILURE if any control broke as
intended, else PASS. The evidence of a check is its facts' provenance: source file and selector, and the recorded rows.

**Findings (5.1).** The status is the machine verdict and never changes. What a reader sees is the check's **finding**,
which separates a result the experiment reports from a proof that broke:

| Status | Kind | Finding |
|---|---|---|
| PASS | any | PASS |
| EXPECTED_FAILURE | control | EXPECTED FAILURE (the control noticed the removed safeguard) |
| FAIL | hypothesis | NOT SUPPORTED |
| FAIL | confirmatory | NOT ESTABLISHED |
| FAIL | measurement | NOT OBSERVED, or LIMITATION OBSERVED when the check declares `finding = "LIMITATION OBSERVED"` |
| FAIL | invariant, replay, control, implementation | FAIL: a guarantee or the evidence itself did not hold |

Only a hypothesis, confirmatory or measurement check may declare its finding; a FAIL of an invariant, replay, control or
implementation check always reads FAIL. An experiment's finding is FAIL if any of its checks reads FAIL, else the
findings of its failed checks (for example NOT SUPPORTED · NOT ESTABLISHED), else EXPECTED FAILURE or PASS. Evidence
verification (section 7) is reported apart from findings: a run can be VERIFIED with every finding it measured.

## 4. Claims

```toml
[[claims]]
id = "F1-C02"
statement = "Deterministic governance contained unsafe proposals."   # no result numbers: they are facts
type = "measured"                     # implementation | measured | architecture+measured | control | limitation
verdict = "supported"                 # supported | contradicted | not_established | implementation | control | limitation
experiments = ["F1-R7"]
checks = ["F1-R7-C01", "F1-R7-C02"]
article = ["What the evidence said", "fig:f26"]   # where the article states it (section headings, figures)
facts = ["C.all.unsafe_execution.k"]               # every result fact the article uses for this claim
```

The verdict is tested against the checks: *supported* needs every check PASS (or EXPECTED_FAILURE), *contradicted*
and *not_established* need a FAIL, *control* needs an EXPECTED_FAILURE, *limitation* names what it `rests_on`
instead. Every result fact an article prints must belong to a claim. Prose is never the source of a verdict.

## 5. A run

`evidence/runs/<run>/` holds the standardized package; the raw evidence stays where the run wrote it.

- `manifest.json`: `schema`, `series`, `article_id`, `poc`, `run_id`, `scenario`, `source_commit`, `runtime_mode`,
  `started_at`, `completed_at`, `environment` (os, arch, python, model runtime, model, model version or digest,
  temperature, seed), `benchmark` (case counts, catalog sizes, retrieval k, modes), `execution_profile`,
  `entrypoints`, `integrity`, and `provenance` saying for each field whether it was **recorded** by the run,
  **frozen** before it, or **reconstructed** afterwards. A value nobody recorded is `"unknown"`, never invented.
- `results.json`: run id, status, experiments with results, check counts, every fact (value, display, denominator,
  source, rows), result tables, the execution profile, the claims trace and evidence paths. It is derived by an
  adapter from the benchmark's own output, which is preserved unchanged: never a second source of truth.
- `checks.jsonl`, `summary.json`, `summary.md`, `SHA256SUMS`.

`evidence/published.json` names the published run. Changing it is an explicit operation (`promote`) that refuses
unless the new run has its own verified package, a replay or recorded package, a passing negative control,
regenerated facts and a reviewed proof-refresh delta. Last run never wins. A run whose methodology differs is a new
benchmark version, not another seed.

## 6. Replay, comparison and the negative control

**Replay level**, declared per learning: EXACT (the same measured values, byte for byte), SEMANTIC (identifiers and
timing differ; every measured value and check holds), STATISTICAL (a live re-run compared under declared tolerances),
or UNAVAILABLE (with the reason). Regenerated model output is never called deterministic.

**Run comparison** classifies every row: DETERMINISTIC_EQUIVALENT · NONDETERMINISTIC (only volatile fields differ:
timestamps, process ids, trace ids, wall time) · MODEL_OUTPUT_VARIATION (a live re-run answered differently) ·
METHODOLOGY_CHANGE (benchmark logic differs: no direct comparison) · REGRESSION (an invariant no longer holds).

**Negative control.** Remove one safeguard, run the same inputs, and show that the invariant it protects fails
cleanly. The harness must finish normally; an exception is not a proof. The control records the safeguard removed,
the expected failure, the observed failure, and that every case completed.

## 7. Verification

One command reads the shipped evidence and prints:

```
PROOF VERIFICATION

Manifest                 PASS
Raw evidence             PASS
Experiment checks        PASS   <n> checks: <p> pass, <f> fail, <e> expected failure
Claim mappings           PASS
Integrity                PASS
Replay                   PASS / N/A
Negative control         PASS
Publication facts        PASS
Secret scan              PASS

VERIFIED
```

It checks: the manifests against the schemas; that the published run and its raw artifacts exist; that every check
names existing evidence; that experiment totals equal check totals; that every measured article claim is mapped; the
SHA256SUMS; the replay comparison's declared equivalence; that the negative control broke the intended invariant and
did not merely crash; that the facts recompute from the raw evidence; that the article, the Lab and the README print
the published facts; that no raw evidence changed; and that nothing published carries a credential or a private path.
FAIL checks are results, not verification failures: verification asks whether the evidence holds together.

A SHA256SUMS verifies files against a list. It is not a signature and says nothing about who wrote them.

## 8. Publication

Every number an article, a figure's text, the README or the Lab prints is substituted from the published run's facts
(`{{fact}}`). A build fails when a printed value differs from the facts, a figure's run id differs from the published
run, a rate lacks its denominator, or a typed number is neither a fact nor a listed non-result. Measured figures carry
a footer — MEASURED · run · experiment · source — and architecture figures say so. When a published value changes, the
article says so in a visible refresh note with the old run, the new run, the methodology and the deltas.

## 9. Adopting the contract in a learning

1. Copy (vendor) evidence-kit 5 and record its version.
2. Write `proof/manifest.toml`, `proof/experiments.toml`, `proof/claims.toml` against the learning's facts.
3. Extend the learning's adapter so every fact a check needs exists, with its provenance.
4. Add the runner commands `verify`, `proof`, `replay`, `negative-control`, `lab`, `package` (experiment-runner's
   template has them) and a Makefile that only delegates to them.
5. Take the publication baseline of the article before editing it; afterwards, produce the proof-refresh delta.
6. Render the README from facts; add the proof strip, the reality map and figure footers to the article.
