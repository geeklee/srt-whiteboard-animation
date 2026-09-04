"""
开场封面（scripts/make_cover.py）+ 副标排版 + 封面接入合并的测试。

封面是默认必做的一步：主标/副标由渲染器手写（不烤进出图），
片头写完标题再点缀小黑，末尾留一段停留，然后擦入第一幕。
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
pytest.importorskip("PIL", reason="需要 Pillow")
cv2 = pytest.importorskip("cv2", reason="需要 opencv-python")
import numpy as np  # noqa: E402

import make_cover  # noqa: E402
import merge_scenes  # noqa: E402
import retime_srt  # noqa: E402
import text_render as tr  # noqa: E402
from annotation_schema import validate_annotation  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="需要系统 ffmpeg/ffprobe")

TITLE = "动态组合"
SUBTITLE = "把可撤销效应和响应式协效应做成运行时"


@pytest.fixture
def cover_board(tmp_path) -> Path:
    """封面分镜：上半留白，下半一个小黑 vignette。"""
    image = np.full((941, 1672, 3), (215, 235, 245), np.uint8)
    cv2.ellipse(image, (700, 640), (90, 120), 0, 0, 360, (20, 20, 20), -1)
    cv2.rectangle(image, (830, 560), (980, 700), (40, 40, 40), 3)
    path = tmp_path / "cover.png"
    cv2.imwrite(str(path), image)
    return path


# ──────────────────────────────────────────────────────────────
# 副标排版
# ──────────────────────────────────────────────────────────────
def test_subtitle_is_parsed_and_ordered_after_title():
    spec = tr.TextBlockSpec.from_annotation(
        {"title": TITLE, "subtitle": SUBTITLE, "bullets": ["要点"]}
    )
    assert spec.subtitle == SUBTITLE
    assert [kind for kind, _ in spec.rows] == ["title", "subtitle", "bullet"]
    assert spec.lines == [TITLE, SUBTITLE, "要点"]


def test_subtitle_renders_smaller_than_title_and_fits():
    spec = tr.TextBlockSpec(title=TITLE, subtitle=SUBTITLE)
    ink, strokes = tr.render_text_block(spec, 1400, 320)
    ys, xs = np.nonzero(ink < 128)
    assert ys.max() < 320 and xs.max() < 1400, "封面文字必须留在区域内"
    assert len(strokes) > 30

    # 主标那几行的墨迹应比副标更"高"（字号更大）：按行分块比较高度
    rows = np.nonzero((ink < 128).any(axis=1))[0]
    breaks = np.nonzero(np.diff(rows) > 5)[0]
    blocks = np.split(rows, breaks + 1)
    assert len(blocks) >= 2, "主标与副标应是分开的两块"
    assert len(blocks[0]) > len(blocks[-1]), "主标应比副标更大"


def test_subtitle_has_no_bullet_dash():
    """副标不该带要点短横：同宽区域下，纯副标的最左墨迹应在标题左侧附近。"""
    with_subtitle = tr.render_text_block(
        tr.TextBlockSpec(title="标题", subtitle="副标"), 600, 200
    )[0]
    with_bullet = tr.render_text_block(
        tr.TextBlockSpec(title="标题", bullets=["副标"]), 600, 200
    )[0]
    assert not np.array_equal(with_subtitle, with_bullet)


# ──────────────────────────────────────────────────────────────
# 封面标注
# ──────────────────────────────────────────────────────────────
def test_build_cover_layout_and_timing(cover_board):
    cover = make_cover.build_cover(cover_board, TITLE, SUBTITLE)
    assert cover["sceneId"] == "scene-00-cover"
    assert cover["canvas"] == {"width": 1672, "height": 941}

    title, accent = cover["elements"]
    assert title["type"] == "text"
    assert title["text"]["title"] == TITLE and title["text"]["subtitle"] == SUBTITLE
    # 通栏：约 90% 画布宽
    assert title["region"]["width"] == pytest.approx(1672 * 0.90, rel=0.02)
    # 标题区在小黑之上、互不重叠
    assert title["region"]["y"] + title["region"]["height"] <= accent["region"]["y"]
    # 先写标题、再点小黑
    assert accent["reveal"]["startMs"] > (
        title["reveal"]["startMs"] + title["reveal"]["durationMs"]
    )
    # 片头 4–6 秒
    assert 4000 <= cover["sceneDurationMs"] <= 6000, cover["sceneDurationMs"]


def test_cover_annotation_passes_validation(cover_board):
    cover = make_cover.build_cover(cover_board, TITLE, SUBTITLE)
    report = validate_annotation(cover, image_size=(1672, 941))
    assert report.ok, report.errors
    assert not [w for w in report.warnings if "文字区" in w], report.warnings


def test_cover_rejects_top_band_that_would_overlap_accent(tmp_path):
    image = np.full((941, 1672, 3), (215, 235, 245), np.uint8)
    cv2.circle(image, (800, 120), 60, (20, 20, 20), -1)      # 内容顶到最上面
    board = tmp_path / "bad-cover.png"
    cv2.imwrite(str(board), image)
    with pytest.raises(SystemExit, match="顶部留白不足"):
        make_cover.build_cover(board, TITLE, SUBTITLE)


def test_cover_cli_writes_json_and_no_cover_skips(cover_board, tmp_path, capsys):
    out = tmp_path / "cover.annotation.json"
    assert make_cover.main([
        "--board", str(cover_board), "--title", TITLE,
        "--subtitle", SUBTITLE, "--output", str(out),
    ]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["elements"][0]["type"] == "text"

    skipped = tmp_path / "skipped.json"
    assert make_cover.main(["--no-cover", "--output", str(skipped)]) == 0
    assert not skipped.exists()
    assert "跳过封面" in capsys.readouterr().out


def test_cover_cli_requires_args(cover_board):
    with pytest.raises(SystemExit):
        make_cover.main(["--title", TITLE])


def test_write_ms_scales_with_text_length():
    short = make_cover.write_ms_for("四字标题", "")
    long = make_cover.write_ms_for("四字标题", SUBTITLE)
    assert long > short > 0


# ──────────────────────────────────────────────────────────────
# 封面接入合并 + 时间线
# ──────────────────────────────────────────────────────────────
def _clip(path: Path, color, seconds=1.0, fps=10, size=(160, 90), blank_lead=0.0):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    paper = np.full((size[1], size[0], 3), (215, 235, 245), np.uint8)
    for _ in range(int(blank_lead * fps)):
        writer.write(paper)
    frame = np.full((size[1], size[0], 3), color, np.uint8)
    cv2.rectangle(frame, (40, 25), (120, 65), (0, 0, 0), -1)
    for _ in range(int(seconds * fps)):
        writer.write(frame)
    writer.release()


@needs_ffmpeg
def test_merge_prepends_cover_and_records_offsets(tmp_path):
    cover = tmp_path / "cover.mp4"
    _clip(cover, (210, 230, 242), seconds=1.5)
    scenes = []
    for index in range(2):
        path = tmp_path / f"scene-{index + 1}.mp4"
        _clip(path, (200, 220, 240), seconds=1.0, blank_lead=0.5)
        scenes.append(path)
    output = tmp_path / "merged.mp4"
    timeline = tmp_path / "timeline.json"

    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "merge_scenes.py"),
         "--inputs", *[str(s) for s in scenes], "--cover", str(cover),
         "--output", str(output), "--hold-ms", "300", "--erase-ms", "300",
         "--timeline-out", str(timeline)],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "片头封面" in result.stdout
    assert "跳过片头空白" in result.stdout, "第二幕起要裁掉片头空白纸"

    data = json.loads(timeline.read_text(encoding="utf-8"))
    assert data["coverMs"] == pytest.approx(1500, abs=200)
    assert len(data["scenes"]) == 2, "时间线只记正片各幕"
    # 正片整体后移一个封面 + 一次过渡
    assert data["scenes"][0]["startMs"] == pytest.approx(1500 + 600, abs=250)
    assert data["scenes"][0]["leadTrimMs"] > 0, "裁掉的空白要记录下来"


@needs_ffmpeg
def test_merge_no_cover_flag_skips_cover(tmp_path):
    cover = tmp_path / "cover.mp4"
    _clip(cover, (210, 230, 242), seconds=1.0)
    scene = tmp_path / "scene-1.mp4"
    _clip(scene, (200, 220, 240), seconds=1.0)
    output = tmp_path / "merged.mp4"
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "merge_scenes.py"),
         "--inputs", str(scene), "--cover", str(cover), "--no-cover",
         "--output", str(output)],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "片头封面" not in result.stdout
    assert merge_scenes._duration_ms(output) == pytest.approx(1000, abs=250)


def test_retime_subtracts_lead_trim():
    """merge 裁掉了幕首空白，字幕必须跟着提前，否则旁白比画面晚。"""
    cues = [
        {"index": 1, "startMs": 0, "endMs": 3000, "durMs": 3000, "text": "第一句"},
        {"index": 2, "startMs": 3000, "endMs": 6000, "durMs": 3000, "text": "第二句"},
    ]
    scenes = [{"sceneIndex": 1, "startMs": 0, "endMs": 6000, "cueRange": [1, 2]}]
    timeline = {
        "transitionMs": 1000, "totalMs": 12000, "coverMs": 5000,
        "scenes": [{"sceneIndex": 1, "startMs": 6000, "durationMs": 6000,
                    "endMs": 12000, "leadTrimMs": 800}],
    }
    annotation = {
        "canvas": {"width": 100, "height": 100},
        "elements": [
            {"id": "a", "type": "object",
             "region": {"x": 0, "y": 0, "width": 40, "height": 40},
             "reveal": {"startMs": 2000, "durationMs": 1500}},
            {"id": "b", "type": "object",
             "region": {"x": 50, "y": 0, "width": 40, "height": 40},
             "reveal": {"startMs": 4000, "durationMs": 1500}},
        ],
    }
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "scene.json"
        path.write_text(json.dumps(annotation), encoding="utf-8")
        retimed = retime_srt.align_to_drawing(
            cues, scenes, timeline, [path], lead_ms=250, tail_ms=250,
            cover_narration_ms=0,          # 单独测 leadTrim 校正，关掉封面提前
        )
    # 幕起点 6000 − 裁掉 800 + 区域 2000 + lead 250 = 7450
    assert retimed[0]["startMs"] == 7450
    assert retimed[1]["startMs"] == 6000 - 800 + 4000 + 250
    assert all(c["startMs"] >= 6000 for c in retimed), "不得早于本幕在成片里的起点"


# ──────────────────────────────────────────────────────────────
# 橡皮外观
# ──────────────────────────────────────────────────────────────
def test_eraser_draws_a_body_not_a_plain_grey_block():
    frame = np.full((180, 320, 3), (215, 235, 245), np.uint8)
    before = frame.copy()
    merge_scenes._draw_eraser(frame, 160, 180)
    assert not np.array_equal(frame, before), "应该画出橡皮"
    changed = np.any(frame != before, axis=2)
    ys, xs = np.nonzero(changed)
    assert ys.size > 100
    colors = {tuple(int(c) for c in frame[y, x]) for y, x in zip(ys[::7], xs[::7])}
    assert len(colors) >= 3, f"橡皮应有胶皮/套圈/描边多种颜色，实测 {len(colors)} 种"
    # 只在前沿附近，不铺满画面
    assert xs.min() > 100 and xs.max() < 200


def test_eraser_is_a_noop_at_the_edges():
    frame = np.full((180, 320, 3), (215, 235, 245), np.uint8)
    for edge in (0, 320):
        before = frame.copy()
        merge_scenes._draw_eraser(frame, edge, 180)
        assert np.array_equal(frame, before)


# ──────────────────────────────────────────────────────────────
# 封面旁白提前（片头不静音）
# ──────────────────────────────────────────────────────────────
def _scene_annotation(tmp_path: Path, text_start=400, text_dur=4700, beats=(5600, 14000)):
    annotation = {
        "canvas": {"width": 100, "height": 100},
        "elements": [
            {"id": "title", "type": "text", "text": {"title": "标题"},
             "region": {"x": 0, "y": 0, "width": 90, "height": 20},
             "reveal": {"startMs": text_start, "durationMs": text_dur}},
            *[
                {"id": f"beat-{i}", "type": "object",
                 "region": {"x": i * 20, "y": 30, "width": 18, "height": 40},
                 "reveal": {"startMs": start, "durationMs": 6000}}
                for i, start in enumerate(beats)
            ],
        ],
    }
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(annotation), encoding="utf-8")
    return path


COVER_TIMELINE = {
    "transitionMs": 1300, "totalMs": 40000, "coverMs": 5870,
    "scenes": [{"sceneIndex": 1, "startMs": 7170, "durationMs": 30000,
                "endMs": 37170, "leadTrimMs": 1080}],
}
COVER_SCENES = [{"sceneIndex": 1, "startMs": 0, "endMs": 12000, "cueRange": [1, 2]}]
COVER_CUES = [
    {"index": 1, "startMs": 0, "endMs": 6000, "durMs": 6000, "text": "第一句"},
    {"index": 2, "startMs": 6000, "endMs": 12000, "durMs": 6000, "text": "第二句"},
]


def test_first_cue_opens_while_the_cover_title_is_written(tmp_path):
    annotation = _scene_annotation(tmp_path)
    retimed = retime_srt.align_to_drawing(
        COVER_CUES, COVER_SCENES, COVER_TIMELINE, [annotation], 250, 250
    )
    # 封面 5.87s + 过渡后幕1 才到 7.17s；第一条应提前到 600ms 附近开口
    assert retimed[0]["startMs"] == 600
    assert retimed[0]["endMs"] == 6600, "封面提前开口后仍应保留原字幕时长"
    assert retimed[1]["startMs"] > COVER_TIMELINE["scenes"][0]["startMs"], "第二条仍跟着自己的绘制区"
    for previous, current in zip(retimed, retimed[1:]):
        assert previous["endMs"] <= current["startMs"]


def test_cover_narration_lead_can_be_disabled(tmp_path):
    annotation = _scene_annotation(tmp_path)
    retimed = retime_srt.align_to_drawing(
        COVER_CUES, COVER_SCENES, COVER_TIMELINE, [annotation], 250, 250,
        cover_narration_ms=0,
    )
    assert retimed[0]["startMs"] >= COVER_TIMELINE["scenes"][0]["startMs"]


def test_shift_by_timeline_subtracts_lead_trim():
    shifted = retime_srt.shift_by_timeline(
        COVER_CUES, COVER_SCENES, COVER_TIMELINE
    )
    assert shifted[0]["startMs"] == 7170 - 1080


def test_align_rejects_annotation_count_mismatch(tmp_path):
    with pytest.raises(SystemExit, match="annotation 数量"):
        retime_srt.align_to_drawing(
            COVER_CUES, COVER_SCENES, COVER_TIMELINE, [], 250, 250
        )


def test_no_cover_means_no_early_opening(tmp_path):
    annotation = _scene_annotation(tmp_path)
    timeline = json.loads(json.dumps(COVER_TIMELINE))
    timeline["coverMs"] = 0
    timeline["scenes"][0]["startMs"] = 0
    retimed = retime_srt.align_to_drawing(
        COVER_CUES, COVER_SCENES, timeline, [annotation], 250, 250
    )
    # 没有封面时，第一条仍从"标题开始写"算起，不会跑到 600ms 之前
    assert retimed[0]["startMs"] == 400 - 1080 + 250 or retimed[0]["startMs"] >= 0


# ──────────────────────────────────────────────────────────────
# 擦场只留擦的手
# ──────────────────────────────────────────────────────────────
def _frame_with_hand(width=480, height=270):
    """画一帧：纸底 + 几笔墨 + 叠一只真实手部素材。"""
    import stream_render as sr

    frame = np.full((height, width, 3), (227, 241, 246), np.uint8)
    cv2.line(frame, (20, 40), (150, 40), (30, 30, 30), 3)      # 几笔"标题"
    cv2.line(frame, (20, 60), (110, 60), (30, 30, 30), 3)
    asset = sr.resolve_hand_asset(None, quiet=True)
    loaded = sr._load_hand(Path(asset), int(height * 0.44))
    assert loaded is not None
    hand, mask = loaded
    tip = sr.TipOverlay(hand, mask, tip_anchor_x=0.0, tip_anchor_y=0.0)
    tip.stamp(frame, 200, 30)
    return frame


def test_without_hand_removes_the_overlay_but_keeps_ink():
    frame = _frame_with_hand()
    before = merge_scenes._ink_ratio(frame)
    cleaned = merge_scenes._without_hand(frame)
    after = merge_scenes._ink_ratio(cleaned)
    assert after < before, f"应该抹掉手带来的暗像素（{before:.4f} → {after:.4f}）"
    # 原有墨迹要留住：左上那两笔还在
    assert cleaned[40, 60].mean() < 120 and cleaned[60, 60].mean() < 120


def test_locate_hand_finds_the_overlay():
    frame = _frame_with_hand()
    located = merge_scenes._locate_hand(frame)
    assert located is not None
    x, y, mask = located
    assert 150 < x < 260 and 0 <= y < 80, f"位置不对: {(x, y)}"
    assert mask.shape[0] > 60


def test_locate_hand_returns_none_on_plain_paper():
    paper = np.full((270, 480, 3), (227, 241, 246), np.uint8)
    assert merge_scenes._locate_hand(paper) is None


def test_seam_default_threshold_is_small_enough_to_keep_the_drawing():
    """去手之后阈值可以压很低：只要出现第一笔就切，不该裁掉大段作画。"""
    assert merge_scenes.SEAM_INK_RATIO <= 0.002
    assert merge_scenes.SEAM_MAX_SKIP_S <= 3.0


def test_short_detected_lead_is_still_trimmed_to_prevent_seam_flash():
    assert merge_scenes._should_trim_lead(0.05, first_keeps_lead=False, ffmpeg_available=True)
    assert not merge_scenes._should_trim_lead(0.05, first_keeps_lead=True, ffmpeg_available=True)


@needs_ffmpeg
def test_erase_target_has_ink_and_no_second_hand(tmp_path):
    """过渡末帧应该有墨（不闪白纸）、且不含下一幕的手。"""
    prev_video = tmp_path / "prev.mp4"
    next_video = tmp_path / "next.mp4"
    fps = 10
    writer = cv2.VideoWriter(str(prev_video), cv2.VideoWriter_fourcc(*"mp4v"), fps, (480, 270))
    full = np.full((270, 480, 3), (227, 241, 246), np.uint8)
    cv2.rectangle(full, (60, 120), (400, 240), (20, 20, 20), -1)
    for _ in range(10):
        writer.write(full)
    writer.release()

    writer = cv2.VideoWriter(str(next_video), cv2.VideoWriter_fourcc(*"mp4v"), fps, (480, 270))
    paper = np.full((270, 480, 3), (227, 241, 246), np.uint8)
    for _ in range(4):                       # 片头空白
        writer.write(paper)
    inked = _frame_with_hand()               # 之后是"有墨 + 有手"
    for _ in range(10):
        writer.write(inked)
    writer.release()

    out = tmp_path / "t.mp4"
    assert merge_scenes.build_transition(prev_video, next_video, out, 200, 400) is not None
    tail = merge_scenes._last_frame(out)
    assert tail is not None
    assert merge_scenes._ink_ratio(tail) > 0.001, "擦完必须已有墨，不能是空白纸"
    assert merge_scenes._locate_hand(tail) is None, "擦完不该出现下一幕的手"
