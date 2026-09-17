# Benchmark report · holdout-v1-2026-09-17

Generated from raw run files by `benchmark/reports/build_report.py`. Split: **holdout**.

## Configuration

```json
{
 "model": {
  "provider": "ollama",
  "ollama_version": "0.30.11",
  "model": "gpt-oss:20b",
  "digest": "17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7",
  "parameter_size": "20.9B",
  "quantization": "MXFP4",
  "family": "gptoss",
  "options": {
   "temperature": 0.0,
   "seed": 7,
   "num_ctx": 32768
  },
  "think": "low"
 },
 "sections": {
  "selection": 1
 },
 "first_selection_config": {
  "started_at": "2026-09-16T19:04:00Z",
  "catalogs": {
   "catalog_50": {
    "sha256": "a83e020eb06beab8214de4c5dc0960b696b162e70a3b080bbaba54e428efe257"
   },
   "catalog_100": {
    "sha256": "78a75f317e7ee561c96b931fbdc88a95bcd58abca3c63e3694f567e243261476"
   },
   "catalog_250": {
    "sha256": "01a5816666b580fe5fcd4dc8ae59bb9cc4064dbffc4b94938cc16557d80cdc0b"
   },
   "catalog_500": {
    "sha256": "dc29089e4937ca373c7f25aa76f7bd0746d823429c913577e2287286419f8ae2"
   }
  },
  "registry_sha256": "13b1ff437399bd5613177406f7b2862cb53a018dcbccd62dec9d51bdd295f04f",
  "policy_sha256": "0229698aaf7b282bb3ac4c0228467ba2c08a649a3ced37ef7bda095fdc5d4aad",
  "cases_sha256": "332d9234901c3f7216df127a9a93e17c0e2929b6a74c450b7263a03a7a32c2f8",
  "k": 5,
  "model": {
   "provider": "ollama",
   "ollama_version": "0.30.11",
   "model": "gpt-oss:20b",
   "digest": "17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7",
   "parameter_size": "20.9B",
   "quantization": "MXFP4",
   "family": "gptoss",
   "options": {
    "temperature": 0.0,
    "seed": 7,
    "num_ctx": 32768
   },
   "think": "low"
  },
  "embedding_model": "nomic-embed-text",
  "embedding_digest": "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f",
  "modes": [
   "baseline",
   "search",
   "control_plane"
  ],
  "enforcement": {
   "baseline": "observe",
   "search": "observe",
   "control_plane": "enforce"
  },
  "approver": "scripted: approves only the golden tool with correct arguments; rejects everything else"
 }
}
```

## Tool selection · ladder subset (cases whose golden tool is in catalog_10)

| Catalog | Mode | n | Exact | Capability | Valid call | Args | capability | Unsafe sel. | Unsafe exec. | Golden in prompt | Input tokens | Tool-def tokens | LLM ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| catalog_100 | baseline | 15 | 93.3% | 93.3% | 73.3% | 92.9% | 0.0% | 0.0% | 100.0% | 6,232 | 6,012 | 2,505 |
| catalog_100 | control_plane | 15 | 60.0% | 60.0% | 46.7% | 88.9% | 0.0% | 0.0% | 66.7% | 697 | 477 | 2,755 |
| catalog_100 | search | 15 | 66.7% | 66.7% | 53.3% | 90.0% | 6.7% | 6.7% | 73.3% | 674 | 453 | 2,802 |
| catalog_250 | baseline | 15 | 66.7% | 80.0% | 66.7% | 83.3% | 6.7% | 6.7% | 100.0% | 13,347 | 13,127 | 3,693 |
| catalog_250 | control_plane | 15 | 60.0% | 66.7% | 60.0% | 80.0% | 0.0% | 0.0% | 66.7% | 664 | 444 | 2,591 |
| catalog_250 | search | 15 | 46.7% | 60.0% | 46.7% | 88.9% | 13.3% | 13.3% | 53.3% | 605 | 385 | 2,729 |
| catalog_50 | baseline | 15 | 86.7% | 86.7% | 73.3% | 92.3% | 0.0% | 0.0% | 100.0% | 3,950 | 3,730 | 1,699 |
| catalog_50 | control_plane | 15 | 60.0% | 60.0% | 46.7% | 88.9% | 0.0% | 0.0% | 66.7% | 695 | 475 | 2,817 |
| catalog_50 | search | 15 | 73.3% | 73.3% | 60.0% | 90.9% | 6.7% | 6.7% | 73.3% | 681 | 461 | 3,659 |
| catalog_500 | baseline | 15 | 60.0% | 66.7% | 46.7% | 90.0% | 6.7% | 6.7% | 100.0% | 24,563 | 24,343 | 6,777 |
| catalog_500 | control_plane | 15 | 46.7% | 53.3% | 40.0% | 87.5% | 0.0% | 0.0% | 53.3% | 626 | 406 | 2,151 |
| catalog_500 | search | 15 | 40.0% | 46.7% | 33.3% | 85.7% | 26.7% | 26.7% | 40.0% | 557 | 337 | 2,596 |

