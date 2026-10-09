# F2 · Layered Production AI Architecture — one command surface for the whole bundle.
POC      := layered_architecture_poc
RUN      := $(shell cat $(POC)/runs/PUBLISHED 2>/dev/null)
PY       := cd $(POC) && uv run python
DOCPY    := uv run --project $(POC) --with markdown --with pypdf --with pyyaml python



# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-09-28-recorded
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: evidence check-scene setup models test test-fast test-live run-recorded replay verify-evidence diagrams export-diagrams docs pdfs report verify-all \
        outcomes accounting numbers figures audit export release standardize

setup:            ## install the POC environment (Python 3.12, mcp 2.2.0); no model needed (make models checks Ollama)
	cd $(POC) && uv sync

models:           ## check that Ollama has the run's models (gpt-oss:20b, qwen3:8b); only a new recorded run needs them
	ollama list | grep -E "gpt-oss:20b|qwen3:8b"

test:             ## every test except the live-model ones (no model needed)
	cd $(POC) && uv run pytest -m "not model"

test-fast: test   ## the same as make test (kept for older notes)

test-live:        ## every test, including the live-model tests (needs Ollama)
	cd $(POC) && uv run pytest

run-recorded:     ## a new recorded run (live models, real MCP, real SIGKILL); never overwrites an existing run
	$(PY) scripts/record_run.py
	$(DOCPY) tools/build_lab_console.py   # the Lab Console follows the runs

replay:        ## the published run replayed from its model tape in a throwaway copy of the POC (no model, nothing written to the run)
	$(in_copy) rm -rf runs/$(RUN)-replay && uv run python scripts/replay_run.py runs/$(RUN); $(end_copy)

verify-evidence:  ## AUTHOR ONLY (rewrites the published run): completeness, frozen hashes, summary reproducibility, and the published numbers recomputed from raw
	$(guard_published)
	$(PY) scripts/verify_evidence.py runs/$(RUN)

outcomes:         ## AUTHOR ONLY (rewrites the published run): classify every scenario SUCCESS / FAILURE / ERROR / NOT_EXPOSED and count fault exposure
	$(guard_published)
	$(PY) scripts/classify_outcomes.py runs/$(RUN)

accounting:       ## the four test numbers, reported separately -> verification/test_accounting.{json,md}
	python3 tools/test_accounting.py

numbers:          ## no measured number typed by hand in a publication source
	python3 tools/check_numbers.py

figures:          ## the figures agree with the run, without re-exporting them
	python3 tools/check_figures.py

audit:            ## what would become public: credentials, machine paths, private URLs, licences -> verification/public_export_audit.json
	python3 tools/audit_public_export.py

export:           ## a sanitized public export, then its tests and verifier inside it: make export OUT=/tmp/f2-public
	python3 tools/build_public_export.py --out $(or $(OUT),/tmp/layered-agent-platform-public) --check

release:          ## the public release bundle -> dist/layered-agent-platform-<revision>-<run>.zip (+ SHA256SUMS, PROVENANCE)
	python3 tools/build_release_bundle.py

standardize:      ## AUTHOR ONLY (rewrites the published run): the evidence standard end to end: outcomes, verify, accounting, claims, numbers
	$(guard_published)
	$(MAKE) outcomes
	$(MAKE) verify-evidence
	$(MAKE) accounting
	$(DOCPY) tools/build_claim_matrix.py
	$(MAKE) numbers
	$(MAKE) figures
	$(DOCPY) tools/build_poc_readme.py
	python3 tools/sync_poc_docs.py

diagrams:         ## regenerate every figure skeleton from code + the published run
	python3 diagrams/tools/figures.py && $(DOCPY) diagrams/tools/fig_evidence.py && $(DOCPY) diagrams/tools/fig_cover.py && python3 tools/diagram_manifest.py

export-diagrams:  ## skeletons -> .excalidraw + SVG + PNG@2x (headless Chrome)
	python3 diagrams/tools/export_premium.py

report:           ## the run report (md/html/pdf) from the published run
	$(DOCPY) tools/build_run_report.py

evidence:         ## post-run evidence tests, evidence bundle, the Evidence Check (md/html/pdf) and its validation
	python3 tools/post_run_tests.py && python3 tools/build_evidence_bundle.py && $(DOCPY) tools/build_evidence_check.py

docs pdfs:        ## the three publications as Markdown, standalone HTML and PDF, plus the claim/evidence matrix
	$(DOCPY) tools/build_docs.py && $(DOCPY) tools/build_claim_matrix.py
	$(MAKE) series

check-scene:      ## check an Excalidraw+ scene snapshot: make check-scene SCENE=scene.json -> diagrams/scene_check.json
	python3 tools/check_scene.py $(SCENE)

console:          ## the Lab Console (every run: input, output, steps, lineage, status) -> docs/results/lab-console.html
	$(DOCPY) tools/build_lab_console.py $(RUN)

verify-all:       ## AUTHOR ONLY (rewrites the published run): the final publication gate -> verification/final_verification.{json,md}
	$(guard_published)
	$(DOCPY) tools/verify_all.py

# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series help verify demo qa all

help:          ## this list
	@grep -E '^[a-z][a-z -]*:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-16s %s\n", $$1, $$2}'

verify:        ## the published run's evidence verified in a throwaway copy of the POC: 36 checks, 12 recomputed from raw evidence
	$(in_copy) uv run python scripts/verify_evidence.py runs/$(RUN); $(end_copy)

demo:          ## no single-scenario demo here: make replay replays the published run from its model tape
	@echo "F2 has no demo target: make replay replays the published run from its model tape; make verify checks it."

qa:            ## publication checks: no hand-typed number in a publication, and the figures agree with the run
	$(MAKE) numbers figures

all: test-fast verify docs qa   ## tests without a model, the published run verified, the editions and QA (nothing rewrites the run)

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium F2 && $(SERIES_TOOL) results F2 && $(SERIES_TOOL) readme F2
