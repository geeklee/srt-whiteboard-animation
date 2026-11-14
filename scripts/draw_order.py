#!/usr/bin/env python3
"""
显式区域顺序与定向笔画路径（可选、向后兼容）。

区域按序（elementOrder / orderBy）只决定「先揭示哪一块」以及后续区域
从允许掩码中扣除的顺序；它不是真实笔顺。

逐笔路径（strokePaths）才是成片落墨与笔尖共用的定向轨迹。handPath
仍只服务预览台矩形代理，本模块不读取它。

规则：
  - 无 elementOrder 且无 orderBy=sequence：按 reveal.startMs 排序（旧行为）。
  - elementOrder 为非空 id 列表：按该列表排；未知 id 忽略；未列出的元素
    按 startMs 追加在后；重复 id 只取首次。
  - orderBy=sequence：仅在没有有效 elementOrder 时，按 sequence 再 startMs。
  - 元素缺少 strokePaths 或值为 null：该区走旧的 grid/skeleton 自动路径。
  - 元素带有 strokePaths 键（包括 []）：显式模式，空/非法路径不回退自动路径。
"""
from __future__ import annotations

import math
from typing import Any, Iterable


def _start_ms(element: dict) -> float:
    reveal = element.get("reveal") or {}
    try:
        return float(reveal.get("startMs", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _sequence(element: dict) -> float:
    try:
        return float(element.get("sequence", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _element_id(element: dict) -> str | None:
    value = element.get("id")
    if value is None:
        return None
    text = str(value)
    return text if text else None


def ordered_elements(annotation: dict) -> tuple[list[dict], list[str]]:
    """返回按绘制顺序排列的元素副本引用，以及警告。不修改原列表顺序。"""
    warnings: list[str] = []
    raw = annotation.get("elements")
    if not isinstance(raw, list):
        return [], ["elements 不是数组"]
    elements = [e for e in raw if isinstance(e, dict)]
    if len(elements) != len(raw):
        warnings.append("已忽略非对象的 elements 项")

    order_ids = annotation.get("elementOrder")
    if isinstance(order_ids, list) and len(order_ids) > 0:
        by_id: dict[str, dict] = {}
        for element in elements:
            eid = _element_id(element)
            if eid and eid not in by_id:
                by_id[eid] = element
            elif eid:
                warnings.append(f"elements 重复 id: {eid}，elementOrder 仅匹配首项")
        used: set[str] = set()
        ordered: list[dict] = []
        for item in order_ids:
            eid = str(item) if item is not None else ""
            if not eid:
                warnings.append("elementOrder 含空 id，已忽略")
                continue
            if eid in used:
                warnings.append(f"elementOrder 重复 id 已忽略: {eid}")
                continue
            if eid not in by_id:
                warnings.append(f"elementOrder 未知 id 已忽略: {eid}")
                continue
            ordered.append(by_id[eid])
            used.add(eid)
        selected = {id(e) for e in ordered}
        leftover = [e for e in elements if id(e) not in selected]
        leftover.sort(key=_start_ms)
        if leftover:
            warnings.append(
                "elementOrder 未列出 "
                + ", ".join(_element_id(e) or "?" for e in leftover)
                + "，已按 startMs 追加"
            )
            ordered.extend(leftover)
        return ordered, warnings

    if order_ids not in (None, [], ()):
        warnings.append("elementOrder 不是非空数组，已回退默认排序")

    order_by = annotation.get("orderBy") or "startMs"
    if order_by not in ("startMs", "sequence"):
        warnings.append(f"未知 orderBy={order_by!r}，已回退 startMs")
        order_by = "startMs"
    if order_by == "sequence":
        return sorted(elements, key=lambda e: (_sequence(e), _start_ms(e))), warnings
    return sorted(elements, key=_start_ms), warnings


def has_explicit_stroke_paths(element: dict) -> bool:
    """键存在且不是 null 视为显式模式（包括空数组）。"""
    return "strokePaths" in element and element["strokePaths"] is not None


def parse_stroke_paths(
    element: dict,
    sx: float = 1.0,
    sy: float = 1.0,
) -> tuple[bool, list[list[tuple[int, int]]], list[str]]:
    """
    解析元素的 strokePaths。

    返回 (explicit, strokes, warnings)。
    explicit 为 False 时调用方应使用 grid/skeleton 自动路径。
    strokes 为画布坐标已乘 sx/sy 后的整数点折线；单点折线保留为落点。
    """
    warnings: list[str] = []
    label = _element_id(element) or element.get("label") or "?"
    if not has_explicit_stroke_paths(element):
        return False, [], warnings

    raw = element["strokePaths"]
    if not isinstance(raw, list):
        warnings.append(f"{label}: strokePaths 不是数组，按空路径处理（不回退自动路径）")
        return True, [], warnings

    strokes: list[list[tuple[int, int]]] = []
    for index, item in enumerate(raw):
        points = _coerce_polyline(item, sx, sy, warnings, f"{label} 第 {index + 1} 条")
        if points:
            strokes.append(points)
    return True, strokes, warnings


def _coerce_point(value: Any) -> tuple[float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError, OverflowError):
            return None
    if isinstance(value, dict) and "x" in value and "y" in value:
        try:
            return float(value["x"]), float(value["y"])
        except (TypeError, ValueError, OverflowError):
            return None
    return None


def _coerce_polyline(
    item: Any,
    sx: float,
    sy: float,
    warnings: list[str],
    where: str,
) -> list[tuple[int, int]] | None:
    raw_points = item
    if isinstance(item, dict) and "points" in item:
        raw_points = item["points"]
    if not isinstance(raw_points, (list, tuple)):
        warnings.append(f"{where}: 不是点列，已跳过")
        return None
    points: list[tuple[int, int]] = []
    for value in raw_points:
        parsed = _coerce_point(value)
        if parsed is None:
            warnings.append(f"{where}: 非法点 {value!r}，已跳过该点")
            continue
        x, y = parsed
        if not math.isfinite(x) or not math.isfinite(y):
            warnings.append(f"{where}: 非有限坐标，已跳过该点")
            continue
        points.append((int(round(x * sx)), int(round(y * sy))))
    if not points:
        warnings.append(f"{where}: 无有效点，已跳过")
        return None
    return points


def plan_stroke_samples(
    strokes: list[list[tuple[int, int]]],
    sample_step: float = 2.0,
) -> tuple[list[tuple[int, int]], set[int]]:
    """
    把折线重采样为笔尖/揭墨共用的采样点，并标记抬笔下标（新折线的起点）。
    抬笔下标表示「不要把前一点与该点连成揭墨线段」。
    """
    samples: list[tuple[int, int]] = []
    pen_lifts: set[int] = set()
    step = sample_step if sample_step and sample_step > 0 else 2.0
    for stroke_index, stroke in enumerate(strokes):
        if not stroke:
            continue
        if stroke_index > 0 and samples:
            pen_lifts.add(len(samples))
        if len(stroke) == 1:
            samples.append(stroke[0])
            continue
        samples.extend(_resample(stroke, step))
    return samples, pen_lifts


def _resample(points: list[tuple[int, int]], spacing: float) -> list[tuple[int, int]]:
    if len(points) == 1:
        return [points[0]]
    # Preserve every authored vertex: global sampling can shortcut corners.
    out = [points[0]]
    for a, b in zip(points, points[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, math.ceil(length / spacing))
        for i in range(1, n + 1):
            out.append((round(a[0] + (b[0] - a[0]) * i / n),
                        round(a[1] + (b[1] - a[1]) * i / n)))
    return out


def annotation_errors(annotation: Any) -> list[str]:
    """硬错误（应中止渲染）。空 elements 也视为硬错误，与旧 CLI 一致。"""
    if not isinstance(annotation, dict):
        return ["标注不是对象"]
    errors: list[str] = []
    def number(value, *, minimum=None, positive=False):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        try:
            if not math.isfinite(value):
                return False
        except OverflowError:
            return False
        return (minimum is None or value >= minimum) and (not positive or value > 0)

    def rect_errors(region, where):
        if not isinstance(region, dict):
            errors.append(f"{where} 不是矩形对象")
            return
        for key in ("x", "y", "width", "height"):
            if not number(region.get(key), minimum=0 if key in ("width", "height") else None):
                errors.append(f"{where}.{key} 无效")

    canvas = annotation.get("canvas")
    if not isinstance(canvas, dict):
        errors.append("缺少 canvas")
    else:
        for key in ("width", "height"):
            if not number(canvas.get(key), positive=True):
                errors.append(f"canvas.{key} 无效")
    if "sceneDurationMs" in annotation and not number(annotation["sceneDurationMs"], minimum=0):
        errors.append("sceneDurationMs 无效")
    elements = annotation.get("elements")
    if not isinstance(elements, list) or not elements:
        errors.append("标注中没有 elements")
        return errors
    for i, element in enumerate(elements):
        where = f"elements[{i}]"
        if not isinstance(element, dict):
            errors.append(f"{where} 不是对象")
            continue
        rect_errors(element.get("region"), f"{where}.region")
        reveal = element.get("reveal")
        if not isinstance(reveal, dict):
            errors.append(f"{where} 缺少 reveal")
        else:
            for key in ("startMs", "durationMs"):
                if not number(reveal.get(key), minimum=0):
                    errors.append(f"{where}.reveal.{key} 无效")
            protected = reveal.get("protectedRegions", [])
            if not isinstance(protected, list):
                errors.append(f"{where}.reveal.protectedRegions 不是数组")
            else:
                for j, region in enumerate(protected):
                    rect_errors(region, f"{where}.reveal.protectedRegions[{j}]")
    return errors
