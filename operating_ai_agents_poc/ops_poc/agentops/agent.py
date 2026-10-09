"""The scripted agents (P1 layer D's reasoning, replaced by a deterministic script so the platform is the only variable).

Each workflow type is a plan: a generator that yields operations and receives their results. The runtime
(agentops/runtime.py) executes the operations under the platform's controls. A plan may depend on the release: the
scripted agent follows tool descriptions literally, so a description that says "call this before every answer, once
per shipment" makes it call the tool more often. That is a DECLARED behavioural model for the simulation, standing in
for the documented fact that models choose tools from their descriptions; it is not a measurement of any real model.

Two pathologies are scripted on purpose (E4): a payment that stays PENDING makes the refund agent re-check it forever
(a runaway loop), and a coordinator re-delegates a child that came back without an answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .common import cfg

OUT = {k: v.get("out_tokens", {}) for k, v in cfg("workflows")["workflows"].items()}
CHILD_OUT = cfg("workflows")["workflows"]["dispute-investigation"]["child_out_tokens"]
REDELEGATIONS = 3          # how many times the scripted coordinator re-delegates a child that returned no answer


@dataclass
class Model:
    kind: str
    out: int
    decisive: bool = False       # the answer whose correctness decides the workflow's outcome


@dataclass
class Retrieve:
    sources: list[str]


@dataclass
class Tool:
    name: str


@dataclass
class Approval:
    amount: int


@dataclass
class Spawn:
    children: list[dict] = field(default_factory=list)


def per_shipment(release) -> bool:
    return "once per shipment" in release.tool_description("orders.lookup")


def plan(case: dict, release):
    wf = case["workflow"]
    o = OUT.get(wf, {})
    if wf == "order-status":
        yield Retrieve(["policies"])
        yield Model("plan", o["plan"])
        if per_shipment(release):
            for _ in range(case["shipments"]):
                yield Tool("orders.lookup")
            yield Tool("orders.lookup")                   # "before every answer"
            if case["shipments"] >= 2:
                yield Model("summarize", o["summarize"])
        else:
            yield Tool("orders.lookup")                   # one lookup returns every shipment
        yield Model("answer", o["answer"], decisive=True)
    elif wf == "product-question":
        yield Retrieve(["catalog", "policies"])
        yield Model("answer", o["answer"], decisive=True)
    elif wf == "delivery-change":
        yield Retrieve(["policies"])
        yield Model("plan", o["plan"])
        yield Tool("orders.lookup")
        yield Tool("carrier.options")
        yield Model("answer", o["answer"], decisive=True)
    elif wf == "refund-dispute":
        yield Retrieve(["policies", "tickets"])
        yield Model("plan", o["plan"])
        status = yield Tool("payments.status")
        while status == "PENDING":                        # the runaway: re-check until it settles (it never does)
            yield Model("assess", o["assess"])
            status = yield Tool("payments.status")
        yield Tool("orders.lookup")
        yield Model("assess", o["assess"])
        if case["amount"] > release.approval_above:
            yield Approval(case["amount"])
        yield Model("answer", o["answer"], decisive=True)
    elif wf == "recon-check":
        yield Tool("payments.status")
        yield Tool("payments.status")
        yield Model("compare", o["compare"], decisive=True)
    elif wf == "dispute-investigation":
        yield Retrieve(["policies"])
        yield Model("plan", o["plan"])
        kids = [{"workflow": "child", "role": r, "stuck": case.get("stuck") and r == "payments-agent"}
                for r in cfg("workflows")["workflows"]["dispute-investigation"]["children"]]
        results = yield Spawn(kids)
        for _ in range(REDELEGATIONS):                    # the scripted coordinator retries children that failed
            failed = [k for k, r in zip(kids, results) if r != "SUCCESS"]
            if not failed:
                break
            again = yield Spawn(failed)
            it = iter(again)
            results = [r if r == "SUCCESS" else next(it) for r in results]
        yield Model("synthesize", o["synthesize"], decisive=True)
    elif wf == "child":
        role = case["role"]
        if role == "orders-agent":
            yield Retrieve(["policies"])
            yield Model("plan", CHILD_OUT["plan"])
            yield Tool("orders.lookup")
        elif role == "payments-agent":
            yield Model("plan", CHILD_OUT["plan"])
            status = yield Tool("payments.status")
            while status == "PENDING":
                yield Model("assess", CHILD_OUT["plan"])
                status = yield Tool("payments.status")
        else:
            yield Model("plan", CHILD_OUT["plan"])
            yield Tool("carrier.options")
        yield Model("answer", CHILD_OUT["answer"])
    else:
        raise ValueError(wf)


def task_of(case: dict) -> str:
    """The eligibility-contract task of a workflow (children inherit the coordinator's)."""
    return "dispute-investigation" if case["workflow"] == "child" else case["workflow"]
