#!/usr/bin/env python3
"""
手写文字区：把「标题 + 要点」排版成墨迹，并给出书写笔序

为什么不在出图阶段让模型画中文：生成模型写中文几乎必然出错字、糊字。
所以画面里的中文由渲染器自己写——排版可控、字形正确、还能按笔序动画。

产出两样东西：
  ink     —— uint8 灰度图（0=墨, 255=纸），尺寸等于文字区
  strokes —— 书写笔序（区域内坐标的折线序列），供渲染器让笔尖沿着它走

手写感来自三处：逐字微旋转/微位移/微缩放、标题下方一条抖动下划线、
要点前一个手画的短横。字体优先楷体/手写体（见 fonts.py），
没有就退回常规中文字体——抖动仍然在。

同样的输入必然得到同样的输出（随机数按文本内容播种），便于测试与重渲。
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import fonts as font_lookup

INK = 0
PAPER = 255


@dataclass
class TextBlockSpec:
    """一个文字区的内容与排版参数（对应标注里的 element.text）。"""
    title: str = ""
    subtitle: str = ""              # 副标：紧跟主标，不带要点短横（封面用）
    bullets: list[str] = field(default_factory=list)
    title_scale: float = 1.0        # 标题字号相对自动值的倍数
    subtitle_scale: float = 0.62    # 副标字号 = 主标 × 该倍数
    bullet_scale: float = 1.0       # 要点字号相对自动值的倍数
    line_spacing: float = 0.55      # 行距（相对要点字号）
    underline: bool = True          # 标题下方画抖动下划线
    jitter: float = 1.0             # 手写抖动强度（0=不抖）

    @classmethod
    def from_annotation(cls, raw: object) -> "TextBlockSpec":
        """标注里 element["text"] 可以是字符串，也可以是对象。"""
        if isinstance(raw, str):
            return cls(title=raw)
        if not isinstance(raw, dict):
            raise ValueError(f"text 必须是字符串或对象，实际是 {type(raw).__name__}")
        bullets = raw.get("bullets") or []
        if isinstance(bullets, str):
            bullets = [bullets]
        return cls(
            title=str(raw.get("title", "")),
            subtitle=str(raw.get("subtitle", "")),
            bullets=[str(b) for b in bullets],
            title_scale=float(raw.get("titleScale", 1.0)),
            subtitle_scale=float(raw.get("subtitleScale", 0.62)),
            bullet_scale=float(raw.get("bulletScale", 1.0)),
            line_spacing=float(raw.get("lineSpacing", 0.55)),
            underline=bool(raw.get("underline", True)),
            jitter=float(raw.get("jitter", 1.0)),
        )

    @property
    def lines(self) -> list[str]:
        return [text for _kind, text in self.rows]

    @property
    def rows(self) -> list[tuple[str, str]]:
        """按书写顺序给出 (类型, 文本)：title / subtitle / bullet。"""
        out: list[tuple[str, str]] = []
        if self.title:
            out.append(("title", self.title))
        if self.subtitle:
            out.append(("subtitle", self.subtitle))
        out.extend(("bullet", b) for b in self.bullets if b)
        return out


def _load_font(path: str | None, size: int):
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                      # Pillow < 10.1
        return ImageFont.load_default()


def _auto_sizes(spec: TextBlockSpec, width: int, height: int) -> tuple[int, int]:
    """
    按区域大小和内容量推字号：先按行数分配高度，再确认最长行不会超宽。
    标题比要点大 1.45 倍。
    """
    rows = spec.rows
    line_count = max(1, len(rows))
    bullet_lines = max(1, len(spec.bullets)) if spec.bullets else 0
    # 高度预算：主标 1.45 份 + 副标 1.45×subtitle_scale 份 + 要点各 1 份 + 行距
    weight = (1.45 if spec.title else 0)
    weight += (1.45 * spec.subtitle_scale) if spec.subtitle else 0
    weight += bullet_lines
    gaps = (line_count - 1) * spec.line_spacing
    bullet_size = int(height / max(1e-6, weight + gaps))

    # 宽度约束：中文按“每字约等于字号”估算，要点还要留出行首短横
    longest_title = len(spec.title) if spec.title else 0
    longest_subtitle = len(spec.subtitle) if spec.subtitle else 0
    longest_bullet = max((len(b) for b in spec.bullets), default=0)
    if longest_title:
        bullet_size = min(bullet_size, int(width / (longest_title * 1.45 * 1.02)))
    if longest_subtitle:
        bullet_size = min(
            bullet_size,
            int(width / max(1.0, longest_subtitle * 1.45 * spec.subtitle_scale * 1.02)),
        )
    if longest_bullet:
        bullet_size = min(bullet_size, int((width - int(height * 0.06)) / (longest_bullet * 1.04)))

    bullet_size = max(12, int(bullet_size * spec.bullet_scale))
    title_size = max(14, int(bullet_size * 1.45 * spec.title_scale))
    return title_size, bullet_size


def _wobbly_line(
    draw: ImageDraw.ImageDraw, x0: int, y: int, x1: int, rng: random.Random,
    width: int, jitter: float,
) -> list[tuple[int, int]]:
    """画一条手绘感的横线（轻微起伏），返回它的折线点用于笔序。"""
    span = max(1, x1 - x0)
    steps = max(2, span // 18)
    amplitude = 1.6 * jitter
    phase = rng.uniform(0, math.tau)
    points = [
        (
            int(x0 + span * i / steps),
            int(y + math.sin(phase + i / steps * math.pi * 1.7) * amplitude),
        )
        for i in range(steps + 1)
    ]
    draw.line(points, fill=INK, width=width, joint="curve")
    return points


def _char_strokes(
    char_ink: np.ndarray, origin: tuple[int, int], step: int
) -> list[list[tuple[int, int]]]:
    """
    单字的书写笔序（近似）：按行扫描该字的墨迹，从上到下、每行左右交替，
    形成"一笔一笔往下写"的手感。不追求真实笔顺——笔尖只需贴着字走。
    """
    ys, xs = np.nonzero(char_ink < 128)
    if ys.size == 0:
        return []
    ox, oy = origin
    strokes: list[list[tuple[int, int]]] = []
    top, bottom = int(ys.min()), int(ys.max())
    forward = True
    row = top
    while row <= bottom:
        band = np.nonzero(char_ink[row:row + step] < 128)[1]
        if band.size:
            left, right = int(band.min()), int(band.max())
            y = min(row + step // 2, bottom)
            a, b = (left, right) if forward else (right, left)
            strokes.append([(ox + a, oy + y), (ox + b, oy + y)])
            forward = not forward
        row += step
    return strokes


def _render_line(
    line: str, font, size: int, rng: random.Random, jitter: float, max_width: int, step: int
) -> tuple[np.ndarray, list[list[tuple[int, int]]]]:
    """
    把一行字排成独立的小图（已按墨迹裁紧），并给出行内笔序。
    逐字微旋转/微缩放/微位移，做出手写的不齐感。
    """
    pad = max(6, size // 2)
    tile = np.full((size + pad * 2, max_width + pad * 2), PAPER, dtype=np.uint8)
    strokes: list[list[tuple[int, int]]] = []
    x = pad

    for char in line:
        if char.isspace():
            x += int(size * 0.4)
            continue
        glyph = Image.new("L", (size + pad * 2, size + pad * 2), PAPER)
        ImageDraw.Draw(glyph).text((pad, pad), char, font=font, fill=INK)
        dx = dy = 0
        if jitter > 0:
            glyph = glyph.rotate(
                rng.uniform(-2.6, 2.6) * jitter, resample=Image.BICUBIC, fillcolor=PAPER
            )
            scale = 1.0 + rng.uniform(-0.04, 0.04) * jitter
            if abs(scale - 1.0) > 1e-3:
                side = max(8, int(glyph.width * scale))
                glyph = glyph.resize((side, side), Image.BICUBIC)
            dx = int(rng.uniform(-1.2, 1.2) * jitter)
            dy = int(rng.uniform(-1.8, 1.8) * jitter)

        patch = np.array(glyph)
        if not (patch < 128).any():           # 字体缺该字形：跳过但推进光标
            x += int(size * 1.02)
            continue
        px, py = x - pad + dx, pad - pad + dy + pad   # 行内基线统一放在 pad 处
        py = max(0, py - pad)
        x0, y0 = max(0, px), max(0, py)
        x1 = min(tile.shape[1], px + patch.shape[1])
        y1 = min(tile.shape[0], py + patch.shape[0])
        if x1 > x0 and y1 > y0:
            sub = patch[y0 - py:y1 - py, x0 - px:x1 - px]
            target = tile[y0:y1, x0:x1]
            np.minimum(target, sub, out=target)       # 取暗：墨盖纸
            strokes.extend(_char_strokes(sub, (x0, y0), step))
        x += int(size * 1.02)
        if x - pad > max_width:               # 这一行放不下了，截断
            break

    ys, xs = np.nonzero(tile < 128)
    if ys.size == 0:
        return np.full((1, 1), PAPER, dtype=np.uint8), []
    top, bottom = int(ys.min()), int(ys.max())
    left, right = int(xs.min()), int(xs.max())
    cropped = tile[top:bottom + 1, left:right + 1]
    shifted = [[(px - left, py - top) for px, py in stroke] for stroke in strokes]
    return cropped, shifted


def _layout(
    spec: TextBlockSpec, width: int, height: int, resolved: str | None,
    title_size: int, bullet_size: int, step: int, rng: random.Random,
) -> tuple[np.ndarray, list[list[tuple[int, int]]], int]:
    """按给定字号排一次版；返回 (画布, 笔序, 实际占用高度)。"""
    canvas = np.full((height, width), PAPER, dtype=np.uint8)
    draw_image = Image.fromarray(canvas)
    strokes: list[list[tuple[int, int]]] = []
    subtitle_size = max(12, int(title_size * spec.subtitle_scale))
    title_font = _load_font(resolved, title_size)
    subtitle_font = _load_font(resolved, subtitle_size)
    bullet_font = _load_font(resolved, bullet_size)
    dash_width = max(6, int(bullet_size * 0.44))
    dash_gap = max(4, int(bullet_size * 0.26))
    cursor_y = 0

    for kind, line in spec.rows:
        is_title = kind == "title"
        is_subtitle = kind == "subtitle"
        if is_title:
            size, font = title_size, title_font
        elif is_subtitle:
            size, font = subtitle_size, subtitle_font
        else:
            size, font = bullet_size, bullet_font
        # 副标不带短横，但缩进一点，读起来附属于主标
        indent = 0 if is_title else (
            max(4, int(subtitle_size * 0.2)) if is_subtitle else dash_width + dash_gap
        )
        tile, tile_strokes = _render_line(
            line, font, size, rng, spec.jitter, max(8, width - indent), step
        )
        tile_h, tile_w = tile.shape

        if cursor_y + tile_h > height:         # 放不下：交给外层缩字号重排
            return canvas, strokes, cursor_y + tile_h

        # 要点前的手画短横，纵向对齐到这一行的中线（副标不画短横）
        if not is_title and not is_subtitle:
            marker = Image.fromarray(canvas)
            pen = ImageDraw.Draw(marker)
            strokes.append(
                _wobbly_line(pen, 0, cursor_y + tile_h // 2, dash_width, rng,
                             max(2, size // 9), spec.jitter)
            )
            canvas = np.array(marker)

        x0, y0 = indent, cursor_y
        x1, y1 = min(width, x0 + tile_w), min(height, y0 + tile_h)
        target = canvas[y0:y1, x0:x1]
        np.minimum(target, tile[: y1 - y0, : x1 - x0], out=target)
        strokes.extend(
            [[(px + x0, py + y0) for px, py in stroke] for stroke in tile_strokes]
        )
        cursor_y = y1

        if is_title and spec.underline:
            gap = max(3, int(size * 0.16))
            underline_y = cursor_y + gap
            if underline_y < height - 1:
                marker = Image.fromarray(canvas)
                pen = ImageDraw.Draw(marker)
                strokes.append(
                    _wobbly_line(pen, 0, underline_y, min(width - 2, x1), rng,
                                 max(2, size // 12), spec.jitter)
                )
                canvas = np.array(marker)
                cursor_y = underline_y + max(2, int(size * 0.1))
        cursor_y += int(
            (subtitle_size if is_subtitle else bullet_size) * spec.line_spacing
        )

    draw_image.close()
    return canvas, strokes, cursor_y


def render_text_block(
    spec: TextBlockSpec,
    width: int,
    height: int,
    font_path: str | None = None,
    stroke_step: int | None = None,
) -> tuple[np.ndarray, list[list[tuple[int, int]]]]:
    """
    把文字区排版成 (ink, strokes)。
    ink     : (height, width) uint8，0=墨 255=纸
    strokes : 书写笔序，每条是区域坐标系里的折线 [(x, y), ...]

    字号先按区域大小估算，排完发现超出就整体缩小重排（最多 5 轮），
    因此内容多的文字区会自动变小，绝不溢出区域。
    """
    if width < 8 or height < 8:
        raise ValueError(f"文字区太小: {width}x{height}")
    if not spec.lines:
        return np.full((height, width), PAPER, dtype=np.uint8), []

    resolved = font_path or font_lookup.find_font_file(prefer_handwriting=True)
    title_size, bullet_size = _auto_sizes(spec, width, height)
    seed_material = f"{'|'.join(spec.lines)}\0{width}\0{height}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:4], "big")

    canvas = np.full((height, width), PAPER, dtype=np.uint8)
    strokes: list[list[tuple[int, int]]] = []
    for _ in range(5):
        step = stroke_step or max(3, bullet_size // 5)
        canvas, strokes, used = _layout(
            spec, width, height, resolved, title_size, bullet_size, step,
            random.Random(seed),
        )
        if used <= height:
            break
        shrink = max(0.72, (height / used) * 0.96)
        new_bullet = max(11, int(bullet_size * shrink))
        if new_bullet == bullet_size:
            break
        bullet_size = new_bullet
        title_size = max(13, int(title_size * shrink))

    return canvas, [s for s in strokes if len(s) >= 2]


def strokes_to_samples(
    strokes: list[list[tuple[int, int]]], offset: tuple[int, int], step: int = 3
) -> tuple[list[tuple[int, int]], set[int]]:
    """
    把笔序折线插值成连续的笔尖采样点（输出坐标系），并标出抬笔位置。
    与网格/骨架路径同构，可直接交给渲染器的落墨函数。
    """
    ox, oy = offset
    samples: list[tuple[int, int]] = []
    pen_lifts: set[int] = set()
    for stroke in strokes:
        if not stroke:
            continue
        if samples:
            pen_lifts.add(len(samples))
        first = (stroke[0][0] + ox, stroke[0][1] + oy)
        samples.append(first)
        for (x0, y0), (x1, y1) in zip(stroke, stroke[1:]):
            ax, ay = x0 + ox, y0 + oy
            bx, by = x1 + ox, y1 + oy
            count = max(1, int(math.hypot(bx - ax, by - ay) / max(1, step)))
            for i in range(1, count + 1):
                samples.append((int(ax + (bx - ax) * i / count),
                                int(ay + (by - ay) * i / count)))
    return samples, pen_lifts
