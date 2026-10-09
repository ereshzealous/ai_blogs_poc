# enterprise_knowledge_rag_poc · governed retrieval, evidence packets and claim verification

*S2 · Enterprise Knowledge, Context Engineering & RAG · Production AI Engineering*
*Rendered from `README.template.md` by `tools/build_readme.py`; every number is a fact of run `{{run.id}}`.*

## Purpose

An agent retrieves relevant passages and still gives the wrong answer, because relevant is not authorized, current,
applicable or authoritative, and cited is not supported. This POC builds a synthetic enterprise (Meridian Commerce:
two tenants, runbooks, change policies, tickets, a wiki, a release system, a CMDB, an identity provider, an index built
at a nightly watermark), plants a failure in each of forty cases, and runs two pipelines over them:

- **naive**: vector top 8, everything admitted, chunks in rank order cut at the budget;
- **governed**: hybrid BM25 + vector retrieval and live record lookups, an access and status **recheck at the source**,
  scope, lifecycle, authority and conflict gates, an **evidence packet** assembled under the same budget, and a
  claim-level **citation verifier** whose verdicts bind the answer.

Five experiments isolate one variable each. Eighteen development cases were used to build it; {{d.cases}} held-out
cases were run once, after the code, corpus, labels and seventeen hypotheses were frozen.

## Proof at a glance (run `{{run.id}}`, held-out)

| | naive | governed |
|---|---|---|
| **B** labelled-invalid units in context, identical candidates | {{b.naive.invalid_units}} | **{{b.governed.invalid_units}}** |
| **B** units the asker cannot read, identical candidates | {{b.naive.unauthorized_units}} | **{{b.governed.unauthorized_units}}** |
| **B** needed units kept (of {{b.needed_in_pool}} in the pools) | {{b.naive.needed_in_context}} | **{{b.governed.needed_in_context}}** |
| **D** correct answers, {{run.model}}, {{d.cases}} cases × {{d.seeds}} seeds | {{d.naive.correct}} of {{d.naive.runs}} | **{{d.governed.correct}} of {{d.governed.runs}}** |
| **D** answers leaking restricted or revoked content | {{d.naive.leak_runs}} | **{{d.governed.leak_runs}}** |
| **D** answers recommending a forbidden action | {{d.naive.forbidden_action_runs}} | **{{d.governed.forbidden_action_runs}}** |
| **D** correct abstention, of {{d.governed.abst_runs}} unanswerable runs | {{d.naive.abst_ok}} | **{{d.governed.abst_ok}}** |
| **D** false abstention, of {{d.governed.answerable_runs}} answerable runs | **{{d.naive.false_abst}}** | {{d.governed.false_abst}} |
| **D** supporting claims citing invalid evidence | {{d.naive.invalid_support}} | **{{d.governed.invalid_support}}** |
| **D, sensitivity** correct answers, {{run.sens_model}}, one seed | {{ds.naive.correct}} of {{ds.naive.runs}} | **{{ds.governed.correct}} of {{ds.governed.runs}}** |

- **A** · relevance is not validity: vector's top 5 held a labelled-invalid unit in {{a.vector.invalid_top5_cases}} of {{a.trap_cases}} trap cases. Exact facts: the structured route returned {{a2.route}} of {{a2.records}} needed records; ranked prose returned {{a2.prose.hybrid}}.
- **C** · the assembler kept more needed units whole than truncation at 600 tokens ({{c.600.assembler.needed_covered}} vs {{c.600.truncate.needed_covered}}) and **fewer qualifier cases** ({{c.600.assembler.qual_cases_ok}} vs {{c.600.truncate.qual_cases_ok}}). H7 is **{{H7}}**.
- **E** · removing the recheck and scope gates let {{e.gov-minus-acl-scope.invalid_units}} invalid units back in; no single control added to naive matched governed (H17: **{{H17}}**). Negative control without the recheck: I1 **{{inv.nc-minus-recheck.I1}}** (H16: **{{H16}}**).
- **D2** · on held-out claim–citation pairs written blind to it, the lexical verifier agreed with the label on {{d2.heldout.verifier.agree}} of {{d2.heldout.verifier.n}}; a model judge ({{run.judge_model}}) on {{d2.heldout.judge.agree}} of {{d2.heldout.judge.n}}.
- Governed invariants holding: **{{inv.governed.holding}} of {{inv.governed.total}}** (I4 fails on {{inv.governed.I4.failing}}, I6 on {{inv.governed.I6.failing}}: needed evidence admitted and then dropped by the packer, and on H-K8 a qualifier never retrieved).
- Hypotheses: H1 {{H1}} · H2 {{H2}} · H3 {{H3}} · H4 {{H4}} · H5 {{H5}} · H6 {{H6}} · H7 {{H7}} · H8 {{H8}} · H9 {{H9}} · H10 {{H10}} · H11 {{H11}} · H12 {{H12}} · H13 {{H13}} · H14 {{H14}} · H15 {{H15}} · H16 {{H16}} · H17 {{H17}}.

