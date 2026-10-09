"""Ingestion: the nightly connector run that copies prose sources into the retrieval index.

One unit per document section, with full lineage: stable unit id (`doc@version#section`), document identity and version,
content hash, character span in the document body, the source's metadata *as it was at the watermark* (tenant,
environments, services, status, effective window, supersession, procedure key, action, approval, owner, ACL), and the
ingestion time. Qualifier sections (approvals, exceptions, cautions, limits) are marked so the packer can keep them with
the procedure they qualify.

Structured systems of record (deployments, CMDB) are not ingested: they are queried live.

    uv run python -m knowledge_rag.ingest            # -> index/units.jsonl, index/manifest.json
"""

from __future__ import annotations

import json
import re
import sys

from knowledge_rag.util import INDEX, config, sha256
from knowledge_rag.world import Document, load_documents, SourceAPI

VOCAB = config("vocabulary.yaml")


def is_qualifier(heading: str, text: str) -> bool:
    h, t = heading.lower(), text.lower()
    return any(c in h for c in VOCAB["qualifier_headings"]) or any(t.startswith(c) for c in VOCAB["qualifier_openings"])


def index_text(doc: Document, heading: str, text: str) -> str:
    """What the embedding and BM25 see: a contextual header (document id, title, section) and the section text."""
    return f"{doc.doc_id} · {doc.title} — {heading}\n{text}"


def units_for(doc: Document, ingested_at: str) -> list[dict]:
    out, pos = [], 0
    body_parts = []
    for i, s in enumerate(doc.sections):
        start = pos
        body_parts.append(s.text)
        pos += len(s.text) + 2   # sections are joined by a blank line in the document body
        out.append({
            "unit_id": f"{doc.key}#{s.slug}",
            "doc_id": doc.doc_id, "version": doc.version, "doc_key": doc.key, "source": doc.source,
            "doc_type": doc.doc_type, "title": doc.title, "heading": s.heading, "section_index": i,
            "text": s.text, "index_text": index_text(doc, s.heading, s.text),
            "content_hash": sha256(re.sub(r"\s+", " ", s.text.lower()).strip()),
            "char_span": [start, start + len(s.text)],
            "qualifier": is_qualifier(s.heading, s.text),
            "meta": {"tenant": doc.tenant, "environments": list(doc.environments), "services": list(doc.services),
                     "status": doc.status, "valid_from": doc.valid_from, "valid_to": doc.valid_to,
                     "superseded_by": doc.superseded_by, "supersedes": doc.supersedes, "procedure_key": doc.procedure_key,
                     "action": doc.action, "approval": doc.approval, "owner": doc.owner, "acl": list(doc.acl),
                     "updated_at": doc.updated_at},
            "ingested_at": ingested_at,
        })
    return out


def build() -> dict:
    docs = load_documents()
    api = SourceAPI(docs)
    wm = api.watermark.strftime("%Y-%m-%dT%H:%M:%SZ")
    units = []
    for d in sorted(docs, key=lambda d: (d.source, d.doc_id, d.version)):
        if not api.in_index_copy(d.key):
            continue   # published after the watermark: only the source API knows it
        units += units_for(d, wm)
    INDEX.mkdir(exist_ok=True)
    lines = [json.dumps(u, sort_keys=True, ensure_ascii=False) for u in units]
    (INDEX / "units.jsonl").write_text("\n".join(lines) + "\n")
    manifest = {
        "watermark": wm, "documents": len({u["doc_key"] for u in units}), "units": len(units),
        "qualifier_units": sum(u["qualifier"] for u in units),
        "by_source": {s: sum(1 for u in units if u["source"] == s) for s in sorted({u["source"] for u in units})},
        "units_sha256": sha256("\n".join(lines) + "\n"),
        "note": "prose sources only, copied at the watermark; structured systems are queried live and never indexed",
    }
    (INDEX / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest


def load_units() -> list[dict]:
    return [json.loads(line) for line in (INDEX / "units.jsonl").read_text().splitlines() if line.strip()]


if __name__ == "__main__":
    m = build()
    json.dump(m, sys.stdout, indent=1)
    print()
