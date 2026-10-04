# Recorded run and replay verification

Every blind row stores its full model exchange. That covers each request body's hash, each raw response, the tool calls, the gateway stages, approvals, the audit chain and the ledger (`experiment/raw/blind-main/rows/<row>.json`). This makes the run replayable **without the model**.

## What replay does

`poc/scripts/verify_replay.py` re-runs selected rows with `RecordedChat` in place of Ollama. The recorded model responses are fed back in order. Everything downstream of the model executes again for real:

- the MCP server processes (official SDK, stdio);
- retrieval (BM25 plus `nomic-embed-text`, so the embedding model is still needed);
- entity resolution, capability collapse, binding, provenance and schema validation;
- deterministic policy, the approval service with its scripted approver, and the HMAC gateway;
- the simulated systems of record, the effects ledger and the scorer.

A row **reproduces** if its ledger effects, declared outcome and correctness match the recorded row. The script also counts *request-hash mismatches*, meaning model requests whose body differs from the one recorded. A mismatch means the replayed stack sent the model something different from what it saw live, which would matter for a live re-run but not for a replay.

## Selected rows

Five cases at 500 tools, in all three arms (15 rows), chosen before replay to cover the article's claims:

| Case | Why |
|---|---|
| BL-C03-1 | ORD-4917, the article's walkthrough (overlapping refund implementations) |
| BL-C07-1 | Approval-required refund with a scripted supervisor decision |
| BL-C08-1 | Missing requester-owned value (address change), then the requester's answer |
| BL-C10-1 | Nonexistent target, then the requester's corrected id |
| BL-C14-2 | Authoritative system down (persistent 503) while legacy and vendor tools stay up |

## Command

```bash
cd poc
uv run python scripts/verify_replay.py ../experiment/raw/blind-main \
    --out ../experiment/recorded-run/replay-check \
    --cases BL-C03-1 BL-C07-1 BL-C08-1 BL-C10-1 BL-C14-2 --sizes 500 --arms A B C
```

## Result

Run on 2026-09-28, during the repeat pass, from the frozen blind-main rows. **15 of 15 rows reproduced**: the same ledger effects, declared outcome and correctness. There were **zero request-hash mismatches** in every row. Every model request the replayed stack built was byte-identical to the one sent live, which means the deterministic parts of the system (prompt, entity context, retrieval, capability collapse, tool schemas and gateway results) regenerated exactly.

| Row | Effects | Declared outcome | Correctness | Request-hash mismatches |
|---|---|---|---|---|
| `BL-C03-1__A__500` | same | same | same | 0 |
| `BL-C07-1__A__500` | same | same | same | 0 |
| `BL-C08-1__A__500` | same | same | same | 0 |
| `BL-C10-1__A__500` | same | same | same | 0 |
| `BL-C14-2__A__500` | same | same | same | 0 |
| `BL-C03-1__B__500` | same | same | same | 0 |
| `BL-C07-1__B__500` | same | same | same | 0 |
| `BL-C08-1__B__500` | same | same | same | 0 |
| `BL-C10-1__B__500` | same | same | same | 0 |
| `BL-C14-2__B__500` | same | same | same | 0 |
| `BL-C03-1__C__500` | same | same | same | 0 |
| `BL-C07-1__C__500` | same | same | same | 0 |
| `BL-C08-1__C__500` | same | same | same | 0 |
| `BL-C10-1__C__500` | same | same | same | 0 |
| `BL-C14-2__C__500` | same | same | same | 0 |

Full output: `replay-check/replay-verification.json`, `replay-check/rows.jsonl`, `replay-check.log`.
