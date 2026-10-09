# S1 · Memory, Context & State · Results

*What should an agent remember, what should expire, and what is authoritative?*

Production AI Engineering · S1 · State & Knowledge

## The run

- **Published run:** `2026-09-18-recorded` (declared in `tools/fill_article.py (ARTICLE_RUN)`)
- **How it ran:** recorded with a live local model
- **Numbers come from:** `memory-context-state-poc/runs/2026-09-18-recorded/summary.json`

## Two verdicts, kept apart

- **Evidence integrity:** not recorded as a separate verdict. Run the verify command below.
- **Findings:** 10 of 10 invariants hold. Source: `memory-context-state-poc/runs/2026-09-18-recorded/summary.json`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `m0_runbook_rank` | **10** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m9_naive_proceeded` | **5** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m9_runs` | **5** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m0_top5_invalid` | **3** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m0_top5_total` | **5** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `naive_invalid_total` | **13** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `governed_invalid_total` | **0** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m0_naive_recall` | **5/8** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m0_gov_recall` | **8/8** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m9_gov_waited` | **5** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `invariants` | **10/10** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `k5_runbook_present` | **1** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `rows_total` | **10** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m6a_events` | **4** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m6a_naive_persisted` | **4** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m6a_gov_persisted` | **2** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m6b_naive_invalid` | **3** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m6b_gov_invalid` | **0** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `embedding_model` | **nomic-embed-text** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `candidates_n` | **20** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `model` | **gpt-oss:20b** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `decisions_total` | **100** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m8_naive_recall` | **2/7** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `m8_gov_recall` | **5/7** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `forbidden_naive` | **0** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `forbidden_gov` | **0** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |
| `M8_n_correct` | **5/5** | `article/article-numbers.flat.json (from runs/2026-09-18-recorded/summary.json)` |

## The checks

Source: `memory-context-state-poc/runs/2026-09-18-recorded/summary.json`. PASS: 28

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `M0` | governed | budget respected | PASS | Combined hero scenario |
| `M0` | governed | no invalid admitted | PASS | Combined hero scenario |
| `M0` | governed | runbook admitted | PASS | Combined hero scenario |
| `M1` | governed | budget respected | PASS | Correct, relevant memory |
| `M1` | governed | useful memory recalled | PASS | Correct, relevant memory |
| `M2` | governed | budget respected | PASS | Expired memory |
| `M2` | governed | no expired admitted | PASS | Expired memory |
| `M3` | governed | budget respected | PASS | Wrong tenant |
| `M3` | governed | no wrong tenant admitted | PASS | Wrong tenant |
| `M4` | governed | budget respected | PASS | Wrong environment |
| `M4` | governed | no wrong environment admitted | PASS | Wrong environment |
| `M5` | governed | budget respected | PASS | Episode vs authoritative runbook |
| `M5` | governed | runbook admitted | PASS | Episode vs authoritative runbook |
| `M5` | governed | episode not in evidence | PASS | Episode vs authoritative runbook |
| `M5` | governed | episode marked contradicted | PASS | Episode vs authoritative runbook |
| `M7` | governed | budget respected | PASS | Superseded memory |
| `M7` | governed | no superseded admitted | PASS | Superseded memory |
| `M7` | governed | replacement admitted | PASS | Superseded memory |
| `M8` | governed | budget respected | PASS | More valid evidence than budget |
| `M8` | governed | authoritative first | PASS | More valid evidence than budget |
| `M9` | governed | budget respected | PASS | Workflow state is not memory |
| `M9` | governed | no workflow claim admitted | PASS | Workflow state is not memory |
| `M6B` | governed | budget respected | PASS | M6B |
| `M6B` | governed | assertion contextual only | PASS | M6B |
| `M6B` | governed | assertion session scoped | PASS | M6B |
| `M6B` | governed | assertion not in later context | PASS | M6B |
| `M6B` | governed | unverified tool not persisted | PASS | M6B |
| `M6B` | governed | speculation not persisted | PASS | M6B |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python via uv, from uv.lock)
make test    # the POC's tests and its layer contracts (no model)
make verify    # frozen inputs unchanged (s1 check), then the tests; reads the published run, never writes it
make replay    # the published run replayed from its tape in a throwaway copy of the POC (the published run is not written)
make demo    # no single-scenario demo here: make replay replays the published run from its tape
make docs    # the technical edition as standalone HTML and PDF, then the uniform series pages
make qa    # the Medium edition's checks: what Medium cannot show, relative links, stale wording
```

## More detail

- [The technical deep dive (PDF)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/memory_context_state_poc/memory-context-state-poc/docs/S1-technical-reference.pdf)

*Built by `series-start-here/tools/series_edition.py results S1` from the files named above. It computes nothing new.*
