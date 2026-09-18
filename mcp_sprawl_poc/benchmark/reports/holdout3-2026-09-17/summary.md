# Capability resolution by arm

Split: **holdout3**. Definitions: `docs/CAPABILITY_RESOLUTION_V5.md`, section 6. Counts are (hits/decisions); intervals are in `summary.json`.

Runs: Baseline (all tools): `holdout3-baseline-2026-09-17:baseline`; Search, 7 tools: `holdout3-search7-2026-09-17:search`; Control plane v4: `holdout3-v4-2026-09-17:control_plane`; Control plane v5: `holdout3-v5-2026-09-17:control_plane`.

## Overall capability resolution

| Catalog | Baseline (all tools) | Search, 7 tools | Control plane v4 | Control plane v5 |
|---|---:|---:|---:|---:|
| catalog_50 | 84.4% (152/180) | 75.0% (135/180) | 81.7% (147/180) | 89.4% (161/180) |
| catalog_100 | 81.1% (146/180) | 72.2% (130/180) | 81.1% (146/180) | 88.9% (160/180) |
| catalog_250 | 68.3% (123/180) | 58.3% (105/180) | 77.8% (140/180) | 88.3% (159/180) |
| catalog_500 | 60.0% (108/180) | 44.4% (80/180) | 69.4% (125/180) | 86.7% (156/180) |

## catalog_50

120 clear, 60 ambiguous and 20 trap requests.

| Metric | Baseline (all tools) | Search, 7 tools | Control plane v4 | Control plane v5 |
|---|---:|---:|---:|---:|
| Overall capability resolution (clear + ambiguous) | 84.4% (152/180) | 75.0% (135/180) | 81.7% (147/180) | 89.4% (161/180) |
| Clear requests resolved | 94.2% (113/120) | 90.8% (109/120) | 95.0% (114/120) | 98.3% (118/120) |
| Ambiguous requests resolved | 65.0% (39/60) | 43.3% (26/60) | 55.0% (33/60) | 71.7% (43/60) |
| Right tool shown | 100.0% (180/180) | 84.4% (152/180) | 92.2% (166/180) | 93.3% (168/180) |
| Automatic coverage | 100.0% (180/180) | 98.3% (177/180) | 99.4% (179/180) | 30.0% (54/180) |
| Automatic precision | 84.4% (152/180) | 76.3% (135/177) | 82.1% (147/179) | 87.0% (47/54) |
| Wrongly confident | 15.6% (28/180) | 23.3% (42/180) | 17.8% (32/180) | 3.9% (7/180) |
| Asked the user | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) | 70.0% (126/180) |
| Resolved after asking | n/a | n/a | n/a | 90.5% (114/126) |
| Ambiguous requests asked about | 0.0% (0/60) | 0.0% (0/60) | 0.0% (0/60) | 75.0% (45/60) |
| Lucky guesses on ambiguous requests | 65.0% (39/60) | 43.3% (26/60) | 55.0% (33/60) | 16.7% (10/60) |
| Abstentions | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) |
| Exact tool | 83.9% (151/180) | 75.0% (135/180) | 80.6% (145/180) | 89.4% (161/180) |
| Valid call | 49.4% (89/180) | 40.6% (73/180) | 48.9% (88/180) | 54.4% (98/180) |
| Trap requests refused or redirected | 85.0% (17/20) | 70.0% (14/20) | 85.0% (17/20) | 95.0% (19/20) |
| Unsafe selections / sent | 12 / 12 | 18 / 18 | 15 / 1 | 10 / 1 |
| Wrongly confident, by tier | read 23, low 3, high 5 | read 35, low 4, high 9 | read 28, low 4, high 3 | read 6, low 1 |
| Mean input tokens per decision | 3,946 | 818 | 1,465 | 2,067 |
| Mean seconds per decision | 1.8 | 3.1 | 4.9 | 8.0 |

## catalog_100

120 clear, 60 ambiguous and 20 trap requests.

| Metric | Baseline (all tools) | Search, 7 tools | Control plane v4 | Control plane v5 |
|---|---:|---:|---:|---:|
| Overall capability resolution (clear + ambiguous) | 81.1% (146/180) | 72.2% (130/180) | 81.1% (146/180) | 88.9% (160/180) |
| Clear requests resolved | 91.7% (110/120) | 84.2% (101/120) | 93.3% (112/120) | 96.7% (116/120) |
| Ambiguous requests resolved | 60.0% (36/60) | 48.3% (29/60) | 56.7% (34/60) | 73.3% (44/60) |
| Right tool shown | 100.0% (180/180) | 81.1% (146/180) | 91.1% (164/180) | 93.3% (168/180) |
| Automatic coverage | 100.0% (180/180) | 96.7% (174/180) | 99.4% (179/180) | 30.6% (55/180) |
| Automatic precision | 81.1% (146/180) | 74.7% (130/174) | 81.6% (146/179) | 85.5% (47/55) |
| Wrongly confident | 18.9% (34/180) | 24.4% (44/180) | 18.3% (33/180) | 4.4% (8/180) |
| Asked the user | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) | 69.4% (125/180) |
| Resolved after asking | n/a | n/a | n/a | 90.4% (113/125) |
| Ambiguous requests asked about | 0.0% (0/60) | 0.0% (0/60) | 0.0% (0/60) | 73.3% (44/60) |
| Lucky guesses on ambiguous requests | 60.0% (36/60) | 48.3% (29/60) | 56.7% (34/60) | 16.7% (10/60) |
| Abstentions | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) |
| Exact tool | 80.6% (145/180) | 72.2% (130/180) | 80.6% (145/180) | 88.9% (160/180) |
| Valid call | 49.4% (89/180) | 41.1% (74/180) | 48.3% (87/180) | 53.3% (96/180) |
| Trap requests refused or redirected | 90.0% (18/20) | 75.0% (15/20) | 90.0% (18/20) | 95.0% (19/20) |
| Unsafe selections / sent | 12 / 12 | 23 / 23 | 14 / 3 | 11 / 1 |
| Wrongly confident, by tier | read 27, low 3, high 6 | read 31, low 8, high 10 | read 26, low 4, high 5 | read 7, low 1 |
| Mean input tokens per decision | 6,228 | 757 | 1,457 | 2,058 |
| Mean seconds per decision | 2.0 | 3.0 | 2.3 | 5.1 |

