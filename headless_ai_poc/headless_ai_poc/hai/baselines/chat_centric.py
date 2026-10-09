"""Version A · chat-centric AI.  The chat handler IS the agent: it holds a credential for every system, calls them
directly, and its only entry point is a chat message.  Written the way a first assistant usually is."""

from __future__ import annotations

from typing import Any

from hai.world import World

SYSTEM_CREDENTIALS = ["monitoring", "logs", "traces", "deploy", "itsm", "chat"]   # all held by this one process


class ChatAssistant:
    entry_points = {"chat"}

    def __init__(self, world: World):
        self.world = world
        self.credentials = list(SYSTEM_CREDENTIALS)
        self.log: list[dict[str, Any]] = []

    def handle_message(self, user: str, text: str) -> dict[str, Any]:
        svc = "payment-service" if "payment" in text.lower() else "unknown"
        env = "production"
        h = self.world.service_health(svc, env)
        logs = self.world.logs(svc, env)
        deps = self.world.deployments(svc, env)
        self.log.append({"who": user, "did": "investigate", "via": "chat"})
        return {"answer": f"{svc} error rate {h['error_rate'] * 100:.0f}%; latest release {deps[0]['version']}; "
                          f"{sum('TokenVault' in l['line'] for l in logs)} token-vault errors", "acted_as": user}

    def handle_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        """There is no event entry point: the best it can do is page a human and wait for them to open the chat."""
        return {"handled": False, "next": "page on-call; an engineer must open the chat and ask"}
