#!/usr/bin/env python3
"""
22.py

Command-line REPL for the finite basis-tensor workflow used by 16.cpp.

This version is intentionally terminal-only: no Tkinter, no GUI event loop, and
no window state. The REPL owns the same practical operations that the previous
workbench exposed:

- load a 17.txt-style JSON configuration,
- read 19.txt-style seed records,
- build raw/residue tensor datasets,
- inspect row-space and seed-address metadata,
- print terminal tables,
- export 20.txt-style text,
- save parse-observable JSON,
- execute command scripts.

The program is finite and exact. It drives configured finite raw row spaces and
finite seed-address spaces; it does not perform physics simulation or claim to
generate uncountable objects exactly.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


COMPONENTS = ["p", "q", "m", "g", "alpha", "beta"]
SIGNED_COMPONENTS = {"p", "m", "alpha"}


def app_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def resolve_path(path: str) -> str:
    path = str(path).strip().strip('"')
    if not path:
        return app_dir()
    if os.path.isabs(path):
        return path
    return os.path.join(app_dir(), path)


def safe_preview(data: bytes, limit: int = 80) -> str:
    out: List[str] = []
    for b in data[:limit]:
        if b == 10:
            out.append("\\n")
        elif b == 13:
            out.append("\\r")
        elif b == 9:
            out.append("\\t")
        elif b == 32:
            out.append("\\s")
        elif b == 92:
            out.append("\\\\")
        elif b == 34:
            out.append('\\"')
        elif 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append(f"\\x{b:02x}")
    if len(data) > limit:
        out.append("...")
    return "".join(out)


def bytes_to_display(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return safe_preview(data)


def zigzag(n: int) -> int:
    if n == 0:
        return 0
    if n % 2:
        return (n + 1) // 2
    return -(n // 2)


def positive(n: int) -> int:
    return n + 1


def ceil_kth_root(n: int, k: int) -> int:
    if k < 1 or k > 6:
        raise ValueError("seed length/root exponent must be in 1..6")
    if n < 0:
        raise ValueError("cannot take kth root of a negative integer")
    if n <= 1 or k == 1:
        return n
    lo = 0
    hi = 1
    while hi**k < n:
        hi *= 2
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if mid**k >= n:
            hi = mid
        else:
            lo = mid
    return hi


@dataclass
class ComponentSpec:
    name: str
    alphabet_text: str
    mode: str
    fixed: int = 0
    min_len: int = 0
    max_len: int = 0
    modulus: Optional[int] = None
    alphabet: bytes = field(init=False)
    index: Dict[int, int] = field(init=False)
    domain: int = field(init=False)

    def __post_init__(self) -> None:
        self.alphabet = self.alphabet_text.encode("utf-8")
        if not self.alphabet:
            raise ValueError(f"component {self.name}: alphabet must not be empty")
        self.index = {}
        for i, b in enumerate(self.alphabet):
            if b in self.index:
                raise ValueError(
                    f"component {self.name}: duplicate decoded byte symbol {safe_preview(bytes([b]))}"
                )
            self.index[b] = i
        if self.mode == "fixed":
            if self.fixed < 0:
                raise ValueError(f"component {self.name}: fixed length must be nonnegative")
            self.domain = len(self.alphabet) ** self.fixed
        elif self.mode == "variable":
            if self.min_len < 0 or self.max_len < 0:
                raise ValueError(f"component {self.name}: variable lengths must be nonnegative")
            if self.min_len > self.max_len:
                raise ValueError(f"component {self.name}: min length must be <= max length")
            self.domain = sum(len(self.alphabet) ** ell for ell in range(self.min_len, self.max_len + 1))
        else:
            raise ValueError(f"component {self.name}: length mode must be fixed or variable")
        if self.domain <= 0:
            raise ValueError(f"component {self.name}: raw domain must be positive")
        if self.modulus is None:
            self.modulus = self.domain
        if self.modulus <= 0:
            raise ValueError(f"component {self.name}: modulus must be positive")

    @classmethod
    def from_json(cls, name: str, obj: Dict[str, Any]) -> "ComponentSpec":
        if not isinstance(obj, dict):
            raise ValueError(f"component {name}: component object expected")
        if "alphabet" not in obj:
            raise ValueError(f"component {name}: missing alphabet")
        length = obj.get("length")
        if not isinstance(length, dict):
            raise ValueError(f"component {name}: missing length object")
        modulus = parse_optional_modulus(obj.get("modulus"), f"component {name}.modulus")
        mode = str(length.get("mode", ""))
        if mode == "fixed":
            return cls(
                name=name,
                alphabet_text=str(obj["alphabet"]),
                mode=mode,
                fixed=int(length.get("value")),
                modulus=modulus,
            )
        if mode == "variable":
            return cls(
                name=name,
                alphabet_text=str(obj["alphabet"]),
                mode=mode,
                min_len=int(length.get("min")),
                max_len=int(length.get("max")),
                modulus=modulus,
            )
        raise ValueError(f"component {name}: length mode must be fixed or variable")

    def encode(self, text: str) -> int:
        data = text.encode("utf-8")
        if self.mode == "fixed":
            if len(data) != self.fixed:
                raise ValueError(
                    f"component {self.name}: fixed byte length {len(data)} does not match {self.fixed}"
                )
        else:
            if not (self.min_len <= len(data) <= self.max_len):
                raise ValueError(
                    f"component {self.name}: byte length {len(data)} outside [{self.min_len}, {self.max_len}]"
                )
        r = len(self.alphabet)
        ordinal = 0
        for b in data:
            if b not in self.index:
                raise ValueError(f"component {self.name}: byte {safe_preview(bytes([b]))} is outside alphabet")
            ordinal = ordinal * r + self.index[b]
        if self.mode == "variable":
            ordinal += sum(r**ell for ell in range(self.min_len, len(data)))
        if not (0 <= ordinal < self.domain):
            raise ValueError(f"component {self.name}: internal ordinal outside domain")
        return ordinal

    def decode(self, raw_id: int) -> str:
        if not (0 <= raw_id < self.domain):
            raise ValueError(f"component {self.name}: raw id outside domain")
        if self.mode == "fixed":
            return bytes_to_display(self._decode_fixed(raw_id, self.fixed))
        r = len(self.alphabet)
        offset = 0
        for length in range(self.min_len, self.max_len + 1):
            block = r**length
            if raw_id < offset + block:
                return bytes_to_display(self._decode_fixed(raw_id - offset, length))
            offset += block
        raise ValueError(f"component {self.name}: cannot decode raw id")

    def _decode_fixed(self, ordinal: int, length: int) -> bytes:
        r = len(self.alphabet)
        digits = [0] * length
        n = ordinal
        for pos in range(length - 1, -1, -1):
            n, rem = divmod(n, r)
            digits[pos] = rem
        if n:
            raise ValueError(f"component {self.name}: fixed decode overflow")
        return bytes(self.alphabet[d] for d in digits)

    def policy_label(self) -> str:
        if self.mode == "fixed":
            return f"fixed({self.fixed})"
        return f"variable([{self.min_len},{self.max_len}])"


def parse_optional_modulus(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        if not value.isdigit():
            raise ValueError(f"{field_name}: modulus must be a positive decimal integer")
        parsed = int(value)
    else:
        raise ValueError(f"{field_name}: modulus must be a number or decimal string")
    if parsed <= 0:
        raise ValueError(f"{field_name}: modulus must be positive")
    return parsed


@dataclass
class ScalarInfo:
    P: int
    Q: int
    M: int
    G: int
    Alpha: int
    Beta: int
    reduced_alpha: int
    reduced_beta: int
    expression: str
    status: str


@dataclass
class RowResult:
    block: int
    row_index: int
    row_ordinal: int
    strings: Dict[str, str]
    raw_ids: Dict[str, int]
    residues: Dict[str, int]
    moduli: Dict[str, int]
    mapped: Dict[str, int]
    scalar: ScalarInfo


@dataclass
class SeedBlock:
    block: int
    source_line_number: int
    source_line: str
    seed_sequence: List[int]
    seed_length: int
    seed_radix: int
    decoded_address: int
    effective_address: int
    wrapped: bool
    row_ordinals: List[int]
    rows: List[RowResult]


class TensorEngine:
    def __init__(self) -> None:
        self.config_path = resolve_path("17.txt")
        self.seed_file = resolve_path("19.txt")
        self.basis_out = resolve_path("20.txt")
        self.output_path = resolve_path("basis_tensors.json")
        self.seed_mode = "strict"
        self.seed_output_length = 1
        self.instance_count = 0
        self.components: List[ComponentSpec] = []
        self.inline_instances: List[Dict[str, str]] = []
        self.blocks: List[SeedBlock] = []

    def load_config(self, path: str) -> str:
        self.config_path = resolve_path(path)
        with open(self.config_path, "r", encoding="utf-8") as handle:
            cfg = json.load(handle)
        components_obj = cfg.get("components")
        if not isinstance(components_obj, dict):
            raise ValueError("config: missing components object")
        self.components = [ComponentSpec.from_json(name, components_obj[name]) for name in COMPONENTS]
        self.inline_instances = list(cfg.get("instances", []) or [])
        self.instance_count = int(cfg.get("instance_count", len(self.inline_instances)))
        seed = cfg.get("seed", {}) or {}
        if isinstance(seed, dict):
            self.seed_output_length = int(seed.get("output_length", self.seed_output_length))
            self.seed_file = resolve_path(str(seed.get("seed_file", self.seed_file)))
            self.basis_out = resolve_path(str(seed.get("basis_output_path", self.basis_out)))
            self.seed_mode = str(seed.get("mode", self.seed_mode))
            basis_policy = str(seed.get("basis_policy", "ordered_with_repetition"))
            if basis_policy != "ordered_with_repetition":
                raise ValueError("only ordered_with_repetition basis policy is supported")
        output = cfg.get("output", {}) or {}
        if isinstance(output, dict):
            self.output_path = resolve_path(str(output.get("path", self.output_path)))
        if self.seed_output_length < 1 or self.seed_output_length > 6:
            raise ValueError("seed output length must be in 1..6")
        if self.seed_mode not in ("strict", "wrap"):
            raise ValueError("seed mode must be strict or wrap")
        self.blocks.clear()
        return f"loaded {self.config_path} | N={self.instance_count} R={self.row_space_size()} S={self.basis_space_size()}"

    def require_config(self) -> None:
        if len(self.components) != 6:
            raise ValueError("no configuration loaded; run: load-config 17.txt")

    def row_space_size(self) -> int:
        self.require_config()
        result = 1
        for component in self.components:
            result *= component.domain
        return result

    def basis_space_size(self) -> int:
        return self.row_space_size() ** self.instance_count

    def domains_text(self) -> str:
        self.require_config()
        lines = [
            f"config={self.config_path}",
            f"seed_file={self.seed_file}",
            f"basis_out={self.basis_out}",
            f"output_path={self.output_path}",
            f"N={self.instance_count}",
            f"R={self.row_space_size()}",
            f"S={self.basis_space_size()}",
            f"seed_mode={self.seed_mode}",
            f"seed_output_length={self.seed_output_length}",
        ]
        for component in self.components:
            lines.append(
                f"{component.name}: alphabet_size={len(component.alphabet)} "
                f"policy={component.policy_label()} M={component.domain} "
                f"mu={component.modulus} alphabet={safe_preview(component.alphabet)}"
            )
        return "\n".join(lines)

    def rank_row(self, ids: Sequence[int]) -> int:
        self.require_config()
        acc = ids[0]
        for i in range(1, 6):
            acc = acc * self.components[i].domain + ids[i]
        return acc

    def unrank_row(self, row_ordinal: int) -> List[int]:
        self.require_config()
        ids = [0] * 6
        work = row_ordinal
        for i in range(5, 0, -1):
            work, ids[i] = divmod(work, self.components[i].domain)
        ids[0] = work
        if not (0 <= ids[0] < self.components[0].domain):
            raise ValueError("row ordinal is outside the raw row universe")
        return ids

    def rank_basis(self, rows: Iterable[int]) -> int:
        R = self.row_space_size()
        acc = 0
        for row in rows:
            acc = acc * R + row
        return acc

    def unrank_basis(self, address: int) -> List[int]:
        R = self.row_space_size()
        rows = [0] * self.instance_count
        work = address
        for i in range(self.instance_count - 1, -1, -1):
            work, rows[i] = divmod(work, R)
        if work:
            raise ValueError("basis address is outside the basis address space")
        return rows

    def scalar_info(self, ids: Dict[str, int]) -> ScalarInfo:
        P = zigzag(ids["p"])
        Q = positive(ids["q"])
        M = zigzag(ids["m"])
        G = positive(ids["g"])
        Alpha = zigzag(ids["alpha"])
        Beta = positive(ids["beta"])
        divisor = math.gcd(abs(Alpha), Beta) or 1
        reduced_alpha = Alpha // divisor
        reduced_beta = Beta // divisor
        expression = f"({P} / {Q}) * (({M} / {G}) ^ ({Alpha} / {Beta}))"
        if M == 0:
            status = "undefined_real_expression" if Alpha <= 0 else "real_exact_symbolic"
        elif M > 0:
            status = "real_exact_symbolic"
        else:
            status = "real_exact_symbolic" if reduced_beta % 2 == 1 else "complex_required"
        return ScalarInfo(P, Q, M, G, Alpha, Beta, reduced_alpha, reduced_beta, expression, status)

    def make_row_from_ids(self, block: int, row_index: int, ids_list: Sequence[int], row_ordinal: int) -> RowResult:
        strings: Dict[str, str] = {}
        raw_ids: Dict[str, int] = {}
        residues: Dict[str, int] = {}
        moduli: Dict[str, int] = {}
        mapped: Dict[str, int] = {}
        for component, raw_id in zip(self.components, ids_list):
            strings[component.name] = component.decode(raw_id)
            raw_ids[component.name] = raw_id
            residues[component.name] = raw_id % int(component.modulus)
            moduli[component.name] = int(component.modulus)
            mapped[component.name] = zigzag(raw_id) if component.name in SIGNED_COMPONENTS else positive(raw_id)
        return RowResult(block, row_index, row_ordinal, strings, raw_ids, residues, moduli, mapped, self.scalar_info(raw_ids))

    def make_row_from_strings(self, block: int, row_index: int, strings: Dict[str, str]) -> RowResult:
        ids = [component.encode(str(strings[component.name])) for component in self.components]
        return self.make_row_from_ids(block, row_index, ids, self.rank_row(ids))

    def parse_seed_text(self, text: str) -> List[Tuple[int, str, List[int]]]:
        records: List[Tuple[int, str, List[int]]] = []
        for line_no, original in enumerate(text.splitlines(), start=1):
            line = original.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("["):
                if not line.endswith("]"):
                    raise ValueError(f"seed line {line_no}: missing closing bracket")
                line = line[1:-1]
            parts = line.replace(",", " ").split()
            if not parts or len(parts) > 6:
                raise ValueError(f"seed line {line_no}: seed length must be 1..6")
            sequence: List[int] = []
            for part in parts:
                if not part.isdigit():
                    raise ValueError(f"seed line {line_no}: malformed nonnegative integer {part!r}")
                sequence.append(int(part))
            records.append((line_no, original, sequence))
        return records

    def load_seed_records(self, path: Optional[str] = None) -> List[Tuple[int, str, List[int]]]:
        if path:
            self.seed_file = resolve_path(path)
        with open(self.seed_file, "r", encoding="utf-8") as handle:
            return self.parse_seed_text(handle.read())

    def decode_seed(self, sequence: Sequence[int]) -> Tuple[int, int, int, bool]:
        S = self.basis_space_size()
        k = len(sequence)
        W = ceil_kth_root(S, k)
        decoded = 0
        for digit in sequence:
            decoded = decoded * W + digit
        if self.seed_mode == "strict":
            for digit in sequence:
                if not (0 <= digit < W):
                    raise ValueError(f"strict seed digit {digit} is outside radix {W}")
            if not (0 <= decoded < S):
                raise ValueError(f"strict decoded seed address {decoded} is outside [0, {S - 1}]")
            return W, decoded, decoded, False
        effective = decoded % S
        return W, decoded, effective, effective != decoded

    def build_from_seeds(self, path: Optional[str] = None) -> List[SeedBlock]:
        self.require_config()
        records = self.load_seed_records(path)
        blocks: List[SeedBlock] = []
        for block_index, (line_no, line, sequence) in enumerate(records):
            W, decoded, effective, wrapped = self.decode_seed(sequence)
            row_ordinals = self.unrank_basis(effective)
            rows = [
                self.make_row_from_ids(block_index, i, self.unrank_row(row_ordinal), row_ordinal)
                for i, row_ordinal in enumerate(row_ordinals)
            ]
            blocks.append(
                SeedBlock(
                    block=block_index,
                    source_line_number=line_no,
                    source_line=line,
                    seed_sequence=list(sequence),
                    seed_length=len(sequence),
                    seed_radix=W,
                    decoded_address=decoded,
                    effective_address=effective,
                    wrapped=wrapped,
                    row_ordinals=row_ordinals,
                    rows=rows,
                )
            )
        self.blocks = blocks
        return blocks

    def build_inline(self) -> List[SeedBlock]:
        self.require_config()
        if not self.inline_instances:
            raise ValueError("config has no inline instances; use build-seeds or add instances")
        if len(self.inline_instances) != self.instance_count:
            raise ValueError("inline instance count does not match instance_count")
        rows = [self.make_row_from_strings(0, i, instance) for i, instance in enumerate(self.inline_instances)]
        row_ordinals = [row.row_ordinal for row in rows]
        address = self.rank_basis(row_ordinals)
        W = ceil_kth_root(self.basis_space_size(), self.seed_output_length)
        sequence = [0] * self.seed_output_length
        work = address
        for i in range(self.seed_output_length - 1, -1, -1):
            work, sequence[i] = divmod(work, W)
        self.blocks = [
            SeedBlock(
                block=0,
                source_line_number=0,
                source_line="<inline instances>",
                seed_sequence=sequence,
                seed_length=self.seed_output_length,
                seed_radix=W,
                decoded_address=address,
                effective_address=address,
                wrapped=False,
                row_ordinals=row_ordinals,
                rows=rows,
            )
        ]
        return self.blocks

    def block_summary(self) -> str:
        if not self.blocks:
            return "no generated tensor blocks"
        return "\n".join(
            f"block={block.block} seed={block.seed_sequence} k={block.seed_length} "
            f"W={block.seed_radix} K={block.effective_address} rows={block.row_ordinals}"
            for block in self.blocks
        )

    def table_text(self) -> str:
        if not self.blocks:
            return "no generated tensor blocks"
        rows: List[List[str]] = [[
            "block", "seed", "row", "J", "p", "q", "m", "g", "alpha", "beta", "raw", "residue", "status"
        ]]
        for block in self.blocks:
            seed = "[" + ", ".join(str(x) for x in block.seed_sequence) + "]"
            for row in block.rows:
                rows.append([
                    str(block.block),
                    seed,
                    str(row.row_index),
                    str(row.row_ordinal),
                    row.strings["p"],
                    row.strings["q"],
                    row.strings["m"],
                    row.strings["g"],
                    row.strings["alpha"],
                    row.strings["beta"],
                    "[" + ",".join(str(row.raw_ids[name]) for name in COMPONENTS) + "]",
                    "[" + ",".join(str(row.residues[name]) for name in COMPONENTS) + "]",
                    row.scalar.status,
                ])
        return format_table(rows)

    def residue_grid_text(self) -> str:
        if not self.blocks:
            return "no generated tensor blocks"
        lines = ["Residue grid: columns=p q m g alpha beta"]
        for block in self.blocks:
            lines.append(f"block {block.block} seed={block.seed_sequence} K={block.effective_address}")
            for row in block.rows:
                residues = " ".join(str(row.residues[name]).rjust(3) for name in COMPONENTS)
                lines.append(f"  row {row.row_index:>3} J={row.row_ordinal:<8} {residues}")
        return "\n".join(lines)

    def export_20_text(self, path: Optional[str] = None) -> str:
        self.require_config()
        if path:
            self.basis_out = resolve_path(path)
        if not self.blocks:
            raise ValueError("nothing to export; run build-seeds or build-inline first")
        lines = [
            "22.py deterministic seed-build output",
            f"Configuration: {os.path.basename(self.config_path)}",
            "Component order: p, q, m, g, alpha, beta",
            "Symbol mode: byte-symbol mode; alphabets and input lengths are decoded UTF-8 bytes.",
            "Basis policy: ordered_with_repetition",
            f"Seed mode: {self.seed_mode}",
            f"Basis row count N: {self.instance_count}",
            f"Raw row-space size R: {self.row_space_size()}",
            f"Basis-address-space size S: {self.basis_space_size()}",
            "Component raw domain sizes and residue moduli:",
        ]
        for component in self.components:
            lines.append(f"  {component.name}: M_c={component.domain}, mu_c={component.modulus}")
        for block in self.blocks:
            lines.extend([
                "",
                f"===== BASIS BLOCK {block.block} =====",
                f"source_seed_line_number: {block.source_line_number}",
                f"source_seed_line: {block.source_line}",
                f"parsed_seed_sequence: {block.seed_sequence}",
                f"seed_length: {block.seed_length}",
                f"seed_radix: {block.seed_radix}",
                f"decoded_basis_address_K_seed: {block.decoded_address}",
                f"effective_basis_address_K: {block.effective_address}",
                f"seed_wrapped: {str(block.wrapped).lower()}",
                f"row_ordinals: {block.row_ordinals}",
            ])
            for row in block.rows:
                raw = [row.raw_ids[name] for name in COMPONENTS]
                residue = [row.residues[name] for name in COMPONENTS]
                strings = ", ".join(f"{name}={row.strings[name]!r}" for name in COMPONENTS)
                lines.extend([
                    f"  Row {row.row_index}:",
                    f"    canonical_component_strings: {strings}",
                    f"    raw_ids: {raw}",
                    f"    residue_moduli: {[row.moduli[name] for name in COMPONENTS]}",
                    f"    least_residues: {residue}",
                    "    mapped_structure1_parameters: "
                    f"P={row.scalar.P}, Q={row.scalar.Q}, M={row.scalar.M}, G={row.scalar.G}, "
                    f"Alpha={row.scalar.Alpha}, Beta={row.scalar.Beta}",
                    f"    symbolic_scalar_expression: a_{row.row_index} = {row.scalar.expression}",
                    f"    real_admissibility_status: {row.scalar.status}",
                ])
            lines.append(f"B_raw: {[[row.raw_ids[name] for name in COMPONENTS] for row in block.rows]}")
            lines.append(f"B_residue: {[[row.residues[name] for name in COMPONENTS] for row in block.rows]}")
        text = "\n".join(lines) + "\n"
        with open(self.basis_out, "w", encoding="utf-8") as handle:
            handle.write(text)
        return self.basis_out

    def records_json(self) -> Dict[str, Any]:
        self.require_config()
        return {
            "metadata": {
                "source": "22.py command-line tensor REPL",
                "config_path": self.config_path,
                "seed_file": self.seed_file,
                "basis_output_path": self.basis_out,
                "component_order": COMPONENTS,
                "row_space_size": str(self.row_space_size()),
                "basis_address_space_size": str(self.basis_space_size()),
                "seed_mode": self.seed_mode,
            },
            "blocks": [
                {
                    "block": block.block,
                    "source_seed_line_number": str(block.source_line_number),
                    "source_seed_line": block.source_line,
                    "source_seed_sequence": [str(x) for x in block.seed_sequence],
                    "seed_length": str(block.seed_length),
                    "seed_radix": str(block.seed_radix),
                    "decoded_seed_address": str(block.decoded_address),
                    "effective_basis_address": str(block.effective_address),
                    "seed_wrapped": block.wrapped,
                    "row_ordinals": [str(x) for x in block.row_ordinals],
                    "raw_basis_tensor_dataset": [
                        [str(row.raw_ids[name]) for name in COMPONENTS] for row in block.rows
                    ],
                    "residue_basis_tensor_dataset": [
                        [str(row.residues[name]) for name in COMPONENTS] for row in block.rows
                    ],
                }
                for block in self.blocks
            ],
        }

    def save_json(self, path: Optional[str] = None) -> str:
        if path:
            self.output_path = resolve_path(path)
        with open(self.output_path, "w", encoding="utf-8") as handle:
            json.dump(self.records_json(), handle, indent=2)
            handle.write("\n")
        return self.output_path


def format_table(rows: Sequence[Sequence[str]]) -> str:
    widths = [0] * max(len(row) for row in rows)
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    lines: List[str] = []
    for row_index, row in enumerate(rows):
        line = "  ".join(str(cell).ljust(widths[index]) for index, cell in enumerate(row))
        lines.append(line.rstrip())
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths).rstrip())
    return "\n".join(lines)


class TensorRepl:
    def __init__(self, engine: Optional[TensorEngine] = None, quiet: bool = False) -> None:
        self.engine = engine or TensorEngine()
        self.quiet = quiet
        self.running = True

    def println(self, text: str = "") -> None:
        if not self.quiet:
            print(text)

    def execute(self, line: str, echo: bool = False) -> str:
        line = line.strip()
        if not line or line.startswith("#"):
            return ""
        if echo:
            self.println(f"> {line}")
        try:
            result = self.dispatch(line)
        except Exception as exc:
            result = f"error: {exc}"
        if result and not self.quiet:
            print(result)
        return result

    def dispatch(self, line: str) -> str:
        try:
            parts = shlex.split(line, posix=False)
        except ValueError:
            parts = line.split()
        if not parts:
            return ""
        cmd = parts[0].lower()
        args = [part.strip('"') for part in parts[1:]]

        if cmd in {"help", "?"}:
            return HELP_TEXT.strip()
        if cmd in {"quit", "exit"}:
            self.running = False
            return "bye"
        if cmd == "load-config":
            return self.engine.load_config(args[0] if args else "17.txt")
        if cmd == "load-seeds":
            path = args[0] if args else None
            records = self.engine.load_seed_records(path)
            return f"loaded {len(records)} seed records from {self.engine.seed_file}"
        if cmd == "build-seeds":
            blocks = self.engine.build_from_seeds(args[0] if args else None)
            return f"built {len(blocks)} tensor block(s) from seeds"
        if cmd == "build-inline":
            blocks = self.engine.build_inline()
            return f"built {len(blocks)} tensor block(s) from inline instances"
        if cmd == "show-config":
            return (
                f"config={self.engine.config_path}\n"
                f"seed_file={self.engine.seed_file}\n"
                f"basis_out={self.engine.basis_out}\n"
                f"output_path={self.engine.output_path}"
            )
        if cmd == "show-domains":
            return self.engine.domains_text()
        if cmd == "summary":
            return self.engine.block_summary()
        if cmd in {"table", "tensor-table"}:
            return self.engine.table_text()
        if cmd in {"grid", "visualize", "residue-grid"}:
            return self.engine.residue_grid_text()
        if cmd == "clear":
            self.engine.blocks.clear()
            return "cleared generated tensor blocks"
        if cmd == "export-20":
            return f"exported {self.engine.export_20_text(args[0] if args else None)}"
        if cmd == "save-json":
            return f"saved {self.engine.save_json(args[0] if args else None)}"
        if cmd == "set":
            return self.set_command(args)
        if cmd == "run-script":
            if not args:
                raise ValueError("usage: run-script PATH")
            return self.run_script(args[0], echo=True)
        if cmd == "compile16":
            return self.run_external(["c++", "-std=c++17", "-Wall", "-Wextra", "-pedantic", "-O2", "16.cpp", "-o", "basis_tensor"])
        if cmd == "selftest16":
            exe = "basis_tensor.exe" if os.name == "nt" else "./basis_tensor"
            return self.run_external([exe, "--self-test"])
        raise ValueError(f"unknown command {cmd!r}; type help")

    def set_command(self, args: Sequence[str]) -> str:
        if len(args) < 2:
            raise ValueError("usage: set seed-mode strict|wrap | set seed-length 1..6 | set seed-file PATH | set basis-out PATH | set output-path PATH")
        key = args[0].lower()
        value = " ".join(args[1:])
        if key == "seed-mode":
            if value not in {"strict", "wrap"}:
                raise ValueError("seed mode must be strict or wrap")
            self.engine.seed_mode = value
        elif key == "seed-length":
            seed_length = int(value)
            if seed_length < 1 or seed_length > 6:
                raise ValueError("seed length must be 1..6")
            self.engine.seed_output_length = seed_length
        elif key == "seed-file":
            self.engine.seed_file = resolve_path(value)
        elif key == "basis-out":
            self.engine.basis_out = resolve_path(value)
        elif key == "output-path":
            self.engine.output_path = resolve_path(value)
        else:
            raise ValueError(f"unknown setting {key!r}")
        return f"set {key}={value}"

    def run_external(self, argv: Sequence[str]) -> str:
        completed = subprocess.run(
            list(argv),
            cwd=app_dir(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output = completed.stdout.strip()
        if output:
            return output
        return f"process exited with {completed.returncode}"

    def run_script(self, path: str, echo: bool = False) -> str:
        script_path = resolve_path(path)
        count = 0
        with open(script_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                self.execute(line, echo=echo)
                count += 1
                if not self.running:
                    break
        return f"ran {count} command(s) from {script_path}"

    def loop(self) -> int:
        print("22.py tensor REPL. Type 'help' for commands; 'quit' to exit.")
        while self.running:
            try:
                line = input("tensor> ")
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print("\ninterrupt")
                continue
            self.execute(line)
        return 0


HELP_TEXT = """
Commands:
  help
  quit | exit
  load-config [path]       Load a 17.txt-style JSON config.
  load-seeds [path]        Load/validate 19.txt-style seed records.
  build-seeds [path]       Build tensor blocks from seeds.
  build-inline             Build from inline instances in the config.
  show-config              Show active paths.
  show-domains             Show component domains, R, S, and seed settings.
  summary                  Show generated block summaries.
  table                    Print raw/residue tensor table.
  grid                     Print compact residue grid.
  clear                    Clear generated tensor blocks.
  export-20 [path]         Export 20.txt-style seed-build text.
  save-json [path]         Save parse-observable JSON.
  set seed-mode strict|wrap
  set seed-length 1..6
  set seed-file PATH
  set basis-out PATH
  set output-path PATH
  run-script PATH          Execute a text file of REPL commands.
  compile16                Compile 16.cpp if c++ is available.
  selftest16               Run basis_tensor --self-test if compiled.

