"""Label lint — must pass before the benchmark is frozen.

* every ORD-/CUS-/PAY-/TCK- id in a request or label exists in the seed world, unless the
  case is deliberately about a nonexistent target (listed in DELIBERATELY_ABSENT);
* no implementation is both accepted and a trap for the same case;
* every accepted implementation and trap exists in every estate (all cases are scorable
  at every size) and is registered, except deliberately unregistered shadow tools;
* the accepted implementation's region matches the entity's region;
* case ids are unique; blind and dev entities are disjoint.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from typing import Any

from ..registry.model import load_registry
from ..util import DATA_DIR, read_json
from ..world.seed import SEED_DB
from .cases import BENCHMARK_PATH

ID = re.compile(r"\b(ORD-\d+|CUS-\d+|PAY-\d+|TCK-\d+)\b")
DELIBERATELY_ABSENT = {"ORD-9917", "ORD-5999", "CUS-9999", "ORD-7999", "ORD-7888"}


def lint() -> list[str]:
    bench = read_json(BENCHMARK_PATH)
    con = sqlite3.connect(SEED_DB)
    known = set()
    for table, col in (("orders", "order_id"), ("customers", "customer_id"), ("charges", "payment_id"), ("tickets", "ticket_id")):
        known |= {r[0] for r in con.execute(f"SELECT {col} FROM {table} WHERE environment='prod'")}
    order_region = dict(con.execute("SELECT order_id, region FROM orders WHERE environment='prod'").fetchall())
    cust_region = dict(con.execute("SELECT customer_id, region FROM customers WHERE environment='prod'").fetchall())
    problems: list[str] = []
    estates = {n: read_json(DATA_DIR / "estates" / f"estate-{n}" / "manifest.json") for n in (50, 100, 500)}
    regs = {n: load_registry(DATA_DIR / "estates" / f"estate-{n}" / "registry.yaml") for n in (50, 100, 500)}
    tools_in = {n: {f"{s['server']}.{t}" for s in m["servers"] for t in s["tools"]} for n, m in estates.items()}
    shadow = {f"{s['server']}.{t}" for s in estates[500]["servers"] if not s["registered"] for t in s["tools"]}
    ents = {"blind": set(), "dev": set()}
    ids = [c["case_id"] for c in bench["cases"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate case ids")
    for c in bench["cases"]:
        cid, exp = c["case_id"], c["expected"]
        text = c["request"] + " " + json.dumps(exp)
        found = set(ID.findall(text))
        ents[c["split"]] |= {x for x in found if x.startswith("ORD-")}
        for x in found:
            if x not in known and x not in DELIBERATELY_ABSENT:
                problems.append(f"{cid}: {x} does not exist in the seed world")
            if x in DELIBERATELY_ABSENT and c["category"] != "C10":
                problems.append(f"{cid}: deliberately absent id {x} used outside C10")
        both = set(exp["accepted_implementations"]) & set(c["traps_nearby"])
        if both:
            problems.append(f"{cid}: implementation both accepted and trap: {sorted(both)}")
        for impl in list(exp["accepted_implementations"]) + list(c["traps_nearby"]):
            for n in (50, 100, 500):
                if impl in exp["accepted_implementations"] and impl not in tools_in[n]:
                    problems.append(f"{cid}: accepted {impl} missing from estate {n}")
            if impl not in shadow and regs[500].get(impl) is None:
                problems.append(f"{cid}: {impl} not registered and not a known shadow tool")
            if impl in exp["accepted_implementations"] and regs[500].get(impl) and regs[500].get(impl).capability != exp["capability"]:
                problems.append(f"{cid}: accepted {impl} implements {regs[500].get(impl).capability}, label says {exp['capability']}")
        for e in list(exp["effects"]) + list((exp.get("then") or {}).get("effects", [])):
            srv_region = {"refunds": "us", "refunds_eu": "eu"}.get(e["server"])
            ent = e["entity_id"]
            ent_region = order_region.get(ent) or cust_region.get(ent)
            if srv_region and ent_region and srv_region != ent_region:
                problems.append(f"{cid}: effect server {e['server']} ({srv_region}) vs entity {ent} ({ent_region})")
        if exp["handling"] in ("execute", "execute_or_report") and not exp["effects"]:
            problems.append(f"{cid}: execute case without expected effects")
        if exp["handling"] not in ("execute", "execute_or_report") and exp["effects"]:
            problems.append(f"{cid}: non-execute case with expected effects")
        if exp["handling"] == "read" and not exp["read_facts"]:
            problems.append(f"{cid}: read case without read facts")
        if bool(c.get("followups")) != bool(exp.get("then")):
            problems.append(f"{cid}: follow-ups and 'then' expectation must come together")
        for fu in c.get("followups") or []:
            if not set(fu["on"]) <= set(exp["accepted_outcomes"]):
                problems.append(f"{cid}: follow-up trigger {fu['on']} is not an accepted phase-1 outcome")
        if c["category"] == "C14" and not c.get("faults"):
            problems.append(f"{cid}: failure case without injected faults")
    overlap = ents["blind"] & ents["dev"]
    if overlap:
        problems.append(f"blind/dev share entities: {sorted(overlap)}")
    return problems


def main() -> None:
    p = lint()
    for x in p:
        print("LINT:", x)
    print(f"label lint: {'PASS' if not p else 'FAIL'} ({len(p)} problems)")
    sys.exit(1 if p else 0)


if __name__ == "__main__":
    main()