## catalog_250

120 clear, 60 ambiguous and 20 trap requests.

| Metric | Baseline (all tools) | Search, 7 tools | Control plane v4 | Control plane v5 |
|---|---:|---:|---:|---:|
| Overall capability resolution (clear + ambiguous) | 68.3% (123/180) | 58.3% (105/180) | 77.8% (140/180) | 88.3% (159/180) |
| Clear requests resolved | 82.5% (99/120) | 70.0% (84/120) | 91.7% (110/120) | 97.5% (117/120) |
| Ambiguous requests resolved | 40.0% (24/60) | 35.0% (21/60) | 50.0% (30/60) | 70.0% (42/60) |
| Right tool shown | 100.0% (180/180) | 69.4% (125/180) | 89.4% (161/180) | 91.7% (165/180) |
| Automatic coverage | 99.4% (179/180) | 95.6% (172/180) | 99.4% (179/180) | 45.0% (81/180) |
| Automatic precision | 68.7% (123/179) | 61.1% (105/172) | 78.2% (140/179) | 86.4% (70/81) |
| Wrongly confident | 31.1% (56/180) | 37.2% (67/180) | 21.7% (39/180) | 6.1% (11/180) |
| Asked the user | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) | 55.0% (99/180) |
| Resolved after asking | n/a | n/a | n/a | 89.9% (89/99) |
| Ambiguous requests asked about | 0.0% (0/60) | 0.0% (0/60) | 0.0% (0/60) | 63.3% (38/60) |
| Lucky guesses on ambiguous requests | 40.0% (24/60) | 35.0% (21/60) | 50.0% (30/60) | 23.3% (14/60) |
| Abstentions | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) |
| Exact tool | 67.8% (122/180) | 58.3% (105/180) | 77.2% (139/180) | 88.3% (159/180) |
| Valid call | 42.2% (76/180) | 35.6% (64/180) | 48.3% (87/180) | 52.2% (94/180) |
| Trap requests refused or redirected | 50.0% (10/20) | 50.0% (10/20) | 85.0% (17/20) | 100.0% (20/20) |
| Unsafe selections / sent | 27 / 27 | 35 / 35 | 18 / 3 | 12 / 2 |
| Wrongly confident, by tier | read 37, low 8, high 21 | read 47, low 14, high 16 | read 29, low 5, high 8 | read 10, low 1 |
| Mean input tokens per decision | 13,343 | 689 | 1,414 | 1,897 |
| Mean seconds per decision | 2.8 | 2.9 | 2.4 | 12.6 |

## catalog_500

120 clear, 60 ambiguous and 20 trap requests.

| Metric | Baseline (all tools) | Search, 7 tools | Control plane v4 | Control plane v5 |
|---|---:|---:|---:|---:|
| Overall capability resolution (clear + ambiguous) | 60.0% (108/180) | 44.4% (80/180) | 69.4% (125/180) | 86.7% (156/180) |
| Clear requests resolved | 71.7% (86/120) | 55.0% (66/120) | 83.3% (100/120) | 96.7% (116/120) |
| Ambiguous requests resolved | 36.7% (22/60) | 23.3% (14/60) | 41.7% (25/60) | 66.7% (40/60) |
| Right tool shown | 100.0% (180/180) | 56.1% (101/180) | 83.3% (150/180) | 90.6% (163/180) |
| Automatic coverage | 100.0% (180/180) | 96.1% (173/180) | 98.3% (177/180) | 46.1% (83/180) |
| Automatic precision | 60.0% (108/180) | 46.2% (80/173) | 70.6% (125/177) | 87.9% (73/83) |
| Wrongly confident | 40.0% (72/180) | 51.7% (93/180) | 28.9% (52/180) | 5.6% (10/180) |
| Asked the user | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) | 53.9% (97/180) |
| Resolved after asking | n/a | n/a | n/a | 85.6% (83/97) |
| Ambiguous requests asked about | 0.0% (0/60) | 0.0% (0/60) | 0.0% (0/60) | 66.7% (40/60) |
| Lucky guesses on ambiguous requests | 36.7% (22/60) | 23.3% (14/60) | 41.7% (25/60) | 20.0% (12/60) |
| Abstentions | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) | 0.0% (0/180) |
| Exact tool | 59.4% (107/180) | 43.9% (79/180) | 68.9% (124/180) | 86.7% (156/180) |
| Valid call | 37.2% (67/180) | 26.1% (47/180) | 43.3% (78/180) | 50.6% (91/180) |
| Trap requests refused or redirected | 0.0% (0/20) | 0.0% (0/20) | 65.0% (13/20) | 100.0% (20/20) |
| Unsafe selections / sent | 37 / 37 | 52 / 52 | 25 / 9 | 12 / 1 |
| Wrongly confident, by tier | read 47, low 7, high 38 | read 63, low 12, high 38 | read 38, low 5, high 16 | read 9, low 1 |
| Mean input tokens per decision | 24,559 | 636 | 1,365 | 1,831 |
| Mean seconds per decision | 3.7 | 3.2 | 2.3 | 4.8 |
