"""`poc`: the POC's front door. One command per thing a reader wants to do.

    uv run poc check                         is this machine ready? (Ollama, models, memory, MCP servers)
    uv run poc demo                          INC-4917 end to end in about 2 minutes, then open its report
    uv run poc demo --replay                 the same without Ollama: recorded model answers, everything else real
    uv run poc run --profile quick           every experiment, small: about 5 minutes
    uv run poc run --profile standard        both models, 3 runs each: about 10 minutes
    uv run poc run --profile full            plus the end-to-end model tests: about 15 minutes
    uv run poc run --replay                  every experiment from recorded model traffic, in about 3 minutes
    uv run poc runs                          every run on this machine, with its status and report
    uv run poc open [latest|demo|<run-id>]   open a report in the browser

Minutes are measured on a 24 GB Apple Silicon laptop with Ollama otherwise idle. `lap` stays the platform's own CLI;
`poc` is the harness around it (it resets the simulated enterprise systems, which the platform never touches).
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
MODELS = ["gpt-oss:20b", "qwen3:8b"]
EMBEDDING = "nomic-embed-text"
NUM_CTX = 32768
REFERENCE_RUN = "2026-09-17-recorded"  # live run whose model traffic ships with the POC
DEMO_RECORDINGS = ROOT / "traffic" / "recordings"
PROFILES: dict[str, dict[str, Any]] = {
    "quick": {"models": ["gpt-oss:20b"], "k": 1, "model_tests": False, "minutes": 5,
              "what": "gpt-oss:20b only, one run per scenario, fast tests"},
    "standard": {"models": MODELS, "k": 3, "model_tests": False, "minutes": 10,
                 "what": "both models, three runs each, fast tests"},
    "full": {"models": MODELS, "k": 3, "model_tests": True, "minutes": 15,
             "what": "standard, plus the end-to-end tests against the models"},
}
TTY = sys.stdout.isatty()


# ------------------------------------------------------------------ output
def c(text: str, color: str) -> str:
    codes = {"green": "32", "red": "31", "yellow": "33", "dim": "2", "bold": "1", "cyan": "36"}
    return f"\033[{codes[color]}m{text}\033[0m" if TTY else text


MARK = {"ok": c("✓", "green"), "warn": c("!", "yellow"), "fail": c("✗", "red"), "skip": c("–", "dim")}


def table(rows: list[tuple[str, str, str]], pad: int = 2) -> None:
    width = max((len(r[1]) for r in rows), default=0)
    for status, item, detail in rows:
        print(f"{' ' * pad}{MARK[status]} {item.ljust(width)}  {detail}")


def heading(text: str) -> None:
    print("\n" + c(text, "bold"))


def ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")


def clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("LAP_")}
    env.update(extra)
    return env


def open_file(path: Path, want: bool) -> None:
    if want and TTY and not os.environ.get("CI"):
        webbrowser.open(path.resolve().as_uri())


def link_latest(link: Path, target: Path) -> None:
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target.name, target_is_directory=True)
    except OSError:  # no symlinks (for example Windows without developer mode): leave a pointer file instead
        link.with_suffix(".txt").write_text(target.name)


def resolve_latest(link: Path) -> Path | None:
    if link.exists():
        return link.resolve()
    pointer = link.with_suffix(".txt")
    return link.parent / pointer.read_text().strip() if pointer.exists() else None


# ------------------------------------------------------------------ check
def memory_gb() -> float | None:
    try:
        if sys.platform == "darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 2**30
        if Path("/proc/meminfo").exists():
            kb = int(Path("/proc/meminfo").read_text().split("MemTotal:")[1].split()[0])
            return kb / 2**20
    except (ValueError, IndexError, OSError):
        return None
    return None


async def mcp_tools() -> int:
    from agent_platform.actions.mcp_pool import McpPool
    from mock_enterprise.world import World

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "enterprise.db"
        World(db).reset()
        pool = McpPool(db)
        try:
            await pool.start()
            return len(pool.tools)
        finally:
            await pool.close()


def check(replay: bool = False, quiet: bool = False, models: list[str] | None = None) -> bool:
    models = models or MODELS
    rows: list[tuple[str, str, str]] = []
    rows.append(("ok" if sys.version_info >= (3, 12) else "fail", "Python", platform.python_version()))
    if replay:
        rows.append(("skip", "Ollama", "not needed: model answers come from a recording"))
    else:
        try:
            tags = {m["name"] for m in httpx.get(f"{ollama_url()}/api/tags", timeout=3).json()["models"]}
            rows.append(("ok", "Ollama", ollama_url()))
            for m in [*models, EMBEDDING]:
                present = m in tags or f"{m}:latest" in tags
                rows.append(("ok" if present else "fail", f"model {m}", "present" if present else f"missing: run `ollama pull {m}`"))
            loaded = httpx.get(f"{ollama_url()}/api/ps", timeout=3).json().get("models", [])
            for m in loaded:
                name, ctx = m["name"], m.get("context_length")
                if name.split(":latest")[0] not in [*models, EMBEDDING]:
                    rows.append(("warn", "Ollama is busy", f"{name} is loaded; runs will swap models and slow down"))
                elif ctx and name != f"{EMBEDDING}:latest" and ctx != NUM_CTX:
                    rows.append(("warn", "Ollama context", f"{name} is loaded with num_ctx {ctx}; the POC uses {NUM_CTX}, so Ollama will reload it"))
        except (httpx.HTTPError, KeyError, ValueError):
            rows.append(("fail", "Ollama", f"not reachable at {ollama_url()}: start the Ollama app (or `ollama serve`), "
                                            "or use --replay to run without it"))
    mem = memory_gb()
    if mem is not None:
        need = 16 if not replay else 2
        rows.append(("ok" if mem >= need else "warn", "Memory", f"{mem:.0f} GB" + ("" if mem >= need else
                     f"; gpt-oss:20b needs about 16 GB free, so try --replay")))
    free = shutil.disk_usage(ROOT).free / 2**30
    rows.append(("ok" if free >= 2 else "warn", "Disk", f"{free:.0f} GB free"))
    try:
        n = asyncio.run(mcp_tools())
        rows.append(("ok" if n == 11 else "warn", "MCP servers", f"{n} tools from 5 servers over stdio"))
    except Exception as exc:  # the servers are local subprocesses; any failure here blocks every run
        rows.append(("fail", "MCP servers", f"could not start: {type(exc).__name__}: {exc}"))
    failed = any(s == "fail" for s, _, _ in rows)
    if not quiet or failed:
        heading("Checking this machine")
        table(rows)
    if not quiet and not failed:
        heading("What you can run")
        replays = [("uv run poc demo --replay", "INC-4917 end to end from recorded model answers, about 15 s"),
                   ("uv run poc run --replay", f"every experiment from the answers recorded in runs/{REFERENCE_RUN}, about 2 min")]
        hints = replays if replay else [
            ("uv run poc demo", "INC-4917 end to end, 1 to 2 min"),
            *[(f"uv run poc run --profile {n}", f"{p['what']}, about {p['minutes']} min") for n, p in PROFILES.items()],
            *replays]
        for cmd, what in hints:
            print(f"  {cmd.ljust(36)} {what}")
    return not failed


# ------------------------------------------------------------------ demo
def step(n: int, total: int, text: str) -> float:
    print(f"\n{c(f'[{n}/{total}]', 'cyan')} {text}")
    return time.perf_counter()


def done(t0: float, ok: bool = True, note: str = "") -> None:
    print(f"      {MARK['ok' if ok else 'fail']} {time.perf_counter() - t0:.1f} s{('  ' + note) if note else ''}")


def lap(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "agent_platform.channels.cli", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True)


def indent(text: str) -> str:
    return "\n".join("      " + line for line in text.strip().splitlines())


def demo(model: str, replay: bool, want_open: bool, save_recording: str | None) -> int:
    slug = model.replace(":", "_")
    recording = DEMO_RECORDINGS / f"demo-{slug}"
    if replay and not (recording / "chat.jsonl").exists():
        print(c(f"No recorded demo for {model} in {recording.relative_to(ROOT)}.", "red"))
        return 2
    d = RUNS / "demo" / time.strftime("%Y%m%d-%H%M%S")
    d.mkdir(parents=True)
    env = clean_env(LAP_PLATFORM_DB=str(d / "platform.db"), LAP_ENTERPRISE_DB=str(d / "enterprise.db"),
                    LAP_RUNS_DIR=str(d), LAP_KNOWLEDGE_INDEX=str(d / "knowledge_index.json"),
                    LAP_MODEL_REASONING=model, LAP_MODEL_SUMMARY=model,
                    LAP_MODEL_TRAFFIC=f"replay:{recording}" if replay else f"record:{d / 'traffic'}")
    total = 7
    print(c(f"INC-4917 demo · {model}{' · replayed model answers' if replay else ''} · {d.relative_to(ROOT)}", "bold"))

    t = step(1, total, "Check the machine")
    if not check(replay=replay, quiet=True, models=[model]):
        return 1
    done(t)

    t = step(2, total, "Reset the simulated enterprise systems (checkout-api v4.17 in production, incident open)")
    subprocess.run([sys.executable, "-m", "mock_enterprise", "reset"], cwd=ROOT, env=env, capture_output=True, check=True)
    done(t)

    t = step(3, total, "alice reports the incident: lap run INC-4917 --as alice")
    run = lap(["run", "INC-4917", "--as", "alice"], env)
    print(indent(run.stdout))
    wf = next((w for w in run.stdout.split() if w.startswith("wf-")), None)
    if run.returncode or not wf or "WAITING_APPROVAL" not in run.stdout:
        print(indent(run.stderr))
        done(t, False, "the workflow did not reach the approval gate")
        return 1
    done(t, note="investigated, proposed a rollback, stopped at the approval gate")

    t = step(4, total, f"bob tries to approve: lap approve {wf} --as bob")
    bob = lap(["approve", wf, "--as", "bob"], env)
    print(indent(bob.stderr or bob.stdout))
    done(t, bob.returncode != 0, "refused: bob is not an incident commander")

    t = step(5, total, f"alice approves; a new process resumes the workflow: lap approve {wf} --as alice")
    ok = lap(["approve", wf, "--as", "alice"], env)
    print(indent(ok.stdout))
    done(t, "COMPLETED" in ok.stdout)

    t = step(6, total, f"Score the run and check the systems of record: lap eval {wf}")
    ev = json.loads(lap(["eval", wf], env).stdout)
    status = subprocess.run([sys.executable, "-m", "mock_enterprise", "status"], cwd=ROOT, env=env, capture_output=True, text=True)
    world = json.loads(status.stdout)
    rows = [("ok" if x["passed"] else "fail", x["name"].replace("_", " "), x["detail"][:90]) for x in ev["checks"]]
    table(rows, pad=6)
    print(f"      backend: checkout-api on {world['checkout-api/production']}, rollbacks executed {world['rollbacks_executed']}, "
          f"incident active {world['incident_active']}")
    done(t, ev["ok"], f"{ev['passed']}/{ev['total']} checks")

    t = step(7, total, f"Write the report: lap report {wf}")
    report = d / "report.html"
    lap(["report", wf, "--out", str(report)], env)
    done(t, report.exists(), str(report.relative_to(ROOT)))

    link_latest(RUNS / "demo" / "latest", d)
    if save_recording and not replay:
        target = ROOT / save_recording
        shutil.copytree(d / "traffic", target, dirs_exist_ok=True)
        print(f"\nSaved this demo's model traffic to {target.relative_to(ROOT)}")
    good = ev["ok"] and "COMPLETED" in ok.stdout and bob.returncode != 0
    heading("Result: " + (c("PASS", "green") if good else c("FAIL", "red")))
    print(f"  report   {report.relative_to(ROOT)}   (uv run poc open demo)")
    print(f"  inside   diagnosis, tool and model calls, policy, approval, evals, events, audit log and trace")
    if replay:
        print(c("  Model answers were replayed from a recording; MCP, policy, SQLite and the workflow ran for real.", "dim"))
    open_file(report, want_open)
    return 0 if good else 1


# ------------------------------------------------------------------ run
def summarize(run_id: str) -> tuple[bool, list[tuple[str, str, str]]]:
    base = RUNS / run_id
    rows: list[tuple[str, str, str]] = []
    load = lambda p: json.loads((base / p).read_text()) if (base / p).exists() else None  # noqa: E731
    from experiments.report import stages_of

    stages, res, meta = stages_of(base), load("report/results.json") or {}, load("run.json") or {}
    bad = [s["stage"] for s in stages if not s["ok"]]
    rows.append(("ok" if stages and not bad else "fail", "Stages", f"{len(stages) - len(bad)}/{len(stages)} passed" + (f"; failed: {', '.join(bad)}" if bad else "")))
    t = res.get("tests")
    if t:
        rows.append(("ok" if not t.get("failed") else "fail", "Tests", f"{t['passed']} passed ({t['fast']} fast, {t['ollama']} with models), {t.get('failed', 0)} failed"))
    for m, w in (res.get("workflow") or {}).items():
        good = w["all_checks_passed"] == w["runs"]
        rows.append(("ok" if good else "fail", f"Platform · {m}", f"{w['completed']}/{w['runs']} completed, all 8 checks in {w['all_checks_passed']}/{w['runs']}, "
                                                                f"median {w['median_seconds_to_approval']:.0f} s to approval, {w['median_tokens']:,.0f} tokens"))
    f, mo = res.get("faults"), res.get("monolith")
    if f and mo:
        rb = f["rollback"]
        good = rb["backend_executions"] == 1 and mo["lost_response_rollbacks"] > 1
        rows.append(("ok" if good else "fail", "Lost response", f"platform {rb['backend_executions']} execution + {rb['backend_replays']} replay; monolith {mo['lost_response_rollbacks']} rollbacks"))
    cr = res.get("crash")
    if cr:
        good = cr["final_status"] == "COMPLETED" and cr["backend_rollbacks"] == 1
        rows.append(("ok" if good else "fail", "SIGKILL crashes", f"{cr['processes']} processes, {cr['final_status']}, {cr['backend_rollbacks']} rollback, replayed {str(cr['remediation_replayed']).lower()}"))
    for ch in res.get("change_scope") or []:
        ok = all(ch[s].get("applies") for s in ("monolith", "layered")) and ch["layered"].get("contracts_kept", True)
        rows.append(("ok" if ok else "fail", f"Change · {ch['id']}", f"monolith {ch['monolith']['files']} files, platform {ch['layered']['files']}"))
    if meta.get("mode") == "replay":
        rows.append(("skip", "Mode", f"replayed model traffic from {meta.get('replay_from')}; timings are not model timings"))
    return all(s != "fail" for s, _, _ in rows), rows


def run_meta(run_id: str) -> dict[str, Any]:
    path = RUNS / run_id / "run.json"
    return json.loads(path.read_text()) if path.exists() else {}


def run(profile: str, run_id: str | None, replay: str | None, resume: bool, want_open: bool, skip_check: bool) -> int:
    p = PROFILES[profile]
    rid = run_id or f"{time.strftime('%Y-%m-%d-%H%M')}-{profile}{'-replay' if replay else ''}"
    heading(f"{'Replaying' if replay else 'Running'} the experiments · profile {profile} ({p['what']}) · runs/{rid}")
    if replay:
        print(f"  model answers from runs/{replay}; no model server needed; about 2 min"
              + ("; the end-to-end model tests are skipped" if p["model_tests"] else ""))
    else:
        print(f"  about {p['minutes']} min on an idle 24 GB Apple Silicon laptop")
    if not skip_check and not check(replay=bool(replay), quiet=True, models=p["models"]):
        return 1
    cmd = [sys.executable, "-m", "experiments.run", "all", "--run-id", rid, "--models", *p["models"], "--k", str(p["k"]),
           "--profile", profile]
    if p["model_tests"]:
        cmd.append("--model-tests")
    if replay:
        cmd += ["--replay-from", replay]
    if resume:
        cmd.append("--resume")
    sys.stdout.flush()
    code = subprocess.run(cmd, cwd=ROOT, env=clean_env()).returncode
    ok, rows = summarize(rid)
    link_latest(RUNS / "latest", RUNS / rid)
    write_index()
    heading("Result: " + (c("PASS", "green") if ok and code == 0 else c("FAIL", "red")))
    table(rows)
    report = RUNS / rid / "report" / "index.html"
    print(f"\n  report   {report.relative_to(ROOT)}   (uv run poc open latest)")
    print(f"  summary  runs/{rid}/report/summary.md   ·   all runs: uv run poc runs")
    if code:
        print(f"  retry    uv run poc run --resume {rid}   (re-runs only the stages that failed)")
    open_file(report, want_open)
    return 0 if ok and code == 0 else 1


# ------------------------------------------------------------------ runs index
def run_dirs() -> list[Path]:
    return sorted((p for p in RUNS.iterdir() if p.is_dir() and not p.is_symlink()
                   and ((p / "stages.json").exists() or (p / "report" / "index.html").exists())),
                  key=lambda p: p.stat().st_mtime, reverse=True) if RUNS.exists() else []


def write_index() -> Path:
    from agent_platform.channels.html_report import chip, page, section, table as html_table

    rows = []
    for p in run_dirs():
        ok, summary = summarize(p.name)
        meta = json.loads((p / "run.json").read_text()) if (p / "run.json").exists() else {}
        mode = meta.get("mode", "live") + (f" of {meta['replay_from']}" if meta.get("replay_from") else "")
        report = p / "report" / "index.html"
        rows.append([f'<a class="nw" href="{p.name}/report/index.html">{html.escape(p.name)}</a>' if report.exists() else html.escape(p.name),
                     html.escape(time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))), html.escape(mode),
                     html.escape(meta.get("profile", "—")), chip("pass" if ok else "fail", "green" if ok else "red"),
                     "<br>".join(html.escape(f"{item}: {detail}") for _, item, detail in summary[:4])])
    demos = sorted((RUNS / "demo").glob("2*/report.html"), reverse=True) if (RUNS / "demo").exists() else []
    demo_rows = [[f'<a href="demo/{d.parent.name}/report.html">{html.escape(d.parent.name)}</a>'] for d in demos[:20]]
    body = (section("runs", "Experiment runs", "Every run on this machine", "Newest first. Open a run for its full report.",
                    html_table(["Run", "Finished", "Mode", "Profile", "Result", "Highlights"], rows))
            + section("demos", "Demos", "Demo reports", "One INC-4917 workflow each (<code>uv run poc demo</code>).",
                      html_table(["Demo"], demo_rows) if demo_rows else "<p>No demos yet.</p>"))
    out = RUNS / "index.html"
    out.write_text(page("POC runs", "Layered agent platform POC", "Runs on this machine",
                        "Generated by <code>uv run poc runs</code>.", "", body), encoding="utf-8")
    return out


def runs(want_open: bool) -> int:
    dirs = run_dirs()
    if not dirs:
        print("No runs yet. Start with: uv run poc demo   or   uv run poc run --profile quick")
        return 0
    heading("Experiment runs (newest first)")
    for p in dirs:
        ok, summary = summarize(p.name)
        meta = json.loads((p / "run.json").read_text()) if (p / "run.json").exists() else {}
        tag = meta.get("mode", "live") + (f", {meta.get('profile')}" if meta.get("profile") and meta.get("profile") != "custom" else "")
        print(f"  {MARK['ok' if ok else 'fail']} {p.name:<28} {tag:<18} {next((d for _, i, d in summary if i == 'Stages'), '')}")
    out = write_index()
    print(f"\n  index: {out.relative_to(ROOT)}   (uv run poc open index)")
    open_file(out, want_open)
    return 0


def open_report(target: str) -> int:
    if target == "index":
        path = write_index()
    elif target == "demo":
        latest = resolve_latest(RUNS / "demo" / "latest")
        path = latest / "report.html" if latest else RUNS / "demo" / "missing"
    else:
        base = resolve_latest(RUNS / "latest") if target == "latest" else RUNS / target
        path = (base / "report" / "index.html") if base else RUNS / "missing"
    if not path.exists():
        print(c(f"Nothing to open for {target!r} ({path.relative_to(ROOT)} does not exist).", "red"))
        return 1
    print(path)
    webbrowser.open(path.resolve().as_uri())
    return 0


# ------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser(prog="poc", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check", help="is this machine ready?")
    ck.add_argument("--replay", action="store_true", help="check for a replay run (no Ollama needed)")
    dm = sub.add_parser("demo", help="INC-4917 end to end, then open its report")
    dm.add_argument("--model", default="gpt-oss:20b", choices=MODELS)
    dm.add_argument("--replay", action="store_true", help="use recorded model answers; no Ollama needed")
    dm.add_argument("--no-open", action="store_true", help="do not open the report")
    dm.add_argument("--save-recording", metavar="DIR", help=argparse.SUPPRESS)
    rn = sub.add_parser("run", help="every experiment, with a report")
    rn.add_argument("--profile", choices=list(PROFILES),
                    help="quick (default), standard or full; a replay or a resume keeps the profile of its run")
    rn.add_argument("--run-id")
    rn.add_argument("--replay", nargs="?", const=REFERENCE_RUN, metavar="RUN_ID",
                    help=f"replay recorded model traffic (default: {REFERENCE_RUN}); no Ollama needed")
    rn.add_argument("--resume", nargs="?", const="latest", metavar="RUN_ID",
                    help="finish a run: skip the stages that already passed (default: the latest run)")
    rn.add_argument("--no-open", action="store_true")
    rn.add_argument("--skip-check", action="store_true", help=argparse.SUPPRESS)
    rs = sub.add_parser("runs", help="every run on this machine")
    rs.add_argument("--open", action="store_true")
    op = sub.add_parser("open", help="open a report")
    op.add_argument("target", nargs="?", default="latest", help="latest, demo, index, or a run id")
    a = ap.parse_args()
    if a.cmd == "check":
        sys.exit(0 if check(replay=a.replay) else 1)
    if a.cmd == "demo":
        sys.exit(demo(a.model, a.replay, not a.no_open, a.save_recording))
    if a.cmd == "run":
        run_id, profile, replay = a.run_id, a.profile, a.replay
        if a.resume:
            latest = resolve_latest(RUNS / "latest")
            run_id = run_id or (latest.name if a.resume == "latest" and latest else a.resume)
            if run_id == "latest" or not (RUNS / run_id).is_dir():
                ap.error(f"no run to resume: {run_id}")
            meta = run_meta(run_id)
            profile = profile or meta.get("profile")
            replay = replay or meta.get("replay_from")
        elif replay:
            profile = profile or run_meta(replay).get("profile")
        profile = profile if profile in PROFILES else "quick"
        sys.exit(run(profile, run_id, replay, bool(a.resume), not a.no_open, a.skip_check))
    if a.cmd == "runs":
        sys.exit(runs(a.open))
    sys.exit(open_report(a.target))


if __name__ == "__main__":
    main()