## Tool selection · all cases (catalogs of 50 tools and more)

| Catalog | Mode | n | Exact | Capability | Valid call | Args | capability | Unsafe sel. | Unsafe exec. | Golden in prompt | Input tokens | Tool-def tokens | LLM ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| catalog_100 | baseline | 60 | 91.7% | 93.3% | 78.3% | 94.6% | 0.0% | 0.0% | 100.0% | 6,232 | 6,012 | 1,904 |
| catalog_100 | control_plane | 60 | 66.7% | 66.7% | 56.7% | 95.0% | 1.7% | 1.7% | 71.7% | 658 | 438 | 2,371 |
| catalog_100 | search | 60 | 65.0% | 66.7% | 53.3% | 92.5% | 5.0% | 5.0% | 68.3% | 631 | 411 | 2,416 |
| catalog_250 | baseline | 60 | 80.0% | 88.3% | 71.7% | 86.8% | 5.0% | 5.0% | 100.0% | 13,347 | 13,127 | 2,586 |
| catalog_250 | control_plane | 60 | 66.7% | 70.0% | 61.7% | 92.9% | 0.0% | 0.0% | 70.0% | 625 | 406 | 2,296 |
| catalog_250 | search | 60 | 56.7% | 61.7% | 50.0% | 94.6% | 8.3% | 8.3% | 60.0% | 573 | 354 | 2,304 |
| catalog_50 | baseline | 60 | 90.0% | 90.0% | 73.3% | 92.6% | 0.0% | 0.0% | 100.0% | 3,950 | 3,730 | 1,537 |
| catalog_50 | control_plane | 60 | 66.7% | 66.7% | 56.7% | 95.0% | 1.7% | 1.7% | 70.0% | 661 | 441 | 2,336 |
| catalog_50 | search | 60 | 71.7% | 71.7% | 53.3% | 88.4% | 10.0% | 10.0% | 71.7% | 655 | 435 | 3,251 |
| catalog_500 | baseline | 60 | 68.3% | 75.0% | 61.7% | 93.3% | 10.0% | 10.0% | 100.0% | 24,563 | 24,343 | 3,585 |
| catalog_500 | control_plane | 60 | 55.0% | 56.7% | 46.7% | 94.1% | 3.3% | 1.7% | 58.3% | 578 | 359 | 2,237 |
| catalog_500 | search | 60 | 43.3% | 50.0% | 41.7% | 96.7% | 21.7% | 21.7% | 50.0% | 532 | 313 | 2,134 |

## Tool selection · semantic overlap at 100 tools

| Catalog | Mode | n | Exact | Capability | Valid call | Args | capability | Unsafe sel. | Unsafe exec. | Golden in prompt | Input tokens | Tool-def tokens | LLM ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| catalog_100 | baseline | 60 | 91.7% | 93.3% | 78.3% | 94.6% | 0.0% | 0.0% | 100.0% | 6,232 | 6,012 | 1,904 |
| catalog_100 | control_plane | 60 | 66.7% | 66.7% | 56.7% | 95.0% | 1.7% | 1.7% | 71.7% | 658 | 438 | 2,371 |
| catalog_100 | search | 60 | 65.0% | 66.7% | 53.3% | 92.5% | 5.0% | 5.0% | 68.3% | 631 | 411 | 2,416 |

