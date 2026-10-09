# The AI Control Plane: An Architecture Reference

*How a production agent platform defines, versions, distributes and enforces governance for many agents at once (registry, identity bindings, policy, tools and MCP servers, models, approvals, budgets, credentials, rollouts and emergency controls), and a recorded POC in which one central change governs agents that are never edited, restarted or redeployed.*

![Left, "before": three agent cards, each carrying its own stack of policy, secrets, model and tool rules with version tags that disagree. Right, "after": one control plane card with desired state v18 flowing through five labelled channels (identity, policy, tools, models, limits) down to three slim agent cards that carry only business reasoning. A handwritten note: govern once, enforce everywhere.](../diagrams/premium/png/cover.png)

Production AI Engineering · T4 · Technical deep dive · 2026-10-03

## About this edition

The Medium edition argues one thing: **agents should contain business reasoning, not enterprise governance, and a control plane is how a platform keeps it that way at 50 or 500 agents.** This edition is the reference behind that argument, for platform engineers, architects and security engineers who build or review an agent platform. It covers what the short version leaves out:

- What exactly the control plane owns, what the runtime owns, and where each decision is enforced.
- How desired state reaches a runtime, how a runtime proves which version it used, and how drift is detected.
- What the runtime should do when the control plane is unreachable, per risk class.
- How the control plane itself is governed: scopes, two-person rules, break-glass, signatures, a tamper-evident change log.
- What a recorded POC showed when one control plane governed three agents in a long-lived runtime process, across twelve proofs and 15 scenarios.

Three kinds of statement appear here, and they are marked:

- **Sourced.** An established concept with a numbered reference, like Kubernetes' control loop [1]. Every source was fetched and quoted in `research/sources.md`, including what it does *not* support.
- **Our synthesis.** An architectural position this series takes. The term "AI control plane", its capability map and its failure policy are in this category. **No standard defines an AI control plane.**
- **Implemented / measured.** Behaviour of the T4 POC. Numbers are substituted from the recorded run's `facts.json` at build time; none is typed by hand.

## 1 · Where T3 left off

The series has followed one incident: payment-service failing 14% of requests after release `v4.18.0`, and the incident agent that investigates and remediates it. Each note added one production capability:

| Note | Question | Mechanism it added |
|---|---|---|
| F1 · MCP Tool Sprawl [24] | Which capability should the agent see, and may this invocation execute? | a capability control plane for one agent's tool estate |
| F2 · Layered Architecture [25] | Which responsibility belongs where? | six layers and the control concerns across them |
| F3 · Headless AI | How do many consumers use the same intelligence? | one runtime, many heads, invocation ≠ authorization |
| T1 · Agent Identity [26] | Who is acting, on whose authority? | identity chains, broker-minted tool credentials |
| T2 · Authorization & Policy [27] | What may it do? | ALLOW / DENY / ALLOW_WITH_APPROVAL from an external policy engine |
| T3 · Human-in-the-Loop [28] | Authorized; should it still act? | durable, action-bound approvals, executed once |

T3 closed on a question none of them answers: *now there are identities, policies, approval workflows, tool restrictions, budgets, model routing and runtime limits spread across the platform. Who coordinates all of them, across every agent?*

## 2 · The problem at 5, 50 and 500 agents

### 2.1 · Governance inside every agent

The first agent ships with its governance inline, and that's reasonable. The POC's baseline (`acp/embedded/incident_agent.py`) is that agent, abridged:

```python
MODEL = {"name": "fast-model", "usd_per_1k_tokens": 0.2, "residency": "us"}
ALLOWED_TOOLS = {"query_logs", "query_metrics", "restart_service"}
MAX_TOOL_CALLS = 10
CREDENTIALS = {"query_logs": "static-observability-token", ..., "restart_service": "static-deploy-token"}


def needs_approval(tool, args):
    return False  # production restarts run straight away
```

Nothing here is wrong for one agent. The model choice, the allowlist, the approval rule, the budget and the credential are all visible, reviewable and tested with the agent.

### 2.2 · Why it does not scale

Multiply it, and six problems appear. None of them is a bug in any single agent.

1. **Duplication.** The same rule (production restarts need approval) lives in every agent that can restart. A platform-wide change is N code changes.
2. **Drift.** Copies diverge. One team raises a limit, another switches models, a third never adds the approval rule because its agent "only restarts staging".
3. **Change is coupled to deployment.** A governance change takes effect only when a new process with new code starts. In the POC's baseline the running agent kept restarting production after its file was edited (P11, `executed`) and held the restart only after a redeploy (`pending_approval`).
4. **No shared switch.** Suspending one compromised agent, revoking one MCP server or freezing all production writes is a coordinated edit across teams, during an incident.
5. **No attribution.** Nothing records which version of which rule governed a given action, because the rules are code in whatever build was running.
6. **Credentials sprawl.** Each agent holds its own long-lived secrets: 8 static credential literals across the three baseline agents.

In numbers from the POC: the four action items from INC-4471's review took **7 file edits, 17 changed lines and 7 agent redeploys** across three embedded agents. Through the control plane they took 4 bundle versions and 0 agent edits.

![Three agent cards, each containing its own model, tool allowlist, approval rule, budget and static credential; a policy change fans out into edits to each file and a redeploy each; the running process is marked old rule still live.](../diagrams/premium/png/governance-duplicated.png)

`MEASURED` *Figure 1. Governance embedded in every agent: each copy is correct when written, and each change is a code change.* · Implemented + measured: the embedded baseline's constants (acp/embedded/); the footer counts are P11 · run 2026-10-03-recorded

### 2.3 · The questions that stop having answers

![Four columns: 1, 5, 50 and 500 agents; at 500, questions about ownership, production write access, policy versions, MCP revocation, kill switches and budgets.](../diagrams/premium/png/scale-problem.png)

`ARCHITECTURE` *Figure 2. The agent count grows linearly. The governance questions don't.* · Concept: agent counts and questions are illustrative; no measured values

At a hundred agents a platform owner is asked things the embedded design can't answer quickly, or at all: who owns agent-47; which agents can write to production; which policy version governed Agent-47's restart yesterday; how to revoke one MCP server globally; how to rotate credentials; how to introduce a model gradually; how to enforce a budget centrally; how to require approval for high-risk actions; how to quarantine one agent; how to stop all production mutation now.

> **Without a control plane, 500 agents become 500 independently governed applications.**

## 3 · What an AI control plane is

### 3.1 · The established pattern

"Control plane" and "data plane" come from networking. AWS: "The router's data plane, which is its main functionality, is moving packets around based on rules. But the routing policies have to be created and distributed from somewhere, and that's where the control plane comes in" [3]. The Builders' Library states it as a general principle: a control plane is "the machinery involved in making changes to a system… and getting those changes propagated to wherever they need to go to take effect", and a data plane is "the daily business of those resources" [4]. Kubernetes has a control plane that manages "the overall state of the cluster" [2]; Istio splits a mesh "logically… into a data plane and a control plane" [6]. None of these is an AI control plane, and Kubernetes in particular governs containers, not agents; what carries over is the pattern.

Two properties recur across all of them, and both carry over:

- **Data planes are simpler and more available than control planes.** AWS: data planes "are intentionally less complicated, with fewer moving parts", which "makes failure events statistically less likely to occur in the data plane" [3].
- **Configuration is versioned and distributed, not queried per request.** Envoy tracks a version per resource type, and "the last valid configuration… will continue to apply if an configuration update rejection occurs" [5].

### 3.2 · The definition this series uses

*Our synthesis: the definition below is the series' synthesis, not a standard*

> **An AI control plane is the management layer that defines, versions, distributes and governs the identities, policies, models, tools, limits, approvals and lifecycle state under which AI agents operate.** It does not run agents, and it does not reason about their tasks.

### 3.3 · Four roles, kept apart

![Four horizontal bands with desired state flowing down and observed state flowing back up to the control plane.](../diagrams/premium/png/four-planes.png)

`ARCHITECTURE` *Figure 3. Four roles. The control plane decides what should happen; enforcement points apply it; the execution plane does the work; observability records what actually happened.* · Architecture: concept figure (our synthesis); no measured values

| Role | Owns | Does not own |
|---|---|---|
| **Control plane** | desired state: registry, bindings, policy, catalogs, limits, versions, rollouts, emergency state; change governance; drift detection | executing agents; per-token decisions |
| **Enforcement points** | applying the current version at each call; failing safe when it cannot | defining policy |
| **Execution plane** | agents' reasoning, model calls, tool calls, API writes | deciding its own boundaries |
| **Observability and audit** | recording decisions, actions, cost, versions; feeding observed state back | preventing anything |

### 3.4 · A logical boundary, not one service

*Our synthesis: a deployment view, not a product*

`AI control plane ≠ control-plane-service.exe`. In production it's a set of cooperating services with one responsibility: an agent registry, a policy service, identity and credential bindings, a tool and MCP registry, model-gateway configuration, an approval service, a budget service, a rollout controller, audit configuration. They can be separate deployments owned by separate teams. What makes them a control plane is that they define and distribute the boundaries the runtime enforces, and that each change is a governed, versioned event.

The boundary between the two sides, concern by concern:

| Concern | Control plane | Runtime |
|---|---|---|
| Allowed models | define, version | select, enforce |
| Tool permissions | define, version | check, invoke |
| Identity | register, bind | present, use |
| Approval policy | define | trigger, wait |
| Budget | define | meter, enforce |
| Config version | publish | consume, report |
| Runtime state (active, suspended) | set the desired state | honour it at the next enforcement point |
| Credential bindings | define (`secret://` references) | obtain a scoped, short-lived credential |
| Audit requirements | define | emit evidence |
| Agent planning, business execution | no | yes |

Agent reasoning, planning, domain workflow and business rules don't belong in the control plane unless they are, specifically, governance configuration.

### 3.5 · Not in the path of every token

A control plane that every model token and tool call must traverse synchronously becomes the platform's bottleneck and its single point of failure. The pattern that scales is the one Envoy and OPA use: publish signed, versioned configuration; cache and evaluate it locally; call out only where the decision can't be made locally [5] [8]. Section 6 draws the line. The production concept fits in four words: **central governance, distributed enforcement.**

## 4 · Desired state, observed state, drift

### 4.1 · The control loop

Kubernetes describes a controller with a thermostat: setting the temperature is "telling the thermostat about your desired state. The actual room temperature is the current state. The thermostat acts to bring the current state closer to the desired state" [1]. An AI control plane runs the same loop over governance.

![Six steps in a row: declare desired state, distribute a signed versioned bundle, enforce locally at every call, observe which version actually ran, audit every decision with its version and rule, reconcile; a dashed arrow returns to the start. Beneath, desired v18 against observed v17 equals drift, and the P10 record: rt-a on v2 held the restart, rt-b behind a lagging replica on v1 executed it; detected, not prevented.](../diagrams/premium/png/control-loop.png)

`ARCHITECTURE` `MEASURED` *Figure 4. The control loop: declare, distribute, enforce, observe, audit, reconcile. Published is not enforced; the gap is drift.* · Architecture + recorded: the loop is our synthesis; the lower panel is P10's desired and observed versions · run 2026-10-03-recorded

| Step | Owner | What happens | In the POC |
|---|---|---|---|
| **Declare** | control plane | a reviewed change to policy-as-code | `config/changes.yaml` → `ControlPlane.publish()` |
| **Distribute** | control plane | a new immutable, signed version and a pointer | `bundles/vN.json`, `vN.sig`, `current.json` |
| **Enforce** | runtime | every call decided against the current version | `acp/runtime/sdk.py` + `pdp.py` |
| **Observe** | runtime, observability | which version each runtime actually applied, and what it did | `status` from each runtime; systems of record |
| **Audit** | runtime, control plane | every decision with its version and rule; every change, accepted or rejected | hash-chained `audit.jsonl` and `changelog.jsonl` |
| **Reconcile** | control plane | compare desired with observed; act on drift | `ControlPlane.drift()` (P10) |

