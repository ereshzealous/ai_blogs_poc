"""Build the run report for the published F2 run: docs/results/layered-agent-platform-run-report.{md,html,pdf}.

    python3 tools/build_run_report.py

Writes docs/source/report.src.md (generated; do not edit by hand) and renders it with build_docs as the "report" track.
Aggregates are {{fact}} tokens resolved from the run's facts.json.  The per-scenario and probe tables are read from the
run's own files (scenarios/<id>/score.json, experiments/E6_probes.json) by this script; nothing is typed by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_docs as bd  # noqa: E402
from scenario_view import model_errors, scenario_matrix  # noqa: E402

PANELS: dict = {}

ARCH = ("monolith", "layered")
BEHAVIOUR = ["E1", "E2", "E3", "E4", "E5", "E7"]


def plan() -> dict:
    import yaml

    return yaml.safe_load((bd.POC / "experiments" / "preregistration" / "experiment_plan.yaml").read_text())["experiments"]


def row(*cells) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def t(key: str) -> str:
    return "{{" + key + "}}"


def pair(key: str) -> tuple[str, str]:
    e, _, rest = key.partition(".")
    return t(f"{e}.monolith.{rest}"), t(f"{e}.layered.{rest}")


def scenario_rows(run: Path) -> list[str]:
    out = [row("Scenario", "Model", "Checks", "Final status", "Physical rollbacks", "Model calls", "Tokens", "Wall s", "SIGKILL",
               "Model calls after kill", "Failed checks"), row(*["---"] * 11)]
    order = {e: i for i, e in enumerate(["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E9"])}
    dirs = sorted((run / "scenarios").iterdir(), key=lambda d: (order[d.name.split("-")[0]], d.name.split("-")[1] != "monolith", d.name))
    for d in dirs:
        s = json.loads((d / "score.json").read_text())
        failed = ", ".join(f"`{k}`" for k, v in (s.get("checks") or {}).items() if not v) or "none"
        after = s.get("model_calls_after_crash")
        out.append(row(f"`{d.name}`", s.get("model", ""), f'{s["checks_passed"]}/{s["checks_total"]}', s.get("final_status") or "none (killed, not resumed)",
                       s.get("physical_rollbacks"), s.get("model_calls"), bd.fmt(s.get("tokens")), s.get("wall_s_total"), s.get("sigkills", 0),
                       "n/a" if after is None else after, failed))
    return out


def probe_rows(run: Path) -> list[str]:
    p = json.loads((run / "experiments" / "E6_probes.json").read_text())
    by = {a: {r["id"]: r for r in p[a]} for a in ARCH}
    out = [row("Probe", "What it tries", "Monolith", "Layered"), row("---", "---", "---", "---")]
    for pr in p["probes"]:
        def cell(a: str) -> str:
            r = by[a].get(pr["id"])
            if r is None:
                return "n/a"
            n = r.get("backend_executions")
            return r["outcome"].replace("_", " ") + ("" if n is None else f" ({n} backend exec.)")
        out.append(row(pr["id"], pr["what"], cell("monolith"), cell("layered")))
    return out


def source(run: Path) -> str:
    P = plan()
    L: list[str] = []
    a = L.append
    a("---")
    a("title: INC-4917 run report")
    a("subtitle: Monolith versus layered agent platform, {{integrity.scenarios_expected}} preregistered scenarios, recorded on local models with real MCP servers and real SIGKILLs")
    a("byline: F2 · Production AI Engineering")
    a("kicker: Recorded run {{run_id}}")
    a("filed: 2026-09-29")
    a("run: {{run_id}}")
    a("tags: run report, evidence, INC-4917, layered architecture, fault injection")
    a("---")
    a("")
    a("This is the forensic record of the run. For the reader-facing story (question, results that matter, what failed, claim map) see the "
      f"[Evidence Check]({bd.EVIDENCE}.html). Each run's input, output, steps and data lineage are in the [Lab Console](lab-console.html).")
    a("")
    a("This report states what the published run measured, scenario by scenario. Every aggregate is taken from `facts.json`, "
      "which is generated from the run's `summary.json`; the per-scenario tables are read from each scenario's `score.json`. "
      "Where the layered platform lost, or where a check failed for a reason the architecture did not cause, the report says so.")
    a("")
    a(":::: brief At a glance | What the run measured | Recorded run {{run_id}}, plan {{plan_id}}")
    a("problem: A checkout-api incident (INC-4917): release rel-2031 cut the DB pool from 50 to 10. The agent must diagnose, get approval, roll back to rel-2030 once, verify, and update the incident.")
    a("test: The same task on a single-file agent (monolith) and on a six-layer platform, across E1–E9, with lost responses, SIGKILLs, adversarial prompts and code changes.")
    a("result: Both architectures solve the clean incident. Under faults the monolith repeats side effects and model work; the layered platform does not. The layered platform lost on change locality for the dry-run requirement (E9).")
    a("limits: One scenario, simulated enterprise backends, local models at temperature 0, three seeds. Not a reliability estimate.")
    a("meta: {{integrity.scenarios_present}}/{{integrity.scenarios_expected}} | scenarios ran")
    a("meta: {{integrity.sigkills}} | real SIGKILLs")
    a("meta: {{replay.model_calls_served_from_tape}} | model calls recorded")
    a("meta: {{headline.tests}} | tests passed (0 failed)")
    a("::::")
    a("")
    a("## Headline results")
    a("")
    a("::: kind MEASURED | summary.json of the published run")
    a("")
    a(row("Question", "Measure", "Monolith", "Layered"))
    a(row("---", "---", "---", "---"))
    a(row("E1: does layering keep the capability?", "runs passing all 8 checks", t("headline.e1_runs_all_checks.monolith"), t("headline.e1_runs_all_checks.layered")))
    a(row("E4: lost reply after the rollback committed", "duplicate physical rollbacks (3 runs)", t("headline.e4_duplicate_rollbacks.monolith"), t("headline.e4_duplicate_rollbacks.layered")))
    a(row("E5: SIGKILL right after the rollback", "physical rollbacks (3 runs)", t("headline.e5_physical_rollbacks_total.monolith"), t("headline.e5_physical_rollbacks_total.layered")))
    a(row("E5: SIGKILL right after the rollback", "median tokens spent after the kill", t("headline.e5_median_tokens_after_crash.monolith"), t("headline.e5_median_tokens_after_crash.layered")))
    a(row("E6: deterministic write probes", "writes executed", t("headline.e6_probe_writes_executed.monolith"), t("headline.e6_probe_writes_executed.layered")))
    a(row("E8: one request to one tool action", "median trace score", t("headline.e8_median_trace_score.monolith"), t("headline.e8_median_trace_score.layered")))
    a(row("E2: model swap", "concerns touched", t("headline.e2_concerns_touched.monolith"), t("headline.e2_concerns_touched.layered")))
    a(row("E3: deployment tool v2", "concerns touched", t("headline.e3_concerns_touched.monolith"), t("headline.e3_concerns_touched.layered")))
    a(row("E9: dry-run requirement", "files changed", t("headline.e9_files_changed.monolith"), t("headline.e9_files_changed.layered")))
    a("")
    a("")
    a("## Environment and integrity")
    a("")
    a("::: kind RECORDED | manifest.json, verification.json, replay_comparison.json")
    a("")
    a(row("Item", "Value"))
    a(row("---", "---"))
    for label, key in [("Run id", "manifest.run_id"), ("Started (UTC)", "manifest.started_utc"), ("Finished (UTC)", "manifest.finished_utc"),
                       ("Harness wall time (s)", "manifest.harness_wall_s"), ("Machine", "manifest.cpu"), ("Memory (GB)", "manifest.memory_gb"),
                       ("Platform", "manifest.platform"), ("Python", "manifest.python"), ("Ollama", "manifest.ollama_version"),
                       ("MCP Python SDK", "manifest.mcp_sdk"), ("Model A", "models.A"), ("Model A digest", "model.A.digest"),
                       ("Model B", "models.B"), ("Model B digest", "model.B.digest"), ("Plan", "plan_id"), ("Plan SHA-256", "plan_sha256"),
                       ("Evidence revisions", "revisions")]:
        a(row(label, f"`{t(key)}`" if "sha" in key or "digest" in key else t(key)))
    a("")
    a(row("Integrity check", "Result"))
    a(row("---", "---"))
    a(row("Preregistered scenarios present", f'{t("integrity.scenarios_present")} of {t("integrity.scenarios_expected")}'))
    a(row("Replay tape misses", t("integrity.tape_misses")))
    a(row("Real SIGKILLs delivered", t("integrity.sigkills")))
    a(row("Replay of the whole run", f'identical: {t("replay.identical")}; {t("replay.model_calls_served_from_tape")} model calls served from tape, {t("replay.fresh_model_calls")} fresh'))
    v = json.loads((run / "verification.json").read_text())
    a(row("Run verification (`verification.json`)",
          f'{v["passed"]}/{v["total"]} checks passed, {v.get("recomputed", 0)} of them recomputed from raw evidence'))
    a("")
    a("Frozen input hashes (first 12 hex characters of SHA-256):")
    a("")
    a(row("Input", "Hash"))
    a(row("---", "---"))
    for k in ["experiment_plan", "scenario", "runbooks", "memory_seed", "policy", "capabilities", "model_config", "prompts", "scoring",
              "change_patches", "mcp_servers", "tool_schemas", "source_tree"]:
        a(row(k.replace("_", " "), f"`{t('hash.' + k)}`"))
    a("")
    a(":::: callout Evidence revision r2")
    a("After the run, the trace scorer (`experiments/scorers/traces.py`) was revised and declared as revision r2 in the manifest, with the "
      "new file hash. It affects E8 only. The run verifier checks that every frozen input is unchanged or changed only by a declared revision.")
    a("::::")
    a("")
    a("## Tests")
    a("")
    a("::: kind MEASURED | tests.json (pytest inside the recorded run)")
    a("")
    a(row("Category", "Passed", "Failed", "Skipped"))
    a(row("---", "---", "---", "---"))
    for c in ["unit", "contract", "architecture", "integration", "fault_injection", "model", "evidence"]:
        a(row(c.replace("_", " "), t(f"tests.by_category.{c}.passed"), t(f"tests.by_category.{c}.failed"), t(f"tests.by_category.{c}.skipped")))
    a(row("**Total**", f'**{t("tests.passed")}** of {t("tests.total")}', t("tests.failed"), t("tests.skipped")))
    a("")
    a("The skipped evidence tests check the published run itself, so they skip inside the run that is still being written; "
      f'{t("tests.require_local_models")} tests need the local Ollama models.')
    a("")
    a("## Behaviour experiments")
    a("")
    a("::: kind MEASURED | summary.json → experiments; per-run values in scenarios/<id>/score.json")
    a("")
    a(row("Experiment", "Architecture", "Runs", "All 8 checks", "Checks", "Physical rollbacks", "Median model calls", "Median tokens", "Median wall s"))
    a(row(*["---"] * 9))
    for e in BEHAVIOUR:
        for arch in ARCH:
            k = f"{e}.{arch}."
            a(row(f"{e} {P[e]['title']}", arch, t(k + "runs"), t(k + "runs_all_checks"), f'{t(k + "checks_passed")}/{t(k + "checks_total")}',
                  t(k + "physical_rollbacks"), t(k + "median_model_calls"), t(k + "median_tokens"), t(k + "median_wall_s")))
    a("")
    for e in BEHAVIOUR:
        a(f"### {e} · {P[e]['title']}")
        a("")
        a(f"*{P[e]['question']}*")
        a("")
        a(f"Hypothesis (preregistered): {P[e]['hypothesis']}")
        a("")
        if e == "E1":
            a(f'Both architectures passed all eight checks on every seed: monolith {t("E1.monolith.checks_passed")}/{t("E1.monolith.checks_total")}, '
              f'layered {t("E1.layered.checks_passed")}/{t("E1.layered.checks_total")}. The monolith used a median of {t("E1.monolith.median_tokens")} tokens, '
              f'the layered platform {t("E1.layered.median_tokens")}.')
        elif e == "E2":
            a(f'Under model B ({t("E2.model_b")}) both architectures again passed every check: monolith {t("E2.monolith.checks_passed")}/{t("E2.monolith.checks_total")}, '
              f'layered {t("E2.layered.checks_passed")}/{t("E2.layered.checks_total")}. The change-locality result is in the next section.')
        elif e == "E3":
            a(f'Both runs against `deploy_v2` completed with all checks. The v2 rollback stayed behind approval in both: monolith {t("E3.monolith.v2_rollback_gated")}, '
              f'layered {t("E3.layered.v2_rollback_gated")}.')
        elif e == "E4":
            a(f'In the monolith, the model called the rollback again after the timeout error, with no idempotency key: {t("E4.monolith.backend_rollback_requests")} backend requests and '
              f'{t("E4.monolith.physical_rollbacks")} physical rollbacks per run, so it failed `rollback_exactly_once` in '
              f'{t("E4.monolith.runs_with_duplicate_rollback")} of {t("E4.monolith.runs")} runs. The layered gateway also retried '
              f'({t("E4.layered.backend_rollback_requests")} backend requests per run), but sent the same op id each time; the backend replayed its stored result '
              f'({t("E4.layered.backend_idempotent_replays")} idempotent replays), so physical rollbacks were {t("E4.layered.physical_rollbacks")}.')
        elif e == "E5":
            a(f'After the SIGKILL the monolith started over. Per run (seeds 11, 13, 7) it made {t("E5.monolith.model_calls_after_crash")} model calls and spent '
              f'{t("E5.monolith.tokens_after_crash")} tokens after the kill, and physically rolled back {t("E5.monolith.physical_rollbacks")} times. '
              f'The layered platform resumed from its checkpoint ({t("E5.layered.lease_takeovers")} lease takeovers), re-ran only the `execute` step, and spent '
              f'{t("E5.layered.tokens_after_crash")} tokens after the kill per run (None: seed 7 was never killed; see below).')
            a("")
            a(f'**Layered seed 7 failed for a reason the layers did not prevent.** The model proposed `to_release: "previous"`; the deploy server rejected it '
              f'("previous is not a release of checkout-api in production"), so no rollback happened, the crash point after a successful rollback was never reached, '
              f'and the run scored 4/8. Layered E5 therefore shows {t("E5.layered.runs_all_checks")} of {t("E5.layered.runs")} runs passing and '
              f'{t("E5.layered.physical_rollbacks_total")} physical rollbacks in total. It also needed {t("E5.layered.structured_output_repairs")} structured-output repairs.')
            a("")
        elif e == "E7":
            a(f'The process was killed while waiting for approval. The monolith kept its workflow in the model context, so after the restart nothing survived: '
              f'workflow id {t("E7.monolith.workflow_id_survives")}, completed steps {t("E7.monolith.completed_steps_survive")}, approval state '
              f'{t("E7.monolith.approval_state_survives")}. It re-ran with {t("E7.monolith.model_calls_after_crash")} more model calls, never produced a final report, '
              f'and scored {t("E7.monolith.checks_passed")}/{t("E7.monolith.checks_total")}. The layered platform restored its workflow '
              f'(workflow id {t("E7.layered.workflow_id_survives")}, approval state {t("E7.layered.approval_state_survives")}) and scored '
              f'{t("E7.layered.checks_passed")}/{t("E7.layered.checks_total")}.')
            a("")
            me = model_errors(bd.published_run() / "scenarios" / "E7-monolith-s7")
            if me["n"]:
                a(f'Why the monolith produced no report: after the restart it re-ran the investigation and executed the rollback, then the model service '
                  f'returned “{me["status"]}” on {me["n"]} consecutive attempts and the process exited with code {", ".join(map(str, me["exits"]))} '
                  f'(`scenarios/E7-monolith-s7/raw/agent_log.jsonl`, `logs/01-monolith-run.log`). The missing diagnosis and incident update are that error, '
                  'not a wrong answer. It is an error in the run, recorded as such in the Lab Console.')
                a("")
            a(f'A declared re-run of the monolith case (`supplementary/E7-monolith-s7`) gave the same outcome: {t("supplementary.E7-monolith-s7.checks_passed")}/'
              f'{t("supplementary.E7-monolith-s7.checks_total")}, {t("supplementary.E7-monolith-s7.model_calls_after_crash")} model calls after the kill.')
        a("")
    a("## E6 · Approval and governance boundary")
    a("")
    a("::: kind MEASURED | experiments/E6_probes.json and the adversarial scenarios")
    a("")
    a(f"*{P['E6']['question']}*")
    a("")
    a("Seven deterministic probes were sent straight at each architecture's write path, without a model.")
    a("")
    L.extend(probe_rows(run))
    a("")
    a(f'Totals: the monolith executed {t("E6.monolith_probes_executed_writes")} writes, asked a human for {t("E6.monolith_probes_asked_human")} and had no way to express '
      f'{t("E6.monolith_probes_not_expressible")} of the rules. The layered platform blocked {t("E6.layered_probes_blocked")} and executed '
      f'{t("E6.layered_probes_executed_writes")} writes.')
    a("")
    a(f'In the adversarial run (a user message claiming prior approval and asking for a restart), the monolith executed {t("E6.adversarial.monolith.restarts_executed")} production restart and '
      f'scored {t("E6.adversarial.monolith.checks_passed")}/{t("E6.adversarial.monolith.checks_total")}; the layered platform executed '
      f'{t("E6.adversarial.layered.restarts_executed")} restarts and scored {t("E6.adversarial.layered.checks_passed")}/{t("E6.adversarial.layered.checks_total")}.')
    a("")
    a("")
    a("## E8 · Trace completeness")
    a("")
    a("::: kind MEASURED | traces scored by experiments/scorers/traces.py (revision r2)")
    a("")
    a(row("", "Monolith", "Layered"))
    a(row("---", "---", "---"))
    for label, k in [("Runs scored", "runs"), ("Trace elements", "elements"), ("Median score", "median_score"), ("Minimum score", "min_score"),
                     ("Present in every run", "present_in_all_runs"), ("Missing in some run", "missing_in_any_run")]:
        m, l_ = pair(f"E8.{k}")
        a(row(label, m, l_))
    a("")
    a(f'In the layered E5 runs, {t("E8.layered.crash_runs_single_trace_across_processes")} of {t("E8.layered.crash_runs")} kept one trace across all their processes (seed 7 was never killed).')
    a("")
    a("## Change locality · E2, E3, E9")
    a("")
    a("::: kind MEASURED | git diff of frozen patches applied in throwaway worktrees")
    a("")
    a(row("Change", "Architecture", "Files", "Lines +/−", "Concerns touched", "Spill-over", "Review surface (concerns)", "Review surface (LOC)"))
    a(row(*["---"] * 8))
    for e in ["E2", "E3", "E9"]:
        for arch in ARCH:
            k = f"{e}.change.{arch}."
            a(row(f"{e} {P[e]['title']}", arch, t(k + "files_changed"), f'+{t(k + "lines_added")} / −{t(k + "lines_removed")}', t(k + "concerns_touched"),
                  t(k + "spill_over_n"), t(k + "review_surface_concerns_n"), t(k + "review_surface_loc")))
    a("")
    a(f'**E9 went against the layered platform.** Adding a dry-run mode touched {t("E9.change.layered.files_changed")} files and '
      f'{t("E9.change.layered.concerns_touched_n")} concerns ({t("E9.change.layered.concerns_touched")}), because a new request option has to cross the contract, '
      f'the composition root and the CLI. The monolith change was {t("E9.change.monolith.files_changed")} file, though it mixed '
      f'{t("E9.change.monolith.concerns_touched_n")} concerns in it. In both dry runs, deploy writes were zero (monolith {t("E9.monolith.deploy_writes")}, '
      f'layered {t("E9.layered.deploy_writes")}); their rollback checks fail by design, because nothing is supposed to be rolled back.')
    a("")
    a("")
    a("## Every scenario")
    a("")
    a("::: kind RECORDED | scenarios/‹id›/score.json, one row per preregistered scenario")
    a("")
    a("Each outcome below is a sentence generated from that scenario's `score.json`: what physically happened, then the checks it passed.")
    a("")
    sh, smd = scenario_matrix(run, P)
    PANELS["scen"] = {"html": sh, "md": smd}
    a("::: html scen")
    a("")
    num = scenario_rows(run)
    import markdown as _md
    PANELS["scen_numbers"] = {"html": '<details class="ev-d"><summary>The same scenarios as numbers</summary>'
                              + _md.markdown("\n".join(num), extensions=["tables"]) + "</details>", "md": "\n".join(num)}
    a("::: html scen_numbers")
    a("")
    a("E8 has no scenarios of its own; it scores the traces of the runs above.")
    a("")
    a(":::: boundary What this run supports")
    a("supported: With the same model, prompts and tools, the layered platform kept side effects to one under a lost reply (E4) and a SIGKILL (E5), and spent no model work after a crash.")
    a("supported: Authorization decided in code blocked every deterministic write probe; the monolith's prompt-and-string gate executed two.")
    a("supported: Workflow and approval state survived a restart only where it lived outside the model context (E7).")
    a("not_shown: Reliability rates. Three seeds at temperature 0 on one incident are a demonstration, not a distribution.")
    a("not_shown: Behaviour on real enterprise backends; ITSM, deploy and observability are simulated (see docs/real_vs_simulated.md).")
    a("contradicted: 'Layering always localises change'. The dry-run requirement touched more files in the layered platform (E9).")
    a("contradicted: 'Layers stop model mistakes'. Layered E5 seed 7 failed on a bad rollback target the model produced.")
    a("::::")
    a("")
    a("## Files behind this report")
    a("")
    for f, what in [("summary.json", "aggregates (source of facts.json)"), ("facts.json", "the flat key/value facts used in every publication"),
                    ("manifest.json", "environment, hashes, revisions"), ("verification.json", "the run verifier's checks"),
                    ("replay_comparison.json", "record/replay identity"), ("tests.json", "pytest results"), ("scenarios/", "per-scenario scores, logs, ledgers and tapes"),
                    ("experiments/", "per-experiment aggregates and E6 probes"), ("diffs/", "change patches as applied")]:
        a(f"- `layered_architecture_poc/runs/{t('run_id')}/{f}`: {what}")
    a("")
    return "\n".join(L) + "\n"


def main() -> None:
    run = bd.published_run()
    src = bd.ROOT / "docs" / "source" / "report.src.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(source(run))
    (bd.ROOT / "docs" / "source" / "report.panels.json").write_text(json.dumps(PANELS, ensure_ascii=False))
    bd.build("report", bd.load_facts(), {})


if __name__ == "__main__":
    main()
