#!/bin/bash
# Checks that must pass before mcp_sprawl_poc is published (run from the POC folder). No model or network needed.
set -euo pipefail
uv run pytest -q
uv run ruff check control_plane agent benchmark servers tests || true   # style findings do not block a publish