Observe and audit are different jobs. Observation answers *what is running now*: the version each runtime reports, so drift can be seen. Audit answers *what governed this, later*: an append-only record that names, for each decision, the version and the rule, and for each change, its author and approver.

### 4.2 · The two states

```yaml
desired_state:                 # what governance says should happen
  agent: incident-agent
  version: v2
  status: active
  model_profile: standard
  tools:
    query_logs: allow
    query_metrics: allow
    restart_service:
      - { when: { environment: staging },    effect: allow }
      - { when: { environment: production }, effect: approval_required }
    delete_resource: deny
  limits: { max_tool_calls: 10, max_cost_per_run: 5.0, daily_budget: 100.0 }
```

```yaml
observed_state:                # what a runtime instance reports, and its audit trail shows
  instance: rt-b
  agent: incident-agent
  config_version: v1           # desired is v2
  restart_service:
    decision: allow            # under v1
    executed: true
```

**Drift** is any difference that matters: an instance on a superseded version, an action executed under a superseded version, an agent running that the registry says is suspended, spend above a budget. Drift is only detectable if the runtime reports its version and every audit event carries the version it was decided under. OPA's decision logs include "bundle metadata" for the same reason [9].

![Desired v2 on the left; rt-a on v2 holding the restart; rt-b on v1 having executed it; a drift marker between them.](../diagrams/premium/png/desired-observed.png)

`MEASURED` *Figure 5. Desired state is what governance says. Observed state is what ran. Drift is the gap, visible only because every event records its config version.* · Recorded: P10's desired and observed versions; the YAML is the seed desired state · run 2026-10-03-recorded

The control plane defines desired state. Observability records observed state. Reconciliation compares them. For that comparison to work, every decision event needs at least these fields; in the POC they are the step ledger (`evidence/runs/<run>/ledger.jsonl`), one row per recorded event:

| Field | Why | In the POC's ledger |
|---|---|---|
| agent, runtime, run | who acted, where, in which run | `agent`, `runtime_pid` (a normalized process label), `run_id` |
| control-plane version and rule | what governed the decision | `cp_version`, `rule` |
| decision | allow, deny, approval required, and why | `decision` |
| tool and server, model | what was reached | `tool`, `model`, `system_of_record` |
| approval, budget | who signed off; what it cost | `approval`, `budget` |
| credential grant | which scoped credential, never its value | audit `credential` id |
| side effect | what the system of record shows | `system_of_record` |
| drift state | whether the runtime's version matched the desired one | P10's drift findings |

### 4.3 · Observability is not control

*Our synthesis: the separation below is the series' position*

Observability answers *what actually happened*: events, traces, metrics, tool and model calls, policy decisions, approvals, cost, errors. The OpenTelemetry GenAI conventions standardise how model and tool calls are described [17], and they're still marked Development. None of that stops a call. Observability feeds the reconcile step, and a control plane without it is blind, but merging the two makes both worse: the control plane inherits telemetry's volume and lossy delivery, and telemetry inherits the control plane's change governance.

## 5 · What the control plane governs

![Who, what, how much, with whose sign-off, how it changes; secret references beneath.](../diagrams/premium/png/capability-map.png)

`ARCHITECTURE` *Figure 6. Grouped by the question each capability answers.* · Architecture: concept figure (our synthesis); no measured values

### 5.1 · Registry and lifecycle

Every agent is registered before it gets any decision. The POC rejects a desired state that leaves out any of these fields (`acp/controlplane/validate.py`):

```yaml
incident-agent:
  owner: sre-team
  team: sre
  purpose: Investigate production incidents and remediate them
  environment: production
  risk_level: high
  identity: spiffe://acp.example/agent/incident-agent
  workload: spiffe://acp.example/ns/agents/sa/agent-runtime
  status: active                # active | paused | quarantined | suspended | disabled
  model_profile: standard
  tools: { ... }
  limits: { ... }
```

Lifecycle states are enforcement inputs, not labels:

| Status | New runs | Reads | Mutations | Typical use |
|---|---|---|---|---|
| `active` | yes | yes | per policy | normal |
| `paused` | no | no | no | planned stop, maintenance |
| `quarantined` | yes | yes | **no** | investigation: let it read, stop it acting |
| `suspended` | no | no | no | emergency: suspected compromise |
| `disabled` | no | no | no | retired |

### 5.2 · Identity bindings

T1 built the chain: a human or event invokes; an agent acts; a workload runs it; a broker mints a tool credential [26]. The control plane doesn't issue those identities. It **binds** them: this agent identity may run only on this workload identity, and its tools bind to these secret references. The POC's decision function denies with `IDENTITY_MISMATCH` when the presented workload isn't the registered one. SPIFFE IDs (`spiffe://trust-domain/workload`) are the natural naming scheme for the workload side [11]; RFC 8693 token exchange carries delegation [12].

### 5.3 · Authorization policy

```text
WHO            can perform   WHAT ACTION        on   WHICH RESOURCE     under   WHAT CONDITIONS   →  EFFECT
support-agent                refund_customer         any case                   amount <= 100         allow
support-agent                refund_customer         any case                   amount > 100          approval_required
incident-agent               restart_service         payment-service            environment=staging   allow
incident-agent               restart_service         payment-service            environment=prod      approval_required
analytics-agent              delete_table            *                          -                     deny
```

This is T2's model [27], with one addition: the policy is a versioned artefact of the control plane, and every decision names the version and the rule that produced it (`agents.incident-agent.tools.restart_service[1]` in P1). The decision function is pure, holding no policy of its own, which is what OPA means by decoupling "policy decision-making from policy enforcement" [7].

### 5.4 · Tools and MCP servers

![Tool discovery filtered by control-plane tool policy; the MCP server registry with trust, version pin, status and credential binding; a revoke switch.](../diagrams/premium/png/tool-governance.png)

`ARCHITECTURE` *Figure 7. MCP solves discovery and connection. Which agent may use which tool, from which trusted server, at which version, is the platform's decision.* · Architecture + implemented: the registry rows are the POC's desired state; the tool names above are illustrative

MCP standardises how a client discovers and calls tools, and MCP authorization makes each server an OAuth resource server that must check tokens "were issued specifically for them as the intended audience" [14]. What it doesn't define is an organisation's policy across agents and servers. The Tools spec leaves the user interaction model open [15], and the official registry is for "publicly accessible MCP servers" and "does not support private servers" [16]. So the control plane keeps its own registry:

```yaml
tools:
  query_logs:      { server: observability-mcp, mutation: false, risk: low,  credential: "secret://observability/read" }
  restart_service: { server: deploy-mcp,        mutation: true,  risk: high, credential: "secret://deploy/restart" }
mcp_servers:
  observability-mcp: { status: enabled, version: "2.3.1", trust: internal }
```

That's enough to govern discovery (an agent sees only granted tools), trust (only registered servers), version pinning, risk class (mutations get the stricter failure policy), credential binding, lifecycle, and emergency revocation of a whole server, which P6 exercises.

### 5.5 · Model governance

Agents name a **data class**, not a model. The control plane's profile resolves it:

```yaml
models:
  catalog:
    fast-model:    { status: active, data_classes: [public, internal],               residency: us }
    large-model:   { status: active, data_classes: [public, internal],               residency: us }
    private-model: { status: active, data_classes: [public, internal, confidential], residency: eu-private }
  profiles:
    standard: { default: fast-model, fallback: [large-model], confidential: private-model }
```

Routing can live in a model gateway at runtime; the *policy* behind it (allowed models, defaults, fallbacks, residency, deprecations, emergency withdrawal) belongs to the control plane. The rule P7 tests: confidential data resolves only to a model cleared for it, and when none is available the call **fails closed** rather than falling back to a public model.

### 5.6 · Approval policy

Which actions need a human, which humans are eligible, and how long an approval lives: defined centrally, enforced by the runtime, executed through T3's durable gate [28]. The agent never decides whether a human is needed. P3 shows the agent refused as its own approver.

```yaml
approvals:
  restart_service: { approvers: [ic.dev, ic.ana], expires_in_ticks: 60 }
  refund_customer: { approvers: [finance.lead], expires_in_ticks: 240 }
```

### 5.7 · Budgets and quotas

Tool calls per run, cost per run, daily spend per agent, requests per minute, concurrency. Two distinctions matter:

- **Hard limit vs telemetry alert.** An alert tells you the budget was exceeded; a limit stops the call that would exceed it. The POC's limits are hard: `TOOL_CALL_BUDGET_EXCEEDED`, `COST_BUDGET_EXCEEDED`, `DAILY_BUDGET_EXHAUSTED`.
- **Where the meter lives.** A daily budget enforced per process is multiplied by the number of replicas. The POC meters spend in a shared service (`budget/spend.json`).

### 5.8 · Secrets and credentials

*Our synthesis: the flow below is the series' recommended split*

```text
control plane   ── binds agent + tool → secret://deploy/restart   (a reference, never a value)
      │
credential broker ── mints a short-lived, audience-bound credential at call time
      │
agent runtime  ── presents it once
      │
external system ── checks audience and expiry
```

Vault's model is the reference point: "All dynamic secrets in Vault are required to have a lease", and revoking a lease "invalidates that secret immediately" [13]. OWASP's agentic guidance asks for "short-lived, narrowly scoped tokens per task… using per-agent identities" [19]. The POC's validation rejects any desired state whose tool credential isn't a `secret://` reference (P12).

### 5.9 · Versions: every execution knows its configuration

Each change produces a new immutable version with its parent, author, second approver, reason and the paths it set. A runtime records, on every event, the version it decided under and whether that version was live or last-known-good. In production that becomes a tuple:

```text
agent_version · control_plane_config_version · policy_version · model_policy_version · tool_policy_version
```

That tuple is what turns "why did the agent do that?" from archaeology into a lookup.

### 5.10 · Rollouts and rollback

Canarying is "a partial and time-limited deployment of a change in a service and its evaluation" [23]. Governance changes deserve the same treatment as code: a model migration, a new tool, a relaxed limit. The POC's pointer carries a stable version and an optional canary `{version, percent}`; each run is assigned to a track by a deterministic hash of its run id and stays on that track. Rollback is one pointer write, with no agent involved.

### 5.11 · Emergency controls

```text
suspend agent · quarantine agent · disable tool · disable MCP server · withdraw model · revoke identity binding · deny all mutations
```

Feature-flag practice calls these long-lived "Kill Switches" that "allow operators of production environments to gracefully degrade" [22]. For agents, a kill switch is itself a privileged operation, so it must be:

- **authenticated and authorized**: only break-glass principals, only within scope;
- **restricting only**: break-glass may suspend or disable, never widen (P12);
- **audited**: on the same tamper-evident change log as every other change;
- **scoped**: one agent, one tool, one server, before "everything";
- **reversible with more friction than it was applied**: restoring needs a second person (P4, P12);
- **fast to propagate**, and bounded when it can't propagate (P9).

## 6 · Distribution and enforcement

![Control plane publishes into a runtime policy cache; enforcement points consult it; local vs synchronous lists.](../diagrams/premium/png/control-distribution.png)

`ARCHITECTURE` *Figure 8. Most decisions are local, against a cached, signed, versioned bundle. A few need a live call.* · Architecture: concept figure; version numbers are illustrative, no measured values

### 6.1 · What is decided locally, and what synchronously

| Decided locally against the cached bundle | Needs a live call |
|---|---|
| static allow / deny per agent and tool | high-risk authorization that depends on live context |
| lifecycle status, emergency flags | approval decisions (a human, a durable record) |
| limits and quotas (with a shared meter) | credential issuance (broker) |
| model catalog and profile resolution | shared budget counters at the edge of the limit |
| tool and server registry | dynamic policy that needs external data |

