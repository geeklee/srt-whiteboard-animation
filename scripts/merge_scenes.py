#!/usr/bin/env python3
"""
多幕合并：把各场景的白板动画 MP4 按顺序硬切拼接成一条完整视频。

优先级：
  1. 各片尺寸/帧率一致 → ffmpeg concat demuxer + `-c copy`（无损、最快）
  2. 尺寸或帧率不一致 → ffmpeg filter_complex 逐片缩放补边 + 统一帧率再拼
  3. 无 ffmpeg → PyAV 逐帧重编码，缩放到第一段尺寸
单片输入也照常处理。

注意：尺寸不一致时**不能**用 `-c copy`——concat demuxer 那时依然返回 0，
却会产出「容器声明第一片尺寸、实际混着多种尺寸且 DTS 非单调」的坏文件，
所以这里先用 ffprobe 核对，一致才走无损路径。

用法：
  <ENV_PY> merge_scenes.py --inputs a.mp4 b.mp4 c.mp4 --output final.mp4
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np  # noqa: F401  (类型注解与过渡帧处理用)

# 补边颜色：与渲染器画布底色一致（stream_render.Config.canvas_hex）
PAD_COLOR = "0xF6F1E3"


def _concat_quote(path: Path) -> str:
    """
    concat 清单的单引号转义：路径里的 ' 必须写成 '\\'' ，
    否则含单引号的文件名会让清单解析失败，甚至被当成额外的 concat 指令。
    """
    return str(path.resolve().as_posix()).replace("'", "'\\''")


def _probe_streams(inputs: list[Path]) -> list[tuple[int, int, str] | None]:
    """取每片的 (宽, 高, 帧率字符串)。没有 ffprobe 或读不出来的项为 None。"""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return [None] * len(inputs)
    specs: list[tuple[int, int, str] | None] = []
    for path in inputs:
        res = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate", "-of", "csv=p=0:s=,", str(path)],
            capture_output=True, text=True,
        )
        parts = res.stdout.strip().split(",")
        if res.returncode != 0 or len(parts) < 3:
            specs.append(None)
            continue
        try:
            specs.append((int(parts[0]), int(parts[1]), parts[2]))
        except ValueError:
            specs.append(None)
    return specs


def _describe(specs: list[tuple[int, int, str] | None], inputs: list[Path]) -> None:
    for path, spec in zip(inputs, specs):
        text = f"{spec[0]}x{spec[1]} @ {spec[2]}" if spec else "探测失败"
        print(f"         {path.name}: {text}")


def _fps_value(rate: str) -> float:
    try:
        return float(Fraction(rate))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _concat_demuxer(ffmpeg: str, inputs: list[Path], output: Path, copy: bool) -> bool:
    """concat demuxer 路径。copy=True 为无损流拷贝，False 为重编码。"""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for path in inputs:
            f.write(f"file '{_concat_quote(path)}'\n")
        list_path = Path(f.name)
    try:
        tail = ["-c", "copy"] if copy else [
            "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
            "-vf", "scale='trunc(iw/2)*2':'trunc(ih/2)*2'",
        ]
        res = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(list_path), *tail, str(output)],
            capture_output=True, text=True,
        )
        if res.returncode == 0:
            how = "无损拼接" if copy else "重编码拼接"
            print(f"  ffmpeg {how}完成: {output}")
            return True
        how = "-c copy" if copy else "重编码"
        print(f"  [warn] ffmpeg {how} 失败: {res.stderr.strip()[:200]}")
        return False
    finally:
        list_path.unlink(missing_ok=True)


def _concat_filter(
    ffmpeg: str, inputs: list[Path], output: Path, specs: list[tuple[int, int, str] | None]
) -> bool:
    """
    尺寸/帧率不一致时的正确拼法：逐片等比缩放 + 补边到统一画幅、统一帧率，
    再用 filter_complex 的 concat 拼接（concat demuxer 做不到这件事）。
    基准画幅取第一片（长宽取偶数以满足 yuv420p），帧率取各片最大值。
    """
    known = [s for s in specs if s]
    if not known:
        return False
    # 第一片可探测时必须以它为画幅基准；只有第一片探测失败时，
    # 才退回首个可探测片段，让 filter 路径仍有机会完成拼接。
    base = specs[0] if specs and specs[0] is not None else known[0]
    width, height = base[0] // 2 * 2, base[1] // 2 * 2
    fps = max((_fps_value(s[2]) for s in known), default=0.0)
    fps_arg = f"{fps:.6f}".rstrip("0").rstrip(".") if fps > 0 else "30"
    print(f"  [..] 归一化到 {width}x{height} @ {fps_arg}fps 后拼接")

    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    for path in inputs:
        cmd += ["-i", str(path)]
    chains = [
        f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={PAD_COLOR},"
        f"fps={fps_arg},setsar=1[v{i}]"
        for i in range(len(inputs))
    ]
    joined = "".join(f"[v{i}]" for i in range(len(inputs)))
    filter_complex = ";".join(chains) + f";{joined}concat=n={len(inputs)}:v=1:a=0[out]"
    cmd += ["-filter_complex", filter_complex, "-map", "[out]",
            "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(output)]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"  ffmpeg 归一化拼接完成: {output}")
        return True
    print(f"  [warn] ffmpeg 归一化拼接失败: {res.stderr.strip()[:200]}")
    return False


def build_transition(
    prev_video: Path, next_video: Path, out_path: Path,
    hold_ms: int, erase_ms: int, fps: float | None = None,
    strip_next_hand: bool = True,
) -> Path | None:
    """
    造一段「上一幕停留 → 擦掉 → 露出下一幕起始纸面」的过渡片段。

    没有它的话，幕与幕之间就是硬切回空白画布：上一幕刚画完就瞬间消失，
    观众（和已经开口的旁白）会撞上 1–2 秒空白。这里的做法是：
      1. 上一幕最后一帧停留 hold_ms（≥0.5s，用户要求的下限）
      2. 一块橡皮从左到右擦过，把画面逐列换成下一幕第一帧有墨的画面
         （并抹掉那一帧里下一幕自己的手，免得画面上同时出现两只手）
    擦除用下一幕首帧作为目标，所以过渡结束时画面正好等于下一幕的起点，
    拼接处不会闪。
    """
    prev_frame = _last_frame(prev_video)
    next_frame = _first_frame(next_video, strip_hand=strip_next_hand)
    if prev_frame is None or next_frame is None:
        return None
    if prev_frame.shape != next_frame.shape:
        next_frame = cv2.resize(
            next_frame, (prev_frame.shape[1], prev_frame.shape[0]),
            interpolation=cv2.INTER_AREA,
        )

    rate = fps or _probe_fps(prev_video) or 30.0
    hold_frames = max(1, int(round(hold_ms * rate / 1000)))
    erase_frames = max(1, int(round(erase_ms * rate / 1000)))
    height, width = prev_frame.shape[:2]

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    raw = out_path.with_name(out_path.stem + "_raw.mp4")
    writer = cv2.VideoWriter(str(raw), fourcc, rate, (width, height))
    if not writer.isOpened():
        return None
    try:
        for _ in range(hold_frames):          # 1) 完整画面停留
            writer.write(prev_frame)
        for index in range(1, erase_frames + 1):  # 2) 橡皮擦过
            progress = index / erase_frames
            edge = int(round(width * progress))
            frame = prev_frame.copy()
            if edge > 0:
                frame[:, :edge] = next_frame[:, :edge]
            _draw_eraser(frame, edge, height)
            writer.write(frame)
    finally:
        writer.release()

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return raw
    result = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(raw),
         "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", str(out_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  [warn] 过渡片段转码失败，改用原始编码: {result.stderr.strip()[:160]}")
        return raw
    raw.unlink(missing_ok=True)
    return out_path


def _draw_eraser(frame: "np.ndarray", edge: int, height: int) -> None:
    """
    在擦除前沿画一块橡皮：圆角胶皮 + 深色套圈 + 少量碎屑。
    比一个纯灰方块更像"真的在擦"，也让观众看清擦除方向。
    """
    if edge <= 0 or edge >= frame.shape[1]:
        return
    body_h = max(18, height // 7)
    body_w = max(14, height // 11)
    top = max(0, height // 2 - body_h // 2)
    bottom = min(height, top + body_h)
    right = min(frame.shape[1] - 1, edge + max(3, body_w // 5))
    left = max(0, right - body_w)
    if bottom - top < 6 or right - left < 6:
        return

    radius = max(3, body_w // 4)
    body = (left, top, right, bottom)
    # 胶皮主体（暖白）+ 顶部套圈（蓝灰）+ 描边
    _rounded(frame, body, radius, (238, 236, 232), fill=True)
    band_bottom = min(bottom, top + max(5, body_h // 3))
    _rounded(frame, (left, top, right, band_bottom), radius, (176, 158, 132), fill=True)
    _rounded(frame, body, radius, (92, 88, 84), fill=False)

    # 前沿碎屑：几粒短线，越靠前越淡
    rng_seed = (edge * 2654435761) & 0xFFFFFFFF
    for i in range(3):
        offset = ((rng_seed >> (i * 5)) % max(6, body_h // 2)) - body_h // 4
        crumb_y = int(np.clip(height // 2 + offset, 0, height - 1))
        crumb_x = min(frame.shape[1] - 1, right + 2 + i * 3)
        cv2.line(frame, (crumb_x, crumb_y), (min(frame.shape[1] - 1, crumb_x + 3), crumb_y),
                 (150, 146, 140), 1)


def _rounded(frame: "np.ndarray", box: tuple[int, int, int, int], radius: int,
             color: tuple[int, int, int], fill: bool) -> None:
    """画圆角矩形（cv2 没有现成的圆角接口，用矩形 + 四角圆拼）。"""
    x0, y0, x1, y1 = box
    radius = max(1, min(radius, (x1 - x0) // 2, (y1 - y0) // 2))
    thickness = -1 if fill else 2
    if fill:
        cv2.rectangle(frame, (x0 + radius, y0), (x1 - radius, y1), color, thickness)
        cv2.rectangle(frame, (x0, y0 + radius), (x1, y1 - radius), color, thickness)
    else:
        cv2.line(frame, (x0 + radius, y0), (x1 - radius, y0), color, thickness)
        cv2.line(frame, (x0 + radius, y1), (x1 - radius, y1), color, thickness)
        cv2.line(frame, (x0, y0 + radius), (x0, y1 - radius), color, thickness)
        cv2.line(frame, (x1, y0 + radius), (x1, y1 - radius), color, thickness)
    for cx, cy, start in ((x0 + radius, y0 + radius, 180), (x1 - radius, y0 + radius, 270),
                          (x1 - radius, y1 - radius, 0), (x0 + radius, y1 - radius, 90)):
        cv2.ellipse(frame, (cx, cy), (radius, radius), 0, start, start + 90, color, thickness)


def _duration_ms(path: Path) -> float:
    """片段时长（毫秒）。优先 ffprobe，退回 cv2 的帧数/帧率。"""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is not None:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True,
        )
        try:
            return float(result.stdout.strip()) * 1000.0
        except ValueError:
            pass
    capture = cv2.VideoCapture(str(path))
    frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
    rate = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    return (frames / rate * 1000.0) if frames and rate else 0.0


def _write_timeline(
    path: Path, inputs: list[Path], transition_ms: int,
    lead_trims: list[float] | None = None, cover: Path | None = None,
) -> None:
    """
    记录每幕在合并结果中的起始时间。插了过渡之后，第 k 幕整体后移
    k × 过渡时长——旁白要跟着重定时，否则语音会比画面早说。
    配合 parse_srt.py 的 scenes[].cueRange，可用 retime_srt.py 平移字幕。
    """
    scenes = []
    cursor = 0.0
    if cover is not None:                     # 封面占掉片头，正片整体后移
        cover_ms = _duration_ms(cover)
        cursor += cover_ms + transition_ms
    for index, video in enumerate(inputs):
        duration = _duration_ms(video)
        trim = float((lead_trims or [0.0] * len(inputs))[index])
        scenes.append({
            "sceneIndex": index + 1,
            "input": str(video),
            "startMs": int(round(cursor)),
            "durationMs": int(round(duration)),
            "endMs": int(round(cursor + duration)),
            # 片头被裁掉多少毫秒：标注里的 startMs 要减掉它才对得上成片
            "leadTrimMs": int(round(trim)),
        })
        cursor += duration
        if index + 1 < len(inputs):
            cursor += transition_ms
    payload = {
        "transitionMs": transition_ms,
        "totalMs": int(round(cursor)),
        "coverMs": int(round(_duration_ms(cover))) if cover is not None else 0,
        "scenes": scenes,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  时间线已写出: {path}（过渡 {transition_ms}ms/处，总长 {payload['totalMs'] / 1000:.2f}s）")


# 擦除要擦到"已经看得见内容"的一帧：纯纸面会像闪回白板。
# 判定前先把下一幕的手抹掉（见 _without_hand），所以阈值可以压得很低——
# 只要出现第一笔墨就行，几乎不裁掉作画过程。
SEAM_INK_RATIO = 0.0012
SEAM_MAX_SKIP_S = 2.5
# 手部模板的候选高度（相对画面高）：渲染默认 493px@1080 长边，分镜常用 260
_HAND_SCALES = (0.28, 0.34, 0.40, 0.44, 0.48, 0.55, 0.62, 0.72, 0.84)
# 归一化匹配误差阈值。实测：真的有手 ≈1700；纯纸面 ≈16700、去过手 ≈14000、
# 大片黑块 ≈15500 —— 差距很大，取中间偏低的 6000 判"有手"。
_HAND_MATCH_SURE = 2500
_HAND_MATCH_LIMIT = 6000
_hand_cache: dict[str, object] = {}


def _should_trim_lead(skip_s: float, first_keeps_lead: bool, ffmpeg_available: bool) -> bool:
    """只要探测到空白 lead 就裁掉；极短 lead 也不能留给转场制造回闪。"""
    return not first_keeps_lead and skip_s > 0 and ffmpeg_available


def _hand_templates(frame_height: int) -> list[tuple["np.ndarray", "np.ndarray"]]:
    """按候选高度预生成手部模板（BGR + 0/1 蒙版）。找不到素材就返回空表。"""
    key = f"templates:{frame_height}"
    if key in _hand_cache:
        return _hand_cache[key]                      # type: ignore[return-value]
    templates: list[tuple[np.ndarray, np.ndarray]] = []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import stream_render as sr

        asset = sr.resolve_hand_asset(None, quiet=True)
        if asset is not None and Path(asset).exists():
            for ratio in _HAND_SCALES:
                target = int(frame_height * ratio)
                if target < 40:
                    continue
                loaded = sr._load_hand(Path(asset), target)
                if loaded is None:
                    continue
                hand, mask = loaded
                templates.append((hand, (mask > 0.5).astype(np.uint8)))
    except Exception as exc:                          # 素材缺失/读取失败都不该影响合并
        print(f"  [warn] 无法加载手部素材用于擦场去手: {exc}")
    _hand_cache[key] = templates
    return templates


def _locate_hand(frame: "np.ndarray") -> tuple[int, int, "np.ndarray"] | None:
    """
    在一帧里找出叠加的手（模板就是渲染用的那张素材，所以能精确匹配）。
    返回 (x, y, 0/1 蒙版)；匹配不上返回 None。命中的缩放比会被缓存复用。
    """
    height, width = frame.shape[:2]
    templates = _hand_templates(height)
    if not templates:
        return None
    cached = _hand_cache.get("scale_index")
    order = list(range(len(templates)))
    if isinstance(cached, int) and 0 <= cached < len(templates):
        order = [cached] + [i for i in order if i != cached]

    best = None
    for index in order:
        hand, mask = templates[index]
        if hand.shape[0] >= height or hand.shape[1] >= width:
            continue
        mask3 = np.repeat(mask[:, :, None], 3, axis=2) * 255
        result = cv2.matchTemplate(frame, hand, cv2.TM_SQDIFF, mask=mask3)
        score, _, location, _ = cv2.minMaxLoc(result)
        normalized = score / max(1.0, float(mask.sum()))
        if best is None or normalized < best[0]:
            best = (normalized, index, location)
        if normalized < _HAND_MATCH_SURE:            # 已经是明显命中，不用再试其它比例
            break
    if best is None or best[0] > _HAND_MATCH_LIMIT:  # 误差太大：这一帧大概没有手
        return None
    _hand_cache["scale_index"] = best[1]
    _, index, (x, y) = best
    return x, y, templates[index][1]


def _paper_color(frame: "np.ndarray") -> "np.ndarray":
    patch = max(4, min(frame.shape[:2]) // 40)
    corners = np.concatenate([
        frame[:patch, :patch].reshape(-1, 3), frame[:patch, -patch:].reshape(-1, 3),
        frame[-patch:, :patch].reshape(-1, 3), frame[-patch:, -patch:].reshape(-1, 3),
    ])
    return np.median(corners, axis=0).astype(np.uint8)


def _without_hand(frame: "np.ndarray") -> "np.ndarray":
    """
    把帧里叠加的手抹成纸色。

    擦场时如果直接擦到下一幕的真实帧，画面上会同时出现"擦的手"和"下一幕正在写字的手"
    ——两只手很怪。这里把目标帧的手去掉，等擦完播到正片时手再自然出现。
    手底下压着的那一两笔会晚 0.7 秒才露出来，肉眼几乎看不出。
    """
    located = _locate_hand(frame)
    if located is None:
        return frame
    x, y, mask = located
    cleaned = frame.copy()
    height, width = mask.shape
    region = cleaned[y:y + height, x:x + width]
    # 稍微膨胀，免得留下一圈描边
    grown = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    region[grown[: region.shape[0], : region.shape[1]] > 0] = _paper_color(frame)
    return cleaned


def _ink_ratio(frame) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float((gray < 140).mean())


def _lead_blank_seconds(
    path: Path, min_ink_ratio: float = SEAM_INK_RATIO, cap_s: float = SEAM_MAX_SKIP_S,
    strip_hand: bool = True,
) -> tuple[object, float]:
    """
    返回「第一帧看得见内容的画面」以及要跳过的片头秒数。

    片头那段还没落笔的空白纸（以及只有一支手悬着的几帧）在拼接处会像闪回白板，
    所以往后找到墨量达到 min_ink_ratio 的一帧，把之前的都裁掉；
    最多裁 cap_s 秒，免得把整段作画都跳过去。
    """
    capture = cv2.VideoCapture(str(path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    first = None
    content = None
    index = 0
    hand_share: float | None = None       # 手自身贡献的暗像素占比（标定一次即可）
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if first is None:
            first = _without_hand(frame) if strip_hand else frame
        raw = _ink_ratio(frame)
        if raw >= min_ink_ratio:
            if not strip_hand:
                content = frame
                break
            # 逐帧去手太慢：先用一帧标定"手占多少暗像素"，之后只做减法粗筛，
            # 只有粗筛通过才真去手确认。
            if hand_share is None:
                cleaned = _without_hand(frame)
                hand_share = max(0.0, raw - _ink_ratio(cleaned))
                if _ink_ratio(cleaned) >= min_ink_ratio:
                    content = cleaned
                    break
            elif raw - hand_share >= min_ink_ratio:
                cleaned = _without_hand(frame)
                if _ink_ratio(cleaned) >= min_ink_ratio:
                    content = cleaned
                    break
        index += 1
        if index / fps >= cap_s:
            break
    capture.release()
    skip = (index / fps) if content is not None else 0.0
    return (content if content is not None else first), skip


def _first_frame(path: Path, strip_hand: bool = True):
    """擦除目标：下一幕第一帧有墨的画面（默认已抹掉它自己的手）。"""
    frame, _skip = _lead_blank_seconds(path, strip_hand=strip_hand)
    return frame


def _last_frame(path: Path):
    capture = cv2.VideoCapture(str(path))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    frame = None
    if total > 0:
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, total - 1))
        ok, candidate = capture.read()
        if ok:
            frame = candidate
    if frame is None:                     # 有些容器读不到总帧数，退回顺序读到底
        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        while True:
            ok, candidate = capture.read()
            if not ok:
                break
            frame = candidate
    capture.release()
    return frame


def _probe_fps(path: Path) -> float | None:
    capture = cv2.VideoCapture(str(path))
    rate = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    return rate if rate and rate > 0 else None


def _ffmpeg_concat(inputs: list[Path], output: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False

    specs = _probe_streams(inputs)
    uniform = all(spec is not None for spec in specs) and len(set(specs)) == 1
    if uniform:
        if _concat_demuxer(ffmpeg, inputs, output, copy=True):
            return True
        if _concat_demuxer(ffmpeg, inputs, output, copy=False):
            return True
    else:
        if any(spec is None for spec in specs):
            print("  [warn] 无法探测各片参数（缺 ffprobe？），跳过无损拼接:")
        else:
            print("  [warn] 各片尺寸/帧率不一致，不能用 -c copy（会产出坏文件）:")
        _describe(specs, inputs)

    if _concat_filter(ffmpeg, inputs, output, specs):
        return True
    # 探测全失败时 filter 路径没有基准画幅可用，最后再试一次 demuxer 重编码
    return _concat_demuxer(ffmpeg, inputs, output, copy=False)


def _pyav_concat(inputs: list[Path], output: Path) -> bool:
    try:
        import av
    except ImportError:
        return False
    first = av.open(str(inputs[0]))
    vs = first.streams.video[0]
    w, h = vs.codec_context.width, vs.codec_context.height
    rate = vs.average_rate
    first.close()

    out = av.open(str(output), mode="w")
    ostream = out.add_stream("h264", rate=rate)
    ostream.width, ostream.height = w, h
    ostream.pix_fmt = "yuv420p"
    ostream.options = {"crf": "24", "preset": "medium"}
    for p in inputs:
        cont = av.open(str(p))
        for frame in cont.decode(video=0):
            if frame.width != w or frame.height != h:
                frame = frame.reformat(width=w, height=h)
            for pkt in ostream.encode(frame):
                out.mux(pkt)
        cont.close()
    for pkt in ostream.encode(None):
        out.mux(pkt)
    out.close()
    print(f"  PyAV 拼接完成: {output}")
    return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="按顺序合并多幕白板动画 MP4")
    p.add_argument("--inputs", nargs="+", required=True, help="按播放顺序的 MP4 列表")
    p.add_argument("--output", required=True, help="合并输出路径")
    p.add_argument("--hold-ms", type=int, default=600,
                   help="幕尾完整画面停留毫秒（默认 600，用户要求 ≥500）")
    p.add_argument("--erase-ms", type=int, default=700,
                   help="擦除过渡毫秒（默认 700）；设 0 关闭擦除只保留停留")
    p.add_argument("--cover", default=None,
                   help="开场封面 MP4：放在最前面，与第一幕之间同样 hold+erase 过渡")
    p.add_argument("--no-cover", action="store_true",
                   help="即使给了 --cover 也跳过封面（方便上层脚本统一命令）")
    p.add_argument("--seam-ink-ratio", type=float, default=SEAM_INK_RATIO,
                   help=f"擦除目标帧至少要有多少暗像素占比（默认 {SEAM_INK_RATIO}）；"
                        "调大 = 擦到更实的画面，但会多跳过一点作画")
    p.add_argument("--seam-max-skip-s", type=float, default=SEAM_MAX_SKIP_S,
                   help=f"每幕片头最多裁掉多少秒（默认 {SEAM_MAX_SKIP_S}）")
    p.add_argument("--keep-next-hand", action="store_true",
                   help="擦场时保留下一幕的手（默认抹掉，避免画面上出现两只手）")
    p.add_argument("--timeline-out", default=None,
                   help="把每幕在合并结果中的起始时间写成 JSON，供 SRT 重定时使用")
    args = p.parse_args(argv)

    inputs = [Path(x) for x in args.inputs]
    missing = [str(x) for x in inputs if not x.exists()]
    if missing:
        print(f"[err] 缺少输入文件: {', '.join(missing)}", file=sys.stderr)
        return 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    # 第二幕起跳过片头空白纸，擦除目标才有墨，拼接也不会闪回白板
    ffmpeg_bin = shutil.which("ffmpeg")
    trimmed_dir = Path(tempfile.mkdtemp(prefix="scene_trim_"))
    trimmed_inputs: list[Path] = []
    lead_trims: list[float] = []
    cover = None if (args.no_cover or not args.cover) else Path(args.cover)
    if cover is not None and not cover.exists():
        print(f"[err] 找不到封面: {cover}", file=sys.stderr)
        return 1
    for index, src in enumerate(inputs):
        _frame, skip = _lead_blank_seconds(
            src, min_ink_ratio=args.seam_ink_ratio, cap_s=args.seam_max_skip_s,
            strip_hand=not args.keep_next_hand,
        )
        # 有封面时第一幕也要去掉片头空白（它前面已经有封面，不再是全片开头）
        first_keeps_lead = index == 0 and cover is None
        if not _should_trim_lead(skip, first_keeps_lead, ffmpeg_bin is not None):
            trimmed_inputs.append(src)
            lead_trims.append(0.0)
            continue
        dest = trimmed_dir / src.name
        res = subprocess.run(
            [ffmpeg_bin, "-y", "-loglevel", "error", "-ss", f"{skip:.3f}",
             "-i", str(src), "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
             str(dest)],
            capture_output=True, text=True,
        )
        if res.returncode == 0:
            print(f"  第 {index + 1} 幕跳过片头空白 {skip:.2f}s")
            trimmed_inputs.append(dest)
            lead_trims.append(skip * 1000.0)
        else:
            print(f"  [warn] 第 {index + 1} 幕去空白失败，沿用原片")
            trimmed_inputs.append(src)
            lead_trims.append(0.0)
    inputs = trimmed_inputs
    if cover is not None:
        print(f"  片头封面: {cover.name}（{_duration_ms(cover) / 1000:.1f}s）")

    # 幕与幕之间插入「停留 + 擦除」过渡，避免硬切回空白画布
    ordered = ([cover] if cover is not None else []) + list(inputs)
    segments = list(ordered)
    transitions: list[Path] = []
    hold_ms, erase_ms = max(0, args.hold_ms), max(0, args.erase_ms)
    if len(ordered) > 1 and (hold_ms + erase_ms) > 0:
        temp_dir = Path(tempfile.mkdtemp(prefix="scene_transition_"))
        segments = []
        inputs = ordered
        for index, path in enumerate(inputs):
            segments.append(path)
            if index + 1 >= len(inputs):
                break
            piece = temp_dir / f"transition-{index + 1:02d}.mp4"
            built = build_transition(
                path, inputs[index + 1], piece, hold_ms, erase_ms,
                strip_next_hand=not args.keep_next_hand,
            )
            if built is None:
                print(f"  [warn] 第 {index + 1}→{index + 2} 幕之间的过渡生成失败，直接硬切")
                continue
            transitions.append(built)
            segments.append(built)
        print(f"  过渡: {len(transitions)} 段（停留 {hold_ms}ms + 擦除 {erase_ms}ms）")

    ok = _ffmpeg_concat(segments, output) or _pyav_concat(segments, output)
    if not ok:
        print("[err] 合并失败：系统无 ffmpeg 且 PyAV 不可用", file=sys.stderr)
        return 1

    if args.timeline_out:
        scene_inputs = inputs[1:] if (cover is not None and inputs and inputs[0] == cover) else inputs
        _write_timeline(
            Path(args.timeline_out), scene_inputs,
            hold_ms + erase_ms if transitions else 0,
            lead_trims=lead_trims, cover=cover,
        )
    print(f"OUTPUT={output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
