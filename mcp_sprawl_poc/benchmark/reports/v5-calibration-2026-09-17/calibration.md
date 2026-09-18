# Discovery v5 calibration

Runs: `v5-calibration-2026-09-17`. 560 decisions with asking switched off; 94.1% chose the right capability.

| Tier of the leading capability | Decisions | Threshold | Automatic | Precision (95% CI) | Rule |
|---|---:|---:|---:|---|---|
| HIGH_RISK_WRITE | 110 | 0.06 | 50 (45%) | 100.0% [92.9, 100.0] | smallest threshold with at least 99% precision over at least 20 decisions |
| LOW_RISK_WRITE | 54 | 0.08 | 17 (31%) | 100.0% [81.6, 100.0] | fewer than 20 qualifying decisions: the higher of its own 99% threshold and that of HIGH_RISK_WRITE |
| READ_ONLY | 396 | 0.04 | 160 (40%) | 99.4% [96.5, 99.9] | smallest threshold with at least 99% precision over at least 20 decisions |

Under these thresholds, 227 of 560 calibration decisions (40.5%) would be automatic, 99.6% of them right [97.5, 99.9]. The rest would ask.

Precision by threshold, per tier:

- HIGH_RISK_WRITE: 0.00: 88/90, 0.06: 50/50, 0.12: 38/38, 0.18: 32/32, 0.24: 22/22, 0.30: 14/14, 0.36: 5/5, 0.42: 4/4, 0.48: 4/4, 0.54: 4/4, 0.60: 2/2
- LOW_RISK_WRITE: 0.00: 39/41, 0.06: 20/21, 0.12: 16/16, 0.18: 12/12, 0.24: 9/9, 0.30: 6/6, 0.36: 6/6, 0.42: 4/4, 0.48: 2/2, 0.54: 1/1
- READ_ONLY: 0.00: 297/307, 0.06: 129/129, 0.12: 92/92, 0.18: 76/76, 0.24: 63/63, 0.30: 48/48, 0.36: 10/10, 0.42: 3/3, 0.48: 3/3, 0.54: 1/1
