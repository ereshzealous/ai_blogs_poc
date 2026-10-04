"""The control plane: define, version, sign and distribute desired state. It never executes an agent.

    cp = ControlPlane(state_dir)
    cp.bootstrap(tick)                                  v1 from config/desired-state.yaml
    cp.publish_change("restart-requires-approval", t)   v2 = v1 + one reviewed patch from config/changes.yaml
    cp.rollout(version, percent) / cp.promote() / cp.rollback()
    cp.desired(agent) / cp.drift(observed)              desired vs observed state

Storage (a directory standing in for a replicated configuration service):
    controlplane/bundles/<v>.json   immutable bundle: version, parent, desired_state, the change that produced it
    controlplane/bundles/<v>.sig    signature over the bundle's sha256
    controlplane/current.json       the distribution pointer: stable version, optional canary {version, percent}
    controlplane/changelog.jsonl    hash-chained record of every accepted AND rejected change
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from acp.common import CONFIG, append_chained, canon, digest, get_path, read_json, set_path, sha256, sign, write_json
from acp.controlplane.admin import authorize_change
from acp.controlplane.validate import validate

AGENT_STATUSES = ("active", "paused", "quarantined", "suspended", "disabled")


class ChangeRejected(Exception):
    pass


def load_yaml(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text())


class ControlPlane:
    def __init__(self, state: Path):
        self.root = Path(state) / "controlplane"
        self.bundles = self.root / "bundles"
        self.admins = load_yaml("admins.yaml")
        self.changes = load_yaml("changes.yaml")

    # ---- reading ---------------------------------------------------------------------------------------------------------
    def pointer(self) -> dict:
        return read_json(self.root / "current.json", {"stable": None, "canary": None})

    def bundle(self, version: str) -> dict:
        return read_json(self.bundles / f"{version}.json")

    def versions(self) -> list[str]:
        return sorted((p.stem for p in self.bundles.glob("v*.json")), key=lambda v: int(v[1:]))

    def latest(self) -> str:
        return self.versions()[-1]

    def state(self, version: str | None = None) -> dict:
        return copy.deepcopy(self.bundle(version or self.pointer()["stable"])["desired_state"])

    def desired(self, agent: str) -> dict:
        """What governance says, for one agent: the version a runtime should be using and the agent's entry."""
        p = self.pointer()
        return {"agent": agent, "stable": p["stable"], "canary": p["canary"], "status": get_path(self.state(), f"agents.{agent}.status")}

    # ---- writing ---------------------------------------------------------------------------------------------------------
    def _write_bundle(self, desired_state: dict, parent: str | None, change: dict, tick: int) -> str:
        problems = validate(desired_state)
        if problems:
            raise ChangeRejected("; ".join(problems))
        version = f"v{len(self.versions()) + 1}"
        body = {"version": version, "parent": parent, "published_tick": tick, "change": change, "desired_state": desired_state}
        write_json(self.bundles / f"{version}.json", body)
        (self.bundles / f"{version}.sig").write_text(sign(sha256(canon(body))) + "\n")
        return version

    def _log(self, tick: int, **record) -> dict:
        return append_chained(self.root / "changelog.jsonl", {"tick": tick, **record})

    def bootstrap(self, tick: int = 0) -> str:
        seed = load_yaml("desired-state.yaml")
        v = self._write_bundle(seed, None, {"id": "seed", "author": "platform.admin", "reason": "seed desired state"}, tick)
        write_json(self.root / "current.json", {"stable": v, "canary": None})
        self._log(tick, event="published", version=v, change="seed", author="platform.admin", bundle_sha256=digest(self.bundle(v)))
        return v

    def publish(
        self,
        change_id: str,
        sets: dict,
        author: str,
        reason: str,
        tick: int,
        second_approver: str | None = None,
        emergency: bool = False,
        activate: bool = True,
    ) -> str:
        """Authorize, validate, version, sign and (by default) activate one change. Rejections are logged, not silent."""
        parent = self.pointer()["stable"]
        current = self.state(parent)
        new = current
        for path, value in sets.items():
            new = set_path(new, path, value)
        problems = validate(new)  # the CI gate runs first: an invalid state never reaches review
        if problems:
            self._log(
                tick,
                event="rejected",
                change=change_id,
                author=author,
                second_approver=second_approver,
                reason="invalid desired state: " + "; ".join(problems),
                kind="invalid",
                paths=sorted(sets),
            )
            raise ChangeRejected("; ".join(problems))
        decision = authorize_change(self.admins, current, sets, author, second_approver, emergency)
        if not decision.allowed:
            self._log(
                tick,
                event="rejected",
                change=change_id,
                author=author,
                second_approver=second_approver,
                reason=decision.reason,
                kind=decision.kind,
                paths=sorted(sets),
            )
            raise ChangeRejected(decision.reason)
        change = {
            "id": change_id,
            "author": author,
            "second_approver": second_approver,
            "reason": reason,
            "emergency": emergency,
            "kind": decision.kind,
            "set": sets,
        }
        v = self._write_bundle(new, parent, change, tick)
        if activate:
            write_json(self.root / "current.json", {"stable": v, "canary": None})
        self._log(
            tick,
            event="published",
            version=v,
            parent=parent,
            change=change_id,
            author=author,
            second_approver=second_approver,
            kind=decision.kind,
            emergency=emergency,
            activated=activate,
            paths=sorted(sets),
            bundle_sha256=digest(self.bundle(v)),
        )
        return v

    def publish_change(
        self,
        change_id: str,
        tick: int,
        author: str | None = None,
        second_approver: str | None = "__default__",
        emergency: bool | None = None,
        activate: bool = True,
    ) -> str:
        """Publish a named change from config/changes.yaml (the reviewed policy-as-code change set)."""
        c = self.changes[change_id]
        return self.publish(
            change_id,
            c["set"],
            author or c["author"],
            c["reason"],
            tick,
            second_approver=c.get("second_approver") if second_approver == "__default__" else second_approver,
            emergency=c.get("emergency", False) if emergency is None else emergency,
            activate=activate,
        )

    # ---- rollout ---------------------------------------------------------------------------------------------------------
    def rollout(self, version: str, percent: int, author: str, tick: int) -> None:
        p = self.pointer()
        write_json(self.root / "current.json", {"stable": p["stable"], "canary": {"version": version, "percent": percent}})
        self._log(tick, event="rollout", version=version, percent=percent, stable=p["stable"], author=author)

    def promote(self, author: str, tick: int) -> None:
        p = self.pointer()
        write_json(self.root / "current.json", {"stable": p["canary"]["version"], "canary": None})
        self._log(tick, event="promoted", version=p["canary"]["version"], author=author)

    def rollback(self, author: str, tick: int, to: str | None = None) -> None:
        p = self.pointer()
        target = to or p["stable"]
        write_json(self.root / "current.json", {"stable": target, "canary": None})
        self._log(tick, event="rolled_back", from_canary=(p["canary"] or {}).get("version"), to=target, author=author)

    # ---- desired vs observed ---------------------------------------------------------------------------------------------
    def drift(self, observed: list[dict], audit: list[dict]) -> list[dict]:
        """Compare what each runtime reports (observed) and what it did (audit) with what the control plane says (desired).

        observed: [{instance, agent, config_version}] from runtime status reports.
        audit:    runtime audit events; a mutation executed under a version that was already superseded is drift too.
        """
        p = self.pointer()
        allowed = {p["stable"]} | ({p["canary"]["version"]} if p["canary"] else set())
        out = [
            {"kind": "stale_config", "instance": o["instance"], "agent": o["agent"], "observed": o["config_version"], "desired": sorted(allowed)}
            for o in observed
            if o["config_version"] not in allowed
        ]
        published_at = {v: self.bundle(v)["published_tick"] for v in self.versions()}
        order = self.versions()
        for e in audit:
            if e.get("event") != "action.executed":
                continue
            v = e["config_version"]
            newer = [w for w in order[order.index(v) + 1 :] if published_at[w] <= e["tick"]]
            if newer:
                out.append(
                    {
                        "kind": "executed_under_superseded_config",
                        "instance": e["instance"],
                        "agent": e["agent"],
                        "action": e["action"],
                        "config_version": v,
                        "superseded_by": newer[-1],
                        "tick": e["tick"],
                    }
                )
        return out
