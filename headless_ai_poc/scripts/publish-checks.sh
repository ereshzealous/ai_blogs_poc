#!/usr/bin/env bash
# Checks to pass before headless_ai_poc is published. Run from this folder; no Ollama needed.
#
#   scripts/publish-checks.sh
#
# The replay uses the recorded model traffic of the reference run, so it also proves the published evidence still
# reproduces against whatever version of layered_agent_poc this POC sits next to.
set -euo pipefail
cd "$(dirname "$0")/.."

# A marker to compare against: anything in a neighbouring POC newer than this was written by the checks below.
marker=$(mktemp)
trap 'rm -f "$marker"' EXIT

echo "· tests"
uv run pytest -q

echo "· import contracts"
uv run lint-imports

echo "· experiments, replayed (no Ollama)"
OLLAMA_URL=http://127.0.0.1:9 uv run hai-exp run --replay --run-id publish-check
rm -rf runs/publish-check

echo "· nothing was written outside this folder"
# Bytecode caches are written by importing the dependency and are gitignored; anything else is a real stray.
strays=$(find ../layered_agent_poc -newer "$marker" -type f \
  -not -path '*/.git/*' -not -path '*/__pycache__/*' -not -name '*.pyc' 2>/dev/null | head -5 || true)
if [ -n "$strays" ]; then
  echo "FAIL: wrote into layered_agent_poc:" >&2
  echo "$strays" >&2
  exit 1
fi

echo "all checks passed"
