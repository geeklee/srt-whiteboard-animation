"""标注校验（scripts/annotation_schema.py）的单元测试。"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from annotation_schema import (  # noqa: E402
    AnnotationError,
    ensure_valid,
    load_annotation,
    validate_annotation,
)

EXAMPLE = REPO / "examples" / "scene-01-monkey-mountain-banana.annotation.json"


@pytest.fixture
def good() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_annotation_is_valid(good):
    report = validate_annotation(good, image_size=(1672, 941))
    assert report.ok, report.errors
    assert report.warnings == []


def test_missing_canvas_is_error(good):
    del good["canvas"]
    report = validate_annotation(good)
    assert not report.ok
    assert any("canvas" in message for message in report.errors)


def test_missing_reveal_keys_are_errors(good):
    del good["elements"][1]["reveal"]["durationMs"]
    good["elements"][2].pop("reveal")
    report = validate_annotation(good, image_size=(1672, 941))
    assert not report.ok
    assert any("durationMs" in m for m in report.errors)
    assert any("reveal" in m for m in report.errors)


def test_region_outside_canvas_is_error(good):
    good["elements"][0]["region"]["width"] = 5000
    report = validate_annotation(good, image_size=(1672, 941))
    assert not report.ok
    assert any("超出画布" in m for m in report.errors)


def test_negative_start_and_zero_duration_are_errors(good):
    good["elements"][0]["reveal"]["startMs"] = -1
    good["elements"][1]["reveal"]["durationMs"] = 0
    report = validate_annotation(good, image_size=(1672, 941))
    assert len([m for m in report.errors if "startMs" in m or "durationMs" in m]) == 2


def test_protected_region_outside_canvas_is_error(good):
    good["elements"][0]["reveal"]["protectedRegions"] = [
        {"x": 1600, "y": 900, "width": 400, "height": 400}
    ]
    report = validate_annotation(good, image_size=(1672, 941))
    assert not report.ok
    assert any("protectedRegions[0]" in m for m in report.errors)


def test_aspect_ratio_mismatch_is_error_but_size_only_is_warning(good):
    distorted = validate_annotation(good, image_size=(941, 1672))
    assert not distorted.ok
    assert any("长宽比" in m for m in distorted.errors)

    scaled = copy.deepcopy(good)
    scaled["canvas"] = {"width": 836, "height": 470}          # 同比例的一半
    for element in scaled["elements"]:                        # 区域也跟着缩，避免越界
        for key in ("x", "y", "width", "height"):
            element["region"][key] //= 2
    report = validate_annotation(scaled, image_size=(1672, 941))
    assert report.ok, report.errors
    assert any("不一致" in w for w in report.warnings)


def test_sequence_order_mismatch_is_warning_not_error(good):
    good["elements"][0]["sequence"] = 3
    good["elements"][2]["sequence"] = 1
    report = validate_annotation(good, image_size=(1672, 941))
    assert report.ok
    assert any("sequence 顺序与 startMs 顺序不一致" in w for w in report.warnings)


def test_overlapping_time_windows_are_warning(good):
    good["elements"][2]["reveal"]["startMs"] = 3100      # 落在 center 的窗口内
    report = validate_annotation(good, image_size=(1672, 941))
    assert report.ok
    assert any("时间窗重叠" in w for w in report.warnings)


def test_bool_is_not_accepted_as_coordinate(good):
    good["elements"][0]["region"]["x"] = True
    report = validate_annotation(good, image_size=(1672, 941))
    assert not report.ok


def test_ensure_valid_raises_with_all_reasons(good):
    del good["canvas"]
    good["elements"][0]["reveal"]["startMs"] = -1
    with pytest.raises(AnnotationError) as excinfo:
        ensure_valid(good, source="x.json")
    message = str(excinfo.value)
    assert "canvas" in message and "startMs" in message


def test_load_annotation_errors_are_wrapped(tmp_path):
    with pytest.raises(AnnotationError):
        load_annotation(tmp_path / "nope.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(AnnotationError):
        load_annotation(broken)


def test_empty_elements_is_error(good):
    good["elements"] = []
    assert not validate_annotation(good).ok
