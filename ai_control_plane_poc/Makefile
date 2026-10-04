# T4 · AI Control Plane POC, as published: the POC (control_plane_poc/), its proof pack (proof/, evidence/) and the
# verifiers (tools/). No model, no API key, no network.  `make help` lists the targets.
POC    := control_plane_poc
RUN    := $(shell cat $(POC)/runs/PUBLISHED)
P      ?=

.PHONY: help setup lint test demo proof live live-dry verify pack-check evidence all

help:       ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-11s %s\n", $$1, $$2}'

setup:      ## the POC environment (uv installs Python 3.12, pyyaml, pytest, ruff)
	cd $(POC) && uv sync --group dev

lint:       ## ruff format check + ruff lint on the POC
	cd $(POC) && uv run ruff format --check . && uv run ruff check .

test:       ## POC tests: architecture (agents hold no governance), cheating detection, decisions, every proof
	cd $(POC) && uv run pytest

demo:       ## P2: one central change, same agent code, same runtime process, different behaviour
	cd $(POC) && uv run acp demo

proof:      ## proof cards for any proofs, in a scratch run (e.g. make proof P="P2 P4 P9")
	cd $(POC) && uv run acp proof $(P)

live:       ## L1–L3 with a self-hosted LLM (Ollama, qwen3:8b) planning the agent -> runs/live/<id>/ (illustrative)
	ollama list | grep -q "qwen3:8b" || (echo "pull the local model first: ollama pull qwen3:8b" && exit 1)
	cd $(POC) && uv run acp live

live-dry:   ## L1–L3 end to end with a scripted stand-in model (no Ollama needed) -> runs/live/<id>/
	cd $(POC) && uv run acp live --backend scripted

verify:     ## rerun every proof into a fresh copy of the POC and compare with the published run (pids masked, nothing else)
	python3 tools/verify_run.py

pack-check: ## recompute the proof pack from the raw run and compare it byte for byte with evidence/runs/<run>/
	uv run --project $(POC) python tools/proof_pack.py build $(RUN)

evidence:   ## PROOF VERIFICATION of the published run -> evidence/verification/verification.{txt,json}
	uv run --project $(POC) python tools/verify_evidence.py

all: lint test verify pack-check evidence   ## every check a reader can run, in order
