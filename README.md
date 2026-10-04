# AI blog POCs

Working proofs of concept for a series of articles on building AI agent systems that survive production. Each POC is a self-contained project in its own folder, runs on one laptop with local models through [Ollama](https://ollama.com), and records the numbers its article cites.

| Folder | Article | What it shows | Start here |
|---|---|---|---|
| [`mcp_sprawl_poc/`](mcp_sprawl_poc) | Part 1 — MCP tool sprawl | A capability control plane in front of many MCP tools: discovery, argument validation, policy and evidence, measured against catalogues of 50+ tools | [README](mcp_sprawl_poc/README.md) |
| [`layered_architecture_poc/`](layered_architecture_poc) | Part 2 — Your Agent Works in a Demo. Why Does It Break in Production? | One incident (INC-4917) through an agent monolith and a six-layer agent platform: 15 architecture invariants, the published numbers recomputed from raw evidence, outcome and fault-exposure accounting, and every claim checked against what it rests on | [README](layered_architecture_poc/README.md) |
| [`layered_agent_platform/`](layered_agent_platform) | — (shared) | Part 2's earlier implementation, kept as a library: `headless_ai_poc` and `memory_context_state_poc` build against its `agent_platform` package, and the run `2026-09-17-recorded` behind the first edition of the article lives here. Not where a new reader starts | [README](layered_agent_platform/README.md) |
| [`headless_ai_poc/`](headless_ai_poc) | Part 3 — a headless capability boundary | One versioned capability contract serving Slack, a web console, CLI, REST and alerts, on top of Part 2's platform | [README](headless_ai_poc/README.md) |

Each folder has its own `pyproject.toml`, tests and runs, and is installed on its own:

```bash
cd layered_architecture_poc && uv sync && uv run pytest -m "not model"
```

**One Part 2, and one shared platform.** [`layered_architecture_poc/`](layered_architecture_poc) is Part 2: the
standardized edition, canonical run `2026-09-28-recorded`, evidence revision `r3`.
[`layered_agent_platform/`](layered_agent_platform) is the earlier implementation, renamed from `layered_agent_poc`
because it is no longer a POC folder in its own right: it is the library `headless_ai_poc` and
`memory_context_state_poc` build against, through its `agent_platform` package, and it holds the run the first
edition of the article cites. The two are not copies of each other — they share 14 file paths out of about 1,100,
three of them identical, with different packages (`agent_platform` against `layered_platform`), different recorded
runs and different results.

**How they relate.** `headless_ai_poc` depends on `layered_agent_platform` as a local path dependency (`layered-agent-platform = { path = "../layered_agent_platform", editable = true }`) and uses only its service facade; `memory_context_state_poc` imports the same package. `layered_architecture_poc` is a separate implementation — its package is `layered_platform`, not `agent_platform` — so it is not a drop-in replacement for either. Nothing else crosses folder boundaries: no folder reads another's databases, runs or configuration.

**Publishing.** Several people and sessions publish here in parallel. [PUBLISHING.md](PUBLISHING.md) has the rules and the script that enforces them.

Licence: MIT, per folder.
