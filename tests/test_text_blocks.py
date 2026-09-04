"""
手写文字区（标题 + 要点）的测试：排版、校验、渲染。

文字区是用户点名的例外——画面里唯一允许出现的文字。它由渲染器排版书写，
所以这里要保证：不溢出区域、内容可校验、在成片里真的被写出来且不提前出现。
"""
from __future__ import annotations

import json
import subprocess
import sys
import inspect
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

pytest.importorskip("numpy")
pytest.importorskip("PIL", reason="需要 Pillow")
import numpy as np  # noqa: E402

import text_render as tr  # noqa: E402


def test_text_seed_does_not_use_process_salted_hash():
    source = inspect.getsource(tr.render_text_block)
    assert "hashlib.sha256" in source
    assert "seed = hash(" not in source
from annotation_schema import validate_annotation  # noqa: E402


# ──────────────────────────────────────────────────────────────
# 排版
# ──────────────────────────────────────────────────────────────
def test_spec_from_annotation_accepts_string_and_object():
    assert tr.TextBlockSpec.from_annotation("只有标题").title == "只有标题"
    spec = tr.TextBlockSpec.from_annotation(
        {"title": "标题", "bullets": ["一", "二"], "titleScale": 1.2}
    )
    assert spec.title == "标题" and spec.bullets == ["一", "二"]
    assert spec.title_scale == 1.2
    # 单条要点写成字符串也认
    assert tr.TextBlockSpec.from_annotation({"bullets": "就一条"}).bullets == ["就一条"]


def test_spec_rejects_wrong_type():
    with pytest.raises(ValueError):
        tr.TextBlockSpec.from_annotation(42)


def test_render_stays_inside_region():
    spec = tr.TextBlockSpec(
        title="动态装卸的困境",
        bullets=["装上容易，卸下清不干净", "只能整体重启", "攒下的状态全丢"],
    )
    ink, strokes = tr.render_text_block(spec, 620, 300)
    assert ink.shape == (300, 620)
    ys, xs = np.nonzero(ink < 128)
    assert ys.max() < 300 and xs.max() < 620, "文字必须留在区域内"
    assert len(strokes) > 20, "应产出书写笔序"


def test_long_content_is_shrunk_not_overflowed():
    """内容多到放不下时自动缩字号，绝不溢出。"""
    spec = tr.TextBlockSpec(
        title="很长的一个标题写满一行",
        bullets=["第一条要点写得相当长一些", "第二条要点也不短", "第三条", "第四条要点补充说明"],
    )
    ink, _ = tr.render_text_block(spec, 420, 200)
    ys, xs = np.nonzero(ink < 128)
    assert ys.max() < 200 and xs.max() < 420


def test_empty_spec_returns_blank_paper():
    ink, strokes = tr.render_text_block(tr.TextBlockSpec(), 200, 80)
    assert (ink == tr.PAPER).all()
    assert strokes == []


def test_tiny_region_is_rejected():
    with pytest.raises(ValueError):
        tr.render_text_block(tr.TextBlockSpec(title="x"), 4, 4)


def test_render_is_deterministic():
    spec = tr.TextBlockSpec(title="重复渲染", bullets=["应完全一致"])
    first, strokes_a = tr.render_text_block(spec, 300, 140)
    second, strokes_b = tr.render_text_block(spec, 300, 140)
    assert np.array_equal(first, second), "同样输入必须得到同样输出（抖动要可复现）"
    assert strokes_a == strokes_b


def test_jitter_zero_differs_from_jittered():
    plain = tr.render_text_block(tr.TextBlockSpec(title="抖动对比", jitter=0.0), 300, 120)[0]
    wobbly = tr.render_text_block(tr.TextBlockSpec(title="抖动对比", jitter=1.0), 300, 120)[0]
    assert not np.array_equal(plain, wobbly)


def test_strokes_to_samples_interpolates_and_marks_pen_lifts():
    strokes = [[(0, 0), (10, 0)], [(0, 20), (10, 20)]]
    samples, lifts = tr.strokes_to_samples(strokes, (100, 200), step=2)
    assert samples[0] == (100, 200), "应加上区域偏移"
    assert len(samples) > 8, "应插值成连续采样点"
    assert lifts, "两笔之间要标抬笔"
    assert all(100 <= x <= 110 and 200 <= y <= 220 for x, y in samples)


