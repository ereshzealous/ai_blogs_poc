"""Production AI Engineering Proof Contract v1 (``pae-proof/v1``): the machinery every learning's proof pack uses.

    evaluate(experiments, facts)        checks declared in a learning's proof/experiments.toml, each a comparison of
                                        facts → check records (PASS / FAIL / EXPECTED_FAILURE) and experiment results
    trace(claims, experiments, checks)  article claims → experiments → checks → evidence, with each declared verdict
                                        tested against the checks it rests on
    results(...), summary(...)          the canonical results.json / summary.json / summary.md of one run
    sha256sums(paths, root)             a SHA256SUMS file (``shasum -a 256 -c`` compatible); verify_sha256sums(...)
    validate_schema(obj, schema)        the JSON Schema subset the contract's schemas use (no third-party package)
    scan(paths, root, allow)            secrets, credentials and private paths in what a learning publishes
    compare_rows(a, b, ...)             classify the differences between two runs of the same rows
    Report                              the PROOF VERIFICATION report (sections, PASS / FAIL, VERIFIED or not)

The kit knows no experiment: a check names facts (the adapter's registry, each with its provenance) and a comparison;
what was observed is always read from the facts, never typed.  The contract itself is in proof_contract/.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .facts import Facts, fmt

SCHEMA = "pae-proof/v1"
CONTRACT = "Production AI Engineering Proof Contract v1"
HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE / "proof_contract"
STATUSES = ("PASS", "FAIL", "EXPECTED_FAILURE")
# what a reader sees (PROOF_STANDARD.md §3, findings): the status stays the machine verdict; a FAIL of a hypothesis, a
# confirmatory test or a measurement is an experimental finding, a FAIL of anything else is a broken guarantee
FINDING_BY_KIND = {"hypothesis": "NOT SUPPORTED", "confirmatory": "NOT ESTABLISHED", "measurement": "NOT OBSERVED"}
FINDINGS = ("PASS", "NOT SUPPORTED", "NOT ESTABLISHED", "NOT OBSERVED", "LIMITATION OBSERVED", "EXPECTED FAILURE", "FAIL")


def finding(status: str, kind: str, declared: str | None = None) -> str:
    if status == "PASS":
        return "PASS"
    if status == "EXPECTED_FAILURE":
        return "EXPECTED FAILURE"
    return declared or FINDING_BY_KIND.get(kind, "FAIL")


def experiment_finding(findings: list[str]) -> str:
    if "FAIL" in findings:
        return "FAIL"
    out = [f for f in dict.fromkeys(findings) if f not in ("PASS", "EXPECTED FAILURE")]
    return " · ".join(out) if out else "EXPECTED FAILURE" if "EXPECTED FAILURE" in findings else "PASS"
KINDS = ("invariant", "hypothesis", "confirmatory", "measurement", "replay", "control", "implementation")
OPS = ("==", "!=", "<", "<=", ">", ">=", "within", "in", "not in")


class ProofError(SystemExit):
    pass


# ---------------------------------------------------------------- checks

def _num(v: Any) -> Any:
    """Numbers compare as numbers: '549' → 549.0; anything else is compared as it is."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", v.replace(",", "")):
        return float(v.replace(",", ""))
    return v


def _compare(actual: Any, op: str, want: Any, tolerance: float | None = None) -> bool:
    if isinstance(actual, (list, tuple)) and op in ("==", "!=", "<", "<=", ">", ">=", "within"):
        return all(_compare(a, op, want, tolerance) for a in actual)  # every element (e.g. one value per level of the factor)
    a, w = _num(actual), _num(want)
    if op == "==":
        return a == w
    if op == "!=":
        return a != w
    if op == "in":
        return a in (w if isinstance(w, (list, tuple)) else [w])
    if op == "not in":
        return a not in (w if isinstance(w, (list, tuple)) else [w])
    if not isinstance(a, float) or not isinstance(w, float):
        raise ProofError(f"comparison {op} needs numbers, got {actual!r} and {want!r}")
    if op == "within":
        return abs(a - w) <= (tolerance or 0.0) * abs(w)
    return {"<": a < w, "<=": a <= w, ">": a > w, ">=": a >= w}[op]


def source_path(source: str) -> tuple[str, str]:
    """A fact's source 'experiment/analysis/summary.json → cells.x (summed)' → ('experiment/analysis/summary.json', 'cells.x (summed)')."""
    s = (source or "").strip()
    path = re.split(r"\s+(?:→|\()", s, maxsplit=1)[0].strip()
    return path, s[len(path):].lstrip(" →").strip()


