> English translation of `SKILL.md`. The active skill file is `SKILL.md` (Vietnamese); this file is a reference copy and is not loaded as a skill. If you want the agent to work in English, copy this file over `SKILL.md` and add the front matter shown below.
>
> ```yaml
> ---
> name: srt-whiteboard-animation
> description: Turn SRT subtitles into a hand-drawn whiteboard video on warm beige paper: read subtitles → propose an illustration strategy → after confirmation generate consistent line art → mark regions by narrative meaning → adjust in the preview → render MP4. Staging keeps region-mask reveals (annotation.json / sequence / startMs / protectedRegions), while inside each region ink is drawn with a continuous streamed pen stroke (skeleton/grid ink→color). Trigger when the user supplies an SRT and asks for "a hand-drawn whiteboard video from subtitles", "continuous pen strokes from SRT", "SRT to whiteboard animation", or "split scenes and draw by hand following the subtitles".
> ---
> ```

# SRT Whiteboard Animation (mask staging + streamed drawing)

Turn SRT subtitles into hand-drawn whiteboard animation. **Staging** keeps region-mask reveals (regions appear in narrative order, regions not yet reached are fully hidden, overlapping regions are protected with `protectedRegions`). **Drawing** uses a continuous pen stroke: inside each region the pen head slides continuously along a skeleton/grid to lay ink (the `ink` phase, then the `color` phase); all regions share one persistent canvas, and a region that is finished stays as drawn. All explanations, storyboards, configuration and user-facing text must be written in the user's language.

Unlike cell-by-cell jumps or rectangular wipes, the strokes of this skill **flow continuously**. Unlike whole-image streaming, it draws **region by region following the narrative of the subtitles**, so the order and timing of each element can be controlled.

## Default implementation parameters

| Item | Default requirement |
|---|---|
| Paper background | Generated images use a warm aged beige paper (recommended `#F5EBD7`); at render time, sample the background color from the four image corners (inset) to tint the background; pure white is forbidden. |
| Drawing method | Each region is drawn with a continuous streamed pen stroke: first `ink` (cover the line art), then `color` (restore the original colors); time ratio `ink:color = 2:1`. |
| Pen path | `--ink-path grid` (grid, default, stable) or `skeleton` (follow the skeleton, good for illustrations with clear line art). |
| Color fill | `--color-fill contour-wipe` (sweep along contours, default) or `brush` (brush along the trajectory). |
| Undrawn regions | A region's allowed mask = its `region` rectangle minus "all later regions + protectedRegions"; a region that has not started is fully hidden. |
| Duration source | Each image's `sceneDurationMs` comes from the subtitle time span of that scene (25–35 seconds per scene recommended). |
| Editing frames | The preview shows all numbered editing frames by default; editing frames are not part of the animation's visual content. |

## Unified visual rules for image generation (mandatory)

The source images of every scene must share one visual language. Before generating, put all of the following into the image prompt, and check each point after generating:

- **Style and composition:** minimal hand-drawn illustration, pure pencil-sketch, restrained Notion-style doodle aesthetic. Prefer expressing concepts over realism; clean composition, clean background, plenty of white space, a calm and clear overall mood, and consistent line work/characters/colors across the series.
- **Color and material:** beige paper background `#F5EBD7`, dark gray sketch lines; only red, orange and blue may be used as sparing conceptual accents. No other accent colors, highly saturated colors or complex textures.
- **Characters and objects:** objects are simple outlines with few strokes and gaps, emphasizing the core relationship/change/concept rather than proportion, material and real detail.
- **Strictly forbidden:** any text, words, letters, numbers, fonts or labels in a scene's source image; photographic realism and detail, 3D effects, painterly texture; complex scenes, dense backgrounds, ornate decoration and highly saturated images.
- **Exception for the drawing hand:** if the user states that the text on the pen body is their logo and asks to keep it, the logo on the pen body in `drawing-hand.png` may be kept; it does not count as text in the scene's source image and need not be removed or redrawn. Until the user says so explicitly, the "no text in images" rule applies.

## Confirmation gates (mandatory)

In the default workflow, **after each step, stop and wait for explicit user confirmation** before the next step begins. Before confirmation, do not generate the next step's images, annotations, preview, video or merged file; do not treat "no reply", "a general earlier authorization" or "the user did not object" as confirmation. When the user asks to change a previous step, redo only that step and wait for confirmation again afterwards.

The only accompanying action: **after generating the annotation JSON, automatically open the preview and load the folder containing that JSON**; this is part of step 3's deliverable and does not need a separate confirmation for "opening the preview". If the browser's File System Access API needs a user gesture, use the browser UI to pick exactly this folder; do not ask for extra confirmation or make the user open the preview themselves.

## Workflow