## What this proves, and what it does not

**Proves, on this synthetic estate and this run:**

- On identical candidates, deterministic admission outside the model removed every labelled-invalid and unreadable unit
  without losing needed evidence (B; H5 {{H5}}, H6 {{H6}}).
- Each control closes its own class of failure, and no single control is enough (E; H15 {{H15}}, H17 {{H17}}).
- Without the recheck at the source, revoked and withdrawn content returns to the context (negative control; H16 {{H16}}).
- End to end, the governed pipeline gave more correct answers, leaked nothing, and no forbidden action survived binding
  (D; H8 {{H8}}, H11 {{H11}}, H12 {{H12}}).

**Does not prove:**

- that governed retrieval is more accurate in general: one synthetic estate written by the author, {{d.cases}} held-out
  cases, one primary local model;
- that the assembler beats truncation: on qualifiers it lost (H7 {{H7}});
- that governance is free: it refused more answerable questions (H10 {{H10}});
- that the lexical verifier is reliable on its own (H14 {{H14}});
- anything about a real identity provider, document store, CMDB or release system, all simulated here.

The technical edition, §25, lists the threats to validity; §19 lists everything that failed or was qualified.

## The cases

Forty cases, each a principal, an environment and a question, and nothing else: eighteen development cases (`cases/dev.yaml`),
the only ones used while building, and {{d.cases}} held-out cases (`cases/heldout.yaml`), run once after the freeze. The expected
outcomes are in `groundtruth/labels.yaml`, which only the scorer reads.

| Type | Failure injected on purpose | Held-out |
|---|---|---|
| K0 | none (clean control) | H-K0 |
| K1 | a similar runbook for another service | H-K1 |
| K2 | an exact identifier next to a near-identical one | H-K2 |
| K3 | a stale version ranked high | H-K3 |
| K4 | attractive evidence from another tenant | H-K4 |
| K5 | staging evidence competing with production | H-K5 |
| K6 | lower-authority sources contradicting the runbook of record | H-K6 |
| K7 | an unresolved conflict between two owners' runbooks | H-K7 |
| K8 | a qualifier the budget is likely to cut, joined with a record field | H-K8 |
| K9 | four sources needed at once: INC-4917 | H-K9 |
| K10 | history cited as the approved fix | H-K10 |
| K11 | the answer only in a document the asker cannot read | H-K11 |
| K12 | withdrawn, narrowed and superseded after the watermark | H-K12, H-K12b, H-K12c |
| K13 | a poisoned page with an instruction aimed at the model | H-K13 |
| K14 | insufficient evidence | H-K14, H-K14b |
| K15 | the newest document is not the authority | H-K15 |
| P | positive controls: an authorized responder, the other tenant reading its own runbook, a staging question | H-P1, H-P2, H-P3 |

## The experiments

| ID | Question | The only variable | Model |
|---|---|---|---|
| A | Does the needed evidence reach the candidates? | vector · BM25 · hybrid; the structured route for exact facts | none |
| B | Does admission keep invalid evidence out without losing needed evidence? | everything admitted vs the governed gates, on the same frozen candidates | none |
| C | Does packing keep needed units and qualifiers? | truncation vs the assembler at 300, 450, 600, 900 tokens | none |
| D | Correct, supported answers end to end? | the naive vs the governed pipeline | {{run.model}}, {{d.seeds}} seeds; {{run.sens_model}}, one seed |
| D2 | Can a deterministic verifier tell supported citations from unsupported ones? | lexical verifier vs a model judge | {{run.judge_model}} as judge |
| E | What does each control contribute? | one control removed from governed, or added to naive | none; remove-one also live, one seed |
| NC | Can the invariants fail? | the recheck at the source removed | none, and live on one seed |

