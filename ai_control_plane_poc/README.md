# T4 POC · AI Control Plane: change the control plane, not the agent

*Production AI Engineering · Trust & Security track · T4*

**Agents should contain business reasoning, not enterprise governance.** This POC tests one architectural claim: when
the **control plane** changes and the **agent** does not, the governed behaviour changes, everywhere, at the next step,
and on the record. Three agents (incident, support, finance) run in one long-lived runtime process. A separate control
plane declares, versions, signs and distributes their desired state: registry, tool and MCP permissions, model profiles,
approvals, budgets, secret *references*, rollouts and emergency switches. Enforcement stays local to the runtime; the
agents keep only their business plans.

It continues the series' payment-service incident: the incident agent restarts `payment-service` in production.

## The core proof (P2)

One central change (production restarts now need approval), and nothing else:

| | Before (control plane v1) | After (control plane v2) |
|---|---|---|
| Agent code | sha256 `677bca2acd66` | sha256 `677bca2acd66` (agent edits: 0) |
| Runtime process | `rt-a/pid-1` | `rt-a/pid-1` (the same process; redeploys: 0) |
| Request | hash `cb0531217710` | hash `cb0531217710` |
| Decision | `ALLOW` | `APPROVAL_REQUIRED` |
| Production restart | executed | not executed: the deploy system still shows 1 restart |

The restart count comes from the simulated deploy system's own side-effect log, not from what the agent reports. P2 is
built to fail: `tests/test_cheating.py` reruns it with the agent code edited, the process restarted and the request
altered, and it fails each time. Record: `control_plane_poc/runs/2026-10-03-recorded/P2.json`; proof card in `proof.txt`.

## The twelve proofs

| Proofs | Role | Result in run `2026-10-03-recorded` |
|---|---|---|
| **P2** (P1 its baseline) | **The core proof**: one central change, same agent, same process, same request | HELD |
| P3–P8 | Capabilities: approval, suspension, budgets, MCP revocation, model governance, rollout | HELD |
| P9–P10 | Boundary tests: outage, tampered bundle, broker down, stale policy, drift | QUALIFIED where the guarantee stops (see below) |
| P11 | Negative control: the same rules embedded in each agent | the property broken by design, as intended |
| P12 | Governing the governor: who may change the control plane | HELD |

100 of 100 test assertions held across 15 scenarios. In words:

- **P11, the negative control.** The same four changes, embedded in the agents, took 7 file edits and 7 redeploys, left
  8 static credential literals in agent code, and the process that was not redeployed still restarted production. Its
  assertions pass because they assert that the break was observed.
- **P12.** Of 10 change attempts, 3 were accepted and 7 rejected (an agent granting itself a tool, widenings without a
  second approver, break-glass trying to widen, a plaintext credential), all on one hash chain that verifies.
- **P9–P10, qualified, not hidden.** When the control plane is unreachable, reads continue on the last-known-good
  bundle and mutations fail closed, but a suspension published during the partition reached that runtime only after it
  reconnected: 3 calls ran after it was published (P9). Drift is detected, with what ran under the stale version, not
  prevented (P10).

## Reproduce it

