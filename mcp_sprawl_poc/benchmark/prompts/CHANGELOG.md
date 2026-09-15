# Golden-data changelog

Every change to `cases.yaml` after the first benchmark row was produced is listed here. Reports rescore **all** rows
from their raw selections with the current `cases.yaml`, so every row in a report is judged by the same labels; the
report records the SHA-256 of the `cases.yaml` it used.

## 2026-09-15 · before the published run

- **R01, V13: `to_version` is presence-only.** The prompts say "previous release" or "last release" without naming a
  version, and a single decision cannot look the version up. Found in the smoke run (`_scratch-smoke`), where every
  mode passed a guessed version.

## 2026-09-15 · during the published run `gpt-oss-20b-2026-09-15`

- **V18: `observability.search_traces` and `apm.find_traces` added as acceptable.** The request is to add a note
  containing "the ID of a slow checkout trace", but no trace ID is given, and the system prompt tells the model to make
  only the first call of a multi-step request. Finding the trace is that first call. Found while inspecting interim
  results for catalogs 10–50, where every mode chose `search_traces`. Disclosed because it was made after results
  were seen; it applies to all modes and catalogs equally through rescoring.
- **Reviewed and deliberately not changed:**
  - **X03:** the model chose a latency or health check, which cannot tell the database from the application.
  - **V17:** the model passed `environment: dev`, outside the schema's enum.
  - **R12:** the model passed `resolution_code: RolledBack`, outside the enum.
  - **V22:** the model asked which version to roll back to instead of calling a tool. It counts as "no call"; the
    report lists it among no-call responses rather than rescoring it.
