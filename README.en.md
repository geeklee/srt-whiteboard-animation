# SRT Whiteboard Animation Skill

[Tiếng Việt](README.md) · **English** · [中文](README.zh.md)

> Vietnamese and English translations of [geeklee/srt-whiteboard-animation](https://github.com/geeklee/srt-whiteboard-animation) (MIT License). The original Chinese files are kept as `*.zh.*`.

A skill that turns SRT subtitles into hand-drawn whiteboard videos, drawn in narrative order. It combines **region-mask staging** with **continuous streamed pen strokes**: each element appears in turn following the subtitles, the pen lays ink continuously inside its region, then gradually adds color, and the result is exported as MP4.

It suits explainers, spoken stories, course subtitles and short-video scripts, rendered as hand-drawn animation on a warm beige paper background.

## Example

**Scene: monkeys fighting over a banana on a rockery** — following the narrative order of the subtitles, it draws the rockery and the little monkey, the big monkey grabbing the banana, and the children watching.

![Monkeys and the banana: SRT whiteboard animation demo](examples/scene-01-monkey-mountain-stream.gif)

Original line art: [view PNG](examples/scene-01-monkey-mountain.png).

## Core capabilities

- Parses SRT subtitles and splits them into scenes of a suggested 25–35 seconds
- Produces a storyboard and illustration strategy first, so each scene expresses a single core idea
- Orders elements by the events in the subtitles rather than by position on the image
- Manages regions, timing, subtitle links and overlap-protection regions in `annotation.json`
- Draws each region with a continuous streamed stroke: `ink` lays down the line art, then `color` adds color
- Includes a browser preview to adjust regions, order, timing and subtitle links
- Renders scene by scene and merges multiple scenes into a complete MP4

## How it works

The key idea is "subtitle-driven, confirmed step by step". Every step stops for confirmation, so no rendering effort is wasted before the storyboard, line art or annotations are final:

1. Parse the SRT and propose a storyboard and illustration strategy.
2. After confirmation, generate line art in one consistent style.
3. After the line art is confirmed, create annotations from the subtitles and the source image, and load them into the preview.
4. After the annotations are confirmed, generate region and direction check images.
5. In the preview, adjust regions, narrative order, timing and subtitle links, then save.
6. After the final annotations are confirmed, render each scene to MP4.
7. For multi-scene projects, merge the scenes once each is confirmed.

## Visual rules

- Warm beige paper background: `#F5EBD7` recommended
- Dark gray sketch lines; red, orange and blue only as sparing conceptual accents
- Minimal hand-drawn style, clean background and plenty of white space
- No in-scene text, labels, photographic feel, 3D effects or complex textures

## Installation and environment

The skill ships with a script that prepares its own isolated Python virtual environment. On first run:

```bash
python scripts/prepare_env.py --check
python scripts/prepare_env.py
```

On success the first command prints `ENV_PY=<path>`; use that interpreter for all later rendering to keep dependencies isolated.

## Project asset layout

```text
assets/whiteboard/<project>/
├── scene-01-<name>.png
├── scene-01-<name>.annotation.json
├── scene-01-<name>-whiteboard.mp4
└── scene-01-<name>-preview.mp4
```

The image and annotation must share a name, e.g. `scene-01-demo.png` pairs with `scene-01-demo.annotation.json`.

## Annotation format

Each element uses integer pixel coordinates of the source image and links to subtitle events through `sequence`, `subtitle` and `narrativeRole`. Order regions as "setting → key characters/objects → action or change → reaction/result".

```json
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "A little monkey holds a banana on the rockery, a big monkey snatches it, children watch.",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "Rockery scene",
      "sequence": 1,
      "narrativeRole": "Setting that opens the story",
      "subtitle": "The little monkey sits on top of the rockery, holding a banana.",
      "type": "structure",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "reveal": {
        "direction": "top_to_bottom",
        "startMs": 300,
        "durationMs": 2600,
        "maskPaddingPx": 22,
        "protectedRegions": []
      },
      "handPath": { "start": [290, 130], "end": [290, 890], "easing": "easeInOut" }
    }
  ]
}
```

`direction` and `handPath` are used only by the rectangle proxy in the preview; the real strokes in the final video are generated automatically by the stream renderer. For objects that overlap, mark in the earlier element's `protectedRegions` the areas that should appear later, so later content does not show through early.

## Common commands

Parse subtitles and propose a scene split:

```bash
python scripts/parse_srt.py <subtitles.srt> --target-sec 30 --min-sec 25 --max-sec 35
```

Generate a region check image:

```bash
python scripts/render_annotation_preview.py <image path> <annotation path> <preview output path>
```

Open `assets/preview.en.html`, click "Open folder…" to load the scene directory, then edit regions, order, timing and subtitle links.

Render one scene:

```bash
<ENV_PY> scripts/render_stream_whiteboard.py <image path> <annotation path> <output.mp4> assets/drawing-hand.png \
  --ink-path grid --color-fill contour-wipe
```

Merge multiple scenes:

```bash
<ENV_PY> scripts/merge_scenes.py --inputs scene1.mp4 scene2.mp4 scene3.mp4 --output final.mp4
```

## Quality checklist

- The first frame is clean warm beige paper with no line showing early
- `canvas` matches the source image size, and every region is integer pixel coordinates inside the canvas
- `sequence` and `startMs` follow the narrative order of the subtitles
- In mid-scene frames, regions that have not started and protected regions do not appear early
- The pen tip follows the current stroke; with clear line art you can choose `--ink-path skeleton`
- Each scene holds the full picture for at least 0.5 s at the end; the merge order matches the subtitle storyboard

## Repository contents

```text
srt-whiteboard-animation/
├── SKILL.md                         # Full workflow and constraints (Vietnamese)
├── SKILL.en.md / SKILL.zh.md        # English / original Chinese
├── README.md / README.en.md / README.zh.md
├── assets/
│   ├── drawing-hand.png              # Hand asset
│   ├── preview.html                  # Local editing preview (Vietnamese)
│   └── preview.en.html / preview.zh.html
├── examples/                         # Assets for the README example
├── scripts/
│   ├── parse_srt.py                  # Subtitle parsing and scene suggestions
│   ├── render_annotation_preview.py  # Annotation check image
│   ├── render_stream_whiteboard.py   # Streamed-stroke MP4 renderer
│   ├── merge_scenes.py               # Multi-scene merge
│   └── prepare_env.py                # Dependency environment setup
└── agents/openai.yaml                # Codex metadata
```

## Contributing

Issues and pull requests are welcome. Any change touching the drawing logic should be checked with real subtitles, annotations and rendered output to confirm mask protection, timing and the final picture.

## License

Released under the MIT License, see [LICENSE](LICENSE).

## About the original author

Original author: 一个爱养鱼的老登 / AI Builder / building a one-person company with an AI team (Douyin, Bilibili, WeChat public account: 江哥是老登啊).
