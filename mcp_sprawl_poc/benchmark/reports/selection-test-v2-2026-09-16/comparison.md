# Discovery v2 comparison

Split: **test**. Discovery v2 was tuned on the dev split only; the test split was run once, after the profile was fixed. Every row is rescored with the current `cases.yaml`.

Runs. Baseline (all tools): `gpt-oss-20b-2026-09-15`. Tool search: `gpt-oss-20b-2026-09-15`. Control plane, discovery v1: `selection-test-v1-2026-09-16`. Control plane, discovery v2: `selection-test-v2-2026-09-16`. Control plane v1, published run: `gpt-oss-20b-2026-09-15`.

Control plane v1 and v2 ran in the same session with the same model and settings, so they differ only in the discovery profile. Baseline and tool search come from the published run; the discovery profile does not change them.

## Summary

| Catalog | Cases | Baseline | Tool search | Control plane v1 | Control plane v2 | v2 against v1 |
|---|---:|---:|---:|---:|---:|---|
| catalog_10 | 39 | 92.3% | 92.3% | 94.9% | 94.9% | fixed 0 · broke 0 |
| catalog_25 | 63 | 93.7% | 85.7% | 87.3% | 90.5% | fixed 2 · broke 0 |
| catalog_50 | 86 | 93.0% | 84.9% | 86.1% | 88.4% | fixed 3 · broke 1 |
| catalog_100 | 86 | 90.7% | 83.7% | 86.1% | 86.1% | fixed 1 · broke 1 |
| catalog_250 | 86 | 79.1% | 70.9% | 81.4% | 81.4% | fixed 1 · broke 1 |
| catalog_500 | 86 | 76.7% | 58.1% | 80.2% | 77.9% | fixed 0 · broke 2 |
| low_overlap_100 | 86 | 91.9% | 84.9% | 86.1% | 86.1% | fixed 1 · broke 1 |
| high_overlap_100 | 86 | 87.2% | 76.7% | 84.9% | 83.7% | fixed 3 · broke 4 |

Right capability: the golden tool or an acceptable alternative was called.

## catalog_10

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 79.5% | 79.5% | 82.0% | 84.6% | 82.0% |
| Right capability | 92.3% | 92.3% | 94.9% | 94.9% | 94.9% |
| Right capability, 95% interval | [80, 97] | [80, 97] | [83, 99] | [83, 99] | [83, 99] |
| Valid call | 79.5% | 76.9% | 84.6% | 84.6% | 84.6% |
| Golden tool in the prompt | 100.0% | 94.9% | 94.9% | 92.3% | 94.9% |
| Mean input tokens | 1,174 | 759 | 738 | 724 | 738 |
| Unsafe selections | 1 | 1 | 0 | 0 | 0 |
| Unsafe calls executed | 1 | 1 | 0 | 0 | 0 |

Rows: Baseline (all tools) 39, Tool search 39, Control plane, discovery v1 39, Control plane, discovery v2 39, Control plane v1, published run 39.

Paired on the same 39 cases, v2 against v1: right capability fixed 0 · broke 0 (both right 37, both wrong 2; exact McNemar p = 1.00); exact tool fixed 2 · broke 1 (p = 1.00). Fixed: none. Broken: none.

## catalog_25

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 79.4% | 76.2% | 79.4% | 81.0% | 77.8% |
| Right capability | 93.7% | 85.7% | 87.3% | 90.5% | 88.9% |
| Right capability, 95% interval | [85, 98] | [75, 92] | [77, 93] | [81, 96] | [79, 95] |
| Valid call | 81.0% | 71.4% | 77.8% | 79.4% | 81.0% |
| Golden tool in the prompt | 100.0% | 85.7% | 85.7% | 87.3% | 85.7% |
| Mean input tokens | 2,327 | 708 | 695 | 699 | 695 |
| Unsafe selections | 2 | 2 | 1 | 1 | 2 |
| Unsafe calls executed | 2 | 2 | 1 | 1 | 1 |

