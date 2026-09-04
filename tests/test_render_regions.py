"""
渲染器（scripts/render_stream_whiteboard.py）的回归测试。

重点是「允许掩码为空」的区域：过去 grid 模式下会直接抛
TypeError: _lay_ink() takes 6 positional arguments but 7 were given。
需要 cv2/numpy，缺依赖时整个模块跳过。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

pytest.importorskip("cv2", reason="需要 opencv-python：python scripts/prepare_env.py")
pytest.importorskip("numpy")

IMAGE = REPO / "examples" / "scene-01-monkey-mountain-banana.png"
ANNOTATION = REPO / "examples" / "scene-01-monkey-mountain-banana.annotation.json"
RENDERER = REPO / "scripts" / "render_stream_whiteboard.py"

# 小尺寸/低帧率：只验证行为，不追求画质
FAST = ["--cap-long-edge", "320", "--fps", "10"]


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RENDERER), *args],
        capture_output=True, text=True, timeout=600,
    )


@pytest.fixture
def annotation() -> dict:
    return json.loads(ANNOTATION.read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "scene.annotation.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_region_with_empty_allowed_mask_renders(tmp_path, annotation):
    """保护区盖满整个 region → 该区域无墨可落，但不能崩、也不能少写帧。"""
    first = annotation["elements"][0]
    first["reveal"]["protectedRegions"] = [dict(first["region"])]
    ann_path = _write(tmp_path, annotation)
    out = tmp_path / "out.mp4"

    result = _run([str(IMAGE), str(ann_path), str(out), *FAST])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TypeError" not in result.stdout + result.stderr
    assert out.exists() and out.stat().st_size > 0
    assert f"OUTPUT={out}" in result.stdout


def test_empty_mask_keeps_timeline_length(tmp_path, annotation):
    """空掩码区域仍要占满自己的时间片，否则后面的区域会整体提前。"""
    cv2 = pytest.importorskip("cv2")
    outputs = {}
    for name, mutate in (
        ("normal", lambda ann: ann),
        ("empty", _protect_first_region),
    ):
        data = json.loads(ANNOTATION.read_text(encoding="utf-8"))
        ann_path = tmp_path / f"{name}.annotation.json"
        ann_path.write_text(json.dumps(mutate(data), ensure_ascii=False), encoding="utf-8")
        out = tmp_path / f"{name}.mp4"
        assert _run([str(IMAGE), str(ann_path), str(out), *FAST]).returncode == 0
        capture = cv2.VideoCapture(str(out))
        outputs[name] = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        capture.release()

    assert outputs["empty"] == outputs["normal"], outputs


def _protect_first_region(annotation: dict) -> dict:
    first = annotation["elements"][0]
    first["reveal"]["protectedRegions"] = [dict(first["region"])]
    return annotation


def test_invalid_annotation_fails_before_encoding(tmp_path, annotation):
    """缺字段/越界要在编码前报清楚，而不是渲染到一半抛 KeyError。"""
    del annotation["canvas"]
    ann_path = _write(tmp_path, annotation)
    out = tmp_path / "never.mp4"

    result = _run([str(IMAGE), str(ann_path), str(out), *FAST])
    assert result.returncode == 1
    assert "标注校验失败" in result.stdout
    assert "canvas" in result.stdout
    assert "KeyError" not in result.stdout + result.stderr
    assert not out.exists()


def test_out_of_canvas_region_is_rejected(tmp_path, annotation):
    annotation["elements"][0]["region"]["x"] = 1600      # 右边越界
    ann_path = _write(tmp_path, annotation)
    result = _run([str(IMAGE), str(ann_path), str(tmp_path / "x.mp4"), *FAST])
    assert result.returncode == 1
    assert "超出画布" in result.stdout


def test_valid_annotation_renders_and_reports_duration(tmp_path, annotation):
    ann_path = _write(tmp_path, annotation)
    out = tmp_path / "ok.mp4"
    result = _run([str(IMAGE), str(ann_path), str(out), *FAST])
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.exists()
    # 成片不短于标注声明的时长（结尾还要留 0.5s 凝视）
    cv2 = pytest.importorskip("cv2")
    capture = cv2.VideoCapture(str(out))
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    assert frames / fps * 1000 >= annotation["sceneDurationMs"] - 100
