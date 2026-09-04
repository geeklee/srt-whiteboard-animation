#!/usr/bin/env python3
"""在马克笔笔杆上添加文案，生成新图。

用法:
    python3 add_pen_text.py <空图> <文字> <输出路径>
    python3 add_pen_text.py assets/drawing-hand-clean.png "江哥是老登啊" demo/out.png
    python3 add_pen_text.py assets/drawing-hand-clean.png "你好世界" demo/out.png --size 65

文字沿笔杆轴向排布，并在笔杆上做水平/垂直居中，字号与笔画粗细默认与原图
"江哥是老登啊" 保持一致（73px，近黑色）。笔杆之外的透明像素不会被改动。

本脚本既可作为命令行工具独立使用，也可被渲染器 import（见 render_pen_text）。
"""
import argparse
import os
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# 与原图 "江哥是老登啊" 一致的排版参数
DEFAULT_SIZE = 73          # 字号(px)，原图实测每字步进 ≈ 72.7
DEFAULT_COLOR = (7, 7, 6)  # 原图文字颜色实测值

_HERE = Path(__file__).resolve().parent
_ASSETS_DIR = _HERE.parent / "assets"

# --pen-text 的默认底图（笔杆无文字的 clean 图）
DEFAULT_HAND_CLEAN = _ASSETS_DIR / "drawing-hand-clean.png"

