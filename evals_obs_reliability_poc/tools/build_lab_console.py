"""The Lab Console: one offline page with every scenario × runtime, every check, claim, mutant and model call of the run.

    python3 tools/build_lab_console.py      (make console)  -> results/lab-console.html, results/lab-console.evidence.json

Generated from the published run's files and the proof pack; nothing is typed.  Per run it shows the operator's view
(`recovery explain`), the recovery decisions, the providers' ledgers and every eval check with its detail.
"""

from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "recovery_poc"
RUN = (POC / "runs" / "PUBLISHED").read_text().strip()
R = POC / "runs" / RUN


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


LIVE = POC / "runs" / "2026-10-07-live"


def explain_all(run: Path = R) -> dict[str, str]:
    code = ("import io, json, contextlib, sys\nfrom pathlib import Path\nfrom recovery.cli import explain\nfrom recovery.common import scenarios\n"
            f"run = Path({str(run)!r}); out = {{}}\n"
            "for s in scenarios():\n    for a in ('A0','A1','A2'):\n        buf = []\n"
            "        explain(run / 'scenarios' / s['id'] / a, s, a, out=buf.append)\n        out[s['id'] + '-' + a] = '\\n'.join(buf)\n"
            "print(json.dumps(out))")
    p = subprocess.run(["uv", "run", "--quiet", "--project", str(POC), "python", "-c", code], cwd=POC, capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def main() -> None:
    sys.path.insert(0, str(POC))
    from recovery.common import scenarios
    sc = scenarios()
    facts = json.loads((R / "facts.json").read_text())
    res = json.loads((ROOT / "evidence" / "runs" / RUN / "results.json").read_text())
    checks = jl(ROOT / "evidence" / "runs" / RUN / "checks.jsonl")
    runs = {}
    for s in sc:
        for a in ("A0", "A1", "A2"):
            d = R / "scenarios" / s["id"] / a
            runs[f"{s['id']}-{a}"] = {"eval": json.loads((d / "eval.json").read_text()), "ledger": json.loads((d / "world" / "ledger.json").read_text()),
                                      "workers": json.loads((d / "workers.json").read_text())}
    data = {"run": RUN, "scenarios": [{k: s[k] for k in ("id", "title", "layer", "case", "faults", "decisions", "status", "effects")} for s in sc],
            "runs": runs, "explain": explain_all(), "facts": {k: v["value"] for k, v in facts.items()},
            "experiments": res["experiments"], "checks": [{k: c[k] for k in ("id", "experiment", "description", "kind", "expected", "status", "finding", "actual_value")} for c in checks],
            "claims": [{k: c.get(k) for k in ("id", "class", "statement", "checks", "statuses")} for c in res["claims"]],
            "mutants": json.loads((R / "reports" / "mutants.json").read_text()),
            "slice": jl(R / "model-slice" / "scored.jsonl"), "slice_scores": json.loads((R / "model-slice" / "scores.json").read_text()),
            "gates": json.loads((R / "model-slice" / "gate.json").read_text())}
    if LIVE.exists():
        data["live"] = {"run": LIVE.name, "facts": {k: v["value"] for k, v in json.loads((LIVE / "facts.json").read_text()).items()},
                        "evals": {f"{s['id']}-{a}": json.loads((LIVE / "scenarios" / s["id"] / a / "eval.json").read_text()) for s in sc for a in ("A0", "A1", "A2")},
                        "explain": explain_all(LIVE)}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "lab-console.evidence.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))
    page = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")).replace("__RUN__", html.escape(RUN))
    (ROOT / "results" / "lab-console.html").write_text(page)
    print(f"results/lab-console.html: {len(runs)} scenario runs, {len(checks)} checks, {len(data['slice'])} model calls")


TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lab Console · R1 + R2 · Evals, Observability & Reliability</title>
<style>
:root{--ink:#172B4D;--sub:#52637A;--mut:#8494AA;--bd:#E3E8EF;--bg:#F7F9FB;--ok:#1F9D74;--okt:#E6F6EF;--bad:#D14D63;--badt:#FFEEF1;--warn:#D97706;--warnt:#FFF4E0;--blue:#2F6FDE;--bluet:#EEF4FF;--navy:#172B4D}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}
header{background:var(--navy);color:#fff;padding:18px 24px}header h1{margin:0;font-size:20px}header p{margin:4px 0 0;color:#C9D3E3;font-size:13px}
nav.tabs{display:flex;gap:4px;padding:0 24px;background:#fff;border-bottom:1px solid var(--bd);flex-wrap:wrap}
nav.tabs button{border:0;background:none;padding:12px 14px;font:600 14px/1 inherit;color:var(--sub);cursor:pointer;border-bottom:3px solid transparent}
nav.tabs button.on{color:var(--blue);border-bottom-color:var(--blue)}main{padding:20px 24px;max-width:1400px;margin:0 auto}
section{display:none}section.on{display:block}.card{background:#fff;border:1px solid var(--bd);border-radius:12px;padding:16px 18px;margin:0 0 16px}
h2{font-size:17px;margin:0 0 10px}table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{border-bottom:1px solid var(--bd);padding:6px 8px;text-align:left;vertical-align:top}
th{color:var(--sub);font-weight:600;background:#FBFCFD}.wrap{overflow-x:auto}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font:600 12px/1.6 ui-monospace,Menlo,monospace}
.PASS,.ok{background:var(--okt);color:var(--ok)}.FAIL,.bad{background:var(--badt);color:var(--bad)}.NA{background:#EDF0F4;color:var(--sub)}
.EXPECTED_FAILURE,.warn,.LIMITATION{background:var(--warnt);color:var(--warn)}
.grid{display:grid;grid-template-columns:120px repeat(25,1fr);gap:3px;font:12px ui-monospace,Menlo,monospace;min-width:900px}
.grid div{padding:6px 2px;text-align:center;border-radius:5px;cursor:pointer}.grid .h{background:none;color:var(--mut);cursor:default}.grid .lab{text-align:left;cursor:default;font-family:inherit}
pre{background:#0F1B33;color:#DCE6F5;padding:14px;border-radius:10px;overflow-x:auto;font:12.5px/1.45 ui-monospace,Menlo,monospace;white-space:pre}
select{font:inherit;padding:6px 8px;border-radius:8px;border:1px solid var(--bd)}.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.kpi{background:#fff;border:1px solid var(--bd);border-radius:12px;padding:12px 14px}
.kpi b{display:block;font-size:24px}.kpi span{color:var(--sub);font-size:13px}.mono{font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
footer{color:var(--mut);font-size:12.5px;padding:10px 24px 30px;text-align:center}
</style></head><body>
<header><h1>Lab Console · “The Agent Failed” Is Not an Operational Signal</h1>
<p>Production AI Engineering · R1 + R2 · recorded run __RUN__ · every value below is read from the run's files and the proof pack</p></header>
<nav class="tabs" role="tablist"></nav><main></main>
<footer>Generated by tools/build_lab_console.py from recovery_poc/runs/__RUN__ and evidence/runs/__RUN__. Offline, no network.</footer>
<script>
const D = __DATA__;
const $ = (s, e = document) => e.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const pill = (t, cls) => `<span class="pill ${cls || t}">${esc(t)}</span>`;
const F = (k) => D.facts[k];
const tabs = {overview: "Overview", scenarios: "Scenario explorer", live: "Real model end to end", proof: "Proof: experiments & checks", claims: "Claims", mutants: "Mutants", slice: "Real-model slice"};
const nav = $("nav.tabs"), main = $("main");
for (const [id, label] of Object.entries(tabs)) {
  nav.insertAdjacentHTML("beforeend", `<button data-t="${id}">${label}</button>`);
  main.insertAdjacentHTML("beforeend", `<section id="t-${id}"></section>`);
}
function show(id) { nav.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.t === id));
  main.querySelectorAll("section").forEach(s => s.classList.toggle("on", s.id === "t-" + id)); location.hash = id; }
nav.addEventListener("click", (e) => { if (e.target.dataset.t) show(e.target.dataset.t); });

// ---- overview
const arms = {A0: "A0 naive", A1: "A1 idempotent retry", A2: "A2 classified"};
let g = `<div class="grid"><div class="h lab">runtime</div>${D.scenarios.map(s => `<div class="h">${s.id.slice(1)}</div>`).join("")}`;
for (const a of ["A0","A1","A2"]) {
  g += `<div class="lab">${arms[a]}</div>`;
  for (const s of D.scenarios) { const r = D.runs[s.id + "-" + a]; const ok = r.eval.checks.OE1.result === "PASS";
    const dup = r.eval.checks.I1.result === "FAIL" || r.eval.checks.I2.result === "FAIL";
    g += `<div class="${ok ? "ok" : "bad"}" title="${esc(s.id + " · " + s.title)}" onclick="openRun('${s.id}','${a}')">${ok ? "✓" : (dup ? "2×" : "✗")}</div>`; }
}
g += "</div>";
const k = (v, l) => `<div class="kpi"><b>${esc(v)}</b><span>${esc(l)}</span></div>`;
$("#t-overview").innerHTML = `<div class="card"><h2>Outcome per scenario and runtime (click a cell)</h2><div class="wrap">${g}</div></div>
<div class="card"><h2>Per runtime</h2><div class="wrap"><table><tr><th></th><th>A0 naive</th><th>A1 idempotent retry</th><th>A2 classified</th></tr>
${[["dup_scenarios","scenarios with a duplicate external effect"],["outcome_correct","correct outcomes"],["false_claims","false claims in the answer"],
["terminal_retries","retries of refusals"],["trace_split","runs split across traces"],["failures_diagnosed","failures with class + certainty"],["failure_events","failure events"],
["invariant_failures","invariant FAILs"],["escalations","escalations"],["status_queries","reconciliation queries"],["write_requests","write requests reaching providers"]]
.map(([key,l]) => `<tr><td>${l}</td><td>${F("A0."+key)}</td><td>${F("A1."+key)}</td><td>${F("A2."+key)}</td></tr>`).join("")}</table></div></div>
<div class="kpis">${k(F("A2.re1_pass") + " / " + F("scenarios"), "A2 decisions equal to the preregistered oracle")}${k(F("mut.detected") + " / " + F("mut.total"), "mutants caught by the eval suite")}
${k(F("ms.unsafe_executed_total"), "unsafe real-model proposals that would execute")}${k(F("nc.dup_scenarios"), "negative control: scenarios duplicated without reconciliation")}</div>`;

// ---- scenario explorer
const opts = D.scenarios.map(s => `<option value="${s.id}">${s.id} · ${esc(s.title)}</option>`).join("");
$("#t-scenarios").innerHTML = `<div class="row"><select id="sel-s">${opts}</select><select id="sel-a">${Object.entries(arms).map(([a,l]) => `<option value="${a}">${l}</option>`).join("")}</select></div><div id="run"></div>`;
function renderRun() {
  const s = D.scenarios.find(x => x.id === $("#sel-s").value), a = $("#sel-a").value, r = D.runs[s.id + "-" + a];
  const chk = Object.entries(r.eval.checks).map(([c, v]) => `<tr><td class="mono">${c}</td><td>${pill(v.result)}</td><td>${esc(v.detail)}</td></tr>`).join("");
  const led = r.ledger;
  $("#run").innerHTML = `<div class="card"><h2>${s.id} · ${esc(s.title)}</h2><p><b>Layer:</b> ${esc(s.layer)} · <b>Faults:</b> <span class="mono">${esc(s.faults.join(", ") || "none")}</span>
  · <b>Oracle:</b> ${esc(s.status)}, ${esc(JSON.stringify(s.effects))}<br><b>Oracle decisions (A2):</b> <span class="mono">${esc(s.decisions.map(d => d.join(" / ")).join(" → ") || "—")}</span></p>
  <p><b>Workers:</b> ${r.workers.map(w => `${w.worker} exit ${w.exit}${w.signal ? " (" + w.signal + ")" : ""}`).join(" · ")}</p></div>
  <div class="card"><h2>As an operator sees it (recovery explain)</h2><pre>${esc(D.explain[s.id + "-" + a])}</pre></div>
  <div class="card"><h2>Systems of record</h2><div class="wrap"><table><tr><th>credits</th><th>tickets</th><th>messages</th></tr><tr>
  <td class="mono">${led.credits.map(c => esc(c.credit_id + " " + c.charge_id + " " + c.amount + " op=" + c.operation_id)).join("<br>") || "—"}</td>
  <td class="mono">${led.tickets.map(t => esc(t.ticket_id + " " + t.status + " ref=" + t.reference)).join("<br>") || "—"}</td>
  <td class="mono">${led.notifications.map(m => esc(m.message_id + " " + m.template)).join("<br>") || "—"}</td></tr></table></div></div>
  <div class="card"><h2>Eval checks</h2><div class="wrap"><table><tr><th>check</th><th>result</th><th>detail</th></tr>${chk}</table></div></div>`;
}
$("#sel-s").addEventListener("change", renderRun); $("#sel-a").addEventListener("change", renderRun);
window.openRun = (s, a) => { $("#sel-s").value = s; $("#sel-a").value = a; renderRun(); show("scenarios"); };
renderRun();

// ---- the real-model end-to-end run
if (D.live) {
  const L = D.live, LF = (k) => L.facts[k];
  let lg = `<div class="grid"><div class="h lab">runtime</div>${D.scenarios.map(s => `<div class="h">${s.id.slice(1)}</div>`).join("")}`;
  for (const a of ["A0","A1","A2"]) {
    lg += `<div class="lab">${arms[a]}</div>`;
    for (const s of D.scenarios) { const e = L.evals[s.id + "-" + a]; const ok = e.checks.OE1.result === "PASS";
      const dup = e.checks.I1.result === "FAIL" || e.checks.I2.result === "FAIL";
      lg += `<div class="${ok ? "ok" : "bad"}" title="${esc(s.id)}" onclick="openLive('${s.id}','${a}')">${ok ? "✓" : (dup ? "2×" : "✗")}</div>`; }
  }
  lg += "</div>";
  $("#t-live").innerHTML = `<div class="card"><h2>Same faults, qwen3:8b deciding (run ${esc(L.run)}) · click a cell</h2>
  <p>${LF("model.calls")} real model calls on ${LF("model.distinct_prompts")} distinct prompts; ${LF("model.prompts_with_varying_output")} prompts got more than one answer;
  ${LF("model.repair_calls")} repairs; ${LF("model.fallback_calls")} fallback call. A2 decisions equal to the oracle: ${LF("A2.re1_pass")} of ${F("scenarios")}.</p>
  <div class="wrap">${lg}</div></div>
  <div class="card"><h2>Scripted model vs real model</h2><div class="wrap"><table><tr><th></th><th>A0</th><th>A1</th><th>A2</th></tr>
  ${[["dup_scenarios","scenarios with a duplicate effect"],["outcome_correct","correct outcomes"],["false_claims","false claims"]].map(([k, l]) =>
    `<tr><td>${l}</td>${["A0","A1","A2"].map(a => `<td>${F(a + "." + k)} → <b>${LF(a + "." + k)}</b></td>`).join("")}</tr>`).join("")}
  <tr><td>unsafe credits committed (real model)</td>${["A0","A1","A2"].map(a => `<td>${LF(a + ".unsafe_credits")}</td>`).join("")}</tr></table></div></div>
  <div class="card" id="live-run"><p>Click a cell to see that run, as the operator sees it.</p></div>`;
  window.openLive = (s, a) => { const e = L.evals[s + "-" + a];
    $("#live-run").innerHTML = `<h2>${s} · ${arms[a]} · real model</h2><pre>${esc(L.explain[s + "-" + a])}</pre>`; };
} else { $("#t-live").innerHTML = `<div class="card">No real-model run recorded.</div>`; }

// ---- proof
$("#t-proof").innerHTML = D.experiments.map(x => `<div class="card"><h2>${x.id} · ${esc(x.title)} ${pill(x.result)}</h2><p>${esc(x.question)}</p>
<div class="wrap"><table><tr><th>check</th><th>kind</th><th>expected</th><th>observed</th><th>status</th></tr>
${D.checks.filter(c => c.experiment === x.id).map(c => `<tr><td class="mono">${c.id}</td><td>${c.kind}</td><td class="mono">${esc(c.expected)}</td><td class="mono">${esc(c.actual_value)}</td>
<td>${pill(c.status === "FAIL" ? c.finding : c.status, c.status === "FAIL" ? (c.finding === "LIMITATION OBSERVED" ? "LIMITATION" : "FAIL") : c.status)}</td></tr><tr><td></td><td colspan="4">${esc(c.description)}</td></tr>`).join("")}
</table></div></div>`).join("");

// ---- claims
$("#t-claims").innerHTML = `<div class="card"><div class="wrap"><table><tr><th>claim</th><th>class</th><th>statement</th><th>checks</th></tr>
${D.claims.map(c => `<tr><td class="mono">${c.id}</td><td>${pill(c.class, c.class === "SUPPORTED" ? "PASS" : (c.class === "NEGATIVE CONTROL" || c.class === "QUALIFIED" ? "warn" : "NA"))}</td>
<td>${esc(c.statement)}</td><td class="mono">${Object.entries(c.statuses || {}).map(([k, v]) => k + " " + v).join("<br>") || "—"}</td></tr>`).join("")}</table></div></div>`;

// ---- mutants
$("#t-mutants").innerHTML = `<div class="card"><div class="wrap"><table><tr><th>mutant</th><th>scenarios failing</th><th>checks that caught it</th><th>duplicates</th><th>per scenario</th></tr>
${D.mutants.map(m => `<tr><td class="mono">${m.id} ${esc(m.name)}</td><td>${m.scenarios_failed}</td><td class="mono">${m.checks.join(", ")}</td><td class="mono">${m.duplicates.join(", ") || "—"}</td>
<td class="mono">${Object.entries(m.failing).map(([s, c]) => s + ": " + c.join(" ")).join("<br>")}</td></tr>`).join("")}</table></div></div>`;

// ---- slice
const gates = Object.entries(D.gates).map(([m, g]) => `<tr><td class="mono">${esc(m)}</td><td>${pill(g.decision, g.decision === "PASS" ? "PASS" : "FAIL")}</td>
<td class="mono">${Object.entries(g.rates).map(([k, v]) => k + " " + (100 * v).toFixed(0) + "%").join(" · ")}</td><td>${g.unsafe_proposals}</td><td class="mono">${g.missed.join(", ") || "—"}</td></tr>`).join("");
$("#t-slice").innerHTML = `<div class="card"><h2>Release gate (blind cases)</h2><div class="wrap"><table><tr><th>model</th><th>gate</th><th>rates</th><th>unsafe</th><th>missed</th></tr>${gates}</table></div></div>
<div class="card"><h2>Every call (${D.slice.length})</h2><div class="wrap"><table><tr><th>model</th><th>case</th><th>split</th><th>seed</th><th>correct</th><th>unsafe</th><th>gates</th><th>output</th></tr>
${D.slice.map(r => `<tr><td class="mono">${esc(r.model)}</td><td class="mono">${r.case}</td><td>${r.split}</td><td>${r.seed}</td><td>${pill(r.score.correct ? "PASS" : "FAIL")}</td>
<td>${r.score.unsafe_proposal ? pill("unsafe", "bad") : ""}</td><td class="mono">${esc(r.score.gates)}</td><td class="mono">${esc((r.content || "").slice(0, 160))}</td></tr>`).join("")}</table></div></div>`;

show((location.hash || "#overview").slice(1) in tabs ? (location.hash || "#overview").slice(1) : "overview");
</script></body></html>
"""

if __name__ == "__main__":
    main()
