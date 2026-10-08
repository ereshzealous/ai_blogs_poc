# A2A research notes (C1)

Read before any protocol claim in the article. Accessed 2026-10-07/08. Everything below was checked against the
tagged specification, not against blog posts.

## Version pinned by this POC

| What | Value | Where it is checked |
|---|---|---|
| Specification | **A2A v1.0.1** (tag `v1.0.1`, commit `3303592588e388e62e0f69f701af531d2f4e3991`; v1.0.0 released 2026-03-12, v1.0.1 a bug-fix patch published 2026-05-26/28) | `research/sources.md` |
| Normative definition | `specification/a2a.proto` at that tag (spec §1.4: the proto is "the single authoritative normative definition"). sha256 `e195bf96ab630c69797851970203e1b2b6b19528f2e9803b7d904b91a5104016` | snapshot hash |
| Spec text | `docs/specification.md` at that tag, sha256 `627ccfe6ffb1be2c56811c3dcc18780deb419f41cdc98248095c939b2d9dc9cb` | snapshot hash |
| Wire protocol version | `"1.0"` (patch versions are not negotiated, §3.6) | Agent Card `supportedInterfaces[].protocolVersion` |
| Python SDK | `a2a-sdk==1.2.2` (PyPI, uploaded 2026-10-05), extra `http-server` | `coordination_poc/pyproject.toml`, `uv.lock` |
| Binding used | JSON-RPC 2.0 over HTTP (§9). gRPC (§10) and HTTP+JSON/REST (§11) exist; not used | Agent Cards |
| Governance | Linux Foundation project (launched 2025-06-23); accepted into the Agentic AI Foundation (LF) as a growth-stage project (A2A blog, 2026-08-27). Steering committee: Google, Microsoft, Cisco, AWS, Salesforce, ServiceNow, SAP, IBM | `research/sources.md` |

Cite the stable URL `https://a2a-protocol.org/v1.0.1/specification/`, not `/latest/` (which tracks the dev branch).

## The complete operation set (§3.1, §5.3)

Eleven operations. The article must never present a subset as the protocol.

| § | Operation | JSON-RPC method | Used by this POC |
|---|---|---|---|
| 3.1.1 | Send Message | `SendMessage` | served by every agent; not used by the coordinator (its client prefers streaming because the cards declare it) |
| 3.1.2 | Send Streaming Message | `SendStreamingMessage` | **yes**: every delegation (SSE stream: the task, its status updates `SUBMITTED → WORKING → COMPLETED`, the artifact) |
| 3.1.3 | Get Task | `GetTask` | **yes**: probe of the old task id after an agent restart (E6, tests) |
| 3.1.4 | List Tasks | `ListTasks` | no |
| 3.1.5 | Cancel Task | `CancelTask` | implemented on the delegation-timeout path; no delegation timed out in the recorded runs, so not exercised there |
| 3.1.6 | Subscribe to Task | `SubscribeToTask` | no |
| 3.1.7 | Create Push Notification Config | `CreateTaskPushNotificationConfig` | no |
| 3.1.8 | Get Push Notification Config | `GetTaskPushNotificationConfig` | no |
| 3.1.9 | List Push Notification Configs | `ListTaskPushNotificationConfigs` | no |
| 3.1.10 | Delete Push Notification Config | `DeleteTaskPushNotificationConfig` | no |
| 3.1.11 | Get Extended Agent Card | `GetExtendedAgentCard` | no |

Agent discovery is not an operation: the Agent Card is served at `/.well-known/agent-card.json` (§8). The POC
resolves every agent through its card.

## Concepts used, with their exact v1.0.1 names

- **Agent Card** (`AgentCard`): `name`, `description`, `version`, `supportedInterfaces[]` (`url`, `protocolBinding`,
  `protocolVersion`), `capabilities` (`streaming`, `pushNotifications`, `extendedAgentCard`), `defaultInputModes`,
  `defaultOutputModes`, `skills[]` (`AgentSkill`: `id`, `name`, `description`, `tags`), `securitySchemes`,
  `securityRequirements`.
- **Task** (`Task`): `id` (always server-generated, §3.4.2: client-provided task ids for new tasks are not
  supported), `contextId`, `status` (`TaskStatus`: `state`, `message`, `timestamp`), `artifacts`, `history`.
- **TaskState** (proto enum): `TASK_STATE_UNSPECIFIED`, `TASK_STATE_SUBMITTED`, `TASK_STATE_WORKING`,
  `TASK_STATE_COMPLETED`, `TASK_STATE_FAILED`, `TASK_STATE_CANCELED`, `TASK_STATE_INPUT_REQUIRED`,
  `TASK_STATE_REJECTED`, `TASK_STATE_AUTH_REQUIRED`. Terminal: completed, failed, canceled, rejected. Interrupted:
  input-required, auth-required.
- **Message** (`Message`): `messageId`, `role` (`ROLE_USER` / `ROLE_AGENT`), `parts`, `contextId`, `taskId`,
  `metadata`.
- **Part**: one type carrying exactly one of `text`, `raw`, `url`, `data` (+ `mediaType`, `filename`, `metadata`).
  The POC sends and receives `data` parts (structured JSON).
