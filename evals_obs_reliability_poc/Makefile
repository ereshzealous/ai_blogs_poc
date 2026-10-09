# R1 + R2 · Evals, Observability & Production Reliability: one command surface.  `make help` lists the targets.
POC    := recovery_poc
RUN    := $(shell cat $(POC)/runs/PUBLISHED)
DOCPY  := uv run --project $(POC) --with markdown --with pypdf python
S      ?= S09
A      ?= A2
X      ?= X1


# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-10-07-recorded
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: help setup test demo scenario demo-mutant live-scenario record-live replay-live prereg-check record replay facts pack verify console figures export lint-figures manifest docs qa all

help:          ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-14s %s\n", $$1, $$2}'

setup:         ## the POC environment (Python 3.12 via uv; pytest)
	cd $(POC) && uv sync --group dev

test:          ## the POC's unit and end-to-end tests (real processes, no model) -> verification/pytest.*
	python3 tools/derive_facts.py tests && tail -1 verification/pytest.txt

demo:          ## the flagship (S09) through the naive and the classified runtime, explained step by step
	cd $(POC) && uv run recovery demo

scenario:      ## any scenario through any runtime: make scenario S=S16 A=A2
	cd $(POC) && uv run recovery scenario $(S) --arm $(A)

demo-mutant:   ## a scenario under a mutant of the recovery layer: make demo-mutant X=X1 S=S11
	cd $(POC) && uv run recovery scenario $(S) --arm A2 --mutant $(X)

live-scenario: ## one scenario with a REAL model deciding (needs Ollama): make live-scenario S=S09 A=A2
	cd $(POC) && uv run recovery scenario $(S) --arm $(A) --live

record-live:   ## a NEW real-model end-to-end run, all scenarios x runtimes (needs Ollama): make record-live ID=2026-10-08-live
	cd $(POC) && uv run python -m recovery.run record-live --run-id $(ID)

replay-live:   ## AUTHOR ONLY (rewrites the published run): replay the real-model run from its tapes in a scratch copy, no model, and compare byte for byte
	$(guard_published)
	python3 tools/verify_live.py --record

prereg-check:  ## the preregistered files are unchanged since the freeze
	cd $(POC) && uv run recovery prereg-check

record:        ## a NEW recorded run (needs Ollama with qwen3:8b and llama3.1): make record ID=2026-10-08-recorded
	cd $(POC) && uv run python -m recovery.run record --run-id $(ID) --live

replay-record:        ## AUTHOR ONLY (rewrites the published run): re-execute every deterministic experiment into a scratch copy and compare byte for byte (no model)
	$(guard_published)
	python3 tools/verify_run.py --record

facts:         ## docs/derived-facts.json (tests, replay, proof counts, historical facts, raw recomputations)
	python3 tools/derive_facts.py

pack:          ## AUTHOR ONLY (rewrites the published run): the pae-proof/v1 proof pack of the published run -> evidence/runs/<run>/
	$(guard_published)
	uv run --project $(POC) python tools/proof_pack.py build $(RUN) --write && python3 tools/derive_facts.py

verify:        ## PROOF VERIFICATION of the published run -> evidence/verification/verification.{txt,json}
	uv run --project $(POC) python tools/verify_evidence.py

console:       ## the Lab Console -> results/lab-console.html
	python3 tools/build_lab_console.py

figures:       ## figure skeletons from code + the published facts (capstone kit)
	python3 diagrams/tools/figures_final.py

lint-figures:  ## type scale, bounds and overlap lint of every figure
	python3 diagrams/tools/lint_figures.py

export:        ## skeletons -> .excalidraw + SVG + PNG@2x (headless Chrome + @excalidraw/excalidraw)
	cd diagrams/tools && EXPORT_BUDGET=300000 python3 export_premium.py

manifest:      ## diagrams/manifest.json (provenance, badges, files, Excalidraw+ frames)
	python3 tools/diagram_manifest.py

docs: manifest facts   ## both editions and the three evidence documents as Markdown, standalone HTML and PDF
	python3 tools/build_references.py && python3 tools/build_result_sources.py && python3 tools/build_readme.py && $(DOCPY) tools/build_docs.py
	$(MAKE) series

qa:            ## rendered checks of every page (desktop/tablet/mobile) and the Lab Console -> qa/
	node tools/qa_pages.mjs && node tools/qa_console.mjs

all: setup test prereg-check replay figures lint-figures export docs console verify qa   ## everything except a new recording, in order

# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series replay replay-record

replay:        ## every deterministic experiment re-executed in a temp folder and compared with the published run (nothing recorded)
	python3 tools/verify_run.py

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium R1+R2 && $(SERIES_TOOL) results R1+R2 && $(SERIES_TOOL) readme R1+R2