# ──────────────────────────────────────────────────────────────
# 校验
# ──────────────────────────────────────────────────────────────
def _annotation(text_value, **overrides) -> dict:
    element = {
        "id": "title", "label": "标题", "sequence": 1, "type": "text",
        "text": text_value,
        "region": {"x": 30, "y": 20, "width": 900, "height": 170},
        "reveal": {"startMs": 200, "durationMs": 4000, "protectedRegions": []},
    }
    element.update(overrides)
    return {
        "sceneId": "s", "canvas": {"width": 1000, "height": 600},
        "sceneDurationMs": 9000, "elements": [element],
    }


def test_text_element_requires_content():
    assert not validate_annotation(_annotation(None)).ok
    report = validate_annotation({**_annotation("x"), "elements": [
        {"id": "t", "type": "text", "region": {"x": 0, "y": 0, "width": 10, "height": 10},
         "reveal": {"startMs": 0, "durationMs": 100}},
    ]})
    assert not report.ok
    assert any("必须有 text 字段" in m for m in report.errors)


def test_text_element_rejects_empty_and_bad_types():
    assert not validate_annotation(_annotation("")).ok
    assert not validate_annotation(_annotation({"title": "", "bullets": []})).ok
    assert not validate_annotation(_annotation({"title": 5})).ok
    assert not validate_annotation(_annotation({"bullets": [1, 2]})).ok
    # 字符串型 bullets 是合法的（会被规整成一条）
    assert validate_annotation(_annotation({"title": "标题", "bullets": "只有一条"})).ok


def test_text_element_accepts_title_and_bullets():
    report = validate_annotation(_annotation({"title": "本幕标题", "bullets": ["要点一", "要点二"]}))
    assert report.ok, report.errors
    assert report.warnings == []


def test_long_title_and_many_bullets_only_warn():
    report = validate_annotation(_annotation({
        "title": "这是一个非常非常长的标题超过十四个字了",
        "bullets": ["一", "二", "三", "四", "五"],
    }))
    assert report.ok, report.errors
    assert any("标题" in w and "偏长" in w for w in report.warnings)
    assert any("偏多" in w for w in report.warnings)


def test_narrow_text_region_warns_about_title_size():
    """文字区不通栏 → 标题偏小，手机上读不清，必须提醒。"""
    annotation = _annotation({"title": "标题", "bullets": ["要点"]})
    annotation["elements"][0]["region"] = {"x": 10, "y": 10, "width": 400, "height": 170}
    report = validate_annotation(annotation)
    assert report.ok, report.errors
    assert any("通栏" in w for w in report.warnings)


def test_short_text_region_warns_about_output_height():
    annotation = _annotation({"title": "标题", "bullets": ["要点"]})
    annotation["elements"][0]["region"] = {"x": 30, "y": 20, "width": 900, "height": 90}
    report = validate_annotation(annotation)
    assert report.ok, report.errors
    assert any("1080 输出" in w for w in report.warnings)


def test_full_width_tall_text_region_has_no_geometry_warning():
    annotation = _annotation({"title": "标题", "bullets": ["要点"]})
    annotation["elements"][0]["region"] = {"x": 30, "y": 20, "width": 940, "height": 200}
    report = validate_annotation(annotation)
    assert report.ok and not [w for w in report.warnings if "文字区" in w]


def test_text_region_overlapping_later_region_warns():
    """文字区被后画的区域盖住会写不全——必须提醒。"""
    annotation = _annotation({"title": "标题", "bullets": ["要点"]})
    annotation["elements"].append({
        "id": "draw", "label": "隐喻", "sequence": 2, "type": "object",
        "region": {"x": 100, "y": 50, "width": 300, "height": 300},   # 与文字区相交
        "reveal": {"startMs": 5000, "durationMs": 3000, "protectedRegions": []},
    })
    report = validate_annotation(annotation)
    assert report.ok, report.errors
    assert any("重叠" in w and "写不全" in w for w in report.warnings)


