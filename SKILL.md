---
name: srt-whiteboard-animation
description: Turn an SRT subtitle file into a whiteboard hand-drawn animation on warm beige paper: read subtitles, plan illustrations, generate line art, annotate narrative regions, tune in a preview editor, render MP4 (region mask reveals + continuous stream strokes). Use when the user provides an SRT and wants a whiteboard or hand-drawn explainer video.
---

# SRT Whiteboard Animation (mask choreography + stream drawing)

English translation of the original Mandarin SKILL.md from https://github.com/geeklee/srt-whiteboard-animation (MIT).

Converts an SRT into a whiteboard hand-drawn animation. **Choreography** uses region mask reveals: regions appear one by one in narrative order, regions that have not started are fully hidden, and overlaps are guarded with `protectedRegions`. **Drawing** uses a continuous stream pen: inside its allowed mask, each region is inked by a pen tip gliding along a skeleton or grid (first `ink`, then `color`). All regions share one persistent canvas, so finished regions stay drawn. All user-facing explanations, storyboards, config text and replies use the user's language (English by default).

Unlike frame-by-frame jumps or rectangular wipes, the strokes flow continuously. Unlike whole-image stream drawing, this skill draws by subtitle narrative region, so you control the order and timing of every element.

Note: the preview editor UI (`assets/preview.html`) is still in Chinese in this version.

## Default implementation parameters

| Item | Default requirement |
|---|---|
| Paper background | Generated images use warm beige old-paper color (suggested `#F5EBD7`). At render time the paper tone is sampled inset from the four corners of the source image. Pure white is forbidden. |
| Drawing method | Per-region stream strokes: start with `ink` (lay down line art), then `color` (restore original colors). Weight `ink:color = 2:1`. |
| Stroke path | `--ink-path grid` (grid, default, stable) or `skeleton` (skeleton tracing, fits clean line-art illustrations better). |
| Coloring style | `--color-fill contour-wipe` (contour sweep, default) or `brush` (brush along the trajectory). |
| Undrawn regions | A region's allowed mask = its rectangle `region` minus all later regions and its `protectedRegions`. Regions not yet started are fully hidden. |
| Duration source | Each image's `sceneDurationMs` comes from the time span of that scene's subtitles (suggested 25-35 seconds per scene). |
| Edit boxes | The preview editor shows all numbered edit boxes by default. Edit boxes are not part of the animation picture. |

## Unified image style (mandatory)

Every scene's source image must follow one visual language. Write all of the following into the image-generation prompt in full before generating, and check each point afterwards:

- **Style and composition:** Minimal hand-drawn illustration, pure pencil-sketch look, a restrained Notion-like doodle aesthetic. Express concepts rather than realism. Simple composition, clean background, plenty of white space, calm and clear overall mood, consistent lines, characters and palette across the series.
- **Color and material:** Beige paper background `#F5EBD7`, dark gray sketch lines. Only red, orange and blue may be used, sparingly, as conceptual accents. No other accent colors, no highly saturated palettes, no complex textures.
- **People and objects:** Objects use simple outlines, few lines and white space, emphasizing relationships, change and the core concept instead of true proportions, materials and detail.
- **Absolutely forbidden:** Any text, words, letters, numbers, fonts or labels inside scene source images; photorealism, photographic detail, 3D effects, painterly texture; complex scenes, dense backgrounds, elaborate decoration and highly saturated imagery.
- **Drawing-hand exception:** If the user explicitly says the text on the pen barrel is their logo and asks to keep it, the logo on `drawing-hand.png` may stay. It is not scene source-image text and does not need to be removed or redrawn. Without that explicit statement, treat it as a text-free picture.

## Confirmation gates (mandatory)

**After every step of the default workflow, stop and wait for the user's explicit confirmation** before starting the next step. Do not generate the next step's images, annotations, previews, videos or merged files before confirmation. Do not treat "no reply", an earlier blanket authorization, or "the user did not object" as confirmation. When the user asks for changes to the previous step, redo only that step and wait for confirmation again.

The only chained action: **once the annotation JSON is created, immediately open the preview editor and load the directory containing that JSON automatically.** This is part of delivering step 3 and needs no separate confirmation. If the browser's File System Access API requires a user gesture, use the browser UI to select that already-determined directory. Do not ask the user for extra confirmation because of this, and do not hand the job back to the user to open the editor themselves.

## Workflow