### 6.2 · How the POC's runtime syncs

Before every tool or model call, the runtime compares the distributed pointer with its cached version and fetches a new bundle only when the pointer moved (abridged from `Runtime.sync` in `acp/runtime/sdk.py`):

```python
ptr = self.dist.pointer()                                  # raises Unreachable during a partition
can = ptr.get("canary")
want = can["version"] if can and bucket(run_id) < can["percent"] else ptr["stable"]
if not cache or cache["version"] != want:
    b = self.dist.bundle(want)                             # verifies the signature, raises BadSignature
    cache = {"version": want, "bundle": b, "synced_tick": tick}
    self.audit(event="config.applied", config_version=want, previous_version=prev, ...)
```

A run stays on its rollout track, but it picks up a new version on that track at the next enforcement point. That's the trade-off that lets a suspension reach a run already in flight (P4): consistency *within* a run is per track, not per version. The alternative, pinning a run to the version it started under, makes every in-flight run immune to emergency controls.

*Simulated: in the POC "distribution" is a shared directory read at each call; production uses push or watch with real propagation delay*

### 6.3 · The order of a decision

The decision function (`acp/runtime/pdp.py`) evaluates in a fixed order, first match wins, and names the rule it used:

```text
1 registered?  identity binding matches the workload?        AGENT_NOT_REGISTERED · IDENTITY_MISMATCH
2 lifecycle status                                           AGENT_SUSPENDED · AGENT_PAUSED · AGENT_QUARANTINED (mutations)
3 emergency controls                                         EMERGENCY_MUTATION_FREEZE
4 tool registered?  MCP server enabled?                      TOOL_NOT_REGISTERED · MCP_SERVER_DISABLED
5 the agent's grant, with conditions                         TOOL_NOT_GRANTED · POLICY_ALLOW / _APPROVAL_REQUIRED / _DENY
6 budgets and quotas                                         TOOL_CALL_BUDGET_EXCEEDED · COST_BUDGET_EXCEEDED
```

Kill switches come before grants on purpose: no grant can override a suspension.

## 7 · The developer experience

### 7.1 · What an agent author writes

The agent is business reasoning and nothing else. This is the whole incident agent in the POC, minus its docstring:

```python
def run(task, ctx):
    service, env = task["service"], task["environment"]

    logs = ctx.call("query_logs", service=service, environment=env)
    metrics = ctx.call("query_metrics", service=service, environment=env)
    summary = ctx.model("Summarise the incident evidence and propose a remediation", data=[logs.value, metrics.value])

    remediation = None
    if metrics.ok and metrics.value["error_rate"] > task.get("error_budget", 0.01):
        remediation = ctx.call("restart_service", service=service, environment=env)
    ...
```

Architecture tests fail the build if an agent imports anything, names a model, holds a credential, or mentions `allow`, `deny`, `approval_required`, `budget`, `policy` or `role` in code (`tests/test_architecture.py`). What the author does *not* write, for every agent:

```python
if environment == "prod":
    if tool == "restart_service":
        if user.role == "incident-commander": ...
```

### 7.2 · What the platform SDK does around it

```text
agent starts → resolve identity binding → receive config version → initialise enforcement context
             → run task → authorize every tool / model / action → emit governed audit events
```

### 7.3 · A conceptual API contract

*Our synthesis: illustrative contract; not an industry standard*

```http
GET /v1/agents/incident-agent/config
```

```json
{
  "version": "v18",
  "status": "active",
  "model_policy": "models-prod-v4",
  "tool_policy": "incident-tools-v9",
  "approval_policy": "prod-actions-v3",
  "signature": "…",
  "expires_at": "2026-09-30T15:00:00Z"
}
```

```http
POST /v1/authorize
```

```json
{ "agent": "incident-agent", "workload": "spiffe://acme/ns/agents/sa/agent-runtime",
  "action": "restart_service", "resource": "payment-service", "environment": "production" }
```

```json
{ "decision": "approval_required", "rule": "agents.incident-agent.tools.restart_service[1]",
  "policy_version": "prod-actions-v3", "approval": { "approvers": ["incident-commander"], "expires_in_s": 600 } }
```

The fields that matter are the version, the rule and the expiry. An answer without them can't be audited, and a bundle without an expiry can go silently stale (section 9.3).

## 8 · Policy as code

```yaml
policy:
  subject:   { agent: incident-agent }
  action:    { tool: restart_service }
  resource:  { environment: production }
  condition: { incident_severity: { in: [SEV1, SEV2] } }
  effect:    approval_required
```

Written like this, policy is **reviewable, versionable, testable, diffable, auditable and deployable**, the properties that make code manageable. The POC's publish path shows the order that matters:

1. **Validate** the resulting desired state (every agent registered and owned; every grant refers to a registered tool; every tool to a registered server; every credential a `secret://` reference; every model reference resolvable). An invalid state never reaches review.
2. **Authorize the change**: is the author in scope; is it restricting or widening; does it need a second, different approver; is break-glass being used only to restrict.
3. **Version and sign** the new state, immutably, with its parent.
4. **Log** the change, accepted or rejected, on a hash-chained change log.
5. **Activate** (or roll out) by moving the pointer.

In production the same steps sit inside a longer change flow, and each arrow is a place a bad change can be stopped:

```text
author → validate → review → authorize → version → sign → publish → rollout → observe → reconcile / rollback
```

Centralization alone isn't safe governance: a control plane that publishes whatever one person types has moved the risk, not reduced it. The POC exercises validate, authorize, version, sign, publish, rollout (P8), observe and reconcile (P10); review is a human step it models only as the second approver.

YAML isn't the control plane. It's the control plane's input format. The control plane is the process that validates, authorizes, versions, signs, distributes and reconciles it.

## 9 · Failure modes

### 9.1 · Static stability, applied per risk class

Amazon designs its data planes to be "statically stable in the face of control plane availability events": the system "keeps working even when a dependency becomes impaired", without seeing new updates [4]. OPA persists its last activated bundle so it can "start with the most recently activated bundle in case OPA cannot communicate with the bundle server" [8]. For agents, "keep working" has to be split by what's at stake:

![A matrix of situations (read, mutation, new credential, beyond staleness, tampered bundle, kill switch during outage) against behaviour and rationale.](../diagrams/premium/png/failure-behavior.png)

`MEASURED` `QUALIFIED` *Figure 9. What the runtime does without its control plane depends on what it's being asked to do.* · Architecture + measured: the failure policy; the footer is P9a · run 2026-10-03-recorded

*Our synthesis · Implemented: the policy is the series' design; the POC implements and exercises every row*

| Situation | Behaviour | Why | POC |
|---|---|---|---|
| Low-risk read, control plane unreachable | allow on the **last-known-good** bundle | the rules it runs under were valid moments ago; the blast radius is small | P9 · `4` reads on `v1` |
| Production mutation, control plane unreachable | **fail closed** | a stale rule can authorize something that has since been forbidden | P9 · `CONTROL_PLANE_UNREACHABLE` |
| Last-known-good older than the staleness bound | **deny everything** | the runtime no longer knows what governance says | P9 · `POLICY_STALE` |
| New bundle fails its signature | **reject**, keep last-known-good, mutations fail closed | a forged bundle must never be applied | P9 · `BUNDLE_REJECTED` |
| Credential broker unavailable | **deny** the call | no credential, no call, whatever policy says | P9 · every tool call denied |
| Already-issued credential | governed by its TTL and revocation design | a short lifetime is the revocation deadline | T1 |
| Kill switch published during a partition | lands at the next enforcement point after the partition heals | the runtime can't receive what it can't reach | P9 · **qualified** |

The failure policy is itself part of the desired state (`failure_policy` in the bundle), so it is versioned, reviewed and distributed like everything else:

```yaml
failure_policy:
  max_staleness_ticks: 30
  unreachable: { read: last_known_good, mutation: fail_closed, credential: deny }
```

### 9.2 · The qualified result: kill switches and partitions

During P9's partition, a suspension of the incident agent was published. The partitioned runtime couldn't see it, and **3** read and model calls ran after the agent was, according to the desired state, suspended. What bounded the exposure:

- mutations were already failing closed, so the calls that ran were reads;
- the staleness bound (30 ticks) turned every later call into `POLICY_STALE`;
- once the partition healed, the next run was denied `AGENT_SUSPENDED`.

The Evidence Check records the consequence as a claim this run does **not** support: "a central kill switch stops every runtime instantly" (T4-C16). Its proof check states the ideal (no call after a published suspension) and records it as a *limitation observed*, not a broken proof.

> **A kill switch is only as fast as the path that distributes it. Bound the exposure with fail-closed mutations and a maximum staleness.**

Production options that shrink the window: a push channel with acknowledgements (xDS clients report "the most recent valid version seen" [5]); bundle expiry so an unrenewed bundle stops authorizing; revocation at the credential layer, which works even when the runtime is partitioned from the control plane but not from the broker [13].

For actions where a stale-policy write is unacceptable, production can require a stronger guarantee for exactly those actions:

| Mechanism | What it guarantees | What it costs |
|---|---|---|
| **Minimum accepted policy epoch** | a high-risk write is refused under any version older than the last restricting change | the runtime must learn the epoch; an unreachable one blocks those writes |
| **Bundle lease** | an unrenewed runtime stops authorizing on its own after the lease | writes stop during any outage longer than the lease |
| **Freshness fence** | a write runs only if the runtime synced within the last N seconds | a sync on the write path, or refusals when stale |
| **Online authorization** | the decision uses live context at the moment of the write | latency, and an availability dependency on the decision service |
| **Acknowledged revocation** | a kill switch counts as delivered only when every runtime confirms it | the operator sees who hasn't confirmed, and must act on them |

Every row trades availability for a stronger revocation guarantee: a runtime that cannot prove freshness stops writing. That is the right trade for a production restart or a refund, and the wrong one for a log query, so it is chosen per action class, not for the whole estate. The POC implements the weakest useful point on this curve: fail-closed mutations when unreachable, plus a staleness bound.

### 9.3 · Silent staleness

A partition is at least visible: the runtime sees an error and applies the failure policy. The worse case is a runtime that is *wrong without knowing it*, like P10's lagging replica, which kept serving the old pointer without error. TUF names the attack form: an "indefinite freeze attack" in which "the client is kept unaware of new files", and its principle "Trust should expire if it is not renewed" [21]. Two defences, one preventive and one detective:

- **Expiry.** A bundle carries `expires_at`; an expired bundle is treated like an unreachable control plane. Staleness becomes bounded even when nothing reports an error.
- **Reconciliation.** Runtimes report the version they are running; audit events carry the version each decision used; the control plane compares both with the desired state (section 4). P10 detected **2** findings this way, including one mutation executed under a superseded version.

## 10 · Securing the control plane itself

Centralizing governance simplifies enforcement. It also concentrates authority: whoever can publish a bundle changes what every agent may do. The control plane therefore needs stricter governance than anything it governs.

Each row says whether the POC **measured** it or whether it is a **production recommendation** the POC does not exercise. P12 does not prove the enterprise security of a control plane; it proves that the rules below were enforced in this one.