Requirements: [`uv`](https://docs.astral.sh/uv/) (it installs Python 3.12 and the dependencies) and `make`. No model,
no API key, no network, no Docker.

```bash
git clone https://github.com/ereshzealous/ai_blogs_poc.git
cd ai_blogs_poc/ai_control_plane_poc
make setup       # the POC environment
make test        # 44 tests: architecture invariants, cheating detection, decisions, every proof, the live path
make demo        # P2: one central change, same process, same agent code, different behaviour
make verify      # rerun all twelve proofs in a fresh copy; identical to the published run (raw process ids masked)
make evidence    # PROOF VERIFICATION of the published run (Production AI Engineering Proof Contract, pae-proof/v1)
make all         # lint, tests, replay, proof pack recomputed byte for byte, PROOF VERIFICATION
```

`make help` lists every target. `make proof P="P4 P9"` prints any proof's card from a scratch run.

**With a self-hosted LLM in the loop (optional).** `ollama pull qwen3:8b`, then `make live` (L1–L3: the model plans the
incident agent's steps; the runtime still decides every step), or `make live-dry` for the same path with a scripted
stand-in model. Live runs vary, so they are illustrative, not part of the published evidence. The one recorded live run,
`control_plane_poc/runs/live/ollama-2026-09-30T100218Z/`, is described in [`control_plane_poc/README.md`](control_plane_poc/README.md#live-mode-an-llm-in-the-loop).

## The evidence

| What | Where |
|---|---|
| The raw run: every scenario's input, transcript, outcome and full end state | [`control_plane_poc/runs/2026-10-03-recorded/`](control_plane_poc/runs/2026-10-03-recorded/) (`summary.md`, `proof.txt`, `checks.json`, `facts.json`, `P1–P12.json`, `scenarios/`) |
| The proof pack (pae-proof/v1): manifest, results, checks, step ledger, negative control, replay record, SHA256SUMS | [`evidence/runs/2026-10-03-recorded/`](evidence/runs/2026-10-03-recorded/), named by [`evidence/published.json`](evidence/published.json) |
| The last PROOF VERIFICATION report | [`evidence/verification/verification.txt`](evidence/verification/verification.txt) |
| Experiments and claims (each claim → proof → checks, with its status) | [`proof/experiments.toml`](proof/experiments.toml), [`proof/claims.toml`](proof/claims.toml) |
| The Evidence Check: every claim, supported, qualified, negative control, not supported, argued or not tested | [`results/ai-control-plane-evidence.md`](results/ai-control-plane-evidence.md) |
| The Run Report: every observed value and every check | [`results/ai-control-plane-report.md`](results/ai-control-plane-report.md) |
| Real vs simulated | [`results/ai-control-plane-real-vs-simulated.md`](results/ai-control-plane-real-vs-simulated.md) |
| The Lab Console: every scenario's question, input, output, steps, lineage and outcome | [`results/lab-console.html`](results/lab-console.html) (a standalone page: download it and open it in a browser) |
| Every value the articles print, as the build substituted it | [`docs/evidence-uses.json`](docs/evidence-uses.json) (`make evidence` checks each against the run) |

The first edition's run, `2026-09-30-recorded`, is kept unchanged as lineage (`evidence/published.json` → history).

## Real and simulated

**Real code:** bundle versioning, signing and verification, the rollout pointer and buckets, the hash-chained change log
and audit, change authorization and validation, the decision point, the runtime SDK with its cache and failure policy,
the credential broker's minting, approvals, the spend meter, and the separate long-lived runtime process.

**Simulated:** the MCP servers, enterprise systems and models (`control_plane_poc/acp/systems.py`; live mode uses a real
local model); the network (fault flags); time (logical ticks); the agents' plans (fixed in the recorded run); and the
signing key, a demo HMAC key in `control_plane_poc/config/signing.key`, never a production pattern. The full table is
in [Real vs simulated](results/ai-control-plane-real-vs-simulated.md).

## What this POC does not prove

- That a production control plane was built. It proves the architectural reason to have one.
- That a kill switch stops every runtime instantly, or that drift detection prevents stale enforcement: the run
  measures both limits (P9, P10) and supports neither claim.
- Anything about model quality: the recorded agents follow fixed plans; live mode is illustrative.
- Production-grade cryptography and storage: asymmetric signing with keys in a KMS or HSM, a secret manager, a durable
  approval workflow and an atomic budget service are what a production control plane would use instead.

## Layout

```text
control_plane_poc/   the POC (uv project): acp/ (control plane, runtime, agents, systems, experiments), config/, tests/,
                     runs/ (2026-10-03-recorded, 2026-09-30-recorded, live/ollama-2026-09-30T100218Z, PUBLISHED)
proof/               experiments.toml, claims.toml, manifest.toml
evidence/            published.json, runs/<run>/ (the proof pack), verification/
tools/               verify_run.py (replay), proof_pack.py, proof_facts.py, ledger.py, verify_evidence.py (PROOF VERIFICATION)
vendor/kit5/         evidence-kit 5.2.0, pinned ("copy, don't link"): the Proof Contract implementation the tools use
results/             the Evidence Check, the Run Report, Real vs simulated, the Lab Console
docs/                evidence-uses.json
```

Licence: MIT.
