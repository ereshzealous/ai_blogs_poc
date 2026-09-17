"""`poc`: the POC's front door. One command per thing a reader wants to do.

    uv run poc check                         is this machine ready? (Ollama, models, memory, MCP servers)
    uv run poc demo [--replay]               INC-4917 end to end in about a minute, then open its report
    uv run poc plans                         the run plans in plans/: what each tests
    uv run poc plan show <plan>              what a plan runs, which faults and kills it injects, what counts as a pass
    uv run poc run --plan <plan>             run a plan: quick, standard, full, replay, chaos, or your own YAML file
        --models M [M ...]  --runs N  --only a,b  --skip a,b  --set key=value  --replay [RUN]  --run-id ID  --resume [ID]
    uv run poc runs                          every run on this machine, with its result and report
    uv run poc open [latest|demo|index|<run-id>]

A plan (experiments/plan.py) is a YAML file: models, runs per scenario, where model answers come from, which
experiments run, the faults to inject, where to SIGKILL, and the expectations that decide pass or fail. The exit code
is 0 only when every expectation holds, so `poc run` works unchanged in CI.

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
PROFILES = ("quick", "standard", "full")  # plan names kept from the first version of `poc run --profile`
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
        from experiments import plan as plans

        replays = [("uv run poc demo --replay", "INC-4917 end to end from recorded model answers, about 15 s"),
                   ("uv run poc run --plan replay", f"every experiment from the answers recorded in runs/{REFERENCE_RUN}, about 3 min")]
        hints = replays if replay else [
            ("uv run poc demo", "INC-4917 end to end, 1 to 2 min"),
            *[(f"uv run poc run --plan {n}", f"{pl['description']} About {pl['minutes']} min.")
              for n, pl in ((n, plans.load(n)) for n in plans.available()) if pl["model_answers"]["mode"] == "live"],
            *replays,
            ("uv run poc plan show <plan>", "what a plan tests, before you run it")]
        for cmd, what in hints:
            print(f"  {cmd.ljust(32)} {what}")
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
    """Stage results, then each expectation of the run's plan with what was measured."""
    from experiments import plan as plans
    from experiments.report import stages_of

    base = RUNS / run_id
    stages, meta = stages_of(base), run_meta(run_id)
    bad = [x["stage"] for x in stages if not x["ok"]]
    rows = [("ok" if stages and not bad else "fail", "Stages", f"{len(stages) - len(bad)}/{len(stages)} passed" + (f"; failed: {', '.join(bad)}" if bad else ""))]
    plan = plans.for_run(base, meta.get("profile"))
    rows += plans.evaluate(base, plan)
    if meta.get("mode") == "replay":
        rows.append(("skip", "Mode", f"replayed model traffic from {meta.get('replay_from')}; timings are not model timings"))
    return all(st != "fail" for st, _, _ in rows), rows


def run_meta(run_id: str) -> dict[str, Any]:
    path = RUNS / run_id / "run.json"
    return json.loads(path.read_text()) if path.exists() else {}


def run(plan: dict[str, Any], run_id: str | None, resume: bool, want_open: bool, skip_check: bool) -> int:
    from experiments import plan as plans

    replay = plan["model_answers"]["replay_from"] if plan["model_answers"]["mode"] == "replay" else None
    rid = run_id or f"{time.strftime('%Y-%m-%d-%H%M')}-{plan['name']}"
    base = RUNS / rid
    heading(f"{'Replaying' if replay else 'Running'} plan {plan['name']} · runs/{rid}")
    for line in plans.describe(plan)[1:]:
        print(f"  {line}" if line else "")
    if not skip_check and not check(replay=bool(replay), quiet=True, models=plan["models"]):
        return 1
    base.mkdir(parents=True, exist_ok=True)
    (base / "plan.yaml").write_text(plans.dump(plan))
    cmd = [sys.executable, "-m", "experiments.run", "all", "--run-id", rid, "--plan", str((base / "plan.yaml").relative_to(ROOT))]
    if resume:
        cmd.append("--resume")
    sys.stdout.flush()
    code = subprocess.run(cmd, cwd=ROOT, env=clean_env()).returncode
    ok, rows = summarize(rid)
    link_latest(RUNS / "latest", base)
    write_index()
    heading("Result: " + (c("PASS", "green") if ok and code == 0 else c("FAIL", "red")))
    table(rows)
    report = base / "report" / "index.html"
    print(f"\n  report   {report.relative_to(ROOT)}   (uv run poc open latest)")
    print(f"  plan     runs/{rid}/plan.yaml   ·   all runs: uv run poc runs")
    if code or not ok:
        print(f"  retry    uv run poc run --resume {rid}   (re-runs only the stages that failed)")
    open_file(report, want_open)
    return 0 if ok and code == 0 else 1


def plan_of(run_id: str) -> str:
    """The plan a run used: its saved plan.yaml, else the built-in plan its profile names, else full."""
    from experiments import plan as plans

    saved = RUNS / run_id / "plan.yaml"
    if saved.exists():
        return str(saved)
    profile = run_meta(run_id).get("profile")
    return profile if profile in plans.available() else "full"


