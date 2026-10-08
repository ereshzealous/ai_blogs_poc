# AI blog POCs

Working proofs of concept for a series of articles on building AI agent systems that survive production. Each POC is a self-contained project in its own folder, runs on one laptop (with local models through [Ollama](https://ollama.com) where it uses a model), and records the numbers its article cites.

| Folder | Article | What it shows | Start here |
|---|---|---|---|
| [`mcp_sprawl_poc/`](mcp_sprawl_poc) | Part 1 — MCP tool sprawl | A capability control plane in front of many MCP tools: discovery, argument validation, policy and evidence, measured against catalogues of 50+ tools | [README](mcp_sprawl_poc/README.md) |
| [`layered_architecture_poc/`](layered_architecture_poc) | Part 2 — Your Agent Works in a Demo. Why Does It Break in Production? | One incident (INC-4917) through an agent monolith and a six-layer agent platform: 15 architecture invariants, the published numbers recomputed from raw evidence, outcome and fault-exposure accounting, and every claim checked against what it rests on | [README](layered_architecture_poc/README.md) |
| [`layered_agent_platform/`](layered_agent_platform) | — (shared) | Part 2's earlier implementation, kept as a library: `memory_context_state_poc` builds against its `agent_platform` package (as did the first `headless_ai_poc`, kept at the tag `headless_ai_poc-2026-09-17`), and the run `2026-09-17-recorded` behind the first edition of the article lives here. Not where a new reader starts | [README](layered_agent_platform/README.md) |
| [`headless_ai_poc/`](headless_ai_poc) | Part 3 — Headless AI: Your AI Shouldn't Live Inside the UI | One incident-intelligence runtime (payment-service, 14% errors) consumed by eight heads — event, chat, web, API, workflow, scheduler, CI/CD and another agent — through one contract and one governed capability layer. Deterministic, no model: 30 architecture checks and `uv run hai verify` | [README](headless_ai_poc/README.md) |
| [`ai_control_plane_poc/`](ai_control_plane_poc) | T4 — AI Control Plane | Three agents in one long-lived runtime, governed by a separate control plane that versions, signs and distributes their desired state. One central change (P2) turns the same process, code and request from ALLOW into APPROVAL_REQUIRED, with 0 agent edits and 0 redeploys; P1–P12 with a negative control, and a public verifier (`make all`). No model needed | [README](ai_control_plane_poc/README.md) |
| [`multi_agent_a2a_poc/`](multi_agent_a2a_poc) | C1 — Do You Actually Need Multiple Agents? | One incident-investigation capability implemented three ways — one agent, a deterministic workflow with agents, and a coordinator with four agents over A2A v1.0 — on 8 blind incidents × 3 repeats with `gpt-oss:20b`. The workflow with agents had the most successes at the lowest cost; the coordination tax dominated and the A2A boundary was cheap on loopback. Process kills, the A2A boundary's own cost, termination without an owner, and a replay of all 72 workflows without a model (`make verify`) | [README](multi_agent_a2a_poc/README.md) |
| [`agent_mcp_security_poc/`](agent_mcp_security_poc) | T6 — Securing Agents, Tools & MCP | A red-team assurance harness: a worst-case-compliant model proposes hostile actions and a trusted registry, identity, policy, approval, MCP gateway and egress boundary decide what executes. 19 attacks across 8 classes under three arms — system compromised 19/19 (vulnerable) → 13/19 (classifier) → 0/19 (hardened) — with the claim boundary measured and a public verifier (`uv run redteam verify`). Deterministic, synthetic, no model | [README](agent_mcp_security_poc/README.md) |

Each folder has its own `pyproject.toml`, tests and runs, and is installed on its own:

```bash
cd layered_architecture_poc && uv sync && uv run pytest -m "not model"
```

**One Part 2, and one shared platform.** [`layered_architecture_poc/`](layered_architecture_poc) is Part 2: the
standardized edition, canonical run `2026-09-28-recorded`, evidence revision `r3`.
[`layered_agent_platform/`](layered_agent_platform) is the earlier implementation, renamed from `layered_agent_poc`
because it is no longer a POC folder in its own right: it is the library `memory_context_state_poc` builds
against, through its `agent_platform` package (the first `headless_ai_poc` did too), and it holds the run the first
edition of the article cites. The two are not copies of each other — they share 14 file paths out of about 1,100,
three of them identical, with different packages (`agent_platform` against `layered_platform`), different recorded
runs and different results.

**How they relate.** `memory_context_state_poc` imports `layered_agent_platform`'s `agent_platform` package. `headless_ai_poc` is self-contained since it was rebuilt for F3; its first version, which depended on `layered_agent_platform` as a local path dependency, is kept at the tag `headless_ai_poc-2026-09-17`. `layered_architecture_poc` is a separate implementation — its package is `layered_platform`, not `agent_platform` — so it is not a drop-in replacement for either. Nothing else crosses folder boundaries: no folder reads another's databases, runs or configuration.

**Publishing.** Several people and sessions publish here in parallel. [PUBLISHING.md](PUBLISHING.md) has the rules and the script that enforces them.

Licence: MIT, per folder.
