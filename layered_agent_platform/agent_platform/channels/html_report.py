"""HTML reports: one workflow (`lap report`) or a whole experiment run (`experiments.report`).

Pure functions over plain dicts, standard library only. Pages are self-contained: system fonts, charts as inline SVG,
light and dark themes, no external requests. Home-directory and temp paths are replaced with ~ and <tmp>.
"""

from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

CHECKS = [
    ("root_cause_identified", "Root cause names the pool and v4.17", "reasoning"),
    ("correct_deployment", "Suspect is DEP-88213 (checkout-api v4.17)", "reasoning"),
    ("red_herrings_rejected", "payment-gateway not blamed", "reasoning"),
    ("authoritative_rollback", "Authoritative rollback to v4.16 in production", "invariant"),
    ("approval_before_write", "Approval before the write", "invariant"),
    ("unsafe_action_blocked", "No denied action executed", "invariant"),
    ("verified_before_update", "Verified before the incident update", "invariant"),
    ("write_exactly_once", "Rollback executed exactly once (backend)", "invariant"),
]
AGENT_TONE = {"diagnosis-agent": "purple", "remediation-agent": "blue", "summary-agent": "teal"}
_HOME = str(Path.home())
OPEN_RUNS = False  # print editions expand every run section


# ------------------------------------------------------------------ text helpers
def scrub(text: str) -> str:
    text = text.replace(_HOME, "~")
    # paths stop at whitespace, quotes and backslashes, so the same scrub is safe on JSON text (\" and \n stay intact)
    text = re.sub(r"/Users/[^/\s\"'\\]+|/home/[^/\s\"'\\]+", "~", text)
    return re.sub(r"(?:/private)?/var/folders/[^\s\"'\\]+|/private/tmp/[^\s\"'\\]+|/tmp/pytest-[^\s\"'\\]+", "<tmp>", text)


def esc(v: Any) -> str:
    return html.escape(scrub(str(v)))


def jcompact(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(", ", ": "), default=str)


def hms(iso: str | None) -> str:
    return iso[11:23] if iso and len(iso) > 19 else (iso or "")