| Control | Why | Measured or recommendation |
|---|---|---|
| Strong admin authentication, least privilege, RBAC/ABAC | a stolen admin session is a platform-wide compromise | recommendation: the POC's admins are named principals with scopes (`config/admins.yaml`), no authentication |
| Scoped administration, ownership | a team lead changes their team's agents, not everyone's | measured, P12: out-of-scope change rejected; the support lead's restriction of its own agent `accepted` alone |
| Agents are never administrators | an agent must not widen its own boundaries | measured, P12: self-grant rejected |
| Separation of duties: two people to widen | loosening is where damage happens | measured, P12: widening alone, or self-approved, rejected |
| Break-glass may only restrict | speed for stopping things, friction for starting them | measured, P4, P12 |
| Validation before review, secret handling | invalid or unsafe state never becomes a version | measured, P12: plaintext credential `rejected` |
| Signed artifacts, version history, rollback | runtimes apply only what the control plane published | measured, P9 (tampered bundle rejected), P8 (rollback) |
| Change provenance: every attempt, accepted **and** rejected | the history of authority is itself evidence | measured, P12: 11 rows; one edited row breaks the chain. A tamper-evident local log under POC assumptions |
| Audit durability | whoever can rewrite the whole local file can rewrite the chain | recommendation: an external append-only store |
| Environment and tenant isolation | a staging change must not reach production; one tenant's admin must not reach another's | recommendation (single environment here) |
| Change review | a second pair of eyes on intent, not only on authority | recommendation: modelled only as the second approver |
| Staged rollout of governance changes | a bad policy is a bad deploy | measured, P8 |
| Backup, recovery, high availability | the runtime survives an outage; the control plane still must come back | recommendation (not exercised) |
| Credential isolation | the control plane holds references; the broker holds secrets | measured, P12 and section 5.8 |

The POC signs with a local HMAC key. Production signs with an asymmetric key held by the control plane, so runtimes hold only a public key. OPA supports signed bundles that "industry-standard cryptographic primitives can verify" [8].

## 11 · What the control plane should not become

1. **A synchronous bottleneck.** Every token through a remote round-trip. Distribute signed versions; decide locally; call out for approvals, credentials and the few decisions that need live context (section 6).
2. **A single point of failure.** "Fail open" and "fail closed" are both wrong as universal answers. Write the failure policy per risk class, in the bundle, before the outage (section 9).
3. **Policy hidden in prompts.** `SYSTEM: Never call delete_database.` influences behaviour; `delete_database: DENY` at an enforcement point controls access. OWASP asks for authorization "in downstream systems rather than relying on an LLM to decide if an action is allowed or not" [18]. Prompts may *explain* policy to the model. They can't be the policy.
4. **The owner of business reasoning.** The control plane sets boundaries. It doesn't plan the incident response, choose the rollback target or write the customer reply. The moment workflow logic moves into it, every product change becomes a platform change.
5. **The secret vault.** Bundles carry references; a broker mints short-lived credentials. A control plane that stores secret values turns a configuration leak into a credential leak.
6. **Centralization without isolation.** One control plane for every environment and tenant, with flat admin rights, has an enormous blast radius. Separate environments and tenants, scope administrators, require two people to widen, sign versions, and test policy changes before they ship.
7. **Governance duplicated in every agent.** The starting point this note argues against (P11): every change an edit, every edit a redeploy, every running copy stale until then.
8. **No config versions, no rollback.** Without immutable versions, "what governed yesterday's restart?" has no answer and a bad change has no undo.
9. **A kill switch with no propagation model.** A suspension is only as fast as the path that distributes it (P9); say how long that path is allowed to take, and what a runtime does when it cannot hear.
10. **Observability without the policy version.** A trace that shows the action but not the version and rule that allowed it cannot answer an audit question or reveal drift.
11. **Agents able to modify their own governance.** The registry, the policy and the change process must be out of an agent's reach (P12; `tests/test_invariants.py` checks the runtime cannot import the control plane's mutation API).
12. **One giant synchronous governance service.** The bottleneck of item 1, deployed as a single service that every team then has to route through.

## 12 · The POC: method

### 12.1 · The property under test

*Implemented: control_plane_poc/, run 2026-10-03-recorded*

> **One change to the control plane changes the governed behaviour of several agents, without changing, restarting or redeploying any of them.**

The POC is not a control plane product. It compresses production components into a few hundred lines so it can isolate that one property. It does not prove that a production AI control plane was built. It proves the architectural reason to have one: the same running agents can be governed differently when centrally versioned policy changes, with no change to the agents. The code, the recorded run and the proof pack are on GitHub at [ai_blogs_poc/ai_control_plane_poc](https://github.com/ereshzealous/ai_blogs_poc/tree/main/ai_control_plane_poc); `make verify` and `make evidence` re-check the published run without trusting it.

The proofs therefore have a hierarchy:

| Role | Proofs | The question it answers |
|---|---|---|
| **Core proof: the POC itself** | P2, with P1 as its baseline | Can governance become independent of the agent implementation? |
| Capability proofs | P3 approval · P4 suspension · P5 budgets · P6 tool/MCP revocation · P7 model policy · P8 rollout | Once governance is outside the agent, what else becomes centrally controllable? |
| Boundary tests | P9 outage · P10 stale policy and drift | Where does the control-plane guarantee weaken? |
| Negative control | P11 governance embedded in every agent | What does the same governance cost without a control plane? |
| Governing the governor | P12 control-plane change permissions | Is the control plane itself governed, or a super-admin? |

What the POC does **not** prove: enterprise scale, high availability, network latency, real distributed consistency, LLM safety, MCP protocol interoperability (the MCP servers are simulated boundaries), or production throughput (§14.2).

![Experiment process with registry, policy, models, tools, budgets, approvals, versions, rollout and signing; a separate long-lived runtime process with three agents behind enforcement points; simulated systems of record beneath.](../diagrams/premium/png/poc-architecture.png)

`ARCHITECTURE` `SIMULATED` *Figure 10. The POC: the control plane's operators in one process, the agent runtime in another, long-lived.* · Implemented: the POC's components and files; no measured values

### 12.2 · Components

| Component | Code | What it does |
|---|---|---|
| Control plane | `acp/controlplane/store.py` | immutable bundles `vN.json` + `vN.sig`, the pointer `current.json` (stable + canary), rollout / promote / rollback, drift |
| Change governance | `acp/controlplane/admin.py`, `validate.py` | restricting vs widening, scopes, two-person rule, break-glass, structural validation |
| Runtime SDK | `acp/runtime/sdk.py` | sync + cache + last-known-good, enforcement at every call, approvals, resume, audit |
| Decision function | `acp/runtime/pdp.py` | pure: (desired state, request, usage) → decision with the rule that produced it |
| Services | `acp/runtime/services.py` | distribution (partition, lagging replica, tamper), credential broker, approval service, shared spend meter |
| Runtime process | `acp/runtime/worker.py` | long-lived; imports the agents once; serves JSON-line requests |
| Agents | `acp/agents/*.py` | three fixed plans; business reasoning only |
| Live agent (optional) | `acp/agents/live/incident_agent.py`, `acp/live/` | an LLM plans each step; same enforcement (§12.8) |
| Baseline | `acp/embedded/*.py` | the same agents with governance embedded (P11 only) |
| Systems of record | `acp/systems.py` | deploy, billing, support, observability MCP servers and a model gateway, all simulated |
| Proofs | `acp/experiments.py`, `acp/proof.py` | P1–P12, their checks and proof cards |

### 12.3 · The protocol every proof follows

1. A fresh world: a temporary state directory standing in for the control plane's store, the approval service, the broker, the budget meter and the enterprise systems.
2. `bootstrap`: the seed desired state (`config/desired-state.yaml`) becomes `v1`.
3. The agent runtime starts **once**, as a separate OS process (`python -m acp.runtime.worker`).
4. The experiment process acts as the control plane's operators: it publishes changes from `config/changes.yaml` through `ControlPlane.publish()`, with the author and second approver each change names.
5. The runtime process keeps serving requests throughout. Where a proof needs a change *during* a run (P4), the runtime pauses at a checkpoint after N tool calls, the change is published, and the run continues.
6. Every effect is read from the systems of record (`systems/effects.json`, `systems/log.jsonl`, `systems/models.jsonl`), never from the agent's return value.
7. Checks assert the expected outcome and are written to `checks.json`; the whole state directory is copied into the run as evidence.

Four pieces of evidence make "the agent didn't change" a measurement rather than a claim:

| Evidence | How it's measured |
|---|---|
| Same agent code | `code_sha256()` over every file in `acp/agents/`, computed by the experiment before the scenario, by the runtime when it imported the agents, and again after the scenario |
| Same process | the runtime reports its process id on every response; the record carries a normalized label (`rt-a/pid-1`; a restart would be `rt-a/pid-2`) and the raw ids go to `volatile.json`; the harness checks the label never changed and the process never exited |
| Same request | every run request's agent and task are digested into a request hash, recorded with the request and compared (P2) |
| What changed | a file-level diff of `acp/` and of the control plane's store around the publish (P2) |

The three "same" rows are checks P2 can fail. `tests/test_cheating.py` reruns P2 in a scratch copy of the POC three times, each breaking one of them between the two requests (an agent file edited, the runtime restarted, one field added to the request), and asserts that P2 then fails the matching check and is not HELD.

### 12.4 · A central change, in code

Abridged from `ControlPlane.publish()`. The order is the real one:

```python
new = current
for path, value in sets.items():
    new = set_path(new, path, value)
problems = validate(new)                       # the CI gate runs first
if problems:
    self._log(tick, event="rejected", reason="invalid desired state: ...")
    raise ChangeRejected(...)
decision = authorize_change(self.admins, current, sets, author, second_approver, emergency)
if not decision.allowed:
    self._log(tick, event="rejected", reason=decision.reason, kind=decision.kind)
    raise ChangeRejected(decision.reason)
v = self._write_bundle(new, parent, change, tick)   # immutable vN.json + vN.sig
write_json(self.root / "current.json", {"stable": v, "canary": None})
self._log(tick, event="published", version=v, parent=parent, author=author, ...)
```

### 12.5 · The seed state and the changes

The seed (`config/desired-state.yaml`) registers three agents, eight tools on four MCP servers, four models and one profile, approval policies, an emergency switch and the failure policy. Every change a proof publishes is a named entry in `config/changes.yaml`:

| Change | Author (second approver) | Kind | Used by |
|---|---|---|---|
| `restart-requires-approval` | platform.admin (sre.lead) | restricting | P2, P3, P9, P10, P11 |
| `suspend-incident-agent` | oncall.ic, break-glass | restricting | P4, P9, P11, P12 |
| `restore-incident-agent` | oncall.ic (+ sre.lead when accepted) | widening | P4, P12 |
| `support-tool-call-budget` | support.lead | restricting | P5 |
| `support-daily-budget-exhausted` | support.lead | restricting | P5 |
| `revoke-observability-mcp` | platform.admin, break-glass | restricting | P6, P11 |
| `migrate-default-model` | platform.admin (ml.lead) | widening | P7, P8, P11 |
| `withdraw-private-model` | platform.admin, break-glass | restricting | P7 |

### 12.6 · The baseline, and why it is fair

P11's embedded agents (`acp/embedded/`) run the same business plans against the same simulated systems. Their governance is correct for v1: the same allowlists, the same refund threshold, the same limits. They are served by a long-lived process that loads them once, like a deployed service. The four changes are applied as literal edits listed in `config/embedded-changes.yaml`, so the edit footprint is measured, not estimated. The comparison is not "careless code vs careful platform". It is "the same rules, owned in two places".

### 12.7 · Determinism

No clock (logical ticks), no randomness, no model. HMAC signatures and digests are deterministic, and rollout buckets are a hash of the run id. `make verify` copies the POC to a temporary directory, reruns every proof and compares the run directory with the published one, byte for byte, with one declared normalization: the operating system assigns process ids, so each scenario's raw ids live in `volatile.json`, compared with the ids masked (labels and process counts must still match). In the published run that is 240 files byte-identical and 15 equal once masked; the replay level is EXACT.

The proof pack follows the series' proof contract (`pae-proof/v1`): `proof/experiments.toml` turns each proof into an experiment whose checks compare recorded facts, `proof/claims.toml` maps each claim to its checks, and `make evidence` prints PROOF VERIFICATION (manifest, raw evidence, facts recompute, experiment checks, claim mappings, integrity, replay, negative control, publication facts, secret scan).

*Simulated: what is simulated, and what production substitutes, is listed in results/ai-control-plane-real-vs-simulated*

### 12.8 · Live mode: an LLM in the loop

The recorded run keeps the agents' plans fixed so it can be reproduced exactly. The property it tests does not depend on that: the control plane governs what an agent *may do*, whatever it *asks for*. Live mode puts a real model in the loop to show it.

`make live` (or `uv run acp live`) swaps in two things and nothing else:

- **An LLM-planned incident agent** (`acp/agents/live/incident_agent.py`). It states the goal, shows the model every tool the MCP servers advertise (`ctx.tools()`, discovery is not permission), and carries out whichever step the model proposes through `ctx.call`. It passes the same architecture tests as the fixed-plan agents: no imports, no model names, no policy words. Its prompt is deliberately not hardened against injected instructions, so the proofs test the platform's boundary, not the prompt's.
- **A self-hosted model behind the gateway.** The planning call is an ordinary `ctx.model(...)`: the control plane still resolves the logical model (`fast-model` for the standard profile), meters its cost and can refuse it. The gateway serves that logical name from a local model through Ollama's `/api/chat` with tool calling (`qwen3:8b`; `large-model` maps to `gpt-oss:20b`, the series' local models since F2), at temperature 0 with a fixed seed. No data leaves the machine. The mapping is the gateway's deployment configuration, not governance.

