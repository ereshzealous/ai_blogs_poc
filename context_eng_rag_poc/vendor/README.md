# vendor/

Pinned copies, per the series rule "copy, don't link". Never edited in place. Only what `tools/build_docs.py` imports.

- `evidence_kit/`: **evidence-kit 3.6.0** (`__version__` in `evidence_kit/__init__.py`), the reading template: Medium
  skin (`skin_css("medium")`, `medium_js()`), `evidence_kit.medium` (kind, claim, callout) and
  `evidence_kit.components.md`. The whole package is copied unchanged (its Lab Console assets included, unused here), from
  `../evals_obs_reliability/vendor/evidence_kit` on 2026-10-08; that copy came from `../ai_control_plane/vendor/evidence_kit`
  (byte-identical, checked with `diff -r` on 2026-10-08).
- `kit5/evidence_kit/publication.py`: **evidence-kit 5.2.0** (`kit5/VERSION`), the publication local-path scan
  (`local_path_findings`), loaded by file path because `evidence_kit` above is the pinned 3.6.0 package. Standalone
  (standard library only); copied alone, from `../evals_obs_reliability/vendor/kit5/evidence_kit/publication.py` on
  2026-10-08 (byte-identical to `../ai_control_plane/vendor/kit5/evidence_kit/publication.py`). The rest of kit5 (the
  `pae-proof/v1` proof pack) is not used by C1's build and is not copied.

Not vendored: evidence-kit 4.1.0 (`kit4`, the R1 + R2 Lab Console renderer); add it when `make console` is implemented.
