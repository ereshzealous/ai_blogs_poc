# Deviations and errata after the freeze

The preregistration (`experiment/preregistration.md`, commit `2bfe2f7`) is frozen and hashed. It is not edited. Anything found after the freeze is logged here with its time, reason and effect.

## E1 · Stale bullet in preregistration §9 (documentation only)

- **Found:** 2026-09-28 03:15 IST, while drafting the limitations section, during the main blind pass.
- **What:** §9 ("What is not claimed") still contains the bullet *"human approvers (approvals are requested, never granted, in the benchmark; approval binding is tested deterministically in `poc/tests`)"*. That text predates the scripted approver follow-ups. §4 of the same document, the frozen benchmark file and the frozen runner all specify that the four C07 cases carry a scripted supervisor decision (approve ×3, reject ×1), which the approver applies to whatever request is actually pending in arm C.
- **Correct reading:** approvals **are** granted or rejected in the benchmark, by a *scripted* approver. What is not claimed is behaviour with *real human* approvers.
- **Effect on the run:** none. The runner, the benchmark and the scorer (all hashed) define the behaviour. The articles describe the scripted approver.

## E2 · Post-freeze source fix: the model can only propose a surfaced capability (evidence revision r2)

- **Found:** 2026-09-28 afternoon IST, by an external review of the POC source, after the blind run and the article drafts.
- **What:** `Gateway._handle` (`poc/src/sprawl_poc/control_plane/gateway.py`) accepted two kinds of model tool name: a
  capability tool surfaced to the model, and **any exact implementation name** in the estate (`server__tool`). The second
  path used `Binder.bind_implementation`, which does no authoritative value binding, so a model that guessed the
  authoritative implementation's name (`refunds__refund_order`) could have skipped the capability binder and its business
  invariants (for example, refunding the original capture as a duplicate). Trap implementations named this way were still
  denied by policy; the authoritative one was not.
- **Did the recorded evidence use it?** No. Every control-plane proposal in the recorded runs (469 across blind-main,
  blind-repeat and the replay check) named a surfaced capability; none named an implementation.
- **Change (commit `1e916d7`):** the model-facing `handle()` accepts only surfaced capability tools and stops an
  implementation name at the proposal stage (`NOT_EXECUTED`, kind `not_surfaced`), recording it as the implementation the
  model proposed so the frozen scorer judges it unchanged. The implementation path remains only as the internal
  `govern_implementation()`, used by the deterministic policy-rule tests and not reachable from the agent loop. New tests:
  `poc/tests/test_proposal_boundary.py` (82 tests pass in all).
- **Evidence identity:** this changed frozen source, so the evidence is re-identified as **revision r2**
  (`experiment/evidence-revisions.json`, `experiment/frozen-hashes-r2.json`). The blind-run freeze
  (`experiment/frozen-hashes.json`, r1) is not rewritten; `freeze.py --verify` and `uv run sprawl verify` check today's files
  against r2 and that r2 differs from r1 only in the declared `gateway.py` and the `poc/src` tree hash.
- **Re-verification:** every recorded row (728: blind-main 504, blind-repeat 224) was replayed through the r2 code with the
  recorded model responses and no model. **728 of 728 reproduce** their ledger effects, declared outcome and verdict
  (`experiment/recorded-run/replay-r2/`). 38 model requests in 19 rows differ from the live requests in key order only
  (row files store tool-call arguments with sorted keys); the r1 code shows the same mismatches row for row.
- **Effect on the published numbers:** none. No row, cell, test or hypothesis verdict changes. The articles and the Lab
  Console say that the fix came after the run and how it was verified.
- **Related, not changed (F2 backlog):** an approval is consumed before the approved invocation's execution completes, so
  a transient failure after approval leaves retry semantics to a durable-execution layer. That belongs with the observed
  503 weakness (governance is not durable workflow execution), not in F1.

## E3 · A second live blind pass, promoted as the published run (2026-10-01)

- **What.** At the author's request the frozen blind benchmark ran live again (`blind-rerun-2026-10-01`, 504 rows, every
  arm at every size) and was promoted as the published run (`evidence/published.json`, history kept). Nothing that is
  scored changed: the same cases, labels, prompt, scorer, policy, hypotheses, model, digest, seed and settings; the code
  is evidence revision r2 (E2), so the fresh pass never had the closed path.
- **Why it is a deviation.** The preregistration planned one blind main pass and a repeat pass. The fresh pass is a
  replication of the same blind cases, not a new held-out test; the original pass (`blind-main`) is kept as recorded
  evidence and serves as the fresh pass's noise floor.
- **Interrupted once.** The tool session's time limit stopped the runner after some rows; it resumed with `--resume`
  (finished rows kept final, the interrupted row run again from the start), recorded in `run-meta.json` → events.
