"""Which agents exist, what each is for, which route and which read capabilities it gets.  Selection is orchestration's job."""

from __future__ import annotations

from layered_platform.runtime.agent_loop import AgentSpec

DIAGNOSTICIAN = AgentSpec(
    name="diagnostician",
    route="reasoning",
    max_turns=8,
    instructions=(
        "You are the diagnosis agent for a production incident.  Use the read-only tools to look at the affected service's "
        "releases, metrics (latency_p95_ms, error_rate_pct, db_pool_wait_ms, cpu_pct) and logs.  Check that dependencies are "
        "healthy before blaming them.  Decide the root cause and the release that introduced it.  You cannot change anything."
    ),
)
DIAGNOSTICIAN_TOOLS = ["deploy.history", "telemetry.metrics", "telemetry.logs"]

REMEDIATOR = AgentSpec(
    name="remediator",
    route="structured",
    max_turns=1,
    instructions=(
        "You propose one remediation for a diagnosed production incident: the smallest safe action the runbook allows.  "
        "You do not execute it and you do not decide whether it is authorized; the platform does both."
    ),
)
