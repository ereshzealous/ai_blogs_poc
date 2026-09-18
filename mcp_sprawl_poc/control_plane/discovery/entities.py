"""Entity lookup for discovery v5: the named things in a request, resolved by rule against the resource inventory.

Nothing here calls a model. Three kinds of match, in this order (a matched span is not matched again):

1. id shapes, known or not: incidents, deployments, releases, cloud instances and tasks, commits, traces, chat
   channels and pod names;
2. names from the inventory: pods, clusters, databases, caches, feature flags, channels, services, with simple aliases
   (a flag key written with spaces, a database without its environment suffix, a service's namespace);
3. a few unambiguous nouns without a name: "pod" (singular), "instance"/"VM", "flag"/"toggle", "channel"/"war room".

Services are context only: nearly every request names one, so they are not evidence for a capability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from control_plane.paths import SCENARIO_FILE

# entity types that a capability can act on (benchmark/catalog_generator/capabilities.py, PARAM_ENTITIES)
EVIDENCE_TYPES = frozenset({"pod", "instance", "task", "database", "cache", "flag", "channel", "incident", "deployment",
                            "release", "commit", "trace"})
TYPE_DOMAIN = {"pod": "runtime", "cluster": "runtime", "instance": "cloud", "task": "cloud", "cache": "cloud",
               "database": "database", "flag": "feature-flags", "channel": "collaboration", "incident": "itsm",
               "deployment": "delivery", "release": "delivery", "commit": "delivery", "trace": "observability"}
GENERIC_TOKENS = frozenset({"checkout", "api", "service", "prod", "production", "v2", "v3", "client"})
FLAG_WORDS = re.compile(r"\b(?:feature flags?|flags?|toggles?|kill switch)\b")

ID_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("incident", re.compile(r"(?<![#\w-])INC-\d{3,6}\b")),
    ("deployment", re.compile(r"(?<![\w-])DEP-\d+\b")),
    ("release", re.compile(r"(?<![\w-])REL-[\w.-]*\w")),
    ("instance", re.compile(r"(?<![\w-])i-[0-9a-f]{8,17}\b")),
    ("task", re.compile(r"(?<![\w-])task-[a-z0-9]+(?:-[a-z0-9]+)*")),
    ("trace", re.compile(r"(?<![\w-])[0-9a-f]{32}(?![\w-])")),
    ("commit", re.compile(r"(?<![\w-])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![\w-])")),
    ("channel", re.compile(r"(?<![\w&])#[a-z0-9][a-z0-9_-]*[a-z0-9]")),
    ("pod", re.compile(r"(?<![\w-])[a-z][a-z0-9]*(?:-[a-z0-9]+)*-[a-z0-9]{8,10}-[a-z0-9]{5}(?![\w-])")),
    ("release", re.compile(r"(?<![\w.-])v\d+\.\d+(?:\.\d+)?(?![\w-])")),
)
TYPE_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pod", re.compile(r"\bpod\b(?!s)")),
    ("instance", re.compile(r"\b(?:instance|vm|virtual machine)\b")),
    ("flag", re.compile(r"\b(?:feature flag|flag|toggle|kill switch)\b")),
    ("channel", re.compile(r"\b(?:channel|war room|chat room)\b")),
)


@dataclass(frozen=True)
class Entity:
    text: str
    type: str
    id: str | None
    environment: str | None
    service: str | None
    known: bool


@dataclass(frozen=True)
class _Known:
    type: str
    id: str | None
    environment: str | None
    service: str | None


class EntityResolver:
    def __init__(self, names: dict[str, _Known], ids: dict[str, _Known], services: dict[str, str], flags: dict[str, _Known]):
        self._names = dict(sorted(names.items(), key=lambda kv: -len(kv[0])))  # longest first
        self._ids = ids
        self._services = dict(sorted(services.items(), key=lambda kv: -len(kv[0])))
        self._flags = flags

    @classmethod
    def from_scenario(cls, path: str | Path = SCENARIO_FILE) -> EntityResolver:
        with open(path, encoding="utf-8") as fh:
            sc: dict[str, Any] = yaml.safe_load(fh)
        ids: dict[str, _Known] = {}
        names: dict[str, _Known] = {}
        services: dict[str, str] = {}
        for name, svc in sc["services"].items():
            for alias in {name, svc["namespace"], svc["display_name"].lower(), name.rsplit("-", 1)[0], name.replace("-", " ")}:
                services[alias.lower()] = name
        for inc in sc["incidents"]:
            ids[inc["id"]] = _Known("incident", inc["id"], inc.get("environment"), inc.get("service"))
            services.setdefault(inc["service"], inc["service"])
        for dep in sc["deployments"]:
            ids[dep["id"]] = _Known("deployment", dep["id"], dep["environment"], dep["service"])
        for rel in sc["releases"]:
            ids[rel["id"]] = _Known("release", rel["id"], None, rel["service"])
            ids[rel["version"]] = _Known("release", rel["version"], None, rel["service"])
        for sha, commit in sc["commits"].items():
            ids[sha] = _Known("commit", sha, None, commit["repository"].split("/")[-1])
        for trace in sc["traces"].values():
            ids[trace["trace_id"]] = _Known("trace", trace["trace_id"], trace["environment"], trace["service"])
        for channel in sc["collaboration"]["channels"]:
            known = _Known("channel", channel["name"], None, None)
            ids[channel["name"]] = known
            names[channel["name"].lstrip("#")] = known
        kinds = {"managed-postgres": "database", "managed-redis": "cache", "vm-instance": "instance", "container-task": "task"}
        for res in sc["cloud"]["resources"]:
            known = _Known(kinds.get(res["type"], "cloud-resource"), res["id"], res["environment"], None)
            ids[res["id"]] = known
            names[res["id"]] = known
            stem = re.sub(r"-(?:prod|production|staging|stage|dev|development)$", "", res["id"])
            if stem != res["id"] and known.type in ("database", "cache"):
                generic = _Known(known.type, None, None, None)
                for alias in (stem, stem.replace("-", " "), stem.replace("-db", " database")):
                    names.setdefault(alias, generic)
        for service, envs in sc["kubernetes"].items():
            for env, workload in envs.items():
                names[workload["cluster"]] = _Known("cluster", workload["cluster"], env, None)
                for pod in workload["pods"]:
                    ids[pod["name"]] = _Known("pod", pod["name"], env, service)
        flags = {}
        for flag in sc["feature_flags"]["flags"]:
            known = _Known("flag", flag["key"], flag["environment"], None)
            flags[flag["key"]] = known
            names[flag["key"]] = known
            names[flag["key"].replace("-", " ")] = known
        return cls(names, ids, services, flags)

    # -- lookup ---------------------------------------------------------------------------------
    def resolve(self, request: str) -> list[Entity]:
        taken: list[tuple[int, int]] = []
        found: list[Entity] = []
        lower = request.lower()

        def free(start: int, end: int) -> bool:
            return all(end <= s or start >= e for s, e in taken)

        def add(span: tuple[int, int], text: str, known: _Known | None, kind: str, ident: str | None) -> None:
            taken.append(span)
            if known is not None:
                found.append(Entity(text, known.type, known.id, known.environment, known.service, True))
            else:
                found.append(Entity(text, kind, ident, None, None, False))

        for kind, pattern in ID_SHAPES:
            for m in pattern.finditer(request):
                if free(*m.span()):
                    known = self._ids.get(m.group(0))
                    add(m.span(), m.group(0), known, kind, m.group(0))
        for name, known in self._names.items():
            for m in re.finditer(r"(?<![\w#-])" + re.escape(name) + r"(?![\w-])", lower):
                if free(*m.span()):
                    add(m.span(), request[m.start():m.end()], known, known.type, known.id)
        if not any(e.type == "flag" for e in found):
            flag = self._loose_flag(lower)
            if flag is not None:
                found.append(Entity(flag.id or "", "flag", flag.id, flag.environment, None, True))
        services = []
        for alias, service in self._services.items():
            for m in re.finditer(r"(?<![\w#-])" + re.escape(alias) + r"(?![\w-])", lower):
                if free(*m.span()):
                    taken.append(m.span())
                    if service not in services:
                        services.append(service)
                        found.append(Entity(request[m.start():m.end()], "service", service, None, service, True))
        for kind, pattern in TYPE_WORDS:
            if any(e.type == kind for e in found):
                continue
            for m in pattern.finditer(lower):
                if free(*m.span()):
                    taken.append(m.span())
                    found.append(Entity(request[m.start():m.end()], kind, None, None,
                                        services[0] if len(services) == 1 else None, False))
                    break
        return found

    def _loose_flag(self, lower: str) -> _Known | None:
        words = set(re.findall(r"[a-z0-9]+", lower))
        flag_word = bool(FLAG_WORDS.search(lower))
        best = None
        for key, known in self._flags.items():
            distinctive = [t for t in key.split("-") if t not in GENERIC_TOKENS]
            hits = sum(t in words for t in distinctive)
            if hits >= 2 and (flag_word or hits == len(distinctive)):
                if best is None or hits > best[0]:
                    best = (hits, known)
        return best[1] if best else None

    # -- summaries ------------------------------------------------------------------------------
    @staticmethod
    def evidence_types(entities: list[Entity]) -> set[str]:
        return {e.type for e in entities if e.type in EVIDENCE_TYPES}

    @staticmethod
    def domains(entities: list[Entity]) -> list[str]:
        out: list[str] = []
        for e in entities:
            domain = TYPE_DOMAIN.get(e.type)
            if domain and domain not in out and (e.type in EVIDENCE_TYPES or e.type == "cluster"):
                out.append(domain)
        return out

    @staticmethod
    def environment(entities: list[Entity]) -> str | None:
        envs = {e.environment for e in entities if e.known and e.environment and e.type != "service"}
        return envs.pop() if len(envs) == 1 else None
