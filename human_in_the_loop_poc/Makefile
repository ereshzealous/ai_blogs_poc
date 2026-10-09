# T3 · Human-in-the-Loop: one command surface for the whole package.
POC    := hitl_poc
DOCPY  := uv run --project $(POC) --with markdown --with pypdf python


# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-10-03-protocol
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: setup test suite freeze scenarios proof verify demo serve diagrams export-diagrams manifest storyboard results docs readme qa paths gate all

setup:            ## the POC environment (Python 3.12, pydantic, pyyaml, pytest)
	cd $(POC) && uv sync --group dev
test:             ## pytest: the conformance suite (30 tests) + the implementation tests
	cd $(POC) && uv run pytest
suite:            ## the conformance suite, as a table
	cd $(POC) && uv run hitl suite
freeze:           ## AUTHOR ONLY (rewrites the published run): freeze the preregistration before a run: make freeze NOTE="why"  (appends to proof/FREEZE.json history)
	$(guard_published)
	@test -n "$(NOTE)" || { echo 'usage: make freeze NOTE="reason for the freeze"'; exit 2; }
	cd $(POC) && uv run hitl freeze --note "$(NOTE)"
scenarios:        ## the 30 preregistered scenarios under arms A, B and C, as a table (no evidence written)
	cd $(POC) && uv run hitl scenarios
proof:            ## AUTHOR ONLY (rewrites the published run): scenarios + conformance suite + negative controls + HTTP round trip -> evidence/runs/<run>/ (then `uv run hitl promote` to publish)
	$(guard_published)
	cd $(POC) && uv run hitl proof
verify:           ## PROOF VERIFICATION of the published run (pae-proof/v1)
	cd $(POC) && uv run hitl verify
demo:             ## the incident end to end
	cd $(POC) && uv run hitl demo
serve:            ## the approval inbox at http://127.0.0.1:8787/
	cd $(POC) && uv run hitl serve
diagrams:         ## figure skeletons from code + the published run's facts
	python3 diagrams/tools/figures.py
export-diagrams:  ## skeletons -> .excalidraw + SVG + PNG@2x (headless Chrome + @excalidraw/excalidraw from esm.sh)
	python3 diagrams/tools/export_premium.py
manifest:
	python3 tools/diagram_manifest.py
storyboard:
	python3 tools/build_storyboard.py
results:          ## docs/source/report.src.md (the Run Report) from the published run
	python3 tools/build_results.py
docs:             ## both editions and the three results documents as Markdown, standalone HTML and PDF
	$(DOCPY) tools/build_docs.py
	$(MAKE) series
readme:           ## hitl_poc/README.md from the published facts
	python3 tools/render_readme.py
qa:               ## rendered checks at desktop/tablet/mobile + screenshots -> qa/
	node tools/qa_pages.mjs
paths:            ## publication QA: no local path (file://, home, temp, this workspace) in any artifact; PDFs inflated
	PYTHONPATH=vendor python3 -m evidence_kit.publication medium technical results README.md $(POC)/README.md diagrams/premium/svg diagrams/manifest.json $(POC)/evidence --root . --forbid $(abspath ../../..)
gate:             ## the publication gate -> qa/verification.json
	$(DOCPY) tools/verify_all.py
all: diagrams export-diagrams manifest storyboard results docs readme qa paths verify gate   ## every figure, document and check, in order (nothing rewrites the published run)
# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series help replay

help:          ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-16s %s\n", $$1, $$2}'

replay:        ## the published run replayed in a temp folder, as part of PROOF VERIFICATION (writes only the verification report)
	cd $(POC) && uv run hitl verify

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium T3 && $(SERIES_TOOL) results T3 && $(SERIES_TOOL) readme T3
