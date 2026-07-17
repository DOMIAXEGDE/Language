#!/usr/bin/env python3
"""
format_paste.py

Local companion tool for the TR Tensor application.

It turns arbitrary text into Tensor-compatible paste/import inputs. The output can
be generated as tensor_text, databank_text, json_workspace, json_records,
csv_records, jsonl, markdown, summary, or dot.

The tool categorizes source text into document, paragraph, sentence, word, line,
code_block, code_line, heading, and list_item entries by default. A formatting
profile can change category selection, bank/register/address mapping, regexes,
and pointer generation rules without changing this script.
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


TOOL_DIR = Path(__file__).resolve().parent
DEFAULT_TENSOR_CONFIG_PATH = TOOL_DIR / "spec" / "config-id.json"

COMPATIBLE_OUTPUT_FORMATS = {
    "tensor_text",
    "databank_text",
    "json_workspace",
    "json_records",
    "csv_records",
    "jsonl",
    "markdown",
    "summary",
    "dot",
}


DEFAULT_TENSOR_CONFIG: Dict[str, Any] = {
    "config_id": "tensor-default-v1",
    "description": "Default Tensor parser: block files such as Tensor.txt plus CLIX/DataBank-compatible flows.",
    "input": {
        "format_id": "tensor-block-v1",
        "encoding": "utf-8",
        "merge_mode": "replace",
        "default_bank_id": "1",
        "default_register_id": "1",
    },
    "id": {
        "prefix": "x",
        "base": 10,
        "width_bank": 17,
        "width_register": 17,
        "width_address": 17,
        "strip_prefix_on_parse": True,
        "canonicalize_numeric_ids": True,
        "allow_duplicate_values": True,
    },
    "limits": {
        "max_resolve_depth": 32,
        "max_file_bytes": 20_000_000,
        "max_undo": 64,
    },
    "references": {
        "reading_mode": "raw",
        "two_part_mode": "bank_address",
        "missing": "[Missing Ref: {ref}]",
        "circular": "[Circular Ref: {ref}]",
        "depth_exceeded": "[Resolver Depth Exceeded]",
        "patterns": {
            "prefixed_full": r"(?<![A-Za-z0-9_])x(?P<bank>[0-9A-Za-z]+)\.(?P<register>[0-9A-Za-z]+)\.(?P<address>[0-9A-Za-z]+)(?![A-Za-z0-9_])",
            "local_register": r"(?<![A-Za-z0-9_])r(?P<register>[0-9A-Za-z]+)\.(?P<address>[0-9A-Za-z]+)(?![A-Za-z0-9_])",
            "full": r"(?<![A-Za-z0-9_])(?P<bank>[0-9A-Za-z]+)\.(?P<register>[0-9A-Za-z]+)\.(?P<address>[0-9A-Za-z]+)(?![A-Za-z0-9_])",
            "two_part": r"(?<![A-Za-z0-9_])(?P<left>[0-9A-Za-z]+)\.(?P<right>[0-9A-Za-z]+)(?![A-Za-z0-9_])",
        },
    },
    "processing": {
        "pipeline": [],
        "available_ops": [
            "trim",
            "lower",
            "upper",
            "resolve",
            "replace_regex",
            "prefix",
            "suffix",
            "token_count",
            "char_count",
            "drop_empty",
        ],
    },
    "output": {
        "format": "json",
        "encoding": "utf-8",
        "include_meta": True,
        "sort": True,
        "indent": 2,
        "use_original_ids_when_available": True,
        "quote_multiline": True,
    },
}


DEFAULT_FORMAT_PROFILE: Dict[str, Any] = {
    "profile_id": "format-paste-default-v1",
    "description": "Default paste formatter profile for Tensor-compatible categorised text imports.",
    "bank": {
        "id": "1",
        "title": "format_paste",
        "raw_id": "x1",
    },
    "categories": {
        "enabled": [
            "document",
            "paragraph",
            "sentence",
            "word",
            "line",
            "code_block",
            "code_line",
            "heading",
            "list_item",
        ],
        "registers": {
            "document": "1",
            "paragraph": "10",
            "sentence": "20",
            "word": "30",
            "line": "40",
            "code_block": "50",
            "code_line": "60",
            "heading": "70",
            "list_item": "80",
            "pointer": "900",
        },
        "titles": {
            "document": "Document",
            "paragraph": "Paragraphs",
            "sentence": "Sentences",
            "word": "Words",
            "line": "Lines",
            "code_block": "Code Blocks",
            "code_line": "Code Lines",
            "heading": "Headings",
            "list_item": "List Items",
            "pointer": "Pointers",
        },
    },
    "segmentation": {
        "include_empty_lines": False,
        "paragraph_split_regex": r"\n\s*\n+",
        "sentence_regex": r"[^.!?\n]+(?:[.!?]+|$)",
        "word_regex": r"[A-Za-z0-9_]+(?:['-][A-Za-z0-9_]+)?",
        "heading_regex": r"^\s{0,3}(#{1,6})\s+(.+?)\s*$",
        "list_item_regex": r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$",
        "fenced_code_start_regex": r"^\s*(```+|~~~+)\s*([A-Za-z0-9_+.-]*)\s*$",
        "detect_indented_code_blocks": False,
        "indent_code_regex": r"^(?:    |\t).+",
        "exclude_code_from_paragraphs": True,
        "exclude_code_from_sentences": True,
        "exclude_code_from_words": True,
    },
    "addressing": {
        "start": 1,
        "step": 1,
        "per_category": True,
    },
    "values": {
        "document_value": "full_text",
        "word_value": "token",
        "line_value": "text",
        "code_line_value": "text",
        "trim_paragraphs": True,
        "trim_sentences": True,
        "trim_lines": False,
    },
    "pointers": {
        "enabled": True,
        "separator": " ",
        "value_template": "relation={relation} source={source_ref} targets={target_refs}",
        "index_template": "relation={relation} target_category={target_category} targets={target_refs}",
        "rules": [
            {
                "name": "document_to_paragraphs",
                "mode": "children",
                "source_category": "document",
                "target_category": "paragraph",
                "relation": "contains",
            },
            {
                "name": "paragraph_to_sentences",
                "mode": "children",
                "source_category": "paragraph",
                "target_category": "sentence",
                "relation": "contains",
            },
            {
                "name": "sentence_to_words",
                "mode": "children",
                "source_category": "sentence",
                "target_category": "word",
                "relation": "contains",
            },
            {
                "name": "code_block_to_lines",
                "mode": "children",
                "source_category": "code_block",
                "target_category": "code_line",
                "relation": "contains",
            },
            {
                "name": "next_paragraph",
                "mode": "sequence",
                "target_category": "paragraph",
                "relation": "next",
            },
            {
                "name": "all_words",
                "mode": "category_index",
                "target_category": "word",
                "relation": "index",
            },
        ],
    },
    "custom_extractors": [],
    "dedupe": {
        "enabled": True,
        "scope": "category_parent_span_value",
        "value_normalization": "exact",
        "preserve_repeated_occurrences": True,
        "track_skipped": True,
    },
}


@dataclass
class Entry:
    bank: str
    register: str
    address: str
    value: str
    raw_bank: Optional[str] = None
    raw_register: Optional[str] = None
    raw_address: Optional[str] = None
    title: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def ref(self) -> str:
        return f"{self.bank}.{self.register}.{self.address}"


@dataclass
class Bank:
    id: str
    title: str = ""
    raw_id: Optional[str] = None
    registers: Dict[str, Dict[str, Entry]] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def set_entry(self, entry: Entry) -> None:
        self.registers.setdefault(entry.register, {})
        self.registers[entry.register][entry.address] = entry

    def entries(self, sort: bool = True) -> Iterable[Entry]:
        register_ids = list(self.registers.keys())
        if sort:
            register_ids = sorted(register_ids, key=natural_id_key)
        for register_id in register_ids:
            address_ids = list(self.registers[register_id].keys())
            if sort:
                address_ids = sorted(address_ids, key=natural_id_key)
            for address_id in address_ids:
                yield self.registers[register_id][address_id]


@dataclass
class Workspace:
    banks: Dict[str, Bank] = field(default_factory=dict)
    current_bank_id: Optional[str] = None
    dirty: bool = False

    def get_or_create_bank(self, bank_id: str, title: str = "", raw_id: Optional[str] = None) -> Bank:
        if bank_id not in self.banks:
            self.banks[bank_id] = Bank(id=bank_id, title=title, raw_id=raw_id)
            if self.current_bank_id is None:
                self.current_bank_id = bank_id
        elif title and not self.banks[bank_id].title:
            self.banks[bank_id].title = title
        return self.banks[bank_id]

    def entries(self, sort: bool = True) -> Iterable[Entry]:
        bank_ids = list(self.banks.keys())
        if sort:
            bank_ids = sorted(bank_ids, key=natural_id_key)
        for bank_id in bank_ids:
            yield from self.banks[bank_id].entries(sort=sort)

    def stats(self) -> Dict[str, Any]:
        registers = sum(len(bank.registers) for bank in self.banks.values())
        addresses = sum(len(register) for bank in self.banks.values() for register in bank.registers.values())
        categories: Dict[str, int] = {}
        pointer_entries = 0
        for entry in self.entries(sort=False):
            category = str(entry.meta.get("category", "unknown"))
            categories[category] = categories.get(category, 0) + 1
            if category == "pointer":
                pointer_entries += 1
        return {
            "banks": len(self.banks),
            "registers": registers,
            "addresses": addresses,
            "pointer_entries": pointer_entries,
            "categories": categories,
            "current_bank_id": self.current_bank_id,
        }

    def to_dict(self, include_meta: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "type": "tensor-workspace-v1",
            "current_bank_id": self.current_bank_id,
            "banks": {},
        }
        for bank_id, bank in self.banks.items():
            bank_data: Dict[str, Any] = {
                "id": bank.id,
                "title": bank.title,
                "raw_id": bank.raw_id,
                "registers": {},
            }
            if include_meta:
                bank_data["meta"] = bank.meta
            for register_id, address_map in bank.registers.items():
                bank_data["registers"][register_id] = {}
                for address_id, entry in address_map.items():
                    if include_meta:
                        bank_data["registers"][register_id][address_id] = {
                            "value": entry.value,
                            "raw_bank": entry.raw_bank,
                            "raw_register": entry.raw_register,
                            "raw_address": entry.raw_address,
                            "meta": entry.meta,
                        }
                    else:
                        bank_data["registers"][register_id][address_id] = entry.value
            data["banks"][bank_id] = bank_data
        return data


@dataclass
class Segment:
    category: str
    value: str
    key: str
    parent_key: Optional[str] = None
    ordinal: int = 0
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    entry: Optional[Entry] = None


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def set_path(obj: Dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur: Dict[str, Any] = obj
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def parse_json_value(text: str) -> Any:
    text = text.strip()
    if text == "":
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_tensor_config(path: Optional[Path]) -> Dict[str, Any]:
    config = copy.deepcopy(DEFAULT_TENSOR_CONFIG)
    config_path = path or DEFAULT_TENSOR_CONFIG_PATH
    if config_path.exists():
        config = deep_merge(config, load_json(config_path))
    return config


def load_format_profile(path: Optional[Path]) -> Dict[str, Any]:
    profile = copy.deepcopy(DEFAULT_FORMAT_PROFILE)
    if path:
        profile = deep_merge(profile, load_json(path))
    return profile


def natural_id_key(value: str) -> Tuple[int, Any]:
    try:
        return (0, int(str(value), 10))
    except Exception:
        return (1, str(value))


def normalize_dedupe_value(value: str, mode: str = "exact") -> str:
    text = str(value)
    if mode == "whitespace":
        return " ".join(text.split())
    if mode == "casefold":
        return text.casefold()
    if mode == "whitespace_casefold":
        return " ".join(text.split()).casefold()
    return text


def segment_dedupe_key(segment: Segment, dedupe_cfg: Dict[str, Any]) -> Tuple[Any, ...]:
    scope = str(dedupe_cfg.get("scope", "category_parent_span_value"))
    value = normalize_dedupe_value(segment.value, str(dedupe_cfg.get("value_normalization", "exact")))
    category = segment.category
    parent = segment.parent_key or ""
    span = (segment.start_char, segment.end_char, segment.start_line, segment.end_line)
    if scope == "category_value":
        return (category, value)
    if scope == "category_parent_value":
        return (category, parent, value)
    if scope == "category_span_value":
        return (category, span, value)
    return (category, parent, span, value)


def dedupe_segments(segments: List[Segment], profile: Dict[str, Any]) -> Tuple[List[Segment], List[Segment]]:
    dedupe_cfg = profile.get("dedupe", {}) or {}
    if not dedupe_cfg.get("enabled", True):
        return segments, []
    categories = {str(item) for item in dedupe_cfg.get("categories", []) or []}
    seen: Dict[Tuple[Any, ...], Segment] = {}
    kept: List[Segment] = []
    skipped: List[Segment] = []
    for segment in segments:
        if categories and segment.category not in categories:
            kept.append(segment)
            continue
        key = segment_dedupe_key(segment, dedupe_cfg)
        if key in seen:
            segment.meta.setdefault("duplicate_of", seen[key].key)
            skipped.append(segment)
            continue
        seen[key] = segment
        segment.meta.setdefault("dedupe_key", "|".join(str(part) for part in key))
        kept.append(segment)
    return kept, skipped


def entry_fingerprint(entry: Entry) -> Tuple[Any, ...]:
    category = str(entry.meta.get("category", ""))
    parent = str(entry.meta.get("parent_key", ""))
    key = str(entry.meta.get("key", ""))
    span = (
        entry.meta.get("start_char"),
        entry.meta.get("end_char"),
        entry.meta.get("start_line"),
        entry.meta.get("end_line"),
    )
    value = normalize_dedupe_value(entry.value, "exact")
    if category == "pointer":
        return (
            "pointer",
            entry.meta.get("pointer_rule", ""),
            entry.meta.get("mode", ""),
            entry.meta.get("source_key", ""),
            entry.meta.get("target_category", ""),
            value,
        )
    return (category, parent, key, span, value)


def next_address_text(address_number: int, tensor_config: Dict[str, Any]) -> str:
    return canonical_id(address_number, tensor_config)


def reserve_nonduplicate_entry(bank: Bank, entry: Entry, tensor_config: Dict[str, Any]) -> bool:
    """Insert an entry without creating exact duplicates or overwriting conflicts.

    Returns True when the entry was inserted. If the same ref already contains the
    same fingerprint, the new entry is skipped. If the ref is occupied by a
    different entry, the new entry is moved to the next free numeric address in
    the same register.
    """
    register = entry.register
    address = entry.address
    register_map = bank.registers.setdefault(register, {})
    existing = register_map.get(address)
    fingerprint = entry_fingerprint(entry)
    if existing is not None:
        if entry_fingerprint(existing) == fingerprint:
            return False
        original_ref = entry.ref()
        try:
            probe_number = int(str(address), 10)
        except ValueError:
            probe_number = max([int(a) for a in register_map if str(a).isdigit()] or [0])
        while True:
            probe_number += 1
            candidate = next_address_text(probe_number, tensor_config)
            if candidate not in register_map:
                entry.address = candidate
                entry.raw_address = str(probe_number)
                entry.meta.setdefault("dedupe_conflict_original_ref", original_ref)
                break
    register_map[entry.address] = entry
    return True


def strip_config_prefix(raw: str, config: Dict[str, Any]) -> str:
    text = str(raw).strip()
    prefix = str(config.get("id", {}).get("prefix", ""))
    if prefix and config.get("id", {}).get("strip_prefix_on_parse", True):
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix):]
    return text


def canonical_id(raw: str | int, config: Dict[str, Any]) -> str:
    text = strip_config_prefix(str(raw).strip(), config)
    if text == "":
        return text
    if not config.get("id", {}).get("canonicalize_numeric_ids", True):
        return text
    base = int(config.get("id", {}).get("base", 10))
    try:
        return str(int(text, base))
    except Exception:
        return text


def format_id(canonical: str, kind: str, config: Dict[str, Any], raw: Optional[str] = None) -> str:
    output_cfg = config.get("output", {})
    if raw and output_cfg.get("use_original_ids_when_available", True):
        return raw
    widths = {
        "bank": "width_bank",
        "register": "width_register",
        "address": "width_address",
    }
    width = int(config.get("id", {}).get(widths.get(kind, "width_address"), 0))
    base = int(config.get("id", {}).get("base", 10))
    try:
        number = int(str(canonical), 10)
        if base == 10:
            text = str(number)
        else:
            digits = "0123456789abcdefghijklmnopqrstuvwxyz"
            if number == 0:
                text = "0"
            else:
                parts: List[str] = []
                q = number
                while q:
                    q, r = divmod(q, base)
                    parts.append(digits[r])
                text = "".join(reversed(parts))
        return text.zfill(width) if width else text
    except Exception:
        return str(canonical)


def line_number_for_offset(line_starts: List[int], offset: int) -> int:
    # Avoid importing bisect for one tiny lookup loop; text inputs are local-tool sized.
    current = 1
    for index, start in enumerate(line_starts, start=1):
        if start > offset:
            break
        current = index
    return current


def build_line_starts(text: str) -> List[int]:
    starts = [0]
    for match in re.finditer(r"\n", text):
        starts.append(match.end())
    return starts


def detect_code_blocks(text: str, profile: Dict[str, Any]) -> Tuple[List[Segment], List[Tuple[int, int]], Dict[int, Segment]]:
    seg_cfg = profile.get("segmentation", {})
    start_re = re.compile(seg_cfg.get("fenced_code_start_regex", DEFAULT_FORMAT_PROFILE["segmentation"]["fenced_code_start_regex"]))
    indent_re = re.compile(seg_cfg.get("indent_code_regex", DEFAULT_FORMAT_PROFILE["segmentation"]["indent_code_regex"]))
    detect_indented = bool(seg_cfg.get("detect_indented_code_blocks", False))
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    offset = 0
    blocks: List[Segment] = []
    ranges: List[Tuple[int, int]] = []
    line_to_block: Dict[int, Segment] = {}
    active: Optional[Dict[str, Any]] = None
    indented_active: Optional[Dict[str, Any]] = None

    def close_fenced(end_line: int, end_offset: int) -> None:
        nonlocal active
        if active is None:
            return
        content = "\n".join(active["content"])
        ordinal = len(blocks) + 1
        segment = Segment(
            category="code_block",
            value=content,
            key=f"code_block:{ordinal}",
            parent_key="document:1",
            ordinal=ordinal,
            start_line=active["start_line"],
            end_line=end_line,
            start_char=active["start_offset"],
            end_char=end_offset,
            meta={"fence": active["fence"], "language": active.get("language", "")},
        )
        blocks.append(segment)
        ranges.append((active["start_offset"], end_offset))
        for line_number in range(active["start_line"], end_line + 1):
            line_to_block[line_number] = segment
        active = None

    def close_indented(end_line: int, end_offset: int) -> None:
        nonlocal indented_active
        if indented_active is None:
            return
        content = "\n".join(indented_active["content"])
        ordinal = len(blocks) + 1
        segment = Segment(
            category="code_block",
            value=content,
            key=f"code_block:{ordinal}",
            parent_key="document:1",
            ordinal=ordinal,
            start_line=indented_active["start_line"],
            end_line=end_line,
            start_char=indented_active["start_offset"],
            end_char=end_offset,
            meta={"fence": "indent", "language": ""},
        )
        blocks.append(segment)
        ranges.append((indented_active["start_offset"], end_offset))
        for line_number in range(indented_active["start_line"], end_line + 1):
            line_to_block[line_number] = segment
        indented_active = None

    for index, line in enumerate(lines, start=1):
        line_start = offset
        line_end = offset + len(line)
        next_offset = line_end + 1

        if active is not None:
            match = start_re.match(line)
            if match and match.group(1).startswith(active["fence"][0]):
                close_fenced(index, line_end)
            else:
                active["content"].append(line)
            offset = next_offset
            continue

        match = start_re.match(line)
        if match:
            close_indented(index - 1, line_start)
            active = {
                "start_line": index,
                "start_offset": line_start,
                "fence": match.group(1),
                "language": match.group(2) if match.lastindex and match.lastindex >= 2 else "",
                "content": [],
            }
            offset = next_offset
            continue

        if detect_indented and indent_re.match(line):
            if indented_active is None:
                indented_active = {
                    "start_line": index,
                    "start_offset": line_start,
                    "content": [line],
                }
            else:
                indented_active["content"].append(line)
        else:
            close_indented(index - 1, line_start)

        offset = next_offset

    if active is not None:
        close_fenced(len(lines), len(text))
    if indented_active is not None:
        close_indented(len(lines), len(text))
    return blocks, ranges, line_to_block


def in_ranges(start: int, end: int, ranges: List[Tuple[int, int]]) -> bool:
    for range_start, range_end in ranges:
        if start < range_end and end > range_start:
            return True
    return False


def text_outside_ranges(text: str, ranges: List[Tuple[int, int]]) -> str:
    if not ranges:
        return text
    parts: List[str] = []
    cursor = 0
    for start, end in sorted(ranges):
        parts.append(text[cursor:start])
        parts.append("\n\n")
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def make_segmenter(text: str, profile: Dict[str, Any]) -> List[Segment]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    line_starts = build_line_starts(normalized)
    enabled = set(profile.get("categories", {}).get("enabled", []))
    seg_cfg = profile.get("segmentation", {})
    value_cfg = profile.get("values", {})
    code_blocks, code_ranges, line_to_block = detect_code_blocks(normalized, profile)
    segments: List[Segment] = []

    if "document" in enabled:
        segments.append(
            Segment(
                category="document",
                value=normalized if value_cfg.get("document_value", "full_text") == "full_text" else "document",
                key="document:1",
                ordinal=1,
                start_line=1,
                end_line=normalized.count("\n") + 1,
                start_char=0,
                end_char=len(normalized),
            )
        )

    lines = normalized.split("\n")
    running_offset = 0
    line_segments: List[Segment] = []
    for index, line in enumerate(lines, start=1):
        line_start = running_offset
        line_end = running_offset + len(line)
        running_offset = line_end + 1
        if not line and not seg_cfg.get("include_empty_lines", False):
            continue
        if "line" in enabled:
            value = line.strip() if value_cfg.get("trim_lines", False) else line
            line_segment = Segment(
                category="line",
                value=value,
                key=f"line:{len(line_segments) + 1}",
                parent_key="document:1",
                ordinal=len(line_segments) + 1,
                start_line=index,
                end_line=index,
                start_char=line_start,
                end_char=line_end,
                meta={"is_code": index in line_to_block},
            )
            line_segments.append(line_segment)
            segments.append(line_segment)

    if "code_block" in enabled:
        segments.extend(code_blocks)

    if "code_line" in enabled:
        code_line_ordinal = 0
        for block in code_blocks:
            block_lines = block.value.split("\n") if block.value else []
            start_line = (block.start_line or 1) + 1
            for local_index, code_line in enumerate(block_lines, start=1):
                if not code_line and not seg_cfg.get("include_empty_lines", False):
                    continue
                code_line_ordinal += 1
                segments.append(
                    Segment(
                        category="code_line",
                        value=code_line,
                        key=f"code_line:{code_line_ordinal}",
                        parent_key=block.key,
                        ordinal=code_line_ordinal,
                        start_line=start_line + local_index - 1,
                        end_line=start_line + local_index - 1,
                        meta={"code_block_key": block.key, "local_index": local_index, "language": block.meta.get("language", "")},
                    )
                )

    paragraph_source = normalized
    if seg_cfg.get("exclude_code_from_paragraphs", True):
        paragraph_source = text_outside_ranges(normalized, code_ranges)

    paragraph_re = re.compile(seg_cfg.get("paragraph_split_regex", DEFAULT_FORMAT_PROFILE["segmentation"]["paragraph_split_regex"]))
    paragraph_segments: List[Segment] = []
    cursor = 0
    paragraph_ordinal = 0
    for part in paragraph_re.split(paragraph_source):
        if part == "":
            cursor += 1
            continue
        start = paragraph_source.find(part, cursor)
        if start < 0:
            start = cursor
        end = start + len(part)
        cursor = end
        value = part.strip() if value_cfg.get("trim_paragraphs", True) else part
        if not value:
            continue
        paragraph_ordinal += 1
        paragraph = Segment(
            category="paragraph",
            value=value,
            key=f"paragraph:{paragraph_ordinal}",
            parent_key="document:1",
            ordinal=paragraph_ordinal,
            start_line=line_number_for_offset(line_starts, start),
            end_line=line_number_for_offset(line_starts, end),
            start_char=start,
            end_char=end,
        )
        paragraph_segments.append(paragraph)
        if "paragraph" in enabled:
            segments.append(paragraph)

    sentence_re = re.compile(seg_cfg.get("sentence_regex", DEFAULT_FORMAT_PROFILE["segmentation"]["sentence_regex"]), re.MULTILINE)
    sentence_segments: List[Segment] = []
    sentence_ordinal = 0
    if "sentence" in enabled or "word" in enabled:
        sentence_source_segments = paragraph_segments if seg_cfg.get("exclude_code_from_sentences", True) else [
            Segment(category="document", value=normalized, key="document:1", parent_key=None, ordinal=1, start_char=0, end_char=len(normalized))
        ]
        for paragraph in sentence_source_segments:
            base_start = paragraph.start_char or 0
            for match in sentence_re.finditer(paragraph.value):
                raw_value = match.group(0)
                value = raw_value.strip() if value_cfg.get("trim_sentences", True) else raw_value
                if not value:
                    continue
                start = base_start + match.start()
                end = base_start + match.end()
                sentence_ordinal += 1
                sentence = Segment(
                    category="sentence",
                    value=value,
                    key=f"sentence:{sentence_ordinal}",
                    parent_key=paragraph.key,
                    ordinal=sentence_ordinal,
                    start_line=line_number_for_offset(line_starts, start),
                    end_line=line_number_for_offset(line_starts, end),
                    start_char=start,
                    end_char=end,
                )
                sentence_segments.append(sentence)
                if "sentence" in enabled:
                    segments.append(sentence)

    word_re = re.compile(seg_cfg.get("word_regex", DEFAULT_FORMAT_PROFILE["segmentation"]["word_regex"]))
    if "word" in enabled:
        word_ordinal = 0
        word_source_segments = sentence_segments
        if not word_source_segments and not seg_cfg.get("exclude_code_from_words", True):
            word_source_segments = [Segment(category="document", value=normalized, key="document:1", ordinal=1, start_char=0)]
        for sentence in word_source_segments:
            base_start = sentence.start_char or 0
            for match in word_re.finditer(sentence.value):
                word_ordinal += 1
                start = base_start + match.start()
                end = base_start + match.end()
                segments.append(
                    Segment(
                        category="word",
                        value=match.group(0),
                        key=f"word:{word_ordinal}",
                        parent_key=sentence.key,
                        ordinal=word_ordinal,
                        start_line=line_number_for_offset(line_starts, start),
                        end_line=line_number_for_offset(line_starts, end),
                        start_char=start,
                        end_char=end,
                        meta={"lower": match.group(0).lower()},
                    )
                )

    heading_re = re.compile(seg_cfg.get("heading_regex", DEFAULT_FORMAT_PROFILE["segmentation"]["heading_regex"]))
    list_item_re = re.compile(seg_cfg.get("list_item_regex", DEFAULT_FORMAT_PROFILE["segmentation"]["list_item_regex"]))
    heading_ordinal = 0
    list_ordinal = 0
    running_offset = 0
    for line_number, line in enumerate(lines, start=1):
        line_start = running_offset
        line_end = running_offset + len(line)
        running_offset = line_end + 1
        if in_ranges(line_start, line_end, code_ranges):
            continue
        heading_match = heading_re.match(line)
        if heading_match and "heading" in enabled:
            heading_ordinal += 1
            segments.append(
                Segment(
                    category="heading",
                    value=heading_match.group(2).strip() if heading_match.lastindex and heading_match.lastindex >= 2 else line.strip(),
                    key=f"heading:{heading_ordinal}",
                    parent_key="document:1",
                    ordinal=heading_ordinal,
                    start_line=line_number,
                    end_line=line_number,
                    start_char=line_start,
                    end_char=line_end,
                    meta={"level": len(heading_match.group(1)) if heading_match.lastindex else None},
                )
            )
        list_match = list_item_re.match(line)
        if list_match and "list_item" in enabled:
            list_ordinal += 1
            segments.append(
                Segment(
                    category="list_item",
                    value=list_match.group(1).strip() if list_match.lastindex else line.strip(),
                    key=f"list_item:{list_ordinal}",
                    parent_key="document:1",
                    ordinal=list_ordinal,
                    start_line=line_number,
                    end_line=line_number,
                    start_char=line_start,
                    end_char=line_end,
                )
            )

    segments.extend(run_custom_extractors(normalized, profile, line_starts))
    return segments


def run_custom_extractors(text: str, profile: Dict[str, Any], line_starts: List[int]) -> List[Segment]:
    segments: List[Segment] = []
    for extractor in profile.get("custom_extractors", []) or []:
        category = str(extractor.get("category", "")).strip()
        pattern = extractor.get("regex")
        if not category or not pattern:
            continue
        flags = re.MULTILINE
        if extractor.get("ignore_case", False):
            flags |= re.IGNORECASE
        group = extractor.get("value_group", 0)
        parent_key = extractor.get("parent_key", "document:1")
        for match in re.finditer(pattern, text, flags):
            try:
                value = match.group(group)
            except Exception:
                value = match.group(0)
            ordinal = len([seg for seg in segments if seg.category == category]) + 1
            start, end = match.span(group if isinstance(group, int) else 0)
            segments.append(
                Segment(
                    category=category,
                    value=value,
                    key=f"{category}:{ordinal}",
                    parent_key=parent_key,
                    ordinal=ordinal,
                    start_line=line_number_for_offset(line_starts, start),
                    end_line=line_number_for_offset(line_starts, end),
                    start_char=start,
                    end_char=end,
                    meta={"custom_extractor": extractor.get("name", category)},
                )
            )
    return segments


def category_register(category: str, profile: Dict[str, Any], tensor_config: Dict[str, Any]) -> str:
    registers = profile.get("categories", {}).get("registers", {})
    raw_register = registers.get(category)
    if raw_register is None:
        raw_register = str(max([int(v) for v in registers.values() if str(v).isdigit()] or [999]) + 1)
        registers[category] = raw_register
    return canonical_id(raw_register, tensor_config)


def create_workspace(text: str, profile: Dict[str, Any], tensor_config: Dict[str, Any]) -> Tuple[Workspace, List[Segment]]:
    workspace = Workspace()
    raw_bank = str(profile.get("bank", {}).get("raw_id") or profile.get("bank", {}).get("id", "1"))
    bank_id = canonical_id(profile.get("bank", {}).get("id", raw_bank), tensor_config)
    bank = workspace.get_or_create_bank(bank_id, title=str(profile.get("bank", {}).get("title", "format_paste")), raw_id=raw_bank)
    bank.meta = {
        "source": "format_paste.py",
        "profile_id": profile.get("profile_id"),
    }
    raw_segments = make_segmenter(text, profile)
    segments, skipped_segments = dedupe_segments(raw_segments, profile)
    if profile.get("dedupe", {}).get("track_skipped", True):
        bank.meta["dedupe"] = {
            "enabled": bool(profile.get("dedupe", {}).get("enabled", True)),
            "input_segments": len(raw_segments),
            "kept_segments": len(segments),
            "skipped_segments": len(skipped_segments),
            "skipped_keys": [segment.key for segment in skipped_segments[:100]],
        }
    counters: Dict[str, int] = {}
    start = int(profile.get("addressing", {}).get("start", 1))
    step = int(profile.get("addressing", {}).get("step", 1))
    category_titles = profile.get("categories", {}).get("titles", {})

    for segment in segments:
        register = category_register(segment.category, profile, tensor_config)
        counters[segment.category] = counters.get(segment.category, 0) + 1
        address_number = start + ((counters[segment.category] - 1) * step)
        address = canonical_id(address_number, tensor_config)
        entry = Entry(
            bank=bank.id,
            register=register,
            address=address,
            value=segment.value,
            raw_bank=bank.raw_id,
            raw_register=profile.get("categories", {}).get("registers", {}).get(segment.category),
            raw_address=str(address_number),
            title=category_titles.get(segment.category, segment.category),
            meta={
                "category": segment.category,
                "key": segment.key,
                "parent_key": segment.parent_key,
                "ordinal": segment.ordinal,
                "start_line": segment.start_line,
                "end_line": segment.end_line,
                "start_char": segment.start_char,
                "end_char": segment.end_char,
                **segment.meta,
            },
        )
        entry.meta.setdefault("entry_fingerprint", "|".join(str(part) for part in entry_fingerprint(entry)))
        if reserve_nonduplicate_entry(bank, entry, tensor_config):
            segment.entry = entry
        else:
            segment.meta.setdefault("duplicate_entry_skipped", True)

    if profile.get("pointers", {}).get("enabled", True):
        add_pointer_entries(bank, segments, profile, tensor_config, counters)

    workspace.dirty = True
    return workspace, segments


def add_pointer_entries(bank: Bank, segments: List[Segment], profile: Dict[str, Any],
                        tensor_config: Dict[str, Any], counters: Dict[str, int]) -> None:
    pointer_cfg = profile.get("pointers", {})
    pointer_register = category_register("pointer", profile, tensor_config)
    separator = str(pointer_cfg.get("separator", " "))
    value_template = str(pointer_cfg.get("value_template", DEFAULT_FORMAT_PROFILE["pointers"]["value_template"]))
    index_template = str(pointer_cfg.get("index_template", DEFAULT_FORMAT_PROFILE["pointers"]["index_template"]))
    pointer_count = counters.get("pointer", 0)
    pointer_seen: set[Tuple[Any, ...]] = set()
    by_category: Dict[str, List[Segment]] = {}
    by_key: Dict[str, Segment] = {}
    for segment in segments:
        if segment.entry is None:
            continue
        by_category.setdefault(segment.category, []).append(segment)
        by_key[segment.key] = segment

    def next_pointer(value: str, meta: Dict[str, Any]) -> None:
        nonlocal pointer_count
        probe = Entry(
            bank=bank.id,
            register=pointer_register,
            address="0",
            value=value,
            raw_bank=bank.raw_id,
            raw_register=profile.get("categories", {}).get("registers", {}).get("pointer"),
            raw_address="0",
            title=profile.get("categories", {}).get("titles", {}).get("pointer", "Pointers"),
            meta={"category": "pointer", **meta},
        )
        fingerprint = entry_fingerprint(probe)
        if fingerprint in pointer_seen:
            return
        pointer_seen.add(fingerprint)
        pointer_count += 1
        address = canonical_id(pointer_count, tensor_config)
        entry = Entry(
            bank=bank.id,
            register=pointer_register,
            address=address,
            value=value,
            raw_bank=bank.raw_id,
            raw_register=profile.get("categories", {}).get("registers", {}).get("pointer"),
            raw_address=str(pointer_count),
            title=profile.get("categories", {}).get("titles", {}).get("pointer", "Pointers"),
            meta={"category": "pointer", "ordinal": pointer_count, **meta},
        )
        entry.meta.setdefault("entry_fingerprint", "|".join(str(part) for part in entry_fingerprint(entry)))
        reserve_nonduplicate_entry(bank, entry, tensor_config)

    for rule in pointer_cfg.get("rules", []) or []:
        mode = rule.get("mode")
        relation = str(rule.get("relation", rule.get("name", "pointer")))
        if mode == "category_index":
            target_category = str(rule.get("target_category", ""))
            targets = [seg.entry.ref() for seg in by_category.get(target_category, []) if seg.entry]
            if not targets and not rule.get("emit_empty", False):
                continue
            value = index_template.format(
                relation=relation,
                target_category=target_category,
                target_refs=separator.join(targets),
                count=len(targets),
                name=rule.get("name", ""),
            )
            next_pointer(value, {"pointer_rule": rule.get("name"), "mode": mode, "target_category": target_category, "target_count": len(targets)})
        elif mode == "children":
            source_category = str(rule.get("source_category", ""))
            target_category = str(rule.get("target_category", ""))
            for source in by_category.get(source_category, []):
                targets = [
                    seg.entry.ref()
                    for seg in by_category.get(target_category, [])
                    if seg.entry and seg.parent_key == source.key
                ]
                if not targets and not rule.get("emit_empty", False):
                    continue
                source_ref = source.entry.ref() if source.entry else ""
                value = value_template.format(
                    relation=relation,
                    source_ref=source_ref,
                    source_key=source.key,
                    target_category=target_category,
                    target_refs=separator.join(targets),
                    count=len(targets),
                    name=rule.get("name", ""),
                )
                next_pointer(value, {"pointer_rule": rule.get("name"), "mode": mode, "source_key": source.key, "target_count": len(targets)})
        elif mode == "sequence":
            target_category = str(rule.get("target_category", ""))
            seq = by_category.get(target_category, [])
            for current, next_segment in zip(seq, seq[1:]):
                if current.entry is None or next_segment.entry is None:
                    continue
                value = value_template.format(
                    relation=relation,
                    source_ref=current.entry.ref(),
                    source_key=current.key,
                    target_category=target_category,
                    target_refs=next_segment.entry.ref(),
                    count=1,
                    name=rule.get("name", ""),
                )
                next_pointer(value, {"pointer_rule": rule.get("name"), "mode": mode, "source_key": current.key, "target_count": 1})
        elif mode == "source_to_all_targets":
            source_category = str(rule.get("source_category", ""))
            target_category = str(rule.get("target_category", ""))
            targets = [seg.entry.ref() for seg in by_category.get(target_category, []) if seg.entry]
            for source in by_category.get(source_category, []):
                if source.entry is None or (not targets and not rule.get("emit_empty", False)):
                    continue
                value = value_template.format(
                    relation=relation,
                    source_ref=source.entry.ref(),
                    source_key=source.key,
                    target_category=target_category,
                    target_refs=separator.join(targets),
                    count=len(targets),
                    name=rule.get("name", ""),
                )
                next_pointer(value, {"pointer_rule": rule.get("name"), "mode": mode, "source_key": source.key, "target_count": len(targets)})


def entry_record(entry: Entry, workspace: Workspace, include_meta: bool = True) -> Dict[str, Any]:
    bank = workspace.banks[entry.bank]
    record: Dict[str, Any] = {
        "bank": entry.bank,
        "bank_title": bank.title,
        "register": entry.register,
        "address": entry.address,
        "ref": entry.ref(),
        "value": entry.value,
        "title": entry.title or bank.title,
    }
    if include_meta:
        record["meta"] = entry.meta
    return record


def render_workspace(workspace: Workspace, output_format: str, tensor_config: Dict[str, Any]) -> str:
    include_meta = bool(tensor_config.get("output", {}).get("include_meta", True))
    sort = bool(tensor_config.get("output", {}).get("sort", True))
    indent = int(tensor_config.get("output", {}).get("indent", 2))
    if output_format == "json_workspace":
        return json.dumps(workspace.to_dict(include_meta=include_meta), indent=indent, ensure_ascii=False) + "\n"
    if output_format == "json_records":
        return json.dumps([entry_record(entry, workspace, include_meta=include_meta) for entry in workspace.entries(sort=sort)], indent=indent, ensure_ascii=False) + "\n"
    if output_format == "jsonl":
        return "".join(json.dumps(entry_record(entry, workspace, include_meta=include_meta), ensure_ascii=False) + "\n" for entry in workspace.entries(sort=sort))
    if output_format == "csv_records":
        return render_csv_records(workspace, include_meta=include_meta, sort=sort)
    if output_format == "tensor_text":
        return render_tensor_text(workspace, tensor_config, sort=sort)
    if output_format == "databank_text":
        return render_databank_text(workspace, tensor_config, sort=sort)
    if output_format == "markdown":
        return render_markdown(workspace, sort=sort)
    if output_format == "summary":
        return json.dumps(workspace.stats(), indent=indent, ensure_ascii=False) + "\n"
    if output_format == "dot":
        return render_dot(workspace, sort=sort)
    raise ValueError(f"Unsupported output format: {output_format}")


def render_csv_records(workspace: Workspace, include_meta: bool = True, sort: bool = True) -> str:
    output = io.StringIO()
    fieldnames = ["bank", "bank_title", "register", "address", "ref", "value", "title"]
    if include_meta:
        fieldnames.append("meta")
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for entry in workspace.entries(sort=sort):
        row = entry_record(entry, workspace, include_meta=False)
        if include_meta:
            row["meta"] = json.dumps(entry.meta, ensure_ascii=False, sort_keys=True)
        writer.writerow(row)
    return output.getvalue()


def render_tensor_text(workspace: Workspace, tensor_config: Dict[str, Any], sort: bool = True) -> str:
    quote_multiline = bool(tensor_config.get("output", {}).get("quote_multiline", True))
    lines: List[str] = []
    bank_ids = list(workspace.banks.keys())
    if sort:
        bank_ids = sorted(bank_ids, key=natural_id_key)
    for bank_id in bank_ids:
        bank = workspace.banks[bank_id]
        raw_bank = format_id(bank.id, "bank", tensor_config, bank.raw_id)
        title = bank.title or "bank"
        lines.append(f"{raw_bank} ( {title} ) {{")
        register_ids = list(bank.registers.keys())
        if sort:
            register_ids = sorted(register_ids, key=natural_id_key)
        for register_id in register_ids:
            lines.append(format_id(register_id, "register", tensor_config, None))
            address_ids = list(bank.registers[register_id].keys())
            if sort:
                address_ids = sorted(address_ids, key=natural_id_key)
            for address_id in address_ids:
                entry = bank.registers[register_id][address_id]
                address = format_id(entry.address, "address", tensor_config, entry.raw_address)
                if "\n" in entry.value and quote_multiline:
                    lines.append(f"\t{address}\t\"\"\"")
                    lines.extend(entry.value.split("\n"))
                    lines.append("\t\"\"\"")
                else:
                    lines.append(f"\t{address}\t{entry.value}")
            lines.append("")
        lines.append("")
        lines.append("}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_databank_text(workspace: Workspace, tensor_config: Dict[str, Any], sort: bool = True) -> str:
    quote_multiline = bool(tensor_config.get("output", {}).get("quote_multiline", True))
    bank_id = workspace.current_bank_id or (sorted(workspace.banks.keys(), key=natural_id_key)[0] if workspace.banks else None)
    if bank_id is None:
        return ""
    bank = workspace.banks[bank_id]
    register_ids = list(bank.registers.keys())
    if sort:
        register_ids = sorted(register_ids, key=natural_id_key)
    lines: List[str] = []
    for register_id in register_ids:
        lines.append(format_id(register_id, "register", tensor_config, None))
        address_ids = list(bank.registers[register_id].keys())
        if sort:
            address_ids = sorted(address_ids, key=natural_id_key)
        for address_id in address_ids:
            entry = bank.registers[register_id][address_id]
            address = format_id(address_id, "address", tensor_config, entry.raw_address)
            if "\n" in entry.value and quote_multiline:
                lines.append(f"\t{address}\t\"\"\"")
                lines.extend(entry.value.split("\n"))
                lines.append("\t\"\"\"")
            else:
                lines.append(f"\t{address}\t{entry.value}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(workspace: Workspace, sort: bool = True) -> str:
    lines = ["| bank | title | register | address | ref | category | value |", "|---:|---|---:|---:|---|---|---|"]
    for entry in workspace.entries(sort=sort):
        bank = workspace.banks[entry.bank]
        value = entry.value.replace("|", "\\|").replace("\n", "<br>")
        category = str(entry.meta.get("category", "")).replace("|", "\\|")
        lines.append(f"| {entry.bank} | {bank.title} | {entry.register} | {entry.address} | `{entry.ref()}` | {category} | {value} |")
    return "\n".join(lines) + "\n"


def render_dot(workspace: Workspace, sort: bool = True) -> str:
    ref_regex = re.compile(r"(?<![A-Za-z0-9_])(?P<bank>[0-9A-Za-z]+)\.(?P<register>[0-9A-Za-z]+)\.(?P<address>[0-9A-Za-z]+)(?![A-Za-z0-9_])")
    lines = ["digraph format_paste {", "  rankdir=LR;"]
    for entry in workspace.entries(sort=sort):
        label = entry.value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")[:80]
        category = entry.meta.get("category", "")
        lines.append(f'  "{entry.ref()}" [label="{entry.ref()}\\n{category}\\n{label}"];')
    for entry in workspace.entries(sort=sort):
        if entry.meta.get("category") != "pointer":
            continue
        for match in ref_regex.finditer(entry.value):
            target = match.group(0)
            lines.append(f'  "{entry.ref()}" -> "{target}";')
    lines.append("}")
    return "\n".join(lines) + "\n"


def read_input(args: argparse.Namespace, encoding: str) -> str:
    sources: List[str] = []
    if args.text is not None:
        sources.append(args.text)
    for path_text in args.input or []:
        path = Path(path_text)
        sources.append(path.read_text(encoding=encoding))
    if not sources and not sys.stdin.isatty():
        sources.append(sys.stdin.read())
    if not sources:
        raise ValueError("No input supplied. Use --input, --text, or pipe text on stdin.")
    return "\n\n".join(sources)


def write_output(text: str, path: Optional[str], encoding: str) -> None:
    if path:
        Path(path).write_text(text, encoding=encoding)
    else:
        sys.stdout.write(text)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create Tensor-compatible paste/import inputs from arbitrary text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python format_paste.py --input notes.md --format tensor_text --output Tensor.txt\n"
            "  python format_paste.py --input notes.md --format json_workspace --output tensor-workspace.json\n"
            "  python format_paste.py --text \"Hello world.\" --categories paragraph,sentence,word,pointer\n"
            "  python format_paste.py --write-default-profile format-paste-profile.json\n"
            "  python format_paste.py --profile my-profile.json --set-profile pointers.enabled false\n"
        ),
    )
    parser.add_argument("--input", "-i", action="append", help="Input text file. Can be repeated.")
    parser.add_argument("--text", help="Inline source text.")
    parser.add_argument("--output", "-o", help="Output file. Defaults to stdout.")
    parser.add_argument("--format", choices=sorted(COMPATIBLE_OUTPUT_FORMATS), default="tensor_text", help="Tensor-compatible output format.")
    parser.add_argument("--tensor-config", help="Tensor config-id.json path. Defaults to the local tensor/spec/config-id.json.")
    parser.add_argument("--profile", help="format_paste profile JSON path.")
    parser.add_argument("--write-default-profile", help="Write the default format_paste profile JSON and exit.")
    parser.add_argument("--write-effective-profile", help="Write the merged effective format_paste profile JSON and continue.")
    parser.add_argument("--write-effective-tensor-config", help="Write the merged effective Tensor config JSON and continue.")
    parser.add_argument("--categories", help="Comma-separated categories to generate. Include pointer to enable pointer entries.")
    parser.add_argument("--bank-id", help="Override output bank id.")
    parser.add_argument("--bank-title", help="Override output bank title.")
    parser.add_argument("--no-pointers", action="store_true", help="Disable pointer generation.")
    parser.add_argument("--pointer-rule", action="append", help="Append pointer rule JSON object.")
    parser.add_argument("--set-profile", nargs=2, action="append", metavar=("PATH", "JSON_VALUE"), help="Set a dotted path in the format profile.")
    parser.add_argument("--set-tensor-config", nargs=2, action="append", metavar=("PATH", "JSON_VALUE"), help="Set a dotted path in the Tensor config.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.write_default_profile:
        Path(args.write_default_profile).write_text(json.dumps(DEFAULT_FORMAT_PROFILE, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0

    tensor_path = Path(args.tensor_config) if args.tensor_config else None
    tensor_config = load_tensor_config(tensor_path)
    profile = load_format_profile(Path(args.profile) if args.profile else None)

    for dotted, value in args.set_tensor_config or []:
        set_path(tensor_config, dotted, parse_json_value(value))
    for dotted, value in args.set_profile or []:
        set_path(profile, dotted, parse_json_value(value))

    if args.categories:
        categories = [part.strip() for part in args.categories.split(",") if part.strip()]
        profile.setdefault("categories", {})["enabled"] = [cat for cat in categories if cat != "pointer"]
        profile.setdefault("pointers", {})["enabled"] = "pointer" in categories and not args.no_pointers
    if args.bank_id:
        profile.setdefault("bank", {})["id"] = args.bank_id
        profile.setdefault("bank", {})["raw_id"] = args.bank_id
    if args.bank_title:
        profile.setdefault("bank", {})["title"] = args.bank_title
    if args.no_pointers:
        profile.setdefault("pointers", {})["enabled"] = False
    for rule_text in args.pointer_rule or []:
        profile.setdefault("pointers", {}).setdefault("rules", []).append(json.loads(rule_text))

    if args.write_effective_profile:
        Path(args.write_effective_profile).write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.write_effective_tensor_config:
        Path(args.write_effective_tensor_config).write_text(json.dumps(tensor_config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    encoding = tensor_config.get("input", {}).get("encoding", "utf-8")
    text = read_input(args, encoding=encoding)
    workspace, _segments = create_workspace(text, profile, tensor_config)
    rendered = render_workspace(workspace, args.format, tensor_config)
    write_output(rendered, args.output, encoding=tensor_config.get("output", {}).get("encoding", "utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