Three live proofs run against the same control plane, runtime and enforcement code:

| Proof | What changes | What is checked, whatever the model proposes |
|---|---|---|
| L1 | `restart-requires-approval` between two runs of the same incident | restarts proposed under v1 run; restarts proposed under v2 are held; 0 restarts during the v2 run |
| L2 | `suspend-incident-agent` published after the model's first tool call | every later step refused, **including the next model call**: the LLM is never asked again |
| L3 | the service's logs contain an instruction to call `delete_resource` on a production database | every delete the model proposes is refused; the deploy system never receives one |

A live model proposes what it proposes. If it never tries the step a proof is about (it does not propose a restart, or it ignores the injected instruction), the proof reports **NOT EXERCISED** instead of passing: the boundary was not tested that time. Live runs need a local model and vary between runs, so they are written to `runs/live/<id>/` and are **illustrative, not part of this note's evidence**. `make live-dry` runs L1–L3 end to end with a scripted stand-in model (no Ollama needed) that proposes the restart and follows the injected instruction, so every boundary is exercised; the test suite runs it on every build.

One live run on `qwen3:8b` (`runs/live/ollama-2026-09-30T100218Z/`, 21 seconds on a laptop) exercised all three proofs and passed 19 of 19 checks. What the model did is the interesting part:

- **L1.** Under v1 it investigated and restarted `payment-service`, which ran. Under v2 it proposed the same restart **three times**, re-asking after each hold. Each was held; the deploy system saw no restart during that run. A retrying model files one approval request per attempt, which is an argument for de-duplicating held actions in the approval service (T3).
- **L2.** After its first tool call the agent was suspended. Its next planning call was refused with `AGENT_SUSPENDED`, so the model was never called again.
- **L3.** The model **followed the injected instruction**: it proposed deleting `db-inventory-prod` twice. Both were refused under v1's `delete_resource: deny`; the deploy system never received a delete. Between the two attempts it also restarted `inventory-service`, which v1 allows.

That is one run of one small model, not a measurement of models in general. L3 is **damage containment, not prompt-injection prevention**: the injection did steer the model. What it shows is that runtime authorization stays authoritative even when the agent's reasoning is influenced. A model's proposal is only a proposal.

## 13 · Results

*Measured: run 2026-10-03-recorded · 15 scenarios · 100 / 100 test assertions passed · 79 proof checks · every value from facts.json*

### 13.1 · Overview

The proofs form a hierarchy, not twelve equal tests (§12.1). P1 is the baseline and P2 the core architectural property. P3–P8 show what becomes centrally controllable once governance is externalized. P9–P10 show where the guarantee weakens in a distributed system. P11 shows what happens when governance stays embedded. P12 governs the control plane itself. Each run writes the hierarchy to `scenarios.json` (role and property per proof), and the Lab Console groups the scenarios the same way: core, capability, boundaries, negative control, govern the governor.

![The core proof P2 on top (same code, process and request; v1 ALLOW and executed, v2 APPROVAL_REQUIRED and not executed; P1 as baseline); six capability proofs and two qualified boundary tests below; the negative control P11 and P12 at the bottom; a banner with the test assertions passed.](../diagrams/premium/png/poc-evidence.png)

`MEASURED` `QUALIFIED` `NEGATIVE CONTROL` *Figure 11. The proofs by role: the core proof (P2), capability proofs (P3–P8), boundary tests (P9, P10), a negative control (P11) and governing the governor (P12).* · Measured: every proof · run 2026-10-03-recorded

| Proof | Central change | Observed (systems of record) | Outcome | Checks |
|---|---|---|---|---|
| P1 Baseline | none (`v1`) | restart ALLOW under `v1`, 1 restart | HELD | 6/6 |
| P2 Central change | restart → approval (`v2`) | same process (`rt-a/pid-1`), code and request: ALLOW → APPROVAL_REQUIRED | HELD | 9/9 |
| P3 Approval | — | 0 restarts before approval, 1 after; duplicate resume `ALREADY_EXECUTED` | HELD | 9/9 |
| P4 Suspend | suspend mid-run (`v2`) | 0 of 2 later calls executed; new run `denied AGENT_SUSPENDED` | HELD | 8/8 |
| P5 Budgets | quota 2; budget exhausted | call 3 `denied TOOL_CALL_BUDGET_EXCEEDED`; next run `denied DAILY_BUDGET_EXHAUSTED` | HELD | 7/7 |
| P6 Revoke MCP | server disabled (`v2`) | 2 agents denied, 1 unaffected, 0 server calls after | HELD | 7/7 |
| P7 Models | default moved; private model withdrawn | `fast-model` → `large-model`; confidential `DENIED NO_ALLOWED_MODEL_FOR_DATA_CLASS` | HELD | 7/7 |
| P8 Rollout | canary 25% → rollback → promote | 4/20 → 0 → 10 runs on the new version | HELD | 6/6 |
| P9a Outage | control plane unreachable | reads on `v1`; mutation `CONTROL_PLANE_UNREACHABLE`; `POLICY_STALE` past the bound | QUALIFIED | 6/6 |
| P9b Tampered bundle | forged `v2` in transit | `5` rejections; applied `v1` | HELD | 3/3 |
| P9c Broker down | — | 2 tool calls denied, 0 systems reached | HELD | 3/3 |
| P10 Drift | restart → approval; one lagging replica | 2 drift findings; 1 action under a superseded version | QUALIFIED | 7/7 |
| P11 Embedded (baseline) | four action items as code edits | 7 edits, 7 redeploys; old process `executed` | BROKEN — expected negative control | 4/4 |
| P11 Control plane | the same four, centrally | 4 versions, 0 edits, 0 redeploys | HELD | 5/5 |
| P12 Self-governance | 10 attempted changes | 3 accepted (one an in-scope restriction), 7 rejected, 11 log rows verifying | HELD | 13/13 |

**Test assertions, outcomes and proof checks are different things, and never merged.** Every scenario's own checks assert what the run was expected to show: test assertions, 100 of 100 passed. **Outcome** names the governed property: **HELD**, it held (12); **QUALIFIED**, it held within a stated bound (2: P9's outage and P10's drift); **NEGATIVE CONTROL** (1), P11's embedded baseline, whose property broke by design, which is what it is there to show. A negative control that held would be the surprising result. **Proof checks** (`pae-proof/v1`) are comparisons over the recorded facts: 79 in 13 experiments, 73 pass, 2 *limitation observed* (the ideal kill switch and the ideal drift prevention, stated and not met: the two qualifications), and 4 *expected failure* (the negative control). The Evidence Check maps every claim to them.

### 13.2 · P1, P2: the core proof

P1 establishes the baseline: under `v1` the incident agent's production restart is allowed by rule `agents.incident-agent.tools.restart_service[1]`, executed once, and executed with a credential minted for `restart_service` alone.

P2 changes only the control plane:

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P2 — CENTRAL POLICY CHANGE                                                     │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              incident-agent                                              │
│ Agent code         sha256 677bca2acd66…  UNCHANGED                             │
│ Runtime process    started once · SAME process for both requests               │
│ Request            restart_service payment-service production (identical)      │
│ Before             v1 → ALLOW → executed                                       │
│ Central change     v2 · restart-requires-approval · platform.admin             │
│ After              v2 → APPROVAL_REQUIRED → NOT executed                       │
│ Approval           approval-001 (pending)                                      │
│ Files changed      acp/: 0 · control plane store: 4                            │
│ BEFORE → AFTER                                                                 │
│   agent SHA        677bca2acd66 → 677bca2acd66  (same)                         │
│   runtime PID      rt-a/pid-1 → rt-a/pid-1  (same process)                     │
│   request hash     cb0531217710 → cb0531217710  (same)                         │
│   control plane    v1 → v2                                                     │
│   decision         ALLOW → APPROVAL_REQUIRED                                   │
│   restarts         1 → 1  (no new side effect)                                 │
│   agent edits      0 · redeploys 0                                             │
│ Audit              action.executed (v1) → approval.requested (v2)              │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ same request: request hash cb0531217710 before and after
  ✓ same runtime process: rt-a/pid-1 answered both requests, never restarted
  ✓ same agent code: sha256 677bca2acd66 before, at import and after
  ✓ files changed under acp/ by the policy change: 0
  ✓ control plane store changed (new bundle, signature, pointer, changelog)
  ✓ before: v1 ALLOW, executed
  ✓ after: v2 APPROVAL_REQUIRED, not executed
  ✓ deploy system still shows 1 restart (the side effect did not happen)
  ✓ approval request emitted and pending

  PROOF P2: PASS
  Test assertions: 9/9 passed
```

*Proof card P2, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P2`).*

| | Before (`v1`) | After (`v2`) |
|---|---|---|
| Agent source sha256 | `677bca2acd66` | `677bca2acd66` |
| Runtime process | `rt-a/pid-1` | `rt-a/pid-1` |
| Request hash | `cb0531217710` | `cb0531217710` |
| Decision | ALLOW | APPROVAL_REQUIRED |
| Deploy system: restarts | 1 | 1 |
| Agent edits · redeploys | | 0 · 0 |

- Agent source: the runtime's import-time hash matches the hash before and after.
- Files changed under `acp/` by the change: **0**. Files changed in the control plane store: **4** (bundle, signature, pointer, change log).
- Restarts in the deploy system after the second request: **1**, the one from before the change.

![Two panels: under control plane v1 the restart is ALLOW and executed; under v2 the same request is APPROVAL_REQUIRED and not executed, approval-001 pending. An evidence strip from the recorded run: agent SHA same, runtime process same, request hash same, agent edits 0, redeploys 0.](../diagrams/premium/png/proof-same-code.png)

`MEASURED` *Figure 12. P2 as an experiment card: same agent, same process, same request; only the central policy changed.* · Recorded: P2 · run 2026-10-03-recorded

P2 is built to fail when it should: `tests/test_cheating.py` breaks code, process or request in turn, and P2 fails each time (§12.3).

