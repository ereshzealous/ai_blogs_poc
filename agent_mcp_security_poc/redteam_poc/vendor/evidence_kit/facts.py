"""The fact registry: every number a page or an article prints, with where it comes from.

A fact is ``{value, display, unit, denominator, derivation, source, rows, freeze}``.  Only ``value`` is required;
``display`` is the text printed (it defaults to the value, formatted), ``rows`` names the recorded rows behind a count
(``{"run": ..., "ids": [...]}``), ``derivation`` says in words how the value was computed from them, ``source`` names the
file, and ``freeze`` the frozen manifest the source was checked against.

Copy refers to facts as ``{{id}}`` or ``{{id|filter}}``.  The build substitutes the display text, refuses an unknown id,
and refuses copy that types an experiment-derived number itself (``lint``): a number is either a fact or an identifier
the learning's spec allows (H1, R-12, …).
"""

from __future__ import annotations

import re
from typing import Any, Iterable

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.:\-@]+)\s*(?:\|\s*([a-z_]+)\s*)?\}\}")
NUMBER = re.compile(r"(?<![A-Za-z_])\d[\d,.]*")


def _and(items: list) -> str:
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


LIST_FILTERS = {"and": _and, "slash": lambda xs: " / ".join(map(str, xs)), "dot": lambda xs: " · ".join(map(str, xs)),
                "comma": lambda xs: ", ".join(map(str, xs)), "first": lambda xs: str(xs[0]), "last": lambda xs: str(xs[-1]),
                "count": lambda xs: str(len(xs))}
TEXT_FILTERS = {"lower": str.lower, "upper": str.upper, "cap": lambda s: s[:1].upper() + s[1:],
                "short": lambda s: s[1:] if re.match(r"^0\.\d", s) else s,       # p-values: 0.070 -> .070
                "pct": lambda s: f"{round(100 * float(s))}%", "num": lambda s: s.lstrip("#")}  # num: #7 -> 7


def fmt(v: Any) -> str:
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.0f}" if v.is_integer() else f"{v:g}"
    if isinstance(v, (list, tuple)):
        return _and(list(v))
    return str(v)


class Facts:
    def __init__(self) -> None:
        self.d: dict[str, dict] = {}

    def add(self, fid: str, value: Any, display: str | None = None, **prov) -> str:
        """Register a fact; returns its display text. Registering the same id twice with another value is an error."""
        entry = {"value": value, "display": fmt(value) if display is None else str(display),
                 **{k: v for k, v in prov.items() if v is not None}}
        old = self.d.get(fid)
        if old is not None and (old["value"], old["display"]) != (entry["value"], entry["display"]):
            raise ValueError(f"fact {fid} registered twice with different values: {old['display']!r} vs {entry['display']!r}")
        self.d[fid] = {**(old or {}), **entry}
        return entry["display"]

    def __contains__(self, fid: str) -> bool:
        return fid in self.d

    def __getitem__(self, fid: str) -> str:
        return self.d[fid]["display"]

    def value(self, fid: str) -> Any:
        return self.d[fid]["value"]

    def render(self, fid: str, flt: str | None = None) -> str:
        f = self.d[fid]
        if not flt:
            return f["display"]
        if flt in LIST_FILTERS:
            if not isinstance(f["value"], (list, tuple)):
                raise ValueError(f"filter |{flt} needs a list fact; {fid} is {f['value']!r}")
            return LIST_FILTERS[flt](f["value"])
        if flt in TEXT_FILTERS:
            return TEXT_FILTERS[flt](f["display"])
        raise ValueError(f"unknown filter |{flt} on {fid}")

    def resolve(self, text: str, where: str = "") -> str:
        """Substitute every {{id}} in text; an unknown id is an error naming where it was used."""
        def sub(m: re.Match) -> str:
            fid, flt = m.group(1), m.group(2)
            fid, _, field = fid.partition("@")  # {{id@source}}: a field of the fact's provenance
            if fid not in self.d or (field and field not in self.d[fid]):
                raise KeyError(f"{where or 'copy'}: unknown fact {{{{{m.group(1)}}}}}")
            return str(self.d[fid][field]) if field else self.render(fid, flt)
        return PLACEHOLDER.sub(sub, text)

    def used(self, text: str) -> list[str]:
        return [m.group(1) for m in PLACEHOLDER.finditer(text)]

    def to_json(self) -> dict:
        return {k: self.d[k] for k in sorted(self.d)}


def lint(text: str, allow: Iterable[re.Pattern]) -> list[str]:
    """Numbers typed into copy: every digit run outside a {{placeholder}} and outside an allowed identifier."""
    t = PLACEHOLDER.sub(" ", text)
    for rx in allow:
        t = rx.sub(" ", t)
    return [m.group(0).rstrip(".,") for m in NUMBER.finditer(t)]


# spec keys that hold identifiers or layout, not words a reader reads: their strings are resolved but not linted
STRUCTURAL = {"id", "type", "data", "cls", "style", "icon", "source", "metric", "x", "y", "m", "kind", "better", "field", "first", "last",
              "key", "color", "tone", "variant", "show", "case_fact", "kv", "href", "systems", "if", "file", "path", "scale",
              "prov", "check", "checks"}  # 5.0: a provenance footer names a run, an experiment, a file and checks: identifiers


def resolve_tree(obj: Any, facts: Facts, allow: list[re.Pattern], path: str = "", errors: list | None = None,
                 exempt: tuple[str, ...] = (), structural: bool = False) -> Any:
    """Resolve every string in a spec subtree; collect hand-typed numbers in `errors` (paths under `exempt` and
    structural keys skip the lint)."""
    errors = [] if errors is None else errors
    if isinstance(obj, str):
        if not structural and not any(re.fullmatch(e, path) for e in exempt):
            bad = lint(obj, allow)
            if bad:
                errors.append(f"{path}: typed number(s) {', '.join(bad)} in {obj[:90]!r}")
        return facts.resolve(obj, path)
    if isinstance(obj, list):
        return [resolve_tree(x, facts, allow, f"{path}[{i}]", errors, exempt, structural) for i, x in enumerate(obj)]
    if isinstance(obj, dict):
        return {k: resolve_tree(v, facts, allow, f"{path}.{k}" if path else k, errors, exempt, structural or k in STRUCTURAL) for k, v in obj.items()}
    return obj
