"""acp: the T4 command line.

acp demo                          P2 only: one central change, same agent, same process, different behaviour
acp proof [P1 P2 ...]             run the proofs into a scratch run and print their proof cards
acp experiments [--run-id ID]     every proof -> runs/<ID>/ (the published run: facts, checks, proof.txt, scenarios)
acp bundle [VERSION]              print the seed desired state as the control plane would publish it (v1)
acp live [--backend B] [L1 ...]   the live proofs: a self-hosted LLM plans the agent's steps (B = ollama, needs Ollama
                                  with qwen3:8b; or scripted, no model at all) -> runs/live/<id>/
"""

from __future__ import annotations

import argparse
import json
import shutil


def main() -> None:
    ap = argparse.ArgumentParser(prog="acp")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    p = sub.add_parser("proof")
    p.add_argument("only", nargs="*")
    e = sub.add_parser("experiments")
    e.add_argument("--run-id", default="2026-09-30-recorded")
    sub.add_parser("bundle")
    lv = sub.add_parser("live")
    lv.add_argument("--backend", default="ollama", choices=["ollama", "scripted"])
    lv.add_argument("--run-id", default=None)
    lv.add_argument("only", nargs="*")
    a = ap.parse_args()
    if a.cmd == "live":
        from acp.live.backends import LiveBackendError
        from acp.live.proofs import run_live

        try:
            out = run_live(a.backend, a.run_id, [x.upper() for x in a.only] or None)
        except LiveBackendError as e:
            raise SystemExit(
                f"acp live: {e}\n"
                "  local model:  ollama serve  and  ollama pull qwen3:8b,  then  uv run acp live\n"
                "  no model:     uv run acp live --backend scripted   (a scripted stand-in model; exercises every code path)"
            ) from None
        print((out / "proof.txt").read_text())
        print((out / "summary.md").read_text())
        print(f"live run: {out}")
        return
    from acp.experiments import run

    if a.cmd == "experiments":
        out = run(a.run_id)
        print((out / "summary.md").read_text())
        print(f"proof cards: {out / 'proof.txt'}")
    elif a.cmd in ("demo", "proof"):
        only = ["P2"] if a.cmd == "demo" else [x.upper() for x in a.only] or None
        out = run("_scratch", only)
        print((out / "proof.txt").read_text())
        shutil.rmtree(out)
    elif a.cmd == "bundle":
        import tempfile
        from pathlib import Path

        from acp.controlplane import ControlPlane

        d = Path(tempfile.mkdtemp())
        cp = ControlPlane(d)
        v = cp.bootstrap(0)
        print(json.dumps(cp.bundle(v), indent=1))
        shutil.rmtree(d)


if __name__ == "__main__":
    main()
