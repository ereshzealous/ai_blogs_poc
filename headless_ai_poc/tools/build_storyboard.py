"""Write storyboard/scene-specs.md and storyboard/storyboard.md.

    python3 tools/build_storyboard.py

The editorial fields (objective, key message, composition, emphasis …) are written here once.  Everything factual is
derived: export size and icons from the skeleton, figure number and placement from the article sources, provenance
and Excalidraw+ frame from diagrams/manifest.json.  Rerun after changing a figure or an article.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SK = ROOT / "diagrams" / "premium" / "skeletons"

S = {
    "f01": dict(title="Cover · Your AI shouldn't live inside the UI", obj="Communicate the whole idea before a word is read.",
                msg="One intelligence core; many detachable heads; the chat head is unplugged and still welcome.",
                comp="Title block top-left; the core centred low with eight heads on an ellipse; a live event head with its payload card top-right; a violet control-plane strip under the core.",
                actors="Intelligence core (ingress · runtime · capabilities), eight heads, control-plane strip, the monitoring event.",
                arrows="Straight connectors from each head to the core; the event connector heavier; the chat connector broken with an unplug icon.",
                emph="The live Event head (filled teal) and the detached Chat head (dashed).", mobile="Title set at 64 px so it survives a 390 px column; heads 22 px."),
    "f02": dict(title="The chat assumption", obj="Name the default architecture most teams ship without deciding it.",
                msg="We accidentally made the chat box the front door to AI.", comp="Left: five-step vertical chain. Right: an orange zone listing six things chat silently owns.",
                actors="Engineer, chat window, AI agent, tools, enterprise systems.", arrows="Top-down chain only.",
                emph="The orange 'quietly owns' zone.", mobile="Two columns; the right list reads as one column when enlarged."),
    "f03": dict(title="When the chat window disappears", obj="Show that the next callers are machines, and what questions that raises.",
                msg="The next caller of your AI is probably not a person.", comp="Six triggers left converge on one runtime card; five red questions on the right; a dashed 'no chat window' card above the runtime.",
                actors="API, event, workflow, CI/CD, scheduler, another agent; the runtime.", arrows="Elbow arrows from triggers into the runtime; dashed lines from the runtime to the questions.",
                emph="The red question cards.", mobile="Questions are short (≤ 6 words) so they stay legible when scaled."),
    "f04": dict(title="Headless, defined", obj="Give the definition as a picture and rule out the two most common misreadings.",
                msg="Headless doesn't mean no head. It means the intelligence doesn't belong to one.", comp="Nine head tiles in a row → one full-width runtime bar → three definition cards (two NOT, one IS).",
                actors="Nine heads, the headless AI runtime, the contract names.", arrows="Nine straight arrows down into the bar.",
                emph="'chat and web still exist' badge; the green IS card.", mobile="Tiles are icon-first; the definition cards carry the meaning in 21 px titles."),
    "f05": dict(title="The headless CMS analogy", obj="Borrow an understood pattern, then mark where it stops.",
                msg="Separate the intelligence from its presentation. Then govern what it can do.", comp="Two parallel rows (CMS, AI) with four channel/head cards each; an orange 'where the analogy stops' band.",
                actors="Content repository, content API, channels; intelligence runtime, runtime contract, heads.", arrows="Row-wise left to right.",
                emph="The orange limit band.", mobile="Row labels in mono caps; channel names one word."),
    "f06": dict(title="Where F3 sits in the learning map", obj="Keep series continuity explicit.",
                msg="Sprawl was the problem. Layering gave it structure. Headless makes it reusable.", comp="Four question cards F1 → F2 → F3 → Next (dashed); below, the long path as chips, done solid and planned dashed.",
                actors="F1, F2, F3, Agent Identity (planned).", arrows="Card to card.", emph="F3 card with the 'you are here' badge.", mobile="Each card's question is two short lines."),
    "f07": dict(title="Layered versus headless", obj="Separate construction from consumption, the note's central distinction.",
                msg="Headless is not a seventh layer. It is how the layers are consumed.", comp="Split view: left purple zone with F2's six layers and control planes; right teal zone with eight heads → one contract → the same platform.",
                actors="Six layers, control planes, eight heads, contract.", arrows="Layer stack arrows; contract → platform.",
                emph="The 'orthogonal' label and the two answer cards.", mobile="Two answer cards repeat the message in 19 px text."),
    "f08": dict(title="Incident, version A: chat-centric", obj="Show the human as the trigger, session and identity.",
                msg="The monitor can only page someone.", comp="Dark alert card → pager → engineer → chat → assistant → six system chips; right, five measured facts.",
                actors="Monitor, pager, engineer, chat window, chat assistant, six systems.", arrows="Vertical chain; a red arrow from the assistant into the systems.",
                emph="The hourglass 'the investigation waits here'.", mobile="Facts are 24 px headlines."),
    "f09": dict(title="Incident, version B: layered, chat-first", obj="Show that layering fixes the inside but not the door.",
                msg="Layering fixed the structure. Chat is still the front door.", comp="Left: F2-style stack with a control-plane strip; right: a red zone where an alert bot bridges into chat and three things are lost.",
                actors="Engineer, chat experience, runtime, capability layer, systems; alert, alert bot.", arrows="Stack arrows; dashed orange bridge from the bot into the chat experience.",
                emph="The three 'lost' rows (invoker, source, intent).", mobile="Loss rows use 20 px titles."),
    "f10": dict(title="Incident, version C: headless", obj="Walk the headless execution end to end.",
                msg="No one opened an AI app. A human approved the one change that mattered.", comp="Eight numbered step rows (F2 step component): card on the left, mono detail box on the right.",
                actors="Event, identity, capabilities, reasoner, ITSM, approval gate, deploy, audit.", arrows="Implied by numbering (1–8).",
                emph="Step 6 (orange gate) and step 7 (green execution).", mobile="One row per step; the mono detail box is two short lines."),
    "f11": dict(title="Many heads, one intelligence", obj="Show the measured result of eight heads during one investigation.",
                msg="Heads consume one shared execution. They don't independently rerun the investigation.", comp="Eight heads left → one investigation card, a sweep card and a release-check card; right, five green counts.",
                actors="Eight heads, one execution, sweep, release check.", arrows="Elbow arrows into the three cards; a dashed U-arrow from the investigation to the release check.",
                emph="The big green counts.", mobile="Counts at 56 px."),
    "f12": dict(title="Headless AI and MCP sprawl", obj="Reconnect to F1: more heads can mean more sprawl.",
                msg="Without a capability layer, headless multiplies the sprawl too.", comp="Split: red zone with per-head assistants wired to six MCP servers (tangle); green zone with ingress → agents → capability layer → systems.",
                actors="Heads, assistants, MCP servers; ingress, agents, capability layer.", arrows="Many thin red lines (tangle) versus a clean vertical chain.",
                emph="The two totals (48 vs 6).", mobile="Totals are one bold line under each side."),
    "f13": dict(title="The identity problem", obj="Turn 'who is acting?' into the four fields of an execution identity and a scope intersection.",
                msg="Invocation is not authorization.", comp="Three question cards over an event → agent → tool chain; four identity field cards; three scope boxes joined by ∩ and =; a dashed red line of absences.",
                actors="Event, agent, rollbackDeployment; invoker, on-behalf-of, agent, workload.", arrows="Chain arrows only.",
                emph="deploy:rollback absent from all three sets.", mobile="Scope chips are mono 14 px; enlarge for detail."),
    "f14": dict(title="The approval boundary", obj="Make autonomy a per-action policy and show approval attempts.",
                msg="Autonomy is a policy decision per action, not a property of the agent.", comp="Six-rung risk ladder left; five approval attempts with ✓/✗ right.",
                actors="Capabilities by risk; agent, invoker, responder, commander.", arrows="None.",
                emph="HIGH-RISK and DESTRUCTIVE rungs; the single green ✓.", mobile="Ladder level names in mono caps."),
    "f15": dict(title="Invisible execution", obj="Separate observability from audit.",
                msg="Observability explains behaviour. Audit proves authority.", comp="Chain row on top; two panels: span counts by kind (bars) and seven audit questions with checks.",
                actors="Event, runtime, capability, production change.", arrows="Chain arrows.",
                emph="The tamper line in the audit panel.", mobile="Bars double as a legend; counts in 18 px."),
    "f16": dict(title="Production headless AI reference architecture", obj="The one diagram to keep.",
                msg="Many heads, one runtime, governed capabilities, and a control plane that sees every execution.", comp="Five numbered bands (consumers, ingress, runtime, capability layer, systems) with chips; a violet control-plane panel on the right with ten services.",
                actors="All platform components.", arrows="Band to band; dashed lines to the control plane.",
                emph="Band numbers (build order) and the control plane.", mobile="Band names 22 px; chips 14.5 px, readable when enlarged."),
    "f17": dict(title="Headless, embedded, agentic", obj="Separate the consumption axis from the autonomy axis.",
                msg="Headless is about who can call it. Agentic is about what it does once called.", comp="2×2 grid with axis labels; four quadrant cards; a note that RAG/MCP are implementation choices.",
                actors="Headless inference, headless agent runtime, embedded AI, chat agent.", arrows="Axes only.",
                emph="Headless quadrants solid; UI-coupled dashed.", mobile="Quadrant titles 22 px."),
    "f18": dict(title="Design principles", obj="Summarize the rules and tie each to evidence.",
                msg="Headless AI removes the UI as the boundary of intelligence.", comp="Ten numbered rows with icon tiles and experiment badges.",
                actors="—", arrows="None.", emph="Experiment badges.", mobile="Each rule ≤ 8 words in 21 px."),
    "f19": dict(title="From application to platform", obj="Show the shift from app to infrastructure.",
                msg="We moved from building AI applications to designing AI infrastructure.", comp="Three stage cards with five attribute rows each.",
                actors="AI assistant, AI runtime, intelligence platform.", arrows="Stage to stage.", emph="The third card (thicker teal).", mobile="Values 20 px."),
    "f20": dict(title="What comes next", obj="Hand off to Agent Identity.",
                msg="Once intelligence runs without a chat window, identity becomes architecture.", comp="Six-card chain (F3 solid, the rest dashed/planned) over a big question card.",
                actors="Headless AI, Agent identity, Authorization, Policy, HITL, Control plane.", arrows="Card to card.",
                emph="The question card.", mobile="Question at 32 px."),
    "f21": dict(title="The execution lifecycle (Blog B)", obj="Show durable execution states and the three durability behaviours.",
                msg="Executions end when their state says so, not when a tab closes.", comp="State nodes with elbow transitions; three measured notes below.",
                actors="Seven execution states.", arrows="State transitions.", emph="WAITING_APPROVAL (orange).", mobile="State names 20 px mono."),
    "f22": dict(title="Event delivery semantics (Blog B)", obj="Show dedupe, join and dead-letter rules with measured outcomes.",
                msg="Duplicates are normal. Duplicate side effects are a design choice.", comp="Three inputs → three ingress rules → a green systems-of-record panel; an id glossary box.",
                actors="Deliveries, ingress rules, systems of record.", arrows="Input to rule.", emph="Green counts.", mobile="Rule names mono 18 px."),
}


def placements() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for track, srcs in (("medium", [ROOT / "docs/source/medium.src.md"]), ("technical", sorted((ROOT / "docs/source/technical").glob("*.md")))):
        n, section = 0, ""
        for src in srcs:
            for line in src.read_text().splitlines():
                if line.startswith("## "):
                    section = line[3:].strip()
                m = re.match(r"^::: figure (f\d+)", line)
                if m:
                    n += 1
                    out.setdefault(m.group(1), {})[track] = f"Figure {n}, section “{section}”"
            fm = re.search(r"^cover: (f\d+)", srcs[0].read_text(), re.M)
            if fm:
                out.setdefault(fm.group(1), {})[track] = "Cover (hero)"
    return out


def main() -> None:
    man = json.loads((ROOT / "diagrams/manifest.json").read_text())["figures"]
    pl = placements()
    lines = ["# Scene specifications · F3 Headless AI", "",
             "Generated by `tools/build_storyboard.py`. Editorial fields are written in that script; size, icons, placement, provenance and",
             "the Excalidraw+ frame are derived from the skeletons, the article sources and `diagrams/manifest.json`.", "",
             "**Shared conventions** (see `diagrams/VISUAL-LANGUAGE.md`): 1600 px frames, content x = 64–1536, a white card with a `#E3E8EF` border,",
             "a mono kicker with a rule, a mono title on a highlight bar, a Lilita subtitle, tinted zones, icon-tile cards, a closing banner. Exports:",
             "`.excalidraw`, SVG (used inline in HTML and PDF) and PNG @2x (used by the Markdown editions). Icons are Lucide from the shared",
             "*Architecture Icons* collection, placed only where they carry meaning, never parked beside a frame.", ""]
    for fid in sorted(S):
        sk = json.loads((SK / f"{fid}.json").read_text())
        s = S[fid]
        icons = sorted({k.split("--")[0] for k in sk["icons"]})
        texts = [e["text"] for e in sk["elements"] if e["type"] == "text"]
        labels = sorted({e["label"]["text"] for e in sk["elements"] if e.get("label")})
        m = man.get(fid, {})
        ex = m.get("excalidraw") or {}
        lines += [f"## Scene {fid[1:]} · {s['title']}", "",
                  f"| Field | Specification |", "|---|---|",
                  f"| Educational objective | {s['obj']} |", f"| Key message (banner) | {s['msg']} |",
                  f"| Composition and layout | {s['comp']} |", f"| Actors / components | {s['actors']} |",
                  f"| Arrows / relationships | {s['arrows']} |",
                  f"| Labels | {len(texts)} free texts, {len(labels)} shape labels; title “{texts[1] if len(texts) > 1 else ''}” |",
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
    sb = ["# Storyboard · F3 Headless AI", "", "The visual story in reading order. Each scene is one Excalidraw frame and one figure.", "",
          "| # | Scene | Beat | Key message | Blog A | Blog B |", "|---|---|---|---|---|---|"]
    beats = {"f01": "Hook", "f02": "Problem", "f03": "Problem", "f04": "Definition", "f05": "Analogy", "f06": "Series", "f07": "Distinction",
             "f08": "POC A", "f09": "POC B", "f10": "POC C", "f11": "Result", "f12": "F1 again", "f13": "Identity", "f14": "Approval",
             "f15": "Evidence", "f16": "Reference", "f17": "Distinction", "f18": "Principles", "f19": "Shift", "f20": "Next",
             "f21": "Deep dive", "f22": "Deep dive"}
    for fid in sorted(S):
        p = pl.get(fid, {})
        sb.append(f"| {fid[1:]} | {S[fid]['title']} | {beats[fid]} | {S[fid]['msg']} | {'✓' if 'medium' in p else '–'} | {'✓' if 'technical' in p else '–'} |")
    sb += ["", "Scanning only the figures of Blog A in order tells the story: the chat assumption (02) → callers change (03) → definition (04)",
           "→ analogy (05) → from app to platform (19) → series (06) → layered vs headless (07) → the incident three ways (08–10) → many heads,",
           "one intelligence (11) → identity (13) → approval (14) → audit (15) → sprawl (12) → headless vs agentic (17) → principles (18) → next (20).", ""]
    (ROOT / "storyboard" / "storyboard.md").write_text("\n".join(sb))
    print("wrote storyboard/scene-specs.md and storyboard/storyboard.md")


if __name__ == "__main__":
    main()
