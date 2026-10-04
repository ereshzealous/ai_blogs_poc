"""Build the nested 50 / 100 / 500-tool estates.

For each estate this writes, under ``poc/data/estates/estate-<N>/``:

* ``servers/<server>.json`` — exactly what each MCP server publishes (+ handler ids);
* ``registry.yaml``         — the platform-owned governance registry for that estate;
* ``manifest.json``         — counts by kind, per-server tool lists, hashes.

Estates are nested (50 ⊂ 100 ⊂ 500): core commerce servers are present in all of
them; generated servers are appended in a fixed order.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from ..util import DATA_DIR, sha256_file, sha256_obj, write_json
from .core import AGENTS, CORE_CAPABILITIES, CORE_SERVERS, ROLES
from .generated import generated_servers

ESTATE_SIZES = (50, 100, 500)
REGISTRY_VERSION = "2026-09-28.1"


def estate_servers(size: int) -> list[dict[str, Any]]:
    servers = [dict(s) for s in CORE_SERVERS]
    n = sum(len(s["tools"]) for s in servers)
    for g in generated_servers():
        if n >= size:
            break
        servers.append(g)
        n += len(g["tools"])
    if n != size:
        raise ValueError(f"estate {size}: got {n} tools; generated server sizes must land on estate boundaries")
    return servers


def _generated_gov(server: dict[str, Any], tool: dict[str, Any]) -> dict[str, Any]:
    base = server["server"].replace("_legacy", "").replace("_staging", "")
    write = tool["handler"] == "generic.write"
    gov = {
        "capability": f"{base}.{tool['name']}",
        "side_effect": "write" if write else "none",
        "risk": "medium" if write else "low",
        "required_scopes": [f"{base}:{'write' if write else 'read'}"],
        "approval": {"when": "never"},
        "lifecycle": server.get("lifecycle", "active"),
        "replaced_by": f"{server['replaced_by_server']}.{tool['name']}" if server.get("replaced_by_server") else None,
        "binding_profile": None,
    }
    return gov


def build_registry(servers: list[dict[str, Any]]) -> dict[str, Any]:
    implementations: dict[str, Any] = {}
    capabilities: dict[str, Any] = {k: dict(v) for k, v in CORE_CAPABILITIES.items()}
    for s in servers:
        if not s.get("registered", True):
            continue  # shadow servers are, by definition, absent from the registry
        for tl in s["tools"]:
            name = f"{s['server']}.{tl['name']}"
            g = tl.get("gov") or _generated_gov(s, tl)
            implementations[name] = {
                "capability": g["capability"],
                "owner": s["owner"],
                "lifecycle": g["lifecycle"],
                "replaced_by": g["replaced_by"],
                "environment": s["environment"],
                "region": s.get("region", "global"),
                "side_effect": g["side_effect"],
                "risk": g["risk"],
                "required_scopes": g["required_scopes"],
                "approval": g["approval"],
                "binding_profile": g["binding_profile"],
            }
            if "gov" not in tl and s["kind"] == "generated":
                capabilities[g["capability"]] = {
                    "description": tl["description"],
                    "owner": s["owner"],
                    "authoritative": {"global": name},
                    "entity": None,
                }
    return {
        "version": REGISTRY_VERSION,
        "notes": {
            "owner": "AI platform team (simulated)",
            "mutation": "changes via reviewed commit only; hash pinned in the frozen run manifest",
            "source_of_truth_for": "capability, authority, lifecycle, environment, region, side-effect, risk, scopes, approval",
            "not_source_of_truth_for": "tool input schemas (validated against the server-declared inputSchema)",
        },
        "capabilities": dict(sorted(capabilities.items())),
        "implementations": dict(sorted(implementations.items())),
        "roles": ROLES,
        "agents": AGENTS,
    }


PARAM_DESC = {
    "reason": "Short reason, recorded on the record",
    "address": "Full postal address",
    "email": "Email address",
    "customer_email": "Customer's email address",
    "sku": "Product SKU exactly as it appears on the order",
    "note": "Note text",
    "message": "Message text",
    "comment": "Comment text",
    "team": "Team to route to",
    "tracking_number": "Carrier tracking number",
    "refund_id": "Refund id (format RF-<digits>)",
    "campaign": "Campaign id",
    "customer_ids": "Customer ids to include",
    "limit": "Maximum rows to return (default 50)",
    "query": "Keyword or phrase to search for",
    "name": "Display name",
    "details": "Additional structured fields",
    "fields": "Fields to change, as a JSON object",
    "amount": "Amount in the account currency",
    "points": "Number of points (negative to remove)",
    "date": "Date, YYYY-MM-DD",
    "month": "Month, YYYY-MM",
}


def _describe_params(schema: dict[str, Any]) -> dict[str, Any]:
    """Every parameter carries a description, as in realistic MCP tool definitions (affects context weight)."""
    props = {}
    for k, v in (schema.get("properties") or {}).items():
        if "description" not in v:
            v = {**v, "description": PARAM_DESC.get(k) or (f"Identifier of the {k[:-3].replace('_', ' ')}" if k.endswith("_id") else k.replace("_", " ").capitalize())}
        props[k] = v
    return {**schema, "properties": props}


def _server_file(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "server": s["server"],
        "environment": s["environment"],
        "region": s.get("region", "global"),
        "version": "1.0.0",
        "tools": [
            {**{k: tl[k] for k in ("name", "description", "annotations", "handler")}, "inputSchema": _describe_params(tl["inputSchema"])}
            for tl in s["tools"]
        ],
    }


KIND_LABELS = {
    "core": "authoritative core",
    "regional": "regional implementation",
    "env_copy": "environment copy (staging)",
    "legacy": "legacy / retired",
    "vendor": "vendor duplicate",
    "shadow": "shadow / unregistered",
    "generated": "other business units",
    "generated_legacy": "other business units — retired copy",
    "generated_env_copy": "other business units — staging copy",
}


def build(out_root: Path = DATA_DIR / "estates") -> dict[int, Path]:
    out: dict[int, Path] = {}
    for size in ESTATE_SIZES:
        d = out_root / f"estate-{size}"
        (d / "servers").mkdir(parents=True, exist_ok=True)
        for old in (d / "servers").glob("*.json"):
            old.unlink()
        servers = estate_servers(size)
        for s in servers:
            write_json(d / "servers" / f"{s['server']}.json", _server_file(s))
        reg = build_registry(servers)
        (d / "registry.yaml").write_text(yaml.safe_dump(reg, sort_keys=False, width=140))
        by_kind: dict[str, dict[str, int]] = {}
        for s in servers:
            k = by_kind.setdefault(s["kind"], {"servers": 0, "tools": 0})
            k["servers"] += 1
            k["tools"] += len(s["tools"])
        manifest = {
            "estate_size": size,
            "server_count": len(servers),
            "tool_count": sum(len(s["tools"]) for s in servers),
            "registered_tool_count": len(reg["implementations"]),
            "unregistered_tool_count": sum(len(s["tools"]) for s in servers if not s.get("registered", True)),
            "by_kind": {k: {**v, "label": KIND_LABELS[k]} for k, v in sorted(by_kind.items())},
            "servers": [
                {
                    "server": s["server"],
                    "kind": s["kind"],
                    "environment": s["environment"],
                    "region": s.get("region", "global"),
                    "registered": s.get("registered", True),
                    "tools": [tl["name"] for tl in s["tools"]],
                }
                for s in servers
            ],
            "registry_sha256": sha256_file(d / "registry.yaml"),
            "published_catalog_sha256": sha256_obj([_server_file(s) for s in servers]),
        }
        write_json(d / "manifest.json", manifest)
        out[size] = d
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.parse_args(argv)
    for size, d in build().items():
        print(size, d)


if __name__ == "__main__":
    main()