def _evidence(facts: Facts, fids: Iterable[str], extra: Iterable[str] = ()) -> tuple[list[dict], dict | None]:
    ev, rows = [], None
    for fid in fids:
        f = facts.d[fid]
        path, sel = source_path(f.get("source", ""))
        if path:
            ev.append({"fact": fid, "path": path, "selector": sel})
        if f.get("rows") and rows is None:
            rows = {"run": f["rows"]["run"], "count": len(f["rows"]["ids"]), "ids": list(f["rows"]["ids"])}
    for e in extra:
        p, _, sel = e.partition("#")
        ev.append({"path": p, "selector": sel})
    return ev, rows


def evaluate(spec: dict, facts: Facts) -> tuple[list[dict], list[dict]]:
    """spec = proof/experiments.toml.  Every check compares a fact with a value or another fact; what was observed is the
    fact's value.  A control check (expect = "fail") declares the invariant a safeguard protects and expects it to break
    when the safeguard is removed: EXPECTED_FAILURE when it breaks, FAIL when the proof did not notice."""
    experiments, checks, seen = [], [], set()
    for x in spec.get("experiments", []):
        xs = []
        for c in x.get("checks", []):
            cid = c["id"]
            if cid in seen:
                raise ProofError(f"check {cid} declared twice")
            seen.add(cid)
            if not cid.startswith(x["id"] + "-"):
                raise ProofError(f"check {cid} must be named after its experiment {x['id']}")
            for k in ("fact", "op"):
                if k not in c:
                    raise ProofError(f"check {cid}: missing {k}")
            if c["op"] not in OPS:
                raise ProofError(f"check {cid}: unknown op {c['op']!r} (use {', '.join(OPS)})")
            kind = c.get("kind", "invariant")
            if kind not in KINDS:
                raise ProofError(f"check {cid}: unknown kind {kind!r}")
            if c.get("finding") is not None:
                if kind not in FINDING_BY_KIND:
                    raise ProofError(f"check {cid}: a {kind} check cannot declare a finding (its FAIL always reads FAIL)")
                if c["finding"] not in ("NOT SUPPORTED", "NOT ESTABLISHED", "NOT OBSERVED", "LIMITATION OBSERVED"):
                    raise ProofError(f"check {cid}: unknown finding {c['finding']!r}")
            refs = [c["fact"]] + ([c["ref"]] if c.get("ref") else [])
            missing = [f for f in refs if f not in facts]
            if missing:
                raise ProofError(f"check {cid}: unknown fact(s) {missing}")
            if ("ref" in c) == ("value" in c):
                raise ProofError(f"check {cid}: give exactly one of value or ref")
            actual = facts.value(c["fact"])
            want = facts.value(c["ref"]) * c.get("scale", 1) if c.get("ref") else c["value"]
            held = _compare(actual, c["op"], want, c.get("tolerance"))
            expect = c.get("expect", "hold")
            status = ("PASS" if held else "FAIL") if expect == "hold" else ("EXPECTED_FAILURE" if not held else "FAIL")
            if c.get("ref"):
                scale = f" × {fmt(c['scale'])}" if c.get("scale", 1) != 1 else ""
                expected = f"{c['op']} {c['ref']}{scale} ({fmt(want) if not isinstance(want, float) or not want.is_integer() else fmt(int(want))})"
            else:
                expected = f"{c['op']} {fmt(want)}"
            if c["op"] == "within":
                expected += f" ± {fmt(round(100 * c.get('tolerance', 0)))}%"
            ev, rows = _evidence(facts, refs, c.get("evidence", []))
            rec = {"id": cid, "experiment": x["id"], "description": c.get("description", ""), "kind": kind,
                   "fact": c["fact"], "ref": c.get("ref"), "op": c["op"], "expected": expected, "expect": expect,
                   "actual": facts[c["fact"]], "actual_value": actual, "invariant_held": held, "status": status,
                   "finding": finding(status, kind, c.get("finding")),
                   "threshold_source": c.get("threshold_source"), "evidence": ev, "rows": rows}
            xs.append(rec)
        checks.extend(xs)
        st = [r["status"] for r in xs]
        result = "FAIL" if "FAIL" in st else "EXPECTED_FAILURE" if "EXPECTED_FAILURE" in st else "PASS"
        if not xs:
            raise ProofError(f"experiment {x['id']}: no checks (an experiment without a check proves nothing)")
        experiments.append({**{k: v for k, v in x.items() if k != "checks"}, "result": result, "finding": experiment_finding([r["finding"] for r in xs]),
                            "checks": [r["id"] for r in xs],
                            "counts": {s: st.count(s) for s in STATUSES}})
    return experiments, checks


