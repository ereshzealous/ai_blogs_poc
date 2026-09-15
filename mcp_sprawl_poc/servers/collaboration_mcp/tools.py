"""collaboration-mcp: team chat channels and messages."""

from servers.common.meta import registry_record
from servers.common.toolspec import ToolSpec, schema

S = "collaboration"
OWNER = "workplace-tools"
CHANNEL = {"type": "string", "description": "Channel name including #, e.g. #inc-4917-checkout-latency."}


def _meta(capability, resource, ops, risk, scopes):
    return registry_record(domain="collaboration", capability=capability, resource_type=resource, operations=ops, risk=risk,
                           owner=OWNER, scopes=scopes, authoritative_for=[resource])


TOOLS = [
    ToolSpec(
        S, "search_messages",
        "Search chat messages across channels by text, optionally within one channel. Returns author, channel and time.",
        schema({"query": {"type": "string", "minLength": 1}, "channel": CHANNEL, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, ["query"]),
        title="Search messages", read_only_hint=True, open_world_hint=False, handler="collaboration:search_messages",
        collision_group="chat-read", registry=_meta("chat-read", "chat-message", ["search"], "READ_ONLY", ["chat.read"]),
    ),
    ToolSpec(
        S, "get_channel",
        "Get a chat channel's topic, creation time and most recent messages.",
        schema({"channel": CHANNEL}, ["channel"]),
        title="Get channel", read_only_hint=True, open_world_hint=False, handler="collaboration:get_channel",
        collision_group="chat-read", registry=_meta("chat-read", "chat-channel", ["get"], "READ_ONLY", ["chat.read"]),
    ),
    ToolSpec(
        S, "post_message",
        "Post a message to a chat channel as the calling agent.",
        schema({"channel": CHANNEL, "text": {"type": "string", "minLength": 1}}, ["channel", "text"]),
        title="Post message", read_only_hint=False, destructive_hint=False, open_world_hint=True, handler="collaboration:post_message",
        collision_group="chat-write", registry=_meta("chat-write", "chat-message", ["post"], "LOW_RISK_WRITE", ["chat.write"]),
    ),
    ToolSpec(
        S, "create_incident_channel",
        "Create a dedicated incident chat channel named after the incident and invite the assignment group.",
        schema({"incident_id": {"type": "string", "pattern": "^INC-[0-9]{4,6}$"}, "topic": {"type": "string"}}, ["incident_id"]),
        title="Create incident channel", read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
        handler="collaboration:create_incident_channel", collision_group="chat-write",
        registry=_meta("chat-write", "chat-channel", ["create"], "LOW_RISK_WRITE", ["chat.write"]),
    ),
]
