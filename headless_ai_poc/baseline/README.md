# Channel-coupled baseline

A reasonable way teams build their first multi-channel assistant: each channel team ships a complete assistant.
Nothing here is careless. Each copy has approval for production rollbacks, a role check and audit logging. The
problem is structural: every copy owns its own prompt, model call, tool wiring, workflow, memory, policy and
telemetry, so every cross-cutting change must be made correctly in every copy.

| file | channel | owns |
|---|---|---|
| `channel_coupled/web_assistant.py` | web console | prompt, model, tools, workflow, memory, policy, approval UI, telemetry |
| `channel_coupled/slack_assistant.py` | Slack bot | the same concerns, Slack-flavoured |
| `channel_coupled/api_assistant.py` | REST API | the same concerns, API-flavoured |

The model and tool calls are written against Ollama and the Part 2 MCP tools but are not run by the experiments.
Experiment H3 measures change scope on this code with real patches, and exercises each copy's governance functions
(`approval_role`, `may_approve`) directly. That keeps the comparison about structure, not about model quality.