Seventeen hypotheses with mechanical tests are in `experiments/preregistration.toml`, frozen with the code, corpus and labels
(`experiments/FROZEN.sha256`); `s2_eval/hypotheses.py` computes every verdict from `facts.json`. Changes after the freeze go to
`experiments/DEVIATIONS.md`, beside the as-recorded numbers.

## Scoring

The scorer (`s2_eval/score.py`) is the only module that reads the labels. Per answer it checks the status and action against the
allowed ones, the approval requirement, the target where a version matters, completeness by fact patterns, canaries
(leakage is a string match, not a judgement), forbidden actions, and every citation against the packet. An answer is
*correct* only if status, action, approval and target all match and it leaks nothing. The scorer's own defect found after the run (typographic
characters, post-hoc re-score in `runs/{{run.id}}-exploratory/`) changed no correctness or leakage result.

## Tests

`make test` runs {{tests.total}} tests in {{tests.files}} files, no model: {{tests.passed}} passed, {{tests.failed}} failed in the
recorded run (`verification/pytest.txt`). `test_isolation.py` ({{tests.file.test_isolation}}) fails if the system under test
imports the evaluator or names the labels; `test_gates.py` ({{tests.file.test_gates}}), `test_packer.py`
({{tests.file.test_packer}}), `test_verify.py` ({{tests.file.test_verify}}), `test_retrieve.py` ({{tests.file.test_retrieve}}),
`test_world.py` ({{tests.file.test_world}}), `test_ingest.py` ({{tests.file.test_ingest}}), `test_pipeline.py`
({{tests.file.test_pipeline}}) and `test_scorer.py` ({{tests.file.test_scorer}}) cover each stage.

## How the evidence maps to the article

| Article claim | Where the proof is |
|---|---|
| every claim, its experiment, hypothesis and facts | `research/claims.toml` → `research/claims-matrix.md`; the Evidence Check page in `results/` |
| a number in either edition | `runs/{{run.id}}/facts.json` (value and source); post-hoc numbers in `docs/derived-facts.json` |
| a case, stage by stage | `uv run python -m s2_eval.cli explain <case>` |
| the headline numbers, recomputed independently | `verification/evidence-check.txt` ({{evcheck.pass}} pass, {{evcheck.fail}} fail: governed invariants, a true result) |
| nothing changed after the freeze | `verification/frozen-check.txt` ({{frozen.unchanged}} of {{frozen.files}} files) |
| the model outputs are the recorded ones | `verification/replay-check.txt` ({{replay.verdict}}, {{replay.model_calls_from_tape}} calls from tape) |

## Architecture

```text
 question + authenticated principal (identity from the envelope, never from the question)
      │
      ▼
 query.analyze_query ── service, tenant, environment, identifiers, task (rules, no model)
      │
      ├── retrieve.Retriever   index copy at the 02:00 watermark: BM25 + nomic-embed-text vectors, RRF (k 60)
      │                        behind the index ACL pre-filter (an optimisation, not the decision)
      └── world.Cmdb / Deployments   systems of record, queried live: CMDB record, deploys in the last 72 h
      │
      ▼
 gates.admit   recheck at the source (ACL, status, supersession at as_of; fail closed; fetch the current version)
               → scope (tenant, environment, service + CMDB dependencies) → lifecycle → authority (runbook of record,
               history only when asked, advisory only when the authority is silent) → conflict (outranked vs unresolved)
      │
      ▼
 packer.assembler   evidence packet: prelude (request context, conflicts, gaps, left-out counts) + items with
                    provenance; qualifiers bound, identical content once, breadth first by role, whole units, budget
      │
      ▼
 generate.ModelClient   Ollama structured output (contracts.ANSWER_SCHEMA), recorded to a tape; replay needs no model
      │
      ▼
 verify.bind   every material claim: cited id in context · quote verbatim · anchors · action polarity · authority
               for the claim kind → unsupported claims removed; an action survives only if a supported claim cites
               a runbook that prescribes it; an approval may be added, never dropped; conflict → escalate
```

