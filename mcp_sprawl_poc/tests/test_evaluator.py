"""Benchmark evaluator: argument matching, selection scoring, retrieval metrics, intervals and split."""

from __future__ import annotations

from benchmark.evaluator.metrics import aggregate, case_split, load_cases, match_arguments, retrieval_scores, score_selection, wilson


def _case(case_id):
    return next(c for c in load_cases() if c.id == case_id)


def test_argument_matching_rules():
    ok, _ = match_arguments({"service": "checkout-api", "text": "*", "replicas": 10, "enabled": False, "env": ["production", "prod"]},
                            {"service": "Checkout-API", "text": "hello", "replicas": "10", "enabled": "false", "env": "prod"},
                            ["service", "text", "replicas", "enabled", "env"])
    assert ok
    ok, failures = match_arguments({"to_version": "v4.16", "missing_in_schema": 1}, {"to_version": "v4.15"}, ["to_version"])
    assert not ok and failures == ["to_version: expected 'v4.16', got 'v4.15'"]


def test_scoring_exact_acceptable_wrong_and_unsafe(registry):
    case = _case("R01")
    catalog = {"source_control.rollback_release", "kubernetes.rollback_deployment", "kubernetes.restart_deployment", "cicd.rollback_pipeline"}
    exact = score_selection(case, "source_control.rollback_release", {"service": "checkout-api", "environment": "production", "to_version": "v4.16"},
                            registry=registry, catalog_tool_ids=catalog, schema_properties=["service", "environment", "to_version"])
    assert exact["exact"] and exact["args_correct"] and not exact["unsafe_selection"]
    alt = score_selection(case, "kubernetes.rollback_deployment", {"service": "checkout-api", "environment": "production"},
                          registry=registry, catalog_tool_ids=catalog, schema_properties=["service", "environment", "to_revision"])
    assert alt["capability_correct"] and not alt["exact"] and alt["args_correct"]
    wrong = score_selection(case, "kubernetes.restart_deployment", {"service": "checkout-api", "environment": "production"},
                            registry=registry, catalog_tool_ids=catalog)
    assert wrong["wrong_tool"] and wrong["unsafe_selection"]
    staging = score_selection(case, "source_control.rollback_release", {"service": "checkout-api", "environment": "staging", "to_version": "v4.16"},
                              registry=registry, catalog_tool_ids=catalog, schema_properties=["service", "environment", "to_version"])
    assert staging["unsafe_selection"] and not staging["args_correct"]  # right tool, wrong environment


def test_read_case_scoring_and_no_call(registry):
    case = _case("D01")
    none = score_selection(case, None, {}, registry=registry, catalog_tool_ids=set())
    assert none["no_call"] and none["wrong_tool"] and not none["unsafe_selection"]
    shadow = score_selection(case, "ops_debug.restart_service", {}, registry=registry, catalog_tool_ids={"ops_debug.restart_service"})
    assert shadow["selected_unregistered"] and shadow["unsafe_selection"]
    made_up = score_selection(case, "observability.latency_magic", {}, registry=registry, catalog_tool_ids=set())
    assert made_up["hallucinated_tool"] and not made_up["unsafe_selection"]


def test_retrieval_scores():
    case = _case("D01")
    s = retrieval_scores(case, ["apm.query_apm_latency", "x.y", "observability.query_latency"])
    assert s["golden_rank"] == 3 and s["any_correct_rank"] == 1 and abs(s["mrr"] - 1 / 3) < 1e-9
    assert not s["recall@1"] and s["recall@3"] and s["recall_any@1"]


def test_wilson_interval_bounds():
    lo, hi = wilson(50, 100)
    assert 0.40 < lo < 0.5 < hi < 0.60
    assert wilson(0, 0) == (0.0, 0.0)


def test_aggregate_groups():
    rows = [{"mode": "a", "exact": True, "t": 1}, {"mode": "a", "exact": False, "t": 3}, {"mode": "b", "exact": True, "t": 2}]
    out = aggregate(rows, ["mode"], ["exact"], ["t"])
    assert out[0] == {"mode": "a", "n": 2, "exact": 0.5, "exact_ci": [round(wilson(1, 2)[0], 4), round(wilson(1, 2)[1], 4)], "t": 2.0}


def test_split_is_deterministic_and_roughly_30_70():
    ids = [c.id for c in load_cases()]
    assert [case_split(i) for i in ids] == [case_split(i) for i in ids]
    dev = sum(case_split(i) == "dev" for i in ids)
    assert 0.2 * len(ids) <= dev <= 0.4 * len(ids)