### 13.3 · P3: held, approved, executed once

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P3 — APPROVAL, THEN EXACTLY ONE EXECUTION                                      │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              incident-agent                                              │
│ Policy version     v2 (restart requires approval)                              │
│ Held action        approval-001 · restart_service payment-service production   │
│ Before approval    resume → APPROVAL_PENDING · restarts 0                      │
│ incident-agent     approve → an agent cannot approve its own action            │
│ support.lead       approve → support.lead is not an eligible approver for      │
│                    restart_service                                             │
│ ic.dev             approve → approved                                          │
│ Resume             APPROVED_AND_EXECUTED · restarts 1                          │
│ Resume again       ALREADY_EXECUTED · restarts still 1                         │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ held action not executed before approval (resume refused, 0 restarts)
  ✓ the agent cannot approve its own action
  ✓ an ineligible principal cannot approve
  ✓ the eligible incident commander's approval is accepted
  ✓ resume after approval executes under the current policy
  ✓ a second resume does not execute again (ALREADY_EXECUTED)
  ✓ deploy system shows exactly 1 restart
  ✓ the executed event carries the approval id
  ✓ agent code unchanged, one runtime process

  PROOF P3: PASS
  Test assertions: 9/9 passed
```

*Proof card P3, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P3`).*

Three things matter beyond the happy path. The runtime refused to resume before a decision. The agent is refused as approver of its own action (the approval service treats any principal equal to the requesting agent, or any workload identity, as ineligible). And a second resume, as a duplicate delivery would cause, is refused as `ALREADY_EXECUTED`, not re-executed. T3 covers the durable gate in depth [28]; P3 shows its *policy* arriving from the control plane.

### 13.4 · P4: the kill switch, including mid-run

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P4 — SUSPEND: THE KILL SWITCH                                                  │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              incident-agent · status active → suspended                  │
│ Central change     v2 · suspend-incident-agent · oncall.ic (break-glass)       │
│ Run in flight      run-001 paused after query_logs; 2 later calls → 0 executed │
│ New run            run-002 → DENIED AGENT_SUSPENDED · 0 tool calls · 0 model   │
│                    calls                                                       │
│ Other agents       support-agent run-003 → every call executed                 │
│ Restore alone      oncall.ic → REJECTED (widening needs a second approver)     │
│ Restore            v3 · oncall.ic + sre.lead → run-004 executes                │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ in-flight run: every call after the suspension was denied (0 executed)
  ✓ in-flight run: denial reason is AGENT_SUSPENDED under the new version
  ✓ new run denied at start: 0 tool calls, 0 model calls
  ✓ no production restart happened
  ✓ support-agent unaffected (every call executed)
  ✓ restoring needs a second person: oncall.ic alone rejected
  ✓ restore with sre.lead as second approver works at the next run
  ✓ agent code unchanged, one runtime process

  PROOF P4: PASS
  Test assertions: 8/8 passed
```

*Proof card P4, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P4`).*

The run in flight had executed `query_logs` when the suspension was published. Its next two enforcement points (`query_metrics`, the model call) both synced `v2` and were denied `AGENT_SUSPENDED`. Because metrics never arrived, the agent's own logic never reached `restart_service`. The support agent, served by the same process in the same state, completed every call: a suspension scoped to one agent stops one agent.

### 13.5 · P5: quotas and budgets

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P5 — BUDGETS AND QUOTAS                                                        │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              support-agent                                               │
│ Central change     v2 · max_tool_calls = 2 · support.lead                      │
│ CALL 1             read_case → EXECUTED                                        │
│ CALL 2             query_logs → EXECUTED                                       │
│ CALL 3             refund_customer → DENY · TOOL_CALL_BUDGET_EXCEEDED          │
│ Refunds            1 (from run-001, before the quota)                          │
│ Central change     v3 · daily budget below today's spend ($0.7104)             │
│ Next run           run-003 → DENIED DAILY_BUDGET_EXHAUSTED                     │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ before the quota: 3 tool calls executed, 1 refund
  ✓ call 1 ALLOW, call 2 ALLOW
  ✓ call 3 DENY TOOL_CALL_BUDGET_EXCEEDED
  ✓ billing system shows 1 refund (the capped run refunded nothing)
  ✓ exhausted daily budget: next run denied at start
  ✓ the budget is metered centrally (shared spend meter), not per process
  ✓ agent code unchanged, one runtime process

  PROOF P5: PASS
  Test assertions: 7/7 passed
```

*Proof card P5, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P5`).*

Two kinds of limit, two enforcement moments: a per-run quota stops the *call* that would exceed it; an exhausted daily budget stops the *run* at its start, before any model or tool is touched. Spend is metered in a shared service (`0.7` USD before the budget change), so adding runtime replicas doesn't multiply the budget.

### 13.6 · P6: one server, every agent

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P6 — REVOKE ONE MCP SERVER FOR EVERY AGENT                                     │
├────────────────────────────────────────────────────────────────────────────────┤
│ Shared tool        query_logs (observability-mcp)                              │
│ Before             incident-agent → ALLOW · support-agent → ALLOW              │
│ Central change     v2 · observability-mcp = disabled · platform.admin (break-  │
│                    glass)                                                      │
│ After              incident-agent → DENY · support-agent → DENY                │
│                    (MCP_SERVER_DISABLED)                                       │
│ Unaffected         finance-agent → every call executed                         │
│ observability-mcp  3 calls before · 0 after                                    │
│ Agent code         UNCHANGED · 0 files edited · 0 redeploys                    │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ before: incident-agent query_logs ALLOW
  ✓ before: support-agent query_logs ALLOW
  ✓ after: incident-agent query_logs DENY MCP_SERVER_DISABLED
  ✓ after: support-agent query_logs DENY MCP_SERVER_DISABLED
  ✓ observability-mcp received 0 calls after the revocation
  ✓ finance-agent (no observability tools) unaffected
  ✓ one central change, 0 agent files changed

  PROOF P6: PASS
  Test assertions: 7/7 passed
```

*Proof card P6, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P6`).*

The MCP servers are simulated boundaries (`acp/systems.py`). P6 shows central revocation of a tool server for every agent that uses it; it does not validate MCP protocol interoperability or a real MCP deployment.

### 13.7 · P7: models without model names

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P7 — MODEL GOVERNANCE                                                          │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agents             incident-agent (internal data) · support-agent              │
│                    (confidential case)                                         │
│ Agent code         names no model: 0 catalog names in acp/agents/              │
│ v1                 incident → fast-model · support → private-model             │
│ Central change     v2 · default model → large-model (platform.admin + ml.lead) │
│ v2                 incident → large-model · support → private-model            │
│ Central change     v3 · private-model withdrawn (break-glass)                  │
│ v3                 incident → large-model · support → DENIED (no fallback to a │
│                    public model)                                               │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ agent source names no model (0 catalog names in acp/agents/)
  ✓ v1: incident-agent served by fast-model
  ✓ v2: incident-agent served by large-model, agent unchanged
  ✓ confidential data always served by private-model while it is allowed
  ✓ v3: private-model withdrawn → confidential call DENIED, no fallback to a
    public model
  ✓ no confidential prompt ever reached a model without confidential clearance
  ✓ agent code unchanged, one runtime process

  PROOF P7: PASS
  Test assertions: 7/7 passed
```

*Proof card P7, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P7`).*

The confidential case matters most. When `private-model` was withdrawn, the confidential call had two options: fall back to the next model in the profile, or fail. The profile resolves confidential data only to its `confidential` model, and the catalog only allows models whose `data_classes` include `confidential`; with none available it **failed closed**. Across the run, 2 confidential prompts reached a model, and each of them reached one cleared for confidential data.

### 13.8 · P8: staged rollout

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P8 — STAGED ROLLOUT AND ROLLBACK                                               │
├────────────────────────────────────────────────────────────────────────────────┤
│ Agent              finance-agent (20 + 20 + 10 runs)                           │
│ Change             v2 · default model → large-model, published inactive        │
│ Canary 25%         4 of 20 runs on v2 (large-model) · rest on v1               │
│ Rollback           0 of 20 runs on v2                                          │
│ Promote            10 of 10 runs on v2                                         │
│ Agent code         UNCHANGED · no redeploy at any step                         │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ canary reached some but not all runs
  ✓ canary membership = deterministic bucket < 25
  ✓ every run used exactly one version, and its model matches it
  ✓ after rollback: 0 runs on the canary version
  ✓ after promote: every run on the new version
  ✓ agent code unchanged, one runtime process

  PROOF P8: PASS
  Test assertions: 6/6 passed
```

*Proof card P8, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P8`).*

The canary share (4 of 20 runs at 25%) is a property of the run ids' hashes, not of chance: the same ids land in the same buckets in every rerun. Every run used exactly one configuration version, and its model matched that version.

### 13.9 · P9: failure behaviour

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P9a — CONTROL PLANE UNREACHABLE                                                │
├────────────────────────────────────────────────────────────────────────────────┤
│ Runtime            rt-a · last-known-good v1 cached                            │
│ Read (query_logs)  ALLOW from last-known-good v1                               │
│ Mutation (restart) DENY · CONTROL_PLANE_UNREACHABLE (fail closed)              │
│ Suspension         v2 published during the partition                           │
│ …after it          3 read/model calls still executed on v1  ← QUALIFIED        │
│ Past staleness     DENY · POLICY_STALE for everything                          │
│ Partition heals    next run → DENY · AGENT_SUSPENDED                           │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ reads during the outage ran on the last-known-good bundle (v1)
  ✓ production mutation during the outage failed closed
    (CONTROL_PLANE_UNREACHABLE)
  ✓ deploy system: only the warm run's restart (1)
  ✓ QUALIFIED: the suspension could not reach a partitioned runtime; reads
    continued under v1
  ✓ beyond max_staleness every run is denied (POLICY_STALE)
  ✓ after recovery the suspension lands at the next enforcement point

  PROOF P9a: QUALIFIED · held within the stated bound (max staleness, fail-closed mutations)
  Test assertions: 6/6 passed
```

*Proof card P9a, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P9a`).*

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P9b — TAMPERED BUNDLE IN TRANSIT                                               │
├────────────────────────────────────────────────────────────────────────────────┤
│ Attack             v2 altered to allow delete_resource and production restarts │
│ Runtime            signature check FAILED → 5 config.rejected events           │
│ Applied            v1 (last-known-good); the altered bundle never applied      │
│ Mutation           restart_service → DENY · BUNDLE_REJECTED (fail closed)      │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ the altered bundle failed signature verification and was not applied
  ✓ the mutation failed closed while no verified current bundle was available
    (BUNDLE_REJECTED)
  ✓ deploy system: no production restart, no deletion

  PROOF P9b: PASS
  Test assertions: 3/3 passed
```

*Proof card P9b, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P9b`).*

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P9c — CREDENTIAL BROKER DOWN                                                   │
├────────────────────────────────────────────────────────────────────────────────┤
│ Policy             v1 · query_logs, query_metrics ALLOW                        │
│ Broker             unavailable                                                 │
│ Result             every tool call → DENY · CREDENTIAL_UNAVAILABLE             │
│ Systems            0 calls received · 0 restarts                               │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ every tool call denied CREDENTIAL_UNAVAILABLE (policy allowed them)
  ✓ no system received a call without a credential
  ✓ deploy system: 0 restarts

  PROOF P9c: PASS
  Test assertions: 3/3 passed
```

*Proof card P9c, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P9c`).*

