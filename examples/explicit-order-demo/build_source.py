#!/usr/bin/env python3
"""生成不涉及私有素材的顺序绘制样片源图与标注（几何线稿：太阳与小山）。"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
W, H = 960, 540
PAPER = (245, 235, 215)  # #F5EBD7
INK = (45, 45, 45)
SUN_CENTER = (720, 160)
SUN_R = 52
HILL = [(380, 420), (220, 180), (60, 420), (380, 420)]  # 右底 → 顶 → 左底 → 闭合


def _circle(center, radius, start_deg=0, clockwise=True, n=73):
    cx, cy = center
    pts = []
    for i in range(n):
        deg = start_deg + (i / (n - 1)) * (360 if clockwise else -360)
        rad = math.radians(deg)
        pts.append([round(cx + radius * math.cos(rad)), round(cy + radius * math.sin(rad))])
    return pts


def main() -> None:
    img = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(img)
    # 太阳：圆周 + 四向射线（东、南、西、北）
    circle = _circle(SUN_CENTER, SUN_R, start_deg=0, clockwise=True)
    draw.line([tuple(p) for p in circle], fill=INK, width=6, joint="curve")
    rays = []
    for ang in (0, 90, 180, 270):
        rad = math.radians(ang)
        end = (round(SUN_CENTER[0] + 100 * math.cos(rad)), round(SUN_CENTER[1] + 100 * math.sin(rad)))
        draw.line([SUN_CENTER, end], fill=INK, width=6)
        rays.append([list(SUN_CENTER), list(end)])
    # 小山：三角形轮廓，起点在右下角
    draw.line([tuple(p) for p in HILL], fill=INK, width=7, joint="curve")
    png = ROOT / "scene-explicit-order.png"
    img.save(png, quality=95)

    annotation = {
        "sceneId": "scene-explicit-order",
        "canvas": {"width": W, "height": H},
        "storyBasis": "先画出右侧太阳（顺时针圆环，再由中心射出东、南、西、北四道光），再画出左侧小山（从右下角起笔，经山顶到左下角后闭合）。用来证明区域顺序与真实笔顺不是一回事。",
        "sceneDurationMs": 4200,
        "elementOrder": ["sun", "hill"],
        "elements": [
            {
                "id": "hill",
                "label": "小山",
                "sequence": 2,
                "narrativeRole": "后揭示的左侧结构，笔顺从右下角开始，与从上到下的自动路径不同",
                "subtitle": "然后从山脚右侧起笔，翻过山顶，落到左边，再把底边连起来。",
                "type": "structure",
                "region": {"x": 40, "y": 150, "width": 380, "height": 300},
                "reveal": {
                    "direction": "top_to_bottom",
                    "startMs": 0,
                    "durationMs": 1500,
                    "maskPaddingPx": 12,
                    "protectedRegions": [],
                },
                "handPath": {"start": [230, 160], "end": [230, 440], "easing": "easeInOut"},
                "strokePaths": [HILL],
            },
            {
                "id": "sun",
                "label": "太阳",
                "sequence": 1,
                "narrativeRole": "先揭示的右侧主体：顺时针画圆，再依次画出四道光",
                "subtitle": "先从太阳的右侧落笔，顺时针画出圆环，再从中心依次向东、南、西、北画出光芒。",
                "type": "object",
                "region": {"x": 600, "y": 40, "width": 240, "height": 240},
                "reveal": {
                    "direction": "top_to_bottom",
                    "startMs": 200,
                    "durationMs": 1800,
                    "maskPaddingPx": 12,
                    "protectedRegions": [],
                },
                "handPath": {"start": [720, 50], "end": [720, 270], "easing": "easeInOut"},
                "strokePaths": [circle, *rays],
            },
        ],
    }
    # 文件里 hill 写在 sun 前面，正是为了证明 elementOrder 而不是文件顺序说了算
    json_path = ROOT / "scene-explicit-order.annotation.json"
    json_path.write_text(json.dumps(annotation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SOURCE={png}")
    print(f"ANNOTATION={json_path}")


if __name__ == "__main__":
    main()
