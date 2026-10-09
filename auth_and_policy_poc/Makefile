# T2 · Authorization & Policy for AI Agents: one command surface.  `make help` lists the targets.
POC   := authz_poc
RUN   := 2026-09-29-recorded

# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= 2026-09-29-recorded
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: help setup test verify verify-docs replay demo run record-tests console docs qa series all

help:          ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-16s %s\n", $$1, $$2}'

setup:         ## nothing to install: authz_poc uses the Python standard library (the docs build uses uv)
	@python3 -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+'; print('authz_poc: standard library only, nothing to install')"

test:          ## the four test layers, L1 to L4 (L4 replays the run into a temp folder)
	cd $(POC) && python3 -m unittest discover -s tests -v

verify: replay ## PROOF VERIFICATION: the deterministic run re-executed in a throwaway copy, byte for byte against the published run

verify-docs:   ## both editions checked against the recorded run's values, and the retired wording absent (read-only; author)
	python3 tools/verify_publication.py

replay:        ## the deterministic run re-executed in a throwaway copy of the POC and compared byte for byte with the published run
	$(in_copy) mv runs/$(RUN) ../published && python3 -m authz.run --out runs/$(RUN) > /dev/null && n=0 && for f in $$(ls runs/$(RUN)); do cmp -s ../published/$$f runs/$(RUN)/$$f || { echo "DIFFERS: $$f"; n=$$((n+1)); }; done && echo "replay: $$(ls runs/$(RUN) | wc -l | tr -d ' ') files compared, $$n different" && [ $$n -eq 0 ]; $(end_copy)

demo:          ## no single-scenario demo here: make replay re-executes the whole recorded run
	@echo "T2 has no demo target: make replay re-executes the recorded run and compares it; make verify checks the editions against it."

run:           ## AUTHOR ONLY (rewrites the published run): the ten tool calls through the policy engine -> runs/<run>/
	$(guard_published)
	cd $(POC) && python3 -m authz.run

record-tests:  ## AUTHOR ONLY (rewrites the published run): tests.json, manifest.json and verification.json of the run
	$(guard_published)
	cd $(POC) && python3 -m authz.record_tests && python3 -m authz.verify

console:       ## the Lab Console -> results/lab-console.html
	python3 tools/build_lab_console.py

docs:          ## both editions as standalone HTML, the Medium image kit, then the uniform series pages
	uv run --no-project --with markdown python tools/build_html.py && uv run --no-project --with markdown python tools/build_html.py medium
	python3 tools/medium_kit.py
	$(MAKE) series

qa:            ## the Medium edition's checks: what Medium cannot show, relative links, stale wording
	$(SERIES_TOOL) check T2

all: test verify verify-docs docs qa   ## tests, the editions checked, the replay, the documents and QA (nothing rewrites the run)

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium T2 && $(SERIES_TOOL) results T2 && $(SERIES_TOOL) readme T2
