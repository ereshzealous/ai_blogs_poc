# S2 · Enterprise Knowledge, Context Engineering & RAG: one command surface.  `make help` lists the targets.
POC    := enterprise_knowledge_rag_poc
DOCPY  := uv run --project $(POC) --with markdown --with pypdf python
RUN     = $(shell cat $(POC)/runs/PUBLISHED 2>/dev/null)

# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes.
SHELL             := /bin/bash
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi

.PHONY: help setup test index demo record replay facts exploratory freeze-check verify figures export manifest docs readme qa series all

help:          ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-14s %s\n", $$1, $$2}'

setup:         ## the POC environment (Python 3.12 via uv; pytest)
	cd $(POC) && uv sync --group dev

test:          ## unit, integration and regression tests (no model, no Ollama) -> verification/pytest.*
	mkdir -p verification
	cd $(POC) && uv run --group dev pytest --junitxml=../verification/pytest.junit.xml > ../verification/pytest.txt 2>&1; s=$$?; sed -i.bak -E 's/ hostname="[^"]*"//' ../verification/pytest.junit.xml && rm -f ../verification/pytest.junit.xml.bak; tail -1 ../verification/pytest.txt; exit $$s

index:         ## AUTHOR ONLY (rewrites the frozen index): rebuild the index from the corpus and re-check it against the embedding tape
	$(guard_published)
	cd $(POC) && uv run python -m knowledge_rag.ingest > /dev/null && uv run python -m knowledge_rag.embed replay

demo:          ## INC-4917 through the naive and the governed pipeline, from the published tape (no model)
	cd $(POC) && uv run python -m s2_eval.cli demo

record:        ## a NEW recorded run (needs Ollama): make record ID=2026-10-09-heldout SPLIT=heldout
	cd $(POC) && uv run python -m s2_eval.run record --run-id $(ID) --split $(SPLIT)

replay:        ## replay the published run from its tapes into runs/<run>-replay and compare byte for byte (no model)
	set -o pipefail; cd $(POC) && uv run python -m s2_eval.run replay --from $(RUN) --out $(RUN)-replay | tee ../verification/replay-check.txt

facts:         ## AUTHOR ONLY: recompute facts.json of the published run from its rows (rewrites the run)
	$(guard_published)
	cd $(POC) && uv run python -m s2_eval.analysis runs/$(RUN)

exploratory:   ## AUTHOR ONLY (rewrites docs/derived-facts.json): POST-HOC assembler variants and the typography re-score -> runs/<run>-exploratory
	$(guard_published)
	cd $(POC) && uv run python -m s2_eval.exploratory $(RUN) > /dev/null && uv run python -m s2_eval.exploratory $(RUN) --typography > /dev/null
	python3 tools/build_derived_facts.py

freeze-check:  ## every frozen input unchanged since the freeze (or explained in POST-RUN-CHANGES.sha256)
	mkdir -p verification
	set -o pipefail; cd $(POC) && uv run python -m s2_eval.freeze check | tee ../verification/frozen-check.txt

verify:        ## frozen inputs, an independent recomputation of the headline numbers, replay, tests -> verification/
	$(MAKE) freeze-check
	# the evidence check mixes findings with integrity: its FAIL lines are reported in the file, not raised here
	cd $(POC) && uv run python -m s2_eval.verify_evidence $(RUN) | tee ../verification/evidence-check.txt
	$(MAKE) replay
	$(MAKE) test

figures:       ## figure skeletons from code + the published facts, then lint
	python3 diagrams/tools/figures_final.py && python3 diagrams/tools/lint_figures.py

export:        ## skeletons -> .excalidraw + SVG + PNG@2x (headless Chrome), then diagrams/manifest.json
	python3 diagrams/tools/export_premium.py && python3 diagrams/tools/diagram_manifest.py

readme:        ## the POC README from its template and the published facts
	python3 tools/build_readme.py

docs:          ## both editions and the run report as Markdown, standalone HTML and PDF
	python3 tools/build_derived_facts.py && python3 tools/build_report_source.py && python3 tools/build_evidence_source.py && python3 tools/build_references.py
	$(MAKE) readme
	$(DOCPY) tools/build_docs.py all --strict
	$(MAKE) series

all: test figures export docs   ## everything that does not need a model

qa:            ## rendered checks of the pages at desktop, tablet and mobile widths -> qa/
	node tools/qa_pages.mjs

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium S2 && $(SERIES_TOOL) results S2 && $(SERIES_TOOL) readme S2
