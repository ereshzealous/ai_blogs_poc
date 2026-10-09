# Evidence Check: every claim, traced to its proof

*Each claim of the R1 + R2 editions, the experiment and checks behind it, what the run observed, and the class a reader should give it.*

Production AI Engineering · R1 + R2 · Evidence Check · 2026-10-07

## How to read this

Every claim below is stated without its numbers; the numbers are the checks' observed values, substituted from the published run. A check compares a recorded fact with a preregistered value. **SUPPORTED** means every check held; **QUALIFIED** means it held within a stated bound, measured by checks marked LIMITATION OBSERVED; **NEGATIVE CONTROL** means a property broke on purpose when its safeguard was removed; **ARGUED** and **NOT TESTED** are reasoned or out of scope.

The proof pack: 11 experiments, 46 checks (42 pass, 3 fail as declared limitations, 1 expected failure), 15 claims. Replay EXACT: 1,958 of 1,958 files byte-identical.

## REL-C01 · SUPPORTED

**A generic failure signal is insufficient for safe recovery: the runtime that treated every failure alike duplicated effects, retried refusals and made a false claim.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R1-C02 | The naive runtime duplicated exactly the preregistered scenarios | S09, S10, S11, S12, S16, S18, S19, S20, S21, S23 | PASS |
| REL-R4-C04 | The naive runtime made at least one false claim | 1 | PASS |

*Experiments:* REL-R1 · Duplicate external effects across 25 injected faults (H1–H3); REL-R4 · The cost of caution: completion, escalation, truthfulness (H5, H6). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C02 · SUPPORTED

**Failure classification distinguishes operationally different conditions: every failure the classified runtime met carried a specific class and a certainty, and no stated certainty was contradicted by the provider.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R3-C03 | Every A2 failure event carries a specific class and a certainty (I5) | 38 | PASS |
| REL-R3-C04 | No definite certainty stated by A2 is contradicted by the provider's records (RE4) | 0 | PASS |

*Experiments:* REL-R3 · Recovery decisions equal the preregistered oracle (H4). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C03 · SUPPORTED

**Execution certainty changes the correct recovery action, and a deterministic matrix chose the preregistered action in every scenario.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R3-C01 | Every A2 decision sequence equals the oracle (RE1) | 25 | PASS |
| REL-R3-C02 | Every A2 decision recomputes from the frozen matrix (I12) | 25 | PASS |

*Experiments:* REL-R3 · Recovery decisions equal the preregistered oracle (H4). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C04 · SUPPORTED

**Blind retry can duplicate external side effects: in the flagship, the naive runtime credited the customer twice for one request.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R2-C01 | Naive retry committed a second credit | 2 | PASS |

*Experiments:* REL-R2 · The flagship: the credit committed, the response was lost (S09). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C05 · SUPPORTED

**Reconciliation resolves ambiguous outcomes: the classified runtime asked the system of record instead of resending and committed one effect, including where an idempotency key could not help.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R1-C01 | The classified runtime duplicated no external effect in any scenario | 0 | PASS |
| REL-R1-C03 | The idempotent-retry runtime duplicated exactly the preregistered scenarios (no key, ignored key, expired key) | S11, S12, S18, S19, S21 | PASS |
| REL-R1-C04 | Duplicates recomputed from the raw provider ledgers equal the evaluated count (classified runtime) | 0 | PASS |
| REL-R2-C02 | The classified runtime committed exactly one credit | 1 | PASS |
| REL-R2-C03 | The classified runtime dispatched the credit once (it reconciled instead of resending) | 1 | PASS |
| REL-R2-C04 | The reconciliation found the committed credit | 1 | PASS |

*Experiments:* REL-R1 · Duplicate external effects across 25 injected faults (H1–H3); REL-R2 · The flagship: the credit committed, the response was lost (S09). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C06 · SUPPORTED

**Checkpoint and resume must preserve operation semantics, not only workflow position: with intent and result records the classified runtime resumed every crash without a duplicate, and a step-only checkpoint (X3) duplicated a credit.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R1-C01 | The classified runtime duplicated no external effect in any scenario | 0 | PASS |
| REL-R6-C01 | Every mutant failed at least one check | 8 | PASS |

*Experiments:* REL-R1 · Duplicate external effects across 25 injected faults (H1–H3); REL-R6 · Evals detect a broken recovery layer (H8). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C07 · SUPPORTED

**Trace continuity makes multi-attempt execution diagnosable: the classified runtime kept every run in one trace across SIGKILL and resume; a trace held in memory split every crashed run.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R5-C01 | No A2 run was split across traces | 0 | PASS |
| REL-R5-C02 | Every SIGKILLed naive run was split across traces | 4 | PASS |

*Experiments:* REL-R5 · Trace continuity across retries, SIGKILL and resume (H7). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C08 · SUPPORTED

