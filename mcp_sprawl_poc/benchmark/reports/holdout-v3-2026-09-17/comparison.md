# Discovery v3 comparison

Split: **holdout**. The held-out cases were written after the published run by a separate agent without access to the failure analysis or the discovery code, and frozen before this run. Both profiles were measured on them once. Every row is rescored with the current case files.

Runs. Baseline (all tools): `holdout-v1-2026-09-17`. Tool search: `holdout-v1-2026-09-17`. Control plane, discovery v1: `holdout-v1-2026-09-17`. Control plane, discovery v3: `holdout-v3-2026-09-17`.

Control plane v1 and v3 ran in the same session with the same model and settings, so they differ only in the discovery profile. Baseline and tool search come from `holdout-v1-2026-09-17`; the discovery profile does not change them.

## Summary

| Catalog | Cases | Baseline | Tool search | Control plane v1 | Control plane v3 | v3 against v1 |
|---|---:|---:|---:|---:|---:|---|
| catalog_50 | 60 | 90.0% | 71.7% | 66.7% | 75.0% | fixed 6 · broke 1 |
| catalog_100 | 60 | 93.3% | 66.7% | 66.7% | 76.7% | fixed 6 · broke 0 |
| catalog_250 | 60 | 88.3% | 61.7% | 70.0% | 76.7% | fixed 5 · broke 1 |
| catalog_500 | 60 | 75.0% | 50.0% | 56.7% | 66.7% | fixed 7 · broke 1 |

Right capability: the golden tool or an acceptable alternative was called.

## catalog_50

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v3 |
|---|---:|---:|---:|---:|
| Right tool (exact) | 90.0% | 71.7% | 66.7% | 75.0% |
| Right capability | 90.0% | 71.7% | 66.7% | 75.0% |
| Right capability, 95% interval | [80, 95] | [59, 81] | [54, 77] | [63, 84] |
| Valid call | 73.3% | 53.3% | 56.7% | 63.3% |
| Golden tool in the prompt | 100.0% | 71.7% | 70.0% | 80.0% |
| Mean input tokens | 3,950 | 655 | 660 | 825 |
| Unsafe selections | 0 | 6 | 1 | 5 |
| Unsafe calls executed | 0 | 6 | 1 | 1 |

Rows: Baseline (all tools) 60, Tool search 60, Control plane, discovery v1 60, Control plane, discovery v3 60.

Paired on the same 60 cases, v3 against v1: right capability fixed 6 · broke 1 (both right 39, both wrong 14; exact McNemar p = 0.12); exact tool fixed 6 · broke 1 (p = 0.12). Fixed: H039, H043, H053, H056, H059, H060. Broken: H031.

## catalog_100

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v3 |
|---|---:|---:|---:|---:|
| Right tool (exact) | 91.7% | 65.0% | 66.7% | 76.7% |
| Right capability | 93.3% | 66.7% | 66.7% | 76.7% |
| Right capability, 95% interval | [84, 97] | [54, 77] | [54, 77] | [65, 86] |
| Valid call | 78.3% | 53.3% | 56.7% | 65.0% |
| Golden tool in the prompt | 100.0% | 68.3% | 71.7% | 80.0% |
| Mean input tokens | 6,232 | 631 | 658 | 820 |
| Unsafe selections | 0 | 3 | 1 | 3 |
| Unsafe calls executed | 0 | 3 | 1 | 1 |

Rows: Baseline (all tools) 60, Tool search 60, Control plane, discovery v1 60, Control plane, discovery v3 60.

Paired on the same 60 cases, v3 against v1: right capability fixed 6 · broke 0 (both right 40, both wrong 14; exact McNemar p = 0.03); exact tool fixed 6 · broke 0 (p = 0.03). Fixed: H022, H039, H043, H053, H056, H059. Broken: none.

## catalog_250

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v3 |
|---|---:|---:|---:|---:|
| Right tool (exact) | 80.0% | 56.7% | 66.7% | 73.3% |
| Right capability | 88.3% | 61.7% | 70.0% | 76.7% |
| Right capability, 95% interval | [78, 94] | [49, 73] | [57, 80] | [65, 86] |
| Valid call | 71.7% | 50.0% | 61.7% | 66.7% |
| Golden tool in the prompt | 100.0% | 60.0% | 70.0% | 78.3% |
| Mean input tokens | 13,346 | 573 | 625 | 768 |
| Unsafe selections | 3 | 5 | 0 | 3 |
| Unsafe calls executed | 3 | 5 | 0 | 1 |

Rows: Baseline (all tools) 60, Tool search 60, Control plane, discovery v1 60, Control plane, discovery v3 60.

Paired on the same 60 cases, v3 against v1: right capability fixed 5 · broke 1 (both right 41, both wrong 13; exact McNemar p = 0.22); exact tool fixed 5 · broke 1 (p = 0.22). Fixed: H039, H043, H053, H056, H059. Broken: H014.

## catalog_500

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v3 |
|---|---:|---:|---:|---:|
| Right tool (exact) | 68.3% | 43.3% | 55.0% | 63.3% |
| Right capability | 75.0% | 50.0% | 56.7% | 66.7% |
| Right capability, 95% interval | [63, 84] | [38, 62] | [44, 68] | [54, 77] |
| Valid call | 61.7% | 41.7% | 46.7% | 56.7% |
| Golden tool in the prompt | 100.0% | 50.0% | 58.3% | 70.0% |
| Mean input tokens | 24,562 | 532 | 578 | 719 |
| Unsafe selections | 6 | 13 | 2 | 6 |
| Unsafe calls executed | 6 | 13 | 1 | 1 |

Rows: Baseline (all tools) 60, Tool search 60, Control plane, discovery v1 60, Control plane, discovery v3 60.

Paired on the same 60 cases, v3 against v1: right capability fixed 7 · broke 1 (both right 33, both wrong 19; exact McNemar p = 0.07); exact tool fixed 6 · broke 1 (p = 0.12). Fixed: H025, H031, H039, H043, H053, H056, H059. Broken: H029.

## Limits

- One model at temperature 0, one run per case: the paired counts show where the two profiles differ, and the McNemar p-values are per catalog; catalogs share cases, so they are not independent tests.
- The v3 changes (router vocabulary, a soft read filter, an adaptive top-K) were written from analysed dev and test failures. A different estate may need different vocabulary.
- Discovery v3 changes only what the model is shown. Policy and the gateway are unchanged.
