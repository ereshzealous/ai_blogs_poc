# Capability resolution by arm

Split: **holdout3**. Definitions: `docs/CAPABILITY_RESOLUTION_V5.md`, section 6. Counts are (hits/decisions); intervals are in `summary.json`.

Runs: Control plane v5: `holdout3-v5-2026-09-17:control_plane`; v5, never asks: `holdout3-v5-noask-2026-09-17:control_plane`; v5 without entity lookup: `holdout3-v5-noentities-2026-09-17:control_plane`; v5 without canonical capabilities: `holdout3-v5-nocanonical-2026-09-17:control_plane`.

## Overall capability resolution

| Catalog | Control plane v5 | v5, never asks | v5 without entity lookup | v5 without canonical capabilities |
|---|---:|---:|---:|---:|
| catalog_50 | 89.4% (161/180) | n/a | n/a | n/a |
| catalog_100 | 88.9% (160/180) | 81.1% (146/180) | 88.9% (160/180) | 87.8% (158/180) |
| catalog_250 | 88.3% (159/180) | n/a | n/a | n/a |
| catalog_500 | 86.7% (156/180) | 80.0% (144/180) | 86.1% (155/180) | 82.2% (148/180) |

## catalog_50

120 clear, 60 ambiguous and 20 trap requests.

| Metric | Control plane v5 | v5, never asks | v5 without entity lookup | v5 without canonical capabilities |
|---|---:|---:|---:|---:|
| Overall capability resolution (clear + ambiguous) | 89.4% (161/180) | n/a | n/a | n/a |
| Clear requests resolved | 98.3% (118/120) | n/a | n/a | n/a |
| Ambiguous requests resolved | 71.7% (43/60) | n/a | n/a | n/a |
| Right tool shown | 93.3% (168/180) | n/a | n/a | n/a |
| Automatic coverage | 30.0% (54/180) | n/a | n/a | n/a |
| Automatic precision | 87.0% (47/54) | n/a | n/a | n/a |
| Wrongly confident | 3.9% (7/180) | n/a | n/a | n/a |
| Asked the user | 70.0% (126/180) | n/a | n/a | n/a |
| Resolved after asking | 90.5% (114/126) | n/a | n/a | n/a |
| Ambiguous requests asked about | 75.0% (45/60) | n/a | n/a | n/a |
| Lucky guesses on ambiguous requests | 16.7% (10/60) | n/a | n/a | n/a |
| Abstentions | 0.0% (0/180) | n/a | n/a | n/a |
| Exact tool | 89.4% (161/180) | n/a | n/a | n/a |
| Valid call | 54.4% (98/180) | n/a | n/a | n/a |
| Trap requests refused or redirected | 95.0% (19/20) | n/a | n/a | n/a |
| Unsafe selections / sent | 10 / 1 | n/a | n/a | n/a |
| Wrongly confident, by tier | read 6, low 1 | n/a | n/a | n/a |
| Mean input tokens per decision | 2,067 | n/a | n/a | n/a |
| Mean seconds per decision | 8.0 | n/a | n/a | n/a |

## catalog_100

120 clear, 60 ambiguous and 20 trap requests.

| Metric | Control plane v5 | v5, never asks | v5 without entity lookup | v5 without canonical capabilities |
|---|---:|---:|---:|---:|
| Overall capability resolution (clear + ambiguous) | 88.9% (160/180) | 81.1% (146/180) | 88.9% (160/180) | 87.8% (158/180) |
| Clear requests resolved | 96.7% (116/120) | 95.0% (114/120) | 95.0% (114/120) | 94.2% (113/120) |
| Ambiguous requests resolved | 73.3% (44/60) | 53.3% (32/60) | 76.7% (46/60) | 75.0% (45/60) |
| Right tool shown | 93.3% (168/180) | 93.9% (169/180) | 92.8% (167/180) | 92.8% (167/180) |
| Automatic coverage | 30.6% (55/180) | 99.4% (179/180) | 21.7% (39/180) | 33.3% (60/180) |
| Automatic precision | 85.5% (47/55) | 81.6% (146/179) | 79.5% (31/39) | 85.0% (51/60) |
| Wrongly confident | 4.4% (8/180) | 18.3% (33/180) | 4.4% (8/180) | 5.0% (9/180) |
| Asked the user | 69.4% (125/180) | 0.0% (0/180) | 78.3% (141/180) | 66.7% (120/180) |
| Resolved after asking | 90.4% (113/125) | n/a | 91.5% (129/141) | 89.2% (107/120) |
| Ambiguous requests asked about | 73.3% (44/60) | 0.0% (0/60) | 80.0% (48/60) | 75.0% (45/60) |
| Lucky guesses on ambiguous requests | 16.7% (10/60) | 53.3% (32/60) | 11.7% (7/60) | 16.7% (10/60) |
| Abstentions | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) |
| Exact tool | 88.9% (160/180) | 81.1% (146/180) | 88.9% (160/180) | 87.8% (158/180) |
| Valid call | 53.3% (96/180) | 50.6% (91/180) | 55.0% (99/180) | 55.0% (99/180) |
| Trap requests refused or redirected | 95.0% (19/20) | 90.0% (18/20) | 85.0% (17/20) | 90.0% (18/20) |
| Unsafe selections / sent | 11 / 1 | 17 / 1 | 11 / 0 | 11 / 1 |
| Wrongly confident, by tier | read 7, low 1 | read 27, low 4, high 4 | read 10 | read 10 |
| Mean input tokens per decision | 2,058 | 1,636 | 2,108 | 2,021 |
| Mean seconds per decision | 5.1 | 5.0 | 10.0 | 10.6 |

