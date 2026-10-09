# F1 · MCP Tool Sprawl: the Proof Contract v1 targets. Every target only calls the runner (uv run sprawl <command>),
# the one implementation; `make help` lists them. Without make, run the same commands directly (docs/DEVELOPER.md).
RUN_ID ?= live-$(shell date +%Y%m%d-%H%M)


# ---- Production AI Engineering · series conventions (the same block in every chapter) -----------------------------
# A target that rewrites the published run refuses unless the author asks for it with REWRITE_PUBLISHED=yes. A reader
# command that would write into the run runs in a throwaway copy of the POC instead ($(in_copy) ... ; $(end_copy)).
SHELL             := /bin/bash
RUN               ?= blind-rerun-2026-10-01
SERIES_TOOL       := python3 ../series-start-here/tools/series_edition.py
REWRITE_PUBLISHED ?= no
guard_published    = @if [ "$(REWRITE_PUBLISHED)" != "yes" ]; then echo "refusing: '$@' rewrites published evidence of run $(RUN). Readers never need it; the author runs it with REWRITE_PUBLISHED=yes."; exit 1; fi
in_copy            = tmp=$$(mktemp -d) && rsync -a --exclude .venv --exclude __pycache__ $(POC)/ $$tmp/$(POC)/ && cd $$tmp/$(POC) &&
end_copy           = s=$$?; rm -rf $$tmp; exit $$s

.PHONY: help verify test proof replay negative-control lab package proof-live all doctor

help:              ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-17s %s\n", $$1, $$2}'

verify:            ## PROOF VERIFICATION of the published run: reads the shipped evidence, no model (seconds)
	uv run sprawl verify

test:              ## the deterministic unit tests: real MCP server processes, no model
	uv run sprawl test

proof:             ## recompute the published run's proof pack from the recorded files and compare it, byte for byte
	uv run sprawl proof

replay:            ## replay recorded rows through the real stack without the model, and classify them against the run
	uv run sprawl replay

negative-control:  ## AUTHOR ONLY (rewrites the published run): remove the policy from the gateway and show the invariant it protects break (no model)
	$(guard_published)
	uv run sprawl negative-control

lab:               ## rebuild the Proof Lab (evidence/lab-console.html)
	uv run sprawl lab

package:           ## the publication package: dist/f1-proof-pack-<run>.zip, redacted and scanned
	uv run sprawl package

proof-live:        ## a fresh live benchmark run (Ollama + gpt-oss:20b), recorded separately and never promoted automatically
	uv run sprawl run --preset full --run-id $(RUN_ID)

doctor:            ## what this machine has: Python, uv, the MCP SDK, Ollama and the models
	uv run sprawl doctor

all: doctor verify test replay docs qa   ## doctor, the published run verified, tests, replay, the editions and QA (nothing rewrites the run)

# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series setup demo docs qa

setup:         ## the environment (Python and the pinned dependencies, uv)
	uv sync

demo:          ## no single-scenario demo here: make replay replays recorded rows through the real stack
	@echo "F1 has no demo target: make replay replays recorded rows through the real stack; make verify checks the published run."

docs:          ## both editions (Markdown, HTML, PDF) and the static Medium edition, then the uniform series pages
	python3 tools/render.py medium/source/mcp-tool-sprawl-medium.src.md medium/mcp-tool-sprawl-medium.md --doc medium
	python3 tools/assemble_technical.py
	uv run --with markdown --with pypdf python tools/build_article.py medium/mcp-tool-sprawl-medium.md
	uv run --with markdown --with pypdf python tools/build_article.py technical/mcp-tool-sprawl-technical.md
	uv run --with markdown --with pillow python tools/build_medium_static.py
	$(MAKE) series

qa:            ## publication scan: no local path, host name or address in the editions, results and README
	PYTHONPATH=vendor python3 -m evidence_kit.publication medium technical results README.md

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium F1 && $(SERIES_TOOL) results F1 && $(SERIES_TOOL) readme F1