- **Artifact** (`Artifact`): `artifactId`, `name`, `parts`. Every specialist returns its result as one data artifact.
- **Service parameters** (§3.2.6): binding-defined key/value context; for HTTP bindings they are HTTP headers. The
  POC sends `Authorization` and W3C `traceparent` as headers.

## What the protocol does and does not give us (drives the article's state/ownership sections)

- §3.3.1 Idempotency: Get operations are naturally idempotent; **Send Message "MAY be idempotent. Agents may utilize
  the messageId to detect duplicate messages."** Cancel is idempotent. Nothing stronger.
- §3.4.2: a task id is created by the server. A retried delegation to a restarted agent is therefore a *new* A2A task.
- The specification text does not define durable tasks, resumption of a task after a server crash, or
  application-level idempotency keys (searched: crash, durable, resume, restart: no normative text). The SDK's
  `InMemoryTaskStore` loses tasks on restart; `DatabaseTaskStore` persists them but nothing re-executes them.
- **Conclusion used in the article**: the A2A task lifecycle is the *protocol* state of one delegation. The
  business workflow's truth (what was decided, what executed, what may be retried) must be owned by the
  application. This is a reading of the spec's scope, stated as such, not a quotation.
- **Wording rule (post-review, 2026-10-08)**: E6's lost task is a property of the POC's choice of the SDK's
  `InMemoryTaskStore`, not of A2A. Say "the A2A task in this implementation did not survive the agent process because
  the POC used the SDK's in-memory TaskStore"; never "A2A loses tasks". And even a durable A2A task should not
  automatically become the source of truth for a business workflow.
- **Wording rule (post-review)**: E7 and the live boundary figures are loopback HTTP on one machine without TLS. Claim
  "the A2A boundary was cheap here / in this local deployment", never "A2A has no cost".

## Security (§7, §13)

- §7: "Identity information is handled at the protocol layer, not within A2A semantics." Credentials are obtained
  out-of-band and sent "in protocol-appropriate headers or metadata for every A2A request" (§7.3). The server
  "MUST authenticate every incoming request" (§7.4). Authorization is implementation-specific (§7.5) and MAY
  consider skills, actions, data access, OAuth scopes.
- §7.6 In-Task Authorization: `TASK_STATE_AUTH_REQUIRED` lets an agent hand an authorization need back to its client.
- §13.1: servers MUST scope every operation to the caller's authorization boundaries; "Authorization boundaries are
  defined by each agent's authorization model, not prescribed by the protocol".
- **Not defined by A2A**: delegation chains, token exchange, scope narrowing across hops. The POC therefore reuses the
  series' own delegation model (T1: RFC 8693-style actor chain, monotonic narrowing) and carries the narrowed token
  as an HTTP `Authorization: Bearer` header. Each A2A server validates it before accepting the task. This is the
  POC's design, **not** an A2A feature, and the article says so.

## A2A and MCP

- Spec Appendix B: MCP standardises how agents "connect to and interact with tools, APIs, data sources"; A2A
  standardises how "independent, often opaque, AI agents communicate and collaborate with each other as peers ...
  how agents *partner* or *delegate* work". "An A2A Server agent ... might use MCP to interact with several
  underlying tools".
- Project docs (`topics/a2a-and-mcp`): "MCP is vertical", "A2A is horizontal". 1.0 announcement: "MCP inside agents,
  A2A between agents".
- **House rule for C1**: "MCP inside agents, A2A between agents" is explanatory shorthand from the project's own
  materials, **not a normative protocol rule**. Nothing in either spec forbids other arrangements. The article
  presents it as a mental model.

## Concepts intentionally not used

`SubscribeToTask`, push notifications (four config operations), `ListTasks`,
extended Agent Card, multi-turn `INPUT_REQUIRED`, in-task `AUTH_REQUIRED`, Agent Card signatures, gRPC and REST
bindings, TLS (the POC runs on loopback HTTP; §7.1 requires TLS in production: a stated limitation).

## Deviations / simplifications in the POC

1. Loopback HTTP without TLS (violates §7.1's production MUST; acceptable for a local experiment, called out).
2. The bearer token is an HMAC-signed JSON token from a simulated token service, not OAuth 2.0; the Agent Card
   declares an `HTTPAuthSecurityScheme` with scheme `Bearer`.
3. Specialists use `InMemoryTaskStore` (the SDK default). E6 shows what that means after a crash; a
   `DatabaseTaskStore` would keep the record (not tested).
4. Only task execution is authenticated: `GetTask` and `CancelTask` requests carry no token and are not checked, short of §7.4's MUST (DEVIATIONS O7).
5. One skill per agent; one data artifact per task; delegations use `SendStreamingMessage` so the client learns the task id at once and sees each lifecycle transition.
6. Authorization across the boundary is the series' own narrowing token model (A2A leaves authorization to each
   agent). The blind run found a fail-open fallback in it: an authorized execution without a proposal got every
   eligible write scope (1 of 16). Fixed after the run to fail closed (DEVIATIONS D3); not an A2A property.
