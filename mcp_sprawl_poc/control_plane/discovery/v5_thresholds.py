"""Confidence thresholds for discovery v5, one per risk tier of the leading capability.

Written by `python -m benchmark.reports.v5_calibration` from the calibration runs (docs/CAPABILITY_RESOLUTION_V5.md,
section 7) and frozen with the v5 code. None means "not calibrated": that tier always asks.
"""

THRESHOLDS: dict[str, float | None] = {"HIGH_RISK_WRITE": 0.06, "LOW_RISK_WRITE": 0.08, "READ_ONLY": 0.04}
CALIBRATION: dict[str, object] = {
    "runs": [
        "v5-calibration-2026-09-17"
    ],
    "decisions": 560,
    "overall": {
        "automatic": 227,
        "correct": 226,
        "precision": 0.9956,
        "precision_ci": [
            0.9755,
            0.9992
        ],
        "tier_decisions": 560,
        "coverage": 0.4054
    },
    "tiers": {
        "HIGH_RISK_WRITE": {
            "threshold": 0.06,
            "rule": "smallest threshold with at least 99% precision over at least 20 decisions",
            "at_threshold": {
                "threshold": 0.06,
                "automatic": 50,
                "correct": 50,
                "precision": 1.0,
                "precision_ci": [
                    0.9286,
                    1.0
                ],
                "tier_decisions": 110,
                "coverage": 0.4545
            }
        },
        "LOW_RISK_WRITE": {
            "threshold": 0.08,
            "rule": "fewer than 20 qualifying decisions: the higher of its own 99% threshold and that of HIGH_RISK_WRITE",
            "at_threshold": {
                "threshold": 0.08,
                "automatic": 17,
                "correct": 17,
                "precision": 1.0,
                "precision_ci": [
                    0.8157,
                    1.0
                ],
                "tier_decisions": 54,
                "coverage": 0.3148
            }
        },
        "READ_ONLY": {
            "threshold": 0.04,
            "rule": "smallest threshold with at least 99% precision over at least 20 decisions",
            "at_threshold": {
                "threshold": 0.04,
                "automatic": 160,
                "correct": 159,
                "precision": 0.9938,
                "precision_ci": [
                    0.9655,
                    0.9989
                ],
                "tier_decisions": 396,
                "coverage": 0.404
            }
        }
    }
}
