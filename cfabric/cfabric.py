#!/usr/bin/env python3
"""Render and independently validate cfabric-world JSON files.

SVG output uses only the Python standard library. PNG output is available when
Pillow is installed. The renderer accepts both seeded worlds from cfabric.exe
and seedless composed worlds from clyaers.py.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "cfabric-world/1"


class WorldValidationError(ValueError):
    """Raised when a world violates the cfabric schema or zero-collision rule."""


def load_world(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except OSError as exc:
        raise WorldValidationError(f"cannot read {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorldValidationError(f"invalid JSON in {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorldValidationError("world root must be a JSON object")
    return data


def write_world(path: str | Path, data: Mapping[str, Any]) -> None:
    target = Path(path)
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorldValidationError(message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _between(value: int, a: int, b: int) -> bool:
    return min(a, b) <= value <= max(a, b)


def _point_on_segment(point: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> bool:
    px, py = point
    ax, ay = a
    bx, by = b
    if ay == by:
        return py == ay and _between(px, ax, bx)
    if ax == bx:
        return px == ax and _between(py, ay, by)
    return False


def _segment_intersection(
    a1: tuple[int, int],
    a2: tuple[int, int],
    b1: tuple[int, int],
    b2: tuple[int, int],
) -> tuple[str, tuple[int, int] | None]:
    """Return ('none'|'point'|'overlap', point-or-None) for axis-aligned lines."""
    a_horizontal = a1[1] == a2[1]
    b_horizontal = b1[1] == b2[1]

    if a_horizontal and b_horizontal:
        if a1[1] != b1[1]:
            return "none", None
        low = max(min(a1[0], a2[0]), min(b1[0], b2[0]))
        high = min(max(a1[0], a2[0]), max(b1[0], b2[0]))
        if low > high:
            return "none", None
        if low < high:
            return "overlap", None
        return "point", (low, a1[1])

    if not a_horizontal and not b_horizontal:
        if a1[0] != b1[0]:
            return "none", None
        low = max(min(a1[1], a2[1]), min(b1[1], b2[1]))
        high = min(max(a1[1], a2[1]), max(b1[1], b2[1]))
        if low > high:
            return "none", None
        if low < high:
            return "overlap", None
        return "point", (a1[0], low)

    if a_horizontal:
        candidate = (b1[0], a1[1])
        if _point_on_segment(candidate, a1, a2) and _point_on_segment(candidate, b1, b2):
            return "point", candidate
    else:
        candidate = (a1[0], b1[1])
        if _point_on_segment(candidate, a1, a2) and _point_on_segment(candidate, b1, b2):
            return "point", candidate
    return "none", None


def _bbox_closed_intersects(a: Mapping[str, int], b: Mapping[str, int]) -> bool:
    return not (
        a["max_x"] < b["min_x"]
        or b["max_x"] < a["min_x"]
        or a["max_y"] < b["min_y"]
        or b["max_y"] < a["min_y"]
    )


def _computed_bbox(point_ids: Sequence[str], points: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    xs = [int(points[point_id]["x"]) for point_id in point_ids]
    ys = [int(points[point_id]["y"]) for point_id in point_ids]
    return {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}


def validate_world(data: Mapping[str, Any], *, require_seed: bool | None = None) -> dict[str, int]:
    """Validate schema, valid structures, references, and exact zero collisions.

    ``require_seed=True`` is suitable for direct generator output.
    ``require_seed=False`` requires a seedless composed world.
    ``None`` accepts either form.
    """
    _require(data.get("schema") == SCHEMA, f"schema must be {SCHEMA!r}")
    world = data.get("world")
    _require(isinstance(world, Mapping), "world must be an object")
    _require(world.get("dimensions") == 2, "only two-dimensional worlds are renderable")
    has_seed = "seed" in world
    if require_seed is True:
        _require(has_seed and str(world.get("seed", "")) != "", "generated world requires a seed")
    elif require_seed is False:
        _require(not has_seed, "composed world must not contain a seed")

    objects = data.get("objects")
    _require(isinstance(objects, Mapping), "objects must be an object")
    point_list = objects.get("points")
    line_list = objects.get("straight_lines")
    canvases = data.get("canvases")
    partitions = data.get("canvas_partitions")
    _require(isinstance(point_list, list), "objects.points must be an array")
    _require(isinstance(line_list, list), "objects.straight_lines must be an array")
    _require(isinstance(canvases, list) and len(canvases) > 0, "canvases must be a non-empty array")
    _require(isinstance(partitions, list), "canvas_partitions must be an array")

    points: dict[str, Mapping[str, Any]] = {}
    point_coordinates: dict[tuple[int, int], str] = {}
    all_ids: set[str] = set()
    for index, raw in enumerate(point_list):
        _require(isinstance(raw, Mapping), f"point {index} must be an object")
        point_id = raw.get("id")
        _require(isinstance(point_id, str) and point_id, f"point {index} has invalid id")
        _require(point_id not in all_ids, f"duplicate object id {point_id}")
        all_ids.add(point_id)
        _require(raw.get("type") == "point", f"{point_id} must have type point")
        x = raw.get("x")
        y = raw.get("y")
        _require(_is_int(x) and _is_int(y), f"{point_id} coordinates must be integers")
        coordinate = (x, y)
        _require(coordinate not in point_coordinates,
                 f"point collision: {point_id} and {point_coordinates.get(coordinate)} at {coordinate}")
        point_coordinates[coordinate] = point_id
        points[point_id] = raw

    lines: dict[str, Mapping[str, Any]] = {}
    line_endpoints: dict[str, tuple[str, str]] = {}
    for index, raw in enumerate(line_list):
        _require(isinstance(raw, Mapping), f"line {index} must be an object")
        line_id = raw.get("id")
        _require(isinstance(line_id, str) and line_id, f"line {index} has invalid id")
        _require(line_id not in all_ids, f"duplicate object id {line_id}")
        all_ids.add(line_id)
        _require(raw.get("type") == "straight-line", f"{line_id} must have type straight-line")
        refs = raw.get("point_ids")
        _require(isinstance(refs, list) and len(refs) == 2, f"{line_id} needs two point_ids")
        a_id, b_id = refs
        _require(isinstance(a_id, str) and isinstance(b_id, str), f"{line_id} point ids must be strings")
        _require(a_id in points and b_id in points and a_id != b_id,
                 f"{line_id} has missing or identical endpoints")
        a = (int(points[a_id]["x"]), int(points[a_id]["y"]))
        b = (int(points[b_id]["x"]), int(points[b_id]["y"]))
        _require((a[0] == b[0]) ^ (a[1] == b[1]),
                 f"{line_id} must be a non-zero axis-aligned straight line")
        role = raw.get("role")
        _require(role in {"canvas-boundary", "canvas-partition"}, f"{line_id} has invalid role")
        _require(isinstance(raw.get("canvas_id"), str), f"{line_id} needs canvas_id")
        lines[line_id] = raw
        line_endpoints[line_id] = (a_id, b_id)

    canvas_map: dict[str, Mapping[str, Any]] = {}
    canvas_bboxes: dict[str, dict[str, int]] = {}
    for index, raw in enumerate(canvases):
        _require(isinstance(raw, Mapping), f"canvas {index} must be an object")
        canvas_id = raw.get("id")
        _require(isinstance(canvas_id, str) and canvas_id, f"canvas {index} has invalid id")
        _require(canvas_id not in all_ids, f"duplicate id {canvas_id}")
        all_ids.add(canvas_id)
        point_ids = raw.get("point_ids")
        line_ids = raw.get("line_ids")
        _require(isinstance(point_ids, list) and len(point_ids) >= 3,
                 f"{canvas_id} needs at least three points")
        _require(isinstance(line_ids, list) and len(line_ids) >= 3,
                 f"{canvas_id} needs at least three lines")
        _require(len(point_ids) + len(line_ids) >= 6,
                 f"{canvas_id} needs at least six objects")
        _require(len(point_ids) == len(line_ids),
                 f"{canvas_id} boundary point/line counts must match")
        _require(len(set(point_ids)) == len(point_ids), f"{canvas_id} repeats a boundary point")
        _require(len(set(line_ids)) == len(line_ids), f"{canvas_id} repeats a boundary line")
        for item in point_ids:
            _require(item in points, f"{canvas_id} references missing point {item}")
            _require(points[item].get("canvas_id") == canvas_id,
                     f"point {item} has wrong canvas_id")
        for item in line_ids:
            _require(item in lines, f"{canvas_id} references missing line {item}")
            _require(lines[item].get("canvas_id") == canvas_id,
                     f"line {item} has wrong canvas_id")
            _require(lines[item].get("role") == "canvas-boundary",
                     f"{canvas_id} line {item} is not a boundary line")

        for edge_index, line_id in enumerate(line_ids):
            expected = {point_ids[edge_index], point_ids[(edge_index + 1) % len(point_ids)]}
            _require(set(line_endpoints[line_id]) == expected,
                     f"{canvas_id} boundary is not closed in declared order at {line_id}")

        bbox = _computed_bbox(point_ids, points)
        declared_bbox = raw.get("bbox")
        if declared_bbox is not None:
            _require(isinstance(declared_bbox, Mapping), f"{canvas_id}.bbox must be an object")
            _require(all(_is_int(declared_bbox.get(k)) for k in ("min_x", "min_y", "max_x", "max_y")),
                     f"{canvas_id}.bbox values must be integers")
            _require(dict(declared_bbox) == bbox, f"{canvas_id}.bbox does not match its points")
        canvas_map[canvas_id] = raw
        canvas_bboxes[canvas_id] = bbox

    canvas_ids = list(canvas_map)
    for i, canvas_id in enumerate(canvas_ids):
        for other_id in canvas_ids[i + 1:]:
            _require(not _bbox_closed_intersects(canvas_bboxes[canvas_id], canvas_bboxes[other_id]),
                     f"canvas collision between {canvas_id} and {other_id}")

    partition_map: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(partitions):
        _require(isinstance(raw, Mapping), f"partition {index} must be an object")
        partition_id = raw.get("id")
        _require(isinstance(partition_id, str) and partition_id, f"partition {index} has invalid id")
        _require(partition_id not in all_ids, f"duplicate id {partition_id}")
        all_ids.add(partition_id)
        canvas_id = raw.get("canvas_id")
        refs = raw.get("point_ids")
        line_id = raw.get("line_id")
        _require(canvas_id in canvas_map, f"{partition_id} has missing canvas")
        _require(isinstance(refs, list) and len(refs) == 2 and refs[0] in points and refs[1] in points,
                 f"{partition_id} must reference exactly two existing points")
        _require(refs[0] != refs[1], f"{partition_id} points must differ")
        _require(line_id in lines, f"{partition_id} has missing line")
        _require(lines[line_id].get("role") == "canvas-partition",
                 f"{partition_id} line is not a canvas-partition")
        _require(lines[line_id].get("canvas_id") == canvas_id,
                 f"{partition_id} line belongs to another canvas")
        _require(lines[line_id].get("partition_id") == partition_id,
                 f"{partition_id} line has wrong partition_id")
        _require(set(line_endpoints[line_id]) == set(refs),
                 f"{partition_id} is not exactly its two points plus its line")
        for point_id in refs:
            _require(points[point_id].get("canvas_id") == canvas_id,
                     f"{partition_id} endpoint {point_id} belongs to another canvas")
            _require(points[point_id].get("partition_id") == partition_id,
                     f"{partition_id} endpoint {point_id} has wrong partition_id")
        partition_map[partition_id] = raw

    for line_id, raw in lines.items():
        if raw.get("role") == "canvas-partition":
            _require(raw.get("partition_id") in partition_map,
                     f"partition line {line_id} has no partition record")

    # A point may touch only lines for which it is an explicit endpoint.
    for point_id, raw in points.items():
        coordinate = (int(raw["x"]), int(raw["y"]))
        for line_id, (a_id, b_id) in line_endpoints.items():
            if point_id in (a_id, b_id):
                continue
            a = (int(points[a_id]["x"]), int(points[a_id]["y"]))
            b = (int(points[b_id]["x"]), int(points[b_id]["y"]))
            _require(not _point_on_segment(coordinate, a, b),
                     f"point-line collision between {point_id} and {line_id}")

    line_ids = list(lines)
    for i, line_id in enumerate(line_ids):
        a_id, b_id = line_endpoints[line_id]
        a = (int(points[a_id]["x"]), int(points[a_id]["y"]))
        b = (int(points[b_id]["x"]), int(points[b_id]["y"]))
        for other_id in line_ids[i + 1:]:
            c_id, d_id = line_endpoints[other_id]
            c = (int(points[c_id]["x"]), int(points[c_id]["y"]))
            d = (int(points[d_id]["x"]), int(points[d_id]["y"]))
            kind, coordinate = _segment_intersection(a, b, c, d)
            if kind == "none":
                continue
            _require(kind != "overlap", f"line overlap between {line_id} and {other_id}")
            assert coordinate is not None
            allowed = (
                lines[line_id].get("canvas_id") == lines[other_id].get("canvas_id")
                and coordinate in {a, b}
                and coordinate in {c, d}
            )
            _require(allowed,
                     f"line collision between {line_id} and {other_id} at {coordinate}")

    bounds = world.get("bounds")
    if bounds is not None:
        _require(isinstance(bounds, Mapping), "world.bounds must be an object")
        for key in ("min_x", "min_y", "max_x", "max_y"):
            _require(_is_int(bounds.get(key)), f"world.bounds.{key} must be an integer")
        for point_id, raw in points.items():
            _require(bounds["min_x"] <= raw["x"] <= bounds["max_x"] and
                     bounds["min_y"] <= raw["y"] <= bounds["max_y"],
                     f"{point_id} lies outside world.bounds")

    expected_counts = {
        "objects": len(points) + len(lines),
        "points": len(points),
        "straight_lines": len(lines),
        "canvases": len(canvas_map),
        "canvas_partitions": len(partition_map),
    }
    counts = data.get("counts")
    _require(isinstance(counts, Mapping), "counts must be an object")
    for key, expected in expected_counts.items():
        _require(counts.get(key) == expected,
                 f"counts.{key} is {counts.get(key)!r}; expected {expected}")

    fabric = data.get("fabric_counts")
    _require(isinstance(fabric, Mapping), "fabric_counts must be an object")
    ratio_expectations = {
        "object_count": ("a", "b", "x", expected_counts["objects"]),
        "canvas_count": ("c", "d", "y", expected_counts["canvases"]),
        "canvas_partition_count": (
            "e", "f", "z", expected_counts["canvas_partitions"]
        ),
    }
    for ratio_name, (numerator_key, denominator_key, value_key, expected) in ratio_expectations.items():
        ratio = fabric.get(ratio_name)
        _require(isinstance(ratio, Mapping), f"fabric_counts.{ratio_name} must be an object")
        _require(
            ratio.get(numerator_key) == expected
            and ratio.get(denominator_key) == 1
            and ratio.get(value_key) == expected,
            f"fabric_counts.{ratio_name} must be canonical {expected}/1={expected}",
        )
    expected_xor = (
        expected_counts["objects"]
        ^ expected_counts["canvases"]
        ^ expected_counts["canvas_partitions"]
    )
    _require(fabric.get("xor_signature") == expected_xor,
             f"fabric_counts.xor_signature must be {expected_xor}")
    _require(
        fabric.get("valid_structure_expression")
        == "<x xor y xor z> * ((<x xor y xor z>) ^ <x xor y xor z>)",
        "fabric_counts.valid_structure_expression does not match the specification",
    )

    return expected_counts


def world_extent(data: Mapping[str, Any], *, crop_to_content: bool = False) -> tuple[int, int, int, int]:
    world = data["world"]
    bounds = world.get("bounds")
    if not crop_to_content and isinstance(bounds, Mapping):
        return (
            int(bounds["min_x"]),
            int(bounds["min_y"]),
            int(bounds["max_x"]),
            int(bounds["max_y"]),
        )
    points = data["objects"]["points"]
    xs = [int(point["x"]) for point in points]
    ys = [int(point["y"]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _canvas_style(canvas: Mapping[str, Any]) -> tuple[str, str, float]:
    style = canvas.get("style")
    if not isinstance(style, Mapping):
        return "#eeeeee", "#222222", 2.0
    fill = style.get("fill", "#eeeeee")
    stroke = style.get("stroke", "#222222")
    width = style.get("stroke_width", 2)
    if not isinstance(fill, str):
        fill = "#eeeeee"
    if not isinstance(stroke, str):
        stroke = "#222222"
    if not isinstance(width, (int, float)) or isinstance(width, bool) or width <= 0:
        width = 2
    return fill, stroke, float(width)


def _render_svg(
    data: Mapping[str, Any],
    output: Path,
    *,
    scale: float,
    padding: float,
    show_points: bool,
    labels: bool,
    crop_to_content: bool,
    background: str,
) -> None:
    min_x, min_y, max_x, max_y = world_extent(data, crop_to_content=crop_to_content)
    logical_width = max(1.0, float(max_x - min_x) + 2.0 * padding)
    logical_height = max(1.0, float(max_y - min_y) + 2.0 * padding)
    pixel_width = max(1, int(math.ceil(logical_width * scale)))
    pixel_height = max(1, int(math.ceil(logical_height * scale)))
    view_x = float(min_x) - padding
    view_y = float(min_y) - padding

    point_map = {point["id"]: point for point in data["objects"]["points"]}
    line_map = {line["id"]: line for line in data["objects"]["straight_lines"]}
    canvas_map = {canvas["id"]: canvas for canvas in data["canvases"]}

    def point_pair(point_id: str) -> tuple[int, int]:
        point = point_map[point_id]
        return int(point["x"]), int(point["y"])

    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        stream.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{pixel_width}" '
            f'height="{pixel_height}" viewBox="{view_x:g} {view_y:g} '
            f'{logical_width:g} {logical_height:g}">\n'
        )
        title = html.escape(str(data["world"].get("name", "cfabric world")))
        stream.write(f"  <title>{title}</title>\n")
        stream.write(
            f'  <rect x="{view_x:g}" y="{view_y:g}" width="{logical_width:g}" '
            f'height="{logical_height:g}" fill="{html.escape(background, quote=True)}"/>\n'
        )

        # Fill regions first so all object lines remain visible.
        stream.write('  <g id="canvases">\n')
        for canvas in data["canvases"]:
            fill, stroke, stroke_width = _canvas_style(canvas)
            polygon = " ".join(f"{x},{y}" for x, y in map(point_pair, canvas["point_ids"]))
            stream.write(
                f'    <polygon id="{html.escape(canvas["id"], quote=True)}" '
                f'points="{polygon}" fill="{html.escape(fill, quote=True)}" '
                f'fill-opacity="0.72" stroke="none"/>\n'
            )
        stream.write("  </g>\n")

        stream.write('  <g id="straight-lines" fill="none" stroke-linecap="round">\n')
        for role in ("canvas-boundary", "canvas-partition"):
            for line in data["objects"]["straight_lines"]:
                if line.get("role") != role:
                    continue
                a = point_pair(line["point_ids"][0])
                b = point_pair(line["point_ids"][1])
                canvas = canvas_map[line["canvas_id"]]
                _, stroke, width = _canvas_style(canvas)
                if role == "canvas-partition":
                    width = max(1.0, width * 0.72)
                stream.write(
                    f'    <line id="{html.escape(line["id"], quote=True)}" '
                    f'x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" '
                    f'stroke="{html.escape(stroke, quote=True)}" stroke-width="{width:g}" '
                    f'vector-effect="non-scaling-stroke"/>\n'
                )
        stream.write("  </g>\n")

        if show_points:
            stream.write('  <g id="points">\n')
            radius = max(1.5, 2.2 / max(scale, 0.01))
            for point in data["objects"]["points"]:
                canvas = canvas_map[point["canvas_id"]]
                _, stroke, _ = _canvas_style(canvas)
                stream.write(
                    f'    <circle id="{html.escape(point["id"], quote=True)}" '
                    f'cx="{point["x"]}" cy="{point["y"]}" r="{radius:g}" '
                    f'fill="{html.escape(stroke, quote=True)}"/>\n'
                )
            stream.write("  </g>\n")

        if labels:
            stream.write(
                '  <g id="labels" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" '
                'font-size="12" text-anchor="middle" dominant-baseline="middle">\n'
            )
            for canvas in data["canvases"]:
                bbox = canvas.get("bbox") or _computed_bbox(canvas["point_ids"], point_map)
                x = (int(bbox["min_x"]) + int(bbox["max_x"])) / 2.0
                y = (int(bbox["min_y"]) + int(bbox["max_y"])) / 2.0
                _, stroke, _ = _canvas_style(canvas)
                stream.write(
                    f'    <text x="{x:g}" y="{y:g}" fill="{html.escape(stroke, quote=True)}">'
                    f'{html.escape(canvas["id"])}</text>\n'
                )
            stream.write("  </g>\n")

        stream.write("</svg>\n")


def _render_png(
    data: Mapping[str, Any],
    output: Path,
    *,
    scale: float,
    padding: float,
    show_points: bool,
    labels: bool,
    crop_to_content: bool,
    background: str,
) -> None:
    try:
        from PIL import Image, ImageColor, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise WorldValidationError(
            "PNG output requires Pillow; render to .svg or install Pillow"
        ) from exc

    min_x, min_y, max_x, max_y = world_extent(data, crop_to_content=crop_to_content)
    logical_width = max(1.0, float(max_x - min_x) + 2.0 * padding)
    logical_height = max(1.0, float(max_y - min_y) + 2.0 * padding)
    pixel_width = max(1, int(math.ceil(logical_width * scale)))
    pixel_height = max(1, int(math.ceil(logical_height * scale)))
    if pixel_width > 20000 or pixel_height > 20000:
        raise WorldValidationError("rendered PNG would exceed 20000 pixels on one axis")

    origin_x = float(min_x) - padding
    origin_y = float(min_y) - padding

    def transform(x: int | float, y: int | float) -> tuple[int, int]:
        return int(round((float(x) - origin_x) * scale)), int(round((float(y) - origin_y) * scale))

    def color(value: str, fallback: str) -> str:
        try:
            ImageColor.getrgb(value)
            return value
        except ValueError:
            return fallback

    point_map = {point["id"]: point for point in data["objects"]["points"]}
    canvas_map = {canvas["id"]: canvas for canvas in data["canvases"]}
    image = Image.new("RGB", (pixel_width, pixel_height), color(background, "#ffffff"))
    draw = ImageDraw.Draw(image)

    for canvas in data["canvases"]:
        fill, _, _ = _canvas_style(canvas)
        polygon = [transform(point_map[point_id]["x"], point_map[point_id]["y"])
                   for point_id in canvas["point_ids"]]
        draw.polygon(polygon, fill=color(fill, "#eeeeee"))

    for role in ("canvas-boundary", "canvas-partition"):
        for line in data["objects"]["straight_lines"]:
            if line.get("role") != role:
                continue
            a = point_map[line["point_ids"][0]]
            b = point_map[line["point_ids"][1]]
            canvas = canvas_map[line["canvas_id"]]
            _, stroke, width = _canvas_style(canvas)
            if role == "canvas-partition":
                width = max(1.0, width * 0.72)
            draw.line(
                [transform(a["x"], a["y"]), transform(b["x"], b["y"])],
                fill=color(stroke, "#222222"),
                width=max(1, int(round(width * scale))),
            )

    if show_points:
        radius = max(2, int(round(2.5 * scale)))
        for point in data["objects"]["points"]:
            canvas = canvas_map[point["canvas_id"]]
            _, stroke, _ = _canvas_style(canvas)
            x, y = transform(point["x"], point["y"])
            draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                         fill=color(stroke, "#222222"))

    if labels:
        font = ImageFont.load_default()
        for canvas in data["canvases"]:
            bbox = canvas.get("bbox") or _computed_bbox(canvas["point_ids"], point_map)
            x = (int(bbox["min_x"]) + int(bbox["max_x"])) / 2.0
            y = (int(bbox["min_y"]) + int(bbox["max_y"])) / 2.0
            _, stroke, _ = _canvas_style(canvas)
            draw.text(transform(x, y), canvas["id"], anchor="mm",
                      fill=color(stroke, "#222222"), font=font)

    image.save(output)


def render_world(
    data: Mapping[str, Any],
    output: str | Path,
    *,
    scale: float = 1.0,
    padding: float = 24.0,
    show_points: bool = False,
    labels: bool = False,
    crop_to_content: bool = False,
    background: str = "#ffffff",
) -> None:
    if not math.isfinite(scale) or scale <= 0:
        raise WorldValidationError("scale must be a positive finite number")
    if not math.isfinite(padding) or padding < 0:
        raise WorldValidationError("padding must be a non-negative finite number")
    target = Path(output)
    suffix = target.suffix.lower()
    if suffix == ".svg":
        _render_svg(
            data, target, scale=scale, padding=padding, show_points=show_points,
            labels=labels, crop_to_content=crop_to_content, background=background,
        )
    elif suffix == ".png":
        _render_png(
            data, target, scale=scale, padding=padding, show_points=show_points,
            labels=labels, crop_to_content=crop_to_content, background=background,
        )
    else:
        raise WorldValidationError("output extension must be .svg or .png")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and render cfabric-world JSON as SVG or PNG."
    )
    parser.add_argument("input", help="cfabric-world JSON file")
    parser.add_argument("-o", "--output", help="output .svg or .png path")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="pixel scale (default: 1.0)")
    parser.add_argument("--padding", type=float, default=24.0,
                        help="logical padding around the world (default: 24)")
    parser.add_argument("--show-points", action="store_true",
                        help="draw point objects as circles")
    parser.add_argument("--labels", action="store_true",
                        help="draw canvas identifiers")
    parser.add_argument("--crop-to-content", action="store_true",
                        help="ignore declared world bounds and crop to objects")
    parser.add_argument("--background", default="#ffffff",
                        help="background color (default: #ffffff)")
    parser.add_argument("--no-validate", action="store_true",
                        help="skip independent validation before rendering")
    parser.add_argument("--validate-only", action="store_true",
                        help="validate JSON without creating an image")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        data = load_world(args.input)
        counts = None if args.no_validate else validate_world(data)
        if args.validate_only:
            if counts is None:
                counts = validate_world(data)
            print(json.dumps({"valid": True, "counts": counts}, sort_keys=True))
            return 0

        output = Path(args.output) if args.output else Path(args.input).with_suffix(".svg")
        render_world(
            data,
            output,
            scale=args.scale,
            padding=args.padding,
            show_points=args.show_points,
            labels=args.labels,
            crop_to_content=args.crop_to_content,
            background=args.background,
        )
        if counts is None:
            counts = {
                "canvases": len(data["canvases"]),
                "canvas_partitions": len(data["canvas_partitions"]),
            }
        print(
            f"rendered {counts['canvases']} canvases and "
            f"{counts['canvas_partitions']} partitions to {output}",
            file=sys.stderr,
        )
        return 0
    except (WorldValidationError, OSError, ValueError) as exc:
        print(f"cfabric.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
