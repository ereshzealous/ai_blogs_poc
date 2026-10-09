# T6 · Agent, Tool & MCP Security — one command surface. Defensive lab; no network, no model required for the gate.
POC   := redteam_poc
DOCPY := uv run --project $(POC) --with markdown --with pygments python


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

.PHONY: help setup test scenarios matrix ablation demo freeze proof verify diagrams figures docs readme qa gate all

help:          ## this list
	@grep -E '^[a-z][a-z -]*:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-16s %s\n", $$1, $$2}'

setup:          ## create the POC environment (uv, Python 3.12)
	cd $(POC) && uv sync --group dev
test:           ## pytest: import contract, unit invariants, end-to-end scenarios
	cd $(POC) && uv run pytest
scenarios:      ## the whole corpus across arms A/B/C, as a table
	cd $(POC) && uv run redteam scenarios
matrix:         ## the model-manipulated vs system-compromised headline table
	cd $(POC) && uv run redteam matrix
ablation:       ## arm C with one control removed at a time, and each control's standalone reach
	cd $(POC) && uv run redteam ablation
demo:           ## the legitimate task and one contained attack, narrated
	cd $(POC) && uv run redteam demo
freeze:         ## AUTHOR ONLY (rewrites the published run): freeze the preregistration/corpus/config before a run: make freeze NOTE="why"
	$(guard_published)
	cd $(POC) && uv run redteam freeze "$(NOTE)"
proof:          ## AUTHOR ONLY (rewrites the published run): record the run -> evidence/runs/<run>/ (manifest, results, facts, checks, summary, SHA256SUMS)
	$(guard_published)
	cd $(POC) && uv run redteam proof
verify:         ## PROOF VERIFICATION of the published run (EXACT replay + integrity + checks)
	cd $(POC) && uv run redteam verify
figures:        ## generate the premium Excalidraw figures (skeletons) and export to SVG/PNG (needs network for esm.sh)
	python3 diagrams/tools/figures_t6.py
	EXPORT_BUDGET=260000 python3 diagrams/tools/export_premium.py
docs:           ## both editions + results pages as Markdown, standalone HTML and PDF
	$(DOCPY) tools/build_docs.py
	$(MAKE) series
readme:         ## render redteam_poc/README.md and the package README from facts
	python3 tools/render_readme.py
qa:            ## rendered checks of the pages, when the chapter has them; make gate runs the publication gate
	@if [ -f tools/qa_pages.mjs ]; then node tools/qa_pages.mjs; else echo "T6 has no rendered-page checks yet: make gate runs the publication gate."; fi
gate:           ## publication gate -> qa/verification.json
	$(DOCPY) tools/verify_all.py
all: test verify figures docs readme qa gate   ## tests, the published run verified, figures, documents and the publication gate (nothing rewrites the run)

# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series replay

replay:        ## the same as make verify: the published run replayed in memory, exact, as part of PROOF VERIFICATION
	$(MAKE) verify

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium T6 && $(SERIES_TOOL) results T6 && $(SERIES_TOOL) readme T6
