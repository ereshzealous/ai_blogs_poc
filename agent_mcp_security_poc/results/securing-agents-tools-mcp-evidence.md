# Securing Agents, Tools & MCP — Evidence

*Production AI Engineering · T6 · generated from run `2026-10-07-recorded`*

Every number below is substituted from the published run's facts (`redteam_poc/evidence/runs/2026-10-07-recorded/facts.json`)
and reproduced byte for byte by `redteam verify`. Nothing is typed by hand.

## The headline

| Configuration | model manipulated | system compromised |
|---|---|---|
| A — vulnerable toy | 19 / 19 | 19 / 19 |
| B — classifier + unrestricted path | 19 / 19 | 13 / 19 |
| C — deterministic enforcement | 19 / 19 | 0 / 19 |

3 control scenarios (legitimate work) completed in every arm. 19 attacks across 8
classes.

## Claims traced to evidence

| Claim | Status | Rests on |
|---|---|---|
| A manipulated model does not compromise a hardened system | SUPPORTED | GA-C01: arm C compromised = 0, manipulated = 19 |
| The vulnerable toy is really vulnerable | SUPPORTED (control) | GA-C02: arm A compromised = 19 |
| A classifier is defense in depth, not the boundary | SUPPORTED | GA-C03: arm B compromised = 13 |
| Least privilege is the backbone | SUPPORTED | ablation: registry alone contains 15/19 |
| Argument binding is the sole line against redirection | SUPPORTED | ablation: removing it re-opens 4 (PI-4, RAG-1, BYPASS-2, MEM-1) |
| Enforcement does not block legitimate work | SUPPORTED | CTRL-C01: 3 controls contained in arm C |
| Abuse within granted authority is not contained (measured) | LIMITATION OBSERVED | LIMIT-C01: `within_residual` C = 1/1 (executes in the hardened arm), yet `within_compromised` C = 0/1 (not a system compromise) |

## The ablation (each control in isolation, arm C)

| Control | Attacks it alone contains | Attacks it is the sole line for |
|---|---|---|
| registry (least privilege + MCP pinning) | 15 | 0 (overlap elsewhere) |
| policy (authorization) | 5 | 0 |
| egress (data boundary) | 5 | 0 |
| argument binding | 4 | 4 |
| identity / delegation | 2 | 0 |

## How to reproduce

```bash
cd securing_tools_mcp && make setup
make scenarios     # the corpus across arms A/B/C
make ablation      # each control's contribution
make proof         # record the run under pae-proof/v1
make verify        # EXACT replay + integrity + checks -> VERIFIED
make test          # the import contract, the invariants, the end-to-end assertions
```

No model, no API key, no network: the agent follows a scripted worst-case plan, the clock is fixed and every
enterprise system is a local mock. The MCP spec revision referenced throughout is 2026-07-28.
