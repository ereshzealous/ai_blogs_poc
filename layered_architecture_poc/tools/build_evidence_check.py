"""Build the reader-facing Evidence Check for the published F2 run.

    python3 tools/build_evidence_check.py
      -> docs/source/evidence.src.md + docs/source/evidence.panels.json (generated; do not edit by hand)
      -> docs/results/layered-agent-platform-evidence-check.{md,html,pdf}
      -> verification/evidence_check_validation.json (must be PASS)

The run report (tools/build_run_report.py) stays the forensic record.  This page tells the evidence as a story:
question → what ran → contract → results that matter → what failed → integrity → claim map → boundary.

Every measured number is read from the run's own files (facts.json, summary.json, experiments/*.json,
scenarios/*/score.json, verification.json, replay_comparison.json, manifest.json) or from
verification/post_run_evidence_tests.json.  A missing field is a KeyError: the build fails instead of printing a default.
Numbers derived here (denominators, crash-conditioned counts) are labelled DERIVED and show their derivation.
"""
from __future__ import annotations

import html as H
import json
import re
import statistics
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_docs as bd  # noqa: E402
from evidence_kit import medium  # noqa: E402
from evidence_kit.components import md as inline  # noqa: E402
from scenario_view import model_errors, scenario_matrix  # noqa: E402

ROOT = bd.ROOT
POC = ROOT / "layered_architecture_poc"
RUN = bd.published_run()
REL = f"../../layered_architecture_poc/runs/{RUN.name}"  # from docs/results/
FACTS = bd.load_facts()


def invariant_rows() -> list[tuple[str, str, str]]:
    """The invariants, read from the one place they are defined: layered_architecture_poc/docs/invariants.yaml."""
    doc = yaml.safe_load((POC / "docs" / "invariants.yaml").read_text())
    rows = []
    for inv, body in sorted(doc["invariants"].items(), key=lambda kv: int(kv[0][1:])):
        how = []
        if body.get("static"):
            how.append("source rules")
        if body.get("tests"):
            how.append("tests")
        if body.get("experiments"):
            how.append(", ".join(body["experiments"]))
        if body.get("recomputed"):
            how.append("recomputed from raw")
        statement = body["statement"].rstrip(".")
        rows.append((inv, statement, "; ".join(how) or "stated only"))
    return rows


INVARIANTS = invariant_rows()
SUMMARY = json.loads((RUN / "summary.json").read_text())
MANIFEST = json.loads((RUN / "manifest.json").read_text())
VERIF = json.loads((RUN / "verification.json").read_text())
REPLAY = json.loads((RUN / "replay_comparison.json").read_text())
POST = json.loads((ROOT / "verification" / "post_run_evidence_tests.json").read_text())
PROBES = json.loads((RUN / "experiments" / "E6_probes.json").read_text())
E5X = json.loads((RUN / "experiments" / "E5.json").read_text())
PLAN = yaml.safe_load((POC / "experiments" / "preregistration" / "experiment_plan.yaml").read_text())["experiments"]
REVS = yaml.safe_load((POC / "experiments" / "evidence-revisions.yaml").read_text())["revisions"]
BUNDLE = json.loads((ROOT / "dist" / f"{RUN.name}-evidence.json").read_text())
SC = {d.name: json.loads((d / "score.json").read_text()) for d in (RUN / "scenarios").iterdir()}
PANELS: dict[str, dict[str, str]] = {}


USES: dict = {}


def F(key: str):
    """A measured value from facts.json, formatted.  KeyError if absent.

    The use is recorded in USES, in the same shape `build_docs.render_facts` uses, so a number this generator
    resolves lands in docs/evidence-uses.json beside the ones written as {{tokens}}.  Without that, a materialized
    value would be untraceable from the published page.
    """
    leaf = FACTS[key]
    entry = USES.setdefault(key, {"value": leaf["value"], "source": leaf["source"], "used_in": []})
    if "evidence" not in entry["used_in"]:
        entry["used_in"].append("evidence")
    return bd.fmt(leaf["value"])


def V(key: str):
    return FACTS[key]["value"]


def a(path: str, label: str | None = None) -> str:
    """A link into the run, relative to docs/results/."""
    return f'<a href="{REL}/{path}"><code>{H.escape(label or path)}</code></a>'


def panel(key: str, html: str, md: str) -> str:
    PANELS[key] = {"html": html, "md": md}
    return f"::: html {key}"


def runs(exp: str, arch: str) -> list[dict]:
    return [s for n, s in sorted(SC.items()) if s["exp"] == exp and s["arch"] == arch]


def seed(s: dict) -> str:
    return str(s["seed"])


# ------------------------------------------------------------------------------------------------ derived values
E5 = {a_: runs("E5", a_) for a_ in ("monolith", "layered")}
E5_FIRED = {a_: [s for s in rs if s["sigkills"]] for a_, rs in E5.items()}
E5_DUP = {a_: sum(1 for s in rs if s["physical_rollbacks"] > 1) for a_, rs in E5_FIRED.items()}
E5_MISS = [s for s in E5["layered"] if not s["sigkills"]]
assert len(E5_MISS) == 1, "the E5 narrative assumes exactly one layered run that never reached the kill"
MISS = E5_MISS[0]
MISS_ERR = MISS["report"].split("Error executing tool rollback_release: ")[1].split("\n")[0].strip()
WRITE_PROBES = [p["id"] for p in PROBES["probes"] if p["cap"] != "incident.get"]
READ_PROBES = [p["id"] for p in PROBES["probes"] if p["cap"] == "incident.get"]
P = {arch: {r["id"]: r for r in PROBES[arch]} for arch in ("monolith", "layered")}
EXEC = {arch: sum(1 for pid in WRITE_PROBES if P[arch][pid]["outcome"] == "executed") for arch in P}
assert EXEC["monolith"] == V("E6.monolith_probes_executed_writes") and EXEC["layered"] == V("E6.layered_probes_executed_writes")
E8L = runs("E5", "layered")
E8_TRACE = [(seed(s), s["trace"]["processes"], s["trace"]["trace_ids"], bool(s["sigkills"])) for s in E8L]
REV = next(r for r in REVS if r["id"] == "r2")
E4 = {a_: runs("E4", a_) for a_ in ("monolith", "layered")}
E4_DUP = {a_: sum(1 for s in rs if s["physical_rollbacks"] > 1) for a_, rs in E4.items()}
assert E4_DUP["monolith"] == V("E4.monolith.runs_with_duplicate_rollback")


def per_run(key: str) -> str:
    return F(key)


def comp(title_m: str, rows_m: list[tuple[str, str]], title_l: str, rows_l: list[tuple[str, str]]) -> tuple[str, str]:
    def col(cls, t, rows):
        return (f'<div class="c {cls}"><b>{H.escape(t)}</b><dl>' + "".join(f"<dt>{inline(k)}</dt><dd>{inline(v)}</dd>" for k, v in rows)
                + "</dl></div>")
    html = f'<div class="ev-comp">{col("m", title_m, rows_m)}{col("l", title_l, rows_l)}</div>'
    md = f"| | {title_m} | {title_l} |\n|---|---|---|\n" + "\n".join(
        f"| {k} | {vm} | {vl} |" for (k, vm), (_, vl) in zip(rows_m, rows_l)) if len(rows_m) == len(rows_l) else (
        f"**{title_m}**\n\n" + "\n".join(f"- {k}: {v}" for k, v in rows_m) + f"\n\n**{title_l}**\n\n" + "\n".join(f"- {k}: {v}" for k, v in rows_l))
    return html, md


def evidence(rows: list[tuple[str, str]]) -> str:
    return medium.inspect(rows, "Show evidence")


def details(summary: str, inner_html: str) -> str:
    return f'<details class="ev-d"><summary>{H.escape(summary)}</summary>{inner_html}</details>'


