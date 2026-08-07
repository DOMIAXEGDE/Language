#!/usr/bin/env python3
"""Compose cfabric worlds as ordered layers without assigning a new seed.

Later inputs are the upper layers. Every result is independently validated and
contains no ``world.seed`` field.

Examples:
  python clyaers.py a.json b.json -o joined.json --layout horizontal
  python clyaers.py a.json b.json -o overlay.json \
      --offset 0,0 --offset 300,120 --collision reject
  python clyaers.py a.json b.json -o cut.json \
      --collision erase-regions --clearance 1
  python clyaers.py a.json b.json -o touch-cut.json \
      --collision erase-points --clearance 1

``erase-points`` resolves point-only contacts by removing small integer regions
from the incoming (upper) canvas and rebuilding valid rectangular fragments.
It rejects line or area overlaps. ``erase-regions`` subtracts every colliding
lower-layer canvas region from the incoming canvas and rebuilds all surviving
fragments as valid structures.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from cfabric import (
    SCHEMA,
    WorldValidationError,
    load_world,
    render_world,
    validate_world,
    world_extent,
    write_world,
)


@dataclass(frozen=True, order=True)
class Rect:
    min_x: int
    min_y: int
    max_x: int
    max_y: int

    def valid(self, min_span: int = 1) -> bool:
        return self.max_x - self.min_x >= min_span and self.max_y - self.min_y >= min_span

    def translate(self, dx: int, dy: int) -> "Rect":
        return Rect(self.min_x + dx, self.min_y + dy, self.max_x + dx, self.max_y + dy)

    def expand(self, amount: int) -> "Rect":
        return Rect(
            self.min_x - amount,
            self.min_y - amount,
            self.max_x + amount,
            self.max_y + amount,
        )

    def intersection(self, other: "Rect") -> "Rect | None":
        result = Rect(
            max(self.min_x, other.min_x),
            max(self.min_y, other.min_y),
            min(self.max_x, other.max_x),
            min(self.max_y, other.max_y),
        )
        if result.min_x > result.max_x or result.min_y > result.max_y:
            return None
        return result

    def as_json(self) -> dict[str, int]:
        return {
            "min_x": self.min_x,
            "min_y": self.min_y,
            "max_x": self.max_x,
            "max_y": self.max_y,
        }


@dataclass(frozen=True)
class PartitionSpec:
    orientation: str  # vertical or horizontal
    coordinate: int


@dataclass(frozen=True)
class SourceCanvas:
    rect: Rect
    partitions: tuple[PartitionSpec, ...]
    style: Mapping[str, Any]
    source_canvas_id: str
    source_layer: int


def _parse_offset(text: str) -> tuple[int, int]:
    parts = text.replace(":", ",").split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("offset must be X,Y")
    try:
        return int(parts[0].strip(), 0), int(parts[1].strip(), 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("offset values must be integers") from exc


def _subtract_rect(subject: Rect, cut: Rect, min_span: int) -> list[Rect]:
    """Subtract a closed integer rectangle, leaving separated valid rectangles."""
    overlap = subject.intersection(cut)
    if overlap is None:
        return [subject]

    candidates = [
        Rect(subject.min_x, subject.min_y, overlap.min_x - 1, subject.max_y),
        Rect(overlap.max_x + 1, subject.min_y, subject.max_x, subject.max_y),
        Rect(overlap.min_x, subject.min_y, overlap.max_x, overlap.min_y - 1),
        Rect(overlap.min_x, overlap.max_y + 1, overlap.max_x, subject.max_y),
    ]
    return [rect for rect in candidates if rect.valid(min_span)]


def _point_map(data: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {point["id"]: point for point in data["objects"]["points"]}


def _line_map(data: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {line["id"]: line for line in data["objects"]["straight_lines"]}


def _extract_canvases(data: Mapping[str, Any], layer_index: int,
                      dx: int, dy: int) -> list[SourceCanvas]:
    points = _point_map(data)
    lines = _line_map(data)
    partitions_by_canvas: dict[str, list[Mapping[str, Any]]] = {}
    for partition in data["canvas_partitions"]:
        partitions_by_canvas.setdefault(partition["canvas_id"], []).append(partition)

    extracted: list[SourceCanvas] = []
    for canvas in data["canvases"]:
        canvas_id = canvas["id"]
        bbox = canvas["bbox"]
        rect = Rect(
            int(bbox["min_x"]) + dx,
            int(bbox["min_y"]) + dy,
            int(bbox["max_x"]) + dx,
            int(bbox["max_y"]) + dy,
        )
        if not rect.valid(1):
            raise WorldValidationError(f"{canvas_id} is not a non-zero rectangle")

        # The layer erasure operations are exact for axis-aligned rectangular
        # canvases. Split boundary points are allowed and expected.
        corners = {
            (rect.min_x, rect.min_y),
            (rect.max_x, rect.min_y),
            (rect.max_x, rect.max_y),
            (rect.min_x, rect.max_y),
        }
        boundary_coordinates: set[tuple[int, int]] = set()
        for point_id in canvas["point_ids"]:
            point = points[point_id]
            coordinate = (int(point["x"]) + dx, int(point["y"]) + dy)
            boundary_coordinates.add(coordinate)
            x, y = coordinate
            if not (x in (rect.min_x, rect.max_x) or y in (rect.min_y, rect.max_y)):
                raise WorldValidationError(
                    f"{canvas_id} is not rectangular; clyaers region erasure supports rectangles"
                )
        if not corners.issubset(boundary_coordinates):
            raise WorldValidationError(f"{canvas_id} does not contain all rectangle corners")

        specs: list[PartitionSpec] = []
        for partition in partitions_by_canvas.get(canvas_id, []):
            line = lines[partition["line_id"]]
            a = points[line["point_ids"][0]]
            b = points[line["point_ids"][1]]
            ax, ay = int(a["x"]) + dx, int(a["y"]) + dy
            bx, by = int(b["x"]) + dx, int(b["y"]) + dy
            if ax == bx and {ay, by} == {rect.min_y, rect.max_y}:
                if not rect.min_x < ax < rect.max_x:
                    raise WorldValidationError(f"{partition['id']} is not inside {canvas_id}")
                specs.append(PartitionSpec("vertical", ax))
            elif ay == by and {ax, bx} == {rect.min_x, rect.max_x}:
                if not rect.min_y < ay < rect.max_y:
                    raise WorldValidationError(f"{partition['id']} is not inside {canvas_id}")
                specs.append(PartitionSpec("horizontal", ay))
            else:
                raise WorldValidationError(
                    f"{partition['id']} does not span its rectangular canvas"
                )

        orientations = {spec.orientation for spec in specs}
        if len(orientations) > 1:
            raise WorldValidationError(f"{canvas_id} mixes crossing partition orientations")
        style = canvas.get("style") if isinstance(canvas.get("style"), Mapping) else {}
        extracted.append(
            SourceCanvas(
                rect=rect,
                partitions=tuple(sorted(set(specs), key=lambda spec: (spec.orientation, spec.coordinate))),
                style=dict(style),
                source_canvas_id=canvas_id,
                source_layer=layer_index,
            )
        )
    return extracted


class GeometryBuilder:
    def __init__(self) -> None:
        self.points: list[dict[str, Any]] = []
        self.lines: list[dict[str, Any]] = []
        self.canvases: list[dict[str, Any]] = []
        self.partitions: list[dict[str, Any]] = []

    def _point_id(self) -> str:
        return f"xP{len(self.points) + 1:06d}"

    def _line_id(self) -> str:
        return f"xL{len(self.lines) + 1:06d}"

    def _canvas_id(self) -> str:
        return f"xC{len(self.canvases) + 1:04d}"

    def _partition_ids(self, count: int) -> list[str]:
        start = len(self.partitions) + 1
        return [f"xZ{index:06d}" for index in range(start, start + count)]

    def _add_point(self, x: int, y: int, canvas_id: str,
                   partition_id: str | None = None) -> str:
        point_id = self._point_id()
        roles = ["canvas"]
        point: dict[str, Any] = {
            "id": point_id,
            "type": "point",
            "x": x,
            "y": y,
            "roles": roles,
            "canvas_id": canvas_id,
        }
        if partition_id is not None:
            roles.append("canvas-partition")
            point["partition_id"] = partition_id
        self.points.append(point)
        return point_id

    def _add_line(self, a: str, b: str, role: str, canvas_id: str,
                  partition_id: str | None = None) -> str:
        line_id = self._line_id()
        line: dict[str, Any] = {
            "id": line_id,
            "type": "straight-line",
            "point_ids": [a, b],
            "role": role,
            "canvas_id": canvas_id,
        }
        if partition_id is not None:
            line["partition_id"] = partition_id
        self.lines.append(line)
        return line_id

    def add_canvas(self, source: SourceCanvas, rect: Rect,
                   specs: Iterable[PartitionSpec]) -> str:
        canvas_id = self._canvas_id()
        vertical = sorted({spec.coordinate for spec in specs
                           if spec.orientation == "vertical" and rect.min_x < spec.coordinate < rect.max_x})
        horizontal = sorted({spec.coordinate for spec in specs
                             if spec.orientation == "horizontal" and rect.min_y < spec.coordinate < rect.max_y})
        if vertical and horizontal:
            raise WorldValidationError("rebuilt canvas would contain crossing partition orientations")
        coordinates = vertical if vertical else horizontal
        orientation = "vertical" if vertical else "horizontal"
        partition_ids = self._partition_ids(len(coordinates))
        first_side: list[str] = []
        second_side: list[str] = [""] * len(coordinates)
        boundary: list[str] = []

        if orientation == "vertical":
            boundary.append(self._add_point(rect.min_x, rect.min_y, canvas_id))
            for coordinate, partition_id in zip(coordinates, partition_ids):
                point_id = self._add_point(coordinate, rect.min_y, canvas_id, partition_id)
                first_side.append(point_id)
                boundary.append(point_id)
            boundary.append(self._add_point(rect.max_x, rect.min_y, canvas_id))
            boundary.append(self._add_point(rect.max_x, rect.max_y, canvas_id))
            for index in range(len(coordinates) - 1, -1, -1):
                point_id = self._add_point(
                    coordinates[index], rect.max_y, canvas_id, partition_ids[index]
                )
                second_side[index] = point_id
                boundary.append(point_id)
            boundary.append(self._add_point(rect.min_x, rect.max_y, canvas_id))
        else:
            boundary.append(self._add_point(rect.min_x, rect.min_y, canvas_id))
            boundary.append(self._add_point(rect.max_x, rect.min_y, canvas_id))
            for coordinate, partition_id in zip(coordinates, partition_ids):
                point_id = self._add_point(rect.max_x, coordinate, canvas_id, partition_id)
                first_side.append(point_id)
                boundary.append(point_id)
            boundary.append(self._add_point(rect.max_x, rect.max_y, canvas_id))
            boundary.append(self._add_point(rect.min_x, rect.max_y, canvas_id))
            for index in range(len(coordinates) - 1, -1, -1):
                point_id = self._add_point(
                    rect.min_x, coordinates[index], canvas_id, partition_ids[index]
                )
                second_side[index] = point_id
                boundary.append(point_id)

        boundary_lines: list[str] = []
        for index, point_id in enumerate(boundary):
            boundary_lines.append(
                self._add_line(
                    point_id,
                    boundary[(index + 1) % len(boundary)],
                    "canvas-boundary",
                    canvas_id,
                )
            )

        for index, partition_id in enumerate(partition_ids):
            line_id = self._add_line(
                first_side[index], second_side[index], "canvas-partition",
                canvas_id, partition_id,
            )
            self.partitions.append(
                {
                    "id": partition_id,
                    "canvas_id": canvas_id,
                    "point_ids": [first_side[index], second_side[index]],
                    "line_id": line_id,
                }
            )

        style = {
            "fill": source.style.get("fill", "#eeeeee"),
            "stroke": source.style.get("stroke", "#222222"),
            "stroke_width": source.style.get("stroke_width", 2),
        }
        self.canvases.append(
            {
                "id": canvas_id,
                "point_ids": boundary,
                "line_ids": boundary_lines,
                "bbox": rect.as_json(),
                "style": style,
                "source": {
                    "layer": source.source_layer,
                    "canvas_id": source.source_canvas_id,
                },
            }
        )
        return canvas_id

    def finalize(self, name: str, layers: Sequence[Mapping[str, Any]],
                 erasures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        if not self.canvases or not self.points:
            raise WorldValidationError("composition erased every canvas")
        xs = [int(point["x"]) for point in self.points]
        ys = [int(point["y"]) for point in self.points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        result: dict[str, Any] = {
            "schema": SCHEMA,
            "generator": {
                "name": "clyaers",
                "version": "1.0.0",
                "deterministic_composition": True,
            },
            "world": {
                "name": name,
                "dimensions": 2,
                "composed": True,
                "bounds": {
                    "min_x": min_x,
                    "min_y": min_y,
                    "max_x": max_x,
                    "max_y": max_y,
                    "width": max_x - min_x,
                    "height": max_y - min_y,
                },
            },
            "valid_structure": {
                "object_types": ["point", "straight-line"],
                "number_domain": ["zero", "negative-rational", "positive-rational"],
                "coordinate_encoding": "signed-integer-rational",
                "canvas_minimum": {"points": 3, "straight_lines": 3, "objects": 6},
                "canvas_partition_exact": {
                    "points": 2,
                    "straight_lines": 1,
                    "objects": 3,
                },
            },
            "counts": {
                "objects": len(self.points) + len(self.lines),
                "points": len(self.points),
                "straight_lines": len(self.lines),
                "canvases": len(self.canvases),
                "canvas_partitions": len(self.partitions),
            },
            "fabric_counts": {
                "object_count": {
                    "a": len(self.points) + len(self.lines),
                    "b": 1,
                    "x": len(self.points) + len(self.lines),
                },
                "canvas_count": {
                    "c": len(self.canvases),
                    "d": 1,
                    "y": len(self.canvases),
                },
                "canvas_partition_count": {
                    "e": len(self.partitions),
                    "f": 1,
                    "z": len(self.partitions),
                },
                "xor_signature": (len(self.points) + len(self.lines))
                ^ len(self.canvases)
                ^ len(self.partitions),
                "valid_structure_expression": (
                    "<x xor y xor z> * ((<x xor y xor z>) ^ <x xor y xor z>)"
                ),
            },
            "objects": {
                "points": self.points,
                "straight_lines": self.lines,
            },
            "canvases": self.canvases,
            "canvas_partitions": self.partitions,
            "layers": list(layers),
            "erasures": list(erasures),
            "validation": {
                "zero_collision": True,
                "canvas_boundaries_closed": True,
                "canvas_partitions_valid": True,
                "numbers_are_rational": True,
            },
        }
        # Intentionally no world.seed: composed worlds are transformations, not
        # generated worlds with a new pseudo-random source.
        return result


def _layout_offsets(
    worlds: Sequence[Mapping[str, Any]],
    layout: str,
    gap: int,
    explicit: Sequence[tuple[int, int]],
) -> list[tuple[int, int]]:
    if layout == "overlay":
        if len(explicit) > len(worlds):
            raise WorldValidationError("more --offset values than input worlds")
        return list(explicit) + [(0, 0)] * (len(worlds) - len(explicit))
    if explicit:
        raise WorldValidationError("--offset can only be combined with --layout overlay")

    extents = [world_extent(world, crop_to_content=True) for world in worlds]
    offsets: list[tuple[int, int]] = []
    if layout == "horizontal":
        cursor = 0
        for min_x, min_y, max_x, _ in extents:
            offsets.append((cursor - min_x, -min_y))
            cursor += max_x - min_x + gap
        return offsets
    if layout == "vertical":
        cursor = 0
        for min_x, min_y, _, max_y in extents:
            offsets.append((-min_x, cursor - min_y))
            cursor += max_y - min_y + gap
        return offsets
    if layout == "grid":
        columns = max(1, math.ceil(math.sqrt(len(worlds))))
        cell_width = max(max_x - min_x for min_x, _, max_x, _ in extents) + gap
        cell_height = max(max_y - min_y for _, min_y, _, max_y in extents) + gap
        for index, (min_x, min_y, _, _) in enumerate(extents):
            row, column = divmod(index, columns)
            offsets.append((column * cell_width - min_x, row * cell_height - min_y))
        return offsets
    raise WorldValidationError(f"unsupported layout {layout}")


def _specs_for_fragment(source: SourceCanvas, fragment: Rect) -> list[PartitionSpec]:
    selected: list[PartitionSpec] = []
    for spec in source.partitions:
        if spec.orientation == "vertical" and fragment.min_x < spec.coordinate < fragment.max_x:
            selected.append(spec)
        elif spec.orientation == "horizontal" and fragment.min_y < spec.coordinate < fragment.max_y:
            selected.append(spec)
    return selected


def compose_worlds(
    paths: Sequence[str | Path],
    *,
    offsets: Sequence[tuple[int, int]],
    collision: str,
    clearance: int,
    min_fragment_span: int,
    name: str,
) -> dict[str, Any]:
    if clearance < 1:
        raise WorldValidationError("clearance must be at least 1")
    if min_fragment_span < 1:
        raise WorldValidationError("min_fragment_span must be at least 1")

    worlds = [load_world(path) for path in paths]
    for data in worlds:
        validate_world(data)
    if len(offsets) != len(worlds):
        raise WorldValidationError("offset count does not match input count")

    builder = GeometryBuilder()
    accepted: list[Rect] = []
    erasures: list[dict[str, Any]] = []
    layer_metadata: list[dict[str, Any]] = []
    erasure_keys: set[tuple[Any, ...]] = set()

    for layer_index, (path, data, offset) in enumerate(zip(paths, worlds, offsets), start=1):
        dx, dy = offset
        layer_metadata.append(
            {
                "order": layer_index,
                "input": str(path),
                "world_name": str(data["world"].get("name", Path(path).stem)),
                "offset": {"x": dx, "y": dy},
            }
        )
        for source in _extract_canvases(data, layer_index, dx, dy):
            fragments = [source.rect]
            for lower_index, lower in enumerate(accepted, start=1):
                forbidden = lower.expand(clearance - 1)
                next_fragments: list[Rect] = []
                for fragment in fragments:
                    overlap = fragment.intersection(forbidden)
                    if overlap is None:
                        next_fragments.append(fragment)
                        continue

                    if collision == "reject":
                        raise WorldValidationError(
                            f"collision: layer {layer_index} canvas {source.source_canvas_id} "
                            f"intersects accepted region {lower_index} at {overlap.as_json()}"
                        )

                    if collision == "erase-points":
                        if overlap.min_x != overlap.max_x or overlap.min_y != overlap.max_y:
                            raise WorldValidationError(
                                "erase-points only resolves point contacts; use erase-regions "
                                f"for overlap {overlap.as_json()}"
                            )
                        key = ("point", layer_index, source.source_canvas_id,
                               overlap.min_x, overlap.min_y)
                        if key not in erasure_keys:
                            erasure_keys.add(key)
                            erasures.append(
                                {
                                    "type": "point",
                                    "layer": layer_index,
                                    "source_canvas_id": source.source_canvas_id,
                                    "point": {"x": overlap.min_x, "y": overlap.min_y},
                                }
                            )
                        next_fragments.extend(
                            _subtract_rect(fragment, overlap, min_fragment_span)
                        )
                    elif collision == "erase-regions":
                        key = (
                            "region", layer_index, source.source_canvas_id,
                            overlap.min_x, overlap.min_y, overlap.max_x, overlap.max_y,
                        )
                        if key not in erasure_keys:
                            erasure_keys.add(key)
                            erasures.append(
                                {
                                    "type": "region",
                                    "layer": layer_index,
                                    "source_canvas_id": source.source_canvas_id,
                                    "bbox": overlap.as_json(),
                                }
                            )
                        next_fragments.extend(
                            _subtract_rect(fragment, forbidden, min_fragment_span)
                        )
                    else:
                        raise WorldValidationError(f"unknown collision policy {collision}")
                fragments = next_fragments
                if not fragments:
                    break

            for fragment in fragments:
                builder.add_canvas(source, fragment, _specs_for_fragment(source, fragment))
                accepted.append(fragment)

    result = builder.finalize(name, layer_metadata, erasures)
    validate_world(result, require_seed=False)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Layer cfabric JSON worlds into a seedless, independently validated "
            "zero-collision world."
        )
    )
    parser.add_argument("inputs", nargs="+", help="input cfabric-world JSON files in layer order")
    parser.add_argument("-o", "--output", required=True, help="output composed JSON file")
    parser.add_argument(
        "--layout",
        choices=("overlay", "horizontal", "vertical", "grid"),
        default="overlay",
        help="automatic input placement (default: overlay)",
    )
    parser.add_argument(
        "--offset",
        action="append",
        type=_parse_offset,
        default=[],
        metavar="X,Y",
        help="per-input translation; repeat in input order (overlay layout only)",
    )
    parser.add_argument("--gap", type=int, default=24,
                        help="gap for horizontal/vertical/grid layouts (default: 24)")
    parser.add_argument(
        "--collision",
        "--on-collision",
        choices=("reject", "erase-points", "erase-regions"),
        default="reject",
        help="upper-layer collision policy (default: reject)",
    )
    parser.add_argument(
        "--clearance",
        type=int,
        default=1,
        help="minimum integer separation after composition (default: 1)",
    )
    parser.add_argument(
        "--min-fragment-span",
        type=int,
        default=2,
        help="drop erasure fragments thinner than this span (default: 2)",
    )
    parser.add_argument("--name", default="composed-world", help="output world name")
    parser.add_argument("--render", metavar="PATH",
                        help="also render the result to .svg or .png")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="render scale when --render is used")
    parser.add_argument("--padding", type=float, default=24.0,
                        help="render padding when --render is used")
    parser.add_argument("--show-points", action="store_true",
                        help="show points in optional rendering")
    parser.add_argument("--labels", action="store_true",
                        help="show canvas labels in optional rendering")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.gap < 1 and args.layout != "overlay":
            raise WorldValidationError("automatic layouts require --gap of at least 1")
        loaded = [load_world(path) for path in args.inputs]
        for data in loaded:
            validate_world(data)
        offsets = _layout_offsets(loaded, args.layout, args.gap, args.offset)
        result = compose_worlds(
            args.inputs,
            offsets=offsets,
            collision=args.collision,
            clearance=args.clearance,
            min_fragment_span=args.min_fragment_span,
            name=args.name,
        )
        write_world(args.output, result)
        if args.render:
            render_world(
                result,
                args.render,
                scale=args.scale,
                padding=args.padding,
                show_points=args.show_points,
                labels=args.labels,
            )
        print(
            json.dumps(
                {
                    "valid": True,
                    "seedless": "seed" not in result["world"],
                    "counts": result["counts"],
                    "erasures": len(result["erasures"]),
                    "output": str(args.output),
                },
                sort_keys=True,
            )
        )
        return 0
    except (WorldValidationError, OSError, ValueError) as exc:
        print(f"clyaers.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
