"""Version B · layered, but chat is the only door.  It reuses the same runtime, capability layer and control plane as
the headless version (F2's structure), yet the only entry point is a chat session.  Other triggers must be bridged
into chat by a bot user, which is where the real invoker, the source and the causation link are lost."""

from __future__ import annotations

from typing import Any

from hai.ingress.gateway import HeadlessIngress


class LayeredChatExperience:
    entry_points = {"chat"}

    def __init__(self, ingress: HeadlessIngress):
        self.ingress = ingress

    def handle_message(self, credential: str, message: dict[str, Any]):
        return self.ingress.receive("chat", credential, message)


class AlertToChatBridge:
    """What teams build when chat is the only door: an alert bot that posts a question into the channel."""

    def __init__(self, experience: LayeredChatExperience):
        self.experience = experience

    def forward(self, alert: dict[str, Any], ts: str):
        tags = dict(t.split(":", 1) for t in alert["tags"])
        msg = {"event_id": f"bridge-{alert['id']}", "text": f"Why is {tags['service']} failing in {tags['env']}?",
               "channel": "#payments", "ts": ts, "workspace": "slack"}
        return self.experience.handle_message("tok-slack-alertbot", msg)
