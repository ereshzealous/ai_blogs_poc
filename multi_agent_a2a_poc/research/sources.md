# Sources (C1)

Primary sources first. Every entry: URL, access date, what it supports in C1, and what it does **not** support.
Accessed 2026-10-07/08 unless stated.

## Protocols

| Key | Source | Supports | Does not support |
|---|---|---|---|
| `a2a-spec` | A2A Protocol Specification v1.0.1 — https://a2a-protocol.org/v1.0.1/specification/ (text: github.com/a2aproject/A2A/blob/v1.0.1/docs/specification.md, commit 3303592) | the 11 operations (§3.1, §5.3), task states (§4.1.3), server-generated task ids (§3.4.2), idempotency scope (§3.3.1), service parameters as headers (§3.2.6), authentication in headers and per-request (§7.3–7.4), agent-defined authorization (§7.5, §13.1), Appendix B on MCP | any claim about delegation chains, token exchange or scope narrowing (not defined); durable tasks or crash resumption (not defined) |
| `a2a-proto` | `specification/a2a.proto` at tag v1.0.1 (normative per spec §1.4) — https://github.com/a2aproject/A2A/blob/v1.0.1/specification/a2a.proto | exact enum and message names (`TASK_STATE_*`, `StreamResponse`, `SecurityScheme`) | — |
| `a2a-mcp` | "A2A and MCP" — https://a2a-protocol.org/latest/topics/a2a-and-mcp/ | "MCP is vertical … A2A is horizontal" (project's explanatory framing) | a normative rule that agents must use MCP internally |
| `a2a-1.0` | "Announcing A2A 1.0" — https://github.com/a2aproject/A2A/blob/main/docs/blog/posts/announcing-1.0.md | "MCP inside agents, A2A between agents" as shorthand; 1.0 release | — |
| `a2a-sdk` | a2a-python 1.2.2 — https://pypi.org/project/a2a-sdk/1.2.2/ , https://github.com/a2aproject/a2a-python | the server/client API used (`DefaultRequestHandler`, `InMemoryTaskStore`, `create_client`, JSON-RPC routes); 0.3 → 1.0 migration | protocol semantics beyond what the spec states |
| `a2a-lf` | Linux Foundation press release, 2025-06-23 — https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents | governance history | — |
| `a2a-aaif` | "A2A joins AAIF" — https://github.com/a2aproject/A2A/blob/main/docs/blog/posts/a2a-joins-aaif.md (2026-08-27) | current governance | — |
| `mcp-spec` | Model Context Protocol specification — https://modelcontextprotocol.io/specification/latest ; Python SDK `mcp==2.2.0` | tools over stdio as used by every arm | — |
| `rfc8693` | OAuth 2.0 Token Exchange, RFC 8693 — https://www.rfc-editor.org/rfc/rfc8693 | the actor-chain (`act`) model the POC simulates | that the POC implements the RFC (it simulates its semantics) |
| `w3c-tc` | W3C Trace Context — https://www.w3.org/TR/trace-context/ | the `traceparent` header carried over A2A | — |
| `otel-genai` | OpenTelemetry GenAI semantic conventions — https://opentelemetry.io/docs/specs/semconv/gen-ai/ | `gen_ai.*` attribute names | that our spans are complete GenAI semconv coverage |

## Engineering and research on agent architecture

| Key | Source | Supports | Does not support |
|---|---|---|---|
| `anthropic-bea` | Anthropic, "Building effective agents", 2024-12-19 — https://www.anthropic.com/engineering/building-effective-agents | the workflow/agent definitions ("predefined code paths" vs "LLMs dynamically direct their own processes"); "finding the simplest solution possible, and only increasing complexity when needed" | any measurement on our workload |
| `anthropic-mars` | Anthropic, "How we built our multi-agent research system", 2025-06-13 — https://www.anthropic.com/engineering/multi-agent-research-system | a production case where multi-agent wins (breadth-first research, parallel subagents); "multi-agent systems use about 15× more tokens than chats"; coding has "fewer truly parallelizable tasks" | that the ratio transfers to incident response; it is their data, not ours |
| `cognition-dbma` | Walden Yan (Cognition), "Don't Build Multi-Agents", 2025-06-12 — https://cognition.com/blog/dont-build-multi-agents | "Share context, and share full agent traces"; "Actions carry implicit decisions, and conflicting decisions carry bad results" | a measured comparison; the author later described specific multi-agent flows they adopted |
| `mast` | M. Cemri et al., "Why Do Multi-Agent LLM Systems Fail?", arXiv:2503.13657 (first submitted 2025-03-17) — https://arxiv.org/abs/2503.13657 | an empirical failure taxonomy over 7 frameworks: "(i) system design issues, (ii) inter-agent misalignment, and (iii) task verification" | anything about A2A or about deterministic workflows specifically |

## The series (consumed, not repeated)

F2 `layered_architecture/` + `f2_layer_architecture/` (layers, INC-4917); F3 `headless_ai/` (headless contract, §26
multi-agent sketch); S1 `memory_context_state/` ("Workflow state is not memory"); T1 `agent_identity/` (actor chain,
delegate never impersonate); T2 `auth_and_policy/` ("Delegated authority is an intersection, never a union"); T3
`human_in_the_loop/` (approval bound to the action); T5 `governance_for_ai_agents/` (lineage across boundaries); T6
`securing_tools_mcp/` (a peer's message is not authority); P1 `ai_architecture/` (the capstone, one agent); R1+R2
`evals_obs_reliability/` (execution certainty, recovery).

## Could not verify

- The exact AAIF acceptance date on aaif.io (Aug 17 vs Aug 27, 2026): the A2A repository's own post (2026-08-27) is cited.
- Whether a2a-sdk 1.2.x "cluster mode" re-executes a task whose replica crashed: not claimed; C1 uses the single-process
  `InMemoryTaskStore`.