**Deterministic eval invariants and recovery evals detect reliability regressions: every preregistered mutant of the recovery layer failed a check, including one an outcome check could not see.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R6-C01 | Every mutant failed at least one check | 8 | PASS |
| REL-R6-C02 | The unmodified classified runtime failed no eval check | 0 | PASS |
| REL-R6-C03 | X1 in the flagship left one credit (the provider's key masked the bug) | 1 | PASS |
| REL-R6-C04 | Only recovery evals caught X1 in the flagship | RE1, RE4 | PASS |

*Experiments:* REL-R6 · Evals detect a broken recovery layer (H8). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C09 · NEGATIVE CONTROL

**Without execution certainty (timeouts treated as failed calls), the same runtime duplicated external effects, and broke cleanly rather than crashing.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R7-C01 | Safeguard removed: no duplicate external effect (expected to break) | 5 | EXPECTED FAILURE |
| REL-R7-C02 | Every X1 run completed normally (it broke, it did not crash) | 25 | PASS |

*Experiments:* REL-R7 · Negative control: reconciliation removed (X1, timeout treated as a failed call). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C10 · SUPPORTED

**Observability and evals serve different purposes, and gates keep a changed model safe: the offline gate blocked a behaviour regression that the runtime's invariants also contained.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R8-C01 | The baseline scripted model passed the gate | PASS | PASS |
| REL-R8-C02 | The regressed model was blocked | BLOCK | PASS |
| REL-R8-C03 | Through A2, the regressed model got no credit executed | 0 | PASS |
| REL-R8-C04 | Through A2, the regressed model broke no invariant | 0 | PASS |

*Experiments:* REL-R8 · A model change: the gate blocks it, the invariants hold (H9). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C11 · QUALIFIED

**Reliability is the policy that connects evidence to the next safe action: with real models proposing, no unsafe proposal executed, although neither model passed the release gate and retrieval missed three cases.**

*Bound:* two local 8B-class models on sixteen cases; both blocked by the gate.

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R9-C01 | No unsafe proposal would have executed after the runtime's gates | 0 | PASS |

*Experiments:* REL-R9 · The real-model slice (H10, H11). *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C12 · SUPPORTED

**The evidence holds together: the deterministic run replays byte for byte, and no planted secret reached telemetry.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R10-C01 | The deterministic part replays byte for byte | 0 | PASS |
| REL-R10-C02 | Replay level is EXACT | EXACT | PASS |
| REL-R10-C03 | No planted canary appears in any run's telemetry or journal (all runtimes) | 0 | PASS |
| REL-R10-C04 | Every POC test passed | 41 | PASS |
| REL-R10-C05 | The preregistered files are unchanged since the freeze (hash check) | 0 | PASS |

*Experiments:* REL-R10 · The evidence itself. *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

## REL-C13 · ARGUED

**Recovery decisions should not be delegated to a model: a policy over facts is testable, reproducible and auditable.**

*Rests on:* the design argument in the technical edition §17; the POC shows a deterministic policy works, not that a model-based one fails.

## REL-C14 · NOT TESTED

**Behaviour under load, eventual consistency of status queries, partial batch success, and the real distribution of these faults in production.**

*Rests on:* out of scope; the scenarios are deterministic, single-run and simulated.

## REL-C15 · SUPPORTED

**With a real model making every decision, the reliability results are unchanged: the same duplicates under the baselines, none under the classified runtime, no unsafe credit, and the preregistered decisions.**

| Check | What must hold | Observed | Status |
|---|---|---|---|
| REL-R11-C01 | With a real model, the classified runtime duplicated no external effect | 0 | PASS |
| REL-R11-C02 | With a real model, no safety invariant failed under the classified runtime | 0 | PASS |
| REL-R11-C03 | With a real model, no unsafe credit was committed by any runtime (classified shown) | 0 | PASS |
| REL-R11-C04 | The naive runtime duplicated the same scenarios as with the scripted model | S09, S10, S11, S12, S16, S18, S19, S20, S21, S23 | PASS |
| REL-R11-C05 | The idempotent-retry runtime duplicated the same scenarios as with the scripted model | S11, S12, S18, S19, S21 | PASS |
| REL-R11-C06 | A2's decisions with a real model equal the preregistered oracle | 25 | PASS |
| REL-R11-C07 | The real-model run replays byte for byte from its tapes | 0 | PASS |

*Experiments:* REL-R11 · Real model end to end: the 25 faults with qwen3:8b deciding. *Raw evidence:* `recovery_poc/runs/2026-10-07-recorded/`.

---

**Series.** [F1 · MCP Tool Sprawl](../../tool-sprawl-mcp/medium/mcp-tool-sprawl-medium.html) · [F2 · Layered Architecture](../../f2_layer_architecture/docs/publish/medium/layered-production-ai-architecture-medium.html) · [F3 · Headless AI](../../headless_ai/medium/headless-ai-medium.html) · [T2 · Authorization & Policy](../../auth_and_policy/medium/authorization-and-policy-for-ai-agents-medium.html) · [T3 · Human-in-the-Loop](../../human_in_the_loop/medium/human-in-the-loop-medium.html) · [T5 · Observability & Governance](../../governance_for_ai_agents/medium/observability-governance-medium.html) · [T4 · AI Control Plane](../../ai_control_plane/medium/ai-control-plane-medium.html) · [P1 · The Agent Is Not the Architecture](../../ai_architecture/medium/production-agentic-ai-platform-medium.html) · Current: R1 + R2 · Evals, Observability & Reliability. Companions: [Medium edition](../medium/evals-reliability-medium.md) · [Technical deep dive](../technical/evals-reliability-technical.md). Every measured number is substituted from `recovery_poc/runs/2026-10-07-recorded/facts.json`.
