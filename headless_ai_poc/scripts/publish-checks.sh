#!/usr/bin/env sh
# The checks scripts/publish-poc.sh runs before a publish: the deterministic tests and the evidence verification,
# read-only (no model, no network).
set -e
export PYTHONDONTWRITEBYTECODE=1
uv run pytest -q
uv run hai verify --check
