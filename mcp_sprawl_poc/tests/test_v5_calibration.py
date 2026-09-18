"""Discovery v5 calibration: thresholds per risk tier from recorded decisions, and decisions from recorded rows."""

from __future__ import annotations

from benchmark.reports import v5_calibration
from benchmark.reports.v5_calibration import calibrate, render_markdown, write_thresholds
from control_plane.discovery.resolver import decide
from control_plane.registry.capabilities import CapabilityCatalog

CATALOG = CapabilityCatalog.load()
TOOL = {"READ_ONLY": ("observability.query_latency", "latency.read", "observability", "read"),
        "LOW_RISK_WRITE": ("collaboration.post_message", "chat-message.post", "collaboration", "write"),
        "HIGH_RISK_WRITE": ("source_control.rollback_release", "service-release.rollback", "delivery", "write")}


def first(tier, margin, domain=None, operation=None):
    tool, cap, dom, op = TOOL[tier]
    return {"capabilities": None, "ranking": [{"capability": cap, "tool_id": tool, "score": 1.9}], "margin": margin,
            "evidence_types": [], "rewrite": {"domain": domain or dom, "operation": operation or op}}


def row(i, tier, margin, correct, agree=True, **kw):
    tool = TOOL[tier][0] if agree else "itsm.get_incident"
    return {"_id": i, "v5_first": first(tier, margin, **kw), "selected": tool, "capability_correct": correct}


def test_decisions_are_rebuilt_from_a_recorded_row():
    d = decide(first("READ_ONLY", 0.3), "observability.query_latency", {"READ_ONLY": 0.2}, catalog=CATALOG)
    assert d.auto and d.tier == "READ_ONLY" and d.checks["operation"] and d.checks["system"]
    assert not decide(first("READ_ONLY", 0.1), "observability.query_latency", {"READ_ONLY": 0.2}, catalog=CATALOG).auto


def test_the_model_rewrite_must_agree_with_the_leading_capability():
    wrong_system = first("READ_ONLY", 0.5, domain="itsm")
    assert not decide(wrong_system, "observability.query_latency", {"READ_ONLY": 0.0}, catalog=CATALOG).auto
    wrong_effect = first("READ_ONLY", 0.5, operation="write")
    assert not decide(wrong_effect, "observability.query_latency", {"READ_ONLY": 0.0}, catalog=CATALOG).auto


def test_the_smallest_threshold_with_99_percent_precision_over_20_decisions():
    rows = [row(i, "READ_ONLY", 0.02 * (i % 10), correct=(i % 10) >= 2) for i in range(100)]
    cal = calibrate(rows, CATALOG)
    assert cal["thresholds"]["READ_ONLY"] == 0.04
    at = cal["tiers"]["READ_ONLY"]["at_threshold"]
    assert (at["automatic"], at["correct"], at["tier_decisions"]) == (80, 80, 100)


def test_a_tier_with_too_few_qualifying_decisions_takes_the_stricter_tiers_threshold():
    rows = [row(i, "HIGH_RISK_WRITE", 0.5, correct=True) for i in range(30)]
    rows += [row(100 + i, "LOW_RISK_WRITE", 0.5, correct=True) for i in range(5)]
    cal = calibrate(rows, CATALOG)
    assert cal["thresholds"]["HIGH_RISK_WRITE"] == 0.0
    assert cal["thresholds"]["LOW_RISK_WRITE"] == 0.0 and "HIGH_RISK_WRITE" in cal["tiers"]["LOW_RISK_WRITE"]["rule"]
    assert cal["thresholds"]["READ_ONLY"] is None


def test_an_inherited_threshold_is_never_below_the_tiers_own_99_percent_point():
    rows = [row(i, "HIGH_RISK_WRITE", 0.02, correct=True) for i in range(30)]
    rows += [row(100, "LOW_RISK_WRITE", 0.02, correct=False)] + [row(101 + i, "LOW_RISK_WRITE", 0.5, correct=True) for i in range(5)]
    cal = calibrate(rows, CATALOG)
    assert cal["thresholds"]["HIGH_RISK_WRITE"] == 0.0
    assert cal["thresholds"]["LOW_RISK_WRITE"] == 0.04


def test_a_tier_that_never_reaches_99_percent_always_asks():
    rows = [row(i, "READ_ONLY", 0.9, correct=i % 5 != 0) for i in range(50)]
    assert calibrate(rows, CATALOG)["thresholds"]["READ_ONLY"] is None


def test_disagreeing_picks_never_count_as_automatic():
    rows = [row(i, "READ_ONLY", 0.9, correct=True, agree=False) for i in range(40)]
    cal = calibrate(rows, CATALOG)
    assert cal["tiers"]["READ_ONLY"]["curve"][0]["automatic"] == 0 and cal["thresholds"]["READ_ONLY"] is None


def test_the_frozen_file_and_the_report(tmp_path, monkeypatch):
    rows = [row(i, "READ_ONLY", 0.3, correct=True) for i in range(25)]
    cal = calibrate(rows, CATALOG)
    path = tmp_path / "v5_thresholds.py"
    write_thresholds(cal, ["run-a"], path)
    namespace: dict = {}
    exec(path.read_text(), namespace)
    assert namespace["THRESHOLDS"] == {"HIGH_RISK_WRITE": None, "LOW_RISK_WRITE": None, "READ_ONLY": 0.0}
    assert namespace["CALIBRATION"]["runs"] == ["run-a"]
    md = render_markdown(cal, ["run-a"])
    assert "| READ_ONLY | 25 | 0.00 | 25 (100%) |" in md
    assert v5_calibration.THRESHOLDS_FILE.name == "v5_thresholds.py"
