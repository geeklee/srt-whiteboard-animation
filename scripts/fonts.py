#!/usr/bin/env python3
"""
中文字体定位（预览图与手写文字区共用）

优先级：显式指定 → 环境变量 → 手写体候选 → 常规中文候选 → fontconfig。
手写体候选放在前面：文字区要“像手写出来的”，楷体/手写体比无衬线更贴近白板质感。
没有手写体也能跑——退回常规中文字体，再靠 text_render 的抖动模拟手写感。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# 手写/楷体候选：白板文字区优先用它们
HANDWRITING_CANDIDATES = (
    # 项目自带或用户放置（本仓库不收字体，体积太大）
    "assets/fonts/LXGWWenKai-Regular.ttf",
    "assets/fonts/LXGWWenKaiLite-Regular.ttf",
    # Linux 常见安装位置
    "/usr/share/fonts/truetype/lxgw-wenkai/LXGWWenKai-Regular.ttf",
    "/usr/share/fonts/opentype/lxgw-wenkai/LXGWWenKai-Regular.ttf",
    "/usr/share/fonts/truetype/arphic/ukai.ttc",          # 文鼎楷体
    "/usr/share/fonts/truetype/arphic-ukai/ukai.ttc",
    # macOS
    "/System/Library/Fonts/Supplemental/Kaiti.ttc",
    "/Library/Fonts/Kaiti.ttf",
    # Windows
    "C:/Windows/Fonts/simkai.ttf",                        # 楷体
    "C:/Windows/Fonts/STKAITI.TTF",
)

# 常规中文候选（预览图标签、以及没有手写体时的兜底）
FONT_CANDIDATES = (
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhl.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
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
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # 无中文，最后兜底
)

FC_FAMILIES = (
    "LXGW WenKai",
    "Kaiti SC",
    "AR PL UKai CN",
    "Noto Sans CJK SC",
    "Noto Sans CJK",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "PingFang SC",
    "Microsoft YaHei",
    "sans-serif",
)

ENV_FONT = "SRT_WB_FONT"
ENV_HAND_FONT = "SRT_WB_TEXT_FONT"
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _existing(candidate: str) -> Path | None:
    path = Path(candidate)
    if not path.is_absolute():
        path = _REPO_ROOT / path
    return path if path.exists() else None


def fc_match(families: tuple[str, ...] = FC_FAMILIES) -> str | None:
    """用 fontconfig 找一个可用字体文件。没有 fc-match 就返回 None。"""
    for family in families:
        try:
            result = subprocess.run(
                ["fc-match", "-f", "%{file}", family],
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        path = result.stdout.strip()
        if result.returncode == 0 and path and Path(path).exists():
            return path
    return None


def find_font_file(
    explicit: str | None = None, prefer_handwriting: bool = False
) -> str | None:
    """
    定位字体文件。explicit 给了但不存在时直接报错（不静默忽略）。
    prefer_handwriting=True 时先找楷体/手写体，找不到再退常规中文字体。
    返回 None 表示只能用 Pillow 内置位图字体。
    """
    if explicit:
        if not Path(explicit).exists():
            raise FileNotFoundError(f"指定的字体文件不存在: {explicit}")
        return explicit

    env_keys = (ENV_HAND_FONT, ENV_FONT) if prefer_handwriting else (ENV_FONT,)
    for key in env_keys:
        value = os.environ.get(key)
        if value:
            if not Path(value).exists():
                raise FileNotFoundError(f"环境变量 {key} 指向的字体不存在: {value}")
            return value

    groups = (HANDWRITING_CANDIDATES, FONT_CANDIDATES) if prefer_handwriting else (FONT_CANDIDATES,)
    for group in groups:
        for candidate in group:
            found = _existing(candidate)
            if found:
                return str(found)
    return fc_match()


def is_handwriting_font(path: str | None) -> bool:
    """粗判是否命中了手写/楷体候选（用于提示用户当前是不是手写字形）。"""
    if not path:
        return False
    name = Path(path).name.lower()
    return any(key in name for key in ("wenkai", "kai", "hand", "xing", "script"))