Script files are plain text. Blank lines and lines starting with # are ignored.
The seed sequence addresses B_raw. It is metadata, not a tensor coordinate.
"""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Command-line REPL for the finite basis-tensor workflow.")
    parser.add_argument("--config", default=None, help="Load configuration before executing commands or entering REPL.")
    parser.add_argument("--seed-file", default=None, help="Set seed-file path before executing commands or entering REPL.")
    parser.add_argument("--command", "-c", action="append", default=[], help="Run a REPL command. Can be repeated.")
    parser.add_argument("--script", help="Run a REPL command script.")
    parser.add_argument("--batch", action="store_true", help="Run commands/scripts and exit instead of entering the interactive REPL.")
    parser.add_argument("--quiet", action="store_true", help="Suppress command output where possible.")
    parser.add_argument("--self-check", action="store_true", help="Load 17.txt, build from 19.txt, print summary, and exit.")
    parser.add_argument("--no-gui-self-check", action="store_true", help="Compatibility alias for --self-check.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    repl = TensorRepl(quiet=args.quiet)

    try:
        if args.config:
            repl.println(repl.engine.load_config(args.config))
        if args.seed_file:
            repl.engine.seed_file = resolve_path(args.seed_file)
            repl.println(f"set seed-file={repl.engine.seed_file}")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.self_check or args.no_gui_self_check:
        repl.execute("load-config 17.txt")
        repl.execute("build-seeds 19.txt")
        repl.execute("summary")
        return 0

    for command in args.command:
        repl.execute(command)
    if args.script:
        repl.run_script(args.script, echo=not args.quiet)

    if args.batch or args.command or args.script:
        return 0
    return repl.loop()


if __name__ == "__main__":
    raise SystemExit(main())