Rows: Baseline (all tools) 63, Tool search 63, Control plane, discovery v1 63, Control plane, discovery v2 63, Control plane v1, published run 63.

Paired on the same 63 cases, v2 against v1: right capability fixed 2 · broke 0 (both right 55, both wrong 6; exact McNemar p = 0.50); exact tool fixed 2 · broke 1 (p = 1.00). Fixed: R04, V22. Broken: none.

## catalog_50

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 80.2% | 73.3% | 74.4% | 76.7% | 73.3% |
| Right capability | 93.0% | 84.9% | 86.1% | 88.4% | 87.2% |
| Right capability, 95% interval | [86, 97] | [76, 91] | [77, 92] | [80, 94] | [79, 93] |
| Valid call | 82.6% | 76.7% | 80.2% | 80.2% | 81.4% |
| Golden tool in the prompt | 100.0% | 79.1% | 82.6% | 83.7% | 82.6% |
| Mean input tokens | 3,940 | 655 | 663 | 662 | 663 |
| Unsafe selections | 3 | 4 | 2 | 2 | 2 |
| Unsafe calls executed | 3 | 4 | 0 | 1 | 0 |

Rows: Baseline (all tools) 86, Tool search 86, Control plane, discovery v1 86, Control plane, discovery v2 86, Control plane v1, published run 86.

Paired on the same 86 cases, v2 against v1: right capability fixed 3 · broke 1 (both right 73, both wrong 9; exact McNemar p = 0.62); exact tool fixed 3 · broke 1 (p = 0.62). Fixed: R04, R13, V22. Broken: M02.

## catalog_100

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 77.9% | 73.3% | 74.4% | 73.3% | 72.1% |
| Right capability | 90.7% | 83.7% | 86.1% | 86.1% | 86.1% |
| Right capability, 95% interval | [83, 95] | [75, 90] | [77, 92] | [77, 92] | [77, 92] |
| Valid call | 79.1% | 73.3% | 79.1% | 79.1% | 80.2% |
| Golden tool in the prompt | 100.0% | 77.9% | 81.4% | 82.6% | 81.4% |
| Mean input tokens | 6,222 | 635 | 661 | 665 | 661 |
| Unsafe selections | 3 | 5 | 2 | 4 | 2 |
| Unsafe calls executed | 3 | 5 | 0 | 0 | 0 |

Rows: Baseline (all tools) 86, Tool search 86, Control plane, discovery v1 86, Control plane, discovery v2 86, Control plane v1, published run 86.

Paired on the same 86 cases, v2 against v1: right capability fixed 1 · broke 1 (both right 73, both wrong 11; exact McNemar p = 1.00); exact tool fixed 1 · broke 2 (p = 1.00). Fixed: R04. Broken: M02.

## catalog_250

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 66.3% | 58.1% | 69.8% | 69.8% | 69.8% |
| Right capability | 79.1% | 70.9% | 81.4% | 81.4% | 81.4% |
| Right capability, 95% interval | [69, 86] | [61, 79] | [72, 88] | [72, 88] | [72, 88] |
| Valid call | 68.6% | 61.6% | 75.6% | 75.6% | 75.6% |
| Golden tool in the prompt | 100.0% | 68.6% | 77.9% | 77.9% | 77.9% |
| Mean input tokens | 13,337 | 579 | 623 | 628 | 623 |
| Unsafe selections | 4 | 8 | 3 | 4 | 3 |
| Unsafe calls executed | 4 | 8 | 0 | 0 | 0 |

Rows: Baseline (all tools) 86, Tool search 86, Control plane, discovery v1 86, Control plane, discovery v2 86, Control plane v1, published run 86.

Paired on the same 86 cases, v2 against v1: right capability fixed 1 · broke 1 (both right 69, both wrong 15; exact McNemar p = 1.00); exact tool fixed 0 · broke 0 (p = 1.00). Fixed: A17. Broken: A12.