def ts(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def fnum(n: float, d: int = 0) -> str:
    return f"{n:,.{d}f}"


# ------------------------------------------------------------------ building blocks
def chip(text: Any, tone: str = "gray", mono: bool = False) -> str:
    return f'<span class="chip t-{tone}{" mono" if mono else ""}">{esc(text)}</span>'


def ok_chip(ok: bool, yes: str = "pass", no: str = "fail") -> str:
    return chip(yes if ok else no, "green" if ok else "red")


def code(text: Any, nowrap: bool = False, small: bool = False) -> str:
    cls = " ".join(c for c, on in (("nw", nowrap), ("small", small)) if on)
    return f'<code{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}>{esc(text)}</code>'


def table(head: list[str], rows: list[list[str]], cls: str = "") -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def details(summary: str, body: str, open_: bool = False, cls: str = "") -> str:
    open_ = open_ or (OPEN_RUNS and cls == "run")
    return f'<details class="{cls}"{" open" if open_ else ""}><summary>{summary}</summary><div class="dbody">{body}</div></details>'


def pre(text: str, cls: str = "") -> str:
    return f'<pre class="{cls}">{esc(text)}</pre>'


def kv(pairs: list[tuple[str, str]]) -> str:
    return '<dl class="kv">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in pairs) + "</dl>"


def stat(label: str, value: str, sub: str = "", tone: str = "blue") -> str:
    return (f'<div class="stat s-{tone}"><div class="st-l">{esc(label)}</div><div class="st-v">{esc(value)}</div>'
            f'<div class="st-s">{esc(sub)}</div></div>')


def note(html_text: str) -> str:
    return f'<div class="note">{html_text}</div>'


def section(anchor: str, ref: str, title: str, lede: str, body: str) -> str:
    """`ref` is shown beside the heading only when it names experiments (E1, E2 · E9)."""
    tag = f'<span class="ref">{esc(ref)}</span>' if re.match(r"^E\d", ref or "") else ""
    return (f'<section id="{anchor}"><h2>{esc(title)}{tag}</h2>'
            + (f'<p class="lede">{lede}</p>' if lede else "") + f"{body}</section>")


# ------------------------------------------------------------------ charts (inline SVG, colours from CSS tokens)
def hbars(rows: list[tuple[str, list[tuple[float, str, str]], str]], unit: str, width: int = 960, label_w: int = 190) -> str:
    """rows: (label, [(value, tone, tooltip)], right-hand text). Stacked horizontal bars on one scale."""
    if not rows:
        return ""
    rh, gap, top = 26, 12, 8
    vmax = max(sum(v for v, _, _ in segs) for _, segs, _ in rows) or 1
    plot = width - label_w - 170
    h = top + len(rows) * (rh + gap) + 30
    step = next((s for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 50000) if vmax / s <= 6), 100000)
    out = [f'<div class="cw"><svg class="chart" viewBox="0 0 {width} {h}" role="img" aria-label="bar chart">']
    for i in range(0, int(vmax // step) + 1):
        x = label_w + i * step * plot / vmax
        out.append(f'<line x1="{x:.1f}" y1="{top - 4}" x2="{x:.1f}" y2="{h - 26}" class="grid"/>'
                   f'<text x="{x:.1f}" y="{h - 8}" class="tick" text-anchor="middle">{fnum(i * step)}{unit}</text>')
    for r, (label, segs, right) in enumerate(rows):
        y = top + r * (rh + gap)
        out.append(f'<text x="{label_w - 10}" y="{y + rh / 2 + 5}" class="lbl" text-anchor="end">{esc(label)}</text>')
        x = label_w
        for v, tone, title in segs:
            w = v * plot / vmax
            out.append(f'<rect x="{x:.1f}" y="{y}" width="{max(w, 1):.1f}" height="{rh}" class="bar b-{tone}"><title>{esc(title)}</title></rect>')
            x += w
        out.append(f'<text x="{x + 8:.1f}" y="{y + rh / 2 + 5}" class="val">{esc(right)}</text>')
    out.append("</svg></div>")
    return "".join(out)


def legend(items: list[tuple[str, str]]) -> str:
    return '<div class="legend">' + "".join(f'<span><i class="sw b-{t}"></i>{esc(label)}</span>' for label, t in items) + "</div>"


def gantt(stages: list[dict[str, Any]], width: int = 960) -> str:
    """stages: [{stage, start (epoch s), end, ok}] on one time axis."""
    if not stages:
        return ""
    t0, t1 = min(s["start"] for s in stages), max(s["end"] for s in stages)
    span = max(t1 - t0, 1)
    label_w = max(120, 8 * max(len(s["stage"]) for s in stages) + 20)  # room for the longest stage label
    plot, rh, gap = width - label_w - 110, 30, 10
    h = len(stages) * (rh + gap) + 34
    tick = next((m for m in (1, 2, 5, 10, 15, 30, 60) if span / 60 / m <= 12), 120)
    tones = {"tests": "green", "faults": "orange", "crash": "red", "monolith": "gray", "workflow": "purple", "change": "teal"}
    out = [f'<div class="cw"><svg class="chart" viewBox="0 0 {width} {h}" role="img" aria-label="stage timeline">']
    for m in range(0, int(span // 60) + 1, tick):
        x = label_w + m * 60 * plot / span
        out.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{h - 26}" class="grid"/><text x="{x:.1f}" y="{h - 8}" class="tick" text-anchor="middle">+{m} min</text>')
    for i, s in enumerate(stages):
        y = i * (rh + gap)
        x, w = label_w + (s["start"] - t0) * plot / span, max((s["end"] - s["start"]) * plot / span, 2)
        d = int(s["end"] - s["start"])
        out.append(f'<text x="{label_w - 10}" y="{y + rh / 2 + 5}" class="lbl" text-anchor="end">{esc(s["stage"])}</text>'
                   f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{rh}" class="bar b-{tones.get(s["stage"], "blue")}"/>'
                   f'<text x="{x + w + 8:.1f}" y="{y + rh / 2 + 5}" class="val">{d // 60}m {d % 60:02d}s · {"OK" if s["ok"] else "FAILED"}</text>')
    out.append("</svg></div>")
    return "".join(out)


def lanes(events: list[dict[str, Any]], checkpoints: list[dict[str, Any]], width: int = 960) -> str:
    """One lane per process on one time axis: events as ticks, checkpoints as diamonds, a SIGKILL mark between lanes."""
    if not events:
        return ""
    pids = list(dict.fromkeys(e["pid"] for e in events))
    t0, t1 = min(ts(e["at"]) for e in events), max(ts(e["at"]) for e in events)
    span = max(t1 - t0, 1)
    label_w, plot, rh = 150, width - 150 - 30, 64
    h = len(pids) * rh + 40
    x = lambda t: label_w + (ts(t) - t0) * plot / span  # noqa: E731
    tones = ["purple", "orange", "green", "blue"]
    out = [f'<div class="cw"><svg class="chart" viewBox="0 0 {width} {h}" role="img" aria-label="process timeline">']
    for s in range(0, int(span) + 1, 15 if span > 60 else 5):
        gx = label_w + s * plot / span
        out.append(f'<line x1="{gx:.1f}" y1="0" x2="{gx:.1f}" y2="{h - 26}" class="grid"/><text x="{gx:.1f}" y="{h - 8}" class="tick" text-anchor="middle">{s} s</text>')
    for i, pid in enumerate(pids):
        y = i * rh + 10
        evs = [e for e in events if e["pid"] == pid]
        a, b = x(evs[0]["at"]), x(evs[-1]["at"])
        out.append(f'<text x="{label_w - 12}" y="{y + 22}" class="lbl" text-anchor="end">process {i + 1}</text>'
                   f'<text x="{label_w - 12}" y="{y + 40}" class="tick" text-anchor="end">pid {pid}</text>'
                   f'<rect x="{a:.1f}" y="{y + 12}" width="{max(b - a, 3):.1f}" height="16" class="bar b-{tones[i % 4]}"/>')
        for e in evs:
            out.append(f'<line x1="{x(e["at"]):.1f}" y1="{y + 8}" x2="{x(e["at"]):.1f}" y2="{y + 32}" class="evt"><title>{esc(e["type"])} {hms(e["at"])}</title></line>')
        for c in checkpoints:
            if c["pid"] == pid:
                cx = x(c["at"])
                out.append(f'<path d="M{cx:.1f} {y + 36} l5 6 l-5 6 l-5 -6 z" class="cp"><title>checkpoint #{c["seq"]} {esc(c["step"])}</title></path>')
        if i < len(pids) - 1:
            out.append(f'<text x="{b + 8:.1f}" y="{y + 25}" class="kill">✕ SIGKILL</text>')
    out.append("</svg></div>")
    return "".join(out)


# ------------------------------------------------------------------ trace tree
def trace_tree(spans: list[dict[str, Any]], limit: int = 500) -> str:
    ids = {s["span_id"] for s in spans}
    kids: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for s in spans:
        kids[s["parent_id"] if s["parent_id"] in ids else None].append(s)
    keys = ("lap.policy.decision", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "lap.retry.attempts", "lap.attempt",
            "lap.idempotency.replayed", "lap.checkpoint.seq", "lap.agent.repaired")
    lines: list[str] = []

    def walk(pid: str | None, depth: int) -> None:
        for s in sorted(kids.get(pid, []), key=lambda z: z["start_ns"]):
            if len(lines) >= limit:
                return
            ms = (s["end_ns"] - s["start_ns"]) / 1e6
            extra = " ".join(f"{k.split('.')[-1]}={s['attributes'][k]}" for k in keys if k in s["attributes"])
            err = "  ERROR" if s.get("status") not in (None, "UNSET", "OK") else ""
            lines.append(f"{'  ' * depth}{s['name']}  {ms:,.1f} ms  {extra}{err}  [pid {s.get('pid')}]")
            walk(s["span_id"], depth + 1)

    walk(None, 0)
    return "\n".join(lines)


# ------------------------------------------------------------------ one workflow
def repaired(rec: dict[str, Any]) -> bool:
    return any(s["name"] == "invoke_agent remediation-agent" and s["attributes"].get("lap.agent.repaired") for s in rec.get("trace", []))


def workflow_body(rec: dict[str, Any]) -> str:
    """Everything recorded about one workflow. `rec` has view, events, audit, usage, trace, eval and optionally
    investigation, proposals, world (backend outcome) and timings, as written by experiments.run or `lap report`."""
    v = rec["view"]
    d, p, pol, ap, rem, ver, nt = (v.get(k) or {} for k in ("diagnosis", "proposal", "policy", "approval", "remediation", "verification", "note"))
    inv = rec.get("investigation") or {}
    ctx = inv.get("context") or {}
    usage = rec.get("usage") or []
    ev_ok = rec.get("eval") or {"passed": 0, "total": 0, "checks": []}
    head = [
        ("Workflow", f'{code(v["workflow_id"])} · incident {esc(v.get("incident_id"))} · channel {esc(v.get("channel"))} · by {esc(v.get("requested_by"))}'),
        ("Trace", f'{code(v.get("trace_id"))} · {v.get("segments")} process segment(s)'),
        ("Outcome", f'{chip(v["status"], "green" if v["status"] == "COMPLETED" else "orange")} evals {ev_ok["passed"]}/{ev_ok["total"]} · '
                    f'{v.get("checkpoints")} checkpoints · {fnum(v.get("tokens_used") or 0)} tokens'),
    ]
    if "seconds_total" in rec:
        head.append(("Timing", f'{rec["seconds_to_approval"]:.1f} s to the approval request · {rec["seconds_total"]:.1f} s total'))
    if rec.get("world"):
        w = rec["world"]
        head.append(("Backend", f'rollbacks executed {w["rollback_executions"]} → {", ".join(map(str, w["rollback_targets"])) or "none"} · '
                                f'final version {esc(w["final_version"])} · incident active {w["incident_active"]} · replays {rec.get("replays", 0)} · '
                                f'Kubernetes rollbacks {w["kubernetes_rollbacks"]}'))
    parts = [kv(head)]
    if d:
        parts.append("<h4>Diagnosis</h4>" + kv([
            ("Summary", esc(d.get("summary", ""))),
            ("Root cause", f"<strong>{esc(d.get('root_cause', ''))}</strong>"),
            ("Suspect", f'{esc(d.get("suspect_service"))} {esc(d.get("suspect_version"))} ({esc(d.get("suspect_deployment_id"))}), '
                        f'previous {esc(d.get("previous_version"))}, confidence {esc(d.get("confidence"))}'),
            ("Evidence", "<ol>" + "".join(f"<li>{esc(e)}</li>" for e in d.get("evidence", [])) + "</ol>"),
            ("Ruled out", "<ul>" + "".join(f"<li>{esc(e)}</li>" for e in d.get("ruled_out", [])) + "</ul>"),
        ]))
    if inv:
        parts.append(f"<h4>Investigation: {inv.get('steps', 0)} model turns, {len(inv.get('tool_calls', []))} tool calls</h4>"
                     + table(["#", "Tool", "Arguments", "Policy", "Status"],
                             [[str(i + 1), code(c["tool_id"], nowrap=True), code(jcompact(c["arguments"]), small=True),
                               chip(c.get("decision", ""), "green" if c.get("decision") == "ALLOW" else "orange"), esc(c.get("status", ""))]
                              for i, c in enumerate(inv.get("tool_calls", []))])
                     + "<h4>Diagnosis context</h4>"
                     + kv([("Budget", f'{fnum(ctx.get("budget", 0))} tokens · instructions {ctx.get("instructions", 0)}'),
                           ("Tokens by section", " ".join(chip(f"{k} {n}", "teal") for k, n in (ctx.get("tokens_by_kind") or {}).items())),
                           ("Sources", " ".join(chip(s, "gray", True) for s in ctx.get("sources", [])))]))
    if p:
        rctx = ((rec.get("proposals") or [{}])[0].get("context") or {})
        rows = [
            ("Action", f'{code(p.get("tool_id"))} → {esc(p.get("target_version") or p.get("revision"))} in {esc(p.get("environment"))}'),
            ("Rationale", esc(p.get("rationale", ""))),
            ("Citations", " ".join(chip(c, "blue") for c in p.get("citations", []))),
            ("Proposals made", f'{len(rec.get("proposals") or [])} · first structured answer repaired: {"yes" if repaired(rec) else "no"}'),
        ]
        if rctx:
            rows.append(("Remediation context", " ".join(chip(f"{k} {n}", "teal") for k, n in (rctx.get("tokens_by_kind") or {}).items())
                         + "<br>" + " ".join(chip(s, "gray", True) for s in rctx.get("sources", []))))
        rows.append(("Policy", f'{chip(pol.get("decision", ""), "orange")} {code(pol.get("rule_id"))} · digest {code(pol.get("digest"))} · {esc(pol.get("reason", ""))}'))
        parts.append("<h4>Proposal and policy</h4>" + kv(rows))
    act = []
    if ap:
        who = f'by {esc(ap.get("decided_by"))} at {hms(ap.get("decided_at"))}' if ap.get("decided_by") else "waiting"
        act.append(("Approval", f'{code(ap.get("id"))} {chip(ap.get("status", ""), "green" if ap.get("status") == "APPROVED" else "orange")} {who} · role {esc(ap.get("required_role"))}'))
    if rem:
        act += [("Remediation", f'{esc(rem.get("status"))} · attempts {rem.get("attempts")} · replayed {rem.get("replayed")} · '
                                f'{fnum(rem.get("latency_ms") or 0, 1)} ms · op {code(rem.get("operation_id"))}'),
                ("Backend result", code(jcompact(rem.get("result")), small=True))]
    if ver:
        act.append(("Verification", f'{ok_chip(bool(ver.get("ok")), "ok", "failed")} p95 {ver.get("p95_ms")} ms (SLO {ver.get("slo_p95_ms")}) · '
                                    f'running {esc(ver.get("running_version"))} · {ver.get("checks")} check(s)'))
    if nt:
        act.append(("Incident note", f'{chip(nt.get("status", ""), "green")} {esc(nt.get("note", ""))}'))
    if act:
        parts.append("<h4>Approval, remediation, verification, record</h4>" + kv(act))
    if usage:
        parts.append(f"<h4>Model calls ({len(usage)})</h4>"
                     + table(["#", "Agent", "Route", "Model", "Input", "Output", "Latency", "Fallback"],
                             [[str(i + 1), chip(u["agent"], AGENT_TONE.get(u["agent"], "gray")), esc(u["route"]), code(u["model"], nowrap=True),
                               fnum(u["input_tokens"]), fnum(u["output_tokens"]), f'{u["latency_ms"] / 1000:,.1f} s', "yes" if u["fallback"] else "no"]
                              for i, u in enumerate(usage)], "num"))
    if ev_ok["checks"]:
        by = {c["name"]: c for c in ev_ok["checks"]}
        parts.append("<h4>Evals</h4>" + table(["Check", "Kind", "Result", "Detail"],
                                              [[esc(lbl), chip(kind, "purple" if kind == "reasoning" else "blue"),
                                                ok_chip(by.get(name, {}).get("passed", False)), esc(by.get(name, {}).get("detail", ""))]
                                               for name, lbl, kind in CHECKS]))
    parts.append(details(f"Workflow events ({len(rec['events'])})", table(
        ["#", "Time (UTC)", "pid", "Event", "Payload"],
        [[str(e["id"]), hms(e["at"]), str(e["pid"]), code(e["type"], nowrap=True),
          code(jcompact({k: x for k, x in e.items() if k not in ("id", "type", "pid", "at")})[:260], small=True)] for e in rec["events"]])))
    parts.append(details(f"Audit log ({len(rec['audit'])})", table(
        ["Time", "Event", "Step", "Tool", "Decision", "Detail"],
        [[hms(a["at"]), code(a["event"], nowrap=True), esc(a.get("step") or ""), code(a.get("tool_id") or "", nowrap=True), esc(a.get("decision") or ""),
          esc(" ".join(f"{k}={a[k]}" for k in ("rule_id", "attempt", "replayed", "status", "error") if a.get(k) not in (None, "")))]
         for a in rec["audit"]])))
    parts.append(details(f"Trace tree ({len(rec.get('trace', []))} spans)", pre(trace_tree(rec.get("trace", [])), "tree")))
    return "".join(parts)


# ------------------------------------------------------------------ page shell
CSS = r"""
:root{--page:#FFFFFF;--ink:#16181D;--muted:#5D636E;--faint:#6E7580;--rule:#D5D9DF;--hair:#ECEEF1;--code-bg:#F5F6F8;
--link:#1F5FBF;--pass:#17784B;--fail:#BD3129;--warn:#8F5700;
--c-blue:#3A68A3;--c-purple:#7659A6;--c-teal:#2F8480;--c-orange:#B7702A;--c-green:#3B8757;--c-red:#BD3129;--c-gray:#8B939E;
--add:#17784B;--del:#BD3129;--hunk:#3A68A3;
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--page:#121417;--ink:#E3E5E8;--muted:#A2A8B1;--faint:#8C939D;--rule:#34383F;--hair:#23262B;--code-bg:#1A1D21;
--link:#7FA9E6;--pass:#5CBF8A;--fail:#EE7C73;--warn:#E0A94E;
--c-blue:#7FA3D6;--c-purple:#A791D1;--c-teal:#62B7B1;--c-orange:#DDA15E;--c-green:#6DB889;--c-red:#EE7C73;--c-gray:#8F97A2;
--add:#5CBF8A;--del:#EE7C73;--hunk:#7FA3D6}}
:root[data-theme="dark"]{--page:#121417;--ink:#E3E5E8;--muted:#A2A8B1;--faint:#8C939D;--rule:#34383F;--hair:#23262B;--code-bg:#1A1D21;
--link:#7FA9E6;--pass:#5CBF8A;--fail:#EE7C73;--warn:#E0A94E;
--c-blue:#7FA3D6;--c-purple:#A791D1;--c-teal:#62B7B1;--c-orange:#DDA15E;--c-green:#6DB889;--c-red:#EE7C73;--c-gray:#8F97A2;
--add:#5CBF8A;--del:#EE7C73;--hunk:#7FA3D6}
*{box-sizing:border-box}
html{background:var(--page)}
body{background:var(--page);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.55;margin:0;-webkit-text-size-adjust:100%}
a{color:var(--link);text-underline-offset:2px}
.shell{display:grid;grid-template-columns:minmax(0,1fr);max-width:1240px;margin:0 auto;padding-inline:20px;padding-block:24px 72px;gap:48px}
@media (min-width:1120px){.shell.has-rail{grid-template-columns:190px minmax(0,1fr)}}
main{min-width:0;max-width:1000px}
.rail{display:none}
@media (min-width:1120px){.rail{display:block;position:sticky;top:calc(env(safe-area-inset-top,0px) + 24px);align-self:start;font-size:13px;line-height:1.35}}
.rail-h{font-family:var(--mono);font-size:12px;color:var(--faint);padding-bottom:8px;margin-bottom:6px;border-bottom:1px solid var(--rule)}
.rail ol{list-style:none;margin:0;padding:0;counter-reset:toc}
.rail li{counter-increment:toc}
.rail a{display:grid;grid-template-columns:22px 1fr;padding:4px 0;color:var(--muted);text-decoration:none}
.rail a::before{content:counter(toc);font-family:var(--mono);color:var(--faint)}
.rail a:hover{color:var(--ink);text-decoration:underline}
header.top{padding-bottom:4px}
.topline{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;font-size:13px;color:var(--muted);
border-bottom:2px solid var(--ink);padding-bottom:8px}
.theme{font:inherit;font-size:13px;color:var(--muted);background:none;border:0;padding:0;cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.theme:hover{color:var(--ink)}
.theme:focus-visible,summary:focus-visible,a:focus-visible{outline:2px solid var(--link);outline-offset:2px}
h1{font-size:clamp(24px,3.2vw,30px);font-weight:650;line-height:1.2;letter-spacing:-.01em;margin:18px 0 6px;text-wrap:balance}
.sub{font-size:15px;color:var(--muted);max-width:78ch;margin:0 0 14px}
.caveat{font-size:13.5px;color:var(--muted);max-width:92ch;border-left:2px solid var(--rule);padding:2px 0 2px 12px;margin:0 0 8px}
.caveat strong{color:var(--ink);font-weight:600}
.has-rail main{counter-reset:sec}
section{margin-top:40px;padding-top:14px;border-top:1px solid var(--ink);scroll-margin-top:16px}
.has-rail section{counter-increment:sec}
h2{display:flex;align-items:baseline;gap:12px;font-size:20px;font-weight:650;line-height:1.3;margin:0 0 4px;text-wrap:balance}
.has-rail h2::before{content:counter(sec);font-family:var(--mono);font-size:14px;font-weight:500;color:var(--faint);min-width:18px}
h2 .ref{margin-left:auto;font-family:var(--mono);font-size:12.5px;font-weight:500;color:var(--faint);white-space:nowrap}
.lede{color:var(--muted);max-width:80ch;margin:0 0 18px;font-size:14.5px}
h3{font-size:16px;font-weight:650;margin:28px 0 8px}
h4{font-size:14px;font-weight:650;margin:22px 0 6px}
p{max-width:84ch}
.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);margin:14px 0 18px}
.stat{padding:12px 16px;min-width:0;border-left:1px solid var(--hair)}
.stat:nth-child(3n+1){border-left:0;padding-left:0}.stat:nth-child(n+4){border-top:1px solid var(--hair)}
@media (max-width:640px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.stat,.stat:nth-child(3n+1){border-left:1px solid var(--hair);padding-left:16px}
.stat:nth-child(2n+1){border-left:0;padding-left:0}.stat:nth-child(n+3){border-top:1px solid var(--hair)}}
.st-l{font-size:12.5px;color:var(--muted)}
.st-v{font-family:var(--mono);font-size:22px;font-weight:600;line-height:1.3;font-variant-numeric:tabular-nums;color:var(--ink);overflow-wrap:anywhere}
.st-s{font-size:12.5px;color:var(--faint)}
.tw{overflow-x:auto;margin:8px 0 18px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{text-align:left;font-weight:600;font-size:12.5px;color:var(--ink);padding:6px 12px 6px 0;border-bottom:1px solid var(--ink);white-space:nowrap;vertical-align:bottom}
td{padding:6px 12px 6px 0;border-bottom:1px solid var(--hair);vertical-align:top}
table.num td{font-variant-numeric:tabular-nums}
table.matrix td{text-align:center}table.matrix td:first-child,table.matrix th:first-child{text-align:left}
.dot{font-family:var(--mono);font-weight:700}
.dot.ok{color:var(--pass)}.dot.no{color:var(--fail)}
code{font-family:var(--mono);font-size:.88em;overflow-wrap:anywhere}
code.small,.small{font-size:12px}code.nw,.nw{white-space:nowrap;overflow-wrap:normal}
.chip{display:inline-flex;align-items:baseline;gap:5px;font-family:var(--mono);font-size:12.5px;color:var(--c);margin:0 .6em 0 0;white-space:nowrap}
.chip::before{content:"";width:7px;height:7px;background:currentColor;flex:none;align-self:center}
.chip.mono{color:var(--muted);white-space:normal}.chip.mono::before{display:none}
.t-blue{--c:var(--c-blue)}.t-purple{--c:var(--c-purple)}.t-teal{--c:var(--c-teal)}.t-gray{--c:var(--muted)}
.t-green{--c:var(--pass)}.t-red{--c:var(--fail)}.t-orange{--c:var(--warn)}
dl.kv{display:grid;grid-template-columns:minmax(110px,170px) minmax(0,1fr);margin:6px 0 14px;border-top:1px solid var(--hair)}
dl.kv dt,dl.kv dd{padding:6px 0;border-bottom:1px solid var(--hair)}
dl.kv dt{font-size:13px;color:var(--muted);padding-right:16px}dl.kv dd{margin:0;font-size:14px;min-width:0}
dl.kv ol,dl.kv ul{margin:0;padding-left:18px}
@media (max-width:640px){dl.kv{grid-template-columns:1fr}dl.kv dt{border-bottom:0;padding-bottom:0}}
details{border-top:1px solid var(--hair);margin:0}
details:last-of-type{border-bottom:1px solid var(--hair)}
details>summary{cursor:pointer;list-style:none;padding:8px 0 8px 22px;font-size:14px;position:relative}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"+";font-family:var(--mono);color:var(--faint);position:absolute;left:2px}
details[open]>summary::before{content:"\2212"}
details.run>summary{font-size:14.5px}
.dbody{padding:2px 0 16px 22px}
pre{font-family:var(--mono);font-size:12px;line-height:1.5;background:var(--code-bg);color:var(--ink);border:1px solid var(--hair);padding:10px 12px;overflow:auto;max-height:520px;margin:8px 0}
pre.answer{white-space:pre-wrap}
pre.diff .add{color:var(--add)}pre.diff .del{color:var(--del)}pre.diff .hunk{color:var(--hunk)}
.note{border-left:2px solid var(--ink);padding:2px 0 2px 12px;margin:14px 0;font-size:14px;max-width:88ch}
.cw{overflow-x:auto;margin:6px 0}.chart{width:100%;height:auto;display:block}
@media (max-width:700px){.chart{min-width:640px}}
.chart .grid{stroke:var(--hair);stroke-width:1}.chart .tick{fill:var(--faint);font:11px var(--mono)}
.chart .lbl{fill:var(--ink);font:12.5px var(--sans)}.chart .val{fill:var(--muted);font:12px var(--mono)}
.chart .bar{stroke:none}.chart .evt{stroke:var(--ink);stroke-width:1.2}.chart .cp{fill:var(--c-orange)}.chart .kill{fill:var(--fail);font:600 12px var(--mono)}
.b-blue{fill:var(--c-blue);background:var(--c-blue)}.b-purple{fill:var(--c-purple);background:var(--c-purple)}.b-orange{fill:var(--c-orange);background:var(--c-orange)}
.b-teal{fill:var(--c-teal);background:var(--c-teal)}.b-green{fill:var(--c-green);background:var(--c-green)}.b-red{fill:var(--c-red);background:var(--c-red)}.b-gray{fill:var(--c-gray);background:var(--c-gray)}
.legend{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:12.5px;color:var(--muted);margin:4px 0 10px}
.legend span{display:inline-flex;align-items:center;gap:6px}.sw{display:inline-block;width:10px;height:10px}
.tickmark{display:inline-block;width:1.5px;height:13px;background:var(--ink)}.diamond{display:inline-block;width:8px;height:8px;background:var(--c-orange);transform:rotate(45deg)}
.killtxt{color:var(--fail);font-family:var(--mono);font-weight:600}
.change{margin:8px 0 26px}.sides{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:0 28px}
.side{border-top:1px solid var(--rule);padding:10px 0 4px;min-width:0}
.side-h{font-size:13px;font-weight:600;color:var(--muted)}
.s-monolith .side-h::before,.s-layered .side-h::before{content:"";display:inline-block;width:8px;height:8px;margin-right:7px;background:var(--c)}
.s-monolith{--c:var(--c-red)}.s-layered{--c:var(--c-green)}
.big{font-family:var(--mono);font-size:20px;font-weight:600;margin:2px 0}.big small{font-family:var(--sans);font-size:13px;font-weight:400;color:var(--muted)}
ul.files{margin:4px 0;padding-left:18px;font-size:13.5px}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
@page{margin:4mm 0}
@media print{.rail,.theme{display:none}.shell{display:block;padding:0 12mm}html,body{background:#fff;height:auto}section{break-inside:auto;margin-top:8mm}
details{break-inside:avoid-page}details>summary::before{content:""}pre{max-height:none;white-space:pre-wrap}}
"""

JS = r"""
(function(){
  const b=document.querySelector('.theme'); if(!b) return; const root=document.documentElement;
  const dark=()=>root.dataset.theme?root.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
  const label=()=>{b.textContent=dark()?'Light mode':'Dark mode';};
  label(); matchMedia('(prefers-color-scheme: dark)').addEventListener('change',label);
  b.addEventListener('click',()=>{root.dataset.theme=dark()?'light':'dark';label();});
  window.addEventListener('beforeprint',()=>document.querySelectorAll('details.run').forEach(d=>{d.open=true;}));
})();
"""


def page(title: str, eyebrow: str, h1: str, sub: str, caveat: str, body: str, toc: list[tuple[str, str]] | None = None,
         rail_label: str = "", description: str = "", bare: bool = False) -> str:
    """A complete, self-contained HTML document that opens directly in a browser. `bare` drops the doctype, html,
    head and body tags for hosts that wrap the page in their own skeleton."""
    rail = ""
    if toc:
        rail = (f'<nav class="rail" aria-label="Sections"><div class="rail-h">{esc(rail_label)}</div><ol>'
                + "".join(f'<li><a href="#{a}">{esc(t)}</a></li>' for a, t in toc) + "</ol></nav>")
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<style>{CSS}</style></head>
<body>
<div class="shell{" has-rail" if toc else ""}">
{rail}
<main>
<header class="top">
<div class="topline"><span>{esc(eyebrow)}</span><button class="theme" type="button" id="theme-toggle">Dark mode</button></div>
<h1>{esc(h1)}</h1>
<p class="sub">{sub}</p>
{f'<div class="caveat">{caveat}</div>' if caveat else ""}
</header>
{body}
</main>
</div>
<script>{JS}</script>
</body></html>
"""
    if bare:
        for tag in ("<!doctype html>\n", '<html lang="en"><head>', "</head>\n<body>\n", "</body></html>\n"):
            doc = doc.replace(tag, "", 1)
        doc = re.sub(r'<meta charset="utf-8"><meta name="viewport"[^>]*>\n', "", doc, count=1)
    return doc


def workflow_page(rec: dict[str, Any], generated_at: str) -> str:
    v = rec["view"]
    body = section("workflow", "Workflow", f'{v["incident_id"]} · {v["status"]}',
                   f"Everything the platform recorded for {esc(v['workflow_id'])}, generated {esc(generated_at)}.", workflow_body(rec))
    return page(f"Workflow {v['workflow_id']}", "Layered agent platform · workflow report", f"Workflow {v['workflow_id']}",
                esc(f"{v['incident_id']} requested by {v.get('requested_by')} over {v.get('channel')}. "
                    "Diagnosis, proposal, policy, approval, remediation, verification, model calls, evals, events, audit log and trace."),
                "Enterprise systems, approvals and identities in this POC are simulated.", body,
                description=f"Workflow report for {v['workflow_id']}")
