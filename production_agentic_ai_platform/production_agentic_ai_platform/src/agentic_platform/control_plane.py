"""AI control plane: the versioned, signed definition of what may exist and run.

The control plane defines agents, models, tools, policies, budgets, guardrails, identity and data policy.  It distributes
them as one bundle (a directory of YAML plus a manifest), signs the bundle digest, and records every change.  The runtime
loads the bundle at each decision and refuses a bundle whose signature does not verify.  It is never in the per-token
reasoning loop.

In the POC, "distribution" is the runtime re-reading the bundle directory before every enforcement decision (staleness
zero).  In production it is a push/pull protocol with a staleness bound, last-known-good and fail-closed defaults (T4).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agentic_platform.canonical import canonical_json, sha256

FILES = {"identity": "identity/principals.yaml", "agents": "agents", "models": "models/models.yaml", "tools": "tools/registry.yaml",
         "policies": "policies/production.yaml", "budgets": "budgets", "guardrails": "guardrails/guardrails.yaml", "data": "data/data-policy.yaml"}


class BundleError(Exception):
    pass


@dataclass
class Bundle:
    root: Path
    manifest: dict[str, Any]
    doc: dict[str, Any]
    digest: str

    @property
    def version(self) -> str:
        return f"{self.manifest['bundle']}@{self.manifest['version']}"

    def agent(self, agent_id: str) -> dict[str, Any]:
        for a in self.doc["agents"].values():
            if a["agent"]["id"] == agent_id:
                return a["agent"]
        raise BundleError(f"agent {agent_id} is not registered")

    def budget(self, name: str) -> dict[str, Any]:
        return self.doc["budgets"][name]["limits"]

    @property
    def tools(self) -> dict[str, Any]:
        return self.doc["tools"]["capabilities"]

    @property
    def policy(self) -> dict[str, Any]:
        return self.doc["policies"]

    @property
    def policy_version(self) -> str:
        return f"{self.policy['policy']}@{self.policy['version']}"


def _load_dir(root: Path) -> tuple[dict, dict]:
    manifest = yaml.safe_load((root / "control-plane.yaml").read_text())
    doc: dict[str, Any] = {}
    for k, rel in FILES.items():
        p = root / rel
        if p.is_dir():
            doc[k] = {f.stem: yaml.safe_load(f.read_text()) for f in sorted(p.glob("*.yaml"))}
        else:
            doc[k] = yaml.safe_load(p.read_text())
    return manifest, doc


def bundle_digest(manifest: dict, doc: dict) -> str:
    m = {k: v for k, v in manifest.items() if k != "signature"}
    return sha256(canonical_json({"manifest": m, "doc": doc}))


def sign(key: bytes, digest: str) -> str:
    return hmac.new(key, digest.encode(), hashlib.sha256).hexdigest()


def load(root: str | Path, key: bytes) -> Bundle:
    root = Path(root)
    manifest, doc = _load_dir(root)
    d = bundle_digest(manifest, doc)
    sig = (root / "SIGNATURE").read_text().strip() if (root / "SIGNATURE").exists() else ""
    if not hmac.compare_digest(sig, sign(key, d)):
        raise BundleError(f"BUNDLE_SIGNATURE_INVALID: bundle {manifest.get('bundle')}@{manifest.get('version')} digest {d[:12]}…")
    return Bundle(root, manifest, doc, d)


def publish(root: str | Path, key: bytes) -> Bundle:
    """Sign the bundle as it is on disk (the release step of the control plane)."""
    root = Path(root)
    manifest, doc = _load_dir(root)
    d = bundle_digest(manifest, doc)
    (root / "SIGNATURE").write_text(sign(key, d) + "\n")
    return Bundle(root, manifest, doc, d)


def apply_change(root: str | Path, key: bytes, *, path: str, value: Any, actor: str, reason: str) -> dict[str, Any]:
    """One central change: set `path` (e.g. tools.capabilities.release.execute_rollback.enabled) in the bundle, bump the
    version, re-sign, and append a change record.  No agent code, prompt or deployment is involved."""
    root = Path(root)
    before = load(root, key)
    section, *rest = path.split(".")
    rel = FILES[section]
    f = root / rel
    data = yaml.safe_load(f.read_text())
    node = data
    keys = _split_path(rest, data)
    for k in keys[:-1]:
        node = node[k]
    old = node.get(keys[-1])
    node[keys[-1]] = value
    f.write_text(yaml.safe_dump(data, sort_keys=False, width=200))
    manifest = yaml.safe_load((root / "control-plane.yaml").read_text())
    manifest["version"] = int(manifest["version"]) + 1
    (root / "control-plane.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
    after = publish(root, key)
    rec = {"at": time.time(), "actor": actor, "reason": reason, "path": path, "old": old, "new": value,
           "from_version": before.version, "to_version": after.version, "from_digest": before.digest, "to_digest": after.digest,
           "files_changed": [rel]}
    with (root / "CHANGELOG.jsonl").open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def _split_path(rest: list[str], data: dict) -> list[str]:
    """Capability names contain dots (release.execute_rollback); rebuild keys greedily against the document."""
    keys, node, i = [], data, 0
    while i < len(rest):
        for j in range(len(rest), i, -1):
            cand = ".".join(rest[i:j])
            if isinstance(node, dict) and cand in node:
                keys.append(cand)
                node = node[cand]
                i = j
                break
        else:
            keys.append(rest[i])
            i += 1
    return keys
