# The POC: a Capability Control Plane over real MCP

The Python project behind the benchmark: real MCP servers over stdio, the three experiment arms, the control plane, the
scorer and the frozen analysis. What it tests and what it measured are in the [repository README](../README.md); the
architecture is in [`DESIGN.md`](DESIGN.md).

| Real | Simulated |
|---|---|
| MCP servers as separate OS processes over stdio (official Python SDK) | The enterprise's systems of record: a deterministic SQLite world with an effects ledger, reset before every row |
| A local model, `gpt-oss:20b`, through Ollama (`truncate:false`, temperature 0, fixed seed) | Representatives' replies, supervisor decisions and outages, all scripted in the frozen benchmark |
| Retrieval, registry, binding, provenance, policy, approvals, gateway, audit, ledger | |

## Run it

From the repository root, `uv run sprawl <command>` runs every step in this POC's own locked environment; this
directory's `pyproject.toml` and lock file stay as they were frozen.

| Command | Needs the model? | What it does |
|---|---|---|
| `doctor` | no | what this machine has: Python, uv, the MCP SDK, Ollama and the models |
| `verify` | no | the public verification of the published results (see the repository README) |
| `test` | no | the deterministic tests, against real MCP server processes |
| `build` | no | rebuild the estates, the seed world and the benchmark; keep them only if byte-identical |
| `replay` | no (the embedding-cache snapshot is committed) | replay recorded rows through the real stack into `experiment/runs/replay-latest/` |
| `run` | yes: Ollama with `gpt-oss:20b` and `nomic-embed-text` | a live benchmark run into `experiment/runs/<run-id>/` |

The individual steps, if you prefer to run them yourself:

```bash
cd poc
uv sync

# build (deterministic): estates, registry, seed world, benchmark, label lint
uv run python -m sprawl_poc.catalog.build
uv run python -m sprawl_poc.world.seed
uv run python -m sprawl_poc.bench.cases
uv run python -m sprawl_poc.bench.lint

# deterministic tests (real MCP subprocesses; no model)
uv run pytest

# the frozen inputs against the current evidence revision
uv run python scripts/freeze.py --verify

# replay the ORD-4917 row without the model, then summarise the replay
uv run python scripts/verify_replay.py ../experiment/raw/blind-rerun-2026-10-01 --out ../experiment/runs/replay-latest \
    --cases BL-C03-1 --sizes 500 --arms C
uv run python scripts/summarize.py replay ../experiment/runs/replay-latest

# the public verification
uv run python scripts/public_verify.py
```

Replay and verification need no model: retrieval embeds text with `nomic-embed-text`, but the vector cache from the
recorded runs is committed as `data/embeddings-cache/nomic-embed-text.json.gz`, and the runner restores it when
`data/embeddings/` is missing.

## Technology stack

| Layer | Recorded runs | To reproduce |
|---|---|---|
| Machine | Apple-silicon laptop, macOS (arm64) | macOS, Linux or Windows, natively or with Docker |
| Runtime | Python 3.12, uv, `uv.lock` | uv, or Docker (pins both) |
| MCP | `mcp` 2.2.0, low-level `Server`, stdio, revision 2026-07-28 | from the lock file |
| Model | Ollama, `gpt-oss:20b` | live runs only; plan on 16 GB or more of memory |
| Retrieval | `nomic-embed-text` + BM25, reciprocal-rank fusion | cache snapshot committed |
| Systems of record | SQLite (standard library) | nothing extra |
| Libraries | `jsonschema`, `numpy`, `pyyaml`, `pytest` | from the lock file |

## Layout

```
src/sprawl_poc/
  world/          simulated systems of record (schema, seed, handlers, effects ledger)
  catalog/        core estate + generated business units -> nested 50/100/500 estates
  servers/        one real MCP server process per system (low-level SDK Server, stdio)
  mcp_host.py     host side: launch servers, tools/list, tools/call, protocol record
  registry/       platform-owned governance registry (separate from what servers publish)
  discovery/      hybrid retrieval (BM25 + nomic-embed-text, RRF)
  control_plane/  entity context, capability collapse, binder, provenance, policy,
                  approvals, gateway (HMAC-signed calls), hash-chained audit
  agent/          Ollama client, playbook prompt, the three experiment arms, agent loop
  bench/          cases + labels, lint, runner, scorer, analysis, hypotheses
data/             estates, registries and server specs; the seed world; the embedding-cache snapshot
scripts/          doctor, freeze, replay verification, summaries, the public verification
tests/            deterministic tests: policy, approvals, audit, gateway bypass, scorer
```

All persons, orders, payments and enterprise records in the data are synthetic benchmark fixtures.
