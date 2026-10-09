# Capstone · Production Agentic AI Platform: one command surface for the package.  `make help` lists the targets.
# The proof targets delegate to the POC's runner (uv run pap <command>, Production AI Engineering Proof Contract v1); the
# published run is the one production_agentic_ai_platform/evidence/published.json names. Promotion is not a make target.
POC    := production_agentic_ai_platform
PAP    := cd $(POC) && uv run pap
DOCPY  := uv run --project $(POC) --with markdown --with pypdf python
RUN_ID ?= local-$(shell date +%Y%m%d-%H%M%S)


# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-10-04-proof
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: help setup test verify proof replay negative-control pack facts diagrams export manifest references lab docs medium-images readme poc-zip qa all

help:        ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-16s %s\n", $$1, $$2}'

setup:       ## the POC environment (Python 3.12, mcp 2.2.0, OpenTelemetry SDK, pyyaml, pytest)
	cd $(POC) && uv sync --group dev

test:        ## the unit tests (implementation tests, not proof checks)
	$(PAP) test

verify:      ## PROOF VERIFICATION of the published run, the README, the Lab and both articles -> POC evidence/verification/
	$(PAP) verify

proof:       ## a fresh proof into a new run (RUN_ID=...): run, replay, negative control, pack, verify; never published
	$(PAP) proof --run-id $(RUN_ID)

replay:      ## replay the published run into scratch (evidence/local/) and classify it against the recorded run
	$(PAP) replay

negative-control: ## the approval requirement removed, into scratch: the proof must fail cleanly
	$(PAP) negative-control

pack:        ## recompute the published run's proof pack and compare it byte for byte
	$(PAP) pack

facts:       ## docs/facts.json from the published run's proof pack (every number the articles and figures use)
	python3 tools/derive_facts.py

diagrams:    ## figure skeletons from code + docs/facts.json, then the type-scale / layout lint
	python3 diagrams/tools/figures_final.py
	python3 diagrams/tools/lint_figures.py

export:      ## skeletons -> .excalidraw + SVG + PNG@2x (headless Chrome)
	cd diagrams/tools && python3 export_premium.py

manifest:    ## diagrams/manifest.json (provenance footers, badges, files, Excalidraw+ frames)
	python3 tools/diagram_manifest.py

references:  ## docs/source/references.md from research/sources.md
	python3 tools/build_references.py

lab:         ## the Proof Lab of the published run (POC lab/index.html), copied with social tags to results/
	$(PAP) lab
	python3 tools/publish_lab.py

readme:      ## the POC README rendered from its template and the published run
	cd $(POC) && uv run python tools/build_readme.py

docs: facts manifest references lab readme   ## both editions as Markdown, standalone HTML and PDF, and the Medium image pack
	$(DOCPY) tools/build_docs.py
	python3 tools/medium_images.py
	$(MAKE) series

medium-images: ## the Medium edition's figures as 1600 px PNG + captions and alt text (medium/images)
	python3 tools/medium_images.py

poc-zip:     ## release/production-agentic-ai-platform-poc.zip (+ .sha256): the POC's publication package (pap package)
	python3 tools/package_poc.py

qa:          ## rendered checks at desktop/tablet/mobile + screenshots -> qa/
	node tools/qa_pages.mjs

all: setup test docs verify poc-zip qa   ## everything that does not rewrite published evidence

# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series demo

demo:          ## no single-scenario demo here: make replay replays the published run into scratch
	@echo "P1 has no demo target: make replay replays the published run into scratch; make verify checks it."

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium P1 && $(SERIES_TOOL) results P1 && $(SERIES_TOOL) readme P1