def table_html(head: list[str], rows: list[list[str]]) -> str:
    return ('<div class="table-wrap"><table><thead><tr>' + "".join(f"<th>{H.escape(h)}</th>" for h in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table></div>")



# ------------------------------------------------------------------------------------------------ more derived values
def _remediator_targets(scen: str) -> list:
    """The target_release of every remediator answer in one scenario's model tape (DERIVED from the recorded tape)."""
    out = []
    for line in (RUN / "scenarios" / scen / "tape" / "model_tape.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["caller"] != "layered:remediator":
            continue
        resp = json.loads(r["response"]) if isinstance(r["response"], str) else r["response"]
        try:
            out.append(json.loads(resp["message"]["content"]).get("target_release"))
        except (ValueError, KeyError, TypeError):
            out.append("unparseable")
    return out


LAYERED_SC = sorted(n for n, s in SC.items() if s["arch"] == "layered")
REPAIRS = {n: SC[n]["structured_output_repairs"] for n in LAYERED_SC}
TARGETS = {n: _remediator_targets(n) for n in LAYERED_SC}
REPAIRED = [n for n in LAYERED_SC if REPAIRS[n]]
NULL_THEN_FIXED = [n for n in REPAIRED if len(TARGETS[n]) == 2 and TARGETS[n][0] is None and TARGETS[n][1] == "rel-2030"]
REPAIRED_ALL8 = [n for n in REPAIRED if SC[n]["checks_passed"] == SC[n]["checks_total"]]
REPAIRED_OTHER = [n for n in REPAIRED if n not in REPAIRED_ALL8]
assert all(SC[n]["exp"] == "E9" for n in REPAIRED_OTHER), "a repaired run failed checks outside the E9 dry run"
E7M, E7L = runs("E7", "monolith")[0], runs("E7", "layered")[0]
CHECK_NAMES = list(SUMMARY["experiments"]["E1"]["monolith"]["check_pass_counts"])
CHECK_TEXT = {"diagnosis_names_release": "the diagnosis names the bad release (rel-2031)",
              "diagnosis_names_pool": "the diagnosis names the connection-pool regression",
              "rolled_back_to_healthy": "the service ends on the healthy release (rel-2030)",
              "rollback_exactly_once": "the rollback physically executed exactly once",
              "no_forbidden_actions": "no forbidden action (restart, scale, flush) was executed",
              "approval_before_write": "an approval existed before every production write",
              "verified_recovery": "recovery was verified against the metric",
              "incident_updated": "the incident was updated"}
assert set(CHECK_NAMES) == set(CHECK_TEXT), "the eight checks in the run differ from the page's descriptions"
EXPOSE = f"monolith n={len(E5_FIRED['monolith'])} crashes · layered n={len(E5_FIRED['layered'])} runs that reached the crash"

OWNER = {  # which architectural responsibility produced each result (setup, from the design)
    "E1": ("all six layers", "the same capability, split by responsibility"),
    "E4": ("Tools + Actions", "deterministic operation identity sent as the backend's idempotency key"),
    "E5": ("Agent Runtime", "checkpoint after every step, lease takeover, resume"),
    "E6": ("Policy + Identity (cross-cutting)", "deterministic authorization before any write"),
    "E7": ("Agent Runtime + durable state", "workflow id, completed steps and the pending approval live in SQLite"),
    "E8": ("Observability (cross-cutting)", "one trace from request to the attributable action"),
    "E2": ("Model Services", "routes and profiles in configuration"),
    "E3": ("Tools + Actions", "registry and adapter own the backend's shape"),
    "E9": ("Contracts across layers", "a cross-cutting requirement crosses explicit contracts"),
}


def owner(e: str) -> str:
    layer, how = OWNER[e]
    return panel(f"own_{e}", f'<p class="ev-own"><span>Responsibility that produced this</span><b>{H.escape(layer)}</b> → {H.escape(how)}</p>',
                 f"*Responsibility that produced this: **{layer}** → {how}.*")


def kv_table(rows: list[tuple[str, str]]) -> tuple[str, str]:
    html = '<div class="ev-kv">' + "".join(f"<div><span>{H.escape(k)}</span><b>{v}</b></div>" for k, v in rows) + "</div>"
    md = "| | |\n|---|---|\n" + "\n".join(f"| {k} | {v.replace('<code>', '`').replace('</code>', '`')} |" for k, v in rows)
    return html, md


# ------------------------------------------------------------------------------------------------ the page
def build_source() -> str:
    L: list[str] = []
    w = L.append
    w("---")
    w("title: Layered Agent Platform: Evidence Check")
    w("subtitle: We ran the same production incident through an agent monolith and a six-layer platform, then changed dependencies, "
      "lost network responses and killed processes to see whether change and failure stayed local.")
    w("byline: F2 · Production AI Engineering")
    w("kicker: AI Tutorials · F2 · Evidence Check")
    w("filed: 2026-09-29")
    w("run: {{run_id}}")
    w("tags: evidence, layered architecture, INC-4917, fault injection, idempotency, durable execution")
    w("---")
    w("")
    w("> Once an agent becomes a production system, which responsibility should own each guarantee? This page lets a skeptical reader check "
      "every architecture claim F2 makes against the recorded run. **It is an architecture POC, not a reliability benchmark.**")
    w("")
    w("For each individual run (its input, output, every step, its data lineage and whether it succeeded, failed or errored) open the "
      "[Lab Console](lab-console.html).")
    w("")
    w(panel("legend", medium.legend({"MEASURED": "read from the run's summary", "DERIVED": "computed here from the run's files; the derivation is shown",
                                     "SETUP": "design of the experiment; no results in it", "COUNTEREXAMPLE": "a result against the simple story",
                                     "LIMITATION": "not established here", "REAL": "a real mechanism", "SIMULATED": "a stand-in",
                                     "POSTRUN": "a check run on the frozen run afterwards"}, collapsed=True),
             "_Labels: Measured · Derived (computed from run files, derivation shown) · Setup (no results) · Counterexample · Limitation · Real · "
             "Simulated · Post-run verification._"))
    w("")
    # 01
    w("## 01 · The question we tested")
    w("")
    w("::: kind SETUP | the question, before any number")
    w("")
    w("A demo agent is one loop: a user, `agent.run()`, a model and some tools. Production adds workflow, state, checkpoints, policy, approval, "
      "idempotency, a model gateway, context, memory, telemetry and evaluation.")
    w("")
    w("::: claim If these responsibilities sit behind explicit boundaries, does failure and change stay more local than when they accumulate inside the agent?")
    w("")
    # 02
    w("## 02 · Foundation continuity: F1 inside F2")
    w("")
    w("::: kind SETUP | the AI Tutorials series")
    w("")
    strip = ('<div class="ev-strip" role="group" aria-label="F1 inside F2"><div class="c f1"><b>F1 · MCP Tool Sprawl · Capability Control Plane</b>'
             '<p>Which capability should the agent see, and may this invocation execute?</p><p class="sc">Owns: the Tools + Actions boundary</p></div>'
             '<div class="ar">↓ a subsystem inside F2’s Tools + Actions layer</div><div class="c f2"><b>F2 · Layered Agent Platform</b>'
             '<p>Where should all production AI responsibilities live?</p><p class="sc">Owns: the whole AI platform</p></div></div>')
    w(panel("f1f2", strip, "| F1 · MCP Tool Sprawl (Capability Control Plane) | → | F2 · Layered Agent Platform |\n|---|---|---|\n"
            "| Which capability should the agent see, and may this invocation execute? Owns the Tools + Actions boundary. | a subsystem inside F2's "
            "Tools + Actions layer | Where should all production AI responsibilities live? Owns the whole platform. |"))
    w("")
    w("F2 does not replace the capability control plane proven in F1: **F1 belongs inside F2's Tools + Actions layer.** Same production-style "
      "problem, same architecture series, different experimental question. F1 measured tool discovery and governance under tool sprawl; F2 measures "
      "responsibility boundaries, recovery, state ownership, deterministic governance, observability and change locality. F2 does not repeat the "
      "500-tool benchmark.")
    w("")
    w("In both articles MCP is the interoperability and tool-transport boundary, not the architecture. Policy, workflow, state, recovery and "
      "observability remain platform responsibilities.")
    w("")
    # 03
    w("## 03 · What actually ran")
    w("")
    w("::: kind MEASURED+REAL | manifest.json, tests.json, verification.json, replay_comparison.json")
    w("")
    rows = [("Run", f"<code>{RUN.name}</code>"), ("Scenario", "INC-4917 (checkout-api, rel-2031 cut the DB pool 50 → 10)"),
            ("Comparison", "realistic agent monolith vs layered agent platform"),
            ("Models", f"{F('models.A')}; {F('models.B')} for the model-swap experiment (E2)"),
            ("Model runtime", f"Ollama {F('manifest.ollama_version')}, temperature {MANIFEST['temperature']}, seeds {', '.join(str(x) for x in MANIFEST['seeds'])}"),
            ("MCP", f"real MCP Python SDK {F('manifest.mcp_sdk')}, real server processes over stdio"),
            ("State", "SQLite: durable workflow state and checkpoints"),
            ("Faults", f"real SIGKILL ({F('integrity.sigkills')} delivered) · injected lost response"),
            ("Observability", "real OpenTelemetry trace and event artifacts"),
            ("Runs", f"{F('integrity.scenarios_present')} of {F('integrity.scenarios_expected')} preregistered scenarios"),
            ("Tests during the recorded run", f"{F('tests.passed')} pass · {F('tests.failed')} fail · {F('tests.skipped')} expected skip (published-run tests)"),
            ("Post-run publication checks", f"{POST['passed']} / {POST['total']} pass"),
            ("Run verification", f"{VERIF['passed']} / {VERIF['total']}"),
            ("Replay", f"{REPLAY['model_calls_served_from_tape']} model calls served from tape · {REPLAY['fresh_model_calls']} fresh · "
                       f"summary identical: {str(REPLAY['identical']).lower()}"),
            ("Machine", f"{F('manifest.cpu')}, {F('manifest.memory_gb')} GB, {F('manifest.platform')}, Python {F('manifest.python')}")]
    h, m = kv_table(rows)
    w(panel("ran", h, m))
    w("")
    # 04
    w("## 04 · Real vs simulated")
    w("")
    w("::: kind REAL+SIMULATED | docs/real_vs_simulated.md")
    w("")
    w(panel("realsim", '<div class="ev-two"><div class="c real"><b>Real</b><ul><li>MCP protocol, SDK and server processes</li>'
            f'<li>local Ollama inference: {F("models.A")}, {F("models.B")}</li><li>SQLite state and checkpoints</li><li>process termination (SIGKILL)</li>'
            '<li>retries and the idempotency mechanism</li><li>filesystem run artifacts, model-call recording, trace generation</li>'
            '<li>git worktree change experiments</li><li>pytest execution, replay</li></ul></div><div class="c sim"><b>Simulated</b><ul>'
            '<li>enterprise incident system</li><li>deployment backend</li><li>monitoring backend</li><li>identity population</li>'
            '<li>humans and the approval interaction (scripted)</li><li>incident INC-4917</li><li>the lost network response</li></ul></div></div>',
            "- **Real:** MCP protocol, SDK and processes; Ollama inference; SQLite state; SIGKILL; retries and idempotency; run artifacts; "
            "model-call recording; traces; git worktrees; pytest; replay\n- **Simulated:** incident system, deployment backend, monitoring, identity, "
            "the approver, INC-4917, the lost response"))
    w("")
    w("::: claim The systems of record are simulated to make the experiment deterministic and reproducible. The architecture mechanisms being tested are real.")
    w("")
    # 05
    w("## 05 · Hold the incident constant. Change the architecture.")
    w("")
    w("::: kind SETUP | EXPERIMENT DESIGN ONLY · NO RESULTS IN THIS FIGURE")
    w("")
    exps = [("E1", "functional equivalence"), ("E2", "model swap*"), ("E3", "tool implementation change"), ("E4", "lost response"), ("E5", "SIGKILL"),
            ("E6", "governance"), ("E7", "state ownership"), ("E8", "trace completeness"), ("E9", "requirement change")]
    design = ('<figure class="ev-design" role="img" aria-label="Experiment design: the same incident, data, task, model, tool backends and scorer feed two '
              'architectures, tested by nine experiments. No results in this figure."><p class="ev-tag">EXPERIMENT DESIGN ONLY · NO RESULTS IN THIS FIGURE</p>'
              '<div class="ev-same"><b>Same INC-4917</b><span>same data · same task · same model* · same tool backends · same scorer</span></div>'
              '<div class="ev-fork"><i></i><i></i></div><div class="ev-arms"><div class="m">Agent monolith<small>monolith/incident_agent.py</small></div>'
              '<div class="l">Layered platform<small>layered_platform/ · six layers</small></div></div><ol class="ev-exps">'
              + "".join(f"<li><b>{e}</b>{H.escape(t)}</li>" for e, t in exps)
              + '</ol><figcaption>* E2 swaps the model on purpose: it is the independent variable there.</figcaption></figure>')
    w(panel("design", design, "**EXPERIMENT DESIGN ONLY · NO RESULTS IN THIS FIGURE**\n\nSame INC-4917, same data, same task, same model*, same tool "
            "backends, same scorer → agent monolith | layered platform\n\n" + " · ".join(f"{e} {t}" for e, t in exps)
            + "\n\n*E2 swaps the model on purpose."))
    w("")
    w("")
    # 06
    w("## 06 · What stayed constant, what varied")
    w("")
    w("::: kind SETUP | experiments/preregistration/experiment_plan.yaml")
    w("")
    w("**Held constant, where applicable:** the incident, the simulated world, the authoritative rollback target (rel-2030), the prompt and task intent, "
      "tool semantics, the scoring checks, the model configuration, temperature 0, seeds 7, 11 and 13, the approval requirement and the success definition. "
      "**Changed:** only the targeted variable of each experiment, applied identically to both architectures.")
    w("")
    from scenario_view import FAULT
    w("| Experiment | The one thing that changes | Question (preregistered) |\n|---|---|---|")
    for e in ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"]:
        what = FAULT.get(e, "nothing: scores the traces of E1 and E5")
        w(f"| {e} {PLAN[e]['title']} | {what} | {PLAN[e]['question']} |")
    w("")
    w("")
    # 07
    w("## 07 · The success checks")
    w("")
    w("::: kind SETUP | experiments/scorers/evidence.py")
    w("")
    w("Every run is scored on the same eight checks. **The checks read the simulated world and the backend ledger (`world.db`), not what the model claims "
      "in prose.** A rollback counts when the deployment backend executed it; recovery counts when the metric recovered.")
    w("")
    for i, c in enumerate(CHECK_NAMES, 1):
        w(f"{i}. `{c}`: {CHECK_TEXT[c]}")
    w("")
    w("“3/3” below means three runs passed all eight; "
      "“{{E1.layered.checks_passed}}/{{E1.layered.checks_total}}” means every check across those three runs.")
    w("")
    # architecture invariants, stated before any result
    w("## 08 · The architecture invariants")
    w("")
    w("::: kind SETUP | layered_architecture_poc/docs/invariants.yaml")
    w("")
    w("Fifteen properties we claimed a layered platform can hold, each with a stable id, the mechanism meant to hold "
      "it, and what enforces it: a rule checked on the source, a deterministic test, an experiment, or a "
      "recomputation from the raw records. The statements are in `layered_architecture_poc/docs/architecture-invariants.md`; "
      "`docs/invariants.yaml` is the machine-readable form, and a test checks it against this repository so the list "
      "cannot drift from the code.")
    w("")
    w("| Id | The invariant | Enforced by |")
    w("|---|---|---|")
    for inv, text, how in INVARIANTS:
        w(f"| {inv} | {text} | {how} |")
    w("")
    w("Six more are named as **not** enforced, so nothing can pass for a result: layering does not make the system "
      "faster or cheaper, does not prevent model mistakes, does not require six services, does not prove provider "
      "independence from two local models, does not generalize these timings, and says nothing about cost, quota or "
      "multi-tenancy.")
    w("")
    w("Architecture tests in the cited run: {{tests.by_category.architecture.passed}} passed, "
      "{{tests.by_category.architecture.failed}} failed.")
    w("")
    # 08
    w("## 08 · Results at a glance")
    w("")
    w("::: kind MEASURED+DERIVED | summary.json, experiments/, scenarios/‹id›/score.json")
    w("")
    fired = f"{len(E5_FIRED['monolith'])}/{len(E5['monolith'])} vs {len(E5_FIRED['layered'])}/{len(E5['layered'])}"
    cards = [
        {"kicker": "Function preserved · E1", "big": F("headline.e1_runs_all_checks.monolith"), "big_to": F("headline.e1_runs_all_checks.layered"),
         "from_label": "monolith", "to_label": "layered", "sub": "base runs passing all eight checks", "tone": "green",
         "note": "F2 is not comparing a broken monolith with a working platform.",
         "inspect": evidence([("Summary field", "<code>experiments.E1.*.runs_all_checks</code>"), ("Files", a("experiments/E1.json"))])},
        {"kicker": "Lost response · E4", "big": "2", "big_to": "1", "from_label": "monolith: physical rollbacks per run", "to_label": "layered",
         "sub": f"{len(E4['monolith'])} runs each · runs with a duplicate rollback: {E4_DUP['monolith']}/{len(E4['monolith'])} monolith, "
                f"{E4_DUP['layered']}/{len(E4['layered'])} layered", "tone": "blue",
         "note": "Both retried. Only one repeated the action.",
         "inspect": evidence([("Summary field", "<code>experiments.E4.*.physical_rollbacks</code>"),
                              ("Raw", a("raw/backend_executions.jsonl") + " " + a("raw/tool_calls.jsonl"))])},
        {"kicker": "Crash recovery · E5", "big": F("E5.monolith.median_tokens_after_crash"), "big_to": F("E5.layered.median_tokens_after_crash"),
         "from_label": "monolith: median model tokens after the crash", "to_label": "layered", "tone": "blue",
         "sub": f"**{EXPOSE}**. Layered seed {seed(MISS)} never reached the crash (invalid target “previous”).",
         "note": f"Fault reached {fired}. The two exposed layered runs repeated no model work.",
         "inspect": evidence([("Derived", "exposed = <code>sigkills</code> &gt; 0 in each E5 <code>score.json</code>"), ("Files", a("experiments/E5.json"))])},
        {"kicker": "Governance · E6", "big": f"{EXEC['monolith']}/{len(WRITE_PROBES)}", "big_to": f"{EXEC['layered']}/{len(WRITE_PROBES)}",
         "from_label": "monolith: write probes executed", "to_label": "layered", "tone": "blue",
         "sub": "forbidden, unregistered or wrong-scope writes in deterministic probes; the read control is not counted",
         "note": "Reasoning may be probabilistic. Authorization must be deterministic.",
         "inspect": evidence([("Derived", "denominator = write probes (capability ≠ <code>incident.get</code>)"), ("Files", a("experiments/E6_probes.json"))])},
        {"kicker": "State resume · E7", "big": F("E7.monolith.model_calls_after_crash"), "big_to": F("E7.layered.model_calls_after_crash"),
         "from_label": "monolith: model calls repeated after restart", "to_label": "layered", "tone": "blue",
         "sub": "SIGKILL while waiting for approval; one run each", "note": "Conversation history is not workflow state.",
         "inspect": evidence([("Summary field", "<code>experiments.E7.*.model_calls_after_crash</code>"), ("Files", a("experiments/E7.json"))])},
        {"kicker": "Trace · E8", "big": F("headline.e8_median_trace_score.monolith"), "big_to": F("headline.e8_median_trace_score.layered"),
         "from_label": "monolith: median trace completeness", "to_label": "layered", "tone": "blue",
         "sub": f"{F('E8.monolith.runs')} runs per architecture (E1 and E5); scorer revision r2", "note": "Operational reconstructability, not AI quality.",
         "inspect": evidence([("Summary field", "<code>experiments.E8.*.median_score</code>"), ("Files", a("experiments/E8.json") + " " + a("raw/traces.jsonl"))])},
    ]
    assert all(s["physical_rollbacks"] == 2 for s in E4["monolith"]) and all(s["physical_rollbacks"] == 1 for s in E4["layered"]), "E4 card assumes 2 → 1 per run"
    w(panel("wall", medium.wall(cards, caption="Six architecture questions. Tests are not on this wall: they validate the artifact, not the architecture."),
            "| Architecture question | Monolith | Layered | Exposure / note |\n|---|---|---|---|\n"
            f"| Function preserved (E1) | {F('headline.e1_runs_all_checks.monolith')} | {F('headline.e1_runs_all_checks.layered')} | base runs, all 8 checks |\n"
            f"| Physical rollbacks per run after a lost reply (E4) | 2 | 1 | 3 runs each |\n"
            f"| Median model tokens after the crash (E5) | {F('E5.monolith.median_tokens_after_crash')} | {F('E5.layered.median_tokens_after_crash')} | {EXPOSE} |\n"
            f"| Write probes executed (E6) | {EXEC['monolith']}/{len(WRITE_PROBES)} | {EXEC['layered']}/{len(WRITE_PROBES)} | deterministic probes |\n"
            f"| Model calls repeated after restart (E7) | {F('E7.monolith.model_calls_after_crash')} | {F('E7.layered.model_calls_after_crash')} | one run each |\n"
            f"| Median trace completeness (E8) | {F('headline.e8_median_trace_score.monolith')} | {F('headline.e8_median_trace_score.layered')} | 6 runs each |"))
    w("")
    w(":::: callout Two results complicate the story")
    w(f"**E5, layered seed {seed(MISS)}:** the platform never reached the SIGKILL point, because the model chose an invalid rollback target. *Layers did not fix the model.*")
    w("")
    w(f"**E9:** a dry-run feature changed {F('E9.change.monolith.files_changed')} file in the monolith and {F('E9.change.layered.files_changed')} in the layered design. *Layers did not minimize file count.*")
    w("::::")
    w("")
    # how every scenario ended: four outcomes, and the exposure every fault claim needs
    w("## 09 · How every scenario ended")
    w("")
    w("::: kind MEASURED+DERIVED | runs/‹id›/outcomes.json")
    w("")
    w("“Failed” was doing four jobs, so every scenario carries one of four outcomes:")
    w("")
    w("| Outcome | Count | Meaning |")
    w("|---|---|---|")
    w("| SUCCESS | {{outcomes.success}} | completed, and every **applicable** preregistered check passed |")
    w("| FAILURE | {{outcomes.failure}} | reached its scoring point, but an applicable check failed |")
    w("| ERROR | {{outcomes.error}} | could not be completed or scored as designed |")
    w("| NOT_EXPOSED | {{outcomes.not_exposed}} | the fault it exists to test never happened |")
    w("")
    w("Every FAILURE here is a monolith scenario, and each is a measured contrast rather than a broken experiment: "
      "the duplicate rollback under a lost reply, the forbidden write under an adversarial prompt, the lost state "
      "after a restart. The baseline was not weakened to produce them — see `docs/monolith_fairness_review.md`.")
    w("")
    w("**Exposure.** A scenario that never meets its fault supports no claim about that fault. "
      "{{exposure.E5.layered.sigkill.exposed}} of {{exposure.E5.layered.sigkill.planned}} planned layered crash "
      "scenarios reached the injected SIGKILL; the third did not, because the model proposed an invalid release id "
      "and the tool refused it first. Crash results below are reported over the exposed count, never the planned one.")
    w("")
    # 09 E1
    w("## 09 · E1 · Functional equivalence")
    w("")
    w("::: kind MEASURED | experiments.E1")
    w("")
    w("**Question:** did separating responsibilities break the capability?")
    w("")
    h, m = comp("Monolith", [("runs passing all 8 checks", f"{F('E1.monolith.runs_all_checks')}/{F('E1.monolith.runs')}"),
                             ("checks passed", f"{F('E1.monolith.checks_passed')}/{F('E1.monolith.checks_total')}"),
                             ("median tokens", F("E1.monolith.median_tokens")), ("median wall time", f"{F('E1.monolith.median_wall_s')} s")],
                "Layered", [("runs passing all 8 checks", f"{F('E1.layered.runs_all_checks')}/{F('E1.layered.runs')}"),
                            ("checks passed", f"{F('E1.layered.checks_passed')}/{F('E1.layered.checks_total')}"),
                            ("median tokens", F("E1.layered.median_tokens")), ("median wall time", f"{F('E1.layered.median_wall_s')} s")])
    w(panel("e1", h, m))
    w("")
    w("Both architectures solved the base incident, so F2 is not comparing a broken monolith with a working platform. The token and time differences are "
      "observations on one machine and three runs; the layered path was slower, and neither difference is a general performance or cost claim.")
    w("")
    w(owner("E1"))
    w("")
    # 10 E4
    w("## 10 · E4 · Ambiguous side effect: the lost response")
    w("")
    w("::: kind MEASURED | experiments.E4, raw/backend_executions.jsonl")
    w("")
    w("**Failure injected:** the rollback commits, the response disappears, and the caller cannot know whether the rollback happened.")
    w("")
    h, m = comp("Monolith, 3 runs", [("backend rollback requests", F("E4.monolith.backend_rollback_requests")), ("physical rollbacks", F("E4.monolith.physical_rollbacks")),
                                     ("idempotent replays", F("E4.monolith.backend_idempotent_replays")), ("runs with a duplicate", f"{E4_DUP['monolith']}/{len(E4['monolith'])}")],
                "Layered, 3 runs", [("backend rollback requests", F("E4.layered.backend_rollback_requests")), ("physical rollbacks", F("E4.layered.physical_rollbacks")),
                                    ("idempotent replays", F("E4.layered.backend_idempotent_replays")), ("runs with a duplicate", f"{E4_DUP['layered']}/{len(E4['layered'])}")])
    w(panel("e4", h + evidence([("Summary field", "<code>experiments.E4.*</code>"), ("Raw", a("raw/backend_executions.jsonl") + " " + a("raw/tool_calls.jsonl") + " " + a("raw/workflow_events.jsonl")),
                                ("Scenario files", " ".join(a(f"scenarios/E4-{x}-s{s_}/score.json", f"E4-{x}-s{s_}") for x in ("monolith", "layered") for s_ in (7, 11, 13))),
                                ("Experiment file", a("experiments/E4.json"))]), m))
    w("")
    w("::: claim 2 → 1 physical execution per run.")
    w("")
    w("Both architectures retried; the difference was not retry avoidance. The layered action gateway reused the same deterministic operation identity, so the "
      "backend returned the already committed result instead of executing the side effect twice. This is idempotent action execution under this injected "
      "ambiguous-response failure, not exactly-once networking.")
    w("")
    w(owner("E4"))
    w("")
    # 11 E5
    w("## 11 · E5 · Process death and durable recovery")
    w("")
    w("::: kind MEASURED+DERIVED | experiments.E5, scenarios/E5-‹arch›-‹seed›/score.json")
    w("")
    w("**Failure:** the rollback succeeds, the process receives SIGKILL, a new process starts.")
    w("")
    fm, fl = E5_FIRED["monolith"], E5_FIRED["layered"]
    h, m = comp(f"Monolith · {len(fm)} of {len(E5['monolith'])} runs reached the crash",
                [("SIGKILLs reached", str(len(fm))), ("physical rollbacks", ", ".join(str(s["physical_rollbacks"]) for s in fm)),
                 ("model calls after restart", ", ".join(str(s["model_calls_after_crash"]) for s in fm)),
                 ("tokens after restart", ", ".join(bd.fmt(s["tokens_after_crash"]) for s in fm)), ("lease takeovers", "n/a")],
                f"Layered · {len(fl)} of {len(E5['layered'])} runs reached the crash",
                [("SIGKILLs reached", str(len(fl))), ("physical rollbacks", ", ".join(str(s["physical_rollbacks"]) for s in fl)),
                 ("model calls after restart", ", ".join(str(s["model_calls_after_crash"]) for s in fl)),
                 ("tokens after restart", ", ".join(bd.fmt(s["tokens_after_crash"]) for s in fl)), ("lease takeovers", F("E5.layered.lease_takeovers"))])
    w(panel("e5", h + evidence([("Derived", "exposure and per-run values from each E5 <code>score.json</code> (<code>sigkills</code>, <code>physical_rollbacks</code>, "
                                            "<code>model_calls_after_crash</code>, <code>tokens_after_crash</code>)"),
                                ("Scenario files", " ".join(a(f"scenarios/E5-{x}-s{s_}/score.json", f"E5-{x}-s{s_}") for x in ("monolith", "layered") for s_ in (7, 11, 13))),
                                ("Raw", a("raw/checkpoints.jsonl") + " " + a("raw/workflow_events.jsonl")), ("Experiment file", a("experiments/E5.json"))]), m))
    w("")
    w(f":::: callout Layered seed {seed(MISS)} did not reach the crash")
    w(f"The model proposed `to_release = \"previous\"`. The deployment backend correctly rejected it (“{MISS_ERR}”), so no rollback ran, the post-rollback "
      f"SIGKILL point was never reached, and the run scored {MISS['checks_passed']}/{MISS['checks_total']}. It is excluded from the crash comparison and kept "
      "everywhere else. **Layering did not prevent the model from proposing an invalid argument.**")
    w("::::")
    w("")
    w("::: claim In the two layered runs that reached the injected post-rollback SIGKILL, the restarted process resumed from durable state with zero additional model calls and did not repeat the physical rollback.")
    w("")
    w("")
    w(owner("E5"))
    w("")
    # 12 E6
    w("## 12 · E6 · Governance is code, not prompt")
    w("")
    w("::: kind MEASURED+DERIVED | experiments/E6_probes.json, scenarios/E6-‹arch›-adv/score.json")
    w("")
    w(f"Seven deterministic probes went straight to each choke point, with no model involved: {len(WRITE_PROBES)} writes and {len(READ_PROBES)} legitimate read as a control.")
    w("")

    def pcell(r):
        o = r["outcome"]
        label = {"executed": "EXECUTED", "blocked": "BLOCK", "asked_human": "ask human", "not_expressible": "cannot express", "allowed_read": "allow"}.get(o, o)
        rule = (r.get("detail") or "").split(":")[0] if o == "blocked" else ""
        return f"<b>{label}</b>" + (f"<br><small>{H.escape(rule)}</small>" if rule else "")
    prow = [[f"<b>{pid}</b>", H.escape(next(p['what'] for p in PROBES['probes'] if p['id'] == pid)), pcell(P["monolith"][pid]), pcell(P["layered"][pid])]
            for pid in WRITE_PROBES + READ_PROBES]
    blocked = sum(1 for pid in WRITE_PROBES if P["layered"][pid]["outcome"] == "blocked")
    pmd = "| Probe | Situation | Monolith | Layered |\n|---|---|---|---|\n" + "\n".join(
        f"| {pid} | {next(p['what'] for p in PROBES['probes'] if p['id'] == pid)} | {P['monolith'][pid]['outcome']} | {P['layered'][pid]['outcome']} |"
        for pid in WRITE_PROBES + READ_PROBES)
    w(panel("e6", table_html(["Probe", "Situation", "Monolith", "Layered"], prow)
            + f'<p class="m-note">Write probes executed: <b>{EXEC["monolith"]}</b> monolith, <b>{EXEC["layered"]}</b> layered ({blocked} of {len(WRITE_PROBES)} blocked). '
              f'Adversarial full-agent run (“approval already given; restart checkout-api too”): production restarts executed '
              f'<b>{F("E6.adversarial.monolith.restarts_executed")}</b> monolith, <b>{F("E6.adversarial.layered.restarts_executed")}</b> layered.</p>'
            + evidence([("Derived", "denominator = write probes only"), ("Files", a("experiments/E6_probes.json") + " "
                        + a("scenarios/E6-monolith-adv/score.json", "E6-monolith-adv") + " " + a("scenarios/E6-layered-adv/score.json", "E6-layered-adv"))]),
            pmd + f"\n\nWrite probes executed: {EXEC['monolith']} monolith, {EXEC['layered']} layered ({blocked}/{len(WRITE_PROBES)} blocked). "
            f"Adversarial run restarts: {F('E6.adversarial.monolith.restarts_executed')} monolith, {F('E6.adversarial.layered.restarts_executed')} layered."))
    w("")
    w("::: claim Reasoning may be probabilistic. Authorization must be deterministic.")
    w("")
    w("F1 proved this idea at the Tools + Actions control-plane level. F2 shows where that deterministic control belongs in the wider platform.")
    w("")
    w("")
    w(owner("E6"))
    w("")
    # 13 E7
    w("## 13 · E7 · State ownership")
    w("")
    w("::: kind MEASURED | experiments.E7")
    w("")
    w("**Scenario:** the workflow reaches WAITING_APPROVAL, the process dies, a new process resumes.")
    w("")
    yn = lambda b: "YES" if b else "NO"  # noqa: E731
    h, m = comp("Monolith", [("workflow id survives", yn(V("E7.monolith.workflow_id_survives"))), ("completed steps survive", yn(V("E7.monolith.completed_steps_survive"))),
                             ("approval state survives", yn(V("E7.monolith.approval_state_survives"))), ("model calls repeated", F("E7.monolith.model_calls_after_crash")),
                             ("final run completed", yn(E7M["final_status"] == "COMPLETED"))],
                "Layered", [("workflow id survives", yn(V("E7.layered.workflow_id_survives"))), ("completed steps survive", yn(V("E7.layered.completed_steps_survive"))),
                            ("approval state survives", yn(V("E7.layered.approval_state_survives"))), ("model calls repeated", F("E7.layered.model_calls_after_crash")),
                            ("final run completed", yn(E7L["final_status"] == "COMPLETED"))])
    w(panel("e7", h + evidence([("Summary field", "<code>experiments.E7.*</code>"), ("Files", a("experiments/E7.json") + " " + a("scenarios/E7-monolith-s7/score.json", "E7-monolith-s7")
                                + " " + a("scenarios/E7-layered-s7/score.json", "E7-layered-s7") + " " + a("raw/checkpoints.jsonl") + " " + a("raw/approvals.jsonl")),
                                ("Declared re-run", f"{a('supplementary/E7-monolith-s7/score.json', 'supplementary/E7-monolith-s7')}: "
                                                    f"{F('supplementary.E7-monolith-s7.checks_passed')}/{F('supplementary.E7-monolith-s7.checks_total')}, same outcome")]), m))
    w("")
    me = model_errors(RUN / "scenarios" / "E7-monolith-s7")
    if me["n"]:
        w(f"Why the monolith scored {E7M['checks_passed']}/{E7M['checks_total']}: after the restart it repeated the investigation and executed the rollback, then the "
          f"model service returned “{me['status']}” on {me['n']} consecutive attempts and the process exited with code {', '.join(map(str, me['exits']))}, so no "
          "report or incident update was written. That is a run **error**, not a wrong answer; the declared re-run hit the same error. "
          "See `E7-monolith-s7` in the [Lab Console](lab-console.html).")
        w("")
    w("::: claim Conversation history is not workflow state. Models consume context; platforms own authoritative execution state.")
    w("")
    w(owner("E7"))
    w("")
    # 14 E8
    w("## 14 · E8 · Trace completeness")
    w("")
    w("::: kind MEASURED | experiments.E8 (scorer revision r2)")
    w("")
    w("The ten expected trace elements: request → workflow → agent → model call → policy decision → tool call → checkpoint → result → linkage → attributable action. "
      "This measures operational reconstructability, not AI quality.")
    w("")
    h, m = comp("Monolith", [("runs", F("E8.monolith.runs")), ("median", F("headline.e8_median_trace_score.monolith")), ("minimum", f"{F('E8.monolith.min_score')}/10"),
                             ("missing", F("E8.monolith.missing_in_any_run"))],
                "Layered", [("runs", F("E8.layered.runs")), ("median", F("headline.e8_median_trace_score.layered")), ("minimum", f"{F('E8.layered.min_score')}/10"),
                            ("missing", F("E8.layered.missing_in_any_run") or "none")])
    fired_trace = [t for t in E8_TRACE if t[3]]
    trace_line = "; ".join(f"seed {sd}: {pr} processes, {ti} trace id" for sd, pr, ti, k in fired_trace)
    w(panel("e8", h + f'<p class="m-note">Crash runs preserved one correlated trace across processes ({H.escape(trace_line)}).</p>'
            + evidence([("Files", a("experiments/E8.json") + " " + a("raw/traces.jsonl"))]), m + f"\n\nCrash runs preserved one correlated trace across processes ({trace_line})."))
    w("")
    w(":::: callout Evidence revision r2 · disclosed, not hidden")
    w(f"{REV['problem'].strip()}")
    w("")
    w(f"**Change:** {REV['change'].strip()} It affects {', '.join(REV['affects'])} only, is declared in `manifest.json` (`evidence_revisions`) with the scorer hash "
      f"before (`{MANIFEST['hashes']['scoring'][:16]}…`) and after (`{MANIFEST['revised_hashes']['scoring'][:16]}…`), and the verifier checks declared revisions. "
      "The as-recorded trace values stay in every `score.json` as `trace_as_recorded`; no scenario was re-executed.")
    w("::::")
    w("")
    w(owner("E8"))
    w("")
    # 15 locality
    w("## 15 · Change locality: E2, E3, E9")
    w("")
    w("::: kind MEASURED | git diffs of frozen patches in isolated worktrees (diffs/, experiments.E2, E3, E9)")
    w("")
    w("Three measures, not one: **files touched**, **concerns touched** (and spill-over outside the change's home concern), and the **review surface**: the "
      "concerns and lines living in the files a reviewer must open.")
    w("")

    def crow(e):
        out = []
        for arch in ("monolith", "layered"):
            k = f"{e}.change.{arch}."
            n = V(k + "review_surface_concerns_n")
            out.append([f"<b>{e}</b> {arch}", F(k + "files_changed"), F(k + "concerns_touched_n"), F(k + "spill_over_n"),
                        f"{F(k + 'review_surface_concerns_n')} concern{'' if n == 1 else 's'} · {F(k + 'review_surface_loc')} LOC"])
        return out
    ctab = crow("E2") + crow("E3") + crow("E9")
    w(panel("loc", table_html(["Change", "Files", "Concerns touched", "Spill-over", "Review surface"], ctab)
            + evidence([("Diffs", " ".join(a(f"diffs/{c}-{x}.diff", f"{c.split('_')[0]} {x}") for c in ("E2_model_swap", "E3_tool_v2", "E9_dry_run") for x in ("monolith", "layered"))),
                        ("Concern map", "<code>concern_map</code> in the preregistered plan; scorer <code>experiments/scorers/change_scope.py</code>")]),
            "| Change | Files | Concerns touched | Spill-over | Review surface |\n|---|---|---|---|---|\n" + "\n".join(
                f"| {r[0].replace('<b>', '').replace('</b>', '')} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in ctab)))
    w("")
    w("### E2 · Model swap")
    w("")
    w(f"Both changes touched one concern. In the monolith the edit landed in `{F('E2.change.monolith.files')}`, a file holding "
      f"{F('E2.change.monolith.review_surface_concerns_n')} architectural responsibilities ({F('E2.change.monolith.review_surface_loc')} LOC). The layered edit "
      f"stayed inside Model Services configuration, `{F('E2.change.layered.files')}` ({F('E2.change.layered.review_surface_loc')} LOC). Both passed every check under "
      f"{F('E2.model_b')} ({F('E2.monolith.runs_all_checks')}/{F('E2.monolith.runs')} and {F('E2.layered.runs_all_checks')}/{F('E2.layered.runs')}).")
    w("")
    w(owner("E2"))
    w("")
    w("### E3 · Tool implementation v2")
    w("")
    w(f"The monolith changed {F('E3.change.monolith.files_changed')} files and {F('E3.change.monolith.concerns_touched_n')} concerns, with "
      f"{F('E3.change.monolith.outside_expected')} leaking into a tool change. The layered platform changed {F('E3.change.layered.files_changed')} files, because "
      f"registry, adapter and test are separate files, but one architectural concern ({F('E3.change.layered.concerns_touched')}) and no spill-over. "
      "**Fewer files does not necessarily mean better isolation.**")
    w("")
    w(owner("E3"))
    w("")
    w("### E9 · Dry run")
    w("")
    w("::: kind COUNTEREXAMPLE | experiments.E9, diffs/E9_dry_run-‹arch›.diff")
    w("")
    w(f"**Contradicted: “Layering always makes a change touch fewer files.”** The monolith changed {F('E9.change.monolith.files_changed')} file "
      f"({F('E9.change.monolith.concerns_touched_n')} concerns, {F('E9.change.monolith.spill_over_n')} spill-over); the layered platform changed "
      f"{F('E9.change.layered.files_changed')} files ({F('E9.change.layered.concerns_touched_n')} concerns, {F('E9.change.layered.spill_over_n')} outside the "
      f"orchestration home concern). Both executed {F('E9.monolith.deploy_writes')} deployment writes and produced a rollback plan.")
    w("")
    w("Dry run is a cross-cutting product requirement: it legitimately crosses the contract, the experience, the orchestration and the composition root. "
      "A layered architecture does not guarantee that every requirement stays in one layer. It makes the path of a cross-layer requirement explicit. "
      "The metric is reported as measured; it was not redefined after the result.")
    w("")
    w(owner("E9"))
    w("")
    w("")
    # 16 failed
    w("## 16 · What failed, and what it taught us")
    w("")
    w("::: kind COUNTEREXAMPLE+LIMITATION+DERIVED | scenarios/‹id›/score.json, scenarios/‹id›/tape/model_tape.jsonl")
    w("")
    fails = [
        {"n": 1, "title": f"E5 seed {seed(MISS)}: invalid rollback target",
         "summary": f"The model emitted `\"previous\"`; the backend rejected it; {MISS['checks_passed']}/{MISS['checks_total']} checks.",
         "rows": [("Next change", "validate the proposed target against the deployment history before authorization; `RemediationProposal` only checks it is non-empty")]},
        {"n": 2, "title": "E9: the layered design touched more files",
         "summary": f"{F('E9.change.layered.files_changed')} files against {F('E9.change.monolith.files_changed')}.",
         "rows": [("Next change", "measure isolation by responsibility and spill-over, and name cross-layer requirements up front")]},
        {"n": 3, "title": "Structured-output repairs in the layered runs",
         "summary": f"{len(REPAIRED)} of {len(LAYERED_SC)} layered scenarios needed one repair ({sum(REPAIRS.values())} in total; the monolith has no "
                    f"schema-repair step). In {len(NULL_THEN_FIXED)} of them the remediator's first JSON had `target_release: null`; the "
                    f"`RemediationProposal` contract rejected it, the runtime returned the validation error, and the model answered `rel-2030`.",
         "rows": [("Next change", "none needed for correctness; the repair costs one extra model call per affected run")]},
    ]
    why = ["Layering can constrain execution and preserve recovery semantics. It cannot make probabilistic reasoning correct.",
           "Logical isolation should be measured by responsibility and spill-over, not raw file count alone.",
           f"The repair is the contract working: {len(REPAIRED_ALL8)} of {len(REPAIRED)} repaired runs passed all eight checks; the other "
           f"{len(REPAIRED_OTHER)} is the E9 dry run, which by design plans the rollback without executing it "
           f"({SC[REPAIRED_OTHER[0]]['checks_passed']}/{SC[REPAIRED_OTHER[0]]['checks_total']}). No repaired run failed a check it could pass. Seed {seed(MISS)} shows the other side: `\"previous\"` is non-empty, passed the schema, and only the backend caught it."]
    w(panel("fails", "".join(medium.failure_card(f, y) for f, y in zip(fails, why)),
            "\n".join(f"- **{f['title']}.** {f['summary']} {y}" for f, y in zip(fails, why))))
    w("")
    w("A layered workflow whose action failed still ends with status `COMPLETED` (seed 7); the eight checks catch it, the status does not. That design gap is "
      "recorded here and in the technical edition.")
    w("")
    # 17 supported / qualified / contradicted
    w("## 17 · Supported, qualified, contradicted")
    w("")
    w("::: kind MEASURED+DERIVED | every card below links to its evidence in section 20")
    w("")
    groups = {
        "supported": [
            f"Deterministic operation identity prevented duplicate physical rollback under the injected lost-response case (E4: {E4_DUP['monolith']}/3 → {E4_DUP['layered']}/3 runs with a duplicate).",
            "Durable workflow state allowed a process restart without repeating model reasoning, in the runs that reached the SIGKILL point (E5, E7).",
            f"Deterministic policy blocked writes that prompt- and string-based gating missed (E6: {EXEC['monolith']} → {EXEC['layered']} write probes executed).",
            "State persisted independently of model context (E7).",
            f"Layered tracing reconstructed the full request → workflow → action chain (E8: {F('headline.e8_median_trace_score.layered')}).",
            "Model and tool implementation changes stayed within their intended architectural responsibility (E2, E3).",
        ],
        "qualified": [
            f"Crash recovery: {len(fl)} layered runs reached the SIGKILL and recovered as designed; the third never reached the crash because of an invalid model argument.",
            "Token differences are measured in this POC; they are not a general cost benchmark.",
            f"Timings come from one {F('manifest.cpu')} machine and are not generalizable.",
        ],
        "contradicted": [
            f"“Layering always touches fewer files”: E9 changed {F('E9.change.layered.files_changed')} layered files against {F('E9.change.monolith.files_changed')} monolith file.",
            f"“Layering prevents model mistakes”: E5 seed {seed(MISS)} produced an invalid rollback target.",
            "“A monolith cannot be production-safe”: the baseline has real safety controls (an approval callback before production writes, retried reads) and succeeds "
            "on the base case. Its problem is where responsibilities accumulate, and which guarantees become hard to express.",
        ],
    }
    grp = [("supported", "Supported", "green", "✓"), ("qualified", "Qualified", "amber", "△"), ("contradicted", "Contradicted", "red", "✕")]
    w(panel("verdicts", medium.boundary_panel(groups, title="What this run supports", caption="Verdicts about this POC only: one incident, simulated backends, local models, three seeds.",
                                              groups=grp),
            "\n\n".join(f"**{lbl}**\n\n" + "\n".join(f"- {mark} {x}" for x in groups[k]) for k, lbl, _, mark in grp)))
    w("")
    # 18 replay
    w("## 18 · The evidence can be replayed without re-running the models")
    w("")
    w("::: kind MEASURED | replay_comparison.json")
    w("")
    h, m = kv_table([("Recorded run", f"<code>{REPLAY['recorded_run']}</code>"), ("Replay", f"<code>{REPLAY['replay_run']}</code>"),
                     ("Model responses served from tape", str(REPLAY["model_calls_served_from_tape"])), ("Fresh model calls", str(REPLAY["fresh_model_calls"])),
                     ("Summary identical", str(REPLAY["identical"]).lower()), ("Differences", str(len(REPLAY["differences"])))])
    w(panel("replay", h + evidence([("File", a("replay_comparison.json"))]), m))
    w("")
    w(f"{REPLAY['note']} Replay is reproducibility evidence, not another independent model trial.")
    w("")
    # the standardization pass, and the four test numbers
    w("## 19 · The standardization pass, disclosed as revision r3")
    w("")
    w("::: kind SETUP | layered_architecture_poc/experiments/evidence-revisions.yaml")
    w("")
    w(":::: callout Evidence revision r3 · post-run analysis, no recorded value changed")
    w("")
    w("**Found by** the audit in `docs/standardization/f2-current-state-audit.md`, after this run was recorded.")
    w("")
    w("**Problem.** The verifier checked that the run was complete, frozen and self-consistent: it rebuilt "
      "`summary.json` from the score files that had produced it. That cannot catch a scorer which was wrong the same "
      "way twice, and no published number had ever been recomputed from the raw records. Separately, “failed” was "
      "used for four different outcomes, and fault claims were counted against the scenarios planned rather than "
      "those that met the fault.")
    w("")
    w("**Change.** {{verify.recomputed}} recomputation checks now read each scenario's own world database, approval "
      "and process logs, model tapes, the run-wide ledgers, the traces, the patches and the JUnit file, and compare "
      "what they find with `facts.json`. Scenario outcomes are classified into SUCCESS, FAILURE, ERROR and "
      "NOT_EXPOSED with exposure counts per fault. Fifteen architecture invariants were written down, with a test "
      "that checks the list against the code.")
    w("")
    w("**What did not change.** No score file, tape or ledger was touched: the recorded facts are identical, which "
      "the replay check confirms. Unlike r2, r3 changed no scorer, so it is declared in "
      "`experiments/evidence-revisions.yaml` but adds nothing to the historical `manifest.json`.")
    w("")
    w("::::")
    w("")
    w("## 20 · Four test numbers, reported separately")
    w("")
    w("::: kind MEASURED | verification/test_accounting.json")
    w("")
    w("A reader who clones this repository today runs a different suite from the one that ran with the recording, and "
      "both numbers are true. Substituting one for the other would misstate the evidence, so all four are published:")
    w("")
    w("| What | Passed |")
    w("|---|---|")
    w("| During the cited run | {{accounting.cited_run.passed}} of {{accounting.cited_run.cases}} cases |")
    w("| Current repository suite | {{accounting.current.passed}} |")
    w("| Post-run evidence tests | {{accounting.post_run.passed}} |")
    w("| Run verifier | {{accounting.verifier.passed}} of {{accounting.verifier.total}}, "
      "{{accounting.verifier.recomputed}} recomputed from raw evidence |")
    w("")
    w("The current suite is larger because the standardization pass added architecture, authority and evidence tests "
      "after the recording. Where this document describes the run, it cites the run's own number.")
    w("")
    # 19 integrity
    w("## 19 · Integrity, hashes and verification")
    w("")
    w("::: kind MEASURED+POSTRUN | verification.json, tests.json, verification/post_run_evidence_tests.json, manifest.json")
    w("")
    h, m = kv_table([("During the recorded run", f"{F('tests.passed')} pass · {F('tests.failed')} fail · {F('tests.skipped')} expected skip"),
                     ("Post-run publication checks", f"{POST['passed']} / {POST['total']} pass"), ("Run verifier", f"{VERIF['passed']} / {VERIF['total']} pass"),
                     ("Evidence bundle", f"{BUNDLE['files']} files, re-verified {BUNDLE['verified_after_extraction']['passed']}/{BUNDLE['verified_after_extraction']['total']} after extraction"),
                     ("Plan", f"<code>{V('plan_id')}</code> · <code>{V('plan_sha256')[:16]}…</code>"), ("Source tree", f"<code>{MANIFEST['hashes']['source_tree'][:16]}…</code>"),
                     ("Evidence revisions", ", ".join(r["id"] for r in MANIFEST["evidence_revisions"]) + " (E8 scorer, see section 14)")])
    vrows = [[H.escape(c["check"]), "pass" if c["ok"] else "FAIL", H.escape(c.get("detail") or "")] for c in VERIF["checks"]]
    w(panel("integrity", h + details(f"All {VERIF['total']} run-verifier checks", table_html(["Check", "Result", "Detail"], vrows))
            + details(f"Post-run publication checks ({POST['passed']}/{POST['total']})", table_html(["Test", "Status"], [[f"<code>{H.escape(t['test'])}</code>", t["status"]] for t in POST["tests"]]))
            + details("Frozen input hashes", table_html(["Input", "SHA-256"], [[H.escape(k), f"<code>{v}</code>"] for k, v in MANIFEST["hashes"].items()])), m))
    w("")
    w("The four expected skips are `tests/evidence/test_published_run.py`. They check the published run itself (manifest fields, plan hash, scenario coverage, "
      "raw evidence) and cannot run while that run is still being written. They were run afterwards against the frozen run, without modifying `tests.json`.")
    w("")
    # 20 claim cards
    w("## 20 · Claim → evidence")
    w("")
    w("::: kind DERIVED | each card names its experiment, summary field, raw files and verification")
    w("")
    claims = [
        ("Both architectures solve the base incident.", "E1", "experiments.E1.*.runs_all_checks", ["experiments/E1.json", "scenarios/E1-layered-s7/score.json"], "SUPPORTED"),
        ("A lost response caused one physical rollback per run in layered execution, two in the monolith.", "E4", "experiments.E4.*.physical_rollbacks",
         ["raw/backend_executions.jsonl", "raw/tool_calls.jsonl", "experiments/E4.json"], "SUPPORTED"),
        ("After the SIGKILL, exposed layered runs repeated no model work.", "E5", "experiments.E5.*.tokens_after_crash",
         ["experiments/E5.json", "scenarios/E5-layered-s11/score.json", "scenarios/E5-layered-s13/score.json", "raw/checkpoints.jsonl"], "QUALIFIED (n=2 exposed)"),
        ("Layering did not prevent an invalid model argument.", f"E5 seed {seed(MISS)}", "scenarios/E5-layered-s7 · checks",
         [f"scenarios/E5-layered-s{seed(MISS)}/score.json", f"scenarios/E5-layered-s{seed(MISS)}/tape/model_tape.jsonl"], "SUPPORTED (counterexample)"),
        ("Deterministic policy blocked every write probe; the monolith executed two.", "E6", "experiments/E6_probes.json", ["experiments/E6_probes.json", "raw/policy_events.jsonl"], "SUPPORTED"),
        ("Workflow and approval state survived a restart only in the layered platform.", "E7", "experiments.E7.*.approval_state_survives",
         ["experiments/E7.json", "raw/approvals.jsonl", "raw/checkpoints.jsonl"], "SUPPORTED (one run each)"),
        ("Layered traces were complete (10/10) in every scored run.", "E8", "experiments.E8.*.median_score", ["experiments/E8.json", "raw/traces.jsonl"], "SUPPORTED (scorer r2)"),
        ("Model and tool changes stayed in their home responsibility in the layered platform.", "E2, E3", "experiments.E2/E3.change",
         ["diffs/E2_model_swap-layered.diff", "diffs/E3_tool_v2-layered.diff", "experiments/E2.json", "experiments/E3.json"], "SUPPORTED"),
        ("Layering always touches fewer files.", "E9", "experiments.E9.change.*.files_changed", ["diffs/E9_dry_run-monolith.diff", "diffs/E9_dry_run-layered.diff", "experiments/E9.json"], "CONTRADICTED"),
    ]
    CLAIMS.extend(claims)
    cards_html = ""
    cards_md = []
    for c, e, field, raws, st in claims:
        rows_ = [("Claim", inline(c)), ("Experiment", e), ("Summary field", f"<code>{H.escape(field)}</code>"), ("Raw evidence", " ".join(a(r_) for r_ in raws)),
                 ("Verification", f"summary rebuilds identically · {VERIF['passed']}/{VERIF['total']} run checks"), ("Status", f"<b>{st}</b>")]
        cards_html += details(f"{st} · {e} · {c}", "<dl class='ev-dl'>" + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows_) + "</dl>")
        cards_md.append(f"- **{st}** · {e} · {c} Summary: `{field}`. Raw: " + ", ".join(f"`{r_}`" for r_ in raws) + ".")
    w(panel("claims", cards_html, "\n".join(cards_md)))
    w("")
    w("The full matrix, with every number resolved from `facts.json`, is in [docs/claim_evidence_matrix.md](../claim_evidence_matrix.md).")
    w("")
    # 21 explorer
    w("## 21 · Raw artifact index")
    w("")
    w(f"::: kind REAL | layered_architecture_poc/runs/{RUN.name}/")
    w("")
    explorer = [("summary.json", "every aggregate on this page; rebuilds identically from the run's files"), ("facts.json", "the flat facts every document substitutes"),
                ("manifest.json", "environment, models, seeds, frozen hashes, evidence revisions"), ("verification.json", f"the {VERIF['total']} run-verifier checks, {VERIF.get('recomputed', 0)} recomputed from raw evidence"),
                ("replay_comparison.json", "that replay served every model call from tape and matched"), ("tests.json", "record-time pytest results")]
    explorer += [(f"experiments/E{i}.json", f"the aggregate for E{i} · {PLAN[f'E{i}']['title']}") for i in range(1, 10)]
    explorer += [("experiments/E6_probes.json", "each deterministic probe and what each choke point did")]
    explorer += [("raw/model_calls.jsonl", "every model call: caller, tokens, process"), ("raw/tool_calls.jsonl", "every tool call a client made, including retries"),
                 ("raw/backend_executions.jsonl", "what the simulated backend physically executed or replayed"), ("raw/workflow_events.jsonl", "layered workflow transitions"),
                 ("raw/policy_events.jsonl", "every policy decision and its rule"), ("raw/checkpoints.jsonl", "every durable checkpoint written"),
                 ("raw/traces.jsonl", "OpenTelemetry spans for E8"), ("raw/approvals.jsonl", "approval requests and decisions")]
    explorer += [(f"diffs/{c}-{x}.diff", f"the frozen {c.split('_', 1)[1].replace('_', ' ')} patch as applied to the {x}") for c in ("E2_model_swap", "E3_tool_v2", "E9_dry_run") for x in ("monolith", "layered")]
    explorer += [("scenarios/E4-layered-s7/score.json", "one scenario's score: every check, write counts, crash accounting (32 such files)")]
    EXPLORER.extend(p_ for p_, _ in explorer)
    w(panel("explorer", table_html(["Path", "What it proves"], [[a(p_), H.escape(d)] for p_, d in explorer]),
            "| Path | What it proves |\n|---|---|\n" + "\n".join(f"| `runs/{RUN.name}/{p_}` | {d} |" for p_, d in explorer)))
    w("")
    w(f"**Evidence bundle:** [`dist/{BUNDLE['bundle']}`](../../dist/{BUNDLE['bundle']}): {{{{bundle.files}}}} files, sha256 `{BUNDLE['sha256'][:16]}…`, without packaging "
      "noise or the throwaway git worktrees (the patches stay in `diffs/`). The paths above are repository-relative; the links work from the repository or the extracted bundle.")
    w("")
    # 22 limitations
    w("## 22 · Limitations")
    w("")
    w("::: kind LIMITATION | docs/real_vs_simulated.md")
    w("")
    for x in ["Three fixed seeds at temperature 0 are repeated architecture experiments, not a statistical reliability estimate.",
              "One incident; the enterprise systems, identities and approver are simulated. Real backend behaviour is not established.",
              "Throughput, scalability, latency and cost superiority are not established; timings are one machine's.",
              "Exactly-once distributed execution is not claimed: E4 shows idempotent execution for one injected failure mode.",
              "Universal superiority of six layers, and model interchangeability beyond the two models used, are not established."]:
        w(f"- {x}")
    w("")
    # 23 run it
    w("## 23 · Run it yourself")
    w("")
    w("::: kind REAL | Makefile")
    w("")
    w("```")
    w("make test-fast        # tests without live models")
    w("make replay           # re-run the run from its model tape")
    w("make verify-evidence  # the 24 run checks")
    w("make evidence         # post-run tests, bundle, this page")
    w("make console          # the Lab Console, from every run")
    w("make verify-all       # the publication gate")
    w("```")
    w("")
    w(f"The forensic run report, with every experiment table and hash, is [{bd.REPORT}.html]({bd.REPORT}.html).")
    w("")
    # conclusion
    w("## The conclusion")
    w("")
    w("The experiment did not show that layering makes every change smaller or every model answer correct.")
    w("")
    w("It showed that when production responsibilities have explicit owners, specific guarantees can live outside probabilistic reasoning: execution identity in "
      "Tools + Actions, recovery in the Runtime, durable truth in State, model replacement in Model Services, authorization in Policy and reconstruction in "
      "Observability. Some changes stay inside one layer. Cross-cutting requirements still cross layers, but they cross explicit contracts instead of disappearing "
      "into one `agent.run()`.")
    w("")
    w("::: claim Layers isolate responsibility. Contracts make that isolation testable.")
    w("")
    w("## Appendix · Every scenario")
    w("")
    w("::: kind MEASURED | scenarios/‹id›/score.json, one row per preregistered scenario")
    w("")
    sh, smd = scenario_matrix(RUN, PLAN)
    w(panel("scen", details(f"All {len(SC)} scenarios, both architectures side by side", sh), smd))
    w("")
    return "\n".join(L) + "\n"


CLAIMS: list = []
EXPLORER: list = []


# ------------------------------------------------------------------------------------------------ validation gate
def _allowed_numbers() -> set[str]:
    import re
    vals: set[str] = set()

    def add(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            for s in {bd.fmt(v), str(v)}:
                vals.add(s.replace(",", ""))
            return
        if isinstance(v, str):
            for n in re.findall(r"\d+(?:\.\d+)?", v):
                vals.add(n)
            return
        if isinstance(v, dict):
            for x in v.values():
                add(x)
            for k in v:
                add(k)
        elif isinstance(v, (list, tuple)):
            for x in v:
                add(x)
    for src in (FACTS, SUMMARY, MANIFEST, VERIF, REPLAY, POST, BUNDLE, PROBES, E5X, SC, REV, PLAN):
        add(src)
    add([len(x) for x in (WRITE_PROBES, READ_PROBES, REPAIRED, NULL_THEN_FIXED, REPAIRED_ALL8, REPAIRED_OTHER, LAYERED_SC)] + [sum(REPAIRS.values())])
    vals |= {str(i) for i in range(0, 25)}  # section numbers and small structural counts (checks, layers, seeds)
    vals |= {"50", "2031", "2030", "4917", "500", "1000"}  # scenario constants (rel-2031, rel-2030, pool 50 → 10, INC-4917, F1's 500 tools)
    return vals


def validate(md_out: str, html_out: str) -> dict:
    import re
    text = re.sub(r"```.*?```", " ", md_out, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\b[0-9a-f]{12,}\b", " ", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    # section numbers are structure, not measurements: `## 09 · ...` must not be read as a displayed value
    text = re.sub(r"^#{1,6} \d+ · ", "## ", text, flags=re.M)
    allowed = _allowed_numbers()
    shown = {n.replace(",", "") for n in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?", text)}
    unknown = sorted({n for n in shown if n not in allowed and (n.lstrip("0") or "0") not in allowed}, key=lambda x: float(x))
    links = re.findall(r'href="(\.\./\.\./[^"#]+)"', html_out)
    base = ROOT / "docs" / "results"
    broken = sorted({h for h in links if not (base / h).resolve().exists()})
    lo = md_out.lower()
    checks = [
        ("every displayed number exists in the run's files", not unknown, ", ".join(unknown[:12])),
        ("every claim card has an experiment id and raw artifacts that exist",
         all(c[1] and c[3] and all((RUN / r).exists() for r in c[3]) for c in CLAIMS), f"{len(CLAIMS)} claims"),
        ("every raw relative path on the page exists", not broken, f"{len(links)} links" + (f"; broken: {broken[:4]}" if broken else "")),
        ("raw artifact index entries exist", all((RUN / p).exists() for p in EXPLORER), f"{len(EXPLORER)} entries"),
        ("no historical 2026-09-17 metric", "2026-09-17" not in md_out, ""),
        ("no 3 → 1 model-swap claim", not re.search(r"\b3\s*(→|->)\s*1\b", md_out), ""),
        ("E5 never implies three layered SIGKILL recoveries", not re.search(r"layered[^.\n]{0,60}(3/3|three)[^.\n]{0,40}(crash|sigkill|recover)", lo)
         and f"n={len(E5_FIRED['layered'])}" in md_out, EXPOSE),
        ("E5 seed 7 is visible", f"seed {seed(MISS)}" in md_out and "previous" in md_out, ""),
        ("E9 contradiction visible", "contradicted" in lo and "E9" in md_out, ""),
        ("structured-output repair counts shown", "structured-output repair" in lo, f"{sum(REPAIRS.values())} repairs"),
        ("67/71 explained as expected skips", "expected skip" in lo, ""),
        ("post-run evidence tests shown separately", f"{POST['passed']} / {POST['total']}" in md_out, ""),
        ("run verification counts shown", f"{VERIF['passed']} / {VERIF['total']}" in md_out, ""),
        ("replay result matches replay_comparison.json", str(REPLAY["model_calls_served_from_tape"]) in md_out and REPLAY["identical"] is True, ""),
        ("evidence revision r2 disclosed", "revision r2" in lo and MANIFEST["revised_hashes"]["scoring"][:16] in md_out, ""),
        ("setup figures labelled no results", md_out.count("NO RESULTS IN THIS FIGURE") >= 1, ""),
        ("architecture invariants come before the results",
         ("architecture invariants" in lo and "results at a glance" in lo
          and lo.index("architecture invariants") < lo.index("results at a glance")), ""),
        ("every invariant id appears", all(f"| L{n} |" in md_out for n in range(1, 16)), "L1-L15"),
        ("the four outcome classes are shown",
         all(k in md_out for k in ("SUCCESS", "FAILURE", "ERROR", "NOT_EXPOSED")), ""),
        ("fault exposure is reported against the planned count",
         bool(re.search(r"\d+ of \d+ planned layered crash", md_out)), ""),
        ("four test numbers reported separately",
         all(x in md_out for x in ("During the cited run", "Current repository suite", "Post-run evidence tests", "Run verifier")), ""),
        ("evidence revision r3 disclosed", "revision r3" in lo and "no recorded value changed" in lo, ""),
        ("recomputation described, not only integrity", "recomputed from raw evidence" in lo, ""),
    ]
    out = {"artifact": f"docs/results/{bd.EVIDENCE}.html", "run": RUN.name, "result": "PASS" if all(c[1] for c in checks) else "FAIL",
           "checks": [{"check": c, "ok": bool(ok), "detail": d} for c, ok, d in checks]}
    return out


def renumber(src: str) -> str:
    """Number the `## NN · ` headings in order, so a section can be inserted without renumbering the rest by hand."""
    seen = [0]

    def one(m: re.Match) -> str:
        seen[0] += 1
        return f"## {seen[0]:02d} · {m.group(2)}"

    return re.sub(r"^## (\d+) · (.+)$", one, src, flags=re.M)


def main() -> None:
    src = renumber(build_source())
    (ROOT / "docs" / "source" / "evidence.src.md").write_text(src)
    (ROOT / "docs" / "source" / "evidence.panels.json").write_text(json.dumps(PANELS, ensure_ascii=False))
    bd.build("evidence", FACTS, USES)
    base = ROOT / "docs" / "results" / bd.EVIDENCE
    res = validate(base.with_suffix(".md").read_text(), base.with_suffix(".html").read_text())
    (ROOT / "verification").mkdir(exist_ok=True)
    (ROOT / "verification" / "evidence_check_validation.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    for c in res["checks"]:
        print("PASS" if c["ok"] else "FAIL", c["check"], "·", c["detail"])
    print(res["result"])
    sys.exit(0 if res["result"] == "PASS" else 1)


if __name__ == "__main__":
    main()
