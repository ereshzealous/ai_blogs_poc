# P1 · Production Agentic AI Platform POC: the Proof Contract v1 targets. Every target only calls the runner
# (uv run pap <command>), the one implementation; `make help` lists them. Promotion is not a make target: uv run pap promote.
RUN_ID ?= local-$(shell date +%Y%m%d-%H%M%S)

.PHONY: help verify test proof replay negative-control pack lab package all

help:              ## this list
	@grep -E '^[a-z-]+:.*## ' Makefile | sed -E 's/:[^#]*## /|/' | awk -F'|' '{printf "  make %-17s %s\n", $$1, $$2}'

verify:            ## PROOF VERIFICATION of the published run: reads the shipped evidence, runs no proof
	uv run pap verify

test:              ## the deterministic unit tests (implementation tests, not proof checks)
	uv run pap test

proof:             ## a fresh proof into a new run (RUN_ID=...): run, replay, negative control, pack, verify; never published
	uv run pap proof --run-id $(RUN_ID)

replay:            ## replay the published run into scratch and classify it against the recorded run
	uv run pap replay

negative-control:  ## the approval requirement removed, into scratch: the invariant must break cleanly
	uv run pap negative-control

pack:              ## recompute the published run's proof pack and compare it byte for byte
	uv run pap pack

lab:               ## rebuild the Proof Lab of the published run (lab/index.html)
	uv run pap lab

package:           ## the publication package: redacted, scanned, hashed (dist/)
	uv run pap package

all:               ## the pipeline: test, verify, replay, negative control, pack, lab
	uv run pap all
