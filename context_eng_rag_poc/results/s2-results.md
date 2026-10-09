# S2 · Enterprise Knowledge & RAG · Results

*How does an agent retrieve valid enterprise evidence without dumping the company into the prompt?*

Production AI Engineering · S2 · State & Knowledge

## The run

- **Published run:** `2026-10-08-heldout` (declared in `enterprise_knowledge_rag_poc/runs/PUBLISHED`)
- **How it ran:** live local model on the held-out split
- **Numbers come from:** `enterprise_knowledge_rag_poc/runs/2026-10-08-heldout/facts.json`

## Two verdicts, kept apart

- **Evidence integrity:** VERIFIED. frozen inputs: FROZEN CHECK OK (41 of 41 files unchanged); replay: REPLAY IDENTICAL. Source: `verification/frozen-check.txt, verification/replay-check.txt`
- **Findings:** 17 preregistered hypotheses: 13 SUPPORTED, 4 NOT SUPPORTED; the evidence check's 1 FAIL line(s) report a finding (governed-arm invariants I4, I6 do not hold), not an integrity failure. Source: `enterprise_knowledge_rag_poc/runs/2026-10-08-heldout/facts.json (H1–H17)`

## Every number in the Medium edition

| Key | Value | Source |
|---|---|---|
| `d.cases` | **22** | `d.jsonl` |
| `b.naive.invalid_units` | **56** | `b.jsonl: labelled-invalid units in the packed context` |
| `b.governed.invalid_units` | **0** | `b.jsonl: labelled-invalid units in the packed context` |
| `d.naive.correct` | **31** | `d.jsonl: arm naive, final answer` |
| `d.naive.runs` | **66** | `d.jsonl: arm naive, final answer` |
| `d.governed.correct` | **44** | `d.jsonl: arm governed, final answer` |
| `d.naive.leak_runs` | **6** | `d.jsonl: arm naive, final answer` |
| `d.governed.leak_runs` | **0** | `d.jsonl: arm governed, final answer` |
| `d.naive.false_abst` | **3** | `d.jsonl: arm naive, final answer` |
| `d.naive.answerable_runs` | **51** | `d.jsonl: arm naive, final answer` |
| `d.governed.false_abst` | **6** | `d.jsonl: arm governed, final answer` |
| `hyp.not_supported` | **4** | `count of the verdicts above` |
| `hyp.total` | **17** | `experiments/preregistration.toml` |
| `flag.needed_total` | **4** | `d.jsonl: H-K9, seed 7` |
| `a.cases` | **18** | `a.jsonl: cases with at least one needed index unit` |
| `a.hybrid.mrr10` | **0.61** | `a.jsonl: mean reciprocal rank of the first needed unit, top 10 (2 decimals)` |
| `a.vector.mrr10` | **0.49** | `a.jsonl: mean reciprocal rank of the first needed unit, top 10 (2 decimals)` |
| `a.hybrid.recall20` | **87.5** | `a.jsonl: macro mean Recall@20, %` |
| `a.vector.recall20` | **77.7778** | `a.jsonl: macro mean Recall@20, %` |
| `a.vector.invalid_top5_cases` | **19** | `a.jsonl: trap cases with a labelled-invalid unit in the top 5` |
| `a.trap_cases` | **22** | `a.jsonl: cases with at least one labelled-invalid unit` |
| `a.hybrid.invalid_top5_cases` | **19** | `a.jsonl: trap cases with a labelled-invalid unit in the top 5` |
| `a.ident.hybrid.full10` | **1** | `a.jsonl: identifier cases with every needed unit in the top 10` |
| `a.ident.cases` | **2** | `a.jsonl: cases whose question names a version or a document id` |
| `a2.route` | **9** | `a.jsonl: needed records the structured route returned` |
| `a2.records` | **9** | `a.jsonl` |
| `a2.prose.hybrid` | **0** | `a.jsonl: needed records whose exact fields appear together in one top-20 prose unit` |
| `b.cases` | **22** | `b.jsonl` |
| `b.needed_in_pool` | **32** | `b.jsonl: needed units present in the frozen pool` |
| `b.naive.unauthorized_units` | **15** | `b.jsonl: units the principal cannot read at as_of` |
| `b.naive.cross_tenant_units` | **16** | `b.jsonl` |
| `b.naive.class.superseded` | **11** | `b.jsonl` |
| `b.governed.needed_in_context` | **32** | `b.jsonl` |
| `b.naive.needed_in_context` | **24** | `b.jsonl` |
| `d.governed.abst_ok` | **15** | `d.jsonl: arm governed, final answer` |
| `d.governed.abst_runs` | **15** | `d.jsonl: arm governed, final answer` |
| `d.naive.abst_ok` | **8** | `d.jsonl: arm naive, final answer` |
| `c.600.assembler.needed_covered` | **36** | `c.jsonl: needed units fully present in the context` |
| `c.600.truncate.needed_covered` | **34** | `c.jsonl: needed units fully present in the context` |
| `c.600.assembler.qual_cases_ok` | **8** | `c.jsonl` |
| `c.600.truncate.qual_cases_ok` | **9** | `c.jsonl` |
| `d.naive.invalid_support` | **49** | `d.jsonl: arm naive, final answer` |
| `d2.heldout.verifier.n` | **40** | `d2.jsonl` |
| `d2.heldout.verifier.agree` | **30** | `d2.jsonl` |
| `run.judge_model` | **qwen3:8b** | `manifest.json` |
| `d2.heldout.judge.agree` | **33** | `d2.jsonl` |
| `run.model` | **gpt-oss:20b** | `manifest.json` |
| `d.governed.forbidden_action_runs` | **0** | `d.jsonl: arm governed, final answer` |
| `d.naive.forbidden_action_runs` | **14** | `d.jsonl: arm naive, final answer` |
| `d.governed.runs` | **66** | `d.jsonl: arm governed, final answer` |
| `d.seeds` | **3** | `d.jsonl` |
| `e.needed_total` | **46** | `e_evidence.jsonl` |
| `e.gov-minus-acl-scope.invalid_units` | **12** | `e_evidence.jsonl` |
| `e.gov-minus-acl-scope.unauthorized_units` | **4** | `e_evidence.jsonl` |
| `e.gov-minus-lifecycle-authority.invalid_units` | **5** | `e_evidence.jsonl` |
| `e.naive-plus-acl-scope.invalid_units` | **25** | `e_evidence.jsonl` |
| `e.naive-plus-lifecycle-authority.invalid_units` | **17** | `e_evidence.jsonl` |
| `el.gov-minus-structured.correct` | **18** | `e_live.jsonl` |
| `el.governed.correct` | **16** | `d.jsonl: arm governed, seed 7 (the ablation seed), bound answer` |
| `el.gov-minus-verify.correct` | **16** | `e_live.jsonl` |
| `el.gov-minus-verify.forbidden_action_runs` | **2** | `e_live.jsonl` |
| `el.naive-plus-verify.false_abst` | **7** | `e_live.jsonl` |
| `el.naive-plus-verify.leak_runs` | **2** | `e_live.jsonl` |
| `hyp.supported` | **13** | `count of the verdicts above` |
| `hyp.not_supported.list` | **H2, H7, H10, H14** | `the verdicts above` |
| `flag.gov.correct_runs` | **0** | `d.jsonl: H-K9, all seeds` |
| `flag.runs` | **3** | `d.jsonl: H-K9, all seeds` |
| `flag.naive.correct_runs` | **0** | `d.jsonl: H-K9, all seeds` |
| `d.governed_raw.forbidden_action_runs` | **6** | `d.jsonl: arm governed, raw answer` |
| `x.typo.d.governed.complete_old` | **21** | `runs/2026-10-08-heldout-exploratory/d_rescore_typography.json (POST-HOC, EXPLORATORY)` |
| `x.typo.d.governed.complete_new` | **29** | `runs/2026-10-08-heldout-exploratory/d_rescore_typography.json (POST-HOC, EXPLORATORY)` |
| `x.typo.d.governed.facts_runs` | **60** | `runs/2026-10-08-heldout-exploratory/d_rescore_typography.json (POST-HOC, EXPLORATORY)` |
| `run.sens_model` | **qwen3:8b** | `manifest.json` |
| `ds.governed.correct` | **17** | `d_sensitivity.jsonl: arm governed, final answer` |
| `ds.naive.correct` | **10** | `d_sensitivity.jsonl: arm naive, final answer` |
| `run.id` | **2026-10-08-heldout** | `manifest.json (a replay keeps the id of the run it replays)` |

