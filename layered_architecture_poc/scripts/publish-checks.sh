#!/usr/bin/env bash
# What must pass before this POC is published (see ../../PUBLISHING.md, rule 4, in the target repository).
#
# This runs the POC-level gate only: the tests, the evidence pipeline and the claims. The bundle-level gate, which
# also checks the three publications, the figures and the Excalidraw scene, is `make verify-all` one directory up.
set -euo pipefail
cd "$(dirname "$0")/.."
RUN=$(cat runs/PUBLISHED)

echo "-- fast tests (everything except the live-model tests)"
uv run pytest -m "not model" -q

echo "-- the published run verifies, and its numbers are recomputed from the raw evidence"
uv run python scripts/verify_evidence.py "runs/$RUN" | tail -3

echo "-- every scenario carries an outcome class, with its fault exposure"
uv run python scripts/classify_outcomes.py "runs/$RUN" | head -1

echo "-- the architecture invariants are enforced, and every citation in them is real"
uv run pytest tests/architecture -q

echo "   $RUN: published run verified, invariants enforced"