def show_plans() -> int:
    from experiments import plan as plans

    heading("Run plans (plans/*.yaml)")
    for name in plans.available():
        pl = plans.load(name)
        mode = "replay" if pl["model_answers"]["mode"] == "replay" else "live"
        print(f"  {name:<10} {mode:<7} {len(pl['experiments'])} experiments · {', '.join(pl['models'])} · {pl['runs']} run(s) · about {pl['minutes']} min")
        print(f"  {'':<10} {pl['description']}")
    print("\n  details: uv run poc plan show <plan>     run: uv run poc run --plan <plan>")
    print("  your own: copy plans/full.yaml, keep the keys you change, and pass the file to --plan")
    return 0


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
    rn = sub.add_parser("run", help="run a plan: every experiment it lists, with a report")
    rn.add_argument("--plan", help="a plan name (poc plans) or a YAML file; default quick, or the plan of the run being resumed or replayed")
    rn.add_argument("--profile", choices=PROFILES, help=argparse.SUPPRESS)  # older spelling of --plan
    rn.add_argument("--models", nargs="+", metavar="MODEL", help="override the plan's models")
    rn.add_argument("--runs", type=int, metavar="N", help="override the runs per scenario")
    rn.add_argument("--only", metavar="A,B", help="run only these experiments (tests, faults, crash, monolith, workflow, change, export)")
    rn.add_argument("--skip", metavar="A,B", help="leave these experiments out")
    rn.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="override any plan key, e.g. --set tests.model_tests=false --set 'crash.kill_at=[after_step:investigate]'")
    rn.add_argument("--run-id")
    rn.add_argument("--replay", nargs="?", const=REFERENCE_RUN, metavar="RUN_ID",
                    help=f"answer model calls from a recorded run (default: {REFERENCE_RUN}); no Ollama needed")
    rn.add_argument("--resume", nargs="?", const="latest", metavar="RUN_ID",
                    help="finish a run with its saved plan: skip the stages that already passed (default: the latest run)")
    rn.add_argument("--no-open", action="store_true")
    rn.add_argument("--skip-check", action="store_true", help=argparse.SUPPRESS)
    pl = sub.add_parser("plans", help="list the run plans")
    ps = sub.add_parser("plan", help="explain a plan")
    ps.add_argument("action", choices=["show"])
    ps.add_argument("target", help="a plan name or YAML file")
    ps.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="show the plan with these overrides")
    rs = sub.add_parser("runs", help="every run on this machine")
    rs.add_argument("--open", action="store_true")
    op = sub.add_parser("open", help="open a report")
    op.add_argument("target", nargs="?", default="latest", help="latest, demo, index, or a run id")
    a = ap.parse_args()
    if a.cmd == "check":
        sys.exit(0 if check(replay=a.replay) else 1)
    if a.cmd == "demo":
        sys.exit(demo(a.model, a.replay, not a.no_open, a.save_recording))
    if a.cmd == "plans":
        sys.exit(show_plans())
    if a.cmd == "plan":
        from experiments import plan as plans

        try:
            over: dict[str, Any] = {}
            for kv in a.set:
                plans.set_value(over, kv)
            pl_ = plans.load(a.target, over)
        except plans.PlanError as exc:
            sys.exit(c(str(exc), "red"))
        print("\n".join(plans.describe(pl_, str(plans.resolve_path(a.target).relative_to(ROOT)))))
        sys.exit(0)
    if a.cmd == "run":
        from experiments import plan as plans

        run_id, source, over = a.run_id, a.plan or a.profile, {}
        try:
            if a.resume:
                latest = resolve_latest(RUNS / "latest")
                run_id = run_id or (latest.name if a.resume == "latest" and latest else a.resume)
                if run_id == "latest" or not (RUNS / run_id).is_dir():
                    ap.error(f"no run to resume: {run_id}")
                source = source or plan_of(run_id)
            elif a.replay and not source:
                source = plan_of(a.replay)
            if a.replay:
                over["model_answers"] = {"mode": "replay", "replay_from": a.replay}
            if a.models:
                over["models"] = a.models
            if a.runs:
                over["runs"] = a.runs
            base_plan = plans.load(source or "quick")
            exps = list(base_plan["experiments"])
            if a.only:
                exps = [e for e in plans.EXPERIMENTS if e in {x.strip() for x in a.only.split(",")}]
                unknown = {x.strip() for x in a.only.split(",")} - set(plans.EXPERIMENTS)
                if unknown:
                    ap.error(f"--only: unknown {sorted(unknown)}")
            if a.skip:
                exps = [e for e in exps if e not in {x.strip() for x in a.skip.split(",")}]
            if exps != base_plan["experiments"]:
                over["experiments"] = exps
            for kv in a.set:
                plans.set_value(over, kv)
            resolved = plans.load(source or "quick", over)
        except plans.PlanError as exc:
            sys.exit(c(str(exc), "red"))
        sys.exit(run(resolved, run_id, bool(a.resume), not a.no_open, a.skip_check))
    if a.cmd == "runs":
        sys.exit(runs(a.open))
    sys.exit(open_report(a.target))


if __name__ == "__main__":
    main()
