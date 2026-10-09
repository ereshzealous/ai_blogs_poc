# O1 + O2 · Operating AI Agents at Scale: one command surface.  `make help` lists the targets.
POC    := ops_poc
RUN    := $(shell cat $(POC)/runs/PUBLISHED)
DOCPY  := uv run --project $(POC) --with markdown --with pypdf python
S      ?= E1


# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-10-08-recorded
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: help setup test demo scenario prereg-check record replay facts pack verify figures lint-figures export manifest docs readme qa all

help:          ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-14s %s\n", $$1, $$2}'

setup:         ## the POC environment (Python 3.12 via uv; pytest)
	cd $(POC) && uv sync --group dev

test:          ## the POC's tests (10 scenario tests + unit tests) -> verification/pytest.*
	uv run --project $(POC) python tools/derive_facts.py tests && tail -1 verification/pytest.txt

demo:          ## the surge with and without admission, then the canary, narrated
	cd $(POC) && uv run agentops demo

scenario:      ## one scenario, every arm: make scenario S=E2   (E1 E2 E3 E5 E7)
	cd $(POC) && uv run agentops scenario $(S)

prereg-check:  ## the preregistered files are unchanged since the freeze
	cd $(POC) && uv run agentops prereg-check

record:        ## a NEW recorded run: make record ID=2026-10-09-recorded
	cd $(POC) && uv run python -m agentops.run record --run-id $(ID)

replay-record:        ## AUTHOR ONLY (rewrites the published run): rerun every scenario from source into a scratch copy and compare byte for byte
	$(guard_published)
	python3 tools/verify_run.py --record

facts:         ## docs/derived-facts.json (tests, proof counts, replay, recomputed facts)
	uv run --project $(POC) python tools/derive_facts.py

pack:          ## AUTHOR ONLY (rewrites the published run): the pae-proof/v1 proof pack of the published run -> evidence/runs/<run>/ and results/claim-evidence.json
	$(guard_published)
	uv run --project $(POC) python tools/proof_pack.py build $(RUN) --write && uv run --project $(POC) python tools/derive_facts.py

verify:        ## PROOF VERIFICATION of the published run -> evidence/verification/verification.{txt,json}
	uv run --project $(POC) python tools/verify_evidence.py

figures:       ## figure skeletons from code + the published facts
	python3 diagrams/tools/figures_o1o2.py

lint-figures:  ## type scale, bounds and overlap lint of every figure
	python3 diagrams/tools/lint_figures.py

export:        ## skeletons -> .excalidraw + SVG + PNG@2x (headless Chrome + @excalidraw/excalidraw from esm.sh)
	cd diagrams/tools && EXPORT_BUDGET=300000 python3 export_premium.py

manifest:      ## diagrams/manifest.json (provenance, badges, files, Excalidraw+ frames)
	python3 tools/diagram_manifest.py

readme:        ## README.md and ops_poc/README.md from their templates and the published facts
	python3 tools/build_readme.py

docs: manifest facts   ## both editions and the evidence documents as Markdown, standalone HTML and PDF
	python3 tools/build_references.py && python3 tools/build_result_sources.py
	$(MAKE) readme
	$(DOCPY) tools/build_docs.py
	$(MAKE) series

qa:            ## rendered checks of every page (desktop/tablet/mobile) -> qa/
	node tools/qa_pages.mjs

all: setup test prereg-check replay figures lint-figures export docs verify qa   ## everything except a new recording, in order

# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series replay replay-record

replay:        ## every scenario rerun from source in a temp folder and compared with the published run (nothing recorded)
	python3 tools/verify_run.py

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium O1+O2 && $(SERIES_TOOL) results O1+O2 && $(SERIES_TOOL) readme O1+O2
