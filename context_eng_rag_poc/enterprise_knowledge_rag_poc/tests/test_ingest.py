"""Ingestion lineage: every unit traces back to one section of one document version."""

import json

from knowledge_rag.ingest import load_units
from knowledge_rag.util import INDEX, sha256
from knowledge_rag.world import load_documents


def test_unit_lineage_and_hashes():
    docs = {d.key: d for d in load_documents()}
    for u in load_units():
        d = docs[u["doc_key"]]
        sec = d.sections[u["section_index"]]
        assert u["unit_id"] == f"{d.key}#{sec.slug}"
        assert u["text"] == sec.text
        body = "\n\n".join(s.text for s in d.sections)
        a, b = u["char_span"]
        assert body[a:b] == sec.text
        assert u["ingested_at"] == "2026-09-22T02:00:00Z"


def test_manifest_matches_the_index():
    m = json.loads((INDEX / "manifest.json").read_text())
    text = (INDEX / "units.jsonl").read_text()
    assert m["units"] == len(load_units()) and m["units_sha256"] == sha256(text)


def test_qualifiers_are_marked():
    q = {u["unit_id"] for u in load_units() if u["qualifier"]}
    assert {"RB-CHK-007@v4#approval-and-exceptions", "RB-GEN-012@v1#exceptions", "RB-INV-004@v5#cache-caution",
            "RB-SRCH-040@v1#limits"} <= q
    assert "RB-CHK-007@v4#remediation" not in q


def test_structured_records_and_source_only_versions_are_not_indexed():
    ids = {u["unit_id"] for u in load_units()}
    assert not any(i.startswith(("dep:", "cmdb:")) for i in ids)
    assert not any(i.startswith(("RB-NOT-004@v2", "RB-CART-003@v3")) for i in ids)
