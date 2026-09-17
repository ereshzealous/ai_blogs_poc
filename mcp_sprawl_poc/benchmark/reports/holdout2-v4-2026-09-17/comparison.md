# Discovery v4 comparison

Split: **holdout2**. The held-out cases were written after the published run by a separate agent without access to the failure analysis or the discovery code, and frozen before this run. Both profiles were measured on them once. Every row is rescored with the current case files.

Runs. Baseline (all tools): `holdout2-v1-2026-09-17`. Tool search: `holdout2-v1-2026-09-17`. Control plane, discovery v1: `holdout2-v1-2026-09-17`. Control plane, discovery v4: `holdout2-v4-2026-09-17`.

Control plane v1 and v4 ran in the same session with the same model and settings, so they differ only in the discovery profile. Baseline and tool search come from `holdout2-v1-2026-09-17`; the discovery profile does not change them.

## Summary

| Catalog | Cases | Baseline | Tool search | Control plane v1 | Control plane v4 | v4 against v1 |
|---|---:|---:|---:|---:|---:|---|
| catalog_50 | 100 | 98.0% | 85.0% | 75.0% | 96.0% | fixed 22 · broke 1 |
| catalog_100 | 100 | 92.0% | 79.0% | 73.0% | 95.0% | fixed 23 · broke 1 |
| catalog_250 | 100 | 85.0% | 74.0% | 72.0% | 93.0% | fixed 22 · broke 1 |
| catalog_500 | 100 | 70.0% | 58.0% | 71.0% | 92.0% | fixed 24 · broke 3 |

Right capability: the golden tool or an acceptable alternative was called.

## catalog_50

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v4 |
|---|---:|---:|---:|---:|
| Right tool (exact) | 97.0% | 84.0% | 74.0% | 95.0% |
| Right capability | 98.0% | 85.0% | 75.0% | 96.0% |
| Right capability, 95% interval | [93, 99] | [77, 91] | [66, 82] | [90, 98] |
| Valid call | 75.0% | 64.0% | 57.0% | 73.0% |
| Golden tool in the prompt | 100.0% | 87.0% | 75.0% | 97.0% |
| Mean input tokens | 3,951 | 658 | 660 | 1,465 |
| Unsafe selections | 3 | 6 | 4 | 5 |
| Unsafe calls executed | 3 | 6 | 3 | 1 |

Rows: Baseline (all tools) 100, Tool search 100, Control plane, discovery v1 100, Control plane, discovery v4 100.

Paired on the same 100 cases, v4 against v1: right capability fixed 22 · broke 1 (both right 74, both wrong 3; exact McNemar p < 0.001); exact tool fixed 22 · broke 1 (p < 0.001). Fixed: H133, H141, H143, H148, H150, H153, H156, H164, H165, H166, H173, H174, H175, H177, H180, H181, H183, H185, H188, H193, H194, H197. Broken: H170.

## catalog_100

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v4 |
|---|---:|---:|---:|---:|
| Right tool (exact) | 88.0% | 75.0% | 70.0% | 91.0% |
| Right capability | 92.0% | 79.0% | 73.0% | 95.0% |
| Right capability, 95% interval | [85, 96] | [70, 86] | [64, 81] | [89, 98] |
| Valid call | 73.0% | 60.0% | 55.0% | 72.0% |
| Golden tool in the prompt | 100.0% | 79.0% | 72.0% | 95.0% |
| Mean input tokens | 6,233 | 627 | 656 | 1,442 |
| Unsafe selections | 3 | 5 | 4 | 2 |
| Unsafe calls executed | 3 | 5 | 4 | 1 |

Rows: Baseline (all tools) 100, Tool search 100, Control plane, discovery v1 100, Control plane, discovery v4 100.

Paired on the same 100 cases, v4 against v1: right capability fixed 23 · broke 1 (both right 72, both wrong 4; exact McNemar p < 0.001); exact tool fixed 22 · broke 1 (p < 0.001). Fixed: H119, H133, H141, H143, H148, H150, H153, H156, H164, H165, H166, H173, H174, H175, H177, H180, H181, H183, H185, H188, H193, H194, H197. Broken: H136.

## catalog_250

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v4 |
|---|---:|---:|---:|---:|
| Right tool (exact) | 82.0% | 68.0% | 68.0% | 88.0% |
| Right capability | 85.0% | 74.0% | 72.0% | 93.0% |
| Right capability, 95% interval | [77, 91] | [65, 82] | [63, 80] | [86, 97] |
| Valid call | 67.0% | 58.0% | 57.0% | 71.0% |
| Golden tool in the prompt | 100.0% | 73.0% | 73.0% | 96.0% |
| Mean input tokens | 13,348 | 573 | 625 | 1,414 |
| Unsafe selections | 8 | 7 | 4 | 4 |
| Unsafe calls executed | 8 | 7 | 1 | 1 |

Rows: Baseline (all tools) 100, Tool search 100, Control plane, discovery v1 100, Control plane, discovery v4 100.

Paired on the same 100 cases, v4 against v1: right capability fixed 22 · broke 1 (both right 71, both wrong 6; exact McNemar p < 0.001); exact tool fixed 22 · broke 2 (p < 0.001). Fixed: H119, H128, H132, H133, H141, H143, H148, H153, H156, H164, H165, H166, H173, H175, H177, H180, H181, H183, H188, H193, H194, H197. Broken: H123.

## catalog_500

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v4 |
|---|---:|---:|---:|---:|
| Right tool (exact) | 63.0% | 50.0% | 66.0% | 84.0% |
| Right capability | 70.0% | 58.0% | 71.0% | 92.0% |
| Right capability, 95% interval | [60, 78] | [48, 67] | [61, 79] | [85, 96] |
| Valid call | 56.0% | 48.0% | 55.0% | 72.0% |
| Golden tool in the prompt | 100.0% | 61.0% | 70.0% | 91.0% |
| Mean input tokens | 24,564 | 537 | 590 | 1,364 |
| Unsafe selections | 14 | 17 | 5 | 5 |
| Unsafe calls executed | 14 | 17 | 2 | 1 |

Rows: Baseline (all tools) 100, Tool search 100, Control plane, discovery v1 100, Control plane, discovery v4 100.

Paired on the same 100 cases, v4 against v1: right capability fixed 24 · broke 3 (both right 68, both wrong 5; exact McNemar p < 0.001); exact tool fixed 22 · broke 4 (p < 0.001). Fixed: H119, H122, H124, H128, H132, H133, H143, H148, H153, H156, H164, H165, H166, H171, H173, H175, H177, H180, H183, H188, H191, H193, H194, H197. Broken: H134, H181, H186.

## Limits

- One model at temperature 0, one run per case: the paired counts show where the two profiles differ, and the McNemar p-values are per catalog; catalogs share cases, so they are not independent tests.
- The v4 changes (a model-written first step and read/write judgement, a collapse of equivalent tools, and v3's router and cut) were written after analysing the main set and the first held-out set. For v4, input tokens include the rewrite call.
- Discovery v4 changes only what the model is shown. Policy and the gateway are unchanged.
