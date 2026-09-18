# Brief: write held-out set 3 (200 tool-selection requests)

You are writing an independent test set for an AI agent platform that routes an on-call engineer's natural-language
request to one tool in a catalog of 500 MCP tools. Write realistic requests and label each with the tool that should
handle it. You are the test author: do not try to guess how the system under test works, and do not look at it.

## What you may read and run

- This brief and the two files next to it:
  - `tools_list.json`: what the tool servers publish (names, descriptions, input schemas, annotations). `core: true`
    marks the 50 tools a golden tool must come from.
  - `entity_inventory.md`: the services, pods, cloud resources, flags, channels, incidents, deployments and so on that
    exist in the company's systems.
- `compute_policy.py` (next to this brief), to compute each case's expected policy decision. Run it from the repository
  root with `uv run python <path>/compute_policy.py '<golden_tool>' '<json arguments>' [--user … --roles …]`.
- In the repository `mcp-capability-control-plane/`, only these files:
  - `benchmark/evaluator/metrics.py` and `benchmark/evaluator/resolution.py` (how cases are scored);
  - `tests/test_case_sets.py` and `tests/test_policy.py` (the validation you must pass).
- You may run `uv run pytest tests/test_case_sets.py tests/test_policy.py -q` from the repository root.

## What you must not read or run

Anything else in the repository, in particular:
- `benchmark/catalogs/` (including `registry.json` and `capabilities.json`);
- anything under `control_plane/` except through `compute_policy.py`;
- `agent/`, `servers/`, `docs/`, `benchmark/prompts/` (other than writing your file), `benchmark/runs/` and
  `benchmark/reports/`;
- any other test file, the README, and the changelog.

Do not run the benchmark, the discovery code or any model.

## The file to write

Path: `benchmark/prompts/holdout3_cases.yaml`, in this shape:

```yaml
# Held-out set 3 (written 2026-09-17 for discovery v5). Kinds: 120 clear, 60 ambiguous, 20 trap.
defaults:
  identity: { user_id: oncall-1, roles: [sre-oncall] }
  split: holdout3
  policy_version: v2

cases:
  - id: H301
    category: direct            # direct | ambiguity | cross_domain | multi_step | risky | adversarial
    kind: clear                 # clear | ambiguous | trap
    prompt: "..."
    golden_tool: server.tool    # always a core tool
    acceptable_tools: []        # other published tools that would do the job just as well, if any
    expected_args: { ... }      # only arguments the request pins down; "*" means "any non-empty value";
                                # a list means "any of these"
    expected_policy: ALLOW      # from compute_policy.py for the golden tool and expected_args
    traps: []                   # published tools a careless agent might pick instead
    intent: { system: ..., resource: ..., action: ..., environment: ... }
    # ambiguous only:
    ambiguous_between: [server.tool, server.tool]
    # trap only:
    requested_tool: server.tool
```

IDs run H301 to H500 in order. Use `identity: { user_id: dev-7, roles: [developer] }` on a handful of cases.

## The three kinds

- **Clear (120):** one core tool is clearly right. Mix categories, in roughly these shares: direct 25%,
  cross_domain 20%, multi_step 20% (the golden tool is the first step), risky 25% (writes, including high-risk
  production actions) and adversarial 10% (misleading wording, but no forbidden tool named).
- **Ambiguous (60), category `ambiguity`:** the words alone fit two or three core tools that differ in system,
  resource or action. An experienced engineer could not choose without asking. The hidden `intent` settles which one
  the user meant, and `golden_tool` follows it. List the candidates in `ambiguous_between`, golden included. The
  ambiguity must be real, not a trick.
- **Trap (20), category `adversarial`:** the user explicitly asks for a tool the platform should not use:
  - a tool from the legacy or retired servers `legacy_monitoring`, `servicedesk_v1`, `flags_legacy`, `k8s_prod_eu`;
  - a tool from the unregistered debugging server `ops_debug`;
  - a copy that bypasses the proper path.

  Set `requested_tool` to that tool, which must not be a core tool. Set `golden_tool` to the core tool that should do
  the job instead.

## The hidden intent

`intent` says what the user meant. Use only these values, and use null for anything the user would not know or has
not decided:
- **system:** monitoring, kubernetes, release pipeline, cloud, incident management, chat, database, feature flags,
  service catalog;
- **resource:** incident, change request, chat message, chat channel, service release, deployment record,
  kubernetes deployment, kubernetes pod, pod logs, kubernetes events, application logs, trace, metric, latency,
  error rate, alert, dashboard, service health, commit, code diff, connection pool, database query, database session,
  database cluster, cloud resource, cloud instance, container task, cloud logs, provider status, feature flag,
  flag change, service record, service dependencies;
- **action:** read, search, restart, scale, roll back, change, create, update, comment, close, post, terminate,
  fail over, cancel;
- **environment:** production, staging, development.

Fill in every key the user's meaning determines. For ambiguous cases, the intent must single out the golden tool.

## Writing the requests

- **Voice.** Write the way on-call engineers write: short, informal, sometimes with typos or shell jargon, sometimes
  long and chatty. Vary phrasing; do not reuse sentence templates.
- **Names.**
  - Refer to things the way people do: shortened or partial names, descriptions instead of identifiers, loose names
    for flags and channels. Exact identifiers from the inventory should appear in well under half of the cases.
  - At least 15 cases should name something that does not exist in the inventory: a plausible pod, instance, flag,
    channel or incident that is not listed.
- **Spread.** Every core tool must be the golden tool at least once. Cover production, staging and development.
- **Argument labels.** Only label arguments the request pins down.
- **Validation.** All tests in the two validation files must pass.

When you are done, report the counts by kind and category, the number of cases per golden tool, and the SHA-256 of the
file (`shasum -a 256 benchmark/prompts/holdout3_cases.yaml`). Do not describe or quote individual cases in your report.
