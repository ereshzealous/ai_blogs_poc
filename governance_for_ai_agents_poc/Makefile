# T5 · Observability & Governance: one command surface for the whole package.  `make help` lists the targets.
POC    := observability_governance_poc
RUN    := $(shell cat $(POC)/runs/PUBLISHED)
DOCPY  := uv run --project $(POC) --with markdown --with pypdf python
NOMODEL := OLLAMA_URL=http://127.0.0.1:1


# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-09-30-recorded
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: help setup test demo proof replay verify console figures export manifest facts docs qa all

help:       ## this list
	@grep -E '^[a-z]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-10s %s\n", $$1, $$2}'

setup:      ## the POC environment (Python 3.12, OpenTelemetry SDK, pytest)
	cd $(POC) && uv sync --group dev

test:       ## POC tests with the model unreachable (unit, real processes, end-to-end scenarios) -> results/tests.json
	python3 tools/derive_facts.py tests

demo:       ## the flagship lost-response scenario from the published tape, then its evidence, event by event
	cd $(POC) && uv run lineage demo

proof:      ## a NEW recorded run (needs Ollama + qwen3:8b): make proof ID=2026-10-01-recorded
	cd $(POC) && uv run python -m lineage.run record --run-id $(ID) && uv run python -m lineage.drift record --run-id $(ID) \
	  && uv run python -c "from pathlib import Path; from lineage.aggregate import aggregate; aggregate(Path('runs/$(ID)'))"

replay-record:     ## AUTHOR ONLY (rewrites the published run): rerun every published scenario from the tapes, no model, and compare with the published run
	$(guard_published)
	rm -rf $(POC)/runs/$(RUN)-replay
	cd $(POC) && $(NOMODEL) uv run python -m lineage.run replay $(RUN)
	mkdir -p $(POC)/runs/$(RUN)-replay/drift && cp -r $(POC)/runs/$(RUN)/drift/tape $(POC)/runs/$(RUN)-replay/drift/ && rm -f $(POC)/runs/$(RUN)-replay/drift/tape/model_tape.consumed.jsonl
	cd $(POC) && $(NOMODEL) uv run python -m lineage.drift replay --run-id $(RUN)-replay

verify:     ## recompute every evidence chain of the published run and check it against the witness anchors
	cd $(POC) && uv run lineage verify-evidence

console:    ## the Lab Console (every scenario × layer: input, output, answers vs truth, steps, lineage) -> results/lab-console.html
	$(DOCPY) tools/build_lab_console.py $(RUN)

figures:    ## figure skeletons from code + the published run's facts
	python3 diagrams/tools/figures_t5.py

export:     ## skeletons -> .excalidraw + SVG + PNG@2x (headless Chrome + @excalidraw/excalidraw from esm.sh)
	cd diagrams/tools && EXPORT_BUDGET=300000 python3 export_premium.py

manifest:   ## diagrams/manifest.json (provenance, files, Excalidraw+ frames)
	python3 tools/diagram_manifest.py

facts:      ## docs/derived-facts.json (replay, tests, run details) from the published run
	python3 tools/derive_facts.py

docs: manifest facts   ## both editions and the three evidence documents (run report, evidence check, real vs simulated) as Markdown, standalone HTML and PDF
	$(DOCPY) tools/build_docs.py
	$(MAKE) series

qa:         ## rendered checks at desktop/tablet/mobile + screenshots -> qa/
	node tools/qa_pages.mjs

all: setup test replay verify figures export docs console qa   ## everything except a new recording, in order

# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series replay replay-record

replay:        ## every published scenario rerun from the tapes in a throwaway copy of the POC (no model) and compared with the published run
	$(in_copy) rm -rf runs/$(RUN)-replay && $(NOMODEL) uv run python -m lineage.run replay $(RUN) && mkdir -p runs/$(RUN)-replay/drift && cp -r runs/$(RUN)/drift/tape runs/$(RUN)-replay/drift/ && rm -f runs/$(RUN)-replay/drift/tape/model_tape.consumed.jsonl && $(NOMODEL) uv run python -m lineage.drift replay --run-id $(RUN)-replay; $(end_copy)

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium T5 && $(SERIES_TOOL) results T5 && $(SERIES_TOOL) readme T5
