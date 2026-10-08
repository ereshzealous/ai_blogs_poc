#!/usr/bin/env sh
# The checks scripts/publish-poc.sh runs before a publish: the pinned environment, the frozen inputs, the replay check of
# the published run and the tests (no model, no network beyond loopback). Nothing here writes to a tracked file.
set -e
export PYTHONDONTWRITEBYTECODE=1
make setup
make verify
