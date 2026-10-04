"""The services the runtime talks to, other than the control plane's own store.

Distribution     how a runtime instance receives the pointer and bundles; can be made unreachable, or a lagging
                 replica, per instance (state/network/<instance>.json), to exercise failure behaviour
CredentialBroker mints a short-lived credential for one tool at call time; never hands out the secret itself
ApprovalService  durable pending approvals bound to one exact action; eligible approvers come from the bundle
SpendMeter       shared daily spend per agent (a budget is useless if each runtime instance counts alone)
"""

from __future__ import annotations

from pathlib import Path

from acp.common import canon, digest, read_json, sha256, verify_signature, write_json


class Unreachable(Exception):
    pass


class BadSignature(Exception):
    pass


class Distribution:
    def __init__(self, state: Path, instance: str):
        self.state, self.instance = Path(state), instance
        self.cp = self.state / "controlplane"

    def net(self) -> dict:
        return read_json(self.state / "network" / f"{self.instance}.json", {})

    def pointer(self) -> dict:
        n = self.net()
        if n.get("unreachable"):
            raise Unreachable(f"control plane unreachable from {self.instance}")
        if n.get("serve_pointer"):  # a lagging replica: answers without error, with an old pointer
            return n["serve_pointer"]
        return read_json(self.cp / "current.json")

    def bundle(self, version: str) -> dict:
        if self.net().get("unreachable"):
            raise Unreachable(f"control plane unreachable from {self.instance}")
        body = read_json(self.cp / "bundles" / f"{version}.json")
        sig = (self.cp / "bundles" / f"{version}.sig").read_text().strip()
        tampered = self.net().get("tamper_in_transit")
        if tampered and tampered.get("version") == version:
            body = {**body, "desired_state": {**body["desired_state"], **tampered["overlay"]}}
        if not verify_signature(sha256(canon(body)), sig):
            raise BadSignature(f"bundle {version} failed signature verification")
        return body


class CredentialBroker:
    def __init__(self, state: Path):
        self.path = Path(state) / "broker"

    def available(self) -> bool:
        return read_json(self.path / "status.json", {"available": True})["available"]

    def issue(self, agent: str, tool: str, secret_ref: str, tick: int, ttl: int = 5) -> dict:
        if not self.available():
            raise Unreachable("credential broker unavailable")
        cred = {"agent": agent, "audience": tool, "secret_ref": secret_ref, "issued_tick": tick, "expires_tick": tick + ttl}
        cred["id"] = "cred-" + digest(cred)[:12]
        return cred


class ApprovalService:
    def __init__(self, state: Path):
        self.path = Path(state) / "approvals" / "approvals.json"

    def all(self) -> dict:
        return read_json(self.path, {})

    def get(self, approval_id: str) -> dict | None:
        return self.all().get(approval_id)

    def _save(self, a: dict) -> None:
        allx = self.all()
        allx[a["id"]] = a
        write_json(self.path, allx)

    def request(self, pending: dict, approvers: list[str], expires_tick: int, tick: int) -> dict:
        allx = self.all()
        a = {
            "id": f"approval-{len(allx) + 1:03d}",
            "status": "pending",
            "action_digest": digest(pending["action"]),
            "pending": pending,
            "eligible": approvers,
            "requested_tick": tick,
            "expires_tick": expires_tick,
            "decided_by": None,
            "executed": False,
        }
        self._save(a)
        return a

    def decide(self, approval_id: str, principal: str, approve: bool, tick: int) -> tuple[bool, str]:
        a = self.get(approval_id)
        if a is None:
            return False, "no such approval"
        if a["status"] != "pending":
            return False, f"approval is {a['status']}"
        if tick > a["expires_tick"]:
            a["status"] = "expired"
            self._save(a)
            return False, "approval expired"
        if principal == a["pending"]["agent"] or principal.startswith("spiffe://"):
            return False, "an agent cannot approve its own action"
        if principal not in a["eligible"]:
            return False, f"{principal} is not an eligible approver for {a['pending']['action']['tool']}"
        a["status"], a["decided_by"], a["decided_tick"] = ("approved" if approve else "rejected"), principal, tick
        self._save(a)
        return True, a["status"]

    def mark_executed(self, approval_id: str) -> None:
        a = self.get(approval_id)
        a["executed"] = True
        a["status"] = "executed"
        self._save(a)


class SpendMeter:
    def __init__(self, state: Path):
        self.path = Path(state) / "budget" / "spend.json"

    def today(self, agent: str) -> float:
        return read_json(self.path, {}).get(agent, 0.0)

    def add(self, agent: str, usd: float) -> None:
        s = read_json(self.path, {})
        s[agent] = round(s.get(agent, 0.0) + usd, 4)
        write_json(self.path, s)
