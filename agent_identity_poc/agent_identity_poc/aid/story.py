"""The article's running story, recorded: the 14:02 Datadog event, the investigation, the 14:09 rollback request, the
approval and the rollback, in chain mode.  `aid demo` prints it; `aid experiments` writes it to runs/<id>/story.json so
the article's closing "audit X-ray" is drawn from a recorded run, not typed.
"""

from __future__ import annotations

from typing import Any

from aid.agents import IncidentIntel
from aid.contracts import EventProvenance
from aid.platform import Platform

KEEP = ("event_source", "event_id", "event_rule", "invoker", "on_behalf_of", "agent", "act_chain", "workload", "scopes", "capability",
        "arguments", "tool_principal", "credential_id", "authorized_by", "approval_id", "revocation")


def story() -> dict[str, Any]:
    p = Platform("chain")
    prov = EventProvenance(source="datadog/monitors", event_id="dd-evt-771204", rule="monitor/payment-service-error-rate")
    ex = p.start("event", "cred-monitoring", "agent.incident-intel", provenance=prov)
    t = ex.token
    agent = IncidentIntel()
    reads = []
    for c in agent.investigate():
        d = p.call(ex, c)
        reads.append({"capability": c.capability, "effect": d.effect, "tool_principal": d.output["tool_principal"] if d.output else None})
    p.clock.advance(7 * 60)
    first = p.call(ex, agent.remediate())
    maya_try = p.approve(first.approval_id, "sre.maya")[1]
    ic_ok = p.approve(first.approval_id, "ic.dev")[1]
    done = p.call(ex, agent.remediate(), approval_id=first.approval_id)
    rec = p.audit.calls("rollbackDeployment")[-1]
    return {
        "token": {"sub": t.sub, "on_behalf_of": t.on_behalf_of, "act": t.act.chain(), "cnf": t.cnf, "scopes": list(t.scopes)},
        "reads": reads,
        "rollback_request": {"effect": first.effect, "reason": first.reason},
        "approval_attempts": {"sre.maya": maya_try, "ic.dev": ic_ok},
        "rollback": {"effect": done.effect, "tool_principal": done.output["tool_principal"]},
        "kubernetes_entry": p.tools["kubernetes"].log[-1],
        "platform_record": {k: rec[k] for k in KEEP},
        "chain_intact": p.audit.verify()[0],
        "physical_rollbacks": len([e for e in p.tools["kubernetes"].effects if e["verb"] == "deployments:patch"]),
    }
