# Benchmark report · holdout2-v1-2026-09-17

Generated from raw run files by `benchmark/reports/build_report.py`. Split: **holdout2**.

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
  "selection": 5
 },
 "first_selection_config": {
  "started_at": "2026-09-16T21:47:12Z",
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
  "cases_sha256": "fa577c03d3292d6577dc74b8cfd9760478324a716fb21d99a850a4174225edc6",
  "discovery_code_sha256": "7cc869037b415f0806ad907a63a4c7ee0cd52407113df4c5b6d411aecf989f1a",
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
| catalog_100 | baseline | 31 | 87.1% | 90.3% | 67.7% | 96.4% | 3.2% | 3.2% | 100.0% | 6,235 | 6,012 | 2,592 |
| catalog_100 | control_plane | 31 | 64.5% | 67.7% | 38.7% | 85.7% | 6.5% | 6.5% | 67.7% | 686 | 462 | 3,619 |
| catalog_100 | search | 31 | 54.8% | 58.1% | 38.7% | 88.9% | 16.1% | 16.1% | 58.1% | 647 | 423 | 3,013 |
| catalog_250 | baseline | 31 | 71.0% | 74.2% | 54.8% | 87.0% | 6.5% | 6.5% | 100.0% | 13,350 | 13,127 | 3,645 |
| catalog_250 | control_plane | 31 | 58.1% | 64.5% | 41.9% | 90.0% | 6.5% | 3.2% | 67.7% | 663 | 440 | 3,809 |
| catalog_250 | search | 31 | 45.2% | 51.6% | 35.5% | 87.5% | 12.9% | 12.9% | 51.6% | 594 | 370 | 2,985 |
| catalog_50 | baseline | 31 | 93.5% | 93.5% | 67.7% | 89.7% | 3.2% | 3.2% | 100.0% | 3,953 | 3,730 | 1,903 |
| catalog_50 | control_plane | 31 | 67.7% | 67.7% | 38.7% | 81.0% | 6.5% | 6.5% | 67.7% | 687 | 464 | 3,029 |
| catalog_50 | search | 31 | 74.2% | 74.2% | 45.2% | 82.6% | 12.9% | 12.9% | 77.4% | 689 | 465 | 2,933 |
| catalog_500 | baseline | 31 | 45.2% | 58.1% | 38.7% | 94.4% | 9.7% | 9.7% | 100.0% | 24,566 | 24,343 | 5,415 |
| catalog_500 | control_plane | 31 | 51.6% | 61.3% | 35.5% | 84.2% | 6.5% | 3.2% | 58.1% | 626 | 403 | 5,790 |
| catalog_500 | search | 31 | 32.3% | 35.5% | 22.6% | 90.9% | 25.8% | 25.8% | 41.9% | 564 | 341 | 3,474 |

## Tool selection · all cases (catalogs of 50 tools and more)

| Catalog | Mode | n | Exact | Capability | Valid call | Args | capability | Unsafe sel. | Unsafe exec. | Golden in prompt | Input tokens | Tool-def tokens | LLM ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| catalog_100 | baseline | 100 | 88.0% | 92.0% | 73.0% | 94.6% | 3.0% | 3.0% | 100.0% | 6,233 | 6,012 | 2,293 |
| catalog_100 | control_plane | 100 | 70.0% | 73.0% | 55.0% | 87.7% | 4.0% | 4.0% | 72.0% | 656 | 435 | 3,202 |
| catalog_100 | search | 100 | 75.0% | 79.0% | 60.0% | 87.3% | 5.0% | 5.0% | 79.0% | 627 | 406 | 2,772 |
| catalog_250 | baseline | 100 | 82.0% | 85.0% | 67.0% | 89.4% | 8.0% | 8.0% | 100.0% | 13,348 | 13,127 | 2,898 |
| catalog_250 | control_plane | 100 | 68.0% | 72.0% | 57.0% | 88.9% | 4.0% | 1.0% | 73.0% | 625 | 404 | 3,255 |
| catalog_250 | search | 100 | 68.0% | 74.0% | 58.0% | 87.8% | 7.0% | 7.0% | 73.0% | 573 | 352 | 2,700 |
| catalog_50 | baseline | 100 | 97.0% | 98.0% | 75.0% | 89.8% | 3.0% | 3.0% | 100.0% | 3,951 | 3,730 | 1,727 |
| catalog_50 | control_plane | 100 | 74.0% | 75.0% | 57.0% | 84.0% | 4.0% | 3.0% | 75.0% | 660 | 439 | 3,094 |
| catalog_50 | search | 100 | 84.0% | 85.0% | 64.0% | 85.9% | 6.0% | 6.0% | 87.0% | 658 | 437 | 2,845 |
| catalog_500 | baseline | 100 | 63.0% | 70.0% | 56.0% | 92.9% | 14.0% | 14.0% | 100.0% | 24,564 | 24,343 | 3,916 |
| catalog_500 | control_plane | 100 | 66.0% | 71.0% | 55.0% | 87.3% | 5.0% | 2.0% | 70.0% | 590 | 369 | 5,002 |
| catalog_500 | search | 100 | 50.0% | 58.0% | 48.0% | 93.1% | 17.0% | 17.0% | 61.0% | 537 | 316 | 3,946 |

## Tool selection · semantic overlap at 100 tools

| Catalog | Mode | n | Exact | Capability | Valid call | Args | capability | Unsafe sel. | Unsafe exec. | Golden in prompt | Input tokens | Tool-def tokens | LLM ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| catalog_100 | baseline | 100 | 88.0% | 92.0% | 73.0% | 94.6% | 3.0% | 3.0% | 100.0% | 6,233 | 6,012 | 2,293 |
| catalog_100 | control_plane | 100 | 70.0% | 73.0% | 55.0% | 87.7% | 4.0% | 4.0% | 72.0% | 656 | 435 | 3,202 |
| catalog_100 | search | 100 | 75.0% | 79.0% | 60.0% | 87.3% | 5.0% | 5.0% | 79.0% | 627 | 406 | 2,772 |

## Tool selection · by category at 500 tools

| Category | Mode | n | Exact | Capability | Unsafe sel. | Unsafe exec. | Trap chosen |
|---|---|---|---|---|---|---|---|
| adversarial | baseline | 18 | 33.3% | 38.9% | 44.4% | 44.4% | 55.6% |
| adversarial | control_plane | 18 | 55.6% | 55.6% | 16.7% | 5.6% | 16.7% |
| adversarial | search | 18 | 16.7% | 27.8% | 33.3% | 33.3% | 66.7% |
| ambiguity | baseline | 18 | 66.7% | 77.8% | 0.0% | 0.0% | 16.7% |
| ambiguity | control_plane | 18 | 66.7% | 72.2% | 0.0% | 0.0% | 5.6% |
| ambiguity | search | 18 | 44.4% | 50.0% | 16.7% | 16.7% | 5.6% |
| cross_domain | baseline | 13 | 69.2% | 76.9% | 0.0% | 0.0% | 0.0% |
| cross_domain | control_plane | 13 | 69.2% | 76.9% | 0.0% | 0.0% | 0.0% |
| cross_domain | search | 13 | 46.2% | 53.8% | 7.7% | 7.7% | 15.4% |
| direct | baseline | 20 | 80.0% | 85.0% | 0.0% | 0.0% | 5.0% |
| direct | control_plane | 20 | 90.0% | 95.0% | 0.0% | 0.0% | 0.0% |
| direct | search | 20 | 80.0% | 80.0% | 0.0% | 0.0% | 10.0% |
| multi_step | baseline | 12 | 66.7% | 75.0% | 0.0% | 0.0% | 8.3% |
| multi_step | control_plane | 12 | 66.7% | 75.0% | 8.3% | 0.0% | 16.7% |
| multi_step | search | 12 | 58.3% | 66.7% | 8.3% | 8.3% | 16.7% |
| risky | baseline | 19 | 63.2% | 68.4% | 31.6% | 31.6% | 15.8% |
| risky | control_plane | 19 | 47.4% | 52.6% | 5.3% | 5.3% | 0.0% |
| risky | search | 19 | 52.6% | 68.4% | 31.6% | 31.6% | 21.1% |

## Governance

```json
[
 {
  "mode": "baseline",
  "n": 400,
  "unsafe_selections": 28,
  "unsafe_executions": 28,
  "unsafe_blocked_rate": 0.0,
  "unsafe_blocked_ci": [
   0.0,
   0.1206
  ],
  "policy_decision_accuracy_on_golden_calls": 0.9818,
  "approval_required_accuracy": 1.0,
  "unsafe_by_kind": {
   "right tool, wrong environment": 6,
   "different side-effecting tool": 14,
   "deprecated tool": 4,
   "unregistered (shadow) tool": 4
  }
 },
 {
  "mode": "search",
  "n": 400,
  "unsafe_selections": 35,
  "unsafe_executions": 35,
  "unsafe_blocked_rate": 0.0,
  "unsafe_blocked_ci": [
   0.0,
   0.0989
  ],
  "policy_decision_accuracy_on_golden_calls": 0.9928,
  "approval_required_accuracy": 1.0,
  "unsafe_by_kind": {
   "different side-effecting tool": 22,
   "right tool, wrong environment": 2,
   "deprecated tool": 8,
   "unregistered (shadow) tool": 3
  }
 },
 {
  "mode": "control_plane",
  "n": 400,
  "unsafe_selections": 17,
  "unsafe_executions": 10,
  "unsafe_blocked_rate": 0.4118,
  "unsafe_blocked_ci": [
   0.2161,
   0.6399
  ],
  "policy_decision_accuracy_on_golden_calls": 0.9964,
  "approval_required_accuracy": 1.0,
  "unsafe_by_kind": {
   "different side-effecting tool": 16,
   "right tool, wrong environment": 1
  }
 }
]
```

## Charts

![selection-accuracy-vs-catalog-size](charts/selection-accuracy-vs-catalog-size.svg)
![input-tokens-vs-catalog-size](charts/input-tokens-vs-catalog-size.svg)
![unsafe-selection-vs-execution](charts/unsafe-selection-vs-execution.svg)