| Module | Role |
|---|---|
| `knowledge_rag/world.py` | the simulated enterprise: sources and their ACLs and versions at any instant, CMDB, deployments, identity |
| `knowledge_rag/ingest.py` · `embed.py` | sections with lineage (`doc@version#section`, hash, span, ACL as indexed) · embeddings on a tape |
| `knowledge_rag/retrieve.py` · `query.py` | BM25, vector, hybrid RRF · rule-based query analysis |
| `knowledge_rag/gates.py` | the recheck at the source and the four gates |
| `knowledge_rag/packer.py` · `contracts.py` | naive truncation, relevance packing, the assembler · request, packet and answer contracts |
| `knowledge_rag/generate.py` · `verify.py` | model client (live, replay, scripted surrogate for tests) · citation verifier and binding |
| `knowledge_rag/pipeline.py` · `capability.py` | the naive and governed pipelines and every ablation · the capability behind a headless request |
| `s2_eval/` | cases, scorer (the only reader of the labels), experiments A–E and D2, analysis, hypotheses, freeze, run and replay, independent evidence check, CLI |

`tests/test_isolation.py` parses every module of `knowledge_rag/` and fails on an import of `s2_eval` or any string
naming the labels.

## Prerequisites

- macOS or Linux, Python 3.12 and [uv](https://docs.astral.sh/uv/). Dependencies: pydantic, PyYAML (pytest for tests).
- For a **new** recording only: [Ollama](https://ollama.com) with `gpt-oss:20b`, `qwen3:8b` and `nomic-embed-text`
  pulled. Everything else runs from the recorded tapes without a model.
- For figures and PDFs: Google Chrome (headless).

## Run

From the package root (`context_eng_rag/`):

```bash
make setup               # uv sync
make test                # isolation, world, ingest, retrieval, gates, packer, verifier, pipeline, scorer (no model)
make demo                # INC-4917 through both pipelines, from the published tape (no model)
make freeze-check        # every frozen input unchanged since the freeze
make verify              # freeze check + independent recomputation of the headline numbers + replay + tests
make replay              # re-execute every experiment from the tapes and compare every rows file byte for byte
make exploratory         # POST-HOC: assembler variants and the typography re-score (not preregistered)
make record ID=<new-id> SPLIT=heldout   # a new recording (needs Ollama)
```

One recorded case, every stage:

```bash
cd enterprise_knowledge_rag_poc
uv run python -m s2_eval.cli explain H-K12b          # ACL narrowed after the watermark
uv run python -m s2_eval.cli explain H-P1 --seed 17  # the positive control the packer failed
```

Your own question, live (needs Ollama; recorded to `runs/ask/tape/`):

```bash
uv run python -m s2_eval.cli ask "orders-db connections are saturated, what should I do?" --as ananya.iyer
```

## What a run contains

`runs/{{run.id}}/`: `manifest.json` (split, mode, models and Ollama digests, sha256 of every frozen input), one rows
file per experiment (`a.jsonl` … `e_live.jsonl`, `d2.jsonl`), `invariants.json`, `facts.json` (every number the
editions quote, with its source), `timings.jsonl` (wall clock, never compared), `tape/` (query embeddings, every model
exchange) and `SHA256SUMS`. Post-hoc analyses live beside it in `runs/{{run.id}}-exploratory/` and are labelled so.

## What is simulated

Everything the pipelines talk to: the identity provider, the document stores and their permission APIs, the index
connector, the release system and the CMDB. The corpus is synthetic and labelled so; there is no real enterprise data,
no credential, and no vendor claim. The agent never executes an action: a recommendation such as a rollback is text a
person decides on. The models are local (Ollama); nothing calls a hosted API.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `make record` fails with a connection error | Ollama is not running: `ollama serve`, then `ollama pull gpt-oss:20b qwen3:8b nomic-embed-text` |
| a new recording differs from the published one | the run's `manifest.json` records each model's Ollama digest; a different model build is a new run under a new id, never a replacement of the published one |
| `make replay` reports a different file | a code or config change since the run; `make freeze-check` names the changed frozen input |
| `make docs` fails with `unknown fact` | a document names a fact the published run does not have; fix the key, never type the number |
| `make docs` fails on a missing figure | run `make figures export` first; the build is strict and never publishes a placeholder |
| PDFs are not produced | Google Chrome is required for headless rendering |
| `ask` answers differently from the editions | live answers are new samples; the editions quote the recorded run only |
