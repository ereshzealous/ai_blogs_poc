"""Build the standalone Proof Lab (lab/index.html) of the published run (or of a named run).

    uv run python lab/build_lab.py [<run-id>]          (uv run pap lab)

Every value on the page is read from the run's proof pack (results.json, checks.jsonl, manifest.json, replay.json,
negative-control/results.json, evidence/verification/verification.json) and its raw evidence (raw/). The facts it prints
are embedded as JSON (id="lab-facts") so verification can check them against the published run.
Nothing is typed by hand; a missing value fails the build.  The page embeds its fonts (the diagrams' three: Lilita One, Nunito, Cascadia Code; SIL OFL 1.1,
from the series' evidence-kit) and needs no network.
"""

from __future__ import annotations

import base64
import functools
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"

STAGES = [("Request", "request.received"), ("Identity", "identity.resolved"), ("Context", "context.assembled"), ("Discovery", "tools.discovered"),
          ("Model", "model.routed"), ("Proposal", "action.proposed"), ("Policy", "policy.write"), ("Approval", "approval.validated"),
          ("Capability", "capability.issued"), ("MCP execute", "action.executed"), ("Verify", "effect.verified"), ("Memory", "memory.write"),
          ("Evaluation", "evaluation.recorded")]
STOP = {"workflow.denied": "denied", "budget.exceeded": "budget", "workflow.failed_closed": "failed closed"}


def esc(v) -> str:
    return html.escape(str(v), quote=True)