- **Effect on the published results.** Reported as measured, not reconciled: H5 is no longer supported; the
  rejected-approval failure did not recur; neither baseline fell back in the persistent outage; the control plane again
  executed nothing unsafe. `docs/proof-standardization/proof-refresh-delta.md` lists every article metric that changed;
  `docs/proof-standardization/fresh-run-2026-10-01.md` compares the two passes cell by cell.

## Post-freeze tooling (not deviations; listed for transparency)

These files were written after the freeze. They package, replay or visualise the frozen results. They do not change what is scored or how.

- `poc/scripts/evidence.py`: calls the frozen `bench/analyze.py` and `bench/hypotheses.py`, then adds descriptive tables: per-category results, a heuristic failure taxonomy, trap effects, multi-turn counts, context sizes, the noise floor, and the deterministic ORD-4917 search ranking. The failure taxonomy is descriptive and post hoc.
- `poc/scripts/verify_replay.py`: replays recorded model responses through the real stack without the model.
- `poc/scripts/freeze.py --revision`, `experiment/evidence-revisions.json` (2026-09-28): evidence revisions after the run (see E2). The blind-run freeze is never rewritten.
- `poc/scripts/evidence_export.py` and `vendor/evidence_kit/` (2026-09-28): the Lab Console (`evidence/lab-console.html`). The exporter reads rows, detail files, audit files and the committed analysis and writes `evidence/evidence.json` (the evidence-kit 2 data contract); the vendored kit renders it. It calls no model and re-runs nothing. Verdicts are the frozen scorer's, stored in each row; rates use the frozen `wilson`. For the blind main pass the build aborts unless every cell equals `experiment/analysis/summary.json` (108 values in 9 cells) and every drill-down count equals `experiment/analysis/facts.json`. It replaced the earlier `poc/scripts/console.py` and the Evidence Dossier (evidence-kit 1) the same day.
- `poc/scripts/sprawl.py` and `./sprawl` (2026-09-28; replaced on 2026-09-29 by `uv run sprawl`, below): one command for the pipeline (`doctor`, `verify`, `test`, `build`, `run`, `replay`, `analyze`, `report`, `all`). It calls the frozen runner, scorer and scripts unchanged. To reach a non-local Ollama without editing frozen code, it forwards `127.0.0.1:11434` to `--ollama-host`. `analyze` and `build` compare their outputs with the committed files and restore the originals unless told to write. New runs go to `experiment/runs/`, never into recorded evidence.
- `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `docker/ollama-shim.py` (2026-09-28): the same CLI in a container (Python 3.12.13, uv 0.11.7, the locked dependencies). The shim answers `ollama list` / `ollama --version` over the Ollama HTTP API, so the frozen harness records the same model digests and version inside the container. The model is never in the image.
- `poc/data/embeddings-cache/nomic-embed-text.json.gz` (2026-09-28): a byte-exact snapshot of the local `nomic-embed-text` vector cache (1,084 vectors) as it stood after the recorded runs. `poc/data/embeddings/` is git-ignored; `sprawl` restores the cache from this snapshot when it is missing, so replay and analysis need no model server.
- Runner (2026-09-29, at the author's request; tooling only). `uv run sprawl` replaces `poc/scripts/sprawl.py`: a separate runner project at the repository root (`pyproject.toml`, `runner/sprawl_cli/`, the vendored `runner/experiment_runner/`), because `poc/pyproject.toml`, the lock file and `poc/src` are frozen. Every step still runs the same frozen harness and scripts in the POC's locked environment; new helper scripts `poc/scripts/doctor.py`, `verify.py` and `summarize.py` hold what the old router did inline. `./sprawl`, `sprawl.cmd` and `sprawl.ps1` only delegate. Outputs were compared command by command with the old runner and are identical apart from the printed helper steps. No frozen file, row, number or verdict changed, and nothing recorded was re-run.
- Evidence Kit 4 (2026-09-29, at the author's request; tooling only). `poc/scripts/evidence_export.py` now joins `poc/scripts/evidence_adapter.py` (reads the recorded files; every number a fact with provenance, re-counted from the rows and cross-checked against `facts.json` and `summary.json`) with `evidence/learning.toml` (the words and pages; every number bound to a fact) through the vendored evidence-kit 4.0.0. A golden comparison with the kit 3 console showed identical text in every view checked and identical evidence value for value; the only visible change is the provenance at the end of each drill-down. No frozen file, row, number or verdict changed, and nothing was re-run.
- Public verification and the public export (2026-10-04, at the author's request; tooling only). `poc/scripts/public_verify.py` is `uv run sprawl verify` in the public repository: it recomputes the preregistered analysis and hypotheses from `rows.jsonl` with the frozen code and checks the frozen inputs, the replay, the featured trace, the negative control, the public manifest and the Lab, without a model and without the publication build tools. The public repository and its full-evidence archive are copies of this workspace; a file changed for publication is declared in `evidence/public-redactions.json` with both hashes.

- Article and figure build tooling (the Medium and Technical editions, their figures) lives outside this repository; its entries are omitted here.