# 字体查找顺序：项目自带开源字体 → 常见系统字体
FONT_FALLBACKS = [
    str(_ASSETS_DIR / "fonts" / "LXGWWenKaiLite-Regular.ttf"),  # 随项目自带 (SIL OFL 1.1, 子集化到 GB2312 常用字)
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
SS = 3                     # 超采样倍数
EDGE_MARGIN = 5            # 距笔杆边缘的安全边距(px)


# ---------------------------------------------------------------- 形态学工具
def _flood(mask, seeds):
    h, w = mask.shape
    out = np.zeros_like(mask)
    q = deque()
    for s in seeds:
        if mask[s] and not out[s]:
            out[s] = True
            q.append(s)
    while q:
        y, x = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                q.append((ny, nx))
    return out


def _erode(m, it=1):
    for _ in range(it):
        o = m.copy()
        o[1:, :] &= m[:-1, :]; o[:-1, :] &= m[1:, :]
        o[:, 1:] &= m[:, :-1]; o[:, :-1] &= m[:, 1:]
        o[1:, 1:] &= m[:-1, :-1]; o[:-1, :-1] &= m[1:, 1:]
        o[1:, :-1] &= m[:-1, 1:]; o[:-1, 1:] &= m[1:, :-1]
        m = o
    return m


def detect_pen(img):
    """返回 (笔杆区域mask, 轴向角度(度, 顺时针为正), 中心(cx, cy))。"""
    a = np.array(img).astype(int)
    rgb = a[..., :3]
    opaque = a[..., 3] > 128
    white = opaque & (rgb.min(2) > 150) & ((rgb.max(2) - rgb.min(2)) < 35)

    # 最大白色连通域 = 笔杆
    seen = np.zeros_like(white)
    best = None
    for sy, sx in zip(*np.nonzero(white)):
        if seen[sy, sx]:
            continue
        comp = _flood(white, [(sy, sx)])
        seen |= comp
        if best is None or comp.sum() > best.sum():
            best = comp
    pen = best

    # 填掉内部空洞(高光/描线断口)，得到完整笔杆区域
    y0, y1 = np.nonzero(pen.any(1))[0][[0, -1]]
    x0, x1 = np.nonzero(pen.any(0))[0][[0, -1]]
    pad = 3
    sub = np.zeros((y1 - y0 + 1 + 2 * pad, x1 - x0 + 1 + 2 * pad), bool)
    sub[pad:-pad, pad:-pad] = pen[y0:y1 + 1, x0:x1 + 1]
    comp = ~sub
    h, w = comp.shape
    border = ([(0, i) for i in range(w)] + [(h - 1, i) for i in range(w)]
              + [(i, 0) for i in range(h)] + [(i, w - 1) for i in range(h)])
    filled_sub = sub | ~_flood(comp, border) & comp
    filled = np.zeros_like(pen)
    filled[y0:y1 + 1, x0:x1 + 1] = filled_sub[pad:-pad, pad:-pad]

    # 主轴方向 (PCA)
    ys, xs = np.nonzero(filled)
    pts = np.stack([xs - xs.mean(), ys - ys.mean()])
    evals, evecs = np.linalg.eigh(pts @ pts.T / pts.shape[1])
    dx, dy = evecs[:, np.argmax(evals)]
    if dx < 0:
        dx, dy = -dx, -dy
    angle = np.degrees(np.arctan2(dy, dx))       # 顺时针(屏幕)为正

    # 在旋转坐标系里取外接框中心 -> 笔杆水平&垂直居中点
    d = np.array([dx, dy])
    n = np.array([-dy, dx])
    u = xs * d[0] + ys * d[1]
    v = xs * n[0] + ys * n[1]
    uc = (u.min() + u.max()) / 2
    vc = (v.min() + v.max()) / 2
    cx = uc * d[0] + vc * n[0]
    cy = uc * d[1] + vc * n[1]
    return filled, angle, (cx, cy), (v.max() - v.min())


# ------------------------------------------------------------------ 文字图层
def pick_font(path, size, index=0):
    for p in ([path] if path else []) + FONT_FALLBACKS:
        if p and os.path.exists(p):
            return ImageFont.truetype(p, size * SS, index=index), p
    raise SystemExit('找不到可用中文字体，请用 --font 指定')


def _is_wide(ch):
    """CJK 及全角标点按 1em 等宽排布，其余(拉丁/数字/空格)用字体自身宽度。"""
    o = ord(ch)
    return (0x2E80 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF
            or 0xF900 <= o <= 0xFAFF or 0xFF00 <= o <= 0xFF60
            or 0x3000 <= o <= 0x303F)


def render_text(text, font, spacing_em):
    """中文按全角步进、西文按字体自身步进，统一基线绘制，返回裁到 ink 的灰度图层。"""
    em = font.size * spacing_em
    W = int(em * max(len(text), 1) + font.size * 4)
    H = int(font.size * 4)
    layer = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(layer)
    x = font.size * 2
    y = H / 2
    for ch in text:
        if _is_wide(ch):
            cw = d.textlength(ch, font=font)
            d.text((x + (em - cw) / 2, y), ch, font=font, fill=255, anchor='ls')
            x += em
        else:
            d.text((x, y), ch, font=font, fill=255, anchor='ls')
            x += d.textlength(ch, font=font)
    bbox = layer.getbbox()
    if bbox is None:
        raise SystemExit('文字渲染为空')
    return layer.crop(bbox)


# ------------------------------------------------------------------ 核心逻辑
def render_pen_text(base_path, text, *, font_path=None, font_index=0,
                    size=DEFAULT_SIZE, spacing=1.0, color=None, angle=None):
    """在笔杆上写字，返回 (RGBA PIL Image, 元信息 dict)。

    元信息含 font/size/angle/cx/cy，供命令行打印调试信息；渲染器可忽略。
    """
    base = Image.open(base_path).convert('RGBA')
    orig = np.array(base)

    pen, detected_angle, (cx, cy), pen_w = detect_pen(base)
    if angle is None:
        angle = detected_angle

    font, resolved_font_path = pick_font(font_path, size, font_index)
    ink = render_text(text, font, spacing)
    ink = ink.resize((max(ink.width // SS, 1), max(ink.height // SS, 1)), Image.LANCZOS)

    # 旋转到笔杆方向（屏幕顺时针 = PIL 负角）
    rot = ink.rotate(-angle, expand=True, resample=Image.BICUBIC)
    ra = np.array(rot).astype(np.float64) / 255.0

    # 以笔杆中心对齐文字中心
    H, W = orig.shape[:2]
    ox = int(round(cx - rot.width / 2))
    oy = int(round(cy - rot.height / 2))
    alpha = np.zeros((H, W))
    sx0, sy0 = max(0, -ox), max(0, -oy)
    dx0, dy0 = max(0, ox), max(0, oy)
    ww = min(rot.width - sx0, W - dx0)
    hh = min(rot.height - sy0, H - dy0)
    alpha[dy0:dy0 + hh, dx0:dx0 + ww] = ra[sy0:sy0 + hh, sx0:sx0 + ww]

    # 只画在笔杆内部（保证笔杆外、透明区域不受影响）
    inner = _erode(pen, EDGE_MARGIN)
    clipped = float(alpha[~inner].sum())
    alpha[~inner] = 0.0
    if clipped > 5:
        print(f'警告: 文字超出笔杆被裁掉 {clipped:.0f} 像素，可考虑减小 --size 或缩短文字')

    color_rgb = DEFAULT_COLOR
    if color:
        c = color.lstrip('#')
        color_rgb = tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

    out = orig.copy()
    a3 = alpha[..., None]
    rgbf = out[..., :3].astype(np.float64)
    out[..., :3] = np.clip(np.round(rgbf * (1 - a3) + np.array(color_rgb) * a3), 0, 255).astype(np.uint8)
    assert (out[..., 3] == orig[..., 3]).all()

    meta = {
        'font': os.path.basename(resolved_font_path),
        'size': size,
        'angle': angle,
        'cx': cx,
        'cy': cy,
    }
    return Image.fromarray(out), meta


def main():
    ap = argparse.ArgumentParser(description='在笔杆上添加文案')
    ap.add_argument('base', help='空图(无文字的底图)路径')
    ap.add_argument('text', help='要写在笔杆上的文字')
    ap.add_argument('out', help='输出图片路径')
    ap.add_argument('--font', default=None, help='字体文件路径')
    ap.add_argument('--font-index', type=int, default=0,
                    help='ttc 字体集合内的子字体序号，如 Hiragino Sans GB 的 W6 为 2')
    ap.add_argument('--size', type=int, default=DEFAULT_SIZE, help=f'字号，默认 {DEFAULT_SIZE}')
    ap.add_argument('--spacing', type=float, default=1.0, help='字间步进(em)，默认 1.0')
    ap.add_argument('--color', default=None, help='文字颜色 #rrggbb，默认贴近原图的近黑色')
    ap.add_argument('--angle', type=float, default=None, help='强制指定倾斜角度(度)')
    args = ap.parse_args()

    img, meta = render_pen_text(
        args.base, args.text,
        font_path=args.font, font_index=args.font_index,
        size=args.size, spacing=args.spacing, color=args.color, angle=args.angle,
    )

    dst = args.out
    d = os.path.dirname(os.path.abspath(dst))
    os.makedirs(d, exist_ok=True)
    img.save(dst)
    print(f'已生成 {dst}  (字体 {meta["font"]}, 字号 {meta["size"]}, '
          f'角度 {meta["angle"]:.2f}°, 笔杆中心 ({meta["cx"]:.0f},{meta["cy"]:.0f}))')


if __name__ == '__main__':
    main()
