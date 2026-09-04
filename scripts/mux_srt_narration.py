#!/usr/bin/env python3
"""
SRT 旁白混音：edge-tts 合成中文旁白 → 按字幕时间轴铺成整轨 → mux 进静音成片

流程：
  1. 解析 SRT（复用 parse_srt.py）
  2. 每条字幕单独用 edge-tts 合成（默认云希 zh-CN-YunxiNeural，免费、无需 key）
  3. 逐条对齐到它自己的字幕起点。默认 **不改语速**：语音比字幕窗长就让它自然说完、
     后面的句子顺延（句间保留半拍），整体放不进视频就报错，提示去加长画面/凝视——
     卡点应该由画面时长决定，而不是把人声催快。
     只有显式 `--fit atempo` 才会加速塞进窗口，并逐条告警。
  4. 铺成与视频等长的单声道 wav
  5. ffmpeg mux：视频流直接 copy，音频编码成 aac

不烧录字幕：字幕仍是外部 .srt，画面不做任何改动（视频流是 -c:v copy）。

用法：
  <ENV_PY> mux_srt_narration.py --srt <字幕.srt> --video <静音.mp4> --output <成片.mp4> \\
      [--voice zh-CN-YunxiNeural] [--rate +0%] [--gap-ms 120] [--keep-wav]

末行输出 OUTPUT=<路径>。缺 edge-tts / 缺 ffmpeg / 合成失败（如无网络）时以非零码退出。
"""
from __future__ import annotations

import argparse
import asyncio
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from parse_srt import parse_srt  # noqa: E402

SAMPLE_RATE = 24000          # edge-tts 输出 24kHz，直接沿用避免重采样
DEFAULT_VOICE = "zh-CN-YunxiNeural"   # 云希：中文男声，免费无 key
DEFAULT_GAP_MS = 120         # 相邻旁白之间至少留的呼吸间隔
MAX_ATEMPO = 2.0             # 单个 atempo 的稳妥上限，超过就串联多级
SPEED_WARN = 1.35            # 加速超过这个倍数就提醒（字幕可能写得太满）


class NarrationError(RuntimeError):
    """旁白混音失败，message 已是可直接展示的中文原因。"""


# ──────────────────────────────────────────────────────────────
# 外部工具
# ──────────────────────────────────────────────────────────────
def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise NarrationError(
            f"找不到 {name}：旁白混音需要系统 ffmpeg（同时提供 ffprobe）。"
            f"请安装 ffmpeg 后重试（macOS: brew install ffmpeg；Debian/Ubuntu: apt install ffmpeg）。"
        )
    return path


def probe_duration_ms(path: Path) -> float:
    ffprobe = require_tool("ffprobe")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip()) * 1000.0
    except ValueError:
        raise NarrationError(f"无法读取时长: {path}（ffprobe: {result.stderr.strip()[:200]}）") from None


def has_audio_stream(path: Path) -> bool:
    ffprobe = require_tool("ffprobe")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_name", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


# ──────────────────────────────────────────────────────────────
# 纯函数：时间轴规划与变速（可单独测试）
# ──────────────────────────────────────────────────────────────
def plan_windows(
    cues: list[dict], total_ms: float, gap_ms: int = DEFAULT_GAP_MS
) -> list[tuple[int, int]]:
    """
    给每条字幕算出 (起点, 可用窗口长度)。

    窗口右边界取「下一条字幕的起点」而不是本条的结束时间：这样即使 SRT 里
    两条字幕重叠，旁白也不会互相压到——最坏情况是被加速，但绝不重叠。
    最后一条以视频总时长收尾。
    """
    windows: list[tuple[int, int]] = []
    for index, cue in enumerate(cues):
        start = max(0, int(cue["startMs"]))
        if index + 1 < len(cues):
            limit = int(cues[index + 1]["startMs"])
        else:
            limit = int(max(total_ms, cue["endMs"]))
        # 密集字幕的真实空间可能小于 MIN_WINDOW_MS；不能为保底窗长越过下一条起点。
        window = max(1, limit - start - gap_ms)
        windows.append((start, window))
    return windows