# ---------------------------------------------------------------- claims

VERDICTS = {  # a declared verdict and what its checks must show
    "supported": lambda st: st and all(s in ("PASS", "EXPECTED_FAILURE") for s in st),
    "contradicted": lambda st: "FAIL" in st,
    "not_established": lambda st: "FAIL" in st,
    "implementation": lambda st: st and all(s == "PASS" for s in st),
    "control": lambda st: "EXPECTED_FAILURE" in st and "FAIL" not in st,
    "limitation": lambda st: True,  # not tested here: it names what it rests on instead of a check
}


def trace(spec: dict, experiments: list[dict], checks: list[dict]) -> tuple[list[dict], list[str]]:
    """spec = proof/claims.toml.  Each claim → its experiments → its checks → their statuses and evidence.  A declared
    verdict that the checks do not bear out is a problem (the article cannot say 'supported' over a failed check)."""
    X = {x["id"]: x for x in experiments}
    C = {c["id"]: c for c in checks}
    out, problems = [], []
    for cl in spec.get("claims", []):
        v = cl.get("verdict")
        if v not in VERDICTS:
            problems.append(f"claim {cl['id']}: unknown verdict {v!r}")
            continue
        miss = [x for x in cl.get("experiments", []) if x not in X] + [c for c in cl.get("checks", []) if c not in C]
        if miss:
            problems.append(f"claim {cl['id']}: unknown experiments or checks {miss}")
            continue
        st = [C[c]["status"] for c in cl.get("checks", [])]
        if not VERDICTS[v](st):
            problems.append(f"claim {cl['id']}: declared {v}, but its checks are {st or 'none'}")
        if v == "limitation" and not cl.get("rests_on"):
            problems.append(f"claim {cl['id']}: a limitation names what it rests on (rests_on)")
        out.append({**cl, "statuses": dict(zip(cl.get("checks", []), st)),
                    "evidence": sorted({e["path"] for c in cl.get("checks", []) for e in C[c]["evidence"]})})
    return out, problems


# ---------------------------------------------------------------- results

def results(run_id: str, manifest: dict, experiments: list[dict], checks: list[dict], facts: Facts, *,
            tables: dict | None = None, profile: dict | None = None, claims: list[dict] | None = None,
            paths: dict | None = None) -> dict:
    st = [c["status"] for c in checks]
    counts = {"experiments": len(experiments), "checks": len(checks), **{s.lower(): st.count(s) for s in STATUSES}}
    by_x = {s.lower(): sum(x["result"] == s for x in experiments) for s in STATUSES}
    fc = [c.get("finding") for c in checks if c["status"] == "FAIL"]
    finding_counts = {f: fc.count(f) for f in FINDINGS if fc.count(f)}  # the FAILs, as a reader sees them
    return {"schema": SCHEMA, "contract": CONTRACT, "run_id": run_id, "article": manifest.get("article_id"),
            "status": "COMPLETE", "check_counts": counts, "experiment_results": by_x, "finding_counts": finding_counts,
            "experiments": experiments, "checks": [c["id"] for c in checks], "claims": claims or [],
            "profile": profile or {}, "tables": tables or {}, "paths": paths or {}, "facts": facts.to_json()}


def summary(res: dict, title: str) -> tuple[dict, str]:
    c = res["check_counts"]
    s = {"schema": SCHEMA, "run_id": res["run_id"], "article": res["article"], "status": res["status"], "check_counts": c,
         "experiments": [{"id": x["id"], "title": x["title"], "result": x["result"], "counts": x["counts"]} for x in res["experiments"]]}
    lines = [f"# {title}", "", f"Run `{res['run_id']}` · {CONTRACT} (`{SCHEMA}`).", "",
             f"{c['experiments']} experiments · {c['checks']} checks: {c['pass']} pass, {c['fail']} fail, "
             f"{c['expected_failure']} expected failure (a negative control that broke as intended).", "",
             "A FAIL is a reported result, not an error: a preregistered hypothesis or comparison that the evidence did not",
             "bear out stays a FAIL. Unit tests are counted separately; they are not proof checks.", "",
             "| Experiment | Question | Result | Checks |", "|---|---|---|---|"]
    for x in res["experiments"]:
        k = x["counts"]
        lines.append(f"| {x['id']} · {x['title']} | {x.get('question', '')} | {x['result']} | "
                     f"{k['PASS']} pass · {k['FAIL']} fail · {k['EXPECTED_FAILURE']} expected failure |")
    return s, "\n".join(lines) + "\n"


