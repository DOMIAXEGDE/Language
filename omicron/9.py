#!/usr/bin/env python3
"""
9.py — General Dimensional Circuit Composition and Rendering Utility

Purpose
-------
This file is a general-dimensional version of C700h_updated.py.

It keeps the C700h-style pipeline:

    accepted state -> colour-index tensor -> deterministic circuit/category/rendering outputs

and generalizes the dimensional logic using the same kind of fabric reasoning found in
nDCodex.php / 7.php:

    L = m^n, m >= min_root
    h^s compared with p^(L-1)
    nearest valid n-dimensional length
    ranked matching of observed text/code length and alphabet size

The result is a standalone Python utility for composing and rendering n-dimensional
logic fabrics. Qiskit, matplotlib, and Pillow are optional: the script always emits
JSON/text outputs, and emits PNG/Qiskit outputs when the optional dependencies exist.

Typical use
-----------
    python 9.py accept --state 0000001000000200000030000004 --dimension 2
    python 9.py derive --in state.txt --dimension 3 --outdir out9
    python 9.py category --in state.txt --dimension 4 --outdir out9 --assembly
    python 9.py projection --in state.txt --dimension 3 --axis-a 0 --axis-b 2
    python 9.py fabric --p 7 --h 10 --s 5 --dimension 2
    python 9.py match-text --text-file source.txt --dimension 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Optional, Sequence


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

SEGMENT_LEN: int = 7
MAX_COLOR_INDEX: int = 16 ** 6  # 16777216, with 1 -> #000000 and 16^6 -> #ffffff.

DEFAULT_GATES: list[str] = [
    "x",
    "y",
    "z",
    "h",
    "s",
    "sdg",
    "t",
    "tdg",
    "rx",
    "ry",
    "rz",
    "cx",
]

_DEC_RE = re.compile(r"^[0-9]+$")


# -----------------------------------------------------------------------------
# Generic arithmetic / dimensional fabric helpers
# -----------------------------------------------------------------------------


def bounded_pow(base: int, exp: int, limit: int) -> int:
    """Return base**exp, or limit + 1 as soon as the value exceeds limit."""
    if base < 0 or exp < 0:
        raise ValueError("base and exponent must be non-negative")
    result = 1
    for _ in range(exp):
        if base != 0 and result > limit // max(1, base):
            return limit + 1
        result *= base
        if result > limit:
            return limit + 1
    return result


def exact_nth_root(x: int, n: int) -> Optional[int]:
    """Return m when x == m**n, otherwise None."""
    if n <= 0 or x < 0:
        raise ValueError("invalid nth-root arguments")
    if x in (0, 1):
        return x
    lo, hi = 1, x
    while lo <= hi:
        mid = (lo + hi) // 2
        p = bounded_pow(mid, n, x)
        if p == x:
            return mid
        if p < x:
            lo = mid + 1
        else:
            hi = mid - 1
    return None


def nth_root_floor(x: int, n: int) -> int:
    """Return floor(x ** (1/n)) using integer arithmetic."""
    if n <= 0 or x < 0:
        raise ValueError("invalid nth-root arguments")
    if x in (0, 1):
        return x
    lo, hi, best = 1, x, 1
    while lo <= hi:
        mid = (lo + hi) // 2
        p = bounded_pow(mid, n, x)
        if p == x:
            return mid
        if p < x:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def valid_length_info(length: int, dimension: int, min_root: int) -> dict[str, Any]:
    """Return validity information for L = m^n with m >= min_root."""
    root = exact_nth_root(length, dimension)
    return {"valid": root is not None and root >= min_root, "m": root}


def nearest_valid_length(target: int, dimension: int, min_root: int, lmax: int) -> dict[str, Any]:
    """Find the nearest L = m^n length to target, bounded by lmax."""
    if target < 1 or lmax < 1:
        return {
            "closest_L": None,
            "m": None,
            "gap": None,
            "exact": False,
            "below_L": None,
            "above_L": None,
        }

    exact = valid_length_info(target, dimension, min_root)
    if exact["valid"] and target <= lmax:
        return {
            "closest_L": target,
            "m": exact["m"],
            "gap": 0,
            "exact": True,
            "below_L": target,
            "above_L": target,
        }

    root_floor = nth_root_floor(target, dimension)
    candidates: dict[int, int] = {}
    start = max(min_root, root_floor - 4)
    end = root_floor + 5
    for m in range(start, end + 1):
        L = bounded_pow(m, dimension, max(1, lmax))
        if 1 <= L <= lmax:
            candidates[L] = m

    if not candidates:
        max_root = nth_root_floor(lmax, dimension)
        if max_root >= min_root:
            L = bounded_pow(max_root, dimension, max(1, lmax))
            return {
                "closest_L": L,
                "m": max_root,
                "gap": abs(L - target),
                "exact": False,
                "below_L": L,
                "above_L": None,
            }
        return {
            "closest_L": None,
            "m": None,
            "gap": None,
            "exact": False,
            "below_L": None,
            "above_L": None,
        }

    below = None
    above = None
    bestL = None
    bestM = None
    bestGap = None
    for L in sorted(candidates):
        m = candidates[L]
        if L <= target:
            below = L
        if L >= target and above is None:
            above = L
        gap = abs(L - target)
        if bestGap is None or gap < bestGap or (gap == bestGap and L > int(bestL or 0)):
            bestGap = gap
            bestL = L
            bestM = m

    return {
        "closest_L": bestL,
        "m": bestM,
        "gap": bestGap,
        "exact": False,
        "below_L": below,
        "above_L": above,
    }


def classify_base(p: int) -> str:
    if p < 2:
        return "invalid"
    if p == 2:
        return "prime"
    if p % 2 == 0:
        return "other"
    r = int(math.sqrt(p))
    for k in range(3, r + 1, 2):
        if p % k == 0:
            return "other"
    return "prime"


def centered_integers(center: int, min_value: int, max_value: int, limit: int) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()

    def push(v: int) -> None:
        if v < min_value or v > max_value or v in seen or len(out) >= limit:
            return
        seen.add(v)
        out.append(v)

    push(center)
    d = 1
    while len(out) < limit and (center - d >= min_value or center + d <= max_value):
        push(center - d)
        push(center + d)
        d += 1
    return out


def max_primary_length(h: int, s: int, p: int) -> int:
    """
    Return the smallest L such that p^L >= h^s.

    This mirrors the 7.php fabric comparison style and supplies a finite bound for
    valid primary lengths whose predecessor capacity satisfies p^(L-1) < h^s.
    """
    if h < 2 or s < 1 or p < 2:
        raise ValueError("require h >= 2, s >= 1, p >= 2")
    target = pow(h, s)
    lo, hi = 1, 1
    while pow(p, hi) < target:
        hi *= 2
    while lo < hi:
        mid = (lo + hi) // 2
        if pow(p, mid) >= target:
            hi = mid
        else:
            lo = mid + 1
    return lo


def min_secondary_length_for_primary_length(h: int, p: int, L: int) -> int:
    """Return the minimum s such that h^s > p^(L-1)."""
    if h < 2 or p < 2 or L < 1:
        raise ValueError("require h >= 2, p >= 2, L >= 1")
    threshold = pow(p, L - 1)
    s = 1
    while pow(h, s) <= threshold:
        s += 1
    return s


def valid_lengths_up_to(lmax: int, dimension: int, min_root: int) -> list[dict[str, int]]:
    out: list[dict[str, int]] = []
    if lmax < 1:
        return out
    max_root = nth_root_floor(lmax, dimension)
    for m in range(max(1, min_root), max_root + 1):
        L = m ** dimension
        if L <= lmax:
            out.append({"L": L, "m": m})
    return out


# -----------------------------------------------------------------------------
# Tensor / colour acceptance
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionSpec:
    dimension: int
    root: int
    length: int
    shape: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "root": self.root,
            "length": self.length,
            "shape": list(self.shape),
        }


@dataclass(frozen=True)
class AcceptanceReport:
    ok: bool
    reason: str
    spec: Optional[DimensionSpec]
    indexes: list[int]
    hex_colors: list[str]
    segment_length: int
    wrap_adjacency: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "dimension": None if self.spec is None else self.spec.dimension,
            "root": None if self.spec is None else self.spec.root,
            "length": len(self.indexes),
            "shape": None if self.spec is None else list(self.spec.shape),
            "segment_length": self.segment_length,
            "wrap_adjacency": self.wrap_adjacency,
            "indexes": self.indexes,
            "hex_colors": self.hex_colors,
        }


def decode_id_to_color_indexes(id_string: str, segment_length: int = SEGMENT_LEN) -> list[int]:
    """Split a decimal string left-to-right into fixed-length integer chunks."""
    out: list[int] = []
    for i in range(0, len(id_string), segment_length):
        seg = id_string[i : i + segment_length]
        try:
            out.append(int(seg, 10))
        except ValueError:
            pass
    return out


def color_index_to_hex(index: int) -> str:
    if not (1 <= index <= MAX_COLOR_INDEX):
        raise ValueError(f"colour index outside [1..{MAX_COLOR_INDEX}]: {index}")
    return "#" + format(index - 1, "06x")


def hex_luma(hex_color: str) -> float:
    hc = hex_color.lstrip("#")
    r = int(hc[0:2], 16) / 255.0
    g = int(hc[2:4], 16) / 255.0
    b = int(hc[4:6], 16) / 255.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    hc = hex_color.lstrip("#")
    return (int(hc[0:2], 16) / 255.0, int(hc[2:4], 16) / 255.0, int(hc[4:6], 16) / 255.0)


def index_to_coord(index: int, shape: Sequence[int]) -> tuple[int, ...]:
    """Convert a row-major flat index to an n-dimensional coordinate."""
    coord = [0] * len(shape)
    x = index
    for axis in range(len(shape) - 1, -1, -1):
        size = shape[axis]
        coord[axis] = x % size
        x //= size
    return tuple(coord)


def coord_to_index(coord: Sequence[int], shape: Sequence[int]) -> int:
    """Convert an n-dimensional coordinate to a row-major flat index."""
    if len(coord) != len(shape):
        raise ValueError("coordinate and shape rank mismatch")
    idx = 0
    for c, size in zip(coord, shape):
        if c < 0 or c >= size:
            raise ValueError(f"coordinate {tuple(coord)} outside shape {tuple(shape)}")
        idx = idx * size + c
    return idx


def iter_coords(shape: Sequence[int]) -> Iterator[tuple[int, ...]]:
    if not shape:
        return
    total = math.prod(shape)
    for i in range(total):
        yield index_to_coord(i, shape)


def infer_dimension_spec(token_count: int, dimension: int, min_root: int) -> Optional[DimensionSpec]:
    root = exact_nth_root(token_count, dimension)
    if root is None or root < min_root:
        return None
    return DimensionSpec(dimension=dimension, root=root, length=token_count, shape=tuple([root] * dimension))


def has_nd_adjacent_conflict(indexes: Sequence[int], shape: Sequence[int], wrap: bool = False) -> bool:
    """True when any orthogonal neighbour pair in any axis has equal token value."""
    total = math.prod(shape)
    if len(indexes) != total:
        return True
    for flat, coord in enumerate(iter_coords(shape)):
        cur = indexes[flat]
        for axis, size in enumerate(shape):
            nxt = list(coord)
            if coord[axis] + 1 < size:
                nxt[axis] += 1
            elif wrap and size > 1:
                nxt[axis] = 0
            else:
                continue
            if cur == indexes[coord_to_index(nxt, shape)]:
                return True
    return False


def verify_acceptance(
    id_decimal: str,
    dimension: int,
    min_root: int = 2,
    segment_length: int = SEGMENT_LEN,
    wrap_adjacency: bool = False,
) -> AcceptanceReport:
    indexes = decode_id_to_color_indexes(id_decimal, segment_length=segment_length)
    spec = infer_dimension_spec(len(indexes), dimension, min_root)
    if spec is None:
        return AcceptanceReport(
            ok=False,
            reason=f"Token count {len(indexes)} is not a valid L=m^n with n={dimension} and m>={min_root}.",
            spec=None,
            indexes=list(indexes),
            hex_colors=[],
            segment_length=segment_length,
            wrap_adjacency=wrap_adjacency,
        )

    if not all(1 <= x <= MAX_COLOR_INDEX for x in indexes):
        return AcceptanceReport(
            ok=False,
            reason=f"One or more tokens are outside [1..{MAX_COLOR_INDEX}].",
            spec=spec,
            indexes=list(indexes),
            hex_colors=[],
            segment_length=segment_length,
            wrap_adjacency=wrap_adjacency,
        )

    if has_nd_adjacent_conflict(indexes, spec.shape, wrap=wrap_adjacency):
        return AcceptanceReport(
            ok=False,
            reason="Adjacency conflict: at least one orthogonal n-dimensional neighbour pair is equal.",
            spec=spec,
            indexes=list(indexes),
            hex_colors=[],
            segment_length=segment_length,
            wrap_adjacency=wrap_adjacency,
        )

    hex_colors = [color_index_to_hex(x) for x in indexes]
    return AcceptanceReport(
        ok=True,
        reason="Accepted.",
        spec=spec,
        indexes=list(indexes),
        hex_colors=hex_colors,
        segment_length=segment_length,
        wrap_adjacency=wrap_adjacency,
    )


# -----------------------------------------------------------------------------
# Parsing / text analysis / matching
# -----------------------------------------------------------------------------


def parse_state_to_decimal_string(raw: str) -> str:
    """Accept decimal or 0b-prefixed binary and return canonical decimal text."""
    s = raw.strip()
    if s.lower().startswith("0b"):
        return str(int(s, 2))
    if not _DEC_RE.match(s):
        raise ValueError("State must be a decimal integer string or a 0b-prefixed binary string.")
    return str(int(s)) if s else "0"


def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def escape_char(ch: str) -> str:
    if ch == "\n":
        return "\\n"
    if ch == "\r":
        return "\\r"
    if ch == "\t":
        return "\\t"
    if ch == " ":
        return "<space>"
    return ch


def analyze_text(text: str) -> dict[str, Any]:
    chars = list(text)
    unique_chars = sorted(set(chars))
    preview = " ".join(escape_char(ch) for ch in unique_chars[:80])
    return {
        "char_length": len(chars),
        "unique_count": len(unique_chars),
        "line_count": 0 if text == "" else text.count("\n") + 1,
        "unique_chars": unique_chars,
        "preview": preview,
    }


def rank_text_matches(
    analysis: dict[str, Any],
    dimension: int,
    min_root: int = 2,
    limit: int = 12,
    primary_min: int = 2,
    primary_max: int = 128,
    h_radius: int = 0,
) -> list[dict[str, Any]]:
    limit = max(1, min(24, int(limit)))
    target_length = max(1, int(analysis["char_length"]))
    observed_unique = max(1, int(analysis["unique_count"]))
    p_candidates = centered_integers(observed_unique, max(2, primary_min), max(primary_min, primary_max), max(24, limit * 4))
    h_candidates = centered_integers(
        observed_unique,
        max(2, observed_unique - h_radius),
        max(2, observed_unique + h_radius),
        max(1, 2 * h_radius + 1),
    ) or [max(2, observed_unique)]

    rows: list[dict[str, Any]] = []
    for h in h_candidates:
        for p in p_candidates:
            s = target_length
            try:
                Lmax = max_primary_length(h, s, p)
            except ValueError:
                continue
            nearest = nearest_valid_length(target_length, dimension, min_root, Lmax)
            if nearest["closest_L"] is None:
                continue
            gap = int(nearest["gap"])
            exact = bool(nearest["exact"])
            h_delta = abs(h - observed_unique)
            p_delta = abs(p - observed_unique)
            score = (-1_000_000 if exact else 0) + gap * 1000 + h_delta * 100 + p_delta
            rows.append(
                {
                    "score": score,
                    "p": p,
                    "h": h,
                    "s": s,
                    "n": dimension,
                    "Lmax": Lmax,
                    "closest_L": int(nearest["closest_L"]),
                    "m": int(nearest["m"]),
                    "gap": gap,
                    "exact": exact,
                    "base_type": classify_base(p),
                }
            )

    rows.sort(key=lambda r: (r["score"], r["gap"], r["h"], r["p"]))
    unique: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for row in rows:
        key = (row["p"], row["h"], row["s"], row["n"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
        if len(unique) >= limit:
            break
    return unique


# -----------------------------------------------------------------------------
# Dimensional circuit composition
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class GateEvent:
    layer: int
    coord: tuple[int, ...]
    token: int
    axis: int
    gate: str
    qubits: tuple[int, ...]
    angle: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "coord": list(self.coord),
            "token": self.token,
            "axis": self.axis,
            "gate": self.gate,
            "qubits": list(self.qubits),
            "angle": self.angle,
        }


def token_to_angle(token: int) -> float:
    k = (token % 32) + 1
    return k * (math.pi / 16.0)


def qubit_from_coord(coord: Sequence[int], token: int, q: int) -> int:
    """Deterministic coordinate-sensitive qubit assignment."""
    if q <= 1:
        return 0
    weighted = sum((axis + 1) * (value + 1) for axis, value in enumerate(coord))
    return (weighted + token) % q


def target_from_axis(control: int, axis: int, token: int, q: int) -> int:
    if q <= 1:
        return 0
    shift = 1 + ((token + axis) % (q - 1))
    return (control + shift) % q


def token_to_semantic_symbol(token: int, q: int, axis: int = 0, reversible_only: bool = False) -> str:
    gate = DEFAULT_GATES[token % len(DEFAULT_GATES)]
    if reversible_only:
        gate = "cx" if (token % 2 == 1 and q > 1) else "x"
    if gate in ("rx", "ry", "rz"):
        return f"{gate}(k={(token % 32) + 1})"
    if gate == "cx":
        if q <= 1:
            return "x"
        return f"cx(axis={axis},shift={1 + ((token + axis) % (q - 1))})"
    return gate


def derive_gate_events(
    indexes: Sequence[int],
    spec: DimensionSpec,
    max_qubits: int = 8,
    max_layers: int = 16,
    reversible_only: bool = False,
) -> list[GateEvent]:
    """
    Convert an n-dimensional token tensor into a bounded deterministic gate stream.

    Composition rule:
      - traversal is row-major over the n-dimensional tensor;
      - layer = ordinal // q;
      - source qubit is coordinate-sensitive;
      - cx target depends on the active axis and token value;
      - reversible_only coerces all events into x/cx.
    """
    q = max(1, min(max_qubits, spec.root, len(indexes)))
    max_events = max(1, max_layers) * q
    events: list[GateEvent] = []

    for ordinal, token in enumerate(indexes[:max_events]):
        coord = index_to_coord(ordinal, spec.shape)
        layer = ordinal // q
        axis = ordinal % spec.dimension
        gate = DEFAULT_GATES[token % len(DEFAULT_GATES)]
        if reversible_only:
            gate = "cx" if (token % 2 == 1 and q > 1) else "x"

        control = qubit_from_coord(coord, token, q)
        if gate == "cx" and q > 1:
            target = target_from_axis(control, axis, token, q)
            events.append(GateEvent(layer, coord, int(token), axis, "cx", (control, target), None))
        elif gate == "cx" and q == 1:
            events.append(GateEvent(layer, coord, int(token), axis, "x", (0,), None))
        elif gate in ("rx", "ry", "rz"):
            events.append(GateEvent(layer, coord, int(token), axis, gate, (control,), token_to_angle(int(token))))
        else:
            events.append(GateEvent(layer, coord, int(token), axis, gate, (control,), None))
    return events


def events_to_gate_sequence(events: Sequence[GateEvent]) -> str:
    parts: list[str] = []
    for e in events:
        coord = ",".join(str(x) for x in e.coord)
        prefix = f"L{e.layer}@({coord})/A{e.axis}:"
        if e.gate in ("rx", "ry", "rz"):
            parts.append(f"{prefix}{e.gate}({e.angle},{e.qubits[0]})")
        elif e.gate == "cx":
            parts.append(f"{prefix}cx({e.qubits[0]},{e.qubits[1]})")
        else:
            parts.append(f"{prefix}{e.gate}({e.qubits[0]})")
    return " ".join(parts)


def build_qiskit_circuits(events: Sequence[GateEvent], qubits: int) -> tuple[Any, Any]:
    """Build quantum and classical-shadow Qiskit circuits. Requires qiskit."""
    from qiskit import QuantumCircuit  # type: ignore

    qc = QuantumCircuit(qubits, name="nd_derived_quantum")
    cc = QuantumCircuit(qubits, name="nd_classical_shadow")
    current_layer = -1
    for e in events:
        if current_layer != -1 and e.layer != current_layer:
            qc.barrier()
        current_layer = e.layer

        if e.gate in ("x", "y", "z", "h", "s", "sdg", "t", "tdg"):
            getattr(qc, e.gate)(e.qubits[0])
            if e.gate == "x":
                cc.x(e.qubits[0])
        elif e.gate == "cx":
            qc.cx(e.qubits[0], e.qubits[1])
            cc.cx(e.qubits[0], e.qubits[1])
        elif e.gate in ("rx", "ry", "rz"):
            getattr(qc, e.gate)(float(e.angle or 0.0), e.qubits[0])
        else:
            raise ValueError(f"unsupported gate: {e.gate}")
    return qc, cc


def save_circuit_png(qc: Any, path: str) -> None:
    from qiskit.visualization import circuit_drawer  # type: ignore

    circuit_drawer(qc, output="mpl", filename=path)


# -----------------------------------------------------------------------------
# Semantic free-category derivation
# -----------------------------------------------------------------------------


def derive_semantic_category(
    indexes: Sequence[int],
    hex_colors: Sequence[str],
    spec: DimensionSpec,
    max_cells: int = 512,
    max_qubits: int = 8,
    reversible_only: bool = False,
) -> dict[str, Any]:
    q = max(1, min(max_qubits, spec.root, len(indexes)))
    window = min(len(indexes), max(1, max_cells))
    obj_set: set[str] = set()
    rgb_sum: dict[str, list[float]] = {}
    rgb_n: dict[str, int] = {}
    gen: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add_obj(sym: str, color: str) -> None:
        obj_set.add(sym)
        r, g, b = hex_to_rgb01(color)
        if sym not in rgb_sum:
            rgb_sum[sym] = [0.0, 0.0, 0.0]
            rgb_n[sym] = 0
        rgb_sum[sym][0] += r
        rgb_sum[sym][1] += g
        rgb_sum[sym][2] += b
        rgb_n[sym] += 1

    def add_edge(src: str, dst: str, kind: str, coord: tuple[int, ...]) -> None:
        key = (src, dst, kind)
        if key not in gen:
            gen[key] = {"src": src, "dst": dst, "kind": kind, "count": 0, "examples": []}
        gen[key]["count"] += 1
        if len(gen[key]["examples"]) < 12:
            gen[key]["examples"].append({"at": list(coord)})

    for flat in range(window):
        coord = index_to_coord(flat, spec.shape)
        token = indexes[flat]
        sym = token_to_semantic_symbol(token, q=q, axis=flat % spec.dimension, reversible_only=reversible_only)
        add_obj(sym, hex_colors[flat])

        for axis, size in enumerate(spec.shape):
            nxt = list(coord)
            if coord[axis] + 1 >= size:
                continue
            nxt[axis] += 1
            nflat = coord_to_index(nxt, spec.shape)
            if nflat >= window:
                continue
            ntoken = indexes[nflat]
            nsym = token_to_semantic_symbol(ntoken, q=q, axis=axis, reversible_only=reversible_only)
            add_obj(nsym, hex_colors[nflat])
            add_edge(sym, nsym, f"A{axis}", coord)

    objects = sorted(obj_set)
    obj_color: dict[str, str] = {}
    for oid in objects:
        n = max(1, rgb_n.get(oid, 1))
        rgb = [rgb_sum[oid][i] / n for i in range(3)]
        obj_color[oid] = "#" + "".join(f"{int(max(0, min(255, round(v * 255)))):02x}" for v in rgb)

    generators = []
    for key, payload in gen.items():
        src, dst, kind = key
        count = int(payload["count"])
        generators.append(
            {
                "src": src,
                "dst": dst,
                "kind": kind,
                "count": count,
                "label": f"{kind}×{count}",
                "examples": payload["examples"],
            }
        )
    generators.sort(key=lambda e: (e["src"], e["dst"], e["kind"]))

    return {
        "kind": "nd_semantic_free_category_presentation",
        "objects": [{"id": oid, "color": obj_color[oid]} for oid in objects],
        "generators": generators,
        "composition": "paths in the free category over the n-dimensional adjacency generator graph",
        "identities": "implicit identity morphism for each object",
        "window": {"cells": window, "q": q, **spec.to_dict()},
        "reversible_only": bool(reversible_only),
    }


# -----------------------------------------------------------------------------
# Rendering helpers
# -----------------------------------------------------------------------------


def combine_pngs_side_by_side(left_path: str, right_path: str, out_path: str) -> None:
    from PIL import Image, ImageChops  # type: ignore

    def trim(im: Any, bg_rgb: tuple[int, int, int] = (255, 255, 255), pad: int = 16) -> Any:
        rgb = im.convert("RGB")
        bg = Image.new("RGB", rgb.size, bg_rgb)
        diff = ImageChops.difference(rgb, bg).convert("L")
        diff = diff.point(lambda p: 255 if p > 10 else 0)
        bbox = diff.getbbox()
        if not bbox:
            return im
        x0, y0, x1, y1 = bbox
        return im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)))

    a = trim(Image.open(left_path).convert("RGBA"))
    b = trim(Image.open(right_path).convert("RGBA"))
    target_h = max(a.height, b.height)

    def resize_to_h(im: Any, h: int) -> Any:
        if im.height == h:
            return im
        w = int(round(im.width * (h / float(im.height))))
        return im.resize((w, h), resample=Image.Resampling.LANCZOS)

    a2 = resize_to_h(a, target_h)
    b2 = resize_to_h(b, target_h)
    pad = 24
    canvas = Image.new("RGBA", (a2.width + b2.width + pad * 3, target_h + pad * 2), (255, 255, 255, 255))
    canvas.paste(a2, (pad, pad), a2)
    canvas.paste(b2, (pad * 2 + a2.width, pad), b2)
    canvas.convert("RGB").save(out_path)


def render_projection_png(
    indexes: Sequence[int],
    hex_colors: Sequence[str],
    spec: DimensionSpec,
    out_path: str,
    axis_a: int = 0,
    axis_b: int = 1,
    fixed: Optional[dict[int, int]] = None,
    show_labels: bool = False,
) -> None:
    """Render a 2D slice/projection of an n-dimensional tensor."""
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError("Missing dependency: matplotlib. Install with: pip install matplotlib") from e

    if spec.dimension < 2:
        raise ValueError("projection rendering requires dimension >= 2")
    if axis_a == axis_b or axis_a < 0 or axis_b < 0 or axis_a >= spec.dimension or axis_b >= spec.dimension:
        raise ValueError("axis_a and axis_b must be distinct valid axes")
    fixed = dict(fixed or {})
    for axis in range(spec.dimension):
        if axis not in (axis_a, axis_b):
            fixed.setdefault(axis, 0)

    w = spec.shape[axis_b]
    h = spec.shape[axis_a]
    fig_w = max(4.0, float(w) * 1.05)
    fig_h = max(4.0, float(h) * 1.05)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    for ra in range(h):
        for cb in range(w):
            coord = [0] * spec.dimension
            for axis, value in fixed.items():
                coord[axis] = value
            coord[axis_a] = ra
            coord[axis_b] = cb
            flat = coord_to_index(coord, spec.shape)
            fc = hex_colors[flat]
            ax.add_patch(Rectangle((cb, -ra - 1), 1, 1, facecolor=fc, edgecolor="black", linewidth=1.0))
            if show_labels:
                txt_color = "white" if hex_luma(fc) < 0.45 else "black"
                ax.text(cb + 0.5, -ra - 0.5, str(indexes[flat]), ha="center", va="center", fontsize=6, color=txt_color)

    ax.set_aspect("equal")
    ax.set_xlim(0, w)
    ax.set_ylim(-h, 0)
    ax.set_title(f"projection axes A{axis_a}/A{axis_b}; fixed={fixed}", fontsize=9)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=220, facecolor="white")
    plt.close(fig)


def render_semantic_category_png(category: dict[str, Any], out_path: str, show_edge_labels: bool = True) -> None:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle, FancyArrowPatch
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError("Missing dependency: matplotlib. Install with: pip install matplotlib") from e

    objects = [o["id"] for o in category.get("objects", [])]
    colors = {o["id"]: o.get("color", "#888888") for o in category.get("objects", [])}
    gens = list(category.get("generators", []))
    n = max(1, len(objects))

    pos: dict[str, tuple[float, float]] = {}
    for i, oid in enumerate(objects):
        ang = (2.0 * math.pi * i) / n
        pos[oid] = (math.cos(ang), math.sin(ang))

    def short_label(oid: str) -> str:
        if len(oid) <= 9:
            return oid
        digest = hashlib.sha256(oid.encode("utf-8")).hexdigest()[:4]
        return oid[:5] + "#" + digest

    idx_map = {oid: i for i, oid in enumerate(objects)}
    fig, ax = plt.subplots(figsize=(8.0, 8.0))

    def curve_for(kind: str, src: str, dst: str) -> float:
        if src == dst:
            return 0.35
        axis_num = int(kind[1:]) if kind.startswith("A") and kind[1:].isdigit() else 0
        base = 0.12 + 0.055 * ((axis_num % 5) - 2)
        base += ((idx_map[src] - idx_map[dst]) % 7 - 3) * 0.01
        return base

    for e in gens:
        src = e.get("src")
        dst = e.get("dst")
        if src not in pos or dst not in pos:
            continue
        x0, y0 = pos[src]
        x1, y1 = pos[dst]
        kind = str(e.get("kind", "A0"))
        rad = curve_for(kind, src, dst)
        arrow = FancyArrowPatch(
            (x0, y0),
            (x1, y1),
            arrowstyle="->",
            mutation_scale=12,
            linewidth=1.1,
            color="black",
            connectionstyle=f"arc3,rad={rad}",
        )
        ax.add_patch(arrow)
        if show_edge_labels and int(e.get("count", 1) or 1) > 1:
            mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            ax.text(mx, my + rad * 0.35, f"{kind}×{int(e.get('count', 1))}", ha="center", va="center", fontsize=8)

    radius = 0.13
    for oid in objects:
        x, y = pos[oid]
        fc = colors.get(oid, "#888888")
        ax.add_patch(Circle((x, y), radius=radius, facecolor=fc, edgecolor="black", linewidth=1.2))
        txt_color = "white" if hex_luma(fc) < 0.45 else "black"
        ax.text(x, y, short_label(oid), ha="center", va="center", fontsize=8, color=txt_color)

    ax.set_aspect("equal")
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-1.35, 1.35)
    ax.axis("off")
    fig.savefig(out_path, dpi=220, bbox_inches="tight", pad_inches=0.2, facecolor="white")
    plt.close(fig)


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------


def raw_state_from_args(args: argparse.Namespace) -> str:
    if getattr(args, "state", None):
        return str(args.state)
    if getattr(args, "infile", None):
        return read_text_file(str(args.infile))
    raise ValueError("missing --state or --in")


def accepted_report_from_args(args: argparse.Namespace) -> AcceptanceReport:
    raw = raw_state_from_args(args)
    dec = parse_state_to_decimal_string(raw)
    return verify_acceptance(
        dec,
        dimension=int(args.dimension),
        min_root=int(args.min_root),
        segment_length=int(args.segment_len),
        wrap_adjacency=bool(args.wrap),
    )


def cmd_accept(args: argparse.Namespace) -> int:
    report = accepted_report_from_args(args)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"Acceptance check: {report.reason}")
        if report.spec:
            print(f"Tensor: shape={report.spec.shape}, L={report.spec.length}, n={report.spec.dimension}, m={report.spec.root}")
        if args.show_indexes:
            print("Indexes:")
            print(" ".join(str(x) for x in report.indexes))
        if args.show_hex and report.hex_colors:
            print("HEX colours:")
            print(" ".join(report.hex_colors))
    return 0 if report.ok else 1


def cmd_derive(args: argparse.Namespace) -> int:
    report = accepted_report_from_args(args)
    if not report.ok or report.spec is None:
        print(f"Acceptance check: {report.reason}", file=sys.stderr)
        return 1
    ensure_dir(args.outdir)
    events = derive_gate_events(
        report.indexes,
        report.spec,
        max_qubits=args.max_qubits,
        max_layers=args.max_layers,
        reversible_only=args.reversible_only,
    )
    q = max(1, min(args.max_qubits, report.spec.root, len(report.indexes)))

    events_path = os.path.join(args.outdir, "nd_gate_events.json")
    seq_path = os.path.join(args.outdir, "nd_gate_sequence.txt")
    manifest_path = os.path.join(args.outdir, "nd_derive_manifest.json")
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump([e.to_dict() for e in events], f, indent=2)
    with open(seq_path, "w", encoding="utf-8") as f:
        f.write(events_to_gate_sequence(events) + "\n")

    outputs = [events_path, seq_path]
    qiskit_status = "not_requested"
    if not args.no_qiskit:
        try:
            qc, cc = build_qiskit_circuits(events, q)
            qasm_path = os.path.join(args.outdir, "nd_quantum_qiskit.txt")
            cseq_path = os.path.join(args.outdir, "nd_classical_shadow_qiskit.txt")
            with open(qasm_path, "w", encoding="utf-8") as f:
                f.write(str(qc) + "\n")
            with open(cseq_path, "w", encoding="utf-8") as f:
                f.write(str(cc) + "\n")
            outputs.extend([qasm_path, cseq_path])
            qiskit_status = "built"
            if not args.no_png:
                qpng = os.path.join(args.outdir, "nd_quantum.png")
                cpng = os.path.join(args.outdir, "nd_classical_shadow.png")
                save_circuit_png(qc, qpng)
                save_circuit_png(cc, cpng)
                outputs.extend([qpng, cpng])
                try:
                    apng = os.path.join(args.outdir, "nd_circuit_assembly.png")
                    combine_pngs_side_by_side(qpng, cpng, apng)
                    outputs.append(apng)
                except Exception:
                    pass
        except ModuleNotFoundError as e:
            qiskit_status = f"missing optional dependency: {e.name}"
        except Exception as e:
            qiskit_status = f"qiskit/render failed: {e}"

    manifest = {
        "accepted": True,
        "spec": report.spec.to_dict(),
        "max_qubits": args.max_qubits,
        "max_layers": args.max_layers,
        "actual_qubits": q,
        "event_count": len(events),
        "reversible_only": bool(args.reversible_only),
        "qiskit_status": qiskit_status,
        "outputs": outputs,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    outputs.append(manifest_path)

    print("Wrote:")
    for p in outputs:
        print(f"  {p}")
    return 0


def cmd_category(args: argparse.Namespace) -> int:
    report = accepted_report_from_args(args)
    if not report.ok or report.spec is None:
        print(f"Acceptance check: {report.reason}", file=sys.stderr)
        return 1
    ensure_dir(args.outdir)
    cat = derive_semantic_category(
        report.indexes,
        report.hex_colors,
        report.spec,
        max_cells=args.max_cells,
        max_qubits=args.max_qubits,
        reversible_only=args.reversible_only,
    )
    cat_path = os.path.join(args.outdir, "nd_category.json")
    with open(cat_path, "w", encoding="utf-8") as f:
        json.dump(cat, f, indent=2)
    outputs = [cat_path]

    if not args.no_png:
        try:
            projection_png = os.path.join(args.outdir, "nd_projection.png")
            render_projection_png(
                report.indexes,
                report.hex_colors,
                report.spec,
                projection_png,
                axis_a=args.axis_a,
                axis_b=args.axis_b,
                fixed=parse_fixed_axes(args.fixed),
                show_labels=args.show_labels,
            )
            outputs.append(projection_png)
        except Exception as e:
            print(f"Projection PNG render failed: {e}", file=sys.stderr)
        try:
            cat_png = os.path.join(args.outdir, "nd_category.png")
            render_semantic_category_png(cat, cat_png, show_edge_labels=not args.hide_edge_labels)
            outputs.append(cat_png)
        except Exception as e:
            print(f"Category PNG render failed: {e}", file=sys.stderr)
        if args.assembly:
            try:
                projection_png = os.path.join(args.outdir, "nd_projection.png")
                cat_png = os.path.join(args.outdir, "nd_category.png")
                assembly_png = os.path.join(args.outdir, "nd_category_assembly.png")
                if os.path.exists(projection_png) and os.path.exists(cat_png):
                    combine_pngs_side_by_side(projection_png, cat_png, assembly_png)
                    outputs.append(assembly_png)
            except Exception:
                pass

    manifest_path = os.path.join(args.outdir, "nd_category_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"spec": report.spec.to_dict(), "outputs": outputs, "category_kind": cat["kind"]}, f, indent=2)
    outputs.append(manifest_path)

    print("Wrote:")
    for p in outputs:
        print(f"  {p}")
    return 0


def parse_fixed_axes(text: Optional[str]) -> dict[int, int]:
    if not text:
        return {}
    out: dict[int, int] = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError("fixed axes must use axis=value pairs, e.g. 2=0,3=1")
        k, v = part.split("=", 1)
        out[int(k.strip())] = int(v.strip())
    return out


def cmd_projection(args: argparse.Namespace) -> int:
    report = accepted_report_from_args(args)
    if not report.ok or report.spec is None:
        print(f"Acceptance check: {report.reason}", file=sys.stderr)
        return 1
    ensure_dir(args.outdir)
    out_path = os.path.join(args.outdir, args.output)
    render_projection_png(
        report.indexes,
        report.hex_colors,
        report.spec,
        out_path,
        axis_a=args.axis_a,
        axis_b=args.axis_b,
        fixed=parse_fixed_axes(args.fixed),
        show_labels=args.show_labels,
    )
    print(f"Wrote: {out_path}")
    return 0


def cmd_fabric(args: argparse.Namespace) -> int:
    Lmax = max_primary_length(args.h, args.s, args.p)
    rows = valid_lengths_up_to(Lmax, args.dimension, args.min_root)
    nearest = nearest_valid_length(args.target, args.dimension, args.min_root, Lmax) if args.target else None
    payload = {
        "p": args.p,
        "h": args.h,
        "s": args.s,
        "n": args.dimension,
        "min_root": args.min_root,
        "Lmax": Lmax,
        "valid_lengths": rows,
        "target_nearest": nearest,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"p={args.p} h={args.h} s={args.s} n={args.dimension} min_root={args.min_root}")
        print(f"Lmax={Lmax}; valid L=m^n count={len(rows)}")
        if nearest:
            print(f"nearest(target={args.target})={nearest}")
        print("valid lengths:")
        for r in rows[: args.limit]:
            print(f"  L={r['L']} m={r['m']}")
        if len(rows) > args.limit:
            print(f"  ... {len(rows) - args.limit} more")
    return 0


def cmd_match_text(args: argparse.Namespace) -> int:
    if args.text_file:
        text = read_text_file(args.text_file)
    elif args.text is not None:
        text = args.text
    else:
        text = sys.stdin.read()
    analysis = analyze_text(text)
    matches = rank_text_matches(
        analysis,
        dimension=args.dimension,
        min_root=args.min_root,
        limit=args.limit,
        primary_min=args.primary_min,
        primary_max=args.primary_max,
        h_radius=args.h_radius,
    )
    payload = {"analysis": analysis, "matches": matches}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Text length={analysis['char_length']} unique={analysis['unique_count']} lines={analysis['line_count']}")
        print(f"Unique preview: {analysis['preview']}")
        print("Ranked matches:")
        for i, row in enumerate(matches, 1):
            print(
                f"  {i:02d}. score={row['score']} p={row['p']}({row['base_type']}) h={row['h']} "
                f"s={row['s']} n={row['n']} Lmax={row['Lmax']} closest_L={row['closest_L']} "
                f"m={row['m']} gap={row['gap']} exact={row['exact']}"
            )
    return 0


def cmd_menu(_: argparse.Namespace) -> int:
    print("\n9.py — General Dimensional Circuit Composition Utility\n")
    while True:
        try:
            mode = input("1=accept 2=derive 3=category 4=fabric 5=exit: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if mode == "5":
            return 0
        if mode not in {"1", "2", "3", "4"}:
            print("Unknown mode.\n")
            continue
        if mode == "4":
            p = int(input("primary alphabet p [7]: ").strip() or "7")
            h = int(input("secondary alphabet h [10]: ").strip() or "10")
            s = int(input("secondary length s [5]: ").strip() or "5")
            n = int(input("dimension n [2]: ").strip() or "2")
            ns = argparse.Namespace(p=p, h=h, s=s, dimension=n, min_root=2, target=0, limit=50, json=False)
            cmd_fabric(ns)
            print()
            continue
        raw = input("Accepted state decimal/0b: ").strip()
        n = int(input("dimension n [2]: ").strip() or "2")
        outdir = input("outdir [out9]: ").strip() or "out9"
        base = argparse.Namespace(
            state=raw,
            infile=None,
            dimension=n,
            min_root=2,
            segment_len=SEGMENT_LEN,
            wrap=False,
            outdir=outdir,
        )
        if mode == "1":
            ns = argparse.Namespace(**base.__dict__, json=False, show_indexes=False, show_hex=False)
            cmd_accept(ns)
        elif mode == "2":
            ns = argparse.Namespace(
                **base.__dict__,
                max_qubits=8,
                max_layers=16,
                reversible_only=False,
                no_qiskit=False,
                no_png=False,
            )
            cmd_derive(ns)
        elif mode == "3":
            ns = argparse.Namespace(
                **base.__dict__,
                max_cells=512,
                max_qubits=8,
                reversible_only=False,
                no_png=False,
                axis_a=0,
                axis_b=1,
                fixed=None,
                show_labels=False,
                hide_edge_labels=False,
                assembly=True,
            )
            cmd_category(ns)
        print()


# -----------------------------------------------------------------------------
# CLI wiring
# -----------------------------------------------------------------------------


def add_state_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", type=str, default=None, help="State as decimal or 0b... binary")
    parser.add_argument("--in", dest="infile", type=str, default=None, help="Read state from a text file")
    parser.add_argument("--dimension", "-n", type=int, default=2, help="Tensor dimension n in L=m^n")
    parser.add_argument("--min-root", type=int, default=2, help="Minimum tensor root m")
    parser.add_argument("--segment-len", type=int, default=SEGMENT_LEN, help="Decimal segment length for colour tokens")
    parser.add_argument("--wrap", action="store_true", help="Check wrap-around adjacency along every dimension axis")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="9.py",
        description="General n-dimensional accepted-state -> circuit/category/projection/fabric utility.",
    )
    sub = p.add_subparsers(dest="cmd", required=False)

    pa = sub.add_parser("accept", help="Run general n-dimensional acceptance check")
    add_state_args(pa)
    pa.add_argument("--json", action="store_true", help="Emit JSON report")
    pa.add_argument("--show-indexes", action="store_true", help="Show decoded colour indexes")
    pa.add_argument("--show-hex", action="store_true", help="Show decoded HEX colours")
    pa.set_defaults(func=cmd_accept)

    pd = sub.add_parser("derive", help="Accept + derive n-dimensional circuit event stream and optional Qiskit outputs")
    add_state_args(pd)
    pd.add_argument("--max-qubits", type=int, default=8)
    pd.add_argument("--max-layers", type=int, default=16)
    pd.add_argument("--reversible-only", action="store_true", help="Force x/cx-only exact classical-shadow mapping")
    pd.add_argument("--outdir", type=str, default="out9")
    pd.add_argument("--no-qiskit", action="store_true", help="Skip Qiskit circuit construction")
    pd.add_argument("--no-png", action="store_true", help="Skip PNG rendering")
    pd.set_defaults(func=cmd_derive)

    pc = sub.add_parser("category", help="Accept + derive n-dimensional semantic free-category presentation")
    add_state_args(pc)
    pc.add_argument("--max-cells", type=int, default=512, help="Maximum tensor cells used for category graph")
    pc.add_argument("--max-qubits", type=int, default=8)
    pc.add_argument("--reversible-only", action="store_true")
    pc.add_argument("--outdir", type=str, default="out9")
    pc.add_argument("--no-png", action="store_true")
    pc.add_argument("--axis-a", type=int, default=0)
    pc.add_argument("--axis-b", type=int, default=1)
    pc.add_argument("--fixed", type=str, default=None, help="Fixed coordinates for other axes, e.g. 2=0,3=1")
    pc.add_argument("--show-labels", action="store_true")
    pc.add_argument("--hide-edge-labels", action="store_true")
    pc.add_argument("--assembly", action="store_true")
    pc.set_defaults(func=cmd_category)

    pp = sub.add_parser("projection", help="Render a 2D projection/slice of an accepted n-dimensional tensor")
    add_state_args(pp)
    pp.add_argument("--outdir", type=str, default="out9")
    pp.add_argument("--output", type=str, default="nd_projection.png")
    pp.add_argument("--axis-a", type=int, default=0)
    pp.add_argument("--axis-b", type=int, default=1)
    pp.add_argument("--fixed", type=str, default=None, help="Fixed coordinates for other axes, e.g. 2=0,3=1")
    pp.add_argument("--show-labels", action="store_true")
    pp.set_defaults(func=cmd_projection)

    pf = sub.add_parser("fabric", help="Compute n-dimensional fabric lengths using p/h/s capacity logic")
    pf.add_argument("--p", type=int, default=7, help="Primary alphabet size")
    pf.add_argument("--h", type=int, default=10, help="Secondary alphabet size")
    pf.add_argument("--s", type=int, default=5, help="Secondary length")
    pf.add_argument("--dimension", "-n", type=int, default=2)
    pf.add_argument("--min-root", type=int, default=2)
    pf.add_argument("--target", type=int, default=0, help="Optional target length for nearest valid search")
    pf.add_argument("--limit", type=int, default=80)
    pf.add_argument("--json", action="store_true")
    pf.set_defaults(func=cmd_fabric)

    pm = sub.add_parser("match-text", help="Analyze pasted/file text and rank dimensional fabric configurations")
    pm.add_argument("--text", type=str, default=None)
    pm.add_argument("--text-file", type=str, default=None)
    pm.add_argument("--dimension", "-n", type=int, default=2)
    pm.add_argument("--min-root", type=int, default=2)
    pm.add_argument("--limit", type=int, default=12)
    pm.add_argument("--primary-min", type=int, default=2)
    pm.add_argument("--primary-max", type=int, default=128)
    pm.add_argument("--h-radius", type=int, default=0)
    pm.add_argument("--json", action="store_true")
    pm.set_defaults(func=cmd_match_text)

    pmenu = sub.add_parser("menu", help="Interactive fallback menu")
    pmenu.set_defaults(func=cmd_menu)

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        return cmd_menu(args)
    if args.cmd in {"accept", "derive", "category", "projection"} and not args.state and not args.infile:
        parser.error(f"{args.cmd} requires --state or --in")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
