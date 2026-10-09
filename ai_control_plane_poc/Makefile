# T4 · AI Control Plane: one command surface for the whole package.  `make help` lists the targets.
POC    := control_plane_poc
RUN    := $(shell cat $(POC)/runs/PUBLISHED)
DOCPY  := uv run --project $(POC) --with markdown --with pypdf python
P      ?=


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

.PHONY: help setup lint test demo proof live live-dry run verify pack evidence verify-all console diagrams export manifest docs qa public all

help:       ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-10s %s\n", $$1, $$2}'

setup:      ## the POC environment (Python 3.12, pyyaml, pytest, ruff)
	cd $(POC) && uv sync --group dev

lint:       ## ruff format check + ruff lint on the POC
	cd $(POC) && uv run ruff format --check . && uv run ruff check .

test:       ## POC tests: architecture (agents hold no governance), decisions, every proof (no model, no network)
	cd $(POC) && uv run pytest

demo:       ## P2 only: one central change, same agent code, same runtime process, different behaviour
	cd $(POC) && uv run acp demo

proof:      ## proof cards for P1–P12 into a scratch run (e.g. make proof P="P2 P4 P9")
	cd $(POC) && uv run acp proof $(P)

live:       ## L1–L3 with a self-hosted LLM (Ollama, qwen3:8b) planning the agent -> runs/live/<id>/ (illustrative)
	ollama list | grep -q "qwen3:8b" || (echo "pull the local model first: ollama pull qwen3:8b" && exit 1)
	cd $(POC) && uv run acp live

live-dry:   ## L1–L3 end to end with a scripted stand-in model (no Ollama needed) -> runs/live/<id>/
	cd $(POC) && uv run acp live --backend scripted

run:        ## AUTHOR ONLY (rewrites the published run): P1–P12 -> control_plane_poc/runs/<PUBLISHED>/ (incl. scenarios/); the Lab Console follows the run
	$(guard_published)
	cd $(POC) && uv run acp experiments --run-id $(RUN)
	$(DOCPY) tools/build_lab_console.py $(RUN)

verify:     ## rerun every proof into a fresh copy of the POC and compare with the published run (pids masked, nothing else)
	python3 tools/verify_run.py

pack:       ## AUTHOR ONLY (rewrites the published run): pae-proof/v1 proof pack of the published run -> evidence/runs/<run>/ (replay record, results, checks, SHA256SUMS)
	$(guard_published)
	python3 tools/verify_run.py --record
	uv run --project $(POC) python tools/proof_pack.py build $(RUN) --write

evidence:   ## PROOF VERIFICATION of the published run -> evidence/verification/verification.{txt,json}
	uv run --project $(POC) python tools/verify_evidence.py

verify-all: ## final gate: lint, tests, replay, proof pack, PROOF VERIFICATION, docs, figures, Lab Console -> verification/
	python3 tools/verify_all.py

console:    ## the Lab Console (every scenario: input, output, steps, lineage, outcome) -> results/lab-console.html
	$(DOCPY) tools/build_lab_console.py $(RUN)

diagrams:   ## figure skeletons from code + the published run's facts
	python3 diagrams/tools/figures_t4.py

export:     ## skeletons -> .excalidraw + SVG + PNG@2x (headless Chrome + @excalidraw/excalidraw from esm.sh)
	cd diagrams/tools && python3 export_premium.py

manifest:   ## diagrams/manifest.json (provenance, files, Excalidraw+ frames)
	python3 tools/diagram_manifest.py

docs: manifest   ## both editions and the three evidence documents (results/) as Markdown, standalone HTML and PDF
	python3 tools/build_results.py
	$(DOCPY) tools/build_docs.py
	$(MAKE) series

qa:         ## rendered checks at desktop/tablet/mobile (editions, evidence documents, Lab Console) + screenshots -> qa/
	node tools/qa_pages.mjs
	node tools/qa_console.mjs

public:     ## assemble the published POC folder (GitHub: ai_blogs_poc/ai_control_plane_poc/) into OUT=<empty dir>
	python3 tools/stage_public.py $(OUT)

all: lint test diagrams export docs evidence qa verify-all   ## everything, in order

# ---- standard series targets ----------------------------------------------------------------------------------
.PHONY: series replay

replay:        ## the same as make verify: every proof rerun in a fresh copy of the POC and compared
	$(MAKE) verify

series:        ## the uniform Medium edition, results page and README (reads the published run, never writes it)
	$(SERIES_TOOL) medium T4 && $(SERIES_TOOL) results T4 && $(SERIES_TOOL) readme T4
