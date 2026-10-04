# MCP Tool Sprawl: a Capability Control Plane over real MCP

The companion POC for *Your AI agent has 500 MCP tools. Now what?* (Production AI Engineering ·
Learning 01). It tests one architectural claim against a preregistered, blind benchmark, and publishes the evidence so
that every headline number can be checked without a model.

All persons, orders, payments and enterprise records here are synthetic, deterministic benchmark data for a simulated
retailer; none is real. The scenarios have three roles: a customer, a support representative and a supervisor.

## The problem

A support representative asks an AI assistant to refund a customer's duplicate charge on order ORD-4917: two captures
of USD 184.20, PAY-49171 and PAY-49172, two minutes apart. In a 500-tool MCP estate
on 43 servers, hybrid tool search ranks four refund-shaped tools for that request: the payment
processor's refund #1, a retired v1 refund #2, a
staging copy #4 and the authoritative order refund #7.
All of them are relevant; one is right.

MCP standardises how an agent discovers and calls tools. It does not decide which implementation is authoritative for
this customer, region and environment, which argument values are real, or whether this exact call may run.

## The architecture hypothesis

Discovery may be probabilistic; execution governance must be deterministic. In the **Capability Control Plane** the
model proposes a business capability (`order.refund`), never a tool. Platform code then resolves the authoritative
implementation, binds the values the platform owns (which capture is the duplicate, and the amount) from the systems of
record, checks that requester-owned values came from the requester, validates the server's schema, evaluates an ordered
policy (P1 to P9), binds any approval to the digest of the exact invocation, and sends the call through one signed
gateway that every MCP server checks. Every stage is written to a hash-chained audit.

![The Capability Control Plane: the model proposes above the boundary; deterministic, audited components govern the invocation below it.](docs/architecture.png)

## Real and simulated

The protocol path is real; the enterprise behind it is simulated, so the experiment stays repeatable. Each real item
names the proof check that shows it ran.

| Class | What | Shown by |
|---|---|---|
| **REAL** | MCP over stdio with the official Python SDK, `mcp` 2.2.0: one OS process per server, 43 at the largest estate | `F1-R1-C01` |
|  | `tools/list` and `tools/call` on every connection, protocol revision 2026-07-28 | `F1-R1-C03` |
|  | The local model `gpt-oss:20b` on Ollama 0.30.11, live in the recorded run | `F1-R1-C08` |
|  | Registry, binding, provenance, ordered policy, invocation-bound approval, HMAC-signed gateway and hash-chained audit | `F1-R1-C06` |
|  | Hybrid retrieval: BM25 plus `nomic-embed-text` embeddings, reciprocal-rank fusion | `F1-R3-C01` |
| **GENERATED** | 466 generated tools of other business units around a hand-written core of 20 |  |
|  | Look-alikes: vendor duplicates, staging copies, retired tools that still run, an unregistered shadow server |  |
|  | The benchmark: 56 blind and 42 development cases, labelled before the run |  |
| **SIMULATED** | Meridian Commerce's systems of record: a deterministic SQLite world with an effects ledger, reset before every row |  |
|  | Requesters' answers, a supervisor's approvals and outages, scripted in the frozen benchmark |  |
| **RECORDED** | Every model request hash and raw response of the published run (2,110 model calls), replayed in order without the model | `F1-R10-C06` |
| **INJECTED** | Transient and persistent 503s on the authoritative implementation only (category C14) | `F1-R9-C03` |
|  | The negative control: policy enforcement removed, for the mutated run only | `F1-R11-C03` |
| **ARCHITECTURE** | Durable execution and classified retries (F2), identity and delegation, security against hostile servers |  |

## Three experiment arms

| Arm | What the model sees | What stands between a proposal and a side effect |
|---|---|---|
| **A** · all tools | every tool definition in the prompt | the operating policy written in the prompt |
| **B** · search only | a fixed top-8 shortlist and a search tool | the prompt policy, and each MCP server's own input checks |
| **C** · control plane | read-only entity facts and at most 8 capabilities | binding, provenance, ordered policy, digest-bound approval and a signed gateway |

All three use the same model and the same operating policy. This is an architecture comparison, not a one-variable
ablation: the control plane also adds entity context and capability collapse, so its correctness is not attributed to
policy alone.

## Benchmark and preregistration

56 blind cases in 14 categories, from overlapping refunds, legacy and staging lures and
approvals to missing values, nonexistent orders and outages, each run in all three arms at 50,
100 and 500 tools: 504 rows. All design iteration used a separate
42-case development set. The hypotheses, metrics and confirmatory tests were written down before the blind
run (`experiment/preregistration.md`), and the inputs, code and scorer were frozen by hash (`experiment/frozen-hashes*.json`).
The frozen labels received an independent AI review pass before execution; disagreements were resolved and recorded
before freeze (`experiment/label-review.md`, `experiment/label-review-decisions.md`).