### 13.10 · P10: drift

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P10 — DESIRED VS OBSERVED STATE                                                │
├────────────────────────────────────────────────────────────────────────────────┤
│ Desired            v2 (restart requires approval)                              │
│ rt-a observed      v2 → restart held for approval                              │
│ rt-b observed      v1 → restart EXECUTED (lagging replica, no error)           │
│ Drift              2 findings · stale_config rt-b ·                            │
│                    executed_under_superseded_config                            │
│ Under desired      that restart → APPROVAL_REQUIRED                            │
│ Reconcile          replica fixed · stale instances 0                           │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ rt-a applied v2 and held the restart for approval
  ✓ rt-b, behind the lagging replica, executed the restart under v1
  ✓ drift detected: rt-b observed v1 while desired is v2
  ✓ drift detected: a mutation executed under a superseded version
  ✓ re-evaluated under the desired version, that action required approval
  ✓ after reconcile: no instance on a stale version
  ✓ agent code unchanged; both runtime processes never restarted

  PROOF P10: QUALIFIED · drift detected, not prevented
  Test assertions: 7/7 passed
```

*Proof card P10, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P10`).*

This is the result I'd want a platform team to take away. **Policy didn't prevent the restart on `rt-b`; observation caught it.** A runtime that believes it's current, behind a distribution path that fails silently, will enforce the old rules faithfully. The control plane's defence is the loop: runtimes report versions, events carry versions, and the control plane compares both with the desired state. After the replica was fixed, `rt-b` re-synced and stale instances went to 0. Bundle expiry (section 9.3) would have turned the silent case into a bounded one.

### 13.11 · P11: the same four changes, without a control plane

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P11a — NEGATIVE CONTROL: GOVERNANCE INSIDE EVERY AGENT                         │
├────────────────────────────────────────────────────────────────────────────────┤
│ Change             production restarts need approval                           │
│ Edit               incident_agent.py · sha256 aae655907550… → 3a424afcaad3…    │
│ Running process    after the edit → restart EXECUTED  ← policy not in effect   │
│ Redeployed process restart → PENDING_APPROVAL                                  │
│ All four changes   7 file edits · 17 lines · 7 agent redeploys                 │
│ Credentials        8 static credential literals in agent code                  │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ before the edit the embedded agent restarts production
  ✓ BROKEN: after the edit, the running process still restarts production (no
    central change is possible)
  ✓ only a redeployed process (new code hash) holds the restart
  ✓ the embedded agents hold long-lived static credentials in code

  PROOF P11a: NEGATIVE CONTROL · property broken by design
  Test assertions: 4/4 passed
```

*Proof card P11a, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P11a`).*

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P11b — THE SAME FOUR CHANGES THROUGH THE CONTROL PLANE                         │
├────────────────────────────────────────────────────────────────────────────────┤
│ Changes            model default · restart approval · revoke MCP · suspend     │
│ Published          v2 … v5 · 4 signed bundle versions                          │
│ Agent code         0 files edited · 0 redeploys · one runtime process          │
│                    throughout                                                  │
│ Effect             each change applied at the next enforcement point           │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ default model moved at the next run (large-model)
  ✓ restart held for approval at the next run
  ✓ observability tools denied at the next run
  ✓ incident-agent denied at the next run
  ✓ 0 agent files edited, 0 processes restarted, 4 bundle versions

  PROOF P11b: PASS
  Test assertions: 5/5 passed
```

*Proof card P11b, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P11b`).*

| Change | Embedded: agent files edited | Control plane |
|---|---|---|
| production restarts need approval | 1 | 1 version |
| disable `observability-mcp` | 2 | 1 version |
| suspend the incident agent | 1 (no switch exists; add one) | 1 version |
| move the default model | 3 | 1 version |

The counts grow with the number of agents that embed each rule. Three agents is the smallest estate where the effect shows. The point isn't the numbers: it's that the running process kept the old rule until it was replaced. P11a's card says so in its verdict, **NEGATIVE CONTROL · property broken by design**, and its test assertions all passed: they assert that the break was observed. In the proof pack its four control checks are *expected failures*, and `evidence/runs/2026-10-03-recorded/negative-control/results.json` records the safeguard removed, the invariant, and that the harness completed.

### 13.12 · P12: governing the control plane

```text
╭────────────────────────────────────────────────────────────────────────────────╮
│ P12 — GOVERNING THE CONTROL PLANE ITSELF                                       │
├────────────────────────────────────────────────────────────────────────────────┤
│ incident-agent     grant itself delete_resource → REJECTED · incident-agent is │
│                    not a control-plane administrator                           │
│ support.lead       raise incident-agent's tool quota → REJECTED · support.lead │
│                    has no scope over incident-agent                            │
│ support.lead       lower support-agent's tool quota (own scope) → ACCEPTED ·   │
│                    v2                                                          │
│ platform.admin     widen incident-agent's tools alone → REJECTED · a widening  │
│                    change needs a second approver                              │
│ platform.admin     platform.admin as its own second approver → REJECTED · the  │
│                    second approver must be a different person                  │
│ oncall.ic          raise a quota via break-glass → REJECTED · a break-glass    │
│                    change may only restrict behaviour                          │
│ platform.admin     a plaintext credential in the registry (with sre.lead) →    │
│                    REJECTED · tool restart_service: credential must be a       │
│                    secret:// reference, never a value                          │
│ oncall.ic          suspend incident-agent (break-glass) → ACCEPTED · v3        │
│ oncall.ic          restore incident-agent alone → REJECTED · a widening change │
│                    needs a second approver                                     │
│ oncall.ic          restore incident-agent with sre.lead → ACCEPTED · v4        │
│ Change log         11 rows, hash-chained · verifies; one edited row → chain    │
│                    broken · tamper-evident local log under POC assumptions     │
╰────────────────────────────────────────────────────────────────────────────────╯
  ✓ an agent cannot change the control plane (not an administrator)
  ✓ scope: a team lead cannot change another team's agent
  ✓ scope: a team lead may restrict its own agent alone
  ✓ two-person rule: a widening change needs a second approver
  ✓ two-person rule: the second approver must be a different person
  ✓ break-glass may only restrict
  ✓ validation: a plaintext credential never becomes a version
  ✓ break-glass suspension accepted from one on-call person
  ✓ restoring (widening) needs a second person
  ✓ every attempt is on the change log, accepted or rejected
  ✓ the change log is hash-chained and verifies
  ✓ editing one change-log row breaks the chain
  ✓ every version is signed; no bundle contains a plaintext credential

  PROOF P12: PASS
  Test assertions: 13/13 passed
```

*Proof card P12, verbatim from `control_plane_poc/runs/2026-10-03-recorded/proof.txt` (printed by `acp proof P12`).*

The attempts are chosen to separate authority from mechanics. An agent is not an administrator. A team lead's scope is its own agents: the support lead raising the incident agent's quota is rejected, and the same lead lowering its own support agent's quota is `accepted`, alone, because restricting needs speed and no second person. Widening needs a second, different, eligible approver. Break-glass may only restrict. Validation runs before authorization, so a plaintext credential is `rejected` whoever sends it. The chain verifies, and an edited copy of it does not (`no`): a tamper-evident local log under POC assumptions, not an immutable audit store.

### 13.13 · Integrity

| Check | Result |
|---|---|
| Test assertions passed | 100 of 100 |
| Proof checks (`pae-proof/v1`) | 79: 73 pass, 2 limitation observed, 4 expected failure |
| Scenarios | 15 across 12 proofs |
| Separate runtime processes started | 16 (one per scenario and instance; 0 restarted) |
| Hash chains and signatures | 14 audit and 14 change-log chains; 34 bundle signatures; all recomputed |
| Bundle versions published across the run | 34 |
| Runtime audit events (hash-chained) | 595 |
| Rerun in a fresh copy (`make verify`) | EXACT: 240 files byte-identical, 15 equal with raw process ids masked, 0 different |
| POC test suite | architecture, invariant, cheating-detection, decision and end-to-end tests (`make test`); see `QA.md` |
| Final gate | `make verify-all` → `verification/final_verification.md` |

## 14 · What surprised me, and the limits of this POC

### 14.1 · What surprised me

- **The hard part of a kill switch is distribution, not the switch.** Suspending an agent is one field. Getting that field to a runtime that can't hear you is the whole problem (P9), and a runtime that thinks it hears you but is fed old data is worse (P10).
- **Per-run consistency and emergency control pull in opposite directions.** Pin a run to the version it started with and every in-flight run ignores the kill switch. Let it pick up new versions at each enforcement point and a run can straddle two versions. The POC takes the second option and records every version a run used, which makes the straddle visible instead of hidden.
- **"Restricting vs widening" turned out to be the most useful property of a change.** It decides who may publish, whether a second person is needed, whether break-glass applies, and it's cheap to compute from the old and new values.
- **The cheapest security control was validation.** Refusing a plaintext credential before it becomes a version took a few lines and closes a whole class of leak.

### 14.2 · Limitations

*Limitation: what this POC does not show*

- **Deterministic agents in the recorded run.** Plans are fixed so every proof is reproducible. A model changes *what the agent asks for*, not *what the control plane allows*, which is the property under test. Live mode (§12.8) puts an LLM in the loop for L1–L3, but its runs vary and are illustrative; no model-run result is part of this note's evidence.
- **Simulated systems and distribution.** Enterprise systems, MCP servers, models, network partitions, lagging replicas and in-transit tampering are simulated with local state and flags. Propagation is immediate at the next call; production has real latency.
- **One environment, one tenant.** Environment and tenant isolation, and admin authentication, are argued, not exercised.
- **Local HMAC signing, logical time.** Production needs asymmetric signing with managed keys, and bundle expiry in real time.
- **Three agents.** The embedded-baseline footprint (P11) scales with the number of agents that embed each rule; the POC measures the smallest case.
- **Not a benchmark.** No latency, throughput or availability numbers; the POC proves properties, not performance.

## 15 · From the POC to production

![POC components on the left, production equivalents on the right.](../diagrams/premium/png/poc-to-production.png)

`ARCHITECTURE` *Figure 13. What each POC component stands in for in production.* · Architecture: mapping (our synthesis); no measured values

| POC | Production |
|---|---|
| YAML desired state + a state directory | a replicated configuration and policy service with a database of record |
| `validate()` in `publish()` | CI policy tests on every change, plus server-side validation |
| admin scopes in `admins.yaml` | the organisation's IdP groups, with MFA and just-in-time elevation |
| HMAC-signed bundles | asymmetric signatures, keys in a KMS or HSM, runtimes hold public keys only |
| a pointer file read at each call | push or watch distribution with acknowledgements and bundle expiry |
| `pdp.py` inside the runtime | an SDK, gateway or sidecar policy enforcement point, possibly backed by a policy engine such as OPA [7] |
| in-process approval queue | a durable workflow and approval service (T3) |
| in-process credential minting | a secret broker issuing leased, audience-bound credentials [13] |
| JSON spend file | a shared quota and budget service with atomic counters |
| hash-chained JSONL: tamper-evident on one machine, under the POC's assumptions (whoever can rewrite the whole file can rewrite the chain) | an immutable external audit store; decision logs with bundle metadata [9] |
| logical ticks | real time; staleness and expiry measured in seconds |

The architectural invariant carries over: runtime behaviour follows centrally versioned policy, without changing or redeploying agents. Production adds what the POC compresses away: real distribution, durability, consistency, security and availability constraints.

## 16 · The reference architecture

![Down the centre, four zones: experience and applications; the agent runtime (planning, reasoning, memory, context, workflow); runtime enforcement, split into local (policy cache, PDP and PEP, authorization, tool gate, model gate, guardrails, data policy, limits, signature and version verification) and online where necessary (approval service, credential broker, shared budget service, high-risk authorization, freshness and revocation); and execution (models, MCP servers, tools, APIs, databases, production systems). On the left the AI control plane distributing signed desired state; on the right observability and audit feeding observed state back to reconciliation.](../diagrams/premium/png/reference-architecture.png)

`ARCHITECTURE` *Figure 14. A reference architecture for an AI control plane: four execution zones, governed from the side.* · Architecture: reference (our synthesis); no measured values

The layers, top to bottom:

