# MCP Tool Sprawl POC. Every target only calls the runner (uv run sprawl <command>); `make help` lists them.
RUN_ID ?= live-$(shell date +%Y%m%d-%H%M)
.PHONY: help verify test replay build doctor all live
help:     ## this list
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ ·/'
verify:   ## verify the published results from the public evidence, no model
	uv run sprawl verify
test:     ## the deterministic tests: real MCP server processes, no model
	uv run sprawl test
replay:   ## replay recorded rows through the real stack without the model
	uv run sprawl replay
build:    ## rebuild the estates, the seed world and the benchmark; keep them only if byte-identical
	uv run sprawl build
doctor:   ## what this machine has: Python, uv, the MCP SDK, Ollama and the models
	uv run sprawl doctor
all:      ## doctor, verify, test, replay
	uv run sprawl all
live:     ## a live benchmark run (Ollama + gpt-oss:20b) into experiment/runs/$(RUN_ID)/
	uv run sprawl run --preset full --run-id $(RUN_ID)
