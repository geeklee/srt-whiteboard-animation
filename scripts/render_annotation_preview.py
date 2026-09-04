#!/usr/bin/env python3
"""
区域编号预览图

在线稿上叠加每个区域的编号、名称、方向箭头，用于核对分区与叙事顺序。
预览图只是检查用的中间产物，不参与成片。

字体解析顺序（找不到中文字体时会退到 Pillow 内置位图字体并告警）：
  1. --font 参数
  2. 环境变量 SRT_WB_FONT
  3. 各平台常见中文字体（Windows / macOS / Linux）
  4. fontconfig（Linux/macOS 的 fc-match）
  5. Pillow 内置字体（无中文字形，标签会显示成方块）

用法：
  <ENV_PY> render_annotation_preview.py <图片> <标注json> <预览图输出> [--font 字体文件]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from annotation_schema import (  # noqa: E402
    AnnotationError,
    ensure_valid,
    load_annotation,
    print_report,
)

# 各平台常见的中文字体，按「字形好 → 兜底」排序
FONT_CANDIDATES = (
    # Windows
    "C:/Windows/Fonts/msyh.ttc",          # 微软雅黑
    "C:/Windows/Fonts/msyhl.ttc",
    "C:/Windows/Fonts/simhei.ttf",        # 黑体
    "C:/Windows/Fonts/simsun.ttc",        # 宋体
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
)

# fontconfig 查询用的字体族名（Linux/macOS 装了 fc-match 时才生效）
FC_FAMILIES = (
    "Noto Sans CJK SC",
    "Noto Sans CJK",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "PingFang SC",
    "Microsoft YaHei",
)


def _supports_cjk(path: str) -> bool:
    """用两个不同汉字的字形判断字体是否真的包含 CJK，而不是 tofu 占位框。"""
    try:
        font = ImageFont.truetype(path, 24)
        masks = [font.getmask(char, mode="L") for char in ("中", "文")]
        signatures = [(mask.size, mask.getbbox(), bytes(mask)) for mask in masks]
        return all(mask.getbbox() is not None for mask in masks) and signatures[0] != signatures[1]
    except (OSError, ValueError):
        return False


def _fc_match() -> str | None:
    """用 fontconfig 找一个可用的中文字体文件。没有 fc-match 就返回 None。"""
    for family in FC_FAMILIES:
        try:
            result = subprocess.run(
                ["fc-match", "-f", "%{file}", family],
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None  # 系统没有 fontconfig，不必再试其它族名
        path = result.stdout.strip()
        if result.returncode == 0 and path and Path(path).exists() and _supports_cjk(path):
            return path
    return None


def find_font_file(explicit: str | None = None) -> str | None:
    """
    定位一个可用的字体文件。返回 None 表示只能退回 Pillow 内置字体。
    explicit 优先（来自 --font 或 SRT_WB_FONT），给错了直接报错而不是静默忽略。
    """
    if explicit:
        if not Path(explicit).exists():
            raise FileNotFoundError(f"指定的字体文件不存在: {explicit}")
        return explicit
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists() and _supports_cjk(candidate):
            return candidate
    return _fc_match()


def load_fonts(explicit: str | None = None) -> tuple[ImageFont.ImageFont, ImageFont.ImageFont]:
    """返回 (大号字体, 小号字体)。找不到中文字体时退回内置字体并告警。"""
    font_file = find_font_file(explicit)
    if font_file:
        try:
            if not _supports_cjk(font_file):
                print(f"  [warn] 字体不含可用中文字形({font_file})，中文标签可能显示为方块。")
            return (
                ImageFont.truetype(font_file, 28),
                ImageFont.truetype(font_file, 18),
            )
        except OSError as exc:
            print(f"  [warn] 字体无法加载({font_file}): {exc}，退回内置字体")
    else:
        print("  [warn] 未找到可用的中文字体，标签中的中文会显示为方块。")
        print("         可用 --font <字体文件> 或环境变量 SRT_WB_FONT 指定，"
              "或安装 Noto Sans CJK / 文泉驿字体。")

    def _default(size: int) -> ImageFont.ImageFont:
        try:
            return ImageFont.load_default(size=size)   # Pillow >= 10.1
        except TypeError:
            return ImageFont.load_default()
    return _default(28), _default(18)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    """量出文本实际宽度（中英混排下按字符数估算会明显偏差）。"""
    try:
        left, _, right, _ = draw.textbbox((0, 0), text, font=font)
        return int(right - left)
    except Exception:
        return len(text) * 19


def render_preview(
    image_path: str, annotation_path: str, output_path: str, font_path: str | None = None
) -> None:
    data = load_annotation(annotation_path)
    with Image.open(image_path) as source:
        image = source.convert("RGBA")
    report = ensure_valid(
        data, image_size=image.size, source=Path(annotation_path).name
    )
    print_report(report, Path(annotation_path).name)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    _, small_font = load_fonts(font_path)
    colors = [
        (38, 103, 255, 225), (255, 105, 92, 225),
        (41, 167, 102, 225), (181, 100, 255, 225),
    ]

    for index, element in enumerate(data["elements"], start=1):
        region = element["region"]
        x, y = region["x"], region["y"]
        right, bottom = x + region["width"], y + region["height"]
        color = colors[(index - 1) % len(colors)]
        fill = (*color[:3], 24)
        draw.rounded_rectangle((x, y, right, bottom), radius=12, outline=color, width=4, fill=fill)
        draw.ellipse((x + 8, y + 8, x + 44, y + 44), fill=color)
        draw.text((x + 19, y + 8), str(index), anchor="ma", font=small_font, fill="white")

        direction = element.get("reveal", {}).get("direction", "")
        label = f"{index}. {element.get('label', element.get('id', ''))}  {direction}".rstrip()
        label_right = min(right - 8, x + 60 + _text_width(draw, label, small_font) + 8)
        draw.rounded_rectangle(
            (x + 52, y + 8, max(x + 60, label_right), y + 46), radius=6, fill=(255, 255, 255, 225)
        )
        draw.text((x + 60, y + 12), label, font=small_font, fill=color)

        # handPath 只是预览台的矩形代理，缺了不影响成片，这里跳过箭头即可
        hand_path = element.get("handPath") or {}
        start, end = hand_path.get("start"), hand_path.get("end")
        if start and end:
            start, end = tuple(start), tuple(end)
            draw.line((start, end), fill=color, width=4)
            draw.polygon(
                (end, (end[0] - 13, end[1] - 7), (end[0] - 13, end[1] + 7)), fill=color
            )

    result = Image.alpha_composite(image, overlay).convert("RGB")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.save(out, quality=95)
    print(f"OUTPUT={out}")


def main(argv: list[str] | None = None) -> int:
    import os

    parser = argparse.ArgumentParser(description="生成区域编号/方向检查图")
    parser.add_argument("image", help="线稿图路径")
    parser.add_argument("annotation", help="同名 annotation.json 路径")
    parser.add_argument("output", help="预览图输出路径")
    parser.add_argument(
        "--font", default=os.environ.get("SRT_WB_FONT"),
        help="指定字体文件（默认自动探测；也可用环境变量 SRT_WB_FONT）",
    )
    args = parser.parse_args(argv)

    try:
        render_preview(args.image, args.annotation, args.output, args.font)
    except AnnotationError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1
    except (OSError, FileNotFoundError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