def checks_jsonl(checks: list[dict]) -> str:
    return "".join(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n" for c in checks)


# ---------------------------------------------------------------- integrity

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256sums(paths: Iterable[Path], root: Path) -> str:
    """Lines `<sha256>  <path relative to root>`, sorted by path: `shasum -a 256 -c` from root verifies them.
    A hash verifies the files against this list; it says nothing about who wrote them."""
    rel = sorted({p.resolve().relative_to(root.resolve()).as_posix(): p for p in paths}.items())
    return "".join(f"{sha256_file(p)}  {r}\n" for r, p in rel)


def verify_sha256sums(listing: Path, root: Path) -> tuple[int, list[str]]:
    problems, n = [], 0
    for line in listing.read_text().splitlines():
        if not line.strip():
            continue
        digest, _, rel = line.partition("  ")
        p = root / rel
        n += 1
        if not p.exists():
            problems.append(f"missing: {rel}")
        elif sha256_file(p) != digest:
            problems.append(f"changed: {rel}")
    return n, problems


# ---------------------------------------------------------------- schema (the subset the contract's schemas use)

def validate_schema(obj: Any, schema: dict, path: str = "$", root: dict | None = None) -> list[str]:
    root = root or schema
    if "$ref" in schema:
        ref = schema["$ref"].split("/")[1:]
        node = root
        for r in ref:
            node = node[r]
        return validate_schema(obj, node, path, root)
    out: list[str] = []
    t = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}
    if t:
        allowed = t if isinstance(t, list) else [t]
        ok = any(isinstance(obj, types[x]) and not (x in ("integer", "number") and isinstance(obj, bool)) for x in allowed)
        if not ok:
            return [f"{path}: expected {t}, got {type(obj).__name__}"]
    if "const" in schema and obj != schema["const"]:
        out.append(f"{path}: must be {schema['const']!r}")
    if "enum" in schema and obj not in schema["enum"]:
        out.append(f"{path}: {obj!r} not in {schema['enum']}")
    if "pattern" in schema and isinstance(obj, str) and not re.search(schema["pattern"], obj):
        out.append(f"{path}: {obj!r} does not match {schema['pattern']}")
    if isinstance(obj, dict):
        for k in schema.get("required", []):
            if k not in obj:
                out.append(f"{path}: missing {k}")
        for k, sub in schema.get("properties", {}).items():
            if k in obj:
                out += validate_schema(obj[k], sub, f"{path}.{k}", root)
        if isinstance(schema.get("additionalProperties"), dict):
            for k, v in obj.items():
                if k not in schema.get("properties", {}):
                    out += validate_schema(v, schema["additionalProperties"], f"{path}.{k}", root)
    if isinstance(obj, list):
        if "minItems" in schema and len(obj) < schema["minItems"]:
            out.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, v in enumerate(obj):
                out += validate_schema(v, schema["items"], f"{path}[{i}]", root)
    return out


def schema(name: str) -> dict:
    return json.loads((CONTRACT_DIR / "v1" / f"{name}.schema.json").read_text())


# ---------------------------------------------------------------- publication hygiene

