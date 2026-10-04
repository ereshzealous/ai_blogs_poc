# AI blog POCs

Working proofs of concept for a series of articles on building AI agent systems that survive production. Each POC is a self-contained project in its own folder, runs on one laptop with local models through [Ollama](https://ollama.com), and records the numbers its article cites.

| Folder | Article | What it shows | Start here |
|---|---|---|---|
| [`mcp_sprawl_poc/`](mcp_sprawl_poc) | Part 1 — MCP tool sprawl | A capability control plane in front of many MCP tools: discovery, argument validation, policy and evidence, measured against catalogues of 50+ tools | [README](mcp_sprawl_poc/README.md) |
| [`layered_architecture_poc/`](layered_architecture_poc) | Part 2 — Your Agent Works in a Demo. Why Does It Break in Production? | One incident (INC-4917) through an agent monolith and a six-layer agent platform: 15 architecture invariants, the published numbers recomputed from raw evidence, outcome and fault-exposure accounting, and every claim checked against what it rests on | [README](layered_architecture_poc/README.md) |
| [`headless_ai_poc/`](headless_ai_poc) | Part 3 — a headless capability boundary | One versioned capability contract serving Slack, a web console, CLI, REST and alerts, on top of Part 2's platform | [README](headless_ai_poc/README.md) |

Each folder has its own `pyproject.toml`, tests and runs, and is installed on its own:

```bash
cd layered_architecture_poc && uv sync && uv run pytest -m "not model"
```

**Part 2's earlier folder is gone.** `layered_agent_poc/` was removed on 2026-10-04; `layered_architecture_poc/` is
Part 2. Nothing is lost: the old folder, including the run `2026-09-17-recorded` that the first edition of the article
cites, stays addressable at the tag `layered_agent_poc-final`.

```bash
git checkout layered_agent_poc-final -- layered_agent_poc    # restore it anywhere you need it
```

**How they relate.** `headless_ai_poc` and `memory_context_state_poc` were built against the removed `layered_agent_poc` (`layered-agent-platform = { path = "../layered_agent_poc", editable = true }`). Until they repoint, restore it from the tag above beside them, or vendor the part they use. `layered_architecture_poc` is a different implementation — its package is `layered_platform`, not `agent_platform` — so it is not a drop-in replacement. Nothing else crosses folder boundaries: no folder reads another's databases, runs or configuration.

**Publishing.** Several people and sessions publish here in parallel. [PUBLISHING.md](PUBLISHING.md) has the rules and the script that enforces them.

Licence: MIT, per folder.
