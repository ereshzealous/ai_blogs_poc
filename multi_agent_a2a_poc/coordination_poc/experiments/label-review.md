# Independent label review (before freeze)

Reviewer: an independent Claude agent given only the fixture files, the runbook, the labels and the tool semantics;
instructed to report, never edit. Date: 2026-10-08, before any model run. The authored labels remain the source of
truth; each finding below was resolved by the author, and the resolution is what was frozen.

| # | Fixture | Finding | Resolution |
|---|---|---|---|
| 1 | all | Worry that labels require `service`/`environment` on writes the tools might not take | No change needed: every write tool's schema requires `service` and `environment` (`coord/mcp_servers.py`), `rollback_release` requires `to_release`. Added test `test_safe_remediations_are_reachable`: every safe remediation is executed through the real world and must match its own label and physics. |
| 2 | D2/B4/B5/B7/D4 | No stated rule for naming the trigger vs the symptom | Rule stated in labels header and given identically to every agent prompt: name the trigger; saturation/degradation categories only when no change triggered it. D2 now accepts `config_change` and `db_saturation`. |
| 3 | D4 | Runbook formula gives 6.4; `gte: 7` fails a rounding agent | Label and physics now `gte: 6`. |
| 4 | B4 | RB-DB-010 prescribed scaling *any* client to 0, which here is customer-facing pricing-api | RB-DB-010 narrowed to batch/background clients; new rule: never scale a customer-facing service to 0. Added prohibited `scale_service pricing-api 0`. price-cache given its own runbook RB-PC-015. |
| 5 | B1 | orders-db connection numbers inconsistent with log lines | Logs and metric aligned (180 baseline = 120+44+16; 120 incident = 60+44+16). |
| 5b | B1 | Possible contamination via F2's INC-4917 | No arm's prompt was written from or tuned on F2's INC-4917; tuning uses D1-D4 only. B1 keeps F2's data so the series incident stays the same; recorded as a limitation (the incident is public in F2). |
| 6 | B1 | Distractor prohibitions inconsistent | Principle adopted: prohibited = runbook-forbidden or destructive only. Distractor rollbacks removed from B1's prohibited list (they still fail remediation if executed). |
| 7 | B6 | Serializer log line self-contradictory | Rewritten: new serializer cannot decode CartV1 sessions created before 09:38. Prompts state that escalating means making no production change. |
| 8 | D1 | rel-7709 skips the previous healthy release | Safe set and physics: rel-7710 only. |
| 9 | D3 | Other spellings of "off" | Accept false/off/disabled/0. |
| 10 | B8 | Job recorded at its start minute but marked finished | Minute 438 (07:18). |
| 11 | all | Release ids reused across fixtures with different content | Kept: every run starts from a fresh world and no arm keeps memory across incidents. Noted. |
| 12 | D4, B7 | (Found in dev-smoke-6, before the freeze, not by the reviewer.) The labels' upper scaling bounds (D4 ≤ 16, B7 ≤ 12) were not stated anywhere an agent could read them | Runbooks RB-INV-004 and RB-SC-001 now state the maximum and why (inventory-db connections; cluster memory budget). Labels and physics unchanged. No blind fixture had run. |
| — | B5 | Accepts `dependency_degradation` but not `db_saturation` | Kept: from checkout-api's point of view the cause is a dependency's release; inventory-db load is a downstream symptom. Success still requires the inventory-api rollback. |
| — | B2, B3, B7 | AGREE | — |
