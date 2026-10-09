"""The trust layer: token exchange, agent -> agent delegation, re-exchange after a pause, and validation.

Four rules, each enforced here and nowhere else:

1. Delegate, never impersonate.  The agent keeps its own name in `act`; the subject is recorded beside it.
2. Authority only narrows.  scopes = delegable(subject) ∩ delegable(head, when acting for a human) ∩ ceiling(agent),
   and every agent -> agent hop intersects again.  No step adds a scope; `non_delegable` scopes never enter a token.
3. Tokens are sender-constrained.  `cnf` names the one workload allowed to present the token.
4. Re-derive, never extend.  After a pause the token is exchanged again from the current directory, so a revoked
   delegation stays revoked.

Narrowing happens at each exchange because RFC 8693 treats nested actors as informational: a downstream consumer
must not be trusted to re-check the history.  The chain is enforced when it is built and recorded when it is shown.
"""

from __future__ import annotations

from aid.attestation import Attestor
from aid.config import Clock, short_id
from aid.contracts import Actor, EventProvenance, ExecutionToken
from aid.directory import Directory


class TrustError(Exception):
    pass


class TrustLayer:
    def __init__(self, directory: Directory, attestor: Attestor, clock: Clock):
        self.d, self.att, self.clock = directory, attestor, clock
        self.issued: dict[str, ExecutionToken] = {}
        self._n = 0

    def _id(self, *parts) -> str:
        self._n += 1
        return short_id("tok", *parts, self.clock.now(), self._n)

    @staticmethod
    def grant_id(human: str) -> str:
        return short_id("grant", human)

    # ---- the first exchange: head + (human) + agent -> execution token ------------------------------------------------
    def exchange(self, execution_id: str, invoker: str, invoker_credential: str, agent: str, on_behalf_of: str | None = None,
                 provenance: EventProvenance | None = None) -> ExecutionToken:
        ref = self.d.agent_ref(agent)
        if not self.d.agent_enabled(ref):
            raise TrustError(f"agent {ref} is disabled")
        if invoker_credential in self.d.revoked_credentials:
            raise TrustError("invoker credential revoked")
        grant = None
        if on_behalf_of:
            grant = self.grant_id(on_behalf_of)
            if grant in self.d.revoked_grants:
                raise TrustError(f"delegation from {on_behalf_of} revoked")
            scopes = self.d.delegable(on_behalf_of) & self.d.delegable(invoker)
        else:
            scopes = self.d.delegable(invoker)
        scopes &= self.d.ceiling(agent)
        now = self.clock.now()
        tok = ExecutionToken(token_id=self._id(execution_id, agent), execution_id=execution_id, sub=on_behalf_of or invoker,
                             invoker=invoker, on_behalf_of=on_behalf_of, grant_id=grant, act=Actor(sub=ref), scopes=tuple(sorted(scopes)),
                             cnf=self.d.spiffe(self.d.agents[agent]["runtime"]), iat=now, exp=now + self.d.ttl, depth=0,
                             provenance=provenance, invoker_credential=invoker_credential)
        self.issued[tok.token_id] = tok
        return tok

    # ---- agent -> agent ---------------------------------------------------------------------------------------------
    def delegate(self, parent: ExecutionToken, to_agent: str, execution_id: str) -> ExecutionToken:
        caller = parent.act.sub.split("@")[0]
        if to_agent not in self.d.agents[caller].get("may_delegate_to", []):
            raise TrustError(f"{caller} may not delegate to {to_agent}")
        if parent.depth + 1 > self.d.max_depth:
            raise TrustError(f"delegation depth {parent.depth + 1} exceeds {self.d.max_depth}")
        ref = self.d.agent_ref(to_agent)
        if not self.d.agent_enabled(ref):
            raise TrustError(f"agent {ref} is disabled")
        scopes = set(parent.scopes) & self.d.ceiling(to_agent)
        tok = ExecutionToken(token_id=self._id(execution_id, to_agent, parent.token_id), execution_id=execution_id, sub=parent.sub,
                             invoker=parent.invoker, on_behalf_of=parent.on_behalf_of, grant_id=parent.grant_id,
                             act=Actor(sub=ref, act=parent.act), scopes=tuple(sorted(scopes)),
                             cnf=self.d.spiffe(self.d.agents[to_agent]["runtime"]), iat=self.clock.now(), exp=parent.exp,
                             depth=parent.depth + 1, provenance=parent.provenance, invoker_credential=parent.invoker_credential)
        self.issued[tok.token_id] = tok
        return tok

    # ---- after a pause ----------------------------------------------------------------------------------------------
    def reexchange(self, tok: ExecutionToken) -> ExecutionToken:
        """Rebuild the token from the current directory, hop by hop.  Revoked delegations and disabled agents fail here."""
        agents = [a.split("@")[0] for a in reversed(tok.act.chain())]
        new = self.exchange(tok.execution_id, tok.invoker, tok.invoker_credential, agents[0], tok.on_behalf_of, tok.provenance)
        for a in agents[1:]:
            new = self.delegate(new, a, tok.execution_id)
        return new

    def extend(self, tok: ExecutionToken) -> ExecutionToken:
        """The unsafe alternative, kept only as a baseline for I7: same claims, later expiry."""
        new = tok.model_copy(update={"token_id": self._id(tok.execution_id, "extend"), "exp": self.clock.now() + self.d.ttl})
        self.issued[new.token_id] = new
        return new

    # ---- at the gateway ---------------------------------------------------------------------------------------------
    def validate(self, tok: ExecutionToken, svid: str) -> str | None:
        """None when the token may be used by this presenter now; otherwise the reason it may not."""
        if self.issued.get(tok.token_id) != tok:
            return "unknown or altered token"
        if tok.exp <= self.clock.now():
            return "token expired"
        presenter = self.att.verify(svid)
        if presenter is None:
            return "presenter failed attestation"
        if presenter != tok.cnf:
            return f"token bound to {tok.cnf}, presented by {presenter}"
        for ref in tok.act.chain():
            if not self.d.agent_enabled(ref):
                return f"agent {ref} is disabled"
        return None