1. **Read the subtitles, propose a strategy (no images yet).** Use `scripts/parse_srt.py` to parse the SRT into subtitle lines and suggest a split of 25–35 seconds per scene. From that, give an illustration strategy: for each scene, the scene number, core idea, subject of the picture, corresponding subtitle range and `sceneDurationMs`. Each scene expresses only one core idea. **Then stop and wait for the user to confirm the strategy.**
2. **Generate line art.** Only after the strategy is confirmed, following the "Unified visual rules", generate one 16:9 line-art image per scene on warm aged beige paper `#F5EBD7`, leaving enough space between subjects to make automatic region separation easy; no text, no complex photographic imagery, no overlapping objects and nothing that breaks the rules. **Then stop, present the line art and wait for confirmation.**
3. **Read the subtitles first, then look at the image, then annotate and open the preview.** Only after the line art is confirmed, first read the subtitles that correspond to the image, then actually look at the image and take the pixel width/height of the source image; do not guess the picture from subtitles alone, and do not mechanically order by position in the image. First extract the narrative events from the subtitles, then match the visible subjects in the image to each event, and order the drawing semantically as "setting → main character/object → conflict or change action → reaction/result". Then generate `<image name>.annotation.json`. Once generated, immediately open `assets/preview.html` in the default browser and use the preview's "Open folder" button to load **the folder containing that annotation file**, including every `<name>.png` + `<name>.annotation.json` pair; do not just hand over a file path or make the user do it. **When the preview has loaded the folder, stop and wait for the user to confirm the annotations and the preview.**
4. **Generate region check images.** Only after the annotations and preview are confirmed, use `render_annotation_preview.py` to export numbered check images with directions; check that the region split matches the narrative order, every region lies inside the canvas, and overlapping subjects are protected by `protectedRegions`. **Then stop and wait for confirmation of the check images.**
5. **Adjust in the preview and save.** Only after the check images are confirmed, adjust in the already-open preview with the right folder loaded: by default (not playing) it shows the full image and the region frames; the canvas is a **rectangle proxy**: drag the four edges and corners of a region to edit `region`; on the right edit name/direction/**start (ms)**/**end (ms)** (duration = end − start, read-only) and **subtitle**; drag items in the module list to **reorder** (`sequence` is renumbered automatically), and selecting a module highlights its subtitle; drag the timeline or press play to see the reveal (regions that have not started are not shown); `direction` only affects this proxy. After editing, press "Save this scene / Save all" to write back to the original `.annotation.json` (including each region's `subtitle`, and align `sceneDurationMs` to the end of the last region + 0.5 seconds). **After saving, stop and wait for the user to confirm the final annotations and timing.**
6. **Render the final video from the command line.** Only after the final annotations and timing are confirmed, use `render_stream_whiteboard.py` to export each scene as a complete MP4, then spot-check three moments: the start, the middle of any overlapping module, and the end. **Then stop and wait for confirmation of the final video.**
7. **Merge multiple scenes (only if there are several).** Only after every per-scene video is confirmed, use `merge_scenes.py` to merge them in order into one video. **Then stop and wait for confirmation of the final merged video.**

## Directory convention

Create in the user's project:

```text
assets/whiteboard/<project>/
  scene-01-<name>.png
  scene-01-<name>.annotation.json     # same name as the png
  scene-01-<name>-whiteboard.mp4      # final video
  scene-01-<name>-preview.mp4         # real clip (made by the preview, low resolution)
```

The image and configuration must share a name: `foo.png` pairs with `foo.annotation.json`. The preview relies on this to load the configuration automatically.

## Semantic ordering and pixel-level annotation (mandatory)

1. **Basis for reading:** before annotating, both the subtitles and the source image must have been seen. If either is missing, ask for it first and do not generate an annotation.
2. **Basis for order:** `sequence`, `startMs` and `label` must reflect the order of events in the subtitles, not just left-to-right, top-to-bottom or visual prominence.
3. **Basis for coordinates:** each module outputs `x`, `y`, `width`, `height` as integer pixels in the source image's coordinate system, origin at the top-left; percentages, ratios, estimated coordinates or missing sizes are forbidden. `canvas.width`/`canvas.height` must equal the source image's pixel size.
4. **Module fields:** each item has `sequence`, `narrativeRole`, `subtitle`, `region`, `reveal`, `handPath`. `narrativeRole` describes its narrative role in the subtitles in the user's language; `subtitle` stores the subtitle text matching that region (taken from the SRT so the preview can link it and use it later); `sequence` is numbered continuously from 1.
5. **Check:** before generating the check images, verify that each region lies inside the canvas, fully covers its visible subject, and matches an event in the subtitles; for overlapping subjects use `protectedRegions` before drawing the module.

## Timing model (specific to streamed drawing)

- **Total duration of each scene** `sceneDurationMs` comes from the subtitle time span of that scene (`scenes[].sceneDurationMs` from `parse_srt.py`).
- **Regions are drawn one after another:** streamed drawing has a single moving pen, so within a scene regions should follow **one another in time** (`startMs` not overlapping): the next region starts at the previous region's `startMs + durationMs` (plus an optional 100–300 ms pause). If `startMs` values overlap the renderer still processes them in sequence, but visually they are no longer parallel.
- **ink→color inside a region:** each region's `durationMs` is split `ink:color = 2:1` into the start-of-stroke phase and the color phase. `durationMs` is determined by the **start/end times** in the preview (end − start) and can be aligned to the duration of the region's subtitle; it can also be estimated as 150 pixels/second × drawing path length.
- **Hold at the end:** after all regions are drawn, extend automatically to `sceneDurationMs`, and make sure the scene holds the full source image for at least 0.5 seconds at the end.
- `reveal.direction` in streamed drawing **does not decide the real pen path** (the path is generated from the skeleton/grid); it only serves the rectangle proxy in the preview, and is kept so the preview works.

## Mask invariants (staging layer, mandatory)

- At time `t`, a module may only show pixels once `reveal.startMs ≤ t` and not beyond the current drawing progress; a module that has not started must not reveal any line, fill or shape.
- A region's **allowed mask** = the `region` rectangle minus the `region` of all **later modules**, then minus the module's own `reveal.protectedRegions`. Streamed ink is confined to the allowed mask, so later regions are not revealed early.
- `protectedRegions` use the same integer source-image pixel coordinates as `region`, and are used when the rectangle is too large, subjects interleave, or background lines may leak.
- The renderer implements the order "confine ink to the allowed mask → later regions and protected regions are naturally untouched"; the preview's rectangle proxy uses an equivalent `destination-out` subtraction to illustrate the same staging.

## Example configuration

```json
{
  "sceneId": "scene-01",
  "canvas": { "width": 1672, "height": 941 },
  "storyBasis": "Summary of the events in this scene's subtitles",
  "sceneDurationMs": 9000,
  "elements": [
    {
      "id": "rockery",
      "label": "Rockery scene",
      "sequence": 1,
      "narrativeRole": "Setting that opens the story",
      "subtitle": "On monkey mountain, a little monkey sits on top of the rockery holding a banana.",
      "type": "structure",
      "region": { "x": 20, "y": 120, "width": 540, "height": 780 },
      "reveal": { "direction": "top_to_bottom", "startMs": 300, "durationMs": 2600, "maskPaddingPx": 22, "protectedRegions": [] },
      "handPath": { "start": [290, 130], "end": [290, 890], "easing": "easeInOut" }
    }
  ]
}
```

> `direction` / `handPath` are only used by the preview's rectangle proxy; the pen strokes in the final video are generated by the streamer and need no tuning.

## Using the scripts

All render scripts run with the interpreter in the skill's `.venv` (isolated dependencies).

1. **Prepare the environment** (first time or when dependencies are missing):
   ```bash
   python scripts/prepare_env.py --check   # probe; on success the last line prints ENV_PY=<path>, note it for later
   python scripts/prepare_env.py           # if missing, creates .venv and installs opencv-python/numpy/av
   ```
2. **Parse subtitles + suggest a scene split**:
   ```bash
   python scripts/parse_srt.py <subtitles.srt> --target-sec 30 --min-sec 25 --max-sec 35
   ```
3. **Numbered region check image**:
   ```bash
   python scripts/render_annotation_preview.py <image> <annotation> <preview image output>
   ```
4. **Preview (no server needed)**: open `assets/preview.html` (or `assets/preview.en.html` for the English UI) directly in Chrome / Edge, click "Open folder" and choose the folder → loads all images + same-named annotations → drag to adjust → "Save" to write back to the original files. Writing back needs the File System Access API (Chrome/Edge); other browsers download the file so you overwrite it manually. Rendering still runs from the command line (step 5 below).
5. **Render the final video for one scene**:
   ```bash
   <ENV_PY> scripts/render_stream_whiteboard.py <image> <annotation> <output mp4> assets/drawing-hand.png \
       [--ink-path grid|skeleton] [--color-fill contour-wipe|brush] [--total-ms <milliseconds>]
   ```
   If `--total-ms` is not set, `sceneDurationMs` from the annotation is used. The last line prints `OUTPUT=<path>`.
6. **Merge multiple scenes**:
   ```bash
   <ENV_PY> scripts/merge_scenes.py --inputs scene1.mp4 scene2.mp4 scene3.mp4 --output final.mp4
   ```

## Quality checks

Before/after rendering, confirm:

- The first frame is clean warm beige paper with no line showing early.
- The matching subtitles were read and the source image was actually viewed; `canvas` matches the source image's pixel size, and every `region` is integer pixel coordinates inside the canvas.
- `sequence` and `startMs` match the order of events in the subtitles; the numbers/labels/regions of the check image all come from the same annotation JSON.
- At three moments — the opening, the middle of any overlapping module, and when all modules are done — check: modules not yet drawn are invisible, protected regions of overlapping modules do not leak, and the final frame shows the full source image.
- The pen head follows the advancing stroke closely; for illustrations with clear line art `--ink-path skeleton` can make strokes follow more tightly.
- After all modules end, hold the full source image for at least 0.5 seconds.
- After merging several scenes, order and duration match the subtitle-based scene split.

To change the result, edit the annotation (region/order/timing) in the preview (`assets/preview.html`) and save, then render from the command line; do not re-render over and over without reason.
