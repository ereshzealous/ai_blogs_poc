# Keep a root-level `pytest` run from colliding on the assembled public copy and the vendored kit.
# The POC's own tests run from redteam_poc/ (see the Makefile: `make test`).
collect_ignore_glob = ["public/*", "redteam_poc/vendor/*"]
