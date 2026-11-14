#!/usr/bin/env python3
"""Reproducible pixel checks without hand-overlay false positives; no browser."""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
STEM = "scene-explicit-order"


def read_frames(path):
    cap = cv2.VideoCapture(str(path))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


def dark(frame, x, y, r=5):
    return int(frame[y-r:y+r+1, x-r:x+r+1].min()) < 100


def main():
    video = ROOT / f"{STEM}-whiteboard.mp4"
    ann = json.loads((ROOT / f"{STEM}.annotation.json").read_text())
    log = json.loads((ROOT / "tip-log.json").read_text())
    frames = read_frames(video)
    # Use the same documented CLI with only the hand disabled. Checking a
    # dark neighbourhood in the hand video itself could merely detect the pen!
    with tempfile.TemporaryDirectory() as td:
        bare, barelog = Path(td) / "bare.mp4", Path(td) / "tip-log.json"
        subprocess.run([sys.executable, str(REPO / "scripts/render_stream_whiteboard.py"),
                        str(ROOT / f"{STEM}.png"), str(ROOT / f"{STEM}.annotation.json"),
                        str(bare), "--bare-tip", "--cap-long-edge", "960", "--fps", "30",
                        "--tip-log", str(barelog)], check=True)
        clean = read_frames(bare)
        clean_log = json.loads(barelog.read_text())
    checks = []
    def check(name, ok, detail):
        checks.append(dict(name=name, ok=bool(ok), detail=detail))
    ink = {eid: [i for i,e in enumerate(log) if e["elementId"] == eid and e["phase"] == "ink" and e["tip"]]
           for eid in ("sun", "hill")}
    sun, hill = ink["sun"], ink["hill"]
    early = sun[3]
    check("same_timeline_with_and_without_hand", log == clean_log and len(frames) == len(clean), len(log))
    check("explicit_order_overrides_start_and_file_order",
          ann["elements"][0]["id"] == "hill" and ann["elements"][0]["reveal"]["startMs"] == 0
          and sun[0] < hill[0], dict(sunStart=sun[0], hillStart=hill[0]))
    check("sun_starts_east", (log[sun[0]]["x"],log[sun[0]]["y"]) == (772,160), log[sun[0]])
    check("clockwise_lower_arc_before_upper_arc", log[early]["y"] > 160
          and dark(clean[early],log[early]["x"],log[early]["y"])
          and not dark(clean[early],720,108), log[early])
    check("hill_hidden_for_entire_sun_phase",
          all(int(clean[i][175:435,50:400].min()) > 100 for i in range(hill[0])), hill[0])
    check("hill_starts_bottom_right", (log[hill[0]]["x"],log[hill[0]]["y"]) == (380,420), log[hill[0]])
    check("all_ink_tips_touch_revealed_ink_without_hand",
          all(dark(clean[i],log[i]["x"],log[i]["y"]) for i in sun+hill), len(sun+hill))
    check("hill_direction_peak_before_left_base",
          any(log[i]["y"] < 190 for i in hill[:len(hill)//2])
          and not dark(clean[hill[0]+3],60,420), len(hill))
    check("sun_persists_when_hill_starts", dark(clean[hill[0]],720,108), hill[0])
    # Interior cross/rays must grow outwards, not appear in a single wipe.
    # Ignore the ring intersection (radius ~52): source-ink revelation naturally
    # exposes a small crossing stub when either overlapping path reaches it.
    radii = (15, 30, 70, 90)
    ray_onsets = {}
    for name, dx, dy in (("east",1,0),("south",0,1),("west",-1,0),("north",0,-1)):
        onsets = []
        for radius in radii:
            x, y = 720 + dx*radius, 160 + dy*radius
            hits = [i for i in sun if dark(clean[i],x,y,r=1)]
            onsets.append(hits[0] if hits else -1)
        ray_onsets[name] = onsets
        check(f"{name}_ray_progressive_near_to_far",
              min(onsets) >= 0 and onsets == sorted(onsets) and len(set(onsets)) >= 3,
              dict(radii=radii, firstVisibleFrames=onsets))
    check("ray_order_east_south_west_north",
          all(ray_onsets[a][-1] <= ray_onsets[b][0] for a,b in
              (("east","south"),("south","west"),("west","north"))), ray_onsets)
    source = cv2.imread(str(ROOT / f"{STEM}.png"))
    source_ink = (source.min(axis=2) < 100).astype("uint8")
    # Compression / anti-aliasing may shift the boundary by a pixel or two.
    allowed_ink = cv2.dilate(source_ink, cv2.getStructuringElement(cv2.MORPH_RECT,(5,5))) > 0
    top_roi = (slice(50,125),slice(705,736))
    extra = [int(((frame.min(axis=2) < 100) & ~allowed_ink)[top_roi].sum()) for frame in clean]
    check("sun_top_has_no_new_hook_outside_source_ink",
          max(extra) == 0,
          dict(extraDarkPixelsBeyond2pxSourceMargin=max(extra),
               sourceFeature="flat-ended north ray crossing the circle, not an authored arrow"))
    indices = {"00-blank":0,"01-sun-start":sun[0],"02-sun-mid-circle":sun[7],
               "03-sun-rays":sun[len(sun)*2//3],"04-hill-start":hill[0],
               "05-hill-mid":hill[len(hill)//3],"06-final":len(frames)-1}
    outframes = ROOT / "frames"
    outframes.mkdir(exist_ok=True)
    meta = {}
    for name, i in indices.items():
        cv2.imwrite(str(outframes / f"{name}.png"),frames[i])
        meta[name] = dict(frameIndex=i,timeMs=round(i*1000/30),tip=log[i],file=f"frames/{name}.png")
    proof = dict(fps=30, frameCount=len(frames), outputSize=dict(width=960,height=540),
                 verification="Pixel assertions use a fresh --bare-tip render with identical tip-log; not the dark pen overlay.",
                 sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                         [video,ROOT/f"{STEM}.annotation.json",ROOT/"tip-log.json"]},
                 frames=meta, checks=checks, allPassed=all(c["ok"] for c in checks))
    (ROOT/"proof.json").write_text(json.dumps(proof,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(checks,ensure_ascii=False,indent=2))
    if not proof["allPassed"]:
        raise SystemExit("sample proof failed")


if __name__ == "__main__":
    main()
