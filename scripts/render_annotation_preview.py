import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import draw_order


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc"),
    ]
    for font_file in candidates:
        if font_file.exists():
            try:
                return ImageFont.truetype(str(font_file), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_polyline(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], color, width: int = 4) -> None:
    if len(points) == 1:
        x, y = points[0]
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)
        return
    draw.line(points, fill=color, width=width)
    end = points[-1]
    start = points[-2]
    import math
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (end[0] - 13 * math.cos(ang - 0.4), end[1] - 13 * math.sin(ang - 0.4))
    right = (end[0] - 13 * math.cos(ang + 0.4), end[1] - 13 * math.sin(ang + 0.4))
    draw.polygon((end, left, right), fill=color)


def main(image_path: str, annotation_path: str, output_path: str) -> None:
    image = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _load_font(28)
    small_font = _load_font(18)
    colors = [(38, 103, 255, 225), (255, 105, 92, 225), (41, 167, 102, 225), (181, 100, 255, 225)]

    data = json.loads(Path(annotation_path).read_text(encoding="utf-8"))
    elements, _warnings = draw_order.ordered_elements(data)
    if not elements:
        elements = [e for e in data.get("elements", []) if isinstance(e, dict)]
    for index, element in enumerate(elements, start=1):
        region = element["region"]
        x, y = region["x"], region["y"]
        right, bottom = x + region["width"], y + region["height"]
        color = colors[(index - 1) % len(colors)]
        fill = (*color[:3], 24)
        draw.rounded_rectangle((x, y, right, bottom), radius=12, outline=color, width=4, fill=fill)
        draw.ellipse((x + 8, y + 8, x + 44, y + 44), fill=color)
        draw.text((x + 19, y + 8), str(index), anchor="ma", font=small_font, fill="white")
        direction = (element.get("reveal") or {}).get("direction", "")
        label = f"{index}. {element.get('label', '')}  {direction}".strip()
        draw.rounded_rectangle((x + 52, y + 8, min(right - 8, x + 52 + len(label) * 19), y + 46), radius=6, fill=(255, 255, 255, 225))
        draw.text((x + 60, y + 12), label, font=small_font, fill=color)
        explicit, strokes, _ = draw_order.parse_stroke_paths(element)
        if explicit:
            for stroke in strokes:
                _draw_polyline(draw, stroke, color)
        else:
            hand = element.get("handPath") or {}
            if "start" in hand and "end" in hand:
                start = tuple(hand["start"])
                end = tuple(hand["end"])
                draw.line((start, end), fill=color, width=4)
                draw.polygon((end, (end[0] - 13, end[1] - 7), (end[0] - 13, end[1] + 7)), fill=color)

    result = Image.alpha_composite(image, overlay).convert("RGB")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, quality=95)


if __name__ == "__main__":
    main(*sys.argv[1:4])