## catalog_500

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 55.8% | 46.5% | 61.6% | 60.5% | 61.6% |
| Right capability | 76.7% | 58.1% | 80.2% | 77.9% | 81.4% |
| Right capability, 95% interval | [67, 84] | [48, 68] | [71, 87] | [68, 85] | [72, 88] |
| Valid call | 67.4% | 48.8% | 76.7% | 74.4% | 76.7% |
| Golden tool in the prompt | 100.0% | 61.6% | 76.7% | 75.6% | 76.7% |
| Mean input tokens | 24,553 | 545 | 594 | 600 | 594 |
| Unsafe selections | 5 | 19 | 4 | 5 | 4 |
| Unsafe calls executed | 5 | 19 | 1 | 1 | 1 |

Rows: Baseline (all tools) 86, Tool search 86, Control plane, discovery v1 86, Control plane, discovery v2 86, Control plane v1, published run 86.

Paired on the same 86 cases, v2 against v1: right capability fixed 0 · broke 2 (both right 67, both wrong 17; exact McNemar p = 0.50); exact tool fixed 0 · broke 1 (p = 1.00). Fixed: none. Broken: A12, R15.

## low_overlap_100

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 82.6% | 74.4% | 74.4% | 74.4% | 72.1% |
| Right capability | 91.9% | 84.9% | 86.1% | 86.1% | 86.1% |
| Right capability, 95% interval | [84, 96] | [76, 91] | [77, 92] | [77, 92] | [77, 92] |
| Valid call | 77.9% | 76.7% | 79.1% | 79.1% | 80.2% |
| Golden tool in the prompt | 100.0% | 79.1% | 81.4% | 82.6% | 81.4% |
| Mean input tokens | 6,306 | 636 | 663 | 665 | 663 |
| Unsafe selections | 3 | 5 | 2 | 4 | 3 |
| Unsafe calls executed | 3 | 5 | 0 | 0 | 0 |

Rows: Baseline (all tools) 86, Tool search 86, Control plane, discovery v1 86, Control plane, discovery v2 86, Control plane v1, published run 86.

Paired on the same 86 cases, v2 against v1: right capability fixed 1 · broke 1 (both right 73, both wrong 11; exact McNemar p = 1.00); exact tool fixed 1 · broke 1 (p = 1.00). Fixed: R04. Broken: M02.

## high_overlap_100

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 70.9% | 61.6% | 66.3% | 67.4% | 66.3% |
| Right capability | 87.2% | 76.7% | 84.9% | 83.7% | 83.7% |
| Right capability, 95% interval | [79, 93] | [67, 84] | [76, 91] | [75, 90] | [75, 90] |
| Valid call | 77.9% | 69.8% | 80.2% | 77.9% | 80.2% |
| Golden tool in the prompt | 100.0% | 73.3% | 80.2% | 79.1% | 80.2% |
| Mean input tokens | 6,354 | 592 | 623 | 627 | 623 |
| Unsafe selections | 4 | 9 | 3 | 4 | 3 |
| Unsafe calls executed | 4 | 9 | 0 | 1 | 0 |

Rows: Baseline (all tools) 86, Tool search 86, Control plane, discovery v1 86, Control plane, discovery v2 86, Control plane v1, published run 86.

Paired on the same 86 cases, v2 against v1: right capability fixed 3 · broke 4 (both right 69, both wrong 10; exact McNemar p = 1.00); exact tool fixed 3 · broke 2 (p = 1.00). Fixed: R04, R13, V22. Broken: M03, M12, R14, R15.

## Limits

- One model at temperature 0, one run per case: the paired counts show where the two profiles differ, and the McNemar p-values are per catalog; catalogs share cases, so they are not independent tests.
- The v2 signals (scope, write intent, operation verb, named identifier) were chosen from dev-split misses. They are general registry and schema signals, but a different estate may need different weights.
- Discovery v2 changes only what the model is shown. Policy and the gateway are unchanged.