SECRETS = [
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("API key (sk-)", r"\bsk-[A-Za-z0-9_-]{20,}"),
    ("AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    ("Slack token", r"\bxox[abpors]-[A-Za-z0-9-]{10,}"),
    ("bearer token", r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    ("password assignment", r"(?i)\b(?:password|passwd|secret|api_key|apikey|access_token)\s*[:=]\s*['\"][^'\"\s]{6,}['\"]"),
    ("home directory", r"(?:/Users|/home)/[A-Za-z][\w.-]+/"),
    ("Windows home directory", r"[A-Za-z]:\\\\Users\\\\[\w.-]+"),
    ("temporary path", r"/(?:private/)?(?:var/folders|tmp)/[\w.-]+/"),
    ("e-mail address", r"\b[A-Za-z0-9._%+-]+@[A-Za-z][A-Za-z0-9-]*(?:\.[A-Za-z][A-Za-z0-9-]*)*\.[A-Za-z]{2,}\b"),  # a domain starts with a letter
]


def scan(paths: Iterable[Path], root: Path, allow: Iterable[str] = ()) -> list[dict]:
    """Findings: {file, line, kind, match}.  `allow` are regexes for matches that are intended (synthetic fixtures such
    as example.com addresses, the author's public byline): a finding that matches one is not reported."""
    allow_rx = [re.compile(a) for a in allow]
    rules = [(k, re.compile(r)) for k, r in SECRETS]
    out = []
    for p in paths:
        try:
            text = p.read_text(errors="replace")
        except (IsADirectoryError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for kind, rx in rules:
                for m in rx.finditer(line):
                    if any(a.search(m.group(0)) for a in allow_rx):
                        continue
                    out.append({"file": p.resolve().relative_to(root.resolve()).as_posix(), "line": i, "kind": kind, "match": m.group(0)[:80]})
    return out


# ---------------------------------------------------------------- run comparison

CLASSES = ("DETERMINISTIC_EQUIVALENT", "NONDETERMINISTIC", "MODEL_OUTPUT_VARIATION", "METHODOLOGY_CHANGE", "REGRESSION")


def compare_rows(a: dict[str, dict], b: dict[str, dict], *, measured: list[str], invariants: list[str], volatile: list[str],
                 methodology: dict[str, tuple[Any, Any]] | None = None, model_inputs: list[str] | None = None) -> dict:
    """Two runs of the same rows (id → row as plain values).  `measured` fields must be equal for the runs to be
    equivalent; `invariants` are fields whose value must still hold (a change there is a REGRESSION); `volatile` fields
    (timestamps, process ids, invocation ids, wall times) may differ; `methodology` maps a setting to its (a, b) values,
    and any difference there makes the comparison METHODOLOGY_CHANGE; `model_inputs` differing marks a row
    MODEL_OUTPUT_VARIATION when the model's output was regenerated rather than replayed."""
    meth = {k: v for k, v in (methodology or {}).items() if v[0] != v[1]}
    rows, counts = [], {c: 0 for c in CLASSES}
    for rid in sorted(set(a) & set(b)):
        x, y = a[rid], b[rid]
        diff_measured = [f for f in measured if x.get(f) != y.get(f)]
        diff_inv = [f for f in invariants if x.get(f) != y.get(f)]
        diff_vol = [f for f in volatile if x.get(f) != y.get(f)]
        diff_model = [f for f in (model_inputs or []) if x.get(f) != y.get(f)]
        if meth:
            cls = "METHODOLOGY_CHANGE"
        elif diff_inv:
            cls = "REGRESSION"
        elif diff_measured:
            cls = "MODEL_OUTPUT_VARIATION" if diff_model else "REGRESSION"
        elif diff_vol:
            cls = "NONDETERMINISTIC"
        else:
            cls = "DETERMINISTIC_EQUIVALENT"
        counts[cls] += 1
        rows.append({"row": rid, "class": cls, "measured_differences": diff_measured, "invariant_differences": diff_inv,
                     "volatile_differences": diff_vol})
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    return {"rows": len(rows), "classes": counts, "only_in_a": only_a, "only_in_b": only_b, "methodology_differences": meth,
            "equivalent": counts["REGRESSION"] == 0 and counts["METHODOLOGY_CHANGE"] == 0 and counts["MODEL_OUTPUT_VARIATION"] == 0,
            "detail": rows}


# ---------------------------------------------------------------- the verification report

class Report:
    """PROOF VERIFICATION: named sections, each PASS / FAIL / N/A with a short detail; VERIFIED only if none failed."""

    def __init__(self, title: str = "PROOF VERIFICATION"):
        self.title, self.sections = title, []

    def add(self, name: str, ok: bool | None, detail: str = "", problems: list[str] | None = None) -> bool:
        self.sections.append({"section": name, "status": "N/A" if ok is None else "PASS" if ok else "FAIL",
                              "detail": detail, "problems": (problems or [])[:20]})
        return bool(ok) or ok is None

    @property
    def verified(self) -> bool:
        return all(s["status"] != "FAIL" for s in self.sections)

    def text(self) -> str:
        w = max([len(s["section"]) for s in self.sections] + [10]) + 4
        lines = [self.title, ""]
        for s in self.sections:
            lines.append(f"{s['section']:<{w}}{s['status']:<6}{('  ' + s['detail']) if s['detail'] else ''}")
            lines += [f"{'':<{w}}  · {p}" for p in s["problems"]]
        lines += ["", "VERIFIED" if self.verified else "NOT VERIFIED"]
        return "\n".join(lines) + "\n"

    def json(self, **extra) -> dict:
        return {"schema": SCHEMA, "report": self.title, "verified": self.verified, "sections": self.sections, **extra}
