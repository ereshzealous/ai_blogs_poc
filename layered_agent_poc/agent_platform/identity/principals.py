"""Identity and delegation. Every tool call carries who asked (user), who acts (agent) and why (workflow)."""

from __future__ import annotations

from dataclasses import dataclass

from agent_platform.config import principals


class Forbidden(PermissionError):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: str
    display_name: str
    roles: tuple[str, ...]

    def has_role(self, role: str) -> bool:
        return role in self.roles


@dataclass(frozen=True)
class Delegation:
    """The agent acting on behalf of a user inside one workflow."""

    user: Principal
    agent_id: str
    workflow_id: str

    def as_attributes(self) -> dict[str, str]:
        return {"enduser.id": self.user.user_id, "gen_ai.agent.id": self.agent_id, "lap.workflow.id": self.workflow_id}


def resolve_user(user_id: str) -> Principal:
    users = principals()["users"]
    if user_id not in users:
        raise Forbidden(f"unknown user {user_id!r}")
    u = users[user_id]
    return Principal(user_id, u["display_name"], tuple(u["roles"]))


def resolve_chat_user(chat_user_id: str) -> Principal:
    mapping = principals().get("chat_users", {})
    if chat_user_id not in mapping:
        raise Forbidden(f"chat user {chat_user_id!r} is not linked to a platform identity")
    return resolve_user(mapping[chat_user_id])


def agent_id() -> str:
    return principals()["agent"]["id"]


def require_role(principal: Principal, role: str) -> None:
    if not principal.has_role(role):
        raise Forbidden(f"{principal.user_id} lacks role {role!r}")
