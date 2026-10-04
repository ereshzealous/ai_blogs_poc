# AI blog POCs

Working proofs of concept for a series of articles on building AI agent systems that survive production. Each POC is a self-contained project in its own folder, runs on one laptop with local models through [Ollama](https://ollama.com), and records the numbers its article cites.

| Folder | Article | What it shows | Start here |
|---|---|---|---|
| [`mcp_sprawl_poc/`](mcp_sprawl_poc) | Part 1 — MCP tool sprawl | A capability control plane in front of many MCP tools: discovery, argument validation, policy and evidence, measured against catalogues of 50+ tools | [README](mcp_sprawl_poc/README.md) |
| [`layered_agent_poc_r3/`](layered_agent_poc_r3) | Part 2 — Your Agent Works in a Demo. Why Does It Break in Production? **(current)** | One incident (INC-4917) through an agent monolith and a six-layer agent platform, standardized: 15 architecture invariants, the published numbers recomputed from raw evidence, outcome and fault-exposure accounting, claims classified against their evidence | [README](layered_agent_poc_r3/README.md) |
| [`layered_agent_poc/`](layered_agent_poc) | Part 2 — the historical edition | The earlier implementation and its evidence, kept because published material cites it. Still complete and still verifiable; superseded for new readers by `layered_agent_poc_r3/` | [README](layered_agent_poc/README.md) |
| [`headless_ai_poc/`](headless_ai_poc) | Part 3 — a headless capability boundary | One versioned capability contract serving Slack, a web console, CLI, REST and alerts, on top of Part 2's platform | [README](headless_ai_poc/README.md) |

Each folder has its own `pyproject.toml`, tests and runs, and is installed on its own:

```bash
cd layered_agent_poc_r3 && uv sync && uv run pytest -m "not model"
```

**Two editions of Part 2.** `layered_agent_poc_r3/` is the one to read: canonical recorded run
`2026-09-28-recorded`, evidence revision `r3`, with architecture invariants, raw recomputation, standardized outcome
accounting and claim-to-evidence verification. `layered_agent_poc/` is the historical edition, preserved because
earlier published material cites its run `2026-09-17-recorded`; it is neither invalid nor broken, and its evidence
chain stays addressable. Each edition's numbers belong to its own run, and the two use different experiment-id
schemes, so cite the run as well as the experiment.

**How they relate.** `headless_ai_poc` depends on `layered_agent_poc` as a local path dependency (`layered-agent-platform = { path = "../layered_agent_poc", editable = true }`) and uses only its service facade. Nothing else crosses folder boundaries: no folder reads another's databases, runs or configuration.

**Publishing.** Several people and sessions publish here in parallel. [PUBLISHING.md](PUBLISHING.md) has the rules and the script that enforces them.

Licence: MIT, per folder.
