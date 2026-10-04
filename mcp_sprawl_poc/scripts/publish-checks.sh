#!/usr/bin/env sh
# The checks scripts/publish-poc.sh runs before a publish: the public verification and the deterministic tests.
set -e
export PYTHONDONTWRITEBYTECODE=1
uv run sprawl verify
uv run sprawl test
