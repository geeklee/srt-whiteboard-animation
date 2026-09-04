#!/usr/bin/env python3
"""
开场封面：把封面分镜 + 中文主标/副标写成一份 annotation.json

封面和普通幕走**同一条**渲染管线（render_stream_whiteboard.py），只是编排固定：
  1. 先在顶部空白带手写主标 + 副标（通栏，约 90% 画布宽）
  2. 再点缀封面里的小黑（一个 vignette）
  3. 末尾留一小段凝视；合并时 merge_scenes 的 hold 会把它凑到约 1 秒，
     然后擦入第一幕

中文标题**不烤进出图**：Codex 出的封面图里不能有字，字由渲染器写。

用法：
  python make_cover.py --board 封面.png --title "动态组合" \\
      --subtitle "把可撤销效应和响应式协效应做成运行时" \\
      --output 封面.annotation.json [--no-cover]

`--no-cover` 时什么都不做、返回 0，方便上层脚本用同一条命令切换有无封面。
末行输出 OUTPUT=<路径>。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

# 标题区宽度占画布比例：通栏才够大，手机上也能一眼读到
TITLE_WIDTH_RATIO = 0.90
# 标题区高度下限（换算到 1080 长边输出后的像素）
MIN_TITLE_OUTPUT_PX = 150
CAP_LONG_EDGE = 1080


def ink_bbox(image: np.ndarray, threshold: int = 128) -> tuple[int, int, int, int]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ys, xs = np.nonzero(gray < threshold)
    if ys.size == 0:
        raise SystemExit("[err] 封面图里没有墨迹，无法定位小黑")
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def write_ms_for(title: str, subtitle: str) -> int:
    """书写时长随字数走：主标慢一点，副标快一点。"""
    return int(900 + len(title) * 260 + len(subtitle) * 110)


def build_cover(
    board: Path, title: str, subtitle: str,
    lead_ms: int = 300, gaze_ms: int = 400,
    accent_ms: int | None = None, write_ms: int | None = None,
    pad: int = 16,
) -> dict:
    image = cv2.imdecode(np.fromfile(str(board), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"[err] 读不出封面图: {board}")
    height, width = image.shape[:2]
    x0, y0, x1, y1 = ink_bbox(image)

    margin_x = int(width * (1 - TITLE_WIDTH_RATIO) / 2)
    margin_y = int(height * 0.05)
    title_bottom = max(margin_y + 80, y0 - pad - 8)
    accent_top = max(0, y0 - pad)
    title_bottom = min(title_bottom, accent_top)
    title_height = title_bottom - margin_y
    if title_height < 60:
        raise SystemExit(
            f"[err] 封面顶部留白不足：标题区只有 {title_height}px，且会与小黑区域重叠。"
            "请把封面主体下移，至少留出 60px 标题区。"
        )
    floor = int(np.ceil(MIN_TITLE_OUTPUT_PX / (CAP_LONG_EDGE / width)))
    if title_height < floor:
        print(f"  [warn] 标题区仅 {title_height}px（输出约 "
              f"{title_height * CAP_LONG_EDGE / width:.0f}px），低于 {floor}px 下限；"
              f"封面图上半部分要留更多空白")

    writing = write_ms or write_ms_for(title, subtitle)
    accent = accent_ms or int(max(900, min(2200, (x1 - x0) * (y1 - y0) / 900)))

    elements = [
        {
            "id": "cover-title", "label": "封面标题", "sequence": 1, "type": "text",
            "narrativeRole": "片头主标与副标", "subtitle": title,
            "text": {"title": title, "subtitle": subtitle},
            "region": {
                "x": margin_x, "y": margin_y,
                "width": int(width * TITLE_WIDTH_RATIO), "height": title_height,
            },
            "reveal": {
                "direction": "left_to_right", "startMs": lead_ms,
                "durationMs": writing, "maskPaddingPx": 22, "protectedRegions": [],
            },
            "handPath": {
                "start": [margin_x, margin_y],
                "end": [margin_x + int(width * TITLE_WIDTH_RATIO), margin_y + title_height],
                "easing": "easeInOut",
            },
        },
        {
            "id": "cover-accent", "label": "封面小黑", "sequence": 2, "type": "structure",
            "narrativeRole": "片头点缀：小黑把两块零件拼到一起", "subtitle": subtitle,
            "region": {
                "x": max(0, x0 - pad), "y": max(0, y0 - pad),
                "width": min(width, x1 + pad) - max(0, x0 - pad),
                "height": min(height, y1 + pad) - max(0, y0 - pad),
            },
            "reveal": {
                "direction": "left_to_right", "startMs": lead_ms + writing + 250,
                "durationMs": accent, "maskPaddingPx": 22, "protectedRegions": [],
            },
            "handPath": {
                "start": [(x0 + x1) // 2, y0], "end": [(x0 + x1) // 2, y1],
                "easing": "easeInOut",
            },
        },
    ]
    last_end = max(e["reveal"]["startMs"] + e["reveal"]["durationMs"] for e in elements)
    return {
        "sceneId": "scene-00-cover",
        "canvas": {"width": width, "height": height},
        "storyBasis": f"{title}｜{subtitle}",
        "sceneDurationMs": last_end + gaze_ms,
        "elements": elements,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成开场封面的 annotation.json")
    parser.add_argument("--board", help="封面分镜 PNG（16:9，上半留白，图内无字）")
    parser.add_argument("--title", help="中文主标（建议 ≤8 字）")
    parser.add_argument("--subtitle", default="", help="中文副标（建议 ≤22 字）")
    parser.add_argument("--output", help="输出的 annotation.json 路径")
    parser.add_argument("--lead-ms", type=int, default=300, help="开场先落笔的等待（默认 300）")
    parser.add_argument("--write-ms", type=int, default=None, help="标题书写时长（默认按字数算）")
    parser.add_argument("--accent-ms", type=int, default=None, help="小黑点缀时长（默认按墨量算）")
    parser.add_argument("--gaze-ms", type=int, default=400,
                        help="封面自身的收尾停留；合并时 merge 的 hold 会把它凑到约 1s（默认 400）")
    parser.add_argument("--no-cover", action="store_true", help="跳过封面，什么都不做")
    args = parser.parse_args(argv)

    if args.no_cover:
        print("  已按 --no-cover 跳过封面")
        return 0
    missing = [name for name in ("board", "title", "output") if not getattr(args, name)]
    if missing:
        parser.error("缺少参数: " + ", ".join("--" + m for m in missing))

    cover = build_cover(
        Path(args.board), args.title, args.subtitle,
        lead_ms=args.lead_ms, gaze_ms=args.gaze_ms,
        accent_ms=args.accent_ms, write_ms=args.write_ms,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cover, ensure_ascii=False, indent=2), encoding="utf-8")
    title_region = cover["elements"][0]["region"]
    print(f"  封面: {cover['sceneDurationMs'] / 1000:.1f}s"
          f"（写字 {cover['elements'][0]['reveal']['durationMs'] / 1000:.1f}s"
          f" + 小黑 {cover['elements'][1]['reveal']['durationMs'] / 1000:.1f}s"
          f" + 凝视 {args.gaze_ms / 1000:.1f}s）"
          f"  标题区 {title_region['width']}x{title_region['height']}")
    print(f"OUTPUT={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
