# C1 · Multi-Agent Systems & Agent2Agent (A2A): one command surface.  `make help` lists the targets.
POC    := coordination_poc
DOCPY  := uv run --project $(POC) --with markdown --with pypdf python


# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-10-08-blind
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: help setup test docs figures export console verify public

help:          ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-14s %s\n", $$1, $$2}'

setup:         ## the POC environment (Python 3.12 via uv; pytest)
	cd $(POC) && uv sync --group dev

test:          ## the POC's unit and end-to-end tests (real A2A and MCP processes, no model) -> verification/pytest.*
	mkdir -p verification
	cd $(POC) && uv run --group dev pytest --junitxml=../verification/pytest.junit.xml > ../verification/pytest.txt 2>&1; s=$$?; tail -1 ../verification/pytest.txt; exit $$s

docs:          ## both editions and the evidence documents as Markdown, standalone HTML and PDF (figures pending -> placeholders)
	python3 tools/build_references.py && python3 tools/build_readme.py && $(DOCPY) tools/build_docs.py all
	$(MAKE) series

figures:       ## figure skeletons from code + the published facts, then lint
	python3 diagrams/tools/figures_final.py && python3 diagrams/tools/lint_figures.py

export:        ## skeletons -> .excalidraw + SVG + PNG@2x, then diagrams/manifest.json
	python3 diagrams/tools/export_premium.py && python3 diagrams/tools/diagram_manifest.py

console:       ## TODO: the Lab Console -> results/lab-console.html
	@echo "TODO: console"

verify:        ## frozen inputs unchanged, replay identical and the tests, in a throwaway copy of the POC (the published run is not written) -> verification/
	mkdir -p verification
	$(in_copy) set -o pipefail && uv run python -m coord.freeze check | tee $(CURDIR)/verification/frozen-check.txt && uv run python -m coord.verify_replay $(RUN) | tee $(CURDIR)/verification/replay-check.txt && uv run --group dev pytest -q; $(end_copy)

public:        ## assemble the published POC folder (GitHub: ai_blogs_poc/multi_agent_a2a_poc/) into OUT=<empty dir>
	python3 tools/stage_public.py $(OUT)

# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series replay demo qa all

replay:        ## the same as make verify: the published run's replay check runs in a throwaway copy
	$(MAKE) verify

demo:          ## one benchmark case (B1) through architecture C with a scripted model, in a throwaway copy of the POC
	$(in_copy) uv run python -m coord.bench run --run-id try --fixture B1 --arch C --scripted; $(end_copy)

qa:            ## the Medium edition's checks: what Medium cannot show, relative links, stale wording
	$(SERIES_TOOL) check C1

all: test verify docs qa   ## tests, the published run verified, the editions and QA (nothing rewrites the run)

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium C1 && $(SERIES_TOOL) results C1 && $(SERIES_TOOL) readme C1