1. **Read the subtitles and produce a strategy (no images yet).** Use `scripts/parse_srt.py` to parse the SRT into cues and suggest a storyboard at 25-35 seconds per scene. From it, output the illustration strategy: per scene, the scene number, core idea, main subject of the picture, the matching subtitle range and `sceneDurationMs`. Each scene expresses exactly one core idea. **Stop when done and wait for the user to confirm the strategy.**
2. **Generate line art.** Only after the strategy is confirmed, generate a 16:9 warm beige old-paper line-art image per scene following the unified image style, background `#F5EBD7`, with ample white space between subjects to make automatic splitting easy. Do not generate text, complex photos, overlapping objects or anything that conflicts with the style. **Stop when done, show the line art and wait for confirmation.**
3. **Read the subtitles, then look at the image, then annotate and open the preview editor.** Only after the user confirms the line art: first read that image's subtitles, then actually view the image and get its pixel width and height. Do not guess the picture from subtitles alone, and do not sort mechanically by on-screen position. Extract the narrative events from the subtitles, map the visible subjects in the image to those events, and order the drawing semantically: scene setup -> key character/object -> action, conflict or change -> reaction/result. Then create `<image name>.annotation.json`. Once created, immediately open `assets/preview.html` in the default browser and load, via the editor's "open folder" button, **the directory containing that annotation file**, with all its `<name>.png` + `<name>.annotation.json` pairs. Do not merely give the file path or ask the user to do it. **Stop once the editor has the directory loaded and wait for the user to confirm the annotations and preview content.**
4. **Generate region preview images.** Only after the user confirms the annotations and preview content, use `render_annotation_preview.py` to produce a numbered, direction-annotated check image. Verify that the regions match the narrative order, all regions lie inside the canvas, and overlapping subjects are guarded with `protectedRegions`. **Stop when done and wait for the user to confirm the preview image.**
5. **Adjust and save in the preview editor.** Only after the user confirms the preview image, adjust in the already open editor with the directory loaded. By default (not playing) it shows the full image and region boxes. The canvas is a **rectangle proxy**: drag the region's edges and corners to change `region`; on the right, edit the name, direction, **start (ms) / end (ms)** (duration = end - start, read-only) and **subtitle**; drag items in the module list to **reorder** (`sequence` renumbers automatically); selecting a module highlights its subtitle. Drag the timeline or press play to watch the reveal (regions not yet started are hidden). `direction` only affects this proxy. When done, click "save this scene / save all" to write back to the original `.annotation.json` (including each region's `subtitle`, and aligning `sceneDurationMs` to the last region's end + 0.5 s). **Stop after saving and wait for the user to confirm the final annotations and timing.**
6. **Render the final video from the command line.** Only after the user confirms the final annotations and timing, use `render_stream_whiteboard.py` to render each scene to a full-clear MP4, and spot check three moments: the opening, mid-point of any overlapping module, and the end. **Stop when done and wait for the user to confirm the video.**
7. **Merge scenes (multi-scene projects only).** Only after the user confirms all single-scene videos, use `merge_scenes.py` to merge them in order into one. **Stop when done and wait for the user to confirm the final merged video.**

## Directory convention

Create in the user's project:

```text
assets/whiteboard/<project>/
  scene-01-<name>.png
  scene-01-<name>.annotation.json     # same name as the png
  scene-01-<name>-whiteboard.mp4      # final render
  scene-01-<name>-preview.mp4         # real clip (made by the editor, low-res)
```

Image and config must share a name: `foo.png` pairs with `foo.annotation.json`. The editor loads configs automatically on that basis.

## Semantic ordering and pixel-level annotation (must do)

1. **Reading basis:** Before annotating you must have both the subtitles and the image you actually viewed. If either is missing, ask for it first; do not generate annotations.
2. **Ordering basis:** `sequence`, `startMs` and `label` must reflect the order of events in the subtitles, not merely left-to-right, top-to-bottom, or visual prominence.
3. **Coordinate basis:** Every module outputs integer pixel `x`, `y`, `width`, `height` in the source image's coordinate system, origin at the top-left. Percentages, ratios, estimated coordinates and omitted sizes are forbidden. `canvas.width` / `canvas.height` must equal the source image's pixel size.
4. **Module fields:** Every element has `sequence`, `narrativeRole`, `subtitle`, `region`, `reveal`, `handPath`. `narrativeRole` states its narrative function in the subtitles; `subtitle` stores the subtitle text for that region (from the SRT, used for editor linkage and later purposes); `sequence` starts at 1 and is consecutive.
5. **Validation:** Before generating the preview, check that each region lies inside the canvas, covers its corresponding visible subject and matches the subtitle event. Guard overlapping subjects with `protectedRegions` so the later module is drawn afterwards.

## Timing model (stream drawing only)

- **Total scene duration** `sceneDurationMs` comes from the scene's subtitle time span (`scenes[].sceneDurationMs` from `parse_srt.py`).
- **Regions are drawn serially:** the stream method is one pen moving, so within a scene the regions should run one after another in time (non-overlapping `startMs`): the next region starts at the previous region's `startMs + durationMs` (+ an optional 100-300 ms breath). If `startMs` values overlap, the renderer still processes them in order, but visually it is no longer concurrent.
- **ink -> color within a region:** Each region's `durationMs` is split `ink:color = 2:1` into a pen-down segment and a coloring segment. `durationMs` is set by the editor's **start/end time** (end - start) and can be aligned to the duration of the region's subtitle; as an initial estimate you can use 150 pixels/second x drawing distance.
- **Hold at the end:** After all regions finish, the video pads out to `sceneDurationMs`, guaranteeing at least 0.5 s of the complete original image at the end.
- Under the stream method, `reveal.direction` **does not determine the real strokes** (strokes come from the skeleton/grid automatically); it only drives the editor's rectangle proxy demo. It is kept so the editor keeps working.

