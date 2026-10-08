#!/bin/zsh
# Runs after the blind run: E6, E7, E8 strictly in sequence (no overlap with any other run).
cd "$(dirname "$0")/.."
while pgrep -f "run-id 2026-10-08-blind" >/dev/null; do sleep 15; done
echo "E1 finished $(date)"; pkill -f coord.a2a_server; sleep 2
uv run python -m coord.freeze check || { echo "FROZEN CHECK FAILED"; exit 1; }
echo "E6 start $(date)"
uv run python -m coord.exp_failure --run-id 2026-10-08-e6 --repeats 3 > runs/2026-10-08-e6.log 2>&1; echo "E6 exit $? $(date)"
pkill -f coord.a2a_server; sleep 2
echo "E7 start $(date)"
uv run python -m coord.exp_boundary --run-id 2026-10-08-e7 --n 100 > runs/2026-10-08-e7.log 2>&1; echo "E7 exit $? $(date)"
pkill -f coord.a2a_server; sleep 2
echo "E8 start $(date)"
uv run python -m coord.bench matrix --run-id 2026-10-08-e8 --fixtures B1,B2,B3,B4,B5,B6,B7,B8 --archs C --repeats 1 --tape record \
  --overrides '{"ablation": true, "workflow": {"max_total_tokens": 600000}}' > runs/2026-10-08-e8.log 2>&1; echo "E8 exit $? $(date)"
pkill -f coord.a2a_server
echo "CHAIN DONE $(date)"
