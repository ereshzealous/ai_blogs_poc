# T1 POC architecture

```text
 heads: Datadog webhook · web console (+ Maya's SSO) · workflow engine · CI pipeline
   │ channel-bound credential (+ a human session, if any)
   ▼
 Directory.authenticate  ──▶  invoker, on_behalf_of, EventProvenance(source, id, rule)
   ▼
 TrustLayer.exchange (aid/trust.py)
   scopes = delegable(subject) ∩ delegable(head, if for a human) ∩ ceiling(agent)      non_delegable never enters
   ExecutionToken{sub, invoker, on_behalf_of, grant_id, act, scopes, cnf=runtime SPIFFE id, exp=+15 min}
   │                               └── delegate(): act nests, scopes intersect again, declared edges, depth ≤ 2
   ▼
 agent proposes CapabilityCall (aid/agents.py: no tools, no tokens)
   ▼
 runtime presents token + its SVID  (expired? re-exchange from the current directory; never extend)
   ▼
 CapabilityGateway (aid/gateway.py)
   validate token + attested presenter + every agent in act enabled
   → registered → scope held → high-risk production write needs an approval bound to this call (grants deploy:rollback once)
   → TokenBroker.mint(capability class@env): audience-bound, 10 minutes
   → Tool.call  (Kubernetes / Jira / Slack / telemetry: own grants, own log)
   → AuditLog: event, invoker, on_behalf_of, grant, agent, act chain, workload, scopes, tool principal, credential id,
               approver, approval id, effect, revocation handles          (hash-chained)
```

## Decisions

1. **Delegate, never impersonate.** The subject and the actor are separate claims. The tool sees neither; it sees a
   tool identity. The platform record keeps both.
2. **Authority only narrows, and narrowing happens where the chain is built.** RFC 8693 treats nested actors as
   informational, so no downstream consumer is trusted to re-check history.
3. **Some authority never travels.** `deploy:rollback` is held by the incident commander and delegable by no one. An
   approval grants it for one call digest, once.
4. **One tool identity per capability class and environment.** Not one per platform (the anti-pattern), not one per
   agent × system × environment (unmanageable). The agent and chain are the platform's to record.
5. **Tokens are bound to a workload.** `cnf` names the runtime's SPIFFE id; the gateway checks the presenter's attested
   id on every call. A disabled agent or a quarantined runtime stops at the next call; a revoked delegation stops at the
   next re-exchange (one token lifetime at most).
6. **Re-derive after a pause.** The runtime re-exchanges an expired token from the current directory rather than
   extending it, so a delegation revoked during an approval wait stays revoked (I7).
7. **Tool credentials are bearer tokens with a short life.** A stolen incident-remediator credential works against
   Kubernetes for up to ten minutes and nowhere else (I4). Sender-constrained tool credentials (mTLS or DPoP-bound) would
   close that window; most tools do not support them, which is why the lifetime is kept short.

## Not implemented (discussed in the technical edition)

A real identity provider and RFC 8693 wire format, real SPIRE attestation, DPoP or mTLS-bound tool credentials,
Kubernetes impersonation headers, transaction tokens across services, token introspection for immediate revocation of
self-contained tokens, and the authorization and policy engine the next article is about.

## Evidence: declared criteria, freeze, replay

`aid/experiments.py` evaluates 41 checks (I1-01 … I7-02 and the global assertions G01–G11), each with an id, a kind
(invariant, control, qualified) and an arm. `aid/freeze.py` reads them statically and keeps them declared in
`proof/preregistration.toml`. `aid freeze` hashes that file, every config file and the criteria code into
`proof/FREEZE.json`. A run refuses to start if any of them changed, and refuses to publish if the evaluated checks differ
from the declared list. `tools/verify_run.py` re-runs into a fresh copy and diffs byte for byte. See `method.md`.

