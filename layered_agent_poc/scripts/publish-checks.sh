#!/usr/bin/env bash
# What must pass before this POC is published (see ../../PUBLISHING.md, rule 4).
set -euo pipefail
cd "$(dirname "$0")/.."
echo "-- fast tests"
uv run pytest -m "not ollama" -q
echo "-- layer contracts"
uv run lint-imports
echo "-- plans load and validate"
uv run python -c "
from experiments import plan
for name in plan.available():
    plan.load(name)
print(f'{len(plan.available())} plans OK')"
