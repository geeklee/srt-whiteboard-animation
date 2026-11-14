#!/usr/bin/env python3
"""单元测试：旧排序兼容、显式区域顺序、显式笔画路径、边界。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import draw_order as d


def _el(eid, seq, start, **extra):
    el = {
        "id": eid,
        "label": eid,
        "sequence": seq,
        "region": {"x": 0, "y": 0, "width": 10, "height": 10},
        "reveal": {"startMs": start, "durationMs": 1000, "direction": "top_to_bottom"},
    }
    el.update(extra)
    return el


def _ann(*elements, **scene):
    data = {
        "canvas": {"width": 100, "height": 100},
        "elements": list(elements),
    }
    data.update(scene)
    return data


class LegacyOrderTests(unittest.TestCase):
    def test_default_sorts_by_start_ms_not_file_or_sequence(self):
        ann = _ann(_el("a", 1, 3000), _el("b", 2, 100), _el("c", 3, 2000))
        ordered, warnings = d.ordered_elements(ann)
        self.assertEqual([e["id"] for e in ordered], ["b", "c", "a"])
        self.assertEqual(warnings, [])

    def test_old_annotation_without_new_fields_unchanged(self):
        # 与 examples 结构相同：无 elementOrder / strokePaths
        ann = _ann(
            _el("left", 1, 300),
            _el("center", 2, 3000),
            _el("right", 3, 5700),
        )
        ordered, warnings = d.ordered_elements(ann)
        self.assertEqual([e["id"] for e in ordered], ["left", "center", "right"])
        self.assertEqual(warnings, [])
        self.assertFalse(d.has_explicit_stroke_paths(ordered[0]))
        explicit, strokes, w = d.parse_stroke_paths(ordered[0])
        self.assertFalse(explicit)
        self.assertEqual(strokes, [])
        self.assertEqual(w, [])


class ElementOrderTests(unittest.TestCase):
    def test_element_order_overrides_start_ms(self):
        ann = _ann(
            _el("left", 1, 100),
            _el("right", 2, 2000),
            elementOrder=["right", "left"],
        )
        ordered, warnings = d.ordered_elements(ann)
        self.assertEqual([e["id"] for e in ordered], ["right", "left"])
        self.assertEqual(warnings, [])

    def test_order_by_sequence_when_start_ms_conflicts(self):
        # startMs 与 sequence 相反
        ann = _ann(
            _el("late-seq", 2, 100),
            _el("early-seq", 1, 5000),
            orderBy="sequence",
        )
        ordered, _ = d.ordered_elements(ann)
        self.assertEqual([e["id"] for e in ordered], ["early-seq", "late-seq"])

    def test_element_order_wins_over_order_by_sequence(self):
        ann = _ann(
            _el("a", 1, 100),
            _el("b", 2, 200),
            elementOrder=["b", "a"],
            orderBy="sequence",
        )
        ordered, _ = d.ordered_elements(ann)
        self.assertEqual([e["id"] for e in ordered], ["b", "a"])

    def test_unknown_duplicate_and_missing_ids(self):
        ann = _ann(
            _el("a", 1, 300),
            _el("b", 2, 100),
            _el("c", 3, 200),
            elementOrder=["ghost", "c", "c", "a"],
        )
        ordered, warnings = d.ordered_elements(ann)
        self.assertEqual([e["id"] for e in ordered], ["c", "a", "b"])
        text = " ".join(warnings)
        self.assertIn("ghost", text)
        self.assertIn("重复", text)
        self.assertIn("b", text)

    def test_empty_or_invalid_element_order_falls_back(self):
        ann = _ann(_el("a", 1, 200), _el("b", 2, 100), elementOrder=[])
        ordered, _ = d.ordered_elements(ann)
        self.assertEqual([e["id"] for e in ordered], ["b", "a"])
        ann2 = _ann(_el("a", 1, 200), _el("b", 2, 100), elementOrder="a,b")
        ordered2, warnings = d.ordered_elements(ann2)
        self.assertEqual([e["id"] for e in ordered2], ["b", "a"])
        self.assertTrue(warnings)

    def test_unknown_order_by_falls_back_to_start_ms(self):
        ann = _ann(_el("a", 1, 200), _el("b", 2, 100), orderBy="mystery")
        ordered, warnings = d.ordered_elements(ann)
        self.assertEqual([e["id"] for e in ordered], ["b", "a"])
        self.assertTrue(any("orderBy" in w for w in warnings))


class StrokePathTests(unittest.TestCase):
    def test_directed_paths_keep_point_order_and_pen_lifts(self):
        el = _el(
            "z",
            1,
            0,
            strokePaths=[
                [[0, 0], [10, 0], [0, 10], [10, 10]],  # Z 形，从左上起笔
                [[20, 20], [30, 20]],
            ],
        )
        explicit, strokes, warnings = d.parse_stroke_paths(el, sx=2, sy=3)
        self.assertTrue(explicit)
        self.assertEqual(warnings, [])
        self.assertEqual(strokes[0][0], (0, 0))
        self.assertEqual(strokes[0][-1], (20, 30))
        self.assertEqual(strokes[1][0], (40, 60))
        samples, lifts = d.plan_stroke_samples(strokes, sample_step=100)
        # 步长大时至少保留起止点；第二条起点是抬笔
        self.assertEqual(samples[0], (0, 0))
        self.assertIn(len(strokes[0]) and samples.index(strokes[1][0]), lifts or {samples.index(strokes[1][0])})
        self.assertTrue(any(s == strokes[1][0] for s in samples))
        lift_index = next(i for i, p in enumerate(samples) if p == strokes[1][0] and i > 0)
        self.assertIn(lift_index, lifts)

    def test_reverse_direction_is_different_path(self):
        fwd = [[0, 0], [10, 0], [10, 10]]
        el_a = _el("a", 1, 0, strokePaths=[fwd])
        el_b = _el("b", 1, 0, strokePaths=[list(reversed(fwd))])
        _, a, _ = d.parse_stroke_paths(el_a)
        _, b, _ = d.parse_stroke_paths(el_b)
        self.assertEqual(a[0][0], (0, 0))
        self.assertEqual(a[0][-1], (10, 10))
        self.assertEqual(b[0][0], (10, 10))
        self.assertEqual(b[0][-1], (0, 0))

    def test_missing_key_is_legacy_null_key_is_legacy(self):
        self.assertFalse(d.has_explicit_stroke_paths(_el("a", 1, 0)))
        el = _el("a", 1, 0)
        el["strokePaths"] = None
        self.assertFalse(d.has_explicit_stroke_paths(el))
        explicit, strokes, _ = d.parse_stroke_paths(el)
        self.assertFalse(explicit)
        self.assertEqual(strokes, [])

    def test_empty_paths_are_explicit_not_legacy(self):
        el = _el("a", 1, 0, strokePaths=[])
        explicit, strokes, _ = d.parse_stroke_paths(el)
        self.assertTrue(explicit)
        self.assertEqual(strokes, [])

    def test_invalid_entries_skipped_without_fallback_flag(self):
        el = _el(
            "a",
            1,
            0,
            strokePaths=["bad", {"points": [[1, 2], ["x", 3]]}, [[0, 0]], {"foo": 1}],
        )
        explicit, strokes, warnings = d.parse_stroke_paths(el)
        self.assertTrue(explicit)
        # 非法点被跳过，折线中剩余合法点仍保留；单点折线也保留
        self.assertEqual(strokes, [[(1, 2)], [(0, 0)]])
        self.assertTrue(warnings)

    def test_wrong_type_explicit_empty(self):
        el = _el("a", 1, 0, strokePaths={"points": [[0, 0], [1, 1]]})
        explicit, strokes, warnings = d.parse_stroke_paths(el)
        self.assertTrue(explicit)
        self.assertEqual(strokes, [])
        self.assertTrue(warnings)

    def test_object_points_form_accepted(self):
        el = _el("a", 1, 0, strokePaths=[{"points": [{"x": 1.4, "y": 2.6}, [3, 4]]}])
        explicit, strokes, _ = d.parse_stroke_paths(el)
        self.assertTrue(explicit)
        self.assertEqual(strokes, [[(1, 3), (3, 4)]])


class AnnotationBoundaryTests(unittest.TestCase):
    def test_missing_elements_and_canvas(self):
        self.assertTrue(d.annotation_errors({}))
        self.assertIn("elements", " ".join(d.annotation_errors({"canvas": {"width": 1, "height": 1}})))
        self.assertTrue(d.annotation_errors("nope"))

    def test_element_missing_region_or_timing(self):
        bad = {
            "canvas": {"width": 10, "height": 10},
            "elements": [{"id": "x", "reveal": {"startMs": 0}}],
        }
        errors = d.annotation_errors(bad)
        self.assertTrue(any("region" in e for e in errors))
        self.assertTrue(any("durationMs" in e for e in errors))

    def test_valid_minimal_annotation(self):
        self.assertEqual(d.annotation_errors(_ann(_el("a", 1, 0))), [])


class ReviewRegressionTests(unittest.TestCase):
    def test_corner_vertices_survive_large_sample_step(self):
        samples, _ = d.plan_stroke_samples([[(0, 0), (10, 0), (10, 10)]], sample_step=100)
        self.assertEqual(samples, [(0, 0), (10, 0), (10, 10)])

    def test_duplicate_element_ids_not_dropped(self):
        a, b = _el("same", 1, 0), _el("same", 2, 100)
        result, warnings = d.ordered_elements(_ann(a, b, elementOrder=["same"]))
        self.assertEqual(len(result), 2)
        self.assertIs(result[0], a)
        self.assertIs(result[1], b)
        self.assertTrue(warnings)

    def test_malformed_numeric_and_protected_fields_rejected(self):
        import copy
        valid = _ann(_el("a", 1, 0))
        changes = [("canvas", "width", float("nan")),
                   ("canvas", "height", "100"),
                   ("region", "x", None), ("region", "width", -1),
                   ("reveal", "durationMs", float("inf")),
                   ("reveal", "startMs", -1),
                   ("reveal", "protectedRegions", None),
                   ("reveal", "protectedRegions", [{"x": 0}])]
        for section, key, value in changes:
            with self.subTest(section=section, key=key, value=value):
                ann = copy.deepcopy(valid)
                target = ann["canvas"] if section == "canvas" else ann["elements"][0][section]
                target[key] = value
                self.assertTrue(d.annotation_errors(ann))


if __name__ == "__main__":
    unittest.main()
