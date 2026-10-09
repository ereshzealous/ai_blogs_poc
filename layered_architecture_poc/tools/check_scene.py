"""Check an Excalidraw+ scene snapshot (the JSON from get_scene_content) and record the result.

    python3 tools/check_scene.py <scene-content.json>      -> diagrams/scene_check.json

Checks: one frame per figure in diagrams/scenes.json, frames at x=0, no element outside a frame (so no loose icon
palette), every image's file present, no free text left on autoResize (the live editor clips those), and no icon
drawn underneath a filled shape of its own frame.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    scene = json.loads(Path(sys.argv[1]).read_text())
    files = scene["files"]
    els = [e for e in scene["elements"] if not e.get("isDeleted")]
    frames = {e["id"]: e for e in els if e["type"] == "frame"}
    want = json.loads((ROOT / "diagrams" / "scenes.json").read_text())
    texts = [e for e in els if e["type"] == "text" and not e.get("containerId")]
    images = [e for e in els if e["type"] == "image"]

    def hidden(im):
        cx, cy = im["x"] + im["width"] / 2, im["y"] + im["height"] / 2
        return any(r["type"] == "rectangle" and r.get("frameId") == im.get("frameId") and r["index"] > im["index"]
                   and r.get("backgroundColor") not in ("transparent", None)
                   and r["x"] <= cx <= r["x"] + r["width"] and r["y"] <= cy <= r["y"] + r["height"] for r in els)

    checks = [
        ("one frame per figure", sorted(v["frame_id"] for v in want.values()) == sorted(frames), f"{len(frames)} frames, {len(want)} figures"),
        ("frames at x=0", all(f["x"] == 0 for f in frames.values()), ""),
        ("no element outside a frame", not [e for e in els if e["type"] != "frame" and not e.get("frameId")], ""),
        ("every image file present", not [e for e in scene["elements"] if e["type"] == "image" and e.get("fileId") not in files], f"{len(images)} images"),
        ("no free text on autoResize", not [t for t in texts if t.get("autoResize", True)], f"{len(texts)} free texts"),
        ("no icon hidden under a filled shape", not [i for i in images if hidden(i)], ""),
    ]
    out = {"checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "scene_version": scene.get("sceneVersion"),
           "elements": len(els), "ok": all(c[1] for c in checks),
           "checks": [{"check": c, "ok": ok, "detail": d} for c, ok, d in checks]}
    (ROOT / "diagrams" / "scene_check.json").write_text(json.dumps(out, indent=1))
    for c in out["checks"]:
        print("PASS" if c["ok"] else "FAIL", c["check"], c["detail"])


if __name__ == "__main__":
    main()