def fit_factor(raw_ms: float, window_ms: int) -> float | None:
    """音频超出窗口时返回需要的加速倍数，否则返回 None（不动它）。"""
    if raw_ms <= window_ms or window_ms <= 0:
        return None
    return raw_ms / window_ms


def atempo_filters(factor: float) -> list[str]:
    """
    把加速倍数拆成若干级 atempo。atempo 单级过大音质会崩，
    所以超过 MAX_ATEMPO 就用几何级串联（如 3.0 → 1.732 × 1.732）。
    """
    if factor <= 1.0:
        return []
    stages = max(1, math.ceil(math.log(factor) / math.log(MAX_ATEMPO)))
    per_stage = factor ** (1.0 / stages)
    return [f"atempo={per_stage:.6f}"] * stages


# ──────────────────────────────────────────────────────────────
# edge-tts 合成
# ──────────────────────────────────────────────────────────────
def synthesize_cue(text: str, voice: str, out_path: Path, rate: str = "+0%") -> None:
    """
    用 edge-tts 合成一条旁白（mp3）。测试里可以整体替换掉这个函数。
    edge-tts 未安装、或合成失败（多数是没网）时抛 NarrationError。
    """
    try:
        import edge_tts
    except ImportError as exc:
        raise NarrationError(
            "缺少 edge-tts：请先运行 `python scripts/prepare_env.py`，"
            "或手动 `pip install edge-tts`。"
        ) from exc

    async def run() -> None:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(str(out_path))

    try:
        asyncio.run(run())
    except NarrationError:
        raise
    except Exception as exc:  # edge-tts 的网络错误类型很杂，统一收口
        raise NarrationError(
            f"edge-tts 合成失败（{type(exc).__name__}: {exc}）。"
            "该服务需要联网访问微软 TTS 接口；离线环境请改用本地 TTS 或事后自行配音。"
        ) from exc

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise NarrationError(f"edge-tts 没有产出音频: {out_path}（通常是网络被拦或音色名有误）")


def list_voices_hint() -> str:
    return "可用 `python -m edge_tts --list-voices | grep zh-CN` 查看中文音色。"


