# S1 · Memory, Context & State: one command surface.  `make help` lists the targets.
POC   := memory-context-state-poc
RUN   := 2026-09-18-recorded

# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-09-18-recorded
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: help setup test verify replay demo fill docs qa series all

help:          ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-16s %s\n", $$1, $$2}'

setup:         ## the POC environment (Python via uv, from uv.lock)
	cd $(POC) && uv sync

test:          ## the POC's tests and its layer contracts (no model)
	cd $(POC) && uv run pytest && uv run lint-imports

verify:        ## frozen inputs unchanged (s1 check), then the tests; reads the published run, never writes it
	cd $(POC) && uv run s1 check
	$(MAKE) test

replay:        ## the published run replayed from its tape in a throwaway copy of the POC (the published run is not written)
	$(in_copy) uv run s1 run --replay $(RUN); $(end_copy)

demo:          ## no single-scenario demo here: make replay replays the published run from its tape
	@echo "S1 has no demo target: make replay replays the published run from its tape; make verify checks the frozen inputs."

fill:          ## AUTHOR ONLY (rewrites the published run): article numbers, both editions and the POC README from the run
	$(guard_published)
	python3 tools/export_diagram_data.py $(RUN) && python3 tools/fill_article.py --run-id $(RUN)

docs:          ## the technical edition as standalone HTML and PDF, then the uniform series pages
	python3 tools/build_html.py article/memory-context-state-technical.md article/memory-context-state-technical.html
	node tools/build_pdf.mjs article/memory-context-state-technical.html article/memory-context-state-technical.pdf
	$(MAKE) series

qa:            ## the Medium edition's checks: what Medium cannot show, relative links, stale wording
	$(SERIES_TOOL) check S1

all: test verify docs qa   ## tests, frozen inputs, the editions and QA (nothing rewrites the published run)

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium S1 && $(SERIES_TOOL) results S1 && $(SERIES_TOOL) readme S1