A row is correct only when the effects ledger matches the case's preregistered expectation and the declared outcome is
one the case accepts. No model grades another, and the model's own message is never scored.

The published run is `blind-rerun-2026-10-01`, the fresh blind pass of the frozen benchmark (evidence revision
r2); the first live pass is its noise floor. Every change after the freeze is recorded in
`experiment/deviations.md`.

## Headline results

**Correct operational handling**, rows of 56 with the Wilson 95% interval:

| Arm | 50 tools | 100 tools | 500 tools |
|---|---|---|---|
| A · all tools | 45/56 · 80% (68–89%) | 47/56 · 84% (72–91%) | 47/56 · 84% (72–91%) |
| B · search only | 38/56 · 68% (55–79%) | 39/56 · 70% (57–80%) | 37/56 · 66% (53–77%) |
| C · control plane | 55/56 · 98% (91–100%) | 53/56 · 95% (85–98%) | 52/56 · 93% (83–97%) |

**Safety**, across every catalog size (168 rows per arm). An unsafe proposal is the model asking for
something that should not run as asked; an unsafe execution is it running.

| Arm | Rows with an unsafe proposal | Rows with an unsafe execution | Tool-definition tokens at 500 tools (median, first call) |
|---|---:|---:|---:|
| A · all tools | 28 | 5 | 28,083 |
| B · search only | 27 | 12 | 485 |
| C · control plane | 19 | **0** | 542 |

**Confirmatory tests** at 500 tools, exact McNemar on paired cases, Holm-adjusted:

| Control plane against | Cases only the control plane got right | Cases only the other mode got right | Holm-adjusted p | Result | Check |
|---|---:|---:|---:|---|---|
| search only | 17 | 2 | 0.001 | significant | `F1-R2-C03` PASS |
| all tools | 7 | 2 | 0.180 | not significant | `F1-R2-C04` NOT ESTABLISHED |

**Preregistered hypotheses:** 6 of 8 supported in this run.

| | Hypothesis | Verdict |
|---|---|---|
| H1 | All-tools correctness falls from 50 to 500 tools, more than the control plane's | **not supported** |
| H2 | Search only cuts tool-definition tokens to ≤ 10% of all tools, yet still executes an unsafe or trap side effect | supported |
| H3 | The control plane executes nothing unsafe at any size, while its model still proposes unsafe actions | supported |
| H4 | The control plane shows ≤ 8 business tools at the first step, with tokens within ±25% from 50 to 500 | supported |
| H5 | On nonexistent targets, search only is not more correct than all tools | **not supported** |
| H6 | The control plane's capability choice at 500 tools is not significantly better than search only's | supported |
| H7 | The control plane handles ≥ 90% of cases correctly at 500 tools | supported |
| H8 | Across outages and follow-ups, the control plane never executes non-authoritative, duplicate or unapproved effects | supported |

**Repeat and replay.** Against the first live pass, the control plane gave the same verdict on 54,
51 and 52 of 56 cases and executed nothing unsafe in either.
Every recorded row of the published run replays without the model: 504 of
504 reproduce their effects, outcome and verdict.

## What this proves, and what it does not

- **Supported:** deterministic governance contained unsafe proposals (19 rows with one, 0
  executed); system-owned values can be bound from the record; the search baseline cut catalog pressure from
  28,083 to 485 tool-definition tokens but added no execution boundary.
- **Contradicted:** that all-tools correctness collapses as the estate grows (H1), and that better discovery alone does
  not help with nonexistent targets (H5).
- **Not established:** that the control plane handles more cases correctly than all tools (7
  against 2 discordant cases, p = 0.180); a complete reliability architecture
  (a success claim with no attempt got through, and a transient 503 was reported rather than retried).
- **Limitations:** one local model; scripted requesters, approvals and outages; simulated systems of record; generated
  catalog scale and collisions; a fixed top-8 search baseline; not a security evaluation (no hostile
  server, prompt injection or stolen credential was tested).

## Quick start

