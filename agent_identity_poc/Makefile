# T1 · Agent Identity: one command surface for the whole package.  `make help` lists the targets.
POC    := agent_identity_poc
RUN    := $(shell cat $(POC)/runs/PUBLISHED)
DOCPY  := uv run --project $(POC) --with markdown --with pypdf python


# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-10-03-recorded
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: help setup test demo run verify console diagrams export manifest docs qa all

help:       ## this list
	@grep -E '^[a-z]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-10s %s\n", $$1, $$2}'

setup:      ## the POC environment (Python 3.12, pydantic, pyyaml, pytest)
	cd $(POC) && uv sync --group dev

test:       ## POC tests (no model, no network)
	cd $(POC) && uv run pytest

demo:       ## the 14:09 rollback, with every identity in the chain printed
	cd $(POC) && uv run aid demo

run:        ## AUTHOR ONLY (rewrites the published run): I1–I7 -> agent_identity_poc/runs/<PUBLISHED>/ (incl. scenarios/); the Lab Console follows the run
	$(guard_published)
	cd $(POC) && uv run aid experiments --run-id $(RUN)
	$(DOCPY) tools/build_lab_console.py $(RUN)

verify:     ## rerun the experiments into a fresh copy of the POC and compare with the published run, byte for byte
	python3 tools/verify_run.py

console:    ## the Lab Console (every scenario: input, output, steps, lineage, outcome) -> results/lab-console.html
	$(DOCPY) tools/build_lab_console.py $(RUN)

diagrams:   ## figure skeletons from code + the published run's facts
	python3 diagrams/tools/figures_t1.py

export:     ## skeletons -> .excalidraw + SVG + PNG@2x (headless Chrome + @excalidraw/excalidraw from esm.sh)
	cd diagrams/tools && python3 export_premium.py

manifest:   ## diagrams/manifest.json (provenance, files, Excalidraw+ frames)
	python3 tools/diagram_manifest.py

docs: manifest   ## both editions and the three evidence documents (results/) as Markdown, standalone HTML and PDF
	python3 tools/build_results.py
	$(DOCPY) tools/build_docs.py
	$(MAKE) series

qa:         ## rendered checks at desktop/tablet/mobile + screenshots -> qa/
	node tools/qa_pages.mjs

all: test verify diagrams export docs qa   ## everything, in order

# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series replay

replay:        ## the same as make verify: the experiments rerun in a fresh copy of the POC and compared byte for byte
	$(MAKE) verify

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium T1 && $(SERIES_TOOL) results T1 && $(SERIES_TOOL) readme T1
