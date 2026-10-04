"""The layered incident platform: six logical layers in one deployable process.

    experience/     channels: CLI, chat renderer            -> talks only to service.py
    orchestration/  the INC workflow, agent selection, HITL -> coordinates, never calls a model or MCP directly
    runtime/        durable step executor, agent loop, retry, checkpoints
    context/        working-context assembly and knowledge retrieval      memory/  remembered facts with provenance
    tools/          capability registry, action gateway, idempotency, the one MCP client
    models/         model gateway, routes, budgets, the one provider adapter
    policy/ telemetry/ evals/ storage/   cross-cutting controls, used by the layers above

A layer here is a package with a contract, not a network service.
"""
