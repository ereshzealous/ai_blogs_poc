# Real vs simulated

The published, linked version is `results/human-in-the-loop-real-vs-simulated.html` (built from
`docs/source/real-vs-simulated.src.md`). This is the short form for the POC.

| Real (exercised as written) | Simulated (faithful local substitute) | Not built |
|---|---|---|
| Approval artifact and action digest · approver authentication, eligibility, separation of duties, two-person quorum · expiry, deny, timeout, escalation · state machine with compare-and-set and single-use consumption · revalidation on resume and request binding · idempotency keys, execution records, reconciliation · credential minted after revalidation · hash-chained audit and reconstruction · the three protocols and the policy-enforcing gateway · HTTP API and inbox | Datadog (one event) · Kubernetes (rolls back to the requested version whatever runs; accepts an idempotency key, which real Kubernetes does not) · Slack/Teams (clicks as calls; chat ids linked to principals) · the IdP and identity context (`config/principals.yaml`) · human waiting (a clock advance) · the humans (scripted) · the agent (a deterministic plan) | durable workflow engine · CIBA or step-up approver authentication · signed approval records · real Slack signing · leases · multi-agent approval chains · the AI control plane |

Injected on purpose: mutated actions, replays, ineligible approvers, world/identity/policy changes during the pause,
duplicate clicks and webhooks, a crash after commit, racing workers, deny, silence, late approval, service and policy
outages, rollout failure and lost responses.