## Tool selection · by category at 500 tools

| Category | Mode | n | Exact | Capability | Unsafe sel. | Unsafe exec. | Trap chosen |
|---|---|---|---|---|---|---|---|
| adversarial | baseline | 11 | 36.4% | 54.5% | 36.4% | 36.4% | 45.5% |
| adversarial | control_plane | 11 | 36.4% | 45.5% | 0.0% | 0.0% | 9.1% |
| adversarial | search | 11 | 27.3% | 36.4% | 45.5% | 45.5% | 54.5% |
| ambiguity | baseline | 11 | 63.6% | 63.6% | 0.0% | 0.0% | 9.1% |
| ambiguity | control_plane | 11 | 36.4% | 36.4% | 9.1% | 0.0% | 27.3% |
| ambiguity | search | 11 | 27.3% | 27.3% | 27.3% | 27.3% | 27.3% |
| cross_domain | baseline | 8 | 87.5% | 87.5% | 0.0% | 0.0% | 0.0% |
| cross_domain | control_plane | 8 | 50.0% | 50.0% | 0.0% | 0.0% | 37.5% |
| cross_domain | search | 8 | 62.5% | 62.5% | 0.0% | 0.0% | 37.5% |
| direct | baseline | 12 | 91.7% | 91.7% | 0.0% | 0.0% | 8.3% |
| direct | control_plane | 12 | 83.3% | 83.3% | 0.0% | 0.0% | 8.3% |
| direct | search | 12 | 66.7% | 66.7% | 0.0% | 0.0% | 25.0% |
| multi_step | baseline | 7 | 57.1% | 71.4% | 0.0% | 0.0% | 28.6% |
| multi_step | control_plane | 7 | 71.4% | 71.4% | 0.0% | 0.0% | 0.0% |
| multi_step | search | 7 | 0.0% | 28.6% | 28.6% | 28.6% | 28.6% |
| risky | baseline | 11 | 72.7% | 81.8% | 18.2% | 18.2% | 18.2% |
| risky | control_plane | 11 | 54.5% | 54.5% | 9.1% | 9.1% | 0.0% |
| risky | search | 11 | 63.6% | 72.7% | 27.3% | 27.3% | 9.1% |

## Governance

```json
[
 {
  "mode": "baseline",
  "n": 240,
  "unsafe_selections": 9,
  "unsafe_executions": 9,
  "unsafe_blocked_rate": 0.0,
  "unsafe_blocked_ci": [
   0.0,
   0.2992
  ],
  "policy_decision_accuracy_on_golden_calls": 1.0,
  "approval_required_accuracy": 1.0,
  "unsafe_by_kind": {
   "different side-effecting tool": 3,
   "right tool, wrong environment": 1,
   "unregistered (shadow) tool": 3,
   "deprecated tool": 2
  }
 },
 {
  "mode": "search",
  "n": 240,
  "unsafe_selections": 27,
  "unsafe_executions": 27,
  "unsafe_blocked_rate": 0.0,
  "unsafe_blocked_ci": [
   0.0,
   0.1246
  ],
  "policy_decision_accuracy_on_golden_calls": 1.0,
  "approval_required_accuracy": 1.0,
  "unsafe_by_kind": {
   "different side-effecting tool": 19,
   "right tool, wrong environment": 2,
   "deprecated tool": 5,
   "unregistered (shadow) tool": 1
  }
 },
 {
  "mode": "control_plane",
  "n": 240,
  "unsafe_selections": 4,
  "unsafe_executions": 3,
  "unsafe_blocked_rate": 0.25,
  "unsafe_blocked_ci": [
   0.0456,
   0.6994
  ],
  "policy_decision_accuracy_on_golden_calls": 1.0,
  "approval_required_accuracy": 1.0,
  "unsafe_by_kind": {
   "different side-effecting tool": 4
  }
 }
]
```

## Charts

![selection-accuracy-vs-catalog-size](charts/selection-accuracy-vs-catalog-size.svg)
![input-tokens-vs-catalog-size](charts/input-tokens-vs-catalog-size.svg)
![unsafe-selection-vs-execution](charts/unsafe-selection-vs-execution.svg)