## The checks

Source: `verification/evidence-check.txt`. PASS: 12, FAIL: 1

| Id | Experiment / arm | What | Status | Finding / detail |
|---|---|---|---|---|
| `1` |  | SHA256SUMS: every recorded file unchanged      got 0  expected 0 | PASS |  |
| `2` |  | B naive: labelled-invalid units in context     got 56  expected 56 | PASS |  |
| `3` |  | B governed: labelled-invalid units in context  got 0  expected 0 | PASS |  |
| `4` |  | B governed: needed units kept                  got 32  expected 32 | PASS |  |
| `5` |  | D naive: correct runs                          got 31  expected 31 | PASS |  |
| `6` |  | D governed: correct runs                       got 44  expected 44 | PASS |  |
| `7` |  | D governed_raw: correct runs                   got 44  expected 44 | PASS |  |
| `8` |  | D naive: runs with a canary in the answer      got 6  expected 6 | PASS |  |
| `9` |  | D governed: runs with a canary in the answer   got 0  expected 0 | PASS |  |
| `10` |  | D2 verifier: agreement with the gold labels    got 30  expected 30 | PASS |  |
| `11` |  | D2 judge: agreement with the gold labels       got 33  expected 33 | PASS |  |
| `12` |  | governed invariants all hold                   got 4  expected 6 | FAIL |  |
| `13` |  | negative control fails I1 or I3 (must fail)    got I1 fails, I3 fails  expected at least one fails | PASS |  |