# ──────────────────────────────────────────────────────────────
# 解码 / 拼轨 / 混音
# ──────────────────────────────────────────────────────────────
def decode_pcm(path: Path, factor: float | None = None) -> np.ndarray:
    """把任意音频解码成 SAMPLE_RATE 单声道 int16；factor 给定则同时变速。"""
    ffmpeg = require_tool("ffmpeg")
    cmd = [ffmpeg, "-v", "error", "-i", str(path)]
    filters = atempo_filters(factor) if factor else []
    if filters:
        cmd += ["-filter:a", ",".join(filters)]
    cmd += ["-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise NarrationError(f"解码失败: {path}（ffmpeg: {result.stderr.decode(errors='replace')[:200]}）")
    return np.frombuffer(result.stdout, dtype=np.int16)


def _fade_out(pcm: np.ndarray, ms: int = 40) -> np.ndarray:
    """给硬截断的尾巴加个短淡出，避免爆音。"""
    n = min(len(pcm), int(SAMPLE_RATE * ms / 1000))
    if n <= 1:
        return pcm
    out = pcm.astype(np.float32)
    out[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
    return out.astype(np.int16)


def build_bed(
    clips: list[tuple[int, np.ndarray]], total_ms: float
) -> np.ndarray:
    """把各条旁白按起点铺进一条与视频等长的静音轨。"""
    total_samples = max(1, int(round(total_ms * SAMPLE_RATE / 1000)))
    bed = np.zeros(total_samples, dtype=np.int16)
    for start_ms, pcm in clips:
        offset = int(round(start_ms * SAMPLE_RATE / 1000))
        if offset >= total_samples:
            continue
        end = min(total_samples, offset + len(pcm))
        chunk = pcm[: end - offset]
        # 构造上不会重叠，这里直接覆盖即可（用加法反而可能削顶）
        bed[offset:end] = chunk
    return bed


def write_wav(path: Path, pcm: np.ndarray) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


def mux(video: Path, audio_wav: Path, output: Path) -> Path:
    """视频流直接 copy，音频编成 aac；不烧录字幕、不改画面。"""
    ffmpeg = require_tool("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-v", "error",
        "-i", str(video), "-i", str(audio_wav),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", str(SAMPLE_RATE),
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise NarrationError(f"mux 失败（ffmpeg: {result.stderr.strip()[:300]}）")
    return output


# ──────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────
def mux_narration(
    srt_path: Path,
    video_path: Path,
    output_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    gap_ms: int = DEFAULT_GAP_MS,
    keep_wav: bool = False,
    fit_mode: str = "extend",
) -> Path:
    """
    fit_mode:
      "extend"（默认）—— 不动语速。语音超出字幕窗就让它自然说完、后面顺延；
                          如果整体超出视频长度，报错并提示去加长画面/凝视。
      "atempo"        —— 强行塞进窗口（会加速并告警），只在明确要求时用。
    """
    if not srt_path.exists():
        raise NarrationError(f"找不到字幕: {srt_path}")
    if not video_path.exists():
        raise NarrationError(f"找不到视频: {video_path}")
    if output_path.resolve() == video_path.resolve():
        raise NarrationError("输出路径不能和输入视频相同（避免覆盖已确认的成片）")

    cues = [c for c in parse_srt(srt_path.read_text(encoding="utf-8-sig")) if c["text"].strip()]
    if not cues:
        raise NarrationError(f"字幕里没有可用文本: {srt_path}")

    video_ms = probe_duration_ms(video_path)
    windows = plan_windows(cues, video_ms, gap_ms)
    print(f"  字幕 {len(cues)} 条，视频 {video_ms / 1000:.2f}s，音色 {voice}")

    clips: list[tuple[int, np.ndarray]] = []
    sped_up = 0
    extended: list[tuple[int, float]] = []
    overflow_ms = 0.0
    with tempfile.TemporaryDirectory(prefix="srtnarration_") as tmp:
        tmp_dir = Path(tmp)
        cursor_ms = 0.0          # 上一条旁白的实际结束时间（extend 模式下用来防重叠）
        for index, (cue, (start_ms, window_ms)) in enumerate(zip(cues, windows), start=1):
            mp3 = tmp_dir / f"cue-{index:03d}.mp3"
            synthesize_cue(cue["text"], voice, mp3, rate=rate)
            raw_ms = probe_duration_ms(mp3)

            note = ""
            place_ms = float(start_ms)
            if fit_mode == "atempo":
                # 强行塞进窗口：只有显式要求时才这么干，音会变快、卡点会飘
                factor = fit_factor(raw_ms, window_ms)
                pcm = decode_pcm(mp3, factor)
                limit_samples = int(round(window_ms * SAMPLE_RATE / 1000))
                if len(pcm) > limit_samples:      # atempo 有取整误差，硬截断兜底
                    pcm = _fade_out(pcm[:limit_samples])
                if factor:
                    sped_up += 1
                    note = (f"  加速 ×{factor:.2f}"
                            + ("  [偏快，建议改用 --fit extend 或精简字幕]"
                               if factor > SPEED_WARN else ""))
            else:
                # 默认 extend：不改语速。语音超窗就让它自然说完，
                # 后面的句子顺延（句与句之间至少留 gap_ms 半拍）。
                pcm = decode_pcm(mp3, None)
                place_ms = max(place_ms, cursor_ms)
                if place_ms > start_ms + 1:
                    note = f"  顺延 +{place_ms - start_ms:.0f}ms"
                if raw_ms > window_ms:
                    extended.append((index, raw_ms - window_ms))
                    note += (f"  超窗 +{raw_ms - window_ms:.0f}ms（未加速；"
                             f"画面这一笔该画久一点）")

            duration_ms = len(pcm) / SAMPLE_RATE * 1000
            cursor_ms = place_ms + duration_ms + gap_ms
            if place_ms + duration_ms > video_ms:
                overflow_ms = max(overflow_ms, place_ms + duration_ms - video_ms)
            clips.append((int(round(place_ms)), pcm))

            print(f"  #{index:>3} {place_ms / 1000:7.2f}s 窗口 {window_ms / 1000:5.2f}s "
                  f"语音 {raw_ms / 1000:5.2f}s{note}")

        if overflow_ms > 0 and fit_mode != "atempo":
            raise NarrationError(
                f"旁白比画面长 {overflow_ms / 1000:.2f}s，放不进当前成片。\n"
                f"  请按下面任一种方式加长画面（推荐，卡点才对得上）：\n"
                f"    · 把最后一幕的 sceneDurationMs / 凝视时间加长 ≥{overflow_ms / 1000:.1f}s\n"
                f"    · 把相关区域的 durationMs 调大（画慢一点）后重渲\n"
                f"    · 或精简这几条字幕的文案\n"
                f"  只有确实要强行塞进现有时长时，才用 --fit atempo（会加速、卡点会飘）。"
            )

        bed = build_bed(clips, video_ms)
        wav_path = (
            output_path.with_suffix("").with_name(output_path.stem + ".narration.wav")
            if keep_wav else tmp_dir / "narration.wav"
        )
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        write_wav(wav_path, bed)
        final = mux(video_path, wav_path, output_path)
        if keep_wav:
            print(f"  旁白轨已保留: {wav_path}")

    speech_ms = sum(len(pcm) for _, pcm in clips) / SAMPLE_RATE * 1000
    print(f"\n  旁白总时长 {speech_ms / 1000:.2f}s / 视频 {video_ms / 1000:.2f}s"
          f"（占比 {speech_ms / video_ms * 100:.0f}%）")
    if fit_mode == "atempo":
        print(f"  模式 atempo：{sped_up} 条被加速")
    else:
        print(f"  模式 extend：未改语速，{len(extended)} 条超出字幕窗（已自然说完并顺延）")
        for index, over in extended[:6]:
            print(f"    · 第 {index} 条超窗 {over / 1000:.2f}s —— 建议把对应区域画久一点")
    return final


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="用 edge-tts 给静音白板成片配中文旁白并 mux 进 MP4"
    )
    parser.add_argument("--srt", required=True, help="原始字幕文件（与成片同一份）")
    parser.add_argument("--video", required=True, help="静音成片 MP4")
    parser.add_argument("--output", required=True, help="带旁白的输出 MP4")
    parser.add_argument("--voice", default=DEFAULT_VOICE,
                        help=f"edge-tts 音色（默认 {DEFAULT_VOICE} 云希）。{list_voices_hint()}")
    parser.add_argument("--rate", default="+0%",
                        help="edge-tts 语速偏移，如 -10%% / +10%%（默认 +0%%）")
    parser.add_argument("--gap-ms", type=int, default=DEFAULT_GAP_MS,
                        help=f"相邻旁白之间的呼吸间隔毫秒（默认 {DEFAULT_GAP_MS}）")
    parser.add_argument("--fit", dest="fit_mode", default="extend",
                        choices=["extend", "atempo"],
                        help="语音超出字幕窗时怎么办：extend 不改语速、自然说完并顺延（默认，"
                             "放不进就报错让你加长画面）；atempo 强行加速塞进窗口（会告警）")
    parser.add_argument("--keep-wav", action="store_true", help="保留铺好的旁白 wav")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    print("=" * 56)
    print("SRT 旁白混音 (edge-tts)")
    print("=" * 56)
    try:
        final = mux_narration(
            Path(args.srt), Path(args.video), Path(args.output),
            voice=args.voice, rate=args.rate, gap_ms=args.gap_ms, keep_wav=args.keep_wav,
            fit_mode=args.fit_mode,
        )
    except NarrationError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    size_mb = final.stat().st_size / (1024 * 1024)
    print(f"\n最终视频: {final}  ({size_mb:.2f} MB)")
    print("=" * 56)
    print(f"OUTPUT={final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
