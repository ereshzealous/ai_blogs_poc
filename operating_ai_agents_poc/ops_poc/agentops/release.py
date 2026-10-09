"""The behavioural release: every artifact that can change what the agent does, versioned as one unit.

A release manifest is the merged release configuration (config/releases.toml: the base, then a candidate's changes)
plus the content hash of the agent's code. Its id is a hash of the canonical manifest: computed, never assigned, so
two releases that differ in one tool description have different ids, and two candidates with identical artifacts share
one. The image digest is a hash of the code only, so it cannot see a prompt, a routing table or a policy change.

The registry is the control plane's record of which release may receive traffic (T4: define centrally, enforce where
agents run). A release that has not passed the gate cannot be given traffic.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .common import POC, canonical, cfg, sha256_file, sha256_text

ARTIFACTS = ["agent_code", "workflow", "prompt", "model", "routing", "tools", "retrieval", "knowledge", "memory_policy",
             "authz_policy", "approval_policy", "ops", "evals"]


def merge(base: dict, change: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in change.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("overrides",) else copy.deepcopy(v)
    return out


def _code_digest() -> str:
    """The image: every runtime module of the package. Identical for every release built from this source tree."""
    files = sorted((POC / "agentops").glob("*.py"))
    return "img-" + sha256_text(canonical({p.name: sha256_file(p) for p in files}))[:12]


@dataclass
class Release:
    name: str
    config: dict
    manifest: dict = field(init=False)
    release_id: str = field(init=False)
    image_digest: str = field(init=False)

    def __post_init__(self) -> None:
        c = self.config
        code = dict(c["agent_code"])
        code["sha256"] = sha256_file(POC / code["module"])
        self.image_digest = _code_digest()
        self.manifest = {"agent_code": code, **{k: c[k] for k in ARTIFACTS if k != "agent_code"},
                         "image": {**c["image"], "digest": self.image_digest}}
        self.release_id = "rel-" + sha256_text(canonical(self.manifest))[:12]

    # convenience accessors used by the runtime -------------------------------------------------------------------
    def tool_description(self, tool: str) -> str:
        return self.config["tools"][tool]["description"]

    @property
    def system_tokens(self) -> int:
        return self.config["prompt"]["system_tokens"]

    @property
    def retrieval(self) -> dict:
        return self.config["retrieval"]

    @property
    def routing_overrides(self) -> dict:
        return self.config["routing"].get("overrides", {})

    @property
    def approval_above(self) -> int:
        return self.config["approval_policy"]["refund_approval_above_eur"]

    @property
    def delegated_limit(self) -> int:
        return self.config["authz_policy"]["delegated_refund_limit_eur"]

    @property
    def envelope_enforced(self) -> bool:
        return self.config["ops"]["envelope_enforced"]

    def document(self) -> dict:
        return {"name": self.name, "release_id": self.release_id, "image_digest": self.image_digest, "manifest": self.manifest}


def load(name: str = "R41") -> Release:
    r = cfg("releases")
    base = {k: v for k, v in r["base"].items() if k != "name"}
    if name == r["base"]["name"]:
        return Release(name, base)
    return Release(name, merge(base, r["candidates"][name]))


def flatten(d: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in d.items():
        p = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict) and v:
            out.update(flatten(v, p))
        else:
            out[p] = v
    return out


def diff(a: Release, b: Release) -> list[str]:
    """The manifest paths whose value differs between two releases, sorted."""
    fa, fb = flatten(a.manifest), flatten(b.manifest)
    return sorted(k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k))


def artifacts_changed(a: Release, b: Release) -> list[str]:
    """Which behavioural artifacts (top-level, tools per tool) changed."""
    out = set()
    tools = sorted(set(a.manifest["tools"]) | set(b.manifest["tools"]), key=len, reverse=True)
    for p in diff(a, b):
        if p.startswith("tools."):
            out.add(next((f"tools.{t}" for t in tools if p.startswith(f"tools.{t}.") or p == f"tools.{t}"), p))
        else:
            out.add(p.split(".")[0])
    return sorted(out)


class Registry:
    """Which release serves traffic. Statuses: PRODUCTION, CANDIDATE, GATE_PASSED, BLOCKED, CANARY, PROMOTED,
    ROLLED_BACK. Every change is appended to the log (the decision record a release review reads)."""

    def __init__(self, production: Release):
        self.releases = {production.release_id: production}
        self.status = {production.release_id: "PRODUCTION"}
        self.production = production.release_id
        self.weights = {production.release_id: 100}
        self.log: list[dict] = [{"event": "production", "release": production.name, "release_id": production.release_id}]

    def submit(self, rel: Release) -> None:
        self.releases[rel.release_id] = rel
        self.status.setdefault(rel.release_id, "CANDIDATE")
        self.log.append({"event": "submitted", "release": rel.name, "release_id": rel.release_id})

    def gate(self, rel: Release, passed: bool, reasons: list[str]) -> None:
        self.status[rel.release_id] = "GATE_PASSED" if passed else "BLOCKED"
        self.log.append({"event": "gate", "release": rel.name, "release_id": rel.release_id, "passed": passed, "reasons": reasons})

    def set_weight(self, rel: Release, pct: int, reason: str) -> bool:
        """Give a candidate a share of traffic. Refused unless the candidate passed the gate (or is already in canary)."""
        st = self.status.get(rel.release_id)
        if pct > 0 and st not in ("GATE_PASSED", "CANARY"):
            self.log.append({"event": "refused", "release": rel.name, "release_id": rel.release_id, "weight": pct, "status": st})
            return False
        self.weights[rel.release_id] = pct
        self.weights[self.production] = 100 - pct
        self.status[rel.release_id] = "CANARY" if pct > 0 else self.status[rel.release_id]
        self.log.append({"event": "weight", "release": rel.name, "release_id": rel.release_id, "weight": pct, "reason": reason})
        return True

    def promote(self, rel: Release) -> None:
        old = self.production
        self.status[old] = "SUPERSEDED"
        self.production = rel.release_id
        self.status[rel.release_id] = "PRODUCTION"
        self.weights = {rel.release_id: 100}
        self.log.append({"event": "promoted", "release": rel.name, "release_id": rel.release_id, "replaces": old})

    def rollback(self, rel: Release, reason: str) -> None:
        self.weights = {self.production: 100}
        self.status[rel.release_id] = "ROLLED_BACK"
        self.log.append({"event": "rollback", "release": rel.name, "release_id": rel.release_id, "reason": reason,
                         "restored": self.production, "restored_manifest": "every artifact of the production release, by id"})
