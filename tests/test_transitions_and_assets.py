"""
幕间过渡、时间线重定时、手部素材接管的测试。

要守住的行为：
  - 幕与幕之间不再硬切回空白画布（先停留 ≥0.5s，再擦除过渡）
  - 插了过渡之后字幕能跟着平移/对齐，不出现"旁白已开口、画布还空着"
  - 重画版手部素材一旦出现就自动接管，且绝不覆盖原文件
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2", reason="需要 opencv-python")
import numpy as np  # noqa: E402

import merge_scenes  # noqa: E402
import retime_srt  # noqa: E402
import stream_render as sr  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="需要系统 ffmpeg/ffprobe")


def _clip(path: Path, color: tuple[int, int, int], seconds: float = 1.0,
          fps: int = 10, size: tuple[int, int] = (160, 90), mark: bool = False) -> None:
    """造一段纯色片段；mark=True 时在中间画个方块，便于区分首尾帧。"""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    frame = np.full((size[1], size[0], 3), color, np.uint8)
    if mark:
        cv2.rectangle(frame, (60, 30), (100, 60), (0, 0, 0), -1)
    for _ in range(int(seconds * fps)):
        writer.write(frame)
    writer.release()


# ──────────────────────────────────────────────────────────────
# 过渡片段
# ──────────────────────────────────────────────────────────────
def test_transition_holds_then_erases(tmp_path):
    prev_video, next_video = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _clip(prev_video, (200, 220, 240), mark=True)     # 上一幕：有内容
    _clip(next_video, (215, 235, 245))                # 下一幕：干净纸面
    out = tmp_path / "t.mp4"

    built = merge_scenes.build_transition(prev_video, next_video, out, hold_ms=600, erase_ms=500)
    assert built is not None and built.exists()

    capture = cv2.VideoCapture(str(built))
    frames = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frames.append(frame)
    fps = capture.get(cv2.CAP_PROP_FPS)
    capture.release()

    duration = len(frames) / fps
    assert duration == pytest.approx(1.1, abs=0.25), f"应约等于 600+500ms，实测 {duration:.2f}s"

    # 前 0.5s 必须还是上一幕的完整画面（用户要求的停留下限）
    hold_frames = int(0.5 * fps)
    marker = frames[0][45, 80]
    for frame in frames[:hold_frames]:
        assert abs(int(frame[45, 80][0]) - int(marker[0])) < 12, "停留段画面不应变化"

    # 结尾必须已经擦成下一幕的起始纸面
    tail = frames[-1]
    assert abs(int(tail[45, 20][0]) - 215) < 20, f"擦除结束应露出下一幕纸面，实测 {tail[45, 20]}"


def test_transition_last_frame_matches_next_first_frame(tmp_path):
    """过渡末帧 = 下一幕首帧，拼接处才不会闪。"""
    prev_video, next_video = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _clip(prev_video, (100, 120, 140), mark=True)
    _clip(next_video, (215, 235, 245))
    out = tmp_path / "t.mp4"
    merge_scenes.build_transition(prev_video, next_video, out, hold_ms=200, erase_ms=300)

    last = merge_scenes._last_frame(out)
    expected = merge_scenes._first_frame(next_video)
    assert last is not None and expected is not None
    difference = np.abs(last.astype(int) - expected.astype(int)).mean()
    assert difference < 12, f"末帧与下一幕首帧差异过大: {difference:.1f}"


def test_transition_handles_size_mismatch(tmp_path):
    prev_video, next_video = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _clip(prev_video, (200, 220, 240), size=(160, 90))
    _clip(next_video, (215, 235, 245), size=(320, 180))
    out = tmp_path / "t.mp4"
    assert merge_scenes.build_transition(prev_video, next_video, out, 200, 200) is not None


@needs_ffmpeg
def test_merge_inserts_transitions_and_writes_timeline(tmp_path):
    scenes = []
    for index, color in enumerate([(200, 220, 240), (190, 210, 235), (180, 205, 230)]):
        path = tmp_path / f"scene-{index + 1}.mp4"
        _clip(path, color, seconds=1.0, mark=True)
        scenes.append(path)
    output = tmp_path / "merged.mp4"
    timeline = tmp_path / "timeline.json"

    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "merge_scenes.py"),
         "--inputs", *[str(s) for s in scenes], "--output", str(output),
         "--hold-ms", "600", "--erase-ms", "400", "--timeline-out", str(timeline)],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "过渡: 2 段" in result.stdout
    assert output.exists() and timeline.exists()

    data = json.loads(timeline.read_text(encoding="utf-8"))
    assert data["transitionMs"] == 1000
    starts = [s["startMs"] for s in data["scenes"]]
    # 每幕 1s + 每处过渡 1s → 0 / 2000 / 4000
    assert starts[0] == 0
    assert starts[1] == pytest.approx(2000, abs=150)
    assert starts[2] == pytest.approx(4000, abs=200)

    merged_ms = merge_scenes._duration_ms(output)
    assert merged_ms == pytest.approx(5000, abs=300), f"总长应含过渡，实测 {merged_ms:.0f}ms"


@needs_ffmpeg
def test_merge_without_transitions_when_disabled(tmp_path):
    scenes = []
    for index in range(2):
        path = tmp_path / f"s{index}.mp4"
        _clip(path, (200, 220, 240), seconds=1.0)
        scenes.append(path)
    output = tmp_path / "merged.mp4"
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "merge_scenes.py"),
         "--inputs", *[str(s) for s in scenes], "--output", str(output),
         "--hold-ms", "0", "--erase-ms", "0"],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "过渡" not in result.stdout
    assert merge_scenes._duration_ms(output) == pytest.approx(2000, abs=200)


# ──────────────────────────────────────────────────────────────
# SRT 重定时
# ──────────────────────────────────────────────────────────────
CUES = [
    {"index": 1, "startMs": 0, "endMs": 3000, "durMs": 3000, "text": "第一句"},
    {"index": 2, "startMs": 3000, "endMs": 6000, "durMs": 3000, "text": "第二句"},
    {"index": 3, "startMs": 6000, "endMs": 9000, "durMs": 3000, "text": "第三句"},
    {"index": 4, "startMs": 9000, "endMs": 12000, "durMs": 3000, "text": "第四句"},
]
SCENES = [
    {"sceneIndex": 1, "startMs": 0, "endMs": 6000, "cueRange": [1, 2]},
    {"sceneIndex": 2, "startMs": 6000, "endMs": 12000, "cueRange": [3, 4]},
]
TIMELINE = {
    "transitionMs": 1000, "totalMs": 13000,
    "scenes": [
        {"sceneIndex": 1, "startMs": 0, "durationMs": 6000, "endMs": 6000},
        {"sceneIndex": 2, "startMs": 7000, "durationMs": 6000, "endMs": 13000},
    ],
}


def test_shift_by_timeline_moves_later_scenes(tmp_path):
    retimed = retime_srt.shift_by_timeline(CUES, SCENES, TIMELINE)
    assert [c["startMs"] for c in retimed] == [0, 3000, 7000, 10000]
    assert [c["text"] for c in retimed] == ["第一句", "第二句", "第三句", "第四句"]


def test_align_to_drawing_puts_narration_after_the_pen_starts(tmp_path):
    """字幕起点 = 幕起点 + 区域起点 + lead，保证开口时画面已经在动。"""
    annotations = []
    for index, scene in enumerate(SCENES):
        annotation = {
            "canvas": {"width": 100, "height": 100},
            "elements": [
                # 文字区不参与配音对齐
                {"id": "title", "type": "text", "text": {"title": "标题"},
                 "region": {"x": 0, "y": 0, "width": 50, "height": 20},
                 "reveal": {"startMs": 200, "durationMs": 1500}},
                {"id": "a", "type": "object", "region": {"x": 0, "y": 30, "width": 40, "height": 40},
                 "reveal": {"startMs": 2000, "durationMs": 1800}},
                {"id": "b", "type": "object", "region": {"x": 50, "y": 30, "width": 40, "height": 40},
                 "reveal": {"startMs": 4000, "durationMs": 1800}},
            ],
        }
        path = tmp_path / f"scene-{index + 1}.json"
        path.write_text(json.dumps(annotation), encoding="utf-8")
        annotations.append(path)

    # --no-text-lead：幕首等标题写完，第 1 条对齐到绘制区 1
    strict = retime_srt.align_to_drawing(
        CUES, SCENES, TIMELINE, annotations, lead_ms=250, tail_ms=250, text_lead=False
    )
    assert len(strict) == 4
    # 第 1 幕：区域 2000/4000 → 2250 / 4250；第 2 幕整体 +7000
    assert [c["startMs"] for c in strict] == [2250, 4250, 9250, 11250]
    assert strict[0]["startMs"] > 0, "开场不能立刻说话——先落笔"
    for previous, current in zip(strict, strict[1:]):
        assert previous["endMs"] <= current["startMs"], "重定时后不能重叠"


def test_text_lead_removes_the_silent_gap_at_scene_start(tmp_path):
    """默认允许幕首字幕随标题书写开口：写标题也是在动笔，不该干等 5–6 秒。"""
    annotations = []
    for index in range(len(SCENES)):
        annotation = {
            "canvas": {"width": 100, "height": 100},
            "elements": [
                {"id": "title", "type": "text", "text": {"title": "标题"},
                 "region": {"x": 0, "y": 0, "width": 50, "height": 20},
                 "reveal": {"startMs": 400, "durationMs": 5000}},     # 标题写 5 秒
                {"id": "a", "type": "object", "region": {"x": 0, "y": 30, "width": 40, "height": 40},
                 "reveal": {"startMs": 5900, "durationMs": 1800}},
                {"id": "b", "type": "object", "region": {"x": 50, "y": 30, "width": 40, "height": 40},
                 "reveal": {"startMs": 8000, "durationMs": 1800}},
            ],
        }
        path = tmp_path / f"scene-{index + 1}.json"
        path.write_text(json.dumps(annotation), encoding="utf-8")
        annotations.append(path)

    lead = retime_srt.align_to_drawing(CUES, SCENES, TIMELINE, annotations, 250, 250)
    strict = retime_srt.align_to_drawing(
        CUES, SCENES, TIMELINE, annotations, 250, 250, text_lead=False
    )
    # 每幕第一条：提前到 标题起点 + lead = 650；老行为要等到 6150
    assert lead[0]["startMs"] == 650
    assert strict[0]["startMs"] == 6150
    assert lead[2]["startMs"] == 7000 + 650, "第 2 幕同样提前"
    # 幕首静音被消掉，且非首条仍跟着自己的绘制区
    assert lead[0]["startMs"] < strict[0]["startMs"] - 4000
    assert lead[1]["startMs"] == strict[1]["startMs"]
    for previous, current in zip(lead, lead[1:]):
        assert previous["endMs"] <= current["startMs"], "重定时后不能重叠"


def test_format_timestamp_and_write_srt(tmp_path):
    assert retime_srt.format_timestamp(0) == "00:00:00,000"
    assert retime_srt.format_timestamp(3_723_456) == "01:02:03,456"
    path = tmp_path / "out.srt"
    retime_srt.write_srt([{"startMs": 0, "endMs": 1500, "text": "你好"}], path)
    body = path.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,500" in body and "你好" in body

    sys.path.insert(0, str(REPO / "scripts"))
    from parse_srt import parse_srt
    assert parse_srt(body)[0]["endMs"] == 1500, "写出的 SRT 必须能被自己解析回来"


# ──────────────────────────────────────────────────────────────
# 手部素材接管
# ──────────────────────────────────────────────────────────────
def test_default_hand_is_used_when_no_v2(monkeypatch):
    monkeypatch.delenv(sr.ENV_HAND, raising=False)
    monkeypatch.setattr(sr, "HAND_V2_CANDIDATES", ())
    assert Path(sr.resolve_hand_asset(None)).name == "drawing-hand.png"
    assert Path(sr.resolve_hand_asset(sr.DEFAULT_HAND_PNG)).name == "drawing-hand.png"


def test_v2_takes_over_the_default(monkeypatch, tmp_path):
    """重画版一出现就自动接管，且原文件必须仍在、内容不变。"""
    monkeypatch.delenv(sr.ENV_HAND, raising=False)
    v2 = tmp_path / "drawing-hand-v2.png"
    v2.write_bytes(b"fake-v2")
    monkeypatch.setattr(sr, "HAND_V2_CANDIDATES", (v2,))

    before = sr.DEFAULT_HAND_PNG.read_bytes()
    assert Path(sr.resolve_hand_asset(str(sr.DEFAULT_HAND_PNG))) == v2
    assert Path(sr.resolve_hand_asset(None)) == v2
    assert sr.DEFAULT_HAND_PNG.exists()
    assert sr.DEFAULT_HAND_PNG.read_bytes() == before, "绝不能覆盖原手部素材"


def test_explicit_other_hand_wins_over_v2(monkeypatch, tmp_path):
    monkeypatch.delenv(sr.ENV_HAND, raising=False)
    v2 = tmp_path / "drawing-hand-v2.png"
    v2.write_bytes(b"fake-v2")
    monkeypatch.setattr(sr, "HAND_V2_CANDIDATES", (v2,))
    custom = tmp_path / "my-hand.png"
    custom.write_bytes(b"mine")
    assert Path(sr.resolve_hand_asset(str(custom))) == custom


def test_env_override_beats_everything(monkeypatch, tmp_path):
    v2 = tmp_path / "drawing-hand-v2.png"
    v2.write_bytes(b"fake-v2")
    monkeypatch.setattr(sr, "HAND_V2_CANDIDATES", (v2,))
    chosen = tmp_path / "env-hand.png"
    chosen.write_bytes(b"env")
    monkeypatch.setenv(sr.ENV_HAND, str(chosen))
    assert Path(sr.resolve_hand_asset(None)) == chosen


def test_env_override_missing_file_raises(monkeypatch):
    monkeypatch.setenv(sr.ENV_HAND, "/definitely/missing-hand.png")
    with pytest.raises(FileNotFoundError):
        sr.resolve_hand_asset(None)


def test_v2_candidate_paths_include_the_agreed_dropbox():
    """约定好的落地路径要在候选里，否则资产到了也接不上。"""
    paths = [str(p) for p in sr.HAND_V2_CANDIDATES]
    assert any(p.endswith("assets/drawing-hand-v2.png") for p in paths)
    assert any("/workspace/e2e-paper/assets/drawing-hand-v2.png" == p for p in paths)


# ──────────────────────────────────────────────────────────────
# 无 alpha 手部素材的抠图（重画版 v2 是黑底 RGB）
# ──────────────────────────────────────────────────────────────
def _hand_on_background(background: tuple[int, int, int], hole: bool = False) -> np.ndarray:
    """造一张"手"：纯色底 + 一块肤色多边形；hole=True 时在内部画一条近黑细线。"""
    image = np.full((200, 120, 3), background, np.uint8)
    # 用不规则多边形而不是矩形：裁到包围盒后仍应留出背景，才像真实素材
    polygon = np.array([[30, 20], [90, 45], [80, 170], [50, 150], [35, 90]], np.int32)
    cv2.fillPoly(image, [polygon], (150, 190, 230))
    if hole:
        cv2.line(image, (55, 60), (60, 140), (2, 2, 2), 3)      # 笔杆描边那种近黑线
    return image


def test_mask_from_black_background():
    """黑底素材若按"近白即背景"处理，整块黑底会被当成前景、盖出黑方块。"""
    image = _hand_on_background((0, 0, 0))
    mask = sr._mask_from_flat_background(image)
    assert mask[100, 60] == 255, "手的位置应是前景"
    assert mask[5, 5] == 0 and mask[195, 115] == 0, "黑底必须被判为背景"
    coverage = (mask > 0).mean()
    assert 0.15 < coverage < 0.6, f"覆盖率异常: {coverage:.2f}"


def test_mask_from_white_background_still_works():
    image = _hand_on_background((255, 255, 255))
    mask = sr._mask_from_flat_background(image)
    assert mask[100, 60] == 255
    assert mask[5, 5] == 0


def test_mask_fills_interior_holes():
    """笔杆描边、指节褶皱是近黑细线，留着就会透出画布。"""
    image = _hand_on_background((0, 0, 0), hole=True)
    mask = sr._mask_from_flat_background(image)
    assert mask[100, 57] == 255, "手内部的近黑线不应留成孔"


def test_mask_falls_back_when_corners_disagree():
    """四角颜色不一致（不像纯色底）时退回旧的近白判定，不乱抠。"""
    image = _hand_on_background((0, 0, 0))
    image[:20, :20] = (255, 255, 255)          # 一个角故意不同
    mask = sr._mask_from_flat_background(image)
    assert mask.shape == image.shape[:2]
    assert mask[100, 60] == 255


def test_load_hand_handles_rgb_black_background(tmp_path):
    path = tmp_path / "hand-v2.png"
    cv2.imwrite(str(path), _hand_on_background((0, 0, 0), hole=True))
    loaded = sr._load_hand(path, 200)
    assert loaded is not None
    hand, mask = loaded
    assert hand.shape[0] == 200 and mask.shape == hand.shape[:2]
    assert 0.2 < float((mask > 0.5).mean()) < 0.85, "蒙版既不能全空也不能全满"


@pytest.mark.skipif(
    not (Path("/workspace/e2e-paper/assets/drawing-hand-v2.png").exists()),
    reason="重画版手部素材尚未提供",
)
def test_real_v2_asset_masks_sanely():
    loaded = sr._load_hand(Path("/workspace/e2e-paper/assets/drawing-hand-v2.png"), 493)
    assert loaded is not None
    hand, mask = loaded
    coverage = float((mask > 0.5).mean())
    assert 0.2 < coverage < 0.7, f"v2 素材蒙版覆盖率 {coverage:.2f} 不合理（黑底没抠掉？）"
    assert hand.shape[0] == 493