- **Experience and applications**: users, APIs, automation and other agents invoking the runtime (F3).
- **Agent runtime**: planning, reasoning, memory, workflow, context. Business reasoning lives here and nowhere else.
- **Runtime enforcement, local**: the policy cache, signature and version verification, the decision and enforcement points (PDP, PEP), authorization, tool and model gates, guardrails, data policy, static limits. Every call passes through it, locally, with no network hop.
- **Runtime enforcement, online where necessary**: the approval service, the credential broker, the shared budget service, high-risk authorization that needs live context, and freshness or revocation checks for actions where a stale answer is unacceptable. Called synchronously and only when a decision needs them. They are the runtime's real online dependencies, so each has its own failure policy (§9.1).
- **Execution**: models, MCP servers, tools, APIs, databases, production systems.

Governing them from the side, not from inside the request path:

- **The AI control plane**: agent registry, identity bindings, policy, guardrails and data-handling policy, tool and MCP registry, model governance, approval policy, budgets, versions and rollouts, runtime state, emergency controls, secret bindings.
- **Observability and audit**: traces, metrics, decisions, policy rules, config versions, approvals, tools, models, cost, drift and side effects, feeding observed state back to the control plane's reconcile step.

## 17 · How the series' capabilities become platform primitives

![Six series cards feeding primitives into the control plane.](../diagrams/premium/png/series-primitives.png)

`ARCHITECTURE` *Figure 15. Earlier notes built individual capabilities; the control plane makes them centrally governable.* · Series map: the series order; no results claimed

| Note | The capability | What the control plane adds |
|---|---|---|
| F1 · MCP Tool Sprawl [24] | one agent's capability control plane | a registry of servers and tools across all agents, revocable per server |
| F2 · Layered Architecture [25] | responsibilities in layers | one owner for the control concerns that cut across the layers |
| F3 · Headless AI | many consumers, one runtime | the same governance whichever head invoked the agent |
| T1 · Agent Identity [26] | identity chains, minted credentials | bindings: which agent, on which workload, with which secret references |
| T2 · Authorization [27] | an external policy decision | versioned, distributed policy with change governance |
| T3 · Human-in-the-Loop [28] | a durable approval gate | approval *policy*, owned centrally, not decided by the agent |

| Budgets | a spend meter per run | shared budgets, metered once, so replicas cannot multiply them |
| Models | a gateway | which models may process which task and data class, decided centrally |
| Observability | traces and audit | the version and rule on every event: what actually happened, and under which governance |

**The control plane doesn't replace these primitives. It coordinates their governance:** where they are defined, versioned, distributed, changed and reconciled.

None of this requires one service. The control plane is a logical boundary. Its parts can be different systems, as long as each change to them is governed, versioned, distributed and observable.

## 18 · Production checklist

- [ ] Every agent has a stable identity, bound to the workload it runs on.
- [ ] Every agent is registered with an owner, a purpose, a risk level and a lifecycle status.
- [ ] Policies live outside prompts and outside agent code; architecture tests enforce it.
- [ ] Tool access is centrally governable per agent, per tool and per MCP server; servers are version-pinned and revocable.
- [ ] Model usage is governed by profile and data class; confidential data fails closed rather than falling back.
- [ ] High-risk actions have an approval policy with eligible approvers and expiry; agents cannot approve themselves.
- [ ] Budgets and quotas are hard limits, metered centrally, with alerts as a separate layer.
- [ ] Credentials are references in configuration and short-lived, audience-bound leases at runtime.
- [ ] Every change is validated, authorized, versioned, signed and logged, rejected ones included.
- [ ] Widening changes need a second, different approver; break-glass may only restrict.
- [ ] Every runtime reports its config version; every event records the version it was decided under.
- [ ] Rollouts are staged and rollback is one action.
- [ ] Agents can be paused, quarantined, suspended and disabled, including mid-run.
- [ ] The failure policy is written per risk class: last-known-good reads, fail-closed mutations, a staleness bound, bundle expiry.
- [ ] Desired and observed state are compared continuously; drift is an alert with an owner.
- [ ] The control plane itself has isolation per environment and tenant, backups, recovery drills and high availability.

## 19 · Reproduce

```bash
cd ai_control_plane
make setup        # uv environment: Python 3.12, pyyaml, pytest, ruff
make test         # architecture, invariant, cheating-detection, decision and end-to-end tests
make proof        # every proof card, printed (runs into a scratch directory)
make demo         # P2 only: same process, same code, same request, different central policy
make verify       # rerun every proof in a fresh copy; identical to the published run (process ids masked)
make pack         # the pae-proof/v1 proof pack of the published run (evidence/runs/<run>/)
make evidence     # PROOF VERIFICATION of the published run
make verify-all   # the final gate: lint, tests, replay, proof pack, verification, documents, figures, Lab Console
make live-dry     # L1–L3, the live path, with a scripted stand-in model (no Ollama needed)
make live         # L1–L3 with a self-hosted LLM (Ollama, qwen3:8b) planning the agent; illustrative
open results/lab-console.html
```

## 20 · Conclusion

At small scale, governance can hide inside application code. At platform scale, the same approach turns into duplication, drift, inconsistent enforcement and a redeploy for every policy change. The AI control plane changes the unit of governance from the individual agent to the platform: declare the boundaries once, distribute them as signed versions, enforce them at every call, observe what actually ran, and reconcile the difference.

> **Agents decide how to accomplish a task. The control plane decides the boundaries within which they are allowed to operate.**

## References

Every source was fetched and its supporting passage quoted in `research/sources.md`, together with what it does *not* support.

**[1]** Kubernetes — Controllers. [kubernetes.io/docs/concepts/architecture/controller](https://kubernetes.io/docs/concepts/architecture/controller/). Control loops; desired state vs current state.

**[2]** Kubernetes — Components. [kubernetes.io/docs/concepts/overview/components](https://kubernetes.io/docs/concepts/overview/components/). A control plane that manages the overall state of the cluster.

**[3]** AWS — Control planes and data planes (AWS Fault Isolation Boundaries). [docs.aws.amazon.com/whitepapers/latest/aws-fault-isolation-boundaries/control-planes-and-data-planes.html](https://docs.aws.amazon.com/whitepapers/latest/aws-fault-isolation-boundaries/control-planes-and-data-planes.html). Policies created and distributed from the control plane; simpler data planes.

**[4]** Amazon Builders' Library — Static stability using Availability Zones. [aws.amazon.com/builders-library/static-stability-using-availability-zones](https://aws.amazon.com/builders-library/static-stability-using-availability-zones/). Control plane vs data plane; statically stable data planes.

**[5]** Envoy — xDS REST and gRPC protocol. [envoyproxy.io/docs/envoy/latest/api-docs/xds_protocol](https://www.envoyproxy.io/docs/envoy/latest/api-docs/xds_protocol). Versioned resources; last valid configuration kept on rejection; eventual consistency.

**[6]** Istio — Architecture. [istio.io/latest/docs/ops/deployment/architecture](https://istio.io/latest/docs/ops/deployment/architecture/). A mesh logically split into data plane and control plane.

**[7]** Open Policy Agent — Documentation. [openpolicyagent.org/docs](https://www.openpolicyagent.org/docs). Decoupling policy decision-making from enforcement.

**[8]** Open Policy Agent — Bundles. [openpolicyagent.org/docs/management-bundles](https://www.openpolicyagent.org/docs/management-bundles). Signed bundles; polling; persisted last-activated bundle.

**[9]** Open Policy Agent — Decision Logs. [openpolicyagent.org/docs/management-decision-logs](https://www.openpolicyagent.org/docs/management-decision-logs). Decision events with bundle metadata for auditing.

**[10]** NIST SP 800-207 — Zero Trust Architecture. [csrc.nist.gov/pubs/sp/800/207/final](https://csrc.nist.gov/pubs/sp/800/207/final). Per-request least-privilege decisions; non-person entities, including AI agents.

**[11]** SPIFFE — Concepts. [spiffe.io/docs/latest/spiffe-about/spiffe-concepts](https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/). Workload identity; short-lived SVIDs.

**[12]** RFC 8693 — OAuth 2.0 Token Exchange. [rfc-editor.org/rfc/rfc8693](https://www.rfc-editor.org/rfc/rfc8693.html). Delegation vs impersonation.

**[13]** HashiCorp Vault — Lease, Renew, and Revoke. [developer.hashicorp.com/vault/docs/concepts/lease](https://developer.hashicorp.com/vault/docs/concepts/lease). Leased dynamic secrets; immediate revocation.

**[14]** Model Context Protocol — Authorization (2026-07-28). [modelcontextprotocol.io/specification/2026-07-28/basic/authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization). Servers validate token audience.

**[15]** Model Context Protocol — Tools (2026-07-28). [modelcontextprotocol.io/specification/2026-07-28/server/tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools). Human in the loop SHOULD; no mandated interaction model.

**[16]** Model Context Protocol — The MCP Registry. [modelcontextprotocol.io/registry/about](https://modelcontextprotocol.io/registry/about). Public servers only; private registries recommended for private servers.

**[17]** OpenTelemetry — Semantic conventions for generative AI. [github.com/open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai). Model, tool and agent spans (status: Development).

**[18]** OWASP — LLM06:2025 Excessive Agency. [genai.owasp.org/llmrisk/llm062025-excessive-agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/). Complete mediation in downstream systems.

**[19]** OWASP — Top 10 for Agentic Applications for 2026. [genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/). Governed agent identity; short-lived scoped credentials.

**[20]** NIST AI RMF 1.0 (NIST AI 100-1). [nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf). GOVERN: defined roles and responsibilities for human-AI configurations.

**[21]** The Update Framework — Security. [theupdateframework.io/docs/security](https://theupdateframework.io/docs/security/). Indefinite freeze attacks; trust should expire if not renewed.

**[22]** Pete Hodgson — Feature Toggles (aka Feature Flags). [martinfowler.com/articles/feature-toggles.html](https://martinfowler.com/articles/feature-toggles.html). Long-lived operational kill switches.

**[23]** Google — The Site Reliability Workbook, Canarying Releases. [sre.google/workbook/canarying-releases](https://sre.google/workbook/canarying-releases/). Canarying as a partial, time-limited deployment with evaluation.

**[24]** Production AI Engineering, F1 — Your AI Agent Has 500 MCP Tools. Now What? [../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html).

**[25]** Production AI Engineering, F2 — Your Agent Works in a Demo. Why Does It Break in Production? [../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html).

**[26]** Production AI Engineering, T1 — Agent Identity: Who Is Acting, and on Whose Authority? [../../agent_identity/medium/agent-identity-medium.html](../../agent_identity/medium/agent-identity-medium.html).

**[27]** Production AI Engineering, T2 — Authorization and Policy for AI Agents. [../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html).

**[28]** Production AI Engineering, T3 — the Human-in-the-Loop chapter. [../../human_in_the_loop/medium/human-in-the-loop-medium.html](../../human_in_the_loop/medium/human-in-the-loop-medium.html).

---

**Series.** Foundation: [F1 · MCP Tool Sprawl](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html) · [F2 · Layered Architecture](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html) · [F3 · Headless AI](../../headless_ai/medium/headless-ai-medium.html) · Trust: [T1 · Agent Identity](../../agent_identity/medium/agent-identity-medium.html) · [T2 · Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · Previous: [T3 · Human-in-the-Loop](../../human_in_the_loop/medium/human-in-the-loop-medium.html) · Current: T4 · AI Control Plane · Next: [T5 · Observability & Governance](../../governance_for_ai_agents/medium/observability-governance-medium.html). Companions: [Medium edition](../medium/ai-control-plane-medium.md) · [Evidence Check](../results/ai-control-plane-evidence.md). Every measured number is substituted from `control_plane_poc/runs/2026-10-03-recorded/facts.json`.
