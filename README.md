# AI blog POCs

Working proofs of concept for a series of articles on building AI agent systems that survive production. Each POC is a self-contained project in its own folder, runs on one laptop with local models through [Ollama](https://ollama.com), and records the numbers its article cites.

| Folder | Article | What it shows | Start here |
|---|---|---|---|
| [`mcp_sprawl_poc/`](mcp_sprawl_poc) | Part 1 — MCP tool sprawl | A capability control plane in front of many MCP tools: discovery, argument validation, policy and evidence, measured against catalogues of 50+ tools | [README](mcp_sprawl_poc/README.md) |
| [`layered_architecture_poc/`](layered_architecture_poc) | Part 2 — Your Agent Works in a Demo. Why Does It Break in Production? | One incident (INC-4917) through an agent monolith and a six-layer agent platform: 15 architecture invariants, the published numbers recomputed from raw evidence, outcome and fault-exposure accounting, and every claim checked against what it rests on | [README](layered_architecture_poc/README.md) |
| [`layered_agent_poc/`](layered_agent_poc) | — | Part 2's earlier implementation. Kept **only** because `headless_ai_poc` builds against it: a path dependency and four modules importing its `agent_platform` package. Not the place to start, and due for removal once Part 3 moves | [README](layered_agent_poc/README.md) |
| [`headless_ai_poc/`](headless_ai_poc) | Part 3 — a headless capability boundary | One versioned capability contract serving Slack, a web console, CLI, REST and alerts, on top of Part 2's platform | [README](headless_ai_poc/README.md) |

Each folder has its own `pyproject.toml`, tests and runs, and is installed on its own:

```bash
cd layered_architecture_poc && uv sync && uv run pytest -m "not model"
```

**One Part 2, and one leftover.** [`layered_architecture_poc/`](layered_architecture_poc) is Part 2: canonical
recorded run `2026-09-28-recorded`, evidence revision `r3`. `layered_agent_poc/` is the earlier implementation of the
same article, and it stays only because `headless_ai_poc` compiles against its `agent_platform` package. When Part 3
moves to its own dependency, that folder goes; its evidence stays addressable in git history at commit `05df9ba`.

**How they relate.** `headless_ai_poc` depends on `layered_agent_poc` as a local path dependency (`layered-agent-platform = { path = "../layered_agent_poc", editable = true }`) and uses only its service facade. That is the one dependency across folders; nothing else crosses: no folder reads another's databases, runs or configuration.

**Publishing.** Several people and sessions publish here in parallel. [PUBLISHING.md](PUBLISHING.md) has the rules and the script that enforces them.

Licence: MIT, per folder.