def test_non_overlapping_text_region_has_no_warning():
    annotation = _annotation({"title": "标题", "bullets": ["要点"]})
    annotation["elements"].append({
        "id": "draw", "label": "隐喻", "sequence": 2, "type": "object",
        "region": {"x": 500, "y": 300, "width": 300, "height": 200},
        "reveal": {"startMs": 5000, "durationMs": 3000, "protectedRegions": []},
    })
    report = validate_annotation(annotation)
    assert report.ok and not [w for w in report.warnings if "重叠" in w]


# ──────────────────────────────────────────────────────────────
# 渲染（需要 cv2）
# ──────────────────────────────────────────────────────────────
@pytest.fixture
def scene(tmp_path):
    cv2 = pytest.importorskip("cv2", reason="需要 opencv-python")
    image = np.full((360, 640, 3), (215, 235, 245), np.uint8)      # 暖黄纸
    cv2.circle(image, (480, 250), 40, (20, 20, 20), -1)            # 右下角一个实心黑
    png = tmp_path / "scene.png"
    cv2.imwrite(str(png), image)
    annotation = {
        "sceneId": "scene-01",
        "canvas": {"width": 640, "height": 360},
        "sceneDurationMs": 9000,
        "elements": [
            {"id": "title", "label": "标题与要点", "sequence": 1, "type": "text",
             "narrativeRole": "本幕主旨", "subtitle": "标题",
             "text": {"title": "测试标题", "bullets": ["要点一", "要点二"]},
             "region": {"x": 20, "y": 20, "width": 340, "height": 120},
             "reveal": {"direction": "left_to_right", "startMs": 300,
                        "durationMs": 3000, "protectedRegions": []}},
            {"id": "blob", "label": "小黑", "sequence": 2, "type": "object",
             "narrativeRole": "动作", "subtitle": "小黑",
             "region": {"x": 400, "y": 180, "width": 200, "height": 160},
             "reveal": {"direction": "left_to_right", "startMs": 3600,
                        "durationMs": 3000, "protectedRegions": []}},
        ],
    }
    path = tmp_path / "scene.annotation.json"
    path.write_text(json.dumps(annotation, ensure_ascii=False), encoding="utf-8")
    return png, path


def _render(png: Path, annotation: Path, out: Path, extra: list[str] | None = None):
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "render_stream_whiteboard.py"),
         str(png), str(annotation), str(out),
         "--cap-long-edge", "320", "--fps", "10", "--bare-tip", *(extra or [])],
        capture_output=True, text=True, timeout=600,
    )


def test_text_block_is_written_into_the_video(scene, tmp_path):
    cv2 = pytest.importorskip("cv2")
    png, annotation = scene
    out = tmp_path / "out.mp4"
    result = _render(png, annotation, out)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "文字区 title" in result.stdout, "应报告文字区已排版"

    capture = cv2.VideoCapture(str(out))
    fps = capture.get(cv2.CAP_PROP_FPS)

    def dark_in_text_region(seconds: float) -> float:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(seconds * fps))
        ok, frame = capture.read()
        assert ok
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        # 文字区约占画面左上：x 20..360 / y 20..140（标注坐标 640x360）
        patch = gray[int(20 / 360 * h):int(140 / 360 * h), int(20 / 640 * w):int(360 / 640 * w)]
        return float((patch < 120).mean())

    before = dark_in_text_region(0.1)
    during = dark_in_text_region(2.0)
    after = dark_in_text_region(8.5)
    capture.release()

    assert before == 0.0, "startMs 之前文字不能出现"
    assert during > 0.005, f"书写中应能看到文字，实测 {during:.4f}"
    assert after > during, "写完后文字应更完整"


def test_text_only_scene_needs_no_drawing(scene, tmp_path):
    """一幕里只有文字区也要能渲染（例如纯标题页）。"""
    png, annotation_path = scene
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    annotation["elements"] = [annotation["elements"][0]]
    annotation["sceneDurationMs"] = 4000
    only_text = tmp_path / "only-text.annotation.json"
    only_text.write_text(json.dumps(annotation, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "only-text.mp4"
    result = _render(png, only_text, out)
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.exists()
