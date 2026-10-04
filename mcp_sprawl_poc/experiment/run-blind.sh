#!/bin/zsh
# Blind run from the FREEZE commit (see experiment/preregistration.md §8).
set -u
cd "$(dirname "$0")/../poc"
uv run python scripts/freeze.py --verify || exit 1
uv run python -m sprawl_poc.bench.runner --split blind --sizes 50 100 500 --arms C B A --out ../experiment/raw/blind-main
# Preregistered repeat pass (noise floor): C at all sizes, B at 500.
uv run python -m sprawl_poc.bench.runner --split blind --sizes 50 100 500 --arms C --out ../experiment/raw/blind-repeat
uv run python -m sprawl_poc.bench.runner --split blind --sizes 500 --arms B --out ../experiment/raw/blind-repeat
