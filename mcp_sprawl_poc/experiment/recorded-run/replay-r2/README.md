# Replay under evidence revision r2

**Why this exists.** After the blind run, an external source review found that the control-plane gateway also accepted an
exact implementation name from the model (for example `refunds__refund_order`). That path did no authoritative value
binding, so a guessed authoritative name could have skipped the capability binder and its duplicate-charge invariant.
Commit `1e916d7` closed it: the model-facing gateway accepts only capability tools surfaced to the model, and stops an
implementation name at the proposal stage. That changed frozen source (`poc/src/sprawl_poc/control_plane/gateway.py`),
so the evidence is re-identified as **revision r2** (`experiment/evidence-revisions.json`).

No recorded row used the closed path: every control-plane proposal in the recorded runs (469 across blind-main,
blind-repeat and the earlier replay check) named a surfaced capability. This replay checks that nothing else changed.

## What was replayed

Every recorded row, with the recorded model responses fed back in order (no model), through the r2 code. MCP server
processes, retrieval, entity resolution, binding, provenance, policy, approval, the gateway, the simulated systems, the
ledger and the scorer all ran again.

| Run | Rows | Reproduced |
|---|---|---|
| `experiment/raw/blind-main` (A, B, C × 50, 100, 500) | 504 | 504 |
| `experiment/raw/blind-repeat` (C × 50, 100, 500) | 168 | 168 |
| `experiment/raw/blind-repeat` (B × 500) | 56 | 56 |
| **Total** | **728** | **728** |

A row reproduces when its ledger effects, declared outcome and correctness equal the recorded row. All 728 do.

## Request-hash mismatches

38 of the replayed model requests, in 19 rows (control-plane rows of cases BL-C02-4, BL-C04-3, BL-C11-3 and one
BL-C08-1), were not byte-identical to the live requests. The only difference is **key order**: row files are written with
sorted keys (`sprawl_poc.util.write_json`), so recorded tool-call arguments replay in sorted order, and the arguments the
gateway echoes back in a tool result come back as `{"note": …, "ticket_id": …}` instead of the model's live
`{"ticket_id": …, "note": …}`. The values are identical.

**Control.** The same 12 rows (those four cases at three sizes) replayed with the pre-fix code (`59dafca`, r1) show the
same mismatches, row for row: the artifact predates the fix and is not caused by it. The earlier 15-row replay check had
none because its cases do not echo reordered arguments.

## Files

`summary.json` (totals, cause, control), and per run: `replay-verification.json` (per-row comparison), `rows.jsonl`
(per-row results and ledger effects) and `run-meta.json` (commit `1e916d7`, clean tree). The per-row transcripts and audit
logs (33 MB, a copy of the recorded rows) are not kept; this command regenerates them:

```bash
cd poc
CASES=$(python3 -c "import json;d=json.load(open('../experiment/benchmark/cases.json'));print(' '.join(c['case_id'] for c in d['cases'] if c['split']=='blind'))")
bash -c "uv run python scripts/verify_replay.py ../experiment/raw/blind-main --out ../experiment/recorded-run/replay-r2/blind-main --cases $CASES --sizes 50 100 500 --arms A B C"
bash -c "uv run python scripts/verify_replay.py ../experiment/raw/blind-repeat --out ../experiment/recorded-run/replay-r2/blind-repeat-C --cases $CASES --sizes 50 100 500 --arms C"
bash -c "uv run python scripts/verify_replay.py ../experiment/raw/blind-repeat --out ../experiment/recorded-run/replay-r2/blind-repeat-B500 --cases $CASES --sizes 500 --arms B"
```
