"""Native payloads, one per head, exactly as each consumer would send them.  Fixtures for the demo, tests and
experiments; nothing here is shared with the runtime."""

from __future__ import annotations

from typing import Any

from hai.world import T0


def monitor_alert(event_id: str = "dd-evt-88121", value: float = 0.14) -> dict[str, Any]:
    return {"id": event_id, "source": "datadog", "monitor_id": "mon-payments-5xx", "alert_type": "error",
            "title": "[P2] payment-service error rate above 1%", "metric": "error_rate", "value": value,
            "tags": ["service:payment-service", "env:production", "team:payments-platform"], "date": T0}


def chat_message(event_id: str = "slk-Ev0921", user_token: str = "tok-slack-maya") -> tuple[str, dict[str, Any]]:
    return user_token, {"event_id": event_id, "text": "Why is PaymentService failing in production?", "channel": "#payments",
                        "ts": "1790690700.000100", "workspace": "slack"}


def web_request(request_id: str = "web-7f31", session_user: str = "sre.maya") -> dict[str, Any]:
    return {"request_id": request_id, "service": "payment-service", "environment": "production", "session_user": session_user}


def api_request(request_id: str = "api-req-5521") -> dict[str, Any]:
    return {"request_id": request_id, "service": "payment-service", "environment": "production",
            "question": "What is the leading hypothesis for the payment-service degradation?"}


def workflow_step(run_id: str = "wf-run-3304") -> dict[str, Any]:
    return {"workflow_run_id": run_id, "step": "triage", "service": "payment-service", "environment": "production",
            "callback": "https://workflow.example.internal/callbacks/wf-run-3304"}


def scheduler_tick(tick: str = "2026-09-29T14:05Z") -> dict[str, Any]:
    return {"schedule": "health-sweep-5m", "tick": tick, "service": "payment-service", "environment": "production"}


def ci_check(pipeline_id: str = "ci-pipe-7788") -> dict[str, Any]:
    return {"pipeline_id": pipeline_id, "service": "payment-service", "environment": "production", "candidate": "v4.18.1"}


def agent_task(task_id: str = "a2a-task-19") -> dict[str, Any]:
    return {"task_id": task_id, "from_agent": "agent.release-guard", "skill": "release_check",
            "input": {"service": "payment-service", "environment": "production", "candidate": "v4.18.1"}}


# heads and the credential each presents
HEADS = {
    "event": ("tok-monitoring", monitor_alert),
    "chat": ("tok-slack-maya", lambda: chat_message()[1]),
    "web": ("tok-web", web_request),
    "api": ("tok-api-client", api_request),
    "workflow": ("tok-workflow", workflow_step),
    "scheduler": ("tok-scheduler", scheduler_tick),
    "cicd": ("tok-ci", ci_check),
    "agent": ("tok-release-guard", agent_task),
}