## Re-run it yourself

From the chapter folder. None of these commands changes the published run; `make verify` and `make test` write their own reports (the verification files), which is how they report.

```bash
make setup    # the POC environment (Python 3.12 via uv; pytest)
make test    # unit, integration and regression tests (no model, no Ollama) -> verification/pytest.*
make verify    # frozen inputs, an independent recomputation of the headline numbers, replay, tests -> verification/
make replay    # replay the published run from its tapes into runs/<run>-replay and compare byte for byte (no model)
make demo    # INC-4917 through the naive and the governed pipeline, from the published tape (no model)
make docs    # both editions and the run report as Markdown, standalone HTML and PDF
make qa    # rendered checks of the pages at desktop, tablet and mobile widths -> qa/
```

## More detail

- [The technical deep dive (PDF)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/context_eng_rag_poc/technical/enterprise-knowledge-rag-technical.pdf)
- [Evidence](https://github.com/ereshzealous/ai_blogs_poc/blob/main/context_eng_rag_poc/results/enterprise-knowledge-rag-evidence.md)
- [Report](https://github.com/ereshzealous/ai_blogs_poc/blob/main/context_eng_rag_poc/results/enterprise-knowledge-rag-report.md)
- [Real vs simulated](https://github.com/ereshzealous/ai_blogs_poc/blob/main/context_eng_rag_poc/results/enterprise-knowledge-rag-real-vs-simulated.md)

*Built by `series-start-here/tools/series_edition.py results S2` from the files named above. It computes nothing new.*
