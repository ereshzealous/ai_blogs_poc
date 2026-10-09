#!/usr/bin/env sh
# The checks scripts/publish-poc.sh runs before a publish, the same in every chapter: the reader's three commands, with
# no model reachable. None of them writes to the published run.
set -e
export PYTHONDONTWRITEBYTECODE=1
export OLLAMA_URL=http://127.0.0.1:1 OLLAMA_HOST=127.0.0.1:1
make setup
make test
make verify
