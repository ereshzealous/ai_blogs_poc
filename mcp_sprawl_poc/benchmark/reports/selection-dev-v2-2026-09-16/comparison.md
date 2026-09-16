# Discovery v2 comparison

Split: **dev**. This split includes the dev cases that were used to tune discovery v2, so it shows the tuning evidence, not an unbiased estimate. Every row is rescored with the current `cases.yaml`.

Runs. Baseline (all tools): `gpt-oss-20b-2026-09-15`. Tool search: `gpt-oss-20b-2026-09-15`. Control plane, discovery v1: `selection-dev-v1-2026-09-16`. Control plane, discovery v2: `selection-dev-v2-2026-09-16`. Control plane v1, published run: `gpt-oss-20b-2026-09-15`.

Control plane v1 and v2 ran in the same session with the same model and settings, so they differ only in the discovery profile. Baseline and tool search come from the published run; the discovery profile does not change them.

## Summary

| Catalog | Cases | Baseline | Tool search | Control plane v1 | Control plane v2 | v2 against v1 |
|---|---:|---:|---:|---:|---:|---|
| catalog_50 | 34 | 94.1% | 94.1% | 91.2% | 94.1% | fixed 1 · broke 0 |
| catalog_100 | 34 | 94.1% | 82.3% | 91.2% | 97.1% | fixed 2 · broke 0 |
| catalog_250 | 34 | 76.5% | 73.5% | 82.3% | 91.2% | fixed 4 · broke 1 |
| catalog_500 | 34 | 76.5% | 61.8% | 70.6% | 82.3% | fixed 4 · broke 0 |

Right capability: the golden tool or an acceptable alternative was called.

## catalog_50

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 82.3% | 79.4% | 73.5% | 76.5% | 79.4% |
| Right capability | 94.1% | 94.1% | 91.2% | 94.1% | 97.1% |
| Right capability, 95% interval | [81, 98] | [81, 98] | [77, 97] | [81, 98] | [85, 99] |
| Valid call | 79.4% | 76.5% | 79.4% | 82.3% | 82.3% |
| Golden tool in the prompt | 100.0% | 88.2% | 91.2% | 94.1% | 91.2% |
| Mean input tokens | 3,941 | 640 | 650 | 653 | 650 |
| Unsafe selections | 0 | 1 | 1 | 0 | 1 |
| Unsafe calls executed | 0 | 1 | 1 | 0 | 1 |

Rows: Baseline (all tools) 34, Tool search 34, Control plane, discovery v1 34, Control plane, discovery v2 34, Control plane v1, published run 34.

Paired on the same 34 cases, v2 against v1: right capability fixed 1 · broke 0 (both right 31, both wrong 2; exact McNemar p = 1.00); exact tool fixed 1 · broke 0 (p = 1.00). Fixed: R17. Broken: none.

## catalog_100

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 79.4% | 64.7% | 73.5% | 76.5% | 73.5% |
| Right capability | 94.1% | 82.3% | 91.2% | 97.1% | 94.1% |
| Right capability, 95% interval | [81, 98] | [66, 92] | [77, 97] | [85, 99] | [81, 98] |
| Valid call | 79.4% | 70.6% | 79.4% | 85.3% | 82.3% |
| Golden tool in the prompt | 100.0% | 76.5% | 88.2% | 94.1% | 88.2% |
| Mean input tokens | 6,223 | 617 | 647 | 652 | 647 |
| Unsafe selections | 0 | 2 | 2 | 0 | 2 |
| Unsafe calls executed | 0 | 2 | 1 | 0 | 1 |

Rows: Baseline (all tools) 34, Tool search 34, Control plane, discovery v1 34, Control plane, discovery v2 34, Control plane v1, published run 34.

Paired on the same 34 cases, v2 against v1: right capability fixed 2 · broke 0 (both right 31, both wrong 1; exact McNemar p = 0.50); exact tool fixed 2 · broke 1 (p = 1.00). Fixed: R17, R22. Broken: none.

## catalog_250

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 67.7% | 52.9% | 64.7% | 76.5% | 61.8% |
| Right capability | 76.5% | 73.5% | 82.3% | 91.2% | 82.3% |
| Right capability, 95% interval | [60, 88] | [57, 85] | [66, 92] | [77, 97] | [66, 92] |
| Valid call | 64.7% | 64.7% | 73.5% | 79.4% | 73.5% |
| Golden tool in the prompt | 100.0% | 67.7% | 79.4% | 91.2% | 79.4% |
| Mean input tokens | 13,338 | 570 | 604 | 612 | 604 |
| Unsafe selections | 3 | 4 | 3 | 2 | 4 |
| Unsafe calls executed | 3 | 4 | 1 | 0 | 1 |

Rows: Baseline (all tools) 34, Tool search 34, Control plane, discovery v1 34, Control plane, discovery v2 34, Control plane v1, published run 34.

Paired on the same 34 cases, v2 against v1: right capability fixed 4 · broke 1 (both right 27, both wrong 2; exact McNemar p = 0.38); exact tool fixed 5 · broke 1 (p = 0.22). Fixed: A09, R17, R22, V14. Broken: R01.

## catalog_500

| Metric | Baseline (all tools) | Tool search | Control plane, discovery v1 | Control plane, discovery v2 | Control plane v1, published run |
|---|---:|---:|---:|---:|---:|
| Right tool (exact) | 58.8% | 41.2% | 50.0% | 64.7% | 50.0% |
| Right capability | 76.5% | 61.8% | 70.6% | 82.3% | 70.6% |
| Right capability, 95% interval | [60, 88] | [45, 76] | [54, 83] | [66, 92] | [54, 83] |
| Valid call | 61.8% | 52.9% | 67.7% | 76.5% | 64.7% |
| Golden tool in the prompt | 100.0% | 58.8% | 76.5% | 85.3% | 76.5% |
| Mean input tokens | 24,554 | 538 | 572 | 579 | 572 |
| Unsafe selections | 3 | 4 | 4 | 2 | 4 |
| Unsafe calls executed | 3 | 4 | 1 | 0 | 2 |

Rows: Baseline (all tools) 34, Tool search 34, Control plane, discovery v1 34, Control plane, discovery v2 34, Control plane v1, published run 34.

Paired on the same 34 cases, v2 against v1: right capability fixed 4 · broke 0 (both right 24, both wrong 6; exact McNemar p = 0.12); exact tool fixed 5 · broke 0 (p = 0.06). Fixed: A05, R17, R22, V14. Broken: none.

## Limits

- One model at temperature 0, one run per case: the paired counts show where the two profiles differ, and the McNemar p-values are per catalog; catalogs share cases, so they are not independent tests.
- The v2 signals (scope, write intent, operation verb, named identifier) were chosen from dev-split misses. They are general registry and schema signals, but a different estate may need different weights.
- Discovery v2 changes only what the model is shown. Policy and the gateway are unchanged.
