"""Runs inside a patched scratch tree (PYTHONPATH points at it). Prints JSON facts about the patched system."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import tempfile
from pathlib import Path

PROD_ROLLBACK = ("source_control.rollback_release", "production")


def baseline_roles() -> dict[str, str | None]:
    out = {}
    for name in ("web", "slack", "api", "teams"):
        try:
            mod = importlib.import_module(f"baseline.channel_coupled.{name}_assistant")
        except ModuleNotFoundError:
            continue
        out[name] = mod.approval_role(*PROD_ROLLBACK)
    return out


async def headless_roles(channels: list[str]) -> dict[str, dict[str, str | None]]:
    import os

    from experiments.harness import prepare_env

    env = prepare_env(Path(tempfile.mkdtemp(prefix="hai-probe-")), replay_workflows=len(channels))
    os.environ.update(env)
    from headless_ai_platform.runtime import open_gateway

    subjects = {"slack": "U04ALICE", "web": "oidc|alice-92ab", "cli": "alice@company.example", "rest": "api|alice",
                "teams": "29:aad-alice-7f3e"}
    out = {}
    async with open_gateway() as gw:
        for c in channels:
            r = await gw.handle({"capability": "incident.remediation", "operation": "start",
                                 "input": {"incident_id": "INC-4917"},
                                 "actor": {"channel": c, "channel_subject": subjects[c]}}, wait=True)
            out[c] = {"status": r.status.value, "required_role": r.state.approval_required_role,
                      "policy_rule": r.state.policy_rule}
    return out


def teams_http() -> dict[str, object]:
    """Drive the Teams adapter over HTTP, if the patch added it."""
    from fastapi.testclient import TestClient

    from headless_ai_platform import server

    if "teams" not in server.ROUTERS:
        return {"present": False}
    from headless_ai_platform.renderers import teams

    activity = {"type": "message", "id": "act-1", "text": "<at>ops</at> INC-4917", "from": {"aadObjectId": "29:aad-alice-7f3e"},
                "conversation": {"id": "19:incident-room"}}
    with TestClient(server.create_app(["teams"])) as client:
        first = client.post("/teams/messages", json=activity).json()["attachments"][0]["content"]
        gw = client.app.state.gateway
        client.portal.call(gw.drain)
        wf = next(f["value"] for f in first["body"][1]["facts"] if f["title"] == "Workflow")
        later = client.portal.call(gw.handle, {"capability": "incident.remediation", "operation": "get", "workflow_id": wf,
                                               "actor": {"channel": "teams", "channel_subject": "29:aad-alice-7f3e"}})
        card = teams.render(later)["content"]
        submit = client.post("/teams/messages", json={**activity, "id": "act-2", "text": "",
                                                      "value": card["actions"][0]["data"]}).json()
        client.portal.call(gw.drain)
        final = client.portal.call(gw.handle, {"capability": "incident.remediation", "operation": "get", "workflow_id": wf,
                                               "actor": {"channel": "teams", "channel_subject": "29:aad-alice-7f3e"}})
    return {"present": True, "first_card": first["type"], "waiting_actions": [a["title"] for a in card["actions"]],
            "submit_reply": submit["type"], "final_status": final.status.value}


def main() -> None:
    what = sys.argv[1]
    if what == "baseline":
        print(json.dumps(baseline_roles()))
    elif what == "headless":
        channels = sys.argv[2].split(",")
        print(json.dumps({"roles": asyncio.run(headless_roles(channels)), "teams": teams_http() if "teams" in channels else None}))


if __name__ == "__main__":
    main()
