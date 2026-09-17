# Tool selection by profile

Split: **holdout2**. Right capability means the golden tool or an acceptable alternative was called. Input tokens include a discovery rewrite call when a profile makes one.

Runs: Baseline (all tools): `holdout2-v1-2026-09-17:baseline`; Tool search: `holdout2-v1-2026-09-17:search`; Control plane v1: `holdout2-v1-2026-09-17:control_plane`; Control plane v3: `holdout2-v3-2026-09-17:control_plane`; Control plane v4: `holdout2-v4-2026-09-17:control_plane`; Control plane v4, may ask: `holdout2-v4-ask-2026-09-17:control_plane`.

## Right capability

| Catalog | Cases | Baseline (all tools) | Tool search | Control plane v1 | Control plane v3 | Control plane v4 | Control plane v4, may ask |
|---|---:|---:|---:|---:|---:|---:|---:|
| catalog_50 | 100 | 98.0% | 85.0% | 75.0% | 85.0% | 96.0% | 96.0% |
| catalog_100 | 100 | 92.0% | 79.0% | 73.0% | 83.0% | 95.0% | 96.0% |
| catalog_250 | 100 | 85.0% | 74.0% | 72.0% | 85.0% | 93.0% | 95.0% |
| catalog_500 | 100 | 70.0% | 58.0% | 71.0% | 79.0% | 92.0% | 91.0% |

## catalog_50

| Metric | Baseline (all tools) | Tool search | Control plane v1 | Control plane v3 | Control plane v4 | Control plane v4, may ask |
|---|---:|---:|---:|---:|---:|---:|
| Right capability | 98.0% | 85.0% | 75.0% | 85.0% | 96.0% | 96.0% |
| Right tool (exact) | 97.0% | 84.0% | 74.0% | 84.0% | 95.0% | 95.0% |
| Valid call | 75.0% | 64.0% | 57.0% | 66.0% | 73.0% | 72.0% |
| Golden tool in the prompt | 100.0% | 87.0% | 75.0% | 86.0% | 97.0% | 97.0% |
| Mean input tokens per decision | 3,951 | 658 | 660 | 822 | 1,465 | 1,569 |
| Unsafe selections | 3 | 6 | 4 | 6 | 5 | 4 |
| Unsafe calls executed | 3 | 6 | 3 | 3 | 1 | 1 |
| Asked the user | n/a | n/a | n/a | n/a | n/a | 2.0% |
| Right without asking | n/a | n/a | n/a | n/a | n/a | 95.0% |

## catalog_100

| Metric | Baseline (all tools) | Tool search | Control plane v1 | Control plane v3 | Control plane v4 | Control plane v4, may ask |
|---|---:|---:|---:|---:|---:|---:|
| Right capability | 92.0% | 79.0% | 73.0% | 83.0% | 95.0% | 96.0% |
| Right tool (exact) | 88.0% | 75.0% | 70.0% | 80.0% | 91.0% | 92.0% |
| Valid call | 73.0% | 60.0% | 55.0% | 63.0% | 72.0% | 72.0% |
| Golden tool in the prompt | 100.0% | 79.0% | 72.0% | 83.0% | 95.0% | 95.0% |
| Mean input tokens per decision | 6,233 | 627 | 656 | 814 | 1,442 | 1,542 |
| Unsafe selections | 3 | 5 | 4 | 6 | 2 | 2 |
| Unsafe calls executed | 3 | 5 | 4 | 4 | 1 | 1 |
| Asked the user | n/a | n/a | n/a | n/a | n/a | 1.0% |
| Right without asking | n/a | n/a | n/a | n/a | n/a | 96.0% |

## catalog_250

| Metric | Baseline (all tools) | Tool search | Control plane v1 | Control plane v3 | Control plane v4 | Control plane v4, may ask |
|---|---:|---:|---:|---:|---:|---:|
| Right capability | 85.0% | 74.0% | 72.0% | 85.0% | 93.0% | 95.0% |
| Right tool (exact) | 82.0% | 68.0% | 68.0% | 80.0% | 88.0% | 90.0% |
| Valid call | 67.0% | 58.0% | 57.0% | 65.0% | 71.0% | 73.0% |
| Golden tool in the prompt | 100.0% | 73.0% | 73.0% | 85.0% | 96.0% | 96.0% |
| Mean input tokens per decision | 13,348 | 573 | 625 | 756 | 1,414 | 1,522 |
| Unsafe selections | 8 | 7 | 4 | 7 | 4 | 3 |
| Unsafe calls executed | 8 | 7 | 1 | 2 | 1 | 1 |
| Asked the user | n/a | n/a | n/a | n/a | n/a | 3.0% |
| Right without asking | n/a | n/a | n/a | n/a | n/a | 93.0% |

## catalog_500

| Metric | Baseline (all tools) | Tool search | Control plane v1 | Control plane v3 | Control plane v4 | Control plane v4, may ask |
|---|---:|---:|---:|---:|---:|---:|
| Right capability | 70.0% | 58.0% | 71.0% | 79.0% | 92.0% | 91.0% |
| Right tool (exact) | 63.0% | 50.0% | 66.0% | 73.0% | 84.0% | 82.0% |
| Valid call | 56.0% | 48.0% | 55.0% | 65.0% | 72.0% | 70.0% |
| Golden tool in the prompt | 100.0% | 61.0% | 70.0% | 82.0% | 91.0% | 91.0% |
| Mean input tokens per decision | 24,564 | 537 | 590 | 716 | 1,364 | 1,476 |
| Unsafe selections | 14 | 17 | 5 | 8 | 5 | 4 |
| Unsafe calls executed | 14 | 17 | 2 | 2 | 1 | 1 |
| Asked the user | n/a | n/a | n/a | n/a | n/a | 3.0% |
| Right without asking | n/a | n/a | n/a | n/a | n/a | 90.0% |