## Mask invariants (choreography layer, must hold)

- At time `t`, a module may only show pixels after `reveal.startMs <= t` and not beyond the current drawing progress. No lines, fills or imagery from a module that has not started may appear.
- Each region's **allowed mask** = its rectangle `region` minus the `region` of all **later modules**, minus this module's `reveal.protectedRegions`. Stream inking is confined to the allowed mask, so later regions never leak early.
- `protectedRegions` use the same integer source-image pixel coordinates as `region`, for cases where a rectangle is too large, subjects overlap, or background lines might leak.
- The renderer already implements the order "ink only inside the allowed mask, so later regions and protected areas are untouched by construction"; the editor's rectangle proxy demonstrates the same choreography with an equivalent `destination-out` subtraction.

## Config example

```json
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "Event summary of this scene's subtitles",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "Rockery scene",
      "sequence": 1,
      "narrativeRole": "Scene setup for the story",
      "subtitle": "On Monkey Mountain, a little monkey sits atop the rockery holding a banana.",
      "type": "structure",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "reveal": { "direction": "top_to_bottom", "startMs": 300, "durationMs": 2600, "maskPaddingPx": 22, "protectedRegions": [] },
      "handPath": { "start": [290, 130], "end": [290, 890], "easing": "easeInOut" }
    }
  ]
}
```

> `direction` / `handPath` are only for the editor's rectangle proxy; the real strokes in the final video are generated automatically by stream drawing and need no fine-tuning.

## Using the scripts

Run all render scripts with the interpreter from the skill's `.venv` (dependency isolation).

1. **Prepare the environment** (first run or missing dependencies):
   ```bash
   python scripts/prepare_env.py --check   # probe; on success the last line prints ENV_PY=<path>, capture it
   python scripts/prepare_env.py           # creates .venv and installs opencv-python/numpy/av/Pillow if missing
   ```
2. **Parse subtitles + suggest storyboard:**
   ```bash
   python scripts/parse_srt.py <subtitles.srt> --target-sec 30 --min-sec 25 --max-sec 35
   ```
3. **Numbered region preview image:**
   ```bash
   <ENV_PY> scripts/render_annotation_preview.py <image> <annotation> <preview output>
   ```
   Labels may contain CJK text, so a CJK font is needed. The script auto-detects common fonts on Windows, macOS and Linux; set the `SRT_WB_FONT` environment variable to a font file (.ttc/.ttf/.otf) if none is found.
4. **Preview editor (no server needed):** open `assets/preview.html` directly in Chrome / Edge, click "open folder" and choose the directory -> it loads every image plus its same-name annotation -> edit by dragging -> "save" writes back to the original files. Writing back needs the File System Access API (Chrome/Edge); other browsers fall back to download-and-overwrite by hand. Rendering still happens on the command line (step 5 below).
5. **Render a single scene:**
   ```bash
   <ENV_PY> scripts/render_stream_whiteboard.py <image> <annotation> <output.mp4> assets/drawing-hand.png \
       [--ink-path grid|skeleton] [--color-fill contour-wipe|brush] [--total-ms <milliseconds>]
   ```
   When `--total-ms` is omitted, the annotation's `sceneDurationMs` is used. The last line prints `OUTPUT=<path>`.
6. **Merge scenes:**
   ```bash
   <ENV_PY> scripts/merge_scenes.py --inputs scene1.mp4 scene2.mp4 scene3.mp4 --output final.mp4
   ```

## Quality checks

Confirm before and after rendering:

- The first frame is a clean warm beige old-paper background with no lines showing early.
- The matching subtitles were read and the source image was actually viewed; `canvas` matches the image's pixel size, and every `region` is integer pixel coordinates inside the canvas.
- `sequence` and `startMs` match the order of subtitle events; the preview image's numbers, labels and regions come from the same annotation JSON.
- Check three moments, the opening, mid-point of any overlapping module, and after all modules finish: undrawn modules are all invisible, protected overlap areas do not leak, and the final frame shows the complete original image.
- The pen tip stays close to the advancing stroke; for clean line-art illustrations use `--ink-path skeleton` to make strokes fit better.
- After all modules finish, at least 0.5 s of the full original image holds.
- After merging, order and duration match the subtitle storyboard.

To change the look, first adjust the annotations (regions / order / timing) in the preview editor (`assets/preview.html`) and save, then render from the command line; do not repeatedly re-render blindly.