def rows(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def short(s: str, n: int = 12) -> str:
    return s if len(str(s)) <= n + 1 else f"{str(s)[:n]}…"


def jblock(obj, title: str, open_: bool = False) -> str:
    return (f'<details class="raw"{" open" if open_ else ""}><summary>{esc(title)}</summary>'
            f'<pre><code>{esc(json.dumps(obj, indent=2, default=str))}</code></pre></details>')


def chip(text: str, tone: str) -> str:
    return f'<span class="chip {tone}">{esc(text)}</span>'


# ---- the observed path of one experiment directory ------------------------------------------------------------------------
def stop_stage(code: str | None, on: str | None) -> str:
    if code in ("BUDGET_EXCEEDED", "NO_ELIGIBLE_MODEL"):
        return "Model" if not on or on.startswith("model") else "MCP execute"
    if code and (code.startswith("APPROVAL") or code in ("SELF_APPROVAL", "APPROVER_NOT_AUTHORIZED")):
        return "Approval"
    if code and code.startswith("CAPABILITY_") and code != "CAPABILITY_DISABLED" and code != "CAPABILITY_NOT_REGISTERED":
        return "Capability"
    return "Policy"


def observed(d: Path) -> tuple[list[tuple[str, str]], str | None]:
    """Which stages of the governed path this directory's audit record shows, and where (if anywhere) it stopped."""
    ev = rows(d / "audit.jsonl")
    types = {e["event_type"] for e in ev}
    policy_seen = any(e["event_type"] == "policy.decided" and e["payload"]["capability"].endswith("rollback") for e in ev)
    out = [(n, "ok" if (policy_seen if et == "policy.write" else et in types) else "none") for n, et in STAGES]
    stop = next((e for e in ev if e["event_type"] in STOP), None)
    if not stop:
        return out, None
    code = stop["payload"].get("code")
    where = stop_stage(code, stop["payload"].get("on"))
    out = [(n, "stop" if n == where else s) for n, s in out]
    return out, f"{STOP[stop['event_type']]}: {code}"


def path_strip(stages: list[tuple[str, str]], note: str | None = None) -> str:
    cells = []
    for name, s in stages:
        mark = {"ok": "✓", "stop": "✕", "none": "·"}[s]
        cells.append(f'<li class="st {s}"><span class="dot">{mark}</span><span class="nm">{esc(name)}</span></li>')
    return f'<ol class="path">{"".join(cells)}</ol>' + (f'<p class="stopnote">Stopped at the red stage — {esc(note)}</p>' if note else "")


# ---- per-experiment visuals (all from recorded facts) ---------------------------------------------------------------------
def vis_r1(e, d):
    f = e["facts"]
    kv = [("workflow", f["workflow_id"]), ("trace", short(f["trace_id"], 16)), ("policy", f["policy_version"]), ("decision", f["decision_id"]),
          ("approval", f"{f['approval_id']} · {f['approver']}"), ("digest", short(f["digest"], 24)), ("capability", f"{f['jti']} · {f['cap_ttl_s']} s"),
          ("idempotency", short(f["idempotency_key"], 24)), ("rollback", f["rollback_id"]), ("after", f"p95 {f['p95_after']} ms · SLO {f['slo']} ms")]
    stats = [("model calls", f["model_calls"]), ("tool calls", int(f["tool_calls"])), ("workflow steps", int(f["workflow_steps"])),
             ("cost units", int(f["cost_units"])), ("audit events", f["audit_events"]), ("spans", f["spans"]), ("evaluations", f"{f['eval_passed']}/{f['eval_total']}")]
    return (path_strip(observed(d)[0]) + '<div class="grid2"><dl class="kv">' + "".join(f"<dt>{esc(k)}</dt><dd><code>{esc(v)}</code></dd>" for k, v in kv)
            + '</dl><div class="stats">' + "".join(f'<div class="stat"><b>{esc(v)}</b><span>{esc(k)}</span></div>' for k, v in stats) + "</div></div>")


def vis_r2(e, d):
    f = e["facts"]
    L = f["layers"]
    bars = "".join(f'<div class="bar"><span class="bl">{esc(k)}</span><span class="bt"><i style="width:{v / max(L.values()) * 100:.0f}%"></i></span><b>{v}</b></div>'
                   for k, v in L.items())
    dec = "".join(f"<tr><td>{esc(k)}</td><td>{chip(v[0], 'deny' if v[0] == 'DENY' else 'wait')}</td><td><code>{esc(v[1])}</code></td>"
                  f"<td>{esc(', '.join(v[2]) or '—')}</td></tr>" for k, v in f["decisions"].items())
    return (f'<div class="grid2"><div><h4>Permissions per layer (sre.alice → agent)</h4>{bars}<div class="bar eff"><span class="bl">effective</span>'
            f'<span class="bt"><i style="width:{len(f["effective"]) / max(L.values()) * 100:.0f}%"></i></span><b>{len(f["effective"])}</b></div>'
            f'<p class="small">effective = {esc(" · ".join(f["effective"]))}</p></div>'
            f'<div><h4>execute_rollback, per target</h4><table class="t"><tr><th>target</th><th>decision</th><th>code</th><th>not granted by</th></tr>{dec}</table>'
            f'<p class="small">“dan” = dev.dan invoking the same agent for checkout-api.</p></div></div>')


def vis_r3(e, d):
    f = e["facts"]
    a = f["attacks"]
    return (f'<div class="digests"><div class="dg ok"><h5>PROPOSED &amp; APPROVED</h5><code class="big">execute_rollback(service="checkout-api", target_version="v4.16")</code>'
            f'<p>approver <b>{esc(f["approver"])}</b> · {esc(f["approval_id"])}</p><p class="hash">{esc(f["approved_digest"])}</p></div>'
            f'<div class="arrow">then the action changes</div>'
            f'<div class="dg bad"><h5>ATTACK</h5><code class="big">target_version: v4.16 → <mark>v4.15</mark></code><p>recomputed digest</p>'
            f'<p class="hash">{esc(f["tampered_digest"])}</p></div>'
            f'<div class="dg verdict"><h5>OBSERVED</h5><p class="v">{chip(a["version"][0], "deny")} <code>{esc(a["version"][1])}</code></p></div></div>'
            '<table class="t"><tr><th>attack</th><th>outcome</th></tr>'
            + "".join(f"<tr><td>{esc(k)}</td><td>{chip(v[0], 'deny')} <code>{esc(v[1])}</code></td></tr>" for k, v in a.items() if k != "version") + "</table>")


def vis_r4(e, d):
    f = e["facts"]
    ex = "".join(f'<li class="{"off" if f"{s}.{t}" not in f["offered"] else "on"}">{esc(s)}.{esc(t)}</li>' for s, ts in f["exposed"].items() for t in ts)
    out = "".join(f"<tr><td><code>{esc(k)}</code></td><td>{chip('DENY', 'deny')} <code>{esc(v)}</code></td></tr>" for k, v in f["outcomes"].items())
    return (f'<div class="grid2"><div><h4>Exposed by MCP ({f["n_exposed"]}) vs offered by discovery ({len(f["offered"])})</h4><ul class="tools">{ex}</ul>'
            f'<p class="small">filled = offered to the agent · outlined = exposed but never offered</p></div>'
            f'<div><h4>A compromised planner asks for them anyway</h4><table class="t"><tr><th>capability</th><th>execution governance</th></tr>{out}</table>'
            f'<p class="small">Control, outside the platform: the untrusted server called directly returned <code>{esc(f["direct"]["status"])}</code> '
            f'— the gateway can refuse to route to it; it cannot make it safe.</p></div></div>')


def vis_r5(e, d):
    f = e["facts"]
    tr = "".join(f"<tr><td>{esc(k.replace('_', ' '))}</td><td>{chip(v[0], 'ok' if v[0] == 'EXECUTED' else 'deny')}</td><td><code>{esc(v[1])}</code></td></tr>"
                 for k, v in f["cases"].items())
    c = f["claims"]
    claims = "".join(f"<dt>{esc(k)}</dt><dd><code>{esc(json.dumps(v) if isinstance(v, dict) else v)}</code></dd>" for k, v in c.items()
                     if k in ("sub", "act", "wl", "aud", "tool", "op", "args", "digest", "exp", "iat", "jti", "uses"))
    return (f'<div class="grid2"><div><h4>Presented to the release MCP server directly (gateway bypassed)</h4><table class="t"><tr><th>capability</th><th>result</th>'
            f'<th>code</th></tr>{tr}</table></div><div><h4>Claims of the capability that executed</h4><dl class="kv">{claims}</dl>'
            f'<p class="small">exp − iat = {c["exp"] - c["iat"]} s. HMAC-signed stand-in for a broker-issued token; see limits.</p></div></div>')


def vis_r6(e, d):
    f = e["facts"]
    lim, use = f["limits"], f["usage"]
    m = {"model_call": "max_model_calls", "tool_call": "max_tool_calls", "workflow_step": "max_workflow_steps", "cost_units": "max_cost_units"}
    meters = "".join(f'<div class="bar{" hit" if m[k] == f["error"]["limit"] else ""}"><span class="bl">{esc(k)}</span><span class="bt"><i style="width:'
                     f'{min(use.get(k, 0) / lim[m[k]], 1) * 100:.0f}%"></i></span><b>{use.get(k, 0):g} / {lim[m[k]]}</b></div>' for k in m)
    return (f'{path_strip(*observed(d))}<div class="grid2"><div><h4>Resource envelope at the stop</h4>{meters}</div><div><h4>What fired</h4>'
            f'<p class="bigcode"><code>{esc(f["error"]["code"])}</code></p><p>{esc(f["error"]["limit"])}: {f["error"]["used"]:g} of {f["error"]["cap"]} used; '
            f'the next call (<code>{esc(f["error"]["on"])}</code>) was refused before it reached a model.</p><p class="small">No prompt contains the word “budget”.</p></div></div>')


def vis_r7(e, d):
    f = e["facts"]
    cand = "".join(f"<tr><td><code>{esc(c['model'])}</code></td><td>{c['priority']}</td><td>{chip('eligible', 'ok') if c['eligible'] else chip('excluded', 'deny')}</td>"
                   f"<td>{esc('; '.join(c['excluded_because']) or '—')}</td></tr>" for c in f["candidates"])
    r = f["routes"][0]
    att = " → ".join(f'{esc(a["model"])} <b class="{"okt" if a["outcome"] == "OK" else "badt"}">{esc(a["outcome"])}</b>' for a in r["attempts"])
    return (f'<div class="grid2"><div><h4>Routing policy, evaluated per call</h4><table class="t"><tr><th>model</th><th>prio</th><th>eligible</th><th>why not</th></tr>{cand}</table></div>'
            f'<div><h4>Observed, every call ({len(f["routes"])})</h4><p class="flow">agent asks for <code>incident-reasoning / high</code> → gateway → {att}</p>'
            f'<p class="small">Both eligible models down: <code>{esc(f["all_down"]["code"])}</code> — fail closed, no silent downgrade to the cheaper us-resident model.</p></div></div>')


def vis_r8(e, d):
    f = e["facts"]
    sel = "".join(f"<li class='on'>{esc(i)}</li>" for i in f["selected"])
    exc = "".join(f"<li class='off'>{esc(k)} <em>{esc(', '.join(v))}</em></li>" for k, v in f["excluded"].items())
    nv = "".join(f"<li class='{'bad' if i not in f['selected'] else 'on'}'>{esc(i)}</li>" for i in f["naive_top4"])
    p = f["predicates"]
    return (f'<p class="flow">identity <code>sre.alice · {esc(p["tenant"])} · {esc(",".join(p["groups"]))} · ≤{esc(p["classifications"][-1])}</code> → '
            f'predicates inside the query → retrieval → ranking → guard → context</p><div class="grid3"><div><h4>Selected (reaches the model)</h4><ul class="tools">{sel}</ul></div>'
            f'<div><h4>Never selected (text not read)</h4><ul class="tools">{exc}</ul></div><div><h4>Control: relevance-only top 4</h4><ul class="tools">{nv}</ul>'
            f'<p class="small">red = would have leaked into the prompt</p></div></div>')


def timeline(d: Path) -> str:
    ev = [r for r in rows(d / "events.jsonl") if r["event_type"] in ("process.started", "workflow.parked", "process.finished")]
    au = [r for r in rows(d / "audit.jsonl") if r["event_type"] in ("approval.requested", "approval.observed", "invocation.restored", "approval.validated",
                                                                     "capability.issued", "action.executed", "action.reconciled", "recovery.detected", "workflow.denied")]
    items = sorted([(r["at"], r["pid"], r["event_type"], r.get("step") or r.get("resumed_from") or "") for r in ev] +
                   [(r["at"], r["pid"], r["event_type"], "") for r in au])
    if not items:
        return ""
    t0 = items[0][0]
    pids = []
    for it in items:
        if it[1] not in pids:
            pids.append(it[1])
    lis = "".join(f'<li class="p{pids.index(p) % 3}"><span class="tt">+{t - t0:0.2f}s</span><span class="pid">pid {p}</span><span class="en">{esc(n)}'
                  f'{(" · " + esc(s)) if s else ""}</span></li>' for t, p, n, s in items)
    return f'<ol class="tl">{lis}</ol>'


def vis_r9(e, d):
    f = e["facts"]
    return (f'<div class="grid2"><div><h4>Three processes, one workflow</h4><table class="t"><tr><th>process</th><th>pid</th><th>exit</th></tr>'
            + "".join(f"<tr><td>{n}</td><td>{p}</td><td>{chip('SIGKILL' if rc == -9 else 'exit 0', 'deny' if rc == -9 else 'ok')}</td></tr>"
                      for n, p, rc in zip(("start → park at approval", "resume → killed after approval checkpoint", "resume → revalidate → execute once"),
                                          f["pids"], f["returncodes"]))
            + f'</table><p class="small">Variant: checkpoint rewritten v4.16 → v4.15 while dead → <code>{esc(f["tampered"]["code"])}</code>, nothing executed.</p></div>'
            f'<div><h4>Recorded timeline</h4>{timeline(d)}</div></div>')


def vis_r10(e, d):
    f = e["facts"]
    cols = [("lookup", "platform: look up the key"), ("resend", "platform: resend, same key"), ("naive", "control: new key per attempt")]
    cards = "".join(f'<div class="lane {"bad" if f[m]["rollbacks"] > 1 else "good"}"><h5>{esc(lbl)}</h5><p>SIGKILL after the pipeline committed '
                    f'(exit {f[m]["sigkill"]}); journal <code>{esc(",".join(f[m]["journal_at_crash"]))}</code></p>'
                    f'<p class="big">{f[m]["rollbacks"]}</p><p>rollback{"s" if f[m]["rollbacks"] != 1 else ""} in the pipeline</p>'
                    f'<p class="small">keys: {esc(", ".join(short(k, 18) for k in f[m]["keys"]))}<br>'
                    f'{"recovered via " + esc(f[m]["recovered_via"]) if f[m]["recovered_via"] else ("idempotent replay" if f[m]["idempotent_replay"] else "executed again")}</p></div>'
                    for m, lbl in cols)
    return f'<div class="lanes">{cards}</div>'


def vis_r11(e, d):
    f = e["facts"]
    c = f["change"]
    return (f'<div class="ks"><div class="kscol on"><h5>{esc(f["bundle_before"])}</h5><code>execute_rollback.enabled: true</code><p>{chip("EXECUTED", "ok")}</p>'
            f'{path_strip(observed(d / "enabled")[0])}</div><div class="kschange"><h5>one central change</h5><p><code>{esc(c["path"])}</code><br>'
            f'{esc(json.dumps(c["old"]))} → <b>{esc(json.dumps(c["new"]))}</b></p><p class="small">by {esc(c["actor"])} · files: {esc(", ".join(c["files_changed"]))}<br>agent sha256 unchanged: '
            f'<code>{esc(short(f["agent_sha256"], 16))}</code></p></div><div class="kscol off"><h5>{esc(f["bundle_after"])}</h5><code>execute_rollback.enabled: false</code>'
            f'<p>{chip("DENIED", "deny")} <code>{esc(f["decision_off"]["code"])}</code></p>{path_strip(*observed(d / "disabled"))}</div></div>')


def vis_r12(e, d):
    f = e["facts"]
    return (f'<p class="inj"><span>injected log line LOG-666</span><code>{esc(f["injected_text"])}</code></p><div class="grid2">'
            f'<div class="lane good"><h5>Defence 1 · context guard (semantic)</h5><p>{chip(f["guard_events"][0]["action"] if f["guard_events"] else "none", "wait")} '
            f'before any model call</p><p>model proposed <code>{esc(f["proposal_guarded"]["service"])} → {esc(f["proposal_guarded"]["target_version"])}</code></p>'
            f'<p class="small">Guardrails influence what the model sees.</p></div><div class="lane bad"><h5>Guard missed (simulated) → Defence 2 · policy (deterministic)</h5>'
            f'<p>model obeyed: <code>{esc(f["proposal_missed"]["service"])} → {esc(f["proposal_missed"]["target_version"])}</code></p>'
            f'<p>{chip(f["policy_missed"]["decision"], "deny")} <code>{esc(f["policy_missed"]["code"])}</code></p><p class="small">{esc(f["policy_missed"]["reasons"][0])}</p>'
            f'<p class="small">Policy controls authority.</p></div></div>')


def vis_r13(e, d):
    f = e["facts"]
    chk = {c["id"].split(".")[1]: c for c in e["checks"]}
    tr = "".join(f"<tr><td>{esc(k.replace('_', ' '))}</td><td><code>{esc(short(json.dumps(v) if not isinstance(v, str) else v, 60))}</code></td>"
                 f"<td>{chip('match', 'ok') if chk[k]['passed'] else chip('MISMATCH', 'deny')}</td></tr>" for k, v in f["answers"].items())
    return (f'<p class="flow">input: trace <code>{esc(f["trace_id"])}</code> → {f["events"]} audit events + {f["spans"]} spans → {f["questions"]} answers, each scored against '
            f'the system of record</p><table class="t"><tr><th>question</th><th>reconstructed from evidence</th><th>vs truth</th></tr>{tr}</table>')


VIS = {"R1": vis_r1, "R2": vis_r2, "R3": vis_r3, "R4": vis_r4, "R5": vis_r5, "R6": vis_r6, "R7": vis_r7, "R8": vis_r8, "R9": vis_r9, "R10": vis_r10,
       "R11": vis_r11, "R12": vis_r12, "R13": vis_r13}


def raw_evidence(eid: str, d: Path) -> str:
    """Collapsible excerpts of the recorded files behind each card."""
    parts = []
    subdirs = [d] + sorted(p for p in d.iterdir() if p.is_dir())
    for sd in subdirs:
        tag = "" if sd == d else f" · {sd.name}"
        pol = [r for r in rows(sd / "policy.jsonl") if r["capability"].endswith("rollback") or r["capability"].endswith("deploy")]
        if pol:
            parts.append(jblock({"input": pol[-1]["input"], "decision": pol[-1]["decision"]}, f"policy input + decision{tag} (policy.jsonl)"))
        ap = rows(sd / "approvals.jsonl")
        if ap:
            parts.append(jblock(ap, f"approval evidence{tag} (approvals.jsonl)"))
        cap = rows(sd / "capability.jsonl")
        if cap:
            parts.append(jblock([c["claims"] for c in cap], f"capability claims{tag} (capability.jsonl; token signatures are never recorded)"))
        au = rows(sd / "audit.jsonl")
        if au:
            parts.append(jblock([{k: r[k] for k in ("seq", "event_type", "pid", "trace_id")} | {"hash": short(r["hash"], 16), "prev": short(r["prev_hash"], 16)} for r in au],
                                f"audit chain{tag} (audit.jsonl, {len(au)} events)"))
        sp = rows(sd / "trace.jsonl")
        if sp:
            parts.append(jblock([{k: s[k] for k in ("name", "trace_id", "span_id", "parent_span_id", "duration_ms", "pid")} | {"attributes": {
                k: v for k, v in s["attributes"].items() if k.startswith(("gen_ai", "platform", "rpc"))}} for s in sp[:60]],
                                f"OpenTelemetry spans{tag} (trace.jsonl, {len(sp)} spans{', first 60' if len(sp) > 60 else ''})"))
    return "".join(parts)


CSS = """
@font-face{font-family:Nunito;src:url(data:font/woff2;base64,__NUNITO__) format('woff2');font-weight:200 1000}
@font-face{font-family:'Lilita One';src:url(data:font/woff2;base64,__LILITA__) format('woff2');font-weight:400}
@font-face{font-family:Cascadia;src:url(data:font/woff2;base64,__CASCADIA__) format('woff2');font-weight:400}
:root{--ink:#172B4D;--sub:#2E3A4F;--body:#52637A;--muted:#8494AA;--line:#E3E8EF;--wash:#F7F9FB;--blue:#2F6FDE;--blue-t:#EEF4FF;--green:#1F9D74;--green-t:#E6F6EF;
--red:#D14D63;--red-t:#FFEEF1;--orange:#D97706;--orange-t:#FFF4E0;--indigo:#4551C9;--indigo-t:#EEF0FD;--teal:#0E8A9A;--teal-t:#E4F5F7;--purple:#6D5BD0;--purple-t:#F1EEFF;
--magenta:#B5487F;--magenta-t:#FBEFF5;--navy:#172B4D;--mono:Cascadia,'SF Mono',Menlo,monospace;--display:'Lilita One',Nunito,sans-serif;--sans:Nunito,-apple-system,'Helvetica Neue',Arial,sans-serif}
*{box-sizing:border-box}code,pre,.mono{font-variant-ligatures:none;font-feature-settings:'calt' 0,'liga' 0}html{-webkit-text-size-adjust:100%;scroll-padding-top:70px}
body{margin:0;background:#fff;color:var(--ink);font:400 15px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
a{color:var(--blue)}code{font-family:var(--mono);font-size:.88em;background:var(--wash);border:1px solid var(--line);border-radius:5px;padding:0 4px;word-break:break-word}
.top{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.95);backdrop-filter:blur(6px);border-bottom:1px solid var(--line)}
.top .in{max-width:1240px;margin:0 auto;padding:10px 20px;display:flex;gap:14px;align-items:center;overflow-x:auto;white-space:nowrap;font-size:13px}
.top b{font-weight:700;margin-right:6px}.top a{color:var(--body);text-decoration:none}.top a:hover{color:var(--ink)}
.wrap{max-width:1240px;margin:0 auto;padding:0 20px}
.hero{background:var(--navy);color:#fff;padding:44px 0 36px}.hero .kick{font:500 13px/1 var(--mono);letter-spacing:.12em;color:#9FB3D1;text-transform:uppercase}
.hero h1{font:400 clamp(32px,5vw,56px)/1.05 var(--display);margin:12px 0 4px;letter-spacing:0}.hero h1 span{color:#8FB4FF}
.hero .tag{font-size:clamp(17px,2.2vw,22px);color:#DCE6F5;margin:14px 0 18px;max-width:760px}
.hero .inc{display:flex;flex-wrap:wrap;gap:10px;align-items:center;font:500 14px/1 var(--mono)}
.hero .inc span{border:1px solid #3B4A66;border-radius:999px;padding:8px 12px;background:#1F3358}.hero .inc .go{background:#1F9D74;border-color:#1F9D74}
.hero .inc .red{background:#7A2336;border-color:#A33A52}
.meas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:22px 0 4px}
.meas div{background:#1F3358;border:1px solid #33476B;border-radius:10px;padding:10px 12px}.meas b{display:block;font-size:20px;line-height:1.2;word-break:break-word}
.meas span{font-size:11.5px;color:#9FB3D1;text-transform:uppercase;letter-spacing:.06em}.meas .pass b{color:#7BE0B8}.meas .fail b{color:#FF9DB0}
.rsr{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0 8px}.rsr>div{border:1px solid #33476B;border-radius:10px;padding:12px 14px;background:#16284A}
.rsr b.h{display:block;font:700 12px/1.2 var(--mono);letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px}.rsr .real b.h{color:#7BE0B8}.rsr .sim b.h{color:#FFD58A}
.rsr .rec b.h{color:#C4B5FF}.rsr ul{margin:0;padding-left:16px;color:#DCE6F5;font-size:13px;line-height:1.45}.rsr li{margin:2px 0}
.idrow{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12.5px;color:#9FB3D1;margin:8px 0 0}.idrow a{color:#DCE6F5}.idrow code{background:#1F3358;border-color:#33476B;color:#DCE6F5;word-break:break-all}
.hero code{background:#1F3358;border-color:#33476B;color:#DCE6F5}.hero pre code{background:none;border:0;padding:0;color:inherit;font-size:inherit;word-break:normal}
.hero pre{background:#0F1B33;color:#DCE6F5;border:1px solid #33476B;padding:12px 14px;border-radius:10px;overflow:auto;font:400 12.5px/1.5 var(--mono);margin:8px 0 0}
.meas .wide{grid-column:span 2}.srcnote{color:#9FB3D1;font-size:12.5px;margin-top:10px}.srcnote code{background:#1F3358;border-color:#33476B;color:#DCE6F5}
h2{font:400 28px/1.2 var(--display);letter-spacing:0;margin:44px 0 6px}h3{font-size:20px;margin:0}h4{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:14px 0 8px}
h5{font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 6px;color:var(--body)}
.lede{color:var(--body);max-width:820px}
.path{list-style:none;padding:0;margin:14px 0 4px;display:flex;flex-wrap:wrap;gap:6px}
.path .st{display:flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:5px 10px 5px 6px;font-size:12.5px;background:#fff}
.path .dot{width:20px;height:20px;border-radius:50%;display:inline-grid;place-items:center;font-size:12px;font-weight:700;color:#fff;background:#CBD3DE}
.path .ok .dot{background:var(--green)}.path .ok{border-color:#B5E3D2}.path .stop .dot{background:var(--red)}.path .stop{border-color:var(--red);background:var(--red-t);font-weight:600}
.path .none{opacity:.45}.stopnote{font-size:13px;color:var(--red);margin:4px 0 0}
.index{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px;margin-top:14px}
.index a{display:block;text-decoration:none;color:inherit;border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:#fff;transition:border-color .15s}
.index a:hover{border-color:var(--blue)}.index .id{font:600 12px/1 var(--mono);color:var(--muted)}.index b{display:block;margin:6px 0 4px}.index p{margin:0;font-size:13px;color:var(--body)}
.card{border:1px solid var(--line);border-radius:16px;margin:26px 0;overflow:hidden;background:#fff;box-shadow:0 1px 0 rgba(23,43,77,.04)}
.card>header{display:flex;gap:14px;align-items:flex-start;justify-content:space-between;padding:18px 20px;border-bottom:1px solid var(--line);background:var(--wash)}
.card>header .q{margin:4px 0 0;color:var(--body)}.card .body{padding:6px 20px 18px}.card .id{font:600 13px/1 var(--mono);color:var(--blue)}
.badge{flex:none;font:700 13px/1 var(--mono);border-radius:999px;padding:8px 12px}.badge.PASS{background:var(--green-t);color:var(--green)}.badge.FAIL{background:var(--red-t);color:var(--red)}
.chip{display:inline-block;font:600 11.5px/1 var(--mono);border-radius:999px;padding:5px 8px;border:1px solid}
.chip.ok{color:var(--green);background:var(--green-t);border-color:#B5E3D2}.chip.deny{color:var(--red);background:var(--red-t);border-color:#F2C2CB}
.chip.wait{color:var(--orange);background:var(--orange-t);border-color:#F6D9A6}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:22px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:6px 12px;margin:12px 0;font-size:13.5px}.kv dt{color:var(--muted)}.kv dd{margin:0;min-width:0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin:12px 0;align-content:start}.stat{border:1px solid var(--line);border-radius:10px;padding:10px}
.stat b{display:block;font-size:22px}.stat span{font-size:12px;color:var(--body)}
table.t{width:100%;border-collapse:collapse;font-size:13.5px;margin:6px 0}.t th{text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
border-bottom:1px solid var(--line);padding:6px 8px}.t td{border-bottom:1px solid var(--line);padding:7px 8px;vertical-align:top}
.checks td:first-child{font:500 12px/1.4 var(--mono);color:var(--muted);white-space:nowrap}.checks td.r{white-space:nowrap}
.checks .x{font-family:var(--mono);font-size:12px;color:var(--body);max-width:320px;overflow-wrap:anywhere}
.bar{display:grid;grid-template-columns:110px 1fr 70px;gap:10px;align-items:center;margin:6px 0;font-size:13px}.bl{color:var(--body)}.bar b{text-align:right;font-family:var(--mono)}
.bt{height:12px;border-radius:6px;background:var(--wash);border:1px solid var(--line);overflow:hidden}.bt i{display:block;height:100%;background:var(--blue)}
.bar.eff .bt i{background:var(--green)}.bar.hit .bt i{background:var(--red)}.bar.hit b{color:var(--red)}
.small{font-size:12.5px;color:var(--body)}
.digests{display:grid;grid-template-columns:1.2fr auto 1.2fr .8fr;gap:12px;align-items:stretch;margin:14px 0}
.dg{border:1.5px solid var(--line);border-radius:12px;padding:12px;min-width:0}.dg.ok{border-color:var(--orange);background:var(--orange-t)}.dg.bad{border-color:var(--red);background:var(--red-t)}
.dg.verdict{border-color:var(--red)}.dg .hash{font:500 11.5px/1.45 var(--mono);word-break:break-all;color:var(--sub);margin:4px 0 0}.dg code.big{display:block;background:#fff;padding:6px}
.dg mark{background:#FFD6DE;color:var(--red);padding:0 2px}.digests .arrow{align-self:center;font-size:12px;color:var(--muted);text-align:center}.dg .v{margin:8px 0 0}
ul.tools{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:6px}ul.tools li{font:500 12px/1 var(--mono);border-radius:7px;padding:6px 8px;border:1px solid var(--teal)}
ul.tools li.on{background:var(--teal-t);color:var(--teal)}ul.tools li.off{background:#fff;color:var(--muted);border-style:dashed;border-color:#CBD3DE}
ul.tools li.bad{background:var(--red-t);color:var(--red);border-color:var(--red)}ul.tools li em{font-style:normal;color:var(--red)}
.flow{font-size:14px;background:var(--wash);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.okt{color:var(--green)}.badt{color:var(--red)}
.lanes{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}.lane{border:1.5px solid var(--line);border-radius:12px;padding:14px}
.lane.good{border-color:#B5E3D2;background:#F4FBF8}.lane.bad{border-color:#F2C2CB;background:#FFF8F9}.lane .big{font-size:clamp(20px,6vw,44px);font-weight:700;margin:6px 0 0;line-height:1;overflow-wrap:anywhere}
.lane.bad .big{color:var(--red)}.lane.good .big{color:var(--green)}
.ks{display:grid;grid-template-columns:1fr .8fr 1fr;gap:12px;margin:14px 0}.kscol{border:1.5px solid;border-radius:12px;padding:12px;min-width:0}
.kscol.on{border-color:#B5E3D2}.kscol.off{border-color:#F2C2CB}.kschange{background:var(--navy);color:#fff;border-radius:12px;padding:12px}
.kschange h5{color:#9FB3D1}.kschange code{background:#1F3358;border-color:#33476B;color:#fff}.kschange .small{color:#C9D3E3}
.inj{border-left:4px solid var(--red);background:var(--red-t);padding:10px 12px;border-radius:8px;display:flex;flex-direction:column;gap:6px}.inj span{font:600 12px/1 var(--mono);color:var(--red)}
.inj code{background:#fff}
.tl{list-style:none;margin:0;padding:0;max-height:330px;overflow:auto;border:1px solid var(--line);border-radius:10px}
.tl li{display:grid;grid-template-columns:62px 80px 1fr;gap:8px;padding:5px 10px;font-size:12.5px;border-bottom:1px solid var(--line)}
.tl .tt{font-family:var(--mono);color:var(--muted)}.tl .pid{font-family:var(--mono)}.tl .p0 .pid{color:var(--indigo)}.tl .p1 .pid{color:var(--red)}.tl .p2 .pid{color:var(--green)}
details.raw{border:1px solid var(--line);border-radius:10px;margin:8px 0;background:#fff}details.raw summary{cursor:pointer;padding:9px 12px;font-size:13px;font-weight:600;color:var(--sub)}
details.raw pre{margin:0;max-height:420px;overflow:auto;background:#0F1B33;color:#DCE6F5;padding:12px;font-size:12px;line-height:1.45;border-radius:0 0 10px 10px}
details.raw pre code{background:none;border:0;color:inherit;padding:0;font-size:inherit}
.rawwrap{margin-top:12px}.rawwrap>h4{margin-top:18px}
.foot{border-top:1px solid var(--line);margin:40px 0 0;padding:20px 0 60px;color:var(--body);font-size:13.5px}
.classes{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:12px 0}.classes>div{border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.classes b.h{display:block;font:700 12px/1.2 var(--mono);letter-spacing:.1em;margin-bottom:2px}.classes ul{margin:6px 0 0;padding-left:16px;font-size:13.5px}.classes li{margin:3px 0}
.classes .real{border-color:#B5E3D2}.classes .real b.h{color:var(--green)}.classes .sim b.h{color:var(--orange)}.classes .rec b.h{color:var(--purple)}.classes .gen b.h{color:var(--muted)}
.classes .inj{border-color:#F2C2CB}.classes .inj b.h{color:var(--red)}.classes .arc b.h{color:var(--muted)}.classes .arc{border-style:dashed}a.ck{font:500 11px/1 var(--mono);white-space:nowrap}
pre.arch{background:#0F1B33;color:#DCE6F5;border-radius:12px;padding:14px 16px;overflow:auto;font:400 12.5px/1.5 var(--mono)}pre.arch code{background:none;border:0;color:inherit;padding:0;font-size:inherit}
.score td.n{font-family:var(--mono);text-align:right}.badge.EXPECTED_FAILURE{background:var(--orange-t);color:var(--orange)}dl.brief{grid-template-columns:110px 1fr}dl.brief dd{color:var(--sub)}
.legend{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.legend span{font-size:12px;border-radius:999px;padding:4px 10px;border:1px solid var(--line)}
@media (max-width:900px){.classes{grid-template-columns:1fr}.rsr{grid-template-columns:1fr}.grid2,.grid3,.lanes,.ks{grid-template-columns:1fr}.digests{grid-template-columns:1fr}.digests .arrow{text-align:left}.meas .wide{grid-column:auto}.lanes{grid-template-columns:minmax(0,1fr)}}
@media (max-width:560px){.card>header{flex-direction:column}.checks td.x{max-width:160px}.bar{grid-template-columns:90px 1fr 60px}.kv{grid-template-columns:1fr}.kv dt{margin-top:6px}}
@media print{.top{display:none}.hero{-webkit-print-color-adjust:exact;print-color-adjust:exact}.card{break-inside:avoid-page}details.raw{display:none}.tl{max-height:none}}
"""


ROOT = HERE.parent
STATUS = {"PASS": ("PASS", "ok"), "EXPECTED_FAILURE": ("EXPECTED FAILURE", "wait"), "FAIL": ("FAIL", "deny")}
ARCH = """ pager (sre.alice) ─▶ request boundary ─▶ durable orchestration ─▶ agent: reasons and proposes, holds no execution capability
                      identity, delegation   checkpoints, journal       │                 ▲
                      effective authority    (SQLite WAL)               ▼                 │
                                                  context gateway    model gateway (recorded A/B, fallback, fail closed)
                                                  (predicates in SQL)
 proposal ─▶ policy P01–P13 ─▶ approval (digest) ─▶ capability broker ─▶ MCP gateway ─▶ release MCP server (stdio)
             ALLOW / DENY /     eligible approver,     one call, short-lived  traceparent    verifies the capability itself;
             REQUIRE_APPROVAL   HMAC-signed            one audience, one use  in _meta       idempotency key bound to the call
 control plane: one signed bundle (registry, policy, budgets, models, guardrails), re-read before every decision
 evidence: OpenTelemetry spans + hash-chained audit + policy, approval and capability records, under one trace id"""


def status_chip(st: str) -> str:
    label, tone = STATUS[st]
    return chip(label, tone)


def build(run_id: str | None = None) -> Path:
    pub = json.loads((ROOT / "evidence" / "published.json").read_text())
    run_id = run_id or pub["run_id"]
    run = ROOT / "evidence" / "runs" / run_id
    rel = lambda p: "../" + Path(p).as_posix()  # noqa: E731   links from lab/ into the POC
    res = json.loads((run / "results.json").read_text())
    man = json.loads((run / "manifest.json").read_text())
    raw = json.loads((run / "raw" / "results.json").read_text())
    checks = [json.loads(x) for x in (run / "checks.jsonl").read_text().splitlines() if x.strip()]
    C = {c["id"]: c for c in checks}
    rp = json.loads((run / "replay.json").read_text())
    nc = json.loads((run / "negative-control" / "results.json").read_text())
    vp = ROOT / "evidence" / "verification" / "verification.json"
    ver = json.loads(vp.read_text()) if vp.exists() else None
    ver = ver if ver and ver.get("run_id") == run_id else None
    F, used = res["facts"], {}

    def fact(k: str) -> str:
        used[k] = F[k]["display"]
        return esc(F[k]["display"])

    RAW = {e["id"]: e for e in raw["experiments"]}
    env, cnt = man["environment"], res["check_counts"]
    b64 = {k: base64.b64encode((FONTS / fn).read_bytes()).decode() for k, fn in
           (("__NUNITO__", "Nunito-Variable-latin.woff2"), ("__LILITA__", "LilitaOne-Regular.woff2"), ("__CASCADIA__", "CascadiaCode-Regular.woff2"))}
    meas = [("proof run", fact("run_id"), "wide"), ("recorded", fact("run.finished_at").replace("T", " ").replace("+00:00", " UTC"), "wide"),
            ("runtime mode", "deterministic · offline", ""), ("experiments", fact("proof.experiments"), ""), ("checks", fact("proof.checks"), ""),
            ("passed", fact("proof.pass"), "pass"), ("expected failures", fact("proof.expected_failure"), ""),
            ("failed", fact("proof.fail"), "fail" if cnt["fail"] else "pass"), ("unit tests", f'{fact("unit_tests_passed")}/{fact("unit_tests")}', "pass"),
            ("MCP transport", f'stdio · SDK {fact("env_mcp_sdk")}', ""), ("state", fact("env_checkpoint_store"), ""), ("model mode", "recorded A/B", ""),
            ("tracing", f'OpenTelemetry {fact("env_opentelemetry_sdk")}', ""), ("replay", fact("replay.level"), "pass"),
            ("negative control", esc(nc["result"].replace("_", " ")), "pass" if nc["result"] == "EXPECTED_FAILURE" else "fail"),
            ("proof schema", fact("proof.schema"), "")]
    mhtml = "".join(f'<div class="{c}"><b>{v}</b><span>{esc(k)}</span></div>' for k, v, c in meas)
    tone = {"REAL": "real", "SIMULATED": "sim", "RECORDED": "rec", "GENERATED": "gen", "INJECTED": "inj", "ARCHITECTURE": "arc"}
    ran = "".join(f'<div class="{tone[c["class"]]}"><b class="h">{esc(c["class"])}</b><p class="small">{esc(c.get("meaning") or "")}</p><ul>'
                  + "".join(f'<li>{esc(i["text"])}' + (f' <a class="ck" href="#chk-{esc(i["check"])}">{esc(i["check"])}</a>' if i.get("check") else "") + "</li>"
                            for i in c["items"]) + "</ul></div>" for c in res["profile"]["classes"])
    r1 = RAW["R1"]
    score = "".join(f'<tr><td><a href="#{esc(x["id"])}">{esc(x["id"])}</a></td><td>{esc(x["title"])}</td><td>{esc(x["question"])}</td>'
                    f'<td class="r">{status_chip(x["result"])}</td><td class="n">{x["counts"]["PASS"]}</td><td class="n">{x["counts"]["EXPECTED_FAILURE"]}</td>'
                    f'<td class="n">{x["counts"]["FAIL"]}</td></tr>' for x in res["experiments"])
    cards = []
    for x in res["experiments"]:
        hid = x.get("harness")
        brief = "".join(f"<dt>{esc(k)}</dt><dd>{esc(x[k]) if isinstance(x[k], str) else '<br>'.join(esc(v) for v in x[k])}</dd>"
                        for k in ("claim", "hypothesis", "setup", "variable", "invariant", "limitations") if x.get(k))
        if hid in VIS:
            e, d = RAW[hid], run / "raw" / RAW[hid]["dir"]
            vis, rawev = VIS[hid](e, d), raw_evidence(hid, d)
        else:   # the negative control: the same proof on a copy without the approval requirement
            g, m = nc["governed"], nc["mutated"]
            vis = (f'<div class="lanes"><div class="lane good"><h5>Governed (published run)</h5><p class="big">{esc(g["policy_decision"])}</p>'
                   f'<p class="small">P1-R1 workflow: {esc(g["parked"])} · harness assertions failed {esc(g["checks_failed"])} of {esc(g["checks"])}</p></div>'
                   f'<div class="lane bad"><h5>Approval requirement removed</h5><p class="big">{esc(m["policy_decision"])}</p>'
                   f'<p class="small">P1-R1 workflow: {esc(m["parked"])} · unapproved rollbacks {esc(m["unapproved_rollbacks"])} · harness assertions failed '
                   f'{fact("neg_checks_failed")} of {fact("neg_checks")} in {esc(re.sub(r"\bR(\d+)\b", r"P1-R\1", m["experiments_failed"]))}</p></div>'
                   f'<div class="lane"><h5>The harness</h5><p class="big">{fact("neg_harness_exceptions")}</p><p class="small">exceptions; exit code '
                   f'{esc(m["proof_exit_code"])}; every experiment ran to the end</p></div></div>'
                   f'<p class="small">Safeguard removed: {esc(nc["safeguard_removed"])}. <a href="{rel(f"evidence/runs/{run_id}/negative-control/raw/mutation.diff")}">mutation.diff</a> · '
                   f'<a href="{rel(f"evidence/runs/{run_id}/negative-control/raw/summary.md")}">the mutated run\'s summary</a></p>')
            rawev = jblock(nc, "the negative control's verdict (negative-control/results.json)")
        rows_ = "".join(
            f'<tr id="chk-{esc(c["id"])}"><td>{esc(c["id"])}</td><td>{esc(c["description"])}<div class="small">{esc(c["kind"])} · <code>{esc(c["fact"])}</code></div></td>'
            f'<td class="x">{esc(c["expected"])}</td><td class="x">{esc(c["actual"])}</td><td class="r">{status_chip(c["status"])}</td>'
            f'<td class="x">' + " ".join(f'<a href="{rel(e["path"])}">{esc(Path(e["path"]).name)}</a>' for e in c["evidence"][:2]) + "</td></tr>"
            for c in (C[i] for i in x["checks"]))
        cards.append(f'<section class="card" id="{esc(x["id"])}"><header><div><span class="id">{esc(x["id"])}</span><h3>{esc(x["title"])}</h3>'
                     f'<p class="q">{esc(x["question"])}</p></div><span class="badge {x["result"]}">{esc(STATUS[x["result"]][0])} · '
                     f'{x["counts"]["PASS"]} pass · {x["counts"]["EXPECTED_FAILURE"]} expected failure · {x["counts"]["FAIL"]} fail</span></header>'
                     f'<div class="body"><dl class="kv brief">{brief}</dl>{vis}'
                     f'<h4>Checks: a comparison of facts read from the run, evaluated by evidence_kit.proof</h4><div style="overflow-x:auto"><table class="t checks">'
                     f'<tr><th>check</th><th>invariant</th><th>expected</th><th>observed</th><th></th><th>evidence</th></tr>{rows_}</table></div>'
                     f'<div class="rawwrap"><h4>Raw evidence</h4>{rawev}</div></div></section>')
    g = rp["groups"]
    replay = (f'<table class="t"><tr><th>rows</th><th>compared</th><th>identical</th><th>volatile (may differ)</th></tr>'
              f'<tr><td>harness assertions: verdict and observed value</td><td>{fact("replay_checks_compared")}</td><td>{fact("replay_checks_identical")}</td><td>—</td></tr>'
              f'<tr><td>content-derived ids (digests, approval, decision, capability, idempotency key, rollback, versions)</td><td>{fact("replay_ids_compared")}</td>'
              f'<td>{fact("replay_ids_identical")}</td><td>—</td></tr>'
              f'<tr><td>trace id, timestamps, process ids, wall-clock time</td><td>{g["volatile"]["rows"]}</td><td>—</td><td>{g["volatile"]["classes"]["NONDETERMINISTIC"]} differ</td></tr></table>'
              f'<p class="small">Level {fact("replay.level")}: {esc(man["replay"]["contract"])}. '
              f'<a href="{rel(f"evidence/runs/{run_id}/replay.json")}">replay.json</a> · <a href="{rel(f"evidence/runs/{run_id}/replay/raw/summary.md")}">the second run</a></p>')
    claims = "".join(f'<tr><td>{esc(c["id"])}</td><td>{esc(c["statement"])}</td><td>{esc(c["verdict"])}</td><td>{esc(", ".join(c.get("experiments", [])) or "—")}</td>'
                     f'<td class="x">' + (" ".join(f'<a href="#chk-{esc(k)}">{esc(k.split("-")[-1])}</a>' for k in c.get("checks", [])) or esc(c.get("rests_on", ""))) + "</td></tr>"
                     for c in res["claims"])
    integ = ("".join(f'<tr><td>{esc(s["section"])}</td><td class="r">{chip(s["status"], "ok" if s["status"] == "PASS" else "wait" if s["status"] == "N/A" else "deny")}</td>'
                     f'<td class="small">{esc(s["detail"])}</td></tr>' for s in ver["sections"]) if ver else "")
    n_sums = len([x for x in (run / "SHA256SUMS").read_text().splitlines() if x.strip()])
    integrity = ((f'<p class="lede">{"VERIFIED" if ver["verified"] else "NOT VERIFIED"} by <code>{esc(ver["command"])}</code>, which reads the shipped evidence and runs no proof.</p>'
                  f'<table class="t">{integ}</table>') if ver else '<p class="lede">Run <code>make verify</code> to verify this run.</p>') + (
        f'<p class="small">SHA256SUMS lists {n_sums} files: the pack, the raw run, the replay and the negative control (a checksum list, not a signature). '
        f'results.json SHA-256 <code>{esc(pub["results_sha256"] if pub["run_id"] == run_id else "n/a")}</code>, recorded in evidence/published.json when the run was promoted.</p>')
    hist = "".join(f'<li><code>{esc(h["run_id"])}</code>: {esc(h["reason"])}</li>' for h in pub["history"]) if pub["run_id"] == run_id else ""
    envkv = "".join(f"<dt>{esc(k)}</dt><dd><code>{esc(v)}</code></dd>" for k, v in
                    [*env.items(), ("source_sha256", man["source_sha256"]), ("agent_code_sha256", man["agent_code_sha256"]),
                     ("proof kit", man["integrity"]["proof_kit"]), ("contract", man["contract"]), ("unit tests", f'{F["unit_tests_passed"]["display"]}/{F["unit_tests"]["display"]}')])
    limits = "".join(f"<li>{esc(c['statement'])}</li>" for c in res["claims"] if c["verdict"] == "limitation")
    limits += "".join(f"<li>Not exercised: {esc(i['text'])}</li>" for c in res["profile"]["classes"] if c["class"] == "ARCHITECTURE" for i in c["items"])
    rawlinks = [("raw/results.json", "what run_proof.py recorded: every harness check, every experiment's facts"), ("raw/run-output.txt", "the run's terminal output"),
                ("raw/trace.jsonl", "OpenTelemetry spans"), ("raw/audit.jsonl", "hash-chained audit events"), ("raw/policy.jsonl", "every policy decision with its input"),
                ("raw/approvals.jsonl", "approval requests and signed decisions"), ("raw/capability.jsonl", "capability issue and verification records"),
                ("raw/events.jsonl", "process and checkpoint events"), ("raw/model_io.jsonl", "model calls (recorded providers)"), ("raw/pytest.txt", "the unit tests"),
                ("manifest.json", "the run manifest"), ("checks.jsonl", "every check"), ("summary.md", "the scorecard"), ("SHA256SUMS", "the checksum list")]
    raws = "".join(f'<li><a href="{rel(f"evidence/runs/{run_id}/{p}")}"><code>{esc(p)}</code></a> {esc(t)}</li>' for p, t in rawlinks if (run / p).exists())
    nav = "".join(f'<a href="#{x["id"]}">{x["id"].removeprefix("P1-")}</a>' for x in res["experiments"])
    lab_facts = {"run_id": run_id, "facts": dict(sorted(used.items()))}
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Proof Lab · Production Agentic AI Platform</title><meta name="description" content="Proof run {esc(run_id)}: one consequential action through every control of the final reference architecture, verified under the Production AI Engineering Proof Contract v1.">
<style>{functools.reduce(lambda c, kv: c.replace(*kv), b64.items(), CSS)}</style></head><body>
<nav class="top" aria-label="Sections"><div class="in"><b>Proof Lab</b><a href="#ran">what ran</a><a href="#path">path</a><a href="#scorecard">scorecard</a>{nav}<a href="#replay">replay</a><a href="#control">control</a><a href="#claims">claims</a><a href="#integrity">integrity</a><a href="#env">environment</a><a href="#limits">limits</a><a href="#raw">raw</a></div></nav>
<header class="hero"><div class="wrap"><div class="kick">Production Agentic AI Platform · Proof Lab</div>
<h1>One consequential action.<br><span>Every control in the path.</span></h1>
<p class="tag">INC-4917 through the final reference architecture: identity, context, model gateway, MCP, deterministic policy, invocation-bound approval, a scoped capability, budgets, the control plane and one causal evidence chain — then broken on purpose.</p>
<div class="inc"><span class="red">INC-4917 · checkout-api · v4.17</span><span>p95 over its {fact("r1_slo")} ms SLO</span><span>→ governed remediation →</span><span class="go">v4.16 · p95 {fact("r1_p95_after")} ms</span></div>
<div class="meas" aria-label="Published proof">{mhtml}</div>
<p class="srcnote">Every value on this page is read from the published run's proof pack (<code>evidence/runs/{esc(run_id)}/</code>, named by <code>evidence/published.json</code>) and the raw evidence beside it. Production AI Engineering Proof Contract v1 (<code>pae-proof/v1</code>).</p></div></header>
<main class="wrap">
<h2 id="ran">What actually ran</h2><p class="lede">Classified by what the code does, not by the diagram. Each REAL and INJECTED item names the check that shows it ran.</p>
<div class="classes">{ran}</div>
<h2 id="arch">The POC, as built</h2><p class="lede">One deep vertical slice: one agent, one incident, one consequential action, every production boundary on its path.</p>
<pre class="arch"><code>{esc(ARCH)}</code></pre>
<h2 id="path">The governed path, as recorded (P1-R1)</h2><p class="lede">What the audit record of R1 shows, in order: each stage is an event in a hash-chained record under one trace id.</p>
{vis_r1(r1, run / "raw" / r1["dir"])}
<div class="legend"><span style="border-color:#B5E3D2">✓ recorded stage</span><span style="border-color:var(--red)">✕ where a request stopped</span><span>· stage never reached</span></div>
<h2 id="scorecard">Scorecard</h2><p class="lede">{fact("proof.experiments")} experiments · {fact("proof.checks")} checks: {fact("proof.pass")} pass, {fact("proof.fail")} fail, {fact("proof.expected_failure")} expected failure. An expected failure is a control: the same scenario without its safeguard, whose invariant breaks as intended.</p>
<div style="overflow-x:auto"><table class="t score"><tr><th>experiment</th><th>title</th><th>question</th><th>result</th><th>pass</th><th>expected failure</th><th>fail</th></tr>{score}</table></div>
{"".join(cards)}
<h2 id="replay">Replay</h2><p class="lede">A second run of the same code, from a fresh start, classified against the published run.</p>{replay}
<h2 id="control">Negative control</h2><p class="lede">{esc(nc["observed"])}. Harness completed: {esc(nc["harness_completed"])}. Result: {esc(nc["result"])}.</p>
<p><a href="#P1-R14">The negative control as an experiment (P1-R14)</a></p>
<h2 id="claims">Claim traceability</h2><p class="lede">Every material claim of the articles → its experiments → its checks; each verdict is tested against the checks.</p>
<div style="overflow-x:auto"><table class="t checks"><tr><th>claim</th><th>statement</th><th>verdict</th><th>experiments</th><th>checks</th></tr>{claims}</table></div>
<h2 id="integrity">Evidence integrity</h2>{integrity}{('<h4>Runs before this one</h4><ul class="small">' + hist + '</ul>') if hist else ''}
<h2 id="env">Environment and versions</h2><dl class="kv">{envkv}</dl>
<h2 id="limits">What this does not prove</h2><ul>{limits}</ul>
<h2 id="raw">Raw evidence</h2><ul class="small">{raws}</ul>
<h2 id="repro">Reproduce</h2><pre class="arch"><code>cd production_agentic_ai_platform &amp;&amp; uv sync
make verify            # PROOF VERIFICATION of the published run (reads the shipped evidence)
make replay            # replay it into evidence/local/ and classify it against the run
make negative-control  # the approval requirement removed: the proof must fail cleanly
make proof RUN_ID=x    # a fresh proof into a new run: run, replay, negative control, pack, verify
uv run python run_proof.py --source-digest   # expect {esc(man["source_sha256"])}</code></pre>
<div class="foot">Published proof: run <code>{esc(run_id)}</code>. Keys used by the run were destroyed at its end. The enterprise systems, identity provider and secrets platform are simulated; models are recorded tapes; MCP, SQLite state, process kills, policy, digests, capabilities, tracing and the audit chain are real.</div>
</main><script type="application/json" id="lab-facts">{html.escape(json.dumps(lab_facts, ensure_ascii=False), quote=False)}</script></body></html>"""
    out = HERE / "index.html"
    out.write_text(page)
    return out


if __name__ == "__main__":
    p = build(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"lab: {p.relative_to(HERE.parent)} ({p.stat().st_size // 1024} KB)")
