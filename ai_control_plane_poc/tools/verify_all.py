"""The final publication gate for T4: verification/final_verification.{json,md}.

    make verify-all

Runs, in order: lint, the POC's tests, a rerun of every proof from source compared with the published run (replay), the
proof pack recomputed byte for byte, PROOF VERIFICATION (tools/verify_evidence.py), then checks what is built from the
run: the facts the publications print, the two editions and three evidence documents (md/html/pdf), the Medium budget
(words, figures), the figures' provenance and the Lab Console. Exit code 1 if any check fails.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "control_plane_poc"
UV = ["uv", "run", "--quiet", "--project", str(POC)]
results: list[dict] = []
# phrases the editions must not use (claim discipline; see proof/claims.toml)
BANNED = [
    (r"(?i)\bthis is a production control plane\b", "the POC is not a production control plane"),
    (r"(?i)\bindustry[- ]standard (?:ai )?control plane\b", "no industry standard exists"),
    (r"(?i)\bkubernetes is an ai control plane\b", "Kubernetes is an analogy, not an AI control plane"),
    (r"(?i)\b(?:proves|guarantees) (?:that )?(?:the )?(?:model|agent)s? (?:will )?behave", "the agents follow fixed plans"),
    (r"(?i)\bkill switch (?:is|was) instant", "P9a: a partitioned runtime kept serving reads after the suspension"),
    (r"(?i)(?<!not an )\bimmutable audit (?:log|trail|store)\b(?! .{0,40}production)", "a tamper-evident local log under POC assumptions, not an immutable store"),
]


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    return ok


def sh(cmd: list[str], cwd: Path = ROOT, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def main() -> int:
    pub = json.loads((ROOT / "evidence" / "published.json").read_text())
    run_id = pub["run_id"]

    p = sh(["uv", "run", "--quiet", "ruff", "format", "--check", "."], POC)
    q = sh(["uv", "run", "--quiet", "ruff", "check", "."], POC)
    check("lint: ruff format and ruff check", p.returncode == 0 and q.returncode == 0, (p.stdout + q.stdout).strip().splitlines()[-1] if (p.stdout + q.stdout).strip() else "")

    t = sh(["uv", "run", "--quiet", "pytest"], POC)  # pyproject's addopts: -q -rA, so every test is listed PASSED / FAILED / ERROR
    lines = t.stdout.splitlines()
    passed = sum(ln.startswith("PASSED ") for ln in lines)
    failed = sum(ln.startswith(("FAILED ", "ERROR ")) for ln in lines)
    tests = sorted({ln.split(" ", 1)[1].split("::")[0] for ln in lines if ln.startswith(("PASSED ", "FAILED ", "ERROR "))})
    check("unit and architecture tests: zero failures", t.returncode == 0 and failed == 0 and passed > 0, f"{passed} passed, {failed} failed ({len(tests)} files)")

    r = sh(["python3", "tools/verify_run.py"])
    check("replay: every proof rerun from source equals the published run", r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:])

    b = sh([*UV, "python", "tools/proof_pack.py", "build", run_id])
    check("proof pack recomputes byte for byte", b.returncode == 0, b.stdout.strip().splitlines()[-1] if b.stdout.strip() else b.stderr[-300:])

    v = sh([*UV, "python", "tools/verify_evidence.py"])
    ver = json.loads((ROOT / "evidence" / "verification" / "verification.json").read_text())
    check("PROOF VERIFICATION", v.returncode == 0 and ver["verified"], " · ".join(f"{s['section']} {s['status']}" for s in ver["sections"]))

    uses = json.loads((ROOT / "docs" / "evidence-uses.json").read_text())
    facts = json.loads((POC / "runs" / run_id / "facts.json").read_text())
    derived = ROOT / "docs" / "derived-facts.json"  # the proof pack's counts and recomputed raw-evidence facts (tools/proof_pack.py)
    facts |= json.loads(derived.read_text()) if derived.exists() else {}
    stale = [k for k, u in uses.items() if k not in facts or facts[k]["value"] != u["value"]]
    check("every fact the publications print equals the published run's", not stale, f"{len(uses)} facts" + (f"; stale: {stale[:6]}" if stale else ""))

    rep = {d["track"]: d for d in json.loads((ROOT / "docs" / "build-report.json").read_text())}
    med = rep.get("medium", {})
    check("Medium: 3,600–4,200 words of prose", 3600 <= med.get("words_prose", 0) <= 4200, f"{med.get('words_prose')} words")
    check("Medium: 9–11 figures", 9 <= med.get("figures", 0) <= 11, f"{med.get('figures')} figures")
    bad_pdf = [k for k, d in rep.items() if not d.get("pdf_ok", d.get("pages", 0) > 0)]
    check("every document built as md, html and pdf", not bad_pdf and len(rep) >= 5, f"{len(rep)} documents" + (f"; pdf problems: {bad_pdf}" if bad_pdf else ""))

    texts = {p.relative_to(ROOT).as_posix(): p.read_text() for p in [ROOT / "medium" / "ai-control-plane-medium.md", ROOT / "technical" / "ai-control-plane-technical.md"]}
    hits = [f"{n}: {why}" for n, txt in texts.items() for rx, why in BANNED if re.search(rx, txt)]
    check("claim discipline: no banned phrasing in either edition", not hits, "; ".join(hits) or f"{len(BANNED)} patterns")

    man = json.loads((ROOT / "diagrams" / "manifest.json").read_text())
    measured = [k for k, f in man["figures"].items() if f.get("data_sources")]
    missing = [k for k, f in man["figures"].items() if not all((ROOT / v).exists() for v in f["files"].values())]
    check(
        "figures: built from the published run, every file present",
        man["run"] == run_id and not missing,
        f"manifest run {man['run']} · {len(man['figures'])} figures, {len(measured)} measured" + (f"; missing files: {missing}" if missing else ""),
    )

    lab = ROOT / "results" / "lab-console.html"
    check("Lab Console built from the published run", lab.exists() and run_id in lab.read_text(), str(lab.relative_to(ROOT)))

    # series publication QA (evidence-kit 5.2.0, vendor/kit5): no local path in anything a reader receives, PDFs inflated
    sys.path.insert(0, str(ROOT / "vendor" / "kit5"))
    from evidence_kit.publication import expand, local_path_findings

    files = expand([ROOT / d for d in ("medium", "technical", "results", "evidence", "proof", "README.md", "public")] + [POC / "README.md", POC / "runs" / run_id])
    leaks = local_path_findings(files, ROOT, forbid=[ROOT.parents[2], Path.home()])
    check("no local paths in any publication artifact (md, html, pdf streams, json)", not leaks,
          f"{len(files)} files" + (f"; {[(x['file'], x['kind'], x['match']) for x in leaks[:4]]}" if leaks else ""))

    # every link to the published POC answers an anonymous reader (the repository is public)
    import urllib.error
    import urllib.request

    def status(url: str) -> int:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "t4-publication-gate"}), timeout=20) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except (urllib.error.URLError, TimeoutError):
            return 0

    texts = [(ROOT / f).read_text() for f in ("medium/ai-control-plane-medium.md", "technical/ai-control-plane-technical.md", "README.md", "public/README.md")]
    gh = sorted({u.rstrip(").,") for t in texts for u in re.findall(r"https://github\.com/ereshzealous/[^\s)\]>\"'`]+", t)})
    gh_bad = [(u, c) for u in gh if (c := status(u)) != 200]
    check("GitHub links answer an anonymous reader", bool(gh) and not gh_bad, f"{len(gh)} links" + (f"; {gh_bad}" if gh_bad else ""))

    ok = all(x["ok"] for x in results)
    out = ROOT / "verification"
    out.mkdir(exist_ok=True)
    (out / "final_verification.json").write_text(json.dumps({"run_id": run_id, "ok": ok, "passed": sum(x["ok"] for x in results), "total": len(results), "checks": results}, indent=1) + "\n")
    md = [f"# T4 · AI Control Plane · final verification of `{run_id}`", "", f"**{'VERIFIED' if ok else 'NOT VERIFIED'}** · {sum(x['ok'] for x in results)}/{len(results)} checks", "",
          "| Check | Result | Detail |", "|---|---|---|"]
    md += [f"| {x['check']} | {'PASS' if x['ok'] else 'FAIL'} | {x['detail'].replace('|', '/')} |" for x in results]
    (out / "final_verification.md").write_text("\n".join(md) + "\n")
    print(f"\n{'VERIFIED' if ok else 'NOT VERIFIED'}: {sum(x['ok'] for x in results)}/{len(results)} → verification/final_verification.md")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
