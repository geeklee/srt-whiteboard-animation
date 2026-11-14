#!/usr/bin/env python3
"""渲染级测试：旧 grid 模式、显式区域顺序、显式笔顺、无墨/空路径/非法标注。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2
import numpy as np

import render_stream_whiteboard as rsw
import stream_render as sr


PAPER = (215, 235, 245)  # BGR of approx #F5EBD7
INK = (20, 20, 20)


def _paper(w=200, h=120) -> np.ndarray:
    img = np.empty((h, w, 3), dtype=np.uint8)
    img[:] = PAPER
    return img


def _cfg(**kw) -> sr.Config:
    base = dict(
        fps=10,
        cap_long_edge=200,
        grid_edge=10,
        sample_step=2,
        ink_weight=2,
        color_weight=1,
        ink_path_mode="grid",
        color_fill="brush",  # 上色沿轨迹，避免 contour 把整区一下子扫开
        match_bg=False,
        brush_radius=4,
    )
    base.update(kw)
    return sr.Config(**base)


def _ann(elements, w=200, h=120, **extra) -> dict:
    data = {
        "sceneId": "test",
        "canvas": {"width": w, "height": h},
        "sceneDurationMs": extra.pop("sceneDurationMs", 1500),
        "elements": elements,
    }
    data.update(extra)
    return data


def _el(eid, x, y, w, h, start, dur=600, **extra):
    el = {
        "id": eid,
        "label": eid,
        "sequence": extra.pop("sequence", 1),
        "region": {"x": x, "y": y, "width": w, "height": h},
        "reveal": {
            "direction": "top_to_bottom",
            "startMs": start,
            "durationMs": dur,
            "maskPaddingPx": 0,
            "protectedRegions": [],
        },
    }
    el.update(extra)
    return el


def _render(image: np.ndarray, annotation: dict, tmp: Path, **cfg_kw):
    cfg = _cfg(**cfg_kw)
    raw = tmp / "raw.mp4"
    renderer = rsw.RegionStreamRenderer(image, annotation, cfg, hand_png=None, bare_tip=True)
    renderer.render_to(raw, annotation.get("sceneDurationMs") or 1500)
    cap = cv2.VideoCapture(str(raw))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return renderer, frames


def _is_inked(frame: np.ndarray, x: int, y: int, radius: int = 3) -> bool:
    h, w = frame.shape[:2]
    y0, y1 = max(0, y - radius), min(h, y + radius + 1)
    x0, x1 = max(0, x - radius), min(w, x + radius + 1)
    patch = frame[y0:y1, x0:x1]
    # 细线在邻域里占比很小，用最小值判断是否已揭墨
    return float(patch.min()) < 80


class LegacyRenderTests(unittest.TestCase):
    def test_legacy_grid_draws_in_start_ms_order(self):
        img = _paper()
        cv2.line(img, (20, 60), (70, 60), INK, 6)
        cv2.line(img, (135, 60), (185, 60), INK, 6)
        ann = _ann([
            _el("left", 10, 20, 70, 80, start=50, dur=500),
            _el("right", 120, 20, 70, 80, start=700, dur=500),
        ], sceneDurationMs=1600)
        with tempfile.TemporaryDirectory() as td:
            renderer, frames = _render(img, ann, Path(td))
            self.assertGreater(len(frames), 8)
            # 按 startMs：先左后右。找第一帧出现明显墨迹的位置。
            first_left = first_right = None
            for i, frame in enumerate(frames):
                if first_left is None and _is_inked(frame, 40, 60):
                    first_left = i
                if first_right is None and _is_inked(frame, 155, 60):
                    first_right = i
            self.assertIsNotNone(first_left)
            self.assertIsNotNone(first_right)
            self.assertLess(first_left, first_right)

    def test_no_ink_region_does_not_crash(self):
        img = _paper()  # 全纸，无墨
        ann = _ann([_el("empty", 10, 10, 80, 80, start=0, dur=400)], sceneDurationMs=900)
        with tempfile.TemporaryDirectory() as td:
            renderer, frames = _render(img, ann, Path(td))
            self.assertGreater(len(frames), 3)
            ids = {e["elementId"] for e in renderer.tip_log}
            self.assertIn("empty", ids)


class ExplicitOrderRenderTests(unittest.TestCase):
    def test_element_order_draws_right_region_first(self):
        img = _paper()
        cv2.line(img, (20, 60), (70, 60), INK, 6)
        cv2.line(img, (135, 60), (185, 60), INK, 6)
        # startMs 仍是左早右晚，但 elementOrder 要求先右后左
        ann = _ann(
            [
                _el("left", 10, 20, 70, 80, start=50, dur=500),
                _el("right", 120, 20, 70, 80, start=700, dur=500),
            ],
            elementOrder=["right", "left"],
            sceneDurationMs=1600,
        )
        with tempfile.TemporaryDirectory() as td:
            renderer, frames = _render(img, ann, Path(td))
            first_left = first_right = None
            for i, frame in enumerate(frames):
                if first_left is None and _is_inked(frame, 40, 60):
                    first_left = i
                if first_right is None and _is_inked(frame, 155, 60):
                    first_right = i
            self.assertIsNotNone(first_left)
            self.assertIsNotNone(first_right)
            self.assertLess(first_right, first_left)
            # 笔尖日志的 ink 阶段也应先 right
            ink = [e for e in renderer.tip_log if e.get("phase") == "ink" and e.get("tip")]
            self.assertTrue(ink)
            self.assertEqual(ink[0]["elementId"], "right")


class ExplicitStrokeRenderTests(unittest.TestCase):
    def test_pen_and_ink_follow_right_to_left_path(self):
        img = _paper()
        # 一条横线。显式笔顺从右走到左，与常见的左起自动路径相反。
        cv2.line(img, (20, 60), (180, 60), INK, 3)
        path = [[180, 60], [20, 60]]
        ann = _ann(
            [_el("bar", 10, 40, 180, 40, start=0, dur=900, strokePaths=[path])],
            sceneDurationMs=1600,
        )
        with tempfile.TemporaryDirectory() as td:
            renderer, frames = _render(img, ann, Path(td))
            ink_idx = [i for i, e in enumerate(renderer.tip_log) if e.get("phase") == "ink" and e.get("tip")]
            self.assertGreater(len(ink_idx), 4)
            first = renderer.tip_log[ink_idx[0]]
            mid = renderer.tip_log[ink_idx[len(ink_idx) // 3]]
            last = renderer.tip_log[ink_idx[-1]]
            self.assertEqual(first["elementId"], "bar")
            # 笔尖从右向左
            self.assertGreater(first["x"], last["x"])
            self.assertGreater(first["x"], 120)
            self.assertLess(last["x"], 80)
            # 中段：右侧已揭墨，左侧仍是纸（证明不是整区一下子露出）
            mid_frame = frames[ink_idx[len(ink_idx) // 3]]
            self.assertTrue(_is_inked(mid_frame, first["x"], 60, radius=6))
            self.assertFalse(_is_inked(mid_frame, 30, 60, radius=4))
            # 笔尖落在已揭墨附近
            self.assertTrue(_is_inked(mid_frame, mid["x"], mid["y"], radius=8))

    def test_empty_stroke_paths_hold_without_auto_fallback(self):
        img = _paper()
        cv2.line(img, (20, 60), (180, 60), INK, 4)
        ann = _ann(
            [_el("bar", 10, 40, 180, 40, start=0, dur=600, strokePaths=[])],
            sceneDurationMs=800,
        )
        with tempfile.TemporaryDirectory() as td:
            renderer, frames = _render(img, ann, Path(td), color_fill="brush")
            ink_idx = [i for i, e in enumerate(renderer.tip_log) if e.get("phase") == "ink"]
            self.assertTrue(ink_idx)
            # 起笔段不应沿自动网格揭墨
            for i in ink_idx:
                self.assertFalse(_is_inked(frames[i], 100, 60, radius=3), msg=f"frame {i} leaked ink")


class ReviewRegressionTests(unittest.TestCase):
    def test_explicit_omitted_ink_stays_hidden_through_color_and_hold(self):
        for color in ("brush", "contour-wipe"):
            with self.subTest(color=color), tempfile.TemporaryDirectory() as td:
                img = _paper()
                cv2.line(img, (20, 60), (180, 60), INK, 3)
                # Omit the far half, plus nearby parallel ink inside brush radius.
                cv2.line(img, (20, 70), (180, 70), INK, 3)
                ann = _ann([_el("bar", 0, 0, 200, 120, 0, 900,
                                  strokePaths=[[[20, 60], [80, 60]]])])
                _, frames = _render(img, ann, Path(td), color_fill=color, brush_radius=24)
                self.assertTrue(_is_inked(frames[-1], 40, 60))
                for frame in frames:
                    self.assertFalse(_is_inked(frame, 150, 60, 1))
                    self.assertFalse(_is_inked(frame, 40, 70, 1))

    def test_empty_explicit_paths_never_reveal_even_in_default_contour_and_hold(self):
        with tempfile.TemporaryDirectory() as td:
            img = _paper()
            cv2.line(img, (20, 60), (180, 60), INK, 4)
            ann = _ann([_el("bar", 0, 0, 200, 120, 0, strokePaths=[])])
            _, frames = _render(img, ann, Path(td), color_fill="contour-wipe")
            self.assertTrue(frames)
            self.assertTrue(all(not _is_inked(f, 100, 60) for f in frames))

    def test_lifted_single_points_stamp_without_connecting(self):
        # Bypass video compression to verify exact dot/lift geometry.
        img = _paper()
        cv2.line(img, (20, 60), (180, 60), INK, 3)
        ann = _ann([_el("dots", 0, 0, 200, 120, 0, strokePaths=[])])
        r = rsw.RegionStreamRenderer(img, ann, _cfg(), None, True)
        frames = []
        class Writer:
            def write(self, frame):
                frames.append(frame.copy())
        allowed = np.ones((120, 200), bool)
        r._lay_ink(Writer(), 2, [(20, 60), (180, 60)], {1}, allowed)
        self.assertTrue(_is_inked(frames[-1], 180, 60, 1))
        self.assertFalse(_is_inked(frames[-1], 100, 60, 1))

    def test_one_frame_phase_consumes_whole_path_not_just_endpoint(self):
        img = _paper()
        cv2.line(img, (20, 60), (180, 60), INK, 3)
        r = rsw.RegionStreamRenderer(img, _ann([_el("a", 0, 0, 200, 120, 0)]), _cfg(), None, True)
        class Writer:
            def write(self, frame):
                pass
        r._lay_ink(Writer(), 1, [(20, 60), (100, 60), (180, 60)], set(), np.ones((120, 200), bool))
        self.assertTrue(_is_inked(r.drawn, 100, 60))

    def test_reversed_schedule_respects_earliest_start_and_serializes(self):
        with tempfile.TemporaryDirectory() as td:
            img = _paper()
            cv2.line(img, (20, 60), (180, 60), INK, 4)
            ann = _ann([_el("left", 0, 0, 90, 120, 0, 600),
                        _el("right", 100, 0, 100, 120, 700, 600)],
                       elementOrder=["right", "left"], sceneDurationMs=1000)
            r, frames = _render(img, ann, Path(td))
            starts = {}
            for i, e in enumerate(r.tip_log):
                if e["tip"] and e["phase"] == "ink":
                    starts.setdefault(e["elementId"], i)
            self.assertEqual(starts, {"right": 7, "left": 13})
            self.assertEqual(len(frames), 24)  # extends past nominal 1000 ms, +500 hold

    def test_overlap_belongs_to_later_region_and_protection_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            img = _paper()
            cv2.line(img, (20, 60), (180, 60), INK, 3)
            a = _el("a", 0, 0, 150, 120, 0, 600, strokePaths=[[[20, 60], [140, 60]]])
            b = _el("b", 100, 0, 100, 120, 700, 600, strokePaths=[[[100, 60], [180, 60]]])
            b["reveal"]["protectedRegions"] = [{"x": 150, "y": 40, "width": 20, "height": 40}]
            r, frames = _render(img, _ann([a, b]), Path(td))
            self.assertTrue(_is_inked(frames[5], 40, 60))
            self.assertFalse(_is_inked(frames[5], 120, 60))
            self.assertTrue(_is_inked(frames[-1], 120, 60))
            self.assertFalse(_is_inked(frames[-1], 160, 60, 1))

    def test_mixed_explicit_and_auto_preserve_actual_result(self):
        for mode in ("grid", "skeleton"):
            for color in ("brush", "contour-wipe"):
                with self.subTest(mode=mode, color=color), tempfile.TemporaryDirectory() as td:
                    img = _paper()
                    cv2.line(img, (20, 40), (80, 40), INK, 3)  # explicit covered
                    cv2.line(img, (20, 70), (80, 70), INK, 3)  # explicit omitted
                    cv2.line(img, (120, 60), (180, 60), INK, 3)  # legacy auto
                    cv2.line(img, (20, 110), (180, 110), INK, 3)  # unannotated
                    ann = _ann([
                        _el("explicit", 0, 0, 100, 90, 0, 600,
                            strokePaths=[[[20, 40], [80, 40]]]),
                        _el("auto", 100, 0, 100, 90, 700, 600),
                    ], sceneDurationMs=1800)
                    r, frames = _render(img, ann, Path(td), ink_path_mode=mode, color_fill=color)
                    self.assertTrue(_is_inked(frames[-1], 50, 40))
                    self.assertTrue(_is_inked(frames[-1], 150, 60))
                    auto_ink = [i for i,e in enumerate(r.tip_log)
                                if e["elementId"] == "auto" and e["phase"] == "ink" and e["tip"]]
                    self.assertTrue(auto_ink)
                    self.assertTrue(_is_inked(frames[auto_ink[-1]], 150, 60))
                    for frame in frames:
                        self.assertFalse(_is_inked(frame, 50, 70))
                        self.assertFalse(_is_inked(frame, 150, 110))

    def test_legacy_skeleton_still_finishes_full_image(self):
        with tempfile.TemporaryDirectory() as td:
            img = _paper()
            cv2.line(img, (20, 60), (180, 60), INK, 3)
            r, frames = _render(img, _ann([_el("a", 0, 0, 200, 120, 0)]), Path(td), ink_path_mode="skeleton")
            self.assertTrue(any(e["tip"] for e in r.tip_log))
            self.assertTrue(_is_inked(frames[-1], 100, 60))


class InvalidAnnotationCliTests(unittest.TestCase):
    def test_cli_rejects_invalid_annotation(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            img_path = td / "a.png"
            cv2.imwrite(str(img_path), _paper())
            bad = td / "a.annotation.json"
            bad.write_text(json.dumps({"canvas": {"width": 200, "height": 120}, "elements": []}), encoding="utf-8")
            code = rsw.main([str(img_path), str(bad), str(td / "out.mp4"), "--bare-tip", "--fps", "8"])
            self.assertEqual(code, 1)

    def test_cli_rejects_nonfinite_geometry_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cv2.imwrite(str(td / "a.png"), _paper())
            ann = _ann([_el("a", float("nan"), 0, 100, 100, 0)])
            (td / "bad.json").write_text(json.dumps(ann))
            self.assertEqual(rsw.main([str(td / "a.png"), str(td / "bad.json"), str(td / "a.mp4")]), 1)
            self.assertFalse((td / "a.mp4").exists())

    def test_cli_rejects_non_utf8_annotation(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cv2.imwrite(str(td / "a.png"), _paper())
            (td / "bad.json").write_bytes(bytes([255, 254, 0]))
            self.assertEqual(rsw.main([str(td / "a.png"), str(td / "bad.json"), str(td / "a.mp4")]), 1)

    def test_cli_rejects_unreadable_json(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            img_path = td / "a.png"
            cv2.imwrite(str(img_path), _paper())
            bad = td / "a.annotation.json"
            bad.write_text("{not-json", encoding="utf-8")
            code = rsw.main([str(img_path), str(bad), str(td / "out.mp4"), "--bare-tip"])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