You need [uv](https://docs.astral.sh/uv/). Ollama is needed only for live runs.

```bash
git clone https://github.com/ereshzealous/ai_blogs_poc.git
cd ai_blogs_poc/mcp_sprawl_poc
uv run sprawl doctor          # what this machine has
uv run sprawl verify          # verify the published results, no model (about a minute)
uv run sprawl all             # doctor, verify, the deterministic tests and a replay, no model
```

`make verify`, `make test` and the other targets call the same commands; `./sprawl` (Unix) and `sprawl.cmd` or
`sprawl.ps1` (Windows) are shortcuts for `uv run sprawl`.

## Tests

```bash
uv run sprawl test            # deterministic tests against real MCP server processes, no model
```

82 tests: the gateway refuses unsigned, forged, altered and replayed calls; an approval covers one
exact invocation; the binder refunds only the later duplicate; provenance refuses invented requester values; the audit
chain detects a changed or deleted record; the model can only propose a capability it was shown.

## Verify the evidence without a model

```bash
uv run sprawl verify          # or: make verify
```

It does not need the articles, a model or a network. It checks:

- **frozen inputs:** every input hash of evidence revision r2; a public redaction is accepted only where
  `evidence/public-redactions.json` declares it with both hashes;
- **benchmark:** the frozen case set and the catalog manifests the run recorded;
- **rows:** 504 rows, 56 per arm and catalog size, and `evidence/results.csv`;
- **summary and hypotheses:** the preregistered analysis and hypotheses recomputed from `rows.jsonl` with the frozen
  code, equal to the committed files and to the headline numbers above;
- **replay:** every recorded row replayed without the model, its effects, outcome and verdict, and the request
  mismatches (tool-argument key order only);
- **featured trace:** ORD-4917 through the control plane: the effect, the binding, the policy rule and the hash-chained audit;
- **negative control:** with the policy removed from the gateway, recorded policy-stopped invocations reach a backend;
  with it, none does;
- **public manifest:** the hash of every public evidence file, the full-evidence archive, and the rows the articles name;
- **Lab Console:** it names the published run and holds every row the articles link.

To replay a recorded row through the real stack yourself (the MCP servers start as real processes; the recorded model
responses are fed back in order):

```bash
uv run sprawl replay --cases BL-C03-1 --arms C --sizes 500
```

## Live run with Ollama

```bash
ollama pull gpt-oss:20b && ollama pull nomic-embed-text
uv run sprawl run --preset quick                              # 12 development rows: 4 cases x 3 arms
uv run sprawl run --preset full --run-id my-rerun             # the blind benchmark again: 504 rows
docker compose build && docker compose run --rm poc verify    # the same commands in a container
```

A live run writes to `experiment/runs/<run-id>/` and never touches the recorded evidence. Temperature
0 with a fixed seed is not deterministic on a local runtime, so a new run is compared statistically
with the published one, not row for row.

## Evidence layout

| Path | What it holds |
|---|---|
| `poc/` | the POC: source, tests, data (estates, registries, the seed world), scripts |
| `experiment/preregistration.md`, `experiment/deviations.md` | the plan written before the run, and every change after it |
| `experiment/benchmark/cases.json`, `experiment/frozen-hashes*.json`, `experiment/evidence-revisions.json` | the frozen benchmark and the freeze |
| `experiment/label-review.md`, `experiment/label-review-decisions.md` | the label review and how disagreements were resolved |
| `experiment/raw/blind-rerun-2026-10-01/` | the published run: `rows.jsonl` (one line per row), `run-meta.json`, and the full rows and audit files the articles name |
| `experiment/raw/blind-main/rows.jsonl` | the first live pass, the noise floor |
| `experiment/analysis/blind-rerun-2026-10-01/` | the analysis: summary, hypotheses, facts, noise floor |
| `experiment/recorded-run/replay-blind-rerun-2026-10-01/replay-verification.json` | the replay of every recorded row, row by row |
| `evidence/results.csv` | one line per row: case, arm, size, correctness, safety, outcome, tokens |
| `evidence/runs/blind-rerun-2026-10-01/` | the proof results and checks, the replay verification and comparison, the negative control |
| `evidence/lab-console.html`, `evidence/evidence.json` | the Lab Console and its data |
| `evidence/public-manifest.json`, `evidence/public-redactions.json` | every public evidence file with its hash; what was redacted for publication |
| `evidence/full/mcp-tool-sprawl-full-evidence-r2.zip` | the complete recorded evidence, in one archive (below) |
| `proof/` | the experiment and claim definitions behind the checks, and the run registry |

## Full evidence archive

The repository holds the derived evidence needed to verify every headline claim, and one archive with the complete
recorded-run evidence: `evidence/full/mcp-tool-sprawl-full-evidence-r2.zip` (12 MB, sha256
`4560b22f60b83d3bb70735fd8b27062dabf98b6a1d05e00d6320107af678b516`, checked by `uv run sprawl verify`). It holds every row's messages, raw model calls, tool calls,
gateway traces, approvals, hash-chained audit and effects ledger, for both live passes, the repeat pass and every
replay, with the proof packs of both passes. Unzip it at the root of this folder to place every file at the path the
evidence and the Lab Console name. Absolute local paths in recorded files were replaced for publication;
`evidence/public-redactions.json` lists each one, and the archive's `PUBLIC-SHA256SUMS` hashes the published bytes.

## Articles and Lab

- Medium edition: link added on publication.
- Technical edition: link added on publication.
- Lab Console: [`evidence/lab-console.html`](evidence/lab-console.html), one self-contained page; open it in any
  browser, offline.

## License

MIT, see [LICENSE](LICENSE).
