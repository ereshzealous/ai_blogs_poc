"""The simulated sources: what the index copy knows versus what the source says at as_of."""

from knowledge_rag.util import ts


def test_withdrawal_after_the_watermark_is_invisible_to_the_index_copy(w):
    at_wm = w.sources.state("RB-PAY-002@v3", w.sources.watermark)
    now = w.sources.state("RB-PAY-002@v3", w.as_of)
    assert at_wm.status == "active" and now.status == "withdrawn"


def test_acl_narrowed_after_the_watermark(w):
    assert "eng-all" in w.sources.state("VENDOR-ACN-01@v1", w.sources.watermark).acl
    assert w.sources.state("VENDOR-ACN-01@v1", w.as_of).acl == ("vendor-mgmt",)


def test_superseded_at_source_points_to_a_version_the_index_never_copied(w):
    st = w.sources.state("RB-NOT-004@v1", w.as_of)
    assert st.status == "superseded" and st.superseded_by == "RB-NOT-004@v2"
    assert not w.sources.in_index_copy("RB-NOT-004@v2") and w.sources.in_index_copy("RB-NOT-004@v1")


def test_valid_from_is_not_ingested_at(w):
    v5 = w.sources.get("RB-CHK-007@v5")
    assert w.sources.in_index_copy(v5.key) and ts(v5.valid_from) > w.as_of   # indexed, not yet effective


def test_structured_records_are_live(w):
    recs = w.deployments.query("acme", "production", "checkout-api", version="4.17.0")
    assert recs and "datasource.maxPoolSize 50 -> 10" in recs[0]["config_diff"]
    assert w.cmdb.runbook_of_record("acme", "production", "checkout-api", "checkout-api/latency-after-deploy") == "RB-CHK-007"
