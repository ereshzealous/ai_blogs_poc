"""Write storyboard/scene-specs.md (T3) and storyboard/storyboard.md.

    python3 tools/build_storyboard.py

The editorial fields (objective, key message, composition, emphasis …) are written here once.  Everything factual is
derived: export size and icons from the skeleton, figure number and placement from the article sources, provenance
and Excalidraw+ frame from diagrams/manifest.json.  Rerun after changing a figure or an article.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SK = ROOT / "diagrams" / "premium" / "skeletons"
sys.path.insert(0, str(ROOT / "diagrams" / "tools"))
from figures_order import ORDER  # noqa: E402  (semantic ids in reading order)

S = {
    "cover": dict(beat="Hook", msg="Human approval only matters if the system can prove what was approved.",
                  obj="State the thesis as a picture: a stamped APPROVED that no longer matches the action the agent now asks for.",
                  comp="Left: the headline APPROVED · BUT APPROVED · WHAT? and the thesis line. Right: the reviewed action card with its digest, "
                       "the APPROVED stamp, and below it the action at 14:46 with a different digest and DIGEST MISMATCH.",
                  actors="The reviewed action (14:09), the action the agent asks for (14:46).", arrows="None; the two digests carry the contrast.",
                  emph="The two digests and the mismatch badge.", mobile="Headline 120 px; digests 26 px."),
    "incident-37-minutes": dict(beat="Problem", obj="Replay the recorded 37 minutes of scenario H5c and what each protocol did with them.",
                  comp="A timeline 14:09 → 14:46 on the left; three arm outcomes on the right.", actors="Agent, approver alice, dana (hotfix), the three arms.",
                  arrows="Timeline order only.", emph="The 37-minute gap and the single REJECTED under arm C.", mobile="Times 26 px; outcomes 22 px."),
    "button-not-control": dict(beat="Anti-pattern", obj="Show why approved = true is not a control.",
                  comp="Left: the Slack card arm A posted. Right: the questions a reviewer would ask that the boolean cannot answer.",
                  actors="Chat message, approver, unanswered questions.", arrows="Card to the missing answers.", emph="The bare Approve button.",
                  mobile="Questions 20 px."),
    "authz-approval-execution": dict(beat="Distinction", obj="Separate the three decisions: may it happen, should we proceed, does it still hold.",
                  comp="A ladder of seven boundaries grouped under three questions.", actors="Authentication, identity, delegation, policy, approval, revalidation, execution gate.",
                  arrows="Top to bottom along the ladder.", emph="The three question brackets.", mobile="Boundary names 20 px."),
    "state-machine": dict(beat="Lifecycle", obj="Show the states the POC enforces and the transitions it refuses.",
                  comp="States left to right from PENDING to EXECUTED, terminal states boxed, refused transitions dashed.",
                  actors="Approval request states (hitl/approvals.py).", arrows="Legal transitions solid, refused transitions dashed red.",
                  emph="REVALIDATING, where the approval is consumed.", mobile="State names 20 px."),
    "bound-approval": dict(beat="Object", obj="Show the approval artifact field by field and the question each field answers.",
                  comp="The recorded artifact of H9a on the left; six coloured field groups on the right.", actors="The artifact fields.",
                  arrows="None; colour links fields to their group.", emph="The action group and its digest.", mobile="Field rows 16 px mono."),
    "production-architecture": dict(beat="Reference", obj="The one diagram to keep: HITL as a control protocol in production.",
                  comp="Agent and policy on the top row, the approval orchestrator on the right, decision and revalidation rows below, an audit strip.",
                  actors="Agent, policy, orchestrator (request store, channel adapter, artifact), human, durable pause, revalidation, consume, gate, credential, side effect.",
                  arrows="Left to right per row; elbow arrows between rows.", emph="The orchestrator box and the revalidate → consume → gate row.",
                  mobile="Card titles 19 px."),
    "poc-testbed": dict(beat="Method", obj="Show what the POC held constant and what it varied.",
                  comp="Fixture and action feed the approval-model switch (A, B, C); shared components below; held-constant list on the right.",
                  actors="Incident fixture, approval models A/B/C, orchestrator, request store, Slack sim, audit, gate, Kubernetes sim, recorder.",
                  arrows="Top to bottom through the switch.", emph="The switch and the CHANGED box.", mobile="Counts 40 px."),
    "exp-mutation": dict(beat="Binding", obj="Show H1 and H2: an approved action changed before execution.",
                  comp="The approved action, the mutated asks, then one column per arm with its outcome and count.", actors="Approver, agent, arms A/B/C.",
                  arrows="Approved → mutated.", emph="4 vs 0 vs 0.", mobile="Counts 96 px."),
    "exp-replay": dict(beat="Single use", obj="Show H3: one approval presented four times.",
                  comp="One approval fans out to four uses; one row per use with the outcome under each arm.", actors="Approval, workflows, arms A/B/C.",
                  arrows="Approval to each use.", emph="3 replays under A, 0 under B and C.", mobile="Outcome chips 14 px mono."),
    "exp-eligibility": dict(beat="Who decides", obj="Show H4: would-be approvers and what each design accepted.",
                  comp="Five rows (guest, readonly, agent, author, two-person) against arm A and arms B/C.", actors="Guest, reggie, the agent, dana, alice and omar.",
                  arrows="None; rows read left to right.", emph="4 accepted under A, 0 under B and C.", mobile="Row titles 19 px."),
    "exp-stale": dict(beat="Staleness", obj="Show H5 and H6: approvals still inside their expiry, and wrong anyway.",
                  comp="The 14:09 → 14:46 timeline on the left; seven world changes with the B and C outcome on the right.",
                  actors="Approver, the changed world (hotfix, manual rollback, revoked delegation, disabled agent, policy v8, lost role).",
                  arrows="Down the timeline.", emph="7 vs 7 vs 0.", mobile="Outcome chips 15 px mono."),
    "exp-duplicate": dict(beat="Exactly once", obj="Show H7: four ways one approval tries to run twice.",
                  comp="A click fanning out to two callbacks that meet at one key; the writes per arm on the right.", actors="Callbacks, workers, arms A/B/C.",
                  arrows="Fan-out and fan-in to the idempotency key.", emph="4 vs 2 vs 0, and why B's two were absorbed.", mobile="Counts 72 px."),
    "decision-card": dict(beat="Human factors", obj="Contrast the bare button with the evidence card the approver saw in arms B and C.",
                  comp="Arm A's message on the left; the recorded card with every field on the right.", actors="Approver, the two messages.",
                  arrows="None.", emph="The digest line and APPROVE EXACT ACTION.", mobile="Card values 18 px."),
    "audit-reconstruction": dict(beat="Audit", obj="Show H9: sixteen review questions against each design's records.",
                  comp="A sixteen-row table with a check or a cross per arm, totals at the bottom.", actors="Arms A/B/C and their records.",
                  arrows="None.", emph="10/16, 15/16, 16/16.", mobile="Questions 19 px."),
    "findings": dict(beat="Results", obj="Separate what the run supports outright from what holds only within a bound.",
                  comp="Two columns of cards: supported on the left, qualified on the right; a not-tested line below.", actors="Findings of the run.",
                  arrows="None.", emph="The qualified column.", mobile="Card titles 19–20 px."),
    "production-rules": dict(beat="Principles", obj="Ten rules for an approval-gated action, each tied to the scenario that tested it.",
                  comp="Ten numbered cards in two columns, each with its scenario badge.", actors="—", arrows="None.",
                  emph="The numbers and the scenario badges.", mobile="Rule text 21 px."),
    "next-control-plane": dict(beat="Next", obj="Hand off to the AI Control Plane.",
                  comp="A ladder of four questions (Agent Identity, Authorization & Policy, HITL, AI Control Plane); the controls every team needs on the right.",
                  actors="The four series notes.", arrows="Top to bottom.", emph="This note's card and the dashed next card.", mobile="Questions 22–25 px."),
    "tech-poc-architecture": dict(beat="Testbed", obj="Show the modules of hitl_poc, what each owns and the evidence it writes.",
                  comp="Fixtures, platform and the variable in three columns; simulated systems and evidence below.", actors="The hitl_poc modules.",
                  arrows="Fixtures → platform → variable → evidence.", emph="THE VARIABLE column.", mobile="Module names 16 px mono."),
    "tech-scorecard": dict(beat="Scorecard", obj="Give the headline metric of every experiment per arm, with its checks.",
                  comp="Nine rows H1–H9 with the A/B/C value and the check tally; a totals row.", actors="Experiments H1–H9, arms A/B/C.",
                  arrows="None.", emph="The C column and the all-scenario totals.", mobile="Values 22 px."),
    "tech-trace": dict(beat="Trace", obj="Walk one recorded request end to end, with the nine revalidation checks.",
                  comp="The event timeline on the left; the revalidation checklist and the outcomes on the right.", actors="Event, policy, request, world changes, approver, worker b.",
                  arrows="Down the timeline.", emph="The two failed checks and REJECTED.", mobile="Event titles 18 px."),
    "tech-failure-modes": dict(beat="Failure modes", obj="List sixteen failure modes with prevent, detect, recover and the POC scenario that tested each.",
                  comp="A five-column matrix, striped rows, untested cells in orange.", actors="—", arrows="None.",
                  emph="The POC column.", mobile="Cells 15.5 px."),
}


def placements() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for track, srcs in (("medium", [ROOT / "docs/source/medium.src.md"]), ("technical", sorted((ROOT / "docs/source/technical").glob("*.md")))):
        n, section = 0, ""
        for src in srcs:
            for line in src.read_text().splitlines():
                if line.startswith("## "):
                    section = line[3:].strip()
                m = re.match(r"^::: figure ([a-z0-9-]+)", line)
                if m:
                    n += 1
                    out.setdefault(m.group(1), {})[track] = f"Figure {n}, section “{section}”"
            fm = re.search(r"^cover: ([a-z0-9-]+)", srcs[0].read_text(), re.M)
            if fm:
                out.setdefault(fm.group(1), {})[track] = "Cover (hero)"
    return out


def main() -> None:
    man = json.loads((ROOT / "diagrams/manifest.json").read_text())["figures"]
    pl = placements()
    lines = ["# Scene specifications · T3 Human-in-the-Loop", "",
             "Generated by `tools/build_storyboard.py`. Editorial fields are written in that script; size, icons, placement, provenance and",
             "the Excalidraw+ frame are derived from the skeletons, the article sources and `diagrams/manifest.json`.", "",
             "**Shared conventions** (see `diagrams/VISUAL-LANGUAGE.md`): 1600 px frames, content x = 64–1536, a white card with a `#E3E8EF` border,",
             "a mono kicker with a rule, a mono title on a highlight bar, a Lilita subtitle, tinted zones, icon-tile cards, a closing banner. Exports:",
             "`.excalidraw`, SVG (used inline in HTML and PDF) and PNG @2x (used by the Markdown editions). Icons are Lucide from the shared",
             "*Architecture Icons* collection, placed only where they carry meaning, never parked beside a frame.", ""]
    assert sorted(S) == sorted(ORDER), "every figure needs editorial fields"
    for n, fid in enumerate(ORDER):
        sk = json.loads((SK / f"{fid}.json").read_text())
        s = S[fid]
        icons = sorted({k.split("--")[0] for k in sk["icons"]})
        texts = [e["text"] for e in sk["elements"] if e["type"] == "text" and e["text"]]
        labels = [e["label"]["text"] for e in sk["elements"] if e.get("label")]
        s.setdefault("msg", labels[-1] if labels else "")
        m = man.get(fid, {})
        ex = m.get("excalidraw") or {}
        lines += [f"## Scene {n:02d} · {sk['name']} (`{fid}`)", "",
                  f"| Field | Specification |", "|---|---|",
                  f"| Educational objective | {s['obj']} |", f"| Key message (banner) | {s['msg']} |",
                  f"| Composition and layout | {s['comp']} |", f"| Actors / components | {s['actors']} |",
                  f"| Arrows / relationships | {s['arrows']} |",
                  f"| Labels | {len(texts)} free texts, {len(set(labels))} shape labels; title “{texts[1] if len(texts) > 1 else ''}” |",
                  f"| Annotations | kicker “{texts[0] if texts else ''}”; provenance line where the figure carries measured values |",
                  f"| Icon references (Lucide, Architecture Icons) | {', '.join(icons) or '—'} |",
                  f"| Emphasis / visual hierarchy | {s['emph']} Kicker → title → subtitle → body → banner. |",
                  f"| Blog A (Medium) | {pl.get(fid, {}).get('medium', 'not used')} |",
                  f"| Blog B (technical) | {pl.get(fid, {}).get('technical', 'not used')} |",
                  f"| Mobile readability | {s['mobile']} On phones the HTML scrolls the figure sideways at ≥ 720 px and opens it full-screen on tap. |",
                  f"| Export | {sk['width']} × {sk['height']} px (aspect {sk['width'] / sk['height']:.2f}); PNG @2x {sk['width'] * 2} × {sk['height'] * 2} |",
                  f"| Provenance | {m.get('provenance', '')} |",
                  f"| Excalidraw+ frame | {('scene ' + ex['scene_id'] + ', frame ' + ex['frame_id']) if ex else 'pending push'} |", ""]
    (ROOT / "storyboard" / "scene-specs.md").write_text("\n".join(lines))
    sb = ["# Storyboard · T3 Human-in-the-Loop", "", "The visual story in reading order. Each scene is one Excalidraw frame and one figure.", "",
          "| # | Scene | Beat | Key message | Blog A | Blog B |", "|---|---|---|---|---|---|"]
    for n, fid in enumerate(ORDER):
        p = pl.get(fid, {})
        name = json.loads((SK / f"{fid}.json").read_text())["name"]
        sb.append(f"| {n:02d} | {name} (`{fid}`) | {S[fid]['beat']} | {S[fid]['msg']} | {'✓' if 'medium' in p else '–'} | {'✓' if 'technical' in p else '–'} |")
    (ROOT / "storyboard" / "storyboard.md").write_text("\n".join(sb))
    print("wrote storyboard/scene-specs.md and storyboard/storyboard.md")


if __name__ == "__main__":
    main()