## catalog_250

120 clear, 60 ambiguous and 20 trap requests.

| Metric | Control plane v5 | v5, never asks | v5 without entity lookup | v5 without canonical capabilities |
|---|---:|---:|---:|---:|
| Overall capability resolution (clear + ambiguous) | 88.3% (159/180) | n/a | n/a | n/a |
| Clear requests resolved | 97.5% (117/120) | n/a | n/a | n/a |
| Ambiguous requests resolved | 70.0% (42/60) | n/a | n/a | n/a |
| Right tool shown | 91.7% (165/180) | n/a | n/a | n/a |
| Automatic coverage | 45.0% (81/180) | n/a | n/a | n/a |
| Automatic precision | 86.4% (70/81) | n/a | n/a | n/a |
| Wrongly confident | 6.1% (11/180) | n/a | n/a | n/a |
| Asked the user | 55.0% (99/180) | n/a | n/a | n/a |
| Resolved after asking | 89.9% (89/99) | n/a | n/a | n/a |
| Ambiguous requests asked about | 63.3% (38/60) | n/a | n/a | n/a |
| Lucky guesses on ambiguous requests | 23.3% (14/60) | n/a | n/a | n/a |
| Abstentions | 0.0% (0/180) | n/a | n/a | n/a |
| Exact tool | 88.3% (159/180) | n/a | n/a | n/a |
| Valid call | 52.2% (94/180) | n/a | n/a | n/a |
| Trap requests refused or redirected | 100.0% (20/20) | n/a | n/a | n/a |
| Unsafe selections / sent | 12 / 2 | n/a | n/a | n/a |
| Wrongly confident, by tier | read 10, low 1 | n/a | n/a | n/a |
| Mean input tokens per decision | 1,897 | n/a | n/a | n/a |
| Mean seconds per decision | 12.6 | n/a | n/a | n/a |

## catalog_500

120 clear, 60 ambiguous and 20 trap requests.

| Metric | Control plane v5 | v5, never asks | v5 without entity lookup | v5 without canonical capabilities |
|---|---:|---:|---:|---:|
| Overall capability resolution (clear + ambiguous) | 86.7% (156/180) | 80.0% (144/180) | 86.1% (155/180) | 82.2% (148/180) |
| Clear requests resolved | 96.7% (116/120) | 95.0% (114/120) | 94.2% (113/120) | 90.0% (108/120) |
| Ambiguous requests resolved | 66.7% (40/60) | 50.0% (30/60) | 70.0% (42/60) | 66.7% (40/60) |
| Right tool shown | 90.6% (163/180) | 92.8% (167/180) | 91.1% (164/180) | 87.8% (158/180) |
| Automatic coverage | 46.1% (83/180) | 98.3% (177/180) | 38.9% (70/180) | 43.3% (78/180) |
| Automatic precision | 87.9% (73/83) | 81.4% (144/177) | 85.7% (60/70) | 85.9% (67/78) |
| Wrongly confident | 5.6% (10/180) | 18.3% (33/180) | 5.6% (10/180) | 6.1% (11/180) |
| Asked the user | 53.9% (97/180) | 0.0% (0/180) | 61.1% (110/180) | 56.7% (102/180) |
| Resolved after asking | 85.6% (83/97) | n/a | 86.4% (95/110) | 79.4% (81/102) |
| Ambiguous requests asked about | 66.7% (40/60) | 0.0% (0/60) | 70.0% (42/60) | 68.3% (41/60) |
| Lucky guesses on ambiguous requests | 20.0% (12/60) | 50.0% (30/60) | 16.7% (10/60) | 18.3% (11/60) |
| Abstentions | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) |
| Exact tool | 86.7% (156/180) | 78.9% (142/180) | 86.1% (155/180) | 81.7% (147/180) |
| Valid call | 50.6% (91/180) | 48.3% (87/180) | 50.6% (91/180) | 48.9% (88/180) |
| Trap requests refused or redirected | 100.0% (20/20) | 90.0% (18/20) | 95.0% (19/20) | 85.0% (17/20) |
| Unsafe selections / sent | 12 / 1 | 18 / 1 | 11 / 0 | 19 / 6 |
| Wrongly confident, by tier | read 9, low 1 | read 26, low 5, high 4 | read 10 | read 12 |
| Mean input tokens per decision | 1,831 | 1,506 | 1,890 | 1,856 |
| Mean seconds per decision | 4.8 | 2.5 | 10.1 | 12.8 |
