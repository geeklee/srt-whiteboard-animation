import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 中文标签字体：按平台依次探测；可用环境变量 SRT_WB_FONT 指定任意字体覆盖
FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",                                # Windows
    "/System/Library/Fonts/PingFang.ttc",                       # macOS
    "/System/Library/Fonts/Hiragino Sans GB.ttc",               # macOS
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",   # Linux
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",             # Linux
)


def load_fonts():
    """返回 (font, small_font)；都探测不到时退回 Pillow 内置位图字体。"""
    candidates = list(FONT_CANDIDATES)
    override = os.environ.get("SRT_WB_FONT")
    if override:
        candidates.insert(0, override)
    for path in candidates:
        try:
            return ImageFont.truetype(path, 28), ImageFont.truetype(path, 18)
        except OSError:
            continue
    print(
        "[warn] 未找到可用的中文字体，标签回退为 Pillow 内置字体（中文将显示为方块）。"
        "可用 SRT_WB_FONT=<字体文件路径> 指定。",
        file=sys.stderr,
    )
    return ImageFont.load_default(), ImageFont.load_default()


def main(image_path: str, annotation_path: str, output_path: str) -> None:
    image = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font, small_font = load_fonts()
    colors = [(38, 103, 255, 225), (255, 105, 92, 225), (41, 167, 102, 225), (181, 100, 255, 225)]

    data = json.loads(Path(annotation_path).read_text(encoding="utf-8"))
    for index, element in enumerate(data["elements"], start=1):
        region = element["region"]
        x, y = region["x"], region["y"]
        right, bottom = x + region["width"], y + region["height"]
        color = colors[(index - 1) % len(colors)]
        fill = (*color[:3], 24)
        draw.rounded_rectangle((x, y, right, bottom), radius=12, outline=color, width=4, fill=fill)
        draw.ellipse((x + 8, y + 8, x + 44, y + 44), fill=color)
        draw.text((x + 19, y + 8), str(index), anchor="ma", font=small_font, fill="white")
        label = f"{index}. {element['label']}  {element['reveal']['direction']}"
        draw.rounded_rectangle((x + 52, y + 8, min(right - 8, x + 52 + len(label) * 19), y + 46), radius=6, fill=(255, 255, 255, 225))
        draw.text((x + 60, y + 12), label, font=small_font, fill=color)
        start = tuple(element["handPath"]["start"])
        end = tuple(element["handPath"]["end"])
        draw.line((start, end), fill=color, width=4)
        draw.polygon((end, (end[0] - 13, end[1] - 7), (end[0] - 13, end[1] + 7)), fill=color)

    result = Image.alpha_composite(image, overlay).convert("RGB")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, quality=95)


if __name__ == "__main__":
    main(*sys.argv[1:4])
