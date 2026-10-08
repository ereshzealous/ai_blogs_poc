"""Architecture C's independent agents: evidence, diagnosis, remediation, review.

One function, `run_specialist`, is the whole agent.  The A2A server (coord/a2a_server.py) calls it inside its own OS
process; experiment E7 also calls it in-process, so the A2A boundary is the only difference between the two paths.

An agent accepts a delegation only with a token minted for it (audience = its principal) for this workflow and this
delegation; it then exchanges that token for a gateway token, which can only narrow (its scopes ∩ the delegated
scopes).  A remediation delegation without `authorize_execution` carries no write scope, so even a model that tries to
write is refused by the gateway, not by the prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from coord import prompts
from coord.agent_loop import AgentSpec, run_agent
from coord.contracts import Diagnosis, EvidenceArtifact, RemediationProposal, RemediationResult, ReviewVerdict
from coord.gateway import CallContext, Gateway, GatewayTools
from coord.identity import AuthError, Token, TokenService
from coord.models import ModelGateway
from coord.util import load_config
from coord.world import WRITE_TOOLS

AGENTS: dict[str, dict[str, Any]] = load_config("agents.yaml")["agents"]
INSTRUCTIONS = {"evidence": prompts.C_EVIDENCE, "diagnosis": prompts.C_DIAGNOSIS, "remediation": prompts.C_REMEDIATION, "review": prompts.C_REVIEW}


@dataclass
class SpecialistEnv:
    gateway: Gateway
    model: ModelGateway
    tokens: TokenService
    limits: dict[str, Any]


def output_for(agent: str, authorize: bool) -> tuple[type, str]:
    if agent == "evidence":
        return EvidenceArtifact, "evidence"
    if agent == "diagnosis":
        return Diagnosis, "diagnosis"
    if agent == "review":
        return ReviewVerdict, "review"
    if agent == "remediation":
        return (RemediationResult, "remediation_result") if authorize else (RemediationProposal, "remediation_proposal")
    raise ValueError(agent)


def brief(request: dict[str, Any], catalog: list[dict[str, Any]] | None = None) -> str:
    inc = request["incident"]
    parts = [f"Delegation {request['delegation_id']} from the coordinator.",
             f"Incident {inc['id']} on {inc['service']} ({inc['environment']}): {inc.get('alert', '')}",
             f"Objective: {request['objective']}"]
    if request["agent"] == "remediation":
        parts.append("Execution IS authorized for this delegation." if request.get("authorize_execution")
                     else "Execution is NOT authorized for this delegation: propose the concrete change you recommend "
                          "(decision=remediate with tool and args) if one is warranted, but do not call any write tool.")
    if catalog:
        parts.append("Write tools (for reference; you may call them only when execution is authorized):\n"
                     + json.dumps(catalog, separators=(",", ":")))
    if request.get("inputs"):
        # sort_keys: A2A carries data parts as protobuf Struct, whose map order is not preserved across the wire
        parts.append("Input artifacts:\n" + json.dumps(request["inputs"], separators=(",", ":"), default=str, sort_keys=True))
    return "\n".join(parts)


async def run_specialist(env: SpecialistEnv, request: dict[str, Any], token: Token) -> dict[str, Any]:
    agent = request["agent"]
    principal = AGENTS[agent]["principal"]
    if token.aud != principal:
        raise AuthError(f"token audience {token.aud} is not {principal}")
    if token.wf != request["workflow_id"] or token.dlg != request["delegation_id"]:
        raise AuthError("token was minted for a different workflow or delegation")
    gw_token = env.tokens.exchange(token, target="gateway")
    authorize = bool(request.get("authorize_execution"))
    names = [t for t in AGENTS[agent]["tools"] if authorize or t not in WRITE_TOOLS]
    port = GatewayTools(env.gateway, gw_token, names,
                        CallContext(request["workflow_id"], principal, request["incident"]["environment"], request["delegation_id"]))
    output, kind = output_for(agent, authorize)
    spec = AgentSpec(principal, INSTRUCTIONS[agent], max_turns=int(env.limits["agents"]["specialist_max_turns"]))
    catalog = env.gateway.catalog([n for n in AGENTS[agent]["tools"] if n in WRITE_TOOLS]) if agent == "remediation" else None
    result, stats = await run_agent(spec, brief(request, catalog), env.model, port, output, workflow_id=request["workflow_id"],
                                    delegation_id=request["delegation_id"])
    return {"kind": kind, "body": result.model_dump(), "stats": stats, "scopes": gw_token.scope, "chain": gw_token.chain()}
