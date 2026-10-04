#!/usr/bin/env sh
# The checks scripts/publish-poc.sh runs before a publish: lint, the tests, the replay of every proof, the proof pack
# recomputed byte for byte, and PROOF VERIFICATION (no model, no network). PROOF VERIFICATION rewrites
# evidence/verification/ with the same bytes when the evidence holds.
set -e
export PYTHONDONTWRITEBYTECODE=1
make all
