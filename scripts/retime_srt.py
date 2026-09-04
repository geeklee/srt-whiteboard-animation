#!/usr/bin/env python3
"""
SRT 重定时：让字幕/旁白跟上合并后的真实时间线

`merge_scenes.py` 会在幕与幕之间插入「停留 + 擦除」过渡，于是第 k 幕在成片里
整体后移 k × 过渡时长；有封面时整条正片还要再后移一个封面长度；另外每幕片头
的空白纸会被裁掉（leadTrimMs）。如果字幕还按原始时间轴走，旁白就会和画面错开——
正是「旁白已开口、画布还空着」的来源之一。本脚本按 timeline.json 把这三项都补上。

本脚本按 `parse_srt.py` 的分幕结果，把每一幕的字幕整体平移到
`merge_scenes.py --timeline-out` 记录的新起点上。

也可以只做「按作画时序对齐」：用 --annotations 指定各幕的 annotation.json，
每条字幕会被对齐到它对应区域的实际作画窗口（区域 startMs/durationMs），
这样旁白必然落在"这一笔正在画"的时间里。每幕第一条字幕默认提前到
文字区开始书写之后（写标题也是在动笔），避免幕首 5–6 秒静音；
不想这样就加 --no-text-lead。

用法：
  python retime_srt.py --srt 原始.srt --scenes scenes.json --timeline timeline.json \\
      --output 重定时.srt [--annotations 幕1.json 幕2.json ...] [--lead-ms 250] [--tail-ms 250]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from parse_srt import parse_srt  # noqa: E402


def format_timestamp(ms: float) -> str:
    ms = max(0, int(round(ms)))
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def write_srt(cues: list[dict], path: Path) -> None:
    blocks = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(
            f"{index}\n"
            f"{format_timestamp(cue['startMs'])} --> {format_timestamp(cue['endMs'])}\n"
            f"{cue['text']}\n"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks), encoding="utf-8")


def shift_by_timeline(
    cues: list[dict], scenes: list[dict], timeline: dict
) -> list[dict]:
    """把每一幕的字幕整体平移到合并后的新起点。"""
    merged = {s["sceneIndex"]: s for s in timeline["scenes"]}
    out: list[dict] = []
    for scene in scenes:
        target = merged.get(scene["sceneIndex"])
        if target is None:
            raise SystemExit(f"[err] 时间线里没有第 {scene['sceneIndex']} 幕")
        offset = (target["startMs"] - float(target.get("leadTrimMs", 0) or 0)
                  - scene["startMs"])
        first, last = scene["cueRange"]
        for cue in cues[first - 1:last]:
            out.append({
                "startMs": cue["startMs"] + offset,
                "endMs": cue["endMs"] + offset,
                "text": cue["text"],
            })
    return out


def align_to_drawing(
    cues: list[dict],
    scenes: list[dict],
    timeline: dict,
    annotations: list[Path],
    lead_ms: int,
    tail_ms: int,
    text_lead: bool = True,
    cover_narration_ms: int | None = None,
) -> list[dict]:
    """
    把每条字幕对齐到它对应区域的作画窗口：
      字幕起点 = 幕起点 + 区域 startMs + lead_ms（先落笔、再开口）
      字幕终点 = 幕起点 + 区域结束 + tail_ms（画完还能说半拍）

    text_lead=True（默认）时，每幕**第一条**字幕提前到文字区开始书写之后：
    写标题也是在动笔，没必要干等 5–6 秒静音。它讲的正是本幕主旨，与标题同义，
    所以提前说不会和画面脱节；其余字幕仍各自跟着自己的绘制区。
    text_lead=False 时回到"文字区完全不参与配音对齐"的老行为。

    有开场封面时（timeline 里 coverMs > 0），全片**第一条**字幕还会再往前提到
    cover_narration_ms —— 封面正在手写主标，画面并不空，没必要让片头静音好几秒。
    传 0 可以关掉这个提前。
    """
    merged = {s["sceneIndex"]: s for s in timeline["scenes"]}
    if len(annotations) != len(scenes):
        raise SystemExit(
            f"[err] annotation 数量({len(annotations)})与场景数量({len(scenes)})不一致，"
            "拒绝静默丢弃场景"
        )
    cover_ms = float(timeline.get("coverMs", 0) or 0)
    if cover_narration_ms is None:
        cover_narration_ms = 600 if cover_ms > 0 else 0
    out: list[dict] = []
    for scene_position, (scene, annotation_path) in enumerate(zip(scenes, annotations)):
        target = merged.get(scene["sceneIndex"])
        if target is None:
            raise SystemExit(f"[err] 时间线里没有第 {scene['sceneIndex']} 幕")
        annotation = json.loads(Path(annotation_path).read_text(encoding="utf-8"))
        ordered = sorted(annotation["elements"], key=lambda e: e["reveal"]["startMs"])
        drawing = [e for e in ordered if e.get("type") != "text"]
        texts = [e for e in ordered if e.get("type") == "text"]
        first, last = scene["cueRange"]
        scene_cues = cues[first - 1:last]
        if len(drawing) != len(scene_cues):
            print(f"  [warn] 第 {scene['sceneIndex']} 幕：作画区域 {len(drawing)} 个，"
                  f"字幕 {len(scene_cues)} 条，按较少的一方对齐")
        # merge_scenes 会裁掉每幕片头的空白纸（擦除要擦到有墨的画面），
        # 于是标注里的 startMs 在成片里整体提前了 leadTrimMs，必须减掉。
        trim = float(target.get("leadTrimMs", 0) or 0)
        for index, (cue, element) in enumerate(zip(scene_cues, drawing)):
            reveal = element["reveal"]
            base = target["startMs"] - trim
            start = base + reveal["startMs"] + lead_ms
            end = base + reveal["startMs"] + reveal["durationMs"] + tail_ms
            floor = target["startMs"]
            if index == 0 and text_lead and texts:
                # 提到"标题开始写"之后：幕首不再有大段静音
                text_start = base + texts[0]["reveal"]["startMs"] + lead_ms
                start = min(start, text_start)
            if scene_position == 0 and index == 0 and cover_ms > 0 and cover_narration_ms > 0:
                # 全片第一条：封面正在写标题时就可以开口，片头不用干等
                start = min(start, float(cover_narration_ms))
                floor = float(cover_narration_ms)
                cue_duration = max(800.0, float(cue["endMs"] - cue["startMs"]))
                end = min(end, start + cue_duration)
            start = max(floor, start)                  # 不早于允许的最早起点
            out.append({
                "startMs": int(round(start)),
                "endMs": int(round(max(end, start + 800))),
                "text": cue["text"],
            })
    # 相邻条目不重叠：后一条起点不早于前一条终点
    for previous, current in zip(out, out[1:]):
        if current["startMs"] < previous["endMs"]:
            previous["endMs"] = current["startMs"]
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="按合并时间线/作画时序重定时 SRT")
    parser.add_argument("--srt", required=True)
    parser.add_argument("--scenes", required=True, help="parse_srt.py 输出的 scenes.json")
    parser.add_argument("--timeline", required=True, help="merge_scenes.py --timeline-out 的 JSON")
    parser.add_argument("--output", required=True)
    parser.add_argument("--annotations", nargs="*", default=None,
                        help="各幕 annotation.json（给了就按作画时序对齐，而不是整幕平移）")
    parser.add_argument("--lead-ms", type=int, default=250,
                        help="先落笔再开口的提前量（默认 250ms）")
    parser.add_argument("--tail-ms", type=int, default=250,
                        help="画完之后字幕仍可延续的时长（默认 250ms）")
    parser.add_argument("--no-text-lead", dest="text_lead", action="store_false",
                        help="不让每幕第一条字幕提前到标题书写期（默认允许，避免幕首静音）")
    parser.add_argument("--cover-narration-ms", type=int, default=None,
                        help="有封面时，全片第一条字幕最早可以在第几毫秒开口"
                             "（默认 600；给 0 表示等封面放完再开口）")
    args = parser.parse_args(argv)

    cues = parse_srt(Path(args.srt).read_text(encoding="utf-8-sig"))
    scenes = json.loads(Path(args.scenes).read_text(encoding="utf-8"))["scenes"]
    timeline = json.loads(Path(args.timeline).read_text(encoding="utf-8"))

    if args.annotations:
        retimed = align_to_drawing(
            cues, scenes, timeline, [Path(a) for a in args.annotations],
            args.lead_ms, args.tail_ms, text_lead=args.text_lead,
            cover_narration_ms=args.cover_narration_ms,
        )
        how = "按作画时序对齐" + ("（幕首随标题书写开口）" if args.text_lead else "（幕首等画完标题）")
    else:
        retimed = shift_by_timeline(cues, scenes, timeline)
        how = "按合并时间线整幕平移"

    write_srt(retimed, Path(args.output))
    print(f"  {how}：{len(retimed)} 条字幕 → {args.output}")
    if retimed:
        print(f"  首条 {retimed[0]['startMs'] / 1000:.2f}s，"
              f"末条结束 {retimed[-1]['endMs'] / 1000:.2f}s，"
              f"成片总长 {timeline['totalMs'] / 1000:.2f}s")
    print(f"OUTPUT={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
