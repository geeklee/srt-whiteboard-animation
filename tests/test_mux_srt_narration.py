"""
旁白混音（scripts/mux_srt_narration.py）的测试。

合成一律用 mock：不联网、不真的调用 edge-tts。
需要 ffmpeg 的用例在缺 ffmpeg 时跳过。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

pytest.importorskip("numpy")
import numpy as np  # noqa: E402

import mux_srt_narration as mux  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="需要系统 ffmpeg/ffprobe")

SRT = """1
00:00:00,000 --> 00:00:03,000
第一句旁白

2
00:00:03,000 --> 00:00:06,000
第二句旁白

3
00:00:06,000 --> 00:00:09,000
第三句旁白
"""


# ──────────────────────────────────────────────────────────────
# 时间轴规划（纯函数）
# ──────────────────────────────────────────────────────────────
def _cues(*spans: tuple[int, int]) -> list[dict]:
    return [
        {"index": i + 1, "startMs": s, "endMs": e, "durMs": e - s, "text": f"第{i + 1}句"}
        for i, (s, e) in enumerate(spans)
    ]


def test_plan_windows_aligns_to_cue_starts():
    cues = _cues((0, 3000), (3000, 6000), (6000, 9000))
    windows = mux.plan_windows(cues, total_ms=9500, gap_ms=120)
    assert [start for start, _ in windows] == [0, 3000, 6000]
    # 前两条窗口 = 到下一条起点为止再留呼吸
    assert windows[0][1] == 3000 - 120
    assert windows[1][1] == 3000 - 120
    # 末条以视频总时长收尾
    assert windows[2][1] == 9500 - 6000 - 120


def test_plan_windows_never_overlaps_even_if_srt_does():
    """SRT 里两条重叠时，窗口右界仍取下一条起点，保证旁白不打架。"""
    cues = _cues((0, 8000), (3000, 9000))     # 第一条明显盖住第二条
    windows = mux.plan_windows(cues, total_ms=12000, gap_ms=100)
    first_start, first_window = windows[0]
    assert first_start + first_window <= cues[1]["startMs"]


def test_plan_windows_dense_cues_never_cross_next_start():
    cues = _cues((0, 100), (150, 400))
    windows = mux.plan_windows(cues, total_ms=1000)
    assert windows[0][1] == 30
    assert windows[0][0] + windows[0][1] < cues[1]["startMs"]


def test_plan_windows_uses_video_length_for_last_cue():
    cues = _cues((0, 2000))
    (_, window), = mux.plan_windows(cues, total_ms=30000, gap_ms=0)
    assert window == 30000


# ──────────────────────────────────────────────────────────────
# 变速（纯函数）
# ──────────────────────────────────────────────────────────────
def test_fit_factor_only_when_over_window():
    assert mux.fit_factor(2000, 3000) is None
    assert mux.fit_factor(3000, 3000) is None
    assert mux.fit_factor(4500, 3000) == pytest.approx(1.5)


def test_atempo_filters_single_and_chained():
    assert mux.atempo_filters(1.0) == []
    assert mux.atempo_filters(1.5) == ["atempo=1.500000"]
    chained = mux.atempo_filters(3.0)
    assert len(chained) == 2, "超过 2 倍要串联，避免单级 atempo 音质崩坏"
    product = 1.0
    for stage in chained:
        product *= float(stage.split("=")[1])
    assert product == pytest.approx(3.0, rel=1e-4)


def test_atempo_filters_extreme_factor_stays_bounded():
    filters = mux.atempo_filters(9.0)
    per_stage = float(filters[0].split("=")[1])
    assert per_stage <= mux.MAX_ATEMPO + 1e-6


# ──────────────────────────────────────────────────────────────
# 铺轨
# ──────────────────────────────────────────────────────────────
def test_build_bed_places_clips_at_offsets():
    rate = mux.SAMPLE_RATE
    clip = np.full(rate // 2, 1000, dtype=np.int16)      # 0.5s
    bed = mux.build_bed([(1000, clip), (3000, clip)], total_ms=5000)
    assert len(bed) == 5 * rate
    assert bed[: rate].max() == 0                        # 第 1 秒静音
    assert bed[rate: rate + rate // 2].max() == 1000     # 1.0s 起有声
    assert bed[3 * rate: 3 * rate + rate // 2].max() == 1000
    assert bed[4 * rate:].max() == 0                     # 尾部静音


def test_build_bed_truncates_clip_past_end():
    rate = mux.SAMPLE_RATE
    clip = np.full(2 * rate, 500, dtype=np.int16)
    bed = mux.build_bed([(1500, clip)], total_ms=2000)
    assert len(bed) == 2 * rate                          # 不因为音频超长而变长


# ──────────────────────────────────────────────────────────────
# 失败路径
# ──────────────────────────────────────────────────────────────
def test_missing_edge_tts_reports_clearly(monkeypatch, tmp_path):
    """未安装 edge-tts 时要给出可执行的提示，而不是 ImportError 栈。"""
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "edge_tts":
            raise ImportError("No module named 'edge_tts'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with pytest.raises(mux.NarrationError) as excinfo:
        mux.synthesize_cue("你好", mux.DEFAULT_VOICE, tmp_path / "a.mp3")
    assert "edge-tts" in str(excinfo.value)
    assert "prepare_env" in str(excinfo.value)


def test_network_failure_is_wrapped(monkeypatch, tmp_path):
    """没网时 edge-tts 会抛各种异常，必须收口成中文说明 + 非零退出。"""
    class Boom:
        def __init__(self, *a, **k):
            pass

        async def save(self, *a, **k):
            raise OSError("Temporary failure in name resolution")

    fake = type(sys)("edge_tts")
    fake.Communicate = Boom
    monkeypatch.setitem(sys.modules, "edge_tts", fake)

    with pytest.raises(mux.NarrationError) as excinfo:
        mux.synthesize_cue("你好", mux.DEFAULT_VOICE, tmp_path / "a.mp3")
    message = str(excinfo.value)
    assert "edge-tts 合成失败" in message and "联网" in message


def test_cli_returns_nonzero_on_narration_error(tmp_path, capsys):
    srt = tmp_path / "a.srt"
    srt.write_text(SRT, encoding="utf-8")
    code = mux.main([
        "--srt", str(srt), "--video", str(tmp_path / "missing.mp4"),
        "--output", str(tmp_path / "out.mp4"),
    ])
    assert code == 1
    assert "找不到视频" in capsys.readouterr().err


def test_refuses_to_overwrite_input_video(tmp_path):
    srt = tmp_path / "a.srt"
    srt.write_text(SRT, encoding="utf-8")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    with pytest.raises(mux.NarrationError, match="不能和输入视频相同"):
        mux.mux_narration(srt, video, video)


def test_empty_srt_is_rejected(tmp_path):
    srt = tmp_path / "empty.srt"
    srt.write_text("\n", encoding="utf-8")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    with pytest.raises(mux.NarrationError, match="没有可用文本"):
        mux.mux_narration(srt, video, tmp_path / "o.mp4")


# ──────────────────────────────────────────────────────────────
# 端到端（mock 合成 + 真 ffmpeg）
# ──────────────────────────────────────────────────────────────
def _silent_video(path: Path, seconds: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"color=c=0xF5EBD7:s=320x180:d={seconds}:r=10",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


def _voiced_runs(pcm: "np.ndarray", rate: int, block_ms: int = 20) -> list[float]:
    """用短时包络找出有声段的时长（正弦波频繁过零，不能按单采样判静音）。"""
    block = max(1, int(rate * block_ms / 1000))
    trimmed = pcm[: len(pcm) // block * block].reshape(-1, block)
    loud = np.abs(trimmed).max(axis=1) > 100
    runs, count = [], 0
    for value in loud:
        if value:
            count += 1
        elif count:
            runs.append(count * block / rate)
            count = 0
    if count:
        runs.append(count * block / rate)
    return runs


def _fake_tts(duration_s: float):
    """用 ffmpeg 生成一段正弦波当作"合成好的旁白"，避免联网。"""
    def synth(text: str, voice: str, out_path: Path, rate: str = "+0%") -> None:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"sine=frequency=440:duration={duration_s}:sample_rate={mux.SAMPLE_RATE}",
             "-c:a", "libmp3lame", str(out_path)],
            check=True, capture_output=True,
        )
    return synth


@needs_ffmpeg
def test_end_to_end_mux_adds_audio_track(tmp_path, monkeypatch):
    srt = tmp_path / "a.srt"
    srt.write_text(SRT, encoding="utf-8")
    video = tmp_path / "silent.mp4"
    _silent_video(video, 9.5)
    assert not mux.has_audio_stream(video)

    monkeypatch.setattr(mux, "synthesize_cue", _fake_tts(1.5))
    out = tmp_path / "narrated.mp4"
    mux.mux_narration(srt, video, out, keep_wav=True)

    assert out.exists()
    assert mux.has_audio_stream(out), "输出必须带音轨"
    # 时长对齐：音频铺到视频长度，mux 后总时长不应明显变化
    assert abs(mux.probe_duration_ms(out) - mux.probe_duration_ms(video)) < 400
    wav = out.with_name(out.stem + ".narration.wav")
    assert wav.exists(), "--keep-wav 应保留旁白轨"
    with wave.open(str(wav)) as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == mux.SAMPLE_RATE


@needs_ffmpeg
def test_keep_wav_creates_missing_output_parent(tmp_path, monkeypatch):
    srt = tmp_path / "a.srt"
    srt.write_text(SRT, encoding="utf-8")
    video = tmp_path / "silent.mp4"
    _silent_video(video, 9.5)
    monkeypatch.setattr(mux, "synthesize_cue", _fake_tts(0.4))
    out = tmp_path / "new" / "nested" / "narrated.mp4"
    mux.mux_narration(srt, video, out, keep_wav=True)
    assert out.exists()
    assert out.with_name(out.stem + ".narration.wav").exists()


@needs_ffmpeg
def test_extend_mode_refuses_to_squeeze_and_asks_for_longer_picture(tmp_path, monkeypatch):
    """
    默认 extend：语音塞不进画面时**不加速**，而是报错要求加长画面。
    卡点应该由作画时长决定，不能把人声催快。
    """
    srt = tmp_path / "a.srt"
    srt.write_text(SRT, encoding="utf-8")
    video = tmp_path / "silent.mp4"
    _silent_video(video, 9.5)
    monkeypatch.setattr(mux, "synthesize_cue", _fake_tts(6.0))   # 窗口只有 2.88s

    with pytest.raises(mux.NarrationError) as excinfo:
        mux.mux_narration(srt, video, tmp_path / "narrated.mp4")
    message = str(excinfo.value)
    assert "旁白比画面长" in message
    assert "sceneDurationMs" in message and "durationMs" in message
    assert "--fit atempo" in message, "要告诉用户强行塞进的开关在哪"


@needs_ffmpeg
def test_extend_mode_keeps_speed_and_pushes_later_cues(tmp_path, monkeypatch, capsys):
    """语音略超窗但视频够长：自然说完 + 后面顺延，语速一点不改。"""
    srt = tmp_path / "a.srt"
    srt.write_text(SRT, encoding="utf-8")
    video = tmp_path / "silent.mp4"
    _silent_video(video, 20.0)                 # 画面留足
    monkeypatch.setattr(mux, "synthesize_cue", _fake_tts(4.0))   # 窗口 2.88s

    out = tmp_path / "narrated.mp4"
    mux.mux_narration(srt, video, out, keep_wav=True)
    printed = capsys.readouterr().out
    assert "加速 ×" not in printed, "extend 模式不允许改语速"
    assert "顺延 +" in printed and "超窗 +" in printed

    wav = out.with_name(out.stem + ".narration.wav")
    with wave.open(str(wav)) as handle:
        pcm = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)
    # 每段语音仍是完整 4s（未被压缩）：用 20ms 包络找出有声段
    runs = _voiced_runs(pcm, mux.SAMPLE_RATE)
    assert runs, "应有有声段"
    assert max(runs) == pytest.approx(4.0, abs=0.3), f"语音时长被改动了: {runs}"
    assert len(runs) == 3, f"三条字幕应有三段语音: {runs}"


@needs_ffmpeg
def test_atempo_mode_squeezes_only_when_asked(tmp_path, monkeypatch, capsys):
    """显式 --fit atempo 时才压回窗口内，且逐条告警、绝不越到下一条。"""
    srt = tmp_path / "a.srt"
    srt.write_text(SRT, encoding="utf-8")
    video = tmp_path / "silent.mp4"
    _silent_video(video, 9.5)

    monkeypatch.setattr(mux, "synthesize_cue", _fake_tts(6.0))   # 窗口只有 2.88s
    out = tmp_path / "narrated.mp4"
    mux.mux_narration(srt, video, out, keep_wav=True, fit_mode="atempo")

    printed = capsys.readouterr().out
    assert "加速 ×" in printed
    assert "模式 atempo" in printed

    wav = out.with_name(out.stem + ".narration.wav")
    with wave.open(str(wav)) as handle:
        pcm = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)
    rate = mux.SAMPLE_RATE
    # 每条字幕起点前的 60ms 必须是静音（说明上一条没有越界）
    for start_ms in (3000, 6000):
        tail = pcm[int((start_ms - 60) * rate / 1000):int(start_ms * rate / 1000)]
        assert np.abs(tail).max() == 0, f"{start_ms}ms 前应有呼吸间隔，实测有声音"


@needs_ffmpeg
def test_no_burned_in_subtitles_video_stream_is_copied(tmp_path, monkeypatch):
    """视频流必须原样 copy：帧数与编码不变，画面不会被烧字幕。"""
    srt = tmp_path / "a.srt"
    srt.write_text(SRT, encoding="utf-8")
    video = tmp_path / "silent.mp4"
    _silent_video(video, 9.5)
    monkeypatch.setattr(mux, "synthesize_cue", _fake_tts(1.0))
    out = tmp_path / "narrated.mp4"
    mux.mux_narration(srt, video, out)

    def frames(path: Path) -> str:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries", "stream=nb_read_frames,codec_name,width,height",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True,
        )
        return result.stdout.strip()

    assert frames(out) == frames(video)


# ──────────────────────────────────────────────────────────────
# 文档：第 8 步必须存在且写清约束
# ──────────────────────────────────────────────────────────────
def test_skill_documents_step_eight():
    import re

    skill = (REPO / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"\n8\. \*\*(.*?)(?=\n## )", skill, re.S)
    assert match, "工作流程要有第 8 步"
    step = match.group(0)
    assert "mux_srt_narration.py" in step
    assert "retime_srt.py" in step, "第 8 步要先把字幕对齐到成片真实时间线"
    assert "等待用户确认" in step, "第 8 步也要保留确认关卡"
    assert "不烧录字幕" in step
    assert "--fit extend" in step and "不改语速" in step
    assert "edge-tts" in skill and "zh-CN-YunxiNeural" in skill
    assert "Piper" not in skill and "piper" not in skill, "旁白只用 edge-tts"


def test_skill_forbids_atempo_as_the_default_cadence_fix():
    """卡点靠画面时长解决，不靠加速人声——文档必须把这条写死。"""
    skill = (REPO / "SKILL.md").read_text(encoding="utf-8")
    assert "不要**用加速凑" in skill or "**而不是**把人声催快" in skill
    assert "只有用户明确要求" in skill and "--fit atempo" in skill


def test_readme_and_requirements_mention_edge_tts():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "mux_srt_narration.py" in readme and "edge-tts" in readme
    requirements = (REPO / "requirements.txt").read_text(encoding="utf-8")
    assert "edge-tts" in requirements
    # 不钉死小版本：只允许大版本上界
    line = next(l for l in requirements.splitlines() if l.startswith("edge-tts"))
    assert "==" not in line, f"不要钉死小版本: {line}"


def test_prepare_env_installs_edge_tts():
    prepare = (REPO / "scripts" / "prepare_env.py").read_text(encoding="utf-8")
    assert '"edge_tts": "edge-tts"' in prepare, "prepare_env 的依赖探测要包含 edge_tts"
