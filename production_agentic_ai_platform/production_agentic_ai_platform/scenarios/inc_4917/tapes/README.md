# Recorded model tapes

These are **scripted fixtures**, not transcripts of a live model. `RecordedModelA` and `RecordedModelB` replay them so that
the published proof is deterministic and runs offline. They stand in for "a model" at the proposal boundary; the proof is
about what the platform does with a proposal, not about how good the proposal is.

| Tape | Used by | What it simulates |
|---|---|---|
| `model_a.jsonl` | recorded-model-a (priority 1) | a model that investigates INC-4917 and proposes rollback to v4.16; if the context contains the injected instruction, it obeys it |
| `model_b.jsonl` | recorded-model-b (fallback) | the same decisions, different wording |
| `model_a_looping.jsonl` | R6 only (fault injection) | a planner that never becomes confident and keeps asking for metrics |

A request that matches no entry raises `TapeMiss`: the provider never improvises.
