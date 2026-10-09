# pae-proof/v1 schemas

| Schema | Validates | Written by |
|---|---|---|
| `manifest.schema.json` | `evidence/runs/<run>/manifest.json` | the learning's proof pack builder |
| `results.schema.json` | `evidence/runs/<run>/results.json` | the proof pack builder (`evidence_kit.proof.results`) |
| `check.schema.json` | each line of `evidence/runs/<run>/checks.jsonl` | `evidence_kit.proof.evaluate` |
| `experiments.schema.json` | `proof/experiments.toml` (parsed) | the author |
| `claims.schema.json` | `proof/claims.toml` (parsed) | the author |
| `published.schema.json` | `evidence/published.json` | an explicit promote, never the last run |
| `negative-control.schema.json` | `evidence/negative-control/results.json` | the learning's negative control |

`evidence_kit.proof.validate_schema(obj, evidence_kit.proof.schema("manifest"))` checks the subset of JSON Schema these
files use (type, const, enum, pattern, required, properties, additionalProperties, items, minItems, `$ref`), with no
third-party package. The contract is `../PROOF_STANDARD.md`.
