# C1 · Multi-agent systems & A2A: the published POC.  `make help` lists the targets.
POC := coordination_poc
RUN  = $(shell cat $(POC)/runs/PUBLISHED)

.PHONY: help setup test verify replay

help:     ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-8s %s\n", $$1, $$2}'

setup:    ## Python 3.12 and the pinned dependencies (uv, from uv.lock)
	cd $(POC) && uv sync --locked --group dev

test:     ## the 64 tests: identity, policy, gateway over real MCP, runtime, real A2A agent processes (no model)
	cd $(POC) && uv run --locked --group dev pytest -q

verify:   ## frozen inputs, the published run's replay check, the tests (no model; writes nothing tracked)
	cd $(POC) && uv run --locked python -m coord.freeze check
	cd $(POC) && uv run --locked python -m coord.verify_replay $(RUN)
	$(MAKE) test

replay:   ## re-execute all 72 blind workflows from the model tape (no model), then compare; rewrites runs/<run>/replay/
	cd $(POC) && uv run --locked python -m coord.bench matrix --run-id $(RUN) --fixtures B1,B2,B3,B4,B5,B6,B7,B8 \
	    --archs A,B,C --repeats 3 --tape replay --overrides '{"multi_agent_c": {"execute_without_proposal": "all_writes"}}'
	cd $(POC) && uv run --locked python -m coord.verify_replay $(RUN)
