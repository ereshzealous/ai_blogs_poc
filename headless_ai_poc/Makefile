# F3 · Headless AI: one command surface for the whole package.
POC    := headless_ai_poc
DOCPY  := uv run --project $(POC) --with markdown --with pypdf python


# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-10-05-recorded
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: setup test demo run evidence diagrams export-diagrams manifest storyboard docs qa paths verify verify-docs all

setup:            ## the POC environment (Python 3.12, pydantic, pyyaml, pytest)
	cd $(POC) && uv sync --group dev

test:             ## POC tests (no model, no network)
	cd $(POC) && uv run pytest

demo:             ## one monitoring event, end to end
	cd $(POC) && uv run hai demo

run:              ## AUTHOR ONLY (rewrites the published run): the seven experiments -> headless_ai_poc/runs/<run named in runs/PUBLISHED>/
	$(guard_published)
	cd $(POC) && uv run hai experiments --run-id $(shell cat $(POC)/runs/PUBLISHED)

evidence:         ## EVIDENCE VERIFICATION of the published run: hashes, checks, claims, byte-for-byte replay, scan
	cd $(POC) && uv run hai verify

diagrams:         ## figure skeletons from code + the published run's facts
	python3 diagrams/tools/fig_cover.py && python3 diagrams/tools/figures.py && python3 diagrams/tools/figures2.py

export-diagrams:  ## skeletons -> .excalidraw + SVG + PNG@2x (headless Chrome + @excalidraw/excalidraw from esm.sh)
	python3 diagrams/tools/export_premium.py

manifest:         ## diagrams/manifest.json (provenance, files, Excalidraw+ frames)
	python3 tools/diagram_manifest.py

storyboard:       ## storyboard/scene-specs.md and storyboard/storyboard.md
	python3 tools/build_storyboard.py

docs:             ## both editions as Markdown, standalone HTML and PDF
	$(DOCPY) tools/build_docs.py
	$(MAKE) series

qa:               ## rendered checks at desktop/tablet/mobile + screenshots -> qa/
	node tools/qa_pages.mjs

paths:            ## publication QA: no local path (file://, home, temp, this workspace) in any artifact; PDFs inflated
	PYTHONPATH=vendor python3 -m evidence_kit.publication medium technical README.md $(POC)/README.md $(POC)/runs $(POC)/proof diagrams/premium/svg diagrams/manifest.json --root . --forbid $(abspath ../../..)

verify:           ## PROOF VERIFICATION of the published run, read-only (hai verify --check; no model)
	cd $(POC) && uv run hai verify --check

verify-docs:      ## the publication gate over the editions, figures and QA -> qa/verification.json (author)
	$(DOCPY) tools/verify_all.py

all: evidence diagrams export-diagrams manifest storyboard docs qa paths verify verify-docs   ## everything except a new recorded run, in order (nothing rewrites the published run)
# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series help replay

help:          ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-16s %s\n", $$1, $$2}'

replay:        ## the byte-for-byte replay of the published run in a temp folder (part of hai verify --check; read-only)
	cd $(POC) && uv run hai verify --check

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium F3 && $(SERIES_TOOL) results F3 && $(SERIES_TOOL) readme F3
