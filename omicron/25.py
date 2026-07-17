#!/usr/bin/env python3
"""
tensor.py

A fully configurable bank/register/address tensor parser, resolver, transformer, and exporter.
It merges the strongest features of CLIx and Data Bank Manager into a local Python CLI/UI:

- CLIX-style REPL commands, configurable ID prefix/base/widths, bank/register/address model,
  duplicate-value policy, import/export, and recursive reference resolver.
- Data Bank Manager-style multi-bank parsing, raw/resolve reading modes, multiline values,
  search, undo snapshots, tabular export, and bulk output formats.
- Format-spec driven input and output so Tensor.txt is only one possible input structure.

No third-party packages are required.
"""

from __future__ import annotations

import argparse
import copy
import csv
import importlib.util
import io
import json
import os
import re
import shlex
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_CONFIG: Dict[str, Any] = {
    "config_id": "tensor-default-v1",
    "description": "Default Tensor parser: block files such as Tensor.txt plus CLIX/DataBank-compatible flows.",
    "input": {
        "format_id": "tensor-block-v1",
        "encoding": "utf-8",
        "merge_mode": "replace",  # replace | merge
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
        "reading_mode": "raw",  # raw | resolve
        "two_part_mode": "bank_address",  # bank_address | local_register_address
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
            "trim", "lower", "upper", "resolve", "replace_regex", "prefix", "suffix",
            "token_count", "char_count", "drop_empty"
        ],
    },
    "output": {
        "format": "json",  # json | jsonl | csv | markdown | tensor_text | databank_text | summary | dot
        "encoding": "utf-8",
        "include_meta": True,
        "sort": True,
        "indent": 2,
        "use_original_ids_when_available": True,
        "quote_multiline": True,
    },
    "formats": {
        "tensor-block-v1": {
            "description": "Header block format: <bank> ( <title> ) { followed by tab-indented <address><tab><value> lines.",
            "type": "block",
            "header_regex": r"^\s*(?P<bank>[xX]?[0-9A-Za-z]+)\s*\(\s*(?P<title>[^)]*)\s*\)\s*\{\s*$",
            "end_regex": r"^\s*}\s*$",
            "register_regex": r"^\s*(?P<register>[0-9A-Za-z]+)\s*$",
            "item_regex": r"^\s*(?P<address>[0-9A-Za-z]+)\s+(?P<value>.*)$",
            "multiline_start": "\"\"\"",
            "multiline_end": "\"\"\"",
            "default_register_id": "1",
        },
        "databank-register-v1": {
            "description": "Data Bank Manager text: register lines, then tab-indented address/value rows.",
            "type": "register_lines",
            "register_regex": r"^\s*(?P<register>[0-9A-Za-z]+)\s*$",
            "item_regex": r"^\s*(?P<address>[0-9A-Za-z]+)\s+(?P<value>.*)$",
            "multiline_start": "\"\"\"",
            "multiline_end": "\"\"\"",
        },
        "json-workspace-v1": {
            "description": "Native tensor.py JSON workspace format.",
            "type": "json_workspace",
        },
        "json-records-v1": {
            "description": "JSON list of records with bank/register/address/value keys.",
            "type": "json_records",
        },
        "csv-records-v1": {
            "description": "CSV records with bank, register, address, value, optional title.",
            "type": "csv_records",
            "delimiter": ",",
        },
    },
}


# ----------------------------- Data model -----------------------------

@dataclass
class Entry:
    bank: str
    register: str
    address: str
    value: str = ""
    raw_bank: Optional[str] = None
    raw_register: Optional[str] = None
    raw_address: Optional[str] = None
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

    def set_value(self, register: str, address: str, value: str, *, raw_register: Optional[str] = None,
                  raw_address: Optional[str] = None, raw_bank: Optional[str] = None,
                  meta: Optional[Dict[str, Any]] = None) -> Entry:
        self.registers.setdefault(register, {})
        ent = Entry(
            bank=self.id,
            register=register,
            address=address,
            value=value,
            raw_bank=raw_bank or self.raw_id,
            raw_register=raw_register,
            raw_address=raw_address,
            meta=meta or {},
        )
        self.registers[register][address] = ent
        return ent

    def get_value(self, register: str, address: str) -> Optional[str]:
        entry = self.registers.get(register, {}).get(address)
        return None if entry is None else entry.value

    def delete_value(self, register: str, address: str) -> bool:
        reg = self.registers.get(register)
        if not reg or address not in reg:
            return False
        del reg[address]
        if not reg:
            del self.registers[register]
        return True

    def entries(self, sort: bool = True) -> Iterable[Entry]:
        reg_ids = list(self.registers.keys())
        if sort:
            reg_ids = sorted(reg_ids, key=natural_id_key)
        for reg_id in reg_ids:
            addr_ids = list(self.registers[reg_id].keys())
            if sort:
                addr_ids = sorted(addr_ids, key=natural_id_key)
            for addr_id in addr_ids:
                yield self.registers[reg_id][addr_id]


@dataclass
class Workspace:
    banks: Dict[str, Bank] = field(default_factory=dict)
    current_bank_id: Optional[str] = None
    dirty: bool = False
    history: List[Dict[str, Any]] = field(default_factory=list)

    def snapshot(self, limit: int = 64) -> None:
        self.history.append(self.to_dict(include_meta=True))
        if len(self.history) > limit:
            self.history = self.history[-limit:]

    def undo(self) -> bool:
        if not self.history:
            return False
        previous = self.history.pop()
        restored = Workspace.from_dict(previous)
        self.banks = restored.banks
        self.current_bank_id = restored.current_bank_id
        self.dirty = True
        return True

    def create_bank(self, bank_id: str, title: str = "", raw_id: Optional[str] = None) -> Bank:
        bank = Bank(id=bank_id, title=title, raw_id=raw_id)
        self.banks[bank_id] = bank
        if self.current_bank_id is None:
            self.current_bank_id = bank_id
        self.dirty = True
        return bank

    def get_bank(self, bank_id: str) -> Optional[Bank]:
        return self.banks.get(bank_id)

    def get_or_create_bank(self, bank_id: str, title: str = "", raw_id: Optional[str] = None) -> Bank:
        bank = self.get_bank(bank_id)
        if bank is None:
            bank = self.create_bank(bank_id, title=title, raw_id=raw_id)
        elif title and not bank.title:
            bank.title = title
        return bank

    def set_value(self, bank: str, register: str, address: str, value: str,
                  raw_bank: Optional[str] = None, raw_register: Optional[str] = None,
                  raw_address: Optional[str] = None, title: str = "") -> Entry:
        b = self.get_or_create_bank(bank, title=title, raw_id=raw_bank)
        self.dirty = True
        return b.set_value(register, address, value, raw_bank=raw_bank, raw_register=raw_register, raw_address=raw_address)

    def get_value(self, bank: str, register: str, address: str) -> Optional[str]:
        b = self.get_bank(bank)
        return None if b is None else b.get_value(register, address)

    def delete_value(self, bank: str, register: str, address: str) -> bool:
        b = self.get_bank(bank)
        if b is None:
            return False
        ok = b.delete_value(register, address)
        if ok:
            self.dirty = True
        return ok

    def entries(self, sort: bool = True) -> Iterable[Entry]:
        bank_ids = list(self.banks.keys())
        if sort:
            bank_ids = sorted(bank_ids, key=natural_id_key)
        for bank_id in bank_ids:
            yield from self.banks[bank_id].entries(sort=sort)

    def stats(self) -> Dict[str, Any]:
        registers = sum(len(b.registers) for b in self.banks.values())
        addresses = sum(len(reg) for b in self.banks.values() for reg in b.registers.values())
        non_empty = sum(1 for e in self.entries(sort=False) if e.value != "")
        return {
            "banks": len(self.banks),
            "registers": registers,
            "addresses": addresses,
            "non_empty_values": non_empty,
            "current_bank_id": self.current_bank_id,
            "dirty": self.dirty,
        }

    def to_dict(self, include_meta: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "type": "tensor-workspace-v1",
            "current_bank_id": self.current_bank_id,
            "banks": {},
        }
        for bank_id, bank in self.banks.items():
            bdata: Dict[str, Any] = {
                "id": bank.id,
                "title": bank.title,
                "raw_id": bank.raw_id,
                "registers": {},
            }
            if include_meta:
                bdata["meta"] = bank.meta
            for reg_id, entries in bank.registers.items():
                bdata["registers"][reg_id] = {}
                for addr_id, entry in entries.items():
                    if include_meta:
                        bdata["registers"][reg_id][addr_id] = {
                            "value": entry.value,
                            "raw_bank": entry.raw_bank,
                            "raw_register": entry.raw_register,
                            "raw_address": entry.raw_address,
                            "meta": entry.meta,
                        }
                    else:
                        bdata["registers"][reg_id][addr_id] = entry.value
            data["banks"][bank_id] = bdata
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Workspace":
        ws = Workspace()
        ws.current_bank_id = data.get("current_bank_id")
        banks = data.get("banks", {})
        for bank_key, bdata in banks.items():
            if isinstance(bdata, dict) and "registers" in bdata:
                bank_id = str(bdata.get("id", bank_key))
                bank = Bank(id=bank_id, title=str(bdata.get("title", "")), raw_id=bdata.get("raw_id"), meta=bdata.get("meta", {}))
                for reg_id, addr_map in bdata.get("registers", {}).items():
                    for addr_id, value_obj in addr_map.items():
                        if isinstance(value_obj, dict) and "value" in value_obj:
                            value = str(value_obj.get("value", ""))
                            bank.set_value(
                                str(reg_id), str(addr_id), value,
                                raw_bank=value_obj.get("raw_bank"),
                                raw_register=value_obj.get("raw_register"),
                                raw_address=value_obj.get("raw_address"),
                                meta=value_obj.get("meta", {}),
                            )
                        else:
                            bank.set_value(str(reg_id), str(addr_id), str(value_obj))
                ws.banks[bank.id] = bank
            elif isinstance(bdata, dict):
                bank = Bank(id=str(bank_key))
                for reg_id, addr_map in bdata.items():
                    if isinstance(addr_map, dict):
                        for addr_id, value in addr_map.items():
                            bank.set_value(str(reg_id), str(addr_id), str(value))
                ws.banks[bank.id] = bank
        return ws


# ----------------------------- Config and IDs -----------------------------

def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_json(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config(path: Optional[str | Path] = None) -> Dict[str, Any]:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path:
        cfg = deep_merge(cfg, load_json(path))
    return cfg


def save_config(config: Dict[str, Any], path: str | Path) -> None:
    with open(path, "w", encoding=config.get("output", {}).get("encoding", "utf-8")) as f:
        json.dump(config, f, indent=int(config.get("output", {}).get("indent", 2)), ensure_ascii=False)
        f.write("\n")


def parse_json_value(text: str) -> Any:
    text = text.strip()
    if text == "":
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def set_path(obj: Dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur: Dict[str, Any] = obj
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


def get_path(obj: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur: Any = obj
    for p in dotted.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def natural_id_key(value: str) -> Tuple[int, Any]:
    try:
        return (0, int(str(value), 10))
    except Exception:
        return (1, str(value))


def strip_config_prefix(raw: str, config: Dict[str, Any]) -> str:
    s = str(raw).strip()
    prefix = str(config.get("id", {}).get("prefix", ""))
    if prefix and config.get("id", {}).get("strip_prefix_on_parse", True):
        if s.lower().startswith(prefix.lower()):
            return s[len(prefix):]
    return s


def canonical_id(raw: str | int, config: Dict[str, Any]) -> str:
    s = strip_config_prefix(str(raw).strip(), config)
    if s == "":
        return s
    if not config.get("id", {}).get("canonicalize_numeric_ids", True):
        return s
    base = int(config.get("id", {}).get("base", 10))
    try:
        return str(int(s, base))
    except Exception:
        return s


def format_id(canonical: str, kind: str, config: Dict[str, Any], raw: Optional[str] = None) -> str:
    out_cfg = config.get("output", {})
    if raw and out_cfg.get("use_original_ids_when_available", True):
        return raw
    widths = {
        "bank": "width_bank",
        "register": "width_register",
        "address": "width_address",
    }
    width = int(config.get("id", {}).get(widths.get(kind, "width_address"), 0))
    base = int(config.get("id", {}).get("base", 10))
    try:
        n = int(str(canonical), 10)
        if base == 10:
            s = str(n)
        else:
            digits = "0123456789abcdefghijklmnopqrstuvwxyz"
            if n == 0:
                s = "0"
            else:
                parts = []
                q = n
                while q:
                    q, r = divmod(q, base)
                    parts.append(digits[r])
                s = "".join(reversed(parts))
        return s.zfill(width) if width else s
    except Exception:
        return str(canonical)


# ----------------------------- Parsing -----------------------------

class TensorParser:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def parse_file(self, path: str | Path, format_id: Optional[str] = None) -> Workspace:
        path = Path(path)
        max_bytes = int(self.config.get("limits", {}).get("max_file_bytes", 20_000_000))
        if path.stat().st_size > max_bytes:
            raise ValueError(f"Input file is too large: {path.stat().st_size} bytes > {max_bytes} bytes")
        encoding = self.config.get("input", {}).get("encoding", "utf-8")
        text = path.read_text(encoding=encoding)
        return self.parse_text(text, format_id=format_id, source=str(path))

    def parse_text(self, text: str, format_id: Optional[str] = None, source: str = "<text>") -> Workspace:
        fid = format_id or self.config.get("input", {}).get("format_id", "tensor-block-v1")
        formats = self.config.get("formats", {})
        if fid not in formats:
            raise KeyError(f"Unknown input format_id: {fid}. Use :formats to list available formats.")
        spec = formats[fid]
        typ = spec.get("type", "block")
        if typ == "block":
            return self._parse_block(text, spec, source)
        if typ == "register_lines":
            return self._parse_register_lines(text, spec, source)
        if typ == "json_workspace":
            return Workspace.from_dict(json.loads(text))
        if typ == "json_records":
            return self._parse_json_records(text, source)
        if typ == "csv_records":
            return self._parse_csv_records(text, spec, source)
        raise ValueError(f"Unsupported parser type: {typ}")

    def _parse_block(self, text: str, spec: Dict[str, Any], source: str) -> Workspace:
        ws = Workspace()
        header_re = re.compile(spec["header_regex"])
        end_re = re.compile(spec.get("end_regex", r"^\s*}\s*$"))
        item_re = re.compile(spec["item_regex"])
        reg_re = re.compile(spec.get("register_regex", r"^\s*(?P<register>[0-9A-Za-z]+)\s*$"))
        default_reg_raw = spec.get("default_register_id", self.config.get("input", {}).get("default_register_id", "1"))
        current_bank: Optional[Bank] = None
        current_reg = canonical_id(default_reg_raw, self.config)
        current_reg_raw = str(default_reg_raw)
        multiline_for: Optional[Tuple[Bank, str, str, str]] = None
        multiline_buffer: List[str] = []
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for line_no, line in enumerate(lines, start=1):
            if multiline_for is not None:
                if line.strip() == spec.get("multiline_end", '"""'):
                    bank, reg_id, addr_id, raw_addr = multiline_for
                    bank.set_value(reg_id, addr_id, "\n".join(multiline_buffer), raw_register=current_reg_raw, raw_address=raw_addr,
                                   meta={"source": source, "line": line_no})
                    multiline_for = None
                    multiline_buffer = []
                else:
                    multiline_buffer.append(line)
                continue

            if not line.strip():
                continue
            hm = header_re.match(line)
            if hm:
                raw_bank = hm.group("bank")
                bank_id = canonical_id(raw_bank, self.config)
                title = hm.groupdict().get("title") or ""
                current_bank = ws.get_or_create_bank(bank_id, title=title.strip(), raw_id=raw_bank)
                current_reg_raw = str(default_reg_raw)
                current_reg = canonical_id(current_reg_raw, self.config)
                continue
            if end_re.match(line):
                current_bank = None
                continue
            if current_bank is None:
                continue
            # Register lines are only accepted when the line is not visibly an indented address row.
            if not line.startswith(("\t", " ")):
                rm = reg_re.match(line)
                if rm and "register" in rm.groupdict():
                    current_reg_raw = rm.group("register")
                    current_reg = canonical_id(current_reg_raw, self.config)
                    continue
            im = item_re.match(line)
            if im:
                raw_addr = im.group("address")
                addr_id = canonical_id(raw_addr, self.config)
                value = im.groupdict().get("value", "")
                if value.strip() == spec.get("multiline_start", '"""'):
                    multiline_for = (current_bank, current_reg, addr_id, raw_addr)
                    multiline_buffer = []
                else:
                    current_bank.set_value(current_reg, addr_id, value, raw_register=current_reg_raw, raw_address=raw_addr,
                                           meta={"source": source, "line": line_no})
        if multiline_for is not None:
            raise ValueError("Unclosed multiline value at end of file.")
        return ws

    def _parse_register_lines(self, text: str, spec: Dict[str, Any], source: str) -> Workspace:
        default_bank_raw = self.config.get("input", {}).get("default_bank_id", "1")
        bank_id = canonical_id(default_bank_raw, self.config)
        ws = Workspace()
        bank = ws.get_or_create_bank(bank_id, title=Path(source).stem if source != "<text>" else "bank", raw_id=str(default_bank_raw))
        reg_re = re.compile(spec["register_regex"])
        item_re = re.compile(spec["item_regex"])
        current_reg = canonical_id(self.config.get("input", {}).get("default_register_id", "1"), self.config)
        current_reg_raw = self.config.get("input", {}).get("default_register_id", "1")
        multiline_for: Optional[Tuple[str, str]] = None
        multiline_buffer: List[str] = []
        for line_no, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
            if multiline_for is not None:
                if line.strip() == spec.get("multiline_end", '"""'):
                    reg_id, addr_id = multiline_for
                    bank.set_value(reg_id, addr_id, "\n".join(multiline_buffer), raw_register=current_reg_raw,
                                   meta={"source": source, "line": line_no})
                    multiline_for = None
                    multiline_buffer = []
                else:
                    multiline_buffer.append(line)
                continue
            if not line.strip():
                continue
            if not line.startswith(("\t", " ")):
                rm = reg_re.match(line)
                if rm:
                    current_reg_raw = rm.group("register")
                    current_reg = canonical_id(current_reg_raw, self.config)
                    continue
            im = item_re.match(line)
            if im:
                raw_addr = im.group("address")
                addr_id = canonical_id(raw_addr, self.config)
                value = im.groupdict().get("value", "")
                if value.strip() == spec.get("multiline_start", '"""'):
                    multiline_for = (current_reg, addr_id)
                    multiline_buffer = []
                else:
                    bank.set_value(current_reg, addr_id, value, raw_register=current_reg_raw, raw_address=raw_addr,
                                   meta={"source": source, "line": line_no})
        if multiline_for is not None:
            raise ValueError("Unclosed multiline value at end of file.")
        return ws

    def _parse_json_records(self, text: str, source: str) -> Workspace:
        data = json.loads(text)
        if isinstance(data, dict):
            records = data.get("records", [])
        else:
            records = data
        ws = Workspace()
        for i, rec in enumerate(records, start=1):
            bank_raw = str(rec.get("bank", rec.get("bank_id", self.config.get("input", {}).get("default_bank_id", "1"))))
            reg_raw = str(rec.get("register", rec.get("register_id", self.config.get("input", {}).get("default_register_id", "1"))))
            addr_raw = str(rec.get("address", rec.get("address_id", i)))
            value = str(rec.get("value", ""))
            title = str(rec.get("title", ""))
            ws.set_value(canonical_id(bank_raw, self.config), canonical_id(reg_raw, self.config), canonical_id(addr_raw, self.config), value,
                         raw_bank=bank_raw, raw_register=reg_raw, raw_address=addr_raw, title=title)
        return ws

    def _parse_csv_records(self, text: str, spec: Dict[str, Any], source: str) -> Workspace:
        ws = Workspace()
        reader = csv.DictReader(io.StringIO(text), delimiter=spec.get("delimiter", ","))
        for i, rec in enumerate(reader, start=1):
            bank_raw = str(rec.get("bank") or rec.get("bank_id") or self.config.get("input", {}).get("default_bank_id", "1"))
            reg_raw = str(rec.get("register") or rec.get("register_id") or self.config.get("input", {}).get("default_register_id", "1"))
            addr_raw = str(rec.get("address") or rec.get("address_id") or i)
            value = str(rec.get("value") or "")
            title = str(rec.get("title") or "")
            ws.set_value(canonical_id(bank_raw, self.config), canonical_id(reg_raw, self.config), canonical_id(addr_raw, self.config), value,
                         raw_bank=bank_raw, raw_register=reg_raw, raw_address=addr_raw, title=title)
        return ws


# ----------------------------- Resolver and processing -----------------------------

class TensorResolver:
    def __init__(self, workspace: Workspace, config: Dict[str, Any]):
        self.ws = workspace
        self.config = config
        self.patterns = self.config.get("references", {}).get("patterns", {})

    def resolve_value(self, value: str, context_bank: Optional[str] = None, context_register: str = "1",
                      depth: int = 0, visited: Optional[set[str]] = None) -> str:
        if visited is None:
            visited = set()
        max_depth = int(self.config.get("limits", {}).get("max_resolve_depth", 32))
        if depth >= max_depth:
            return self.config.get("references", {}).get("depth_exceeded", "[Resolver Depth Exceeded]")
        result = str(value)
        for name in ["prefixed_full", "local_register", "full", "two_part"]:
            pattern = self.patterns.get(name)
            if not pattern:
                continue
            result = re.sub(pattern, lambda m, n=name: self._replace_match(m, n, context_bank, context_register, depth, visited), result)
        return result

    def _replace_match(self, match: re.Match[str], pattern_name: str, context_bank: Optional[str],
                       context_register: str, depth: int, visited: set[str]) -> str:
        gd = match.groupdict()
        raw_ref = match.group(0)
        if pattern_name in ("prefixed_full", "full"):
            bank = canonical_id(gd["bank"], self.config)
            register = canonical_id(gd["register"], self.config)
            address = canonical_id(gd["address"], self.config)
        elif pattern_name == "local_register":
            if context_bank is None:
                return raw_ref
            bank = context_bank
            register = canonical_id(gd["register"], self.config)
            address = canonical_id(gd["address"], self.config)
        elif pattern_name == "two_part":
            mode = self.config.get("references", {}).get("two_part_mode", "bank_address")
            if mode == "local_register_address":
                if context_bank is None:
                    return raw_ref
                bank = context_bank
                register = canonical_id(gd["left"], self.config)
                address = canonical_id(gd["right"], self.config)
            else:
                bank = canonical_id(gd["left"], self.config)
                register = canonical_id(self.config.get("input", {}).get("default_register_id", "1"), self.config)
                address = canonical_id(gd["right"], self.config)
        else:
            return raw_ref

        key = f"{bank}.{register}.{address}"
        if key in visited:
            return self.config.get("references", {}).get("circular", "[Circular Ref: {ref}]").format(ref=raw_ref)
        value = self.ws.get_value(bank, register, address)
        if value is None:
            return self.config.get("references", {}).get("missing", "[Missing Ref: {ref}]").format(ref=raw_ref)
        new_visited = set(visited)
        new_visited.add(key)
        return self.resolve_value(value, bank, register, depth + 1, new_visited)


def clone_workspace(ws: Workspace) -> Workspace:
    return Workspace.from_dict(ws.to_dict(include_meta=True))


def apply_pipeline(ws: Workspace, config: Dict[str, Any]) -> Workspace:
    pipeline = config.get("processing", {}).get("pipeline", []) or []
    out = clone_workspace(ws)
    resolver = TensorResolver(out, config)
    drop: List[Tuple[str, str, str]] = []
    for op in pipeline:
        if isinstance(op, str):
            name, args = op, {}
        elif isinstance(op, dict):
            name, args = op.get("op", ""), op
        else:
            continue
        for entry in list(out.entries(sort=False)):
            v = entry.value
            if name == "trim":
                entry.value = v.strip()
            elif name == "lower":
                entry.value = v.lower()
            elif name == "upper":
                entry.value = v.upper()
            elif name == "resolve":
                entry.value = resolver.resolve_value(v, entry.bank, entry.register)
            elif name == "replace_regex":
                pattern = str(args.get("pattern", ""))
                repl = str(args.get("replacement", ""))
                if pattern:
                    entry.value = re.sub(pattern, repl, v)
            elif name == "prefix":
                entry.value = str(args.get("text", "")) + v
            elif name == "suffix":
                entry.value = v + str(args.get("text", ""))
            elif name == "token_count":
                entry.meta["token_count"] = len(v.split())
            elif name == "char_count":
                entry.meta["char_count"] = len(v)
            elif name == "drop_empty":
                if v == "":
                    drop.append((entry.bank, entry.register, entry.address))
    for b, r, a in drop:
        out.delete_value(b, r, a)
    out.dirty = ws.dirty
    out.current_bank_id = ws.current_bank_id
    return out


# ----------------------------- Rendering/export -----------------------------

class TensorRenderer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def render(self, ws: Workspace, fmt: Optional[str] = None) -> str:
        fmt = fmt or self.config.get("output", {}).get("format", "json")
        sort = bool(self.config.get("output", {}).get("sort", True))
        if fmt == "json":
            return json.dumps(ws.to_dict(include_meta=bool(self.config.get("output", {}).get("include_meta", True))),
                              indent=int(self.config.get("output", {}).get("indent", 2)), ensure_ascii=False) + "\n"
        if fmt == "summary":
            return json.dumps(ws.stats(), indent=int(self.config.get("output", {}).get("indent", 2)), ensure_ascii=False) + "\n"
        if fmt == "jsonl":
            return "".join(json.dumps(self._entry_record(e, ws), ensure_ascii=False) + "\n" for e in ws.entries(sort=sort))
        if fmt == "csv":
            return self._render_csv(ws, sort=sort)
        if fmt == "markdown":
            return self._render_markdown(ws, sort=sort)
        if fmt == "tensor_text":
            return self._render_tensor_text(ws, sort=sort)
        if fmt == "databank_text":
            return self._render_databank_text(ws, sort=sort)
        if fmt == "dot":
            return self._render_dot(ws, sort=sort)
        raise ValueError(f"Unknown output format: {fmt}")

    def _entry_record(self, e: Entry, ws: Workspace) -> Dict[str, Any]:
        bank = ws.banks[e.bank]
        rec = {
            "bank": e.bank,
            "bank_title": bank.title,
            "register": e.register,
            "address": e.address,
            "ref": e.ref(),
            "value": e.value,
        }
        if self.config.get("output", {}).get("include_meta", True):
            rec["meta"] = e.meta
        return rec

    def _render_csv(self, ws: Workspace, sort: bool = True) -> str:
        out = io.StringIO()
        fieldnames = ["bank", "bank_title", "register", "address", "ref", "value"]
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for e in ws.entries(sort=sort):
            bank = ws.banks[e.bank]
            writer.writerow({"bank": e.bank, "bank_title": bank.title, "register": e.register, "address": e.address, "ref": e.ref(), "value": e.value})
        return out.getvalue()

    def _render_markdown(self, ws: Workspace, sort: bool = True) -> str:
        lines = ["| bank | title | register | address | ref | value |", "|---:|---|---:|---:|---|---|"]
        for e in ws.entries(sort=sort):
            title = ws.banks[e.bank].title.replace("|", "\\|")
            value = e.value.replace("|", "\\|").replace("\n", "<br>")
            lines.append(f"| {e.bank} | {title} | {e.register} | {e.address} | `{e.ref()}` | {value} |")
        return "\n".join(lines) + "\n"

    def _render_tensor_text(self, ws: Workspace, sort: bool = True) -> str:
        lines: List[str] = []
        bank_ids = list(ws.banks.keys())
        if sort:
            bank_ids = sorted(bank_ids, key=natural_id_key)
        for bank_id in bank_ids:
            bank = ws.banks[bank_id]
            raw_bank = format_id(bank.id, "bank", self.config, bank.raw_id)
            title = bank.title or "bank"
            lines.append(f"{raw_bank} ( {title} ) {{")
            entries = list(bank.entries(sort=sort))
            for e in entries:
                addr = format_id(e.address, "address", self.config, e.raw_address)
                if "\n" in e.value and self.config.get("output", {}).get("quote_multiline", True):
                    lines.append(f"\t{addr}\t\"\"\"")
                    lines.extend(e.value.split("\n"))
                    lines.append("\t\"\"\"")
                else:
                    lines.append(f"\t{addr}\t{e.value}")
            lines.append("")
            lines.append("}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _render_databank_text(self, ws: Workspace, sort: bool = True) -> str:
        lines: List[str] = []
        bank_id = ws.current_bank_id or (sorted(ws.banks.keys(), key=natural_id_key)[0] if ws.banks else None)
        if not bank_id:
            return ""
        bank = ws.banks[bank_id]
        reg_ids = list(bank.registers.keys())
        if sort:
            reg_ids = sorted(reg_ids, key=natural_id_key)
        for reg_id in reg_ids:
            lines.append(format_id(reg_id, "register", self.config, None))
            addr_ids = list(bank.registers[reg_id].keys())
            if sort:
                addr_ids = sorted(addr_ids, key=natural_id_key)
            for addr_id in addr_ids:
                e = bank.registers[reg_id][addr_id]
                addr = format_id(addr_id, "address", self.config, e.raw_address)
                if "\n" in e.value and self.config.get("output", {}).get("quote_multiline", True):
                    lines.append(f"\t{addr}\t\"\"\"")
                    lines.extend(e.value.split("\n"))
                    lines.append("\t\"\"\"")
                else:
                    lines.append(f"\t{addr}\t{e.value}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _render_dot(self, ws: Workspace, sort: bool = True) -> str:
        resolver_patterns = self.config.get("references", {}).get("patterns", {})
        ref_regexes = [re.compile(p) for p in resolver_patterns.values() if p]
        lines = ["digraph tensor {", "  rankdir=LR;"]
        for e in ws.entries(sort=sort):
            label = e.value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            lines.append(f'  "{e.ref()}" [label="{e.ref()}\\n{label[:80]}"];')
        for e in ws.entries(sort=sort):
            targets = extract_references(e.value, e.bank, e.register, self.config)
            for target in targets:
                lines.append(f'  "{e.ref()}" -> "{target}";')
        lines.append("}")
        return "\n".join(lines) + "\n"


def extract_references(value: str, context_bank: Optional[str], context_register: str, config: Dict[str, Any]) -> List[str]:
    refs: List[str] = []
    patterns = config.get("references", {}).get("patterns", {})
    for name in ["prefixed_full", "local_register", "full", "two_part"]:
        pattern = patterns.get(name)
        if not pattern:
            continue
        for m in re.finditer(pattern, value):
            gd = m.groupdict()
            if name in ("prefixed_full", "full"):
                b = canonical_id(gd["bank"], config)
                r = canonical_id(gd["register"], config)
                a = canonical_id(gd["address"], config)
            elif name == "local_register":
                if context_bank is None:
                    continue
                b = context_bank
                r = canonical_id(gd["register"], config)
                a = canonical_id(gd["address"], config)
            else:
                mode = config.get("references", {}).get("two_part_mode", "bank_address")
                if mode == "local_register_address":
                    if context_bank is None:
                        continue
                    b = context_bank
                    r = canonical_id(gd["left"], config)
                    a = canonical_id(gd["right"], config)
                else:
                    b = canonical_id(gd["left"], config)
                    r = canonical_id(config.get("input", {}).get("default_register_id", "1"), config)
                    a = canonical_id(gd["right"], config)
            ref = f"{b}.{r}.{a}"
            if ref not in refs:
                refs.append(ref)
    return refs


# ----------------------------- Search/import/export helpers -----------------------------

def merge_workspace(target: Workspace, incoming: Workspace, mode: str = "replace") -> None:
    if mode == "replace":
        for bank_id, bank in incoming.banks.items():
            target.banks[bank_id] = bank
    elif mode == "merge":
        for bank_id, bank in incoming.banks.items():
            tb = target.get_or_create_bank(bank_id, title=bank.title, raw_id=bank.raw_id)
            for e in bank.entries(sort=False):
                tb.set_value(e.register, e.address, e.value, raw_register=e.raw_register, raw_address=e.raw_address,
                             raw_bank=e.raw_bank, meta=e.meta)
    else:
        raise ValueError("merge_mode must be replace or merge")
    if incoming.current_bank_id:
        target.current_bank_id = incoming.current_bank_id
    elif target.current_bank_id is None and target.banks:
        target.current_bank_id = next(iter(target.banks))
    target.dirty = True


def search_workspace(ws: Workspace, query: str, regex: bool = False, case_sensitive: bool = False) -> List[Entry]:
    results: List[Entry] = []
    if regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(query, flags)
        for e in ws.entries():
            if pattern.search(e.value) or pattern.search(e.ref()):
                results.append(e)
    else:
        q = query if case_sensitive else query.lower()
        for e in ws.entries():
            hay = f"{e.ref()} {e.value}"
            hay_cmp = hay if case_sensitive else hay.lower()
            if q in hay_cmp:
                results.append(e)
    return results


def parse_ref(text: str, config: Dict[str, Any], current_bank: Optional[str] = None) -> Tuple[str, str, str]:
    s = text.strip()
    s = strip_config_prefix(s, config)
    parts = s.split(".")
    default_reg = canonical_id(config.get("input", {}).get("default_register_id", "1"), config)
    if len(parts) == 3:
        return canonical_id(parts[0], config), canonical_id(parts[1], config), canonical_id(parts[2], config)
    if len(parts) == 2:
        mode = config.get("references", {}).get("two_part_mode", "bank_address")
        if mode == "local_register_address" and current_bank:
            return current_bank, canonical_id(parts[0], config), canonical_id(parts[1], config)
        return canonical_id(parts[0], config), default_reg, canonical_id(parts[1], config)
    if len(parts) == 1 and current_bank:
        return current_bank, default_reg, canonical_id(parts[0], config)
    raise ValueError("Reference must be address, bank.address, bank.register.address, or prefixed full reference.")


# ----------------------------- Format/compose process-flow integration -----------------------------

_FORMAT_COMPOSE_MODULES: Optional[Tuple[Any, Any]] = None


def _load_module_from_path(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_format_compose_modules() -> Tuple[Any, Any]:
    """Load 23.py and 24.py as essential in-process REPL process flows."""
    global _FORMAT_COMPOSE_MODULES
    if _FORMAT_COMPOSE_MODULES is not None:
        return _FORMAT_COMPOSE_MODULES
    tool_dir = Path(__file__).resolve().parent
    format_module = sys.modules.get("format_paste")
    if format_module is None:
        format_module = _load_module_from_path("format_paste", tool_dir / "23.py")
    compose_module = sys.modules.get("compose_flow")
    if compose_module is None:
        compose_module = _load_module_from_path("compose_flow", tool_dir / "24.py")
    _FORMAT_COMPOSE_MODULES = (format_module, compose_module)
    return _FORMAT_COMPOSE_MODULES


def split_option_args(args: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    positionals: List[str] = []
    options: Dict[str, Any] = {}
    i = 0
    while i < len(args):
        item = args[i]
        if not item.startswith("--"):
            positionals.append(item)
            i += 1
            continue
        key = item[2:].replace("-", "_")
        if key in {"no_pointers", "pointer_unique", "stdout"}:
            options[key] = True
            i += 1
            continue
        if key in {"set", "set_profile", "set_tensor_config"}:
            if i + 2 >= len(args):
                raise ValueError(f"missing path/value pair for {item}")
            options.setdefault(key, []).append((args[i + 1], args[i + 2]))
            i += 3
            continue
        if i + 1 >= len(args):
            raise ValueError(f"missing value for {item}")
        value = args[i + 1]
        if key in {"category", "register", "ref", "pointer_rule"}:
            options.setdefault(key, []).append(value)
        else:
            options[key] = value
        i += 2
    return positionals, options


def apply_digest_options(profile: Dict[str, Any], options: Dict[str, Any]) -> None:
    for dotted, value in options.get("set_profile", []) or []:
        set_path(profile, dotted, parse_json_value(value))
    if "categories" in options:
        categories = [part.strip() for part in str(options["categories"]).split(",") if part.strip()]
        profile.setdefault("categories", {})["enabled"] = [cat for cat in categories if cat != "pointer"]
        profile.setdefault("pointers", {})["enabled"] = "pointer" in categories and not options.get("no_pointers", False)
    if "category" in options:
        categories = [str(value) for value in options["category"]]
        profile.setdefault("categories", {})["enabled"] = [cat for cat in categories if cat != "pointer"]
        profile.setdefault("pointers", {})["enabled"] = "pointer" in categories and not options.get("no_pointers", False)
    if options.get("no_pointers"):
        profile.setdefault("pointers", {})["enabled"] = False
    if "bank_id" in options:
        profile.setdefault("bank", {})["id"] = str(options["bank_id"])
        profile.setdefault("bank", {})["raw_id"] = str(options["bank_id"])
    if "bank_title" in options:
        profile.setdefault("bank", {})["title"] = str(options["bank_title"])
    for rule_text in options.get("pointer_rule", []) or []:
        profile.setdefault("pointers", {}).setdefault("rules", []).append(json.loads(rule_text))


def last_option_value(value: Any) -> Any:
    if isinstance(value, list):
        return value[-1] if value else None
    return value


def compose_namespace_from_options(options: Dict[str, Any], output_path: str, output_format: Optional[str]) -> argparse.Namespace:
    return argparse.Namespace(
        set=options.get("set"),
        input_format=None,
        category=options.get("category"),
        register=options.get("register"),
        ref=options.get("ref"),
        value_regex=options.get("value_regex"),
        source_mode=options.get("source_mode"),
        pointer_relation=options.get("pointer_relation"),
        pointer_rule=last_option_value(options.get("pointer_rule")),
        source_ref=options.get("source_ref"),
        source_category=options.get("source_category"),
        target_category=options.get("target_category"),
        output=output_path,
        format=output_format,
        entry_template=options.get("entry_template"),
        join=options.get("join"),
    )


# ----------------------------- CLI UI -----------------------------

HELP = """
Tensor CLI/UI commands
──────────────────────
:help                                  show this help
:formats                               list configured input formats
:config show                           print active config JSON
:config get <path>                     print one config value, e.g. references.reading_mode
:config set <path> <json-value>         set config value, e.g. output.format "markdown"
:config load <file.json>               load and merge config
:config save [file.json]               save active config, default config-id.json
:load <file> [format_id]               import file according to a configured input format
:digest <text-file> [options]          run 23.py text-data digestion and merge generated records
:digest-text [options] -- <text>       run 23.py digestion on literal command text
:compose <file|-> [format] [options]   run 24.py compose export from the active workspace
:summary                               show workspace counts
:show [bank_id] [format]               show current/all data in output format
:open <bank_id>                        set current bank
:ls                                    list banks
:get <ref>                             get value by ref: addr, bank.addr, or bank.reg.addr
:set <ref> <value>                     set value
:del <ref>                             delete value
:resolve <ref-or-text>                 resolve a value, path, or free text
:search <text>                         search refs and values
:pipeline show                         show processing pipeline
:pipeline add <op> [json-object]        add pipeline op, e.g. :pipeline add resolve
:pipeline clear                        clear processing pipeline
:mode raw|resolve                      set reading mode; resolve adds resolver at render-time
:export <file> [format]                export workspace; formats: json,jsonl,csv,markdown,tensor_text,databank_text,summary,dot
:undo                                  restore previous mutating operation
:clear                                 clear terminal screen
:q                                     quit

Digest options:
  --profile PATH --merge-mode replace|merge --categories a,b,c --category word
  --no-pointers --bank-id ID --bank-title TITLE --pointer-rule JSON
  --set-profile PATH JSON_VALUE --set-tensor-config PATH JSON_VALUE

Compose options:
  --config PATH --set PATH JSON_VALUE --category CAT --register REG --ref REF --value-regex REGEX
  --source-mode entries|pointer_entries|pointer_targets|pointer_sources
  --pointer-relation REL --pointer-rule NAME --source-ref REF --pointer-unique
  --source-category CAT --target-category CAT --entry-template TEMPLATE --join TEXT
""".strip()


class TensorCLI:
    def __init__(self, config: Dict[str, Any], workspace: Optional[Workspace] = None):
        self.config = config
        self.ws = workspace or Workspace()
        self.parser = TensorParser(self.config)
        self.renderer = TensorRenderer(self.config)
        self.command_history: List[str] = []

    def run(self) -> None:
        print("TENSOR CLI/UI - configurable input → processing → output system")
        print("Type :help for commands. Type :q to quit.")
        while True:
            try:
                line = input("tensor> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                self.execute(line)
            except SystemExit:
                break
            except Exception as e:
                print(f"ERROR: {e}")

    def execute(self, line: str) -> Optional[str]:
        raw = line.rstrip("\n")
        if not raw.strip():
            return None
        if raw != (self.command_history[-1] if self.command_history else None):
            self.command_history.append(raw)
            if len(self.command_history) > 500:
                self.command_history = self.command_history[-500:]
        if not raw.startswith(":"):
            print("Commands must start with ':'; use :help.")
            return None
        parts = shlex.split(raw)
        cmd = parts[0]
        args = parts[1:]
        if cmd in (":q", ":quit", ":exit"):
            raise SystemExit
        if cmd == ":help":
            print(HELP)
        elif cmd == ":formats":
            for fid, spec in self.config.get("formats", {}).items():
                print(f"{fid}: {spec.get('description', spec.get('type', ''))}")
        elif cmd == ":config":
            self._cmd_config(args)
        elif cmd == ":load":
            self._cmd_load(args)
        elif cmd == ":digest":
            self._cmd_digest(args)
        elif cmd == ":digest-text":
            self._cmd_digest_text(raw, args)
        elif cmd == ":compose":
            self._cmd_compose(args)
        elif cmd == ":summary":
            print(self.renderer.render(self.ws, "summary"), end="")
        elif cmd == ":show":
            self._cmd_show(args)
        elif cmd == ":open":
            self._cmd_open(args)
        elif cmd == ":ls":
            self._cmd_ls()
        elif cmd == ":get":
            self._cmd_get(args)
        elif cmd == ":set":
            self._cmd_set(raw, args)
        elif cmd == ":del":
            self._cmd_del(args)
        elif cmd == ":resolve":
            self._cmd_resolve(raw, args)
        elif cmd == ":search":
            query = raw.split(" ", 1)[1] if " " in raw else ""
            self._cmd_search(query)
        elif cmd == ":pipeline":
            self._cmd_pipeline(raw, args)
        elif cmd == ":mode":
            if not args or args[0] not in ("raw", "resolve"):
                print("Usage: :mode raw|resolve")
            else:
                self.config.setdefault("references", {})["reading_mode"] = args[0]
                print(f"reading_mode={args[0]}")
        elif cmd == ":export":
            self._cmd_export(args)
        elif cmd == ":undo":
            print("undo: ok" if self.ws.undo() else "undo: no history")
        elif cmd == ":clear":
            os.system("cls" if os.name == "nt" else "clear")
        else:
            print(f"Unknown command: {cmd}. Use :help.")
        return None

    def _snapshot(self) -> None:
        self.ws.snapshot(int(self.config.get("limits", {}).get("max_undo", 64)))

    def _materialized(self) -> Workspace:
        ws = self.ws
        pipeline = list(self.config.get("processing", {}).get("pipeline", []) or [])
        if self.config.get("references", {}).get("reading_mode") == "resolve" and "resolve" not in [p if isinstance(p, str) else p.get("op") for p in pipeline]:
            cfg = copy.deepcopy(self.config)
            cfg.setdefault("processing", {})["pipeline"] = pipeline + ["resolve"]
            return apply_pipeline(ws, cfg)
        return apply_pipeline(ws, self.config)

    def _cmd_config(self, args: List[str]) -> None:
        if not args or args[0] == "show":
            print(json.dumps(self.config, indent=2, ensure_ascii=False))
        elif args[0] == "get" and len(args) >= 2:
            print(json.dumps(get_path(self.config, args[1]), indent=2, ensure_ascii=False))
        elif args[0] == "set" and len(args) >= 3:
            value = parse_json_value(" ".join(args[2:]))
            set_path(self.config, args[1], value)
            self.parser = TensorParser(self.config)
            self.renderer = TensorRenderer(self.config)
            print(f"set {args[1]} = {json.dumps(value, ensure_ascii=False)}")
        elif args[0] == "load" and len(args) >= 2:
            self.config = deep_merge(self.config, load_json(args[1]))
            self.parser = TensorParser(self.config)
            self.renderer = TensorRenderer(self.config)
            print(f"loaded config: {args[1]}")
        elif args[0] == "save":
            path = args[1] if len(args) >= 2 else "config-id.json"
            save_config(self.config, path)
            print(f"saved config: {path}")
        else:
            print("Usage: :config show|get|set|load|save")

    def _cmd_load(self, args: List[str]) -> None:
        if not args:
            print("Usage: :load <file> [format_id]")
            return
        fmt = args[1] if len(args) >= 2 else None
        incoming = self.parser.parse_file(args[0], fmt)
        self._snapshot()
        merge_workspace(self.ws, incoming, self.config.get("input", {}).get("merge_mode", "replace"))
        print(f"loaded {args[0]}: {incoming.stats()}")

    def _cmd_digest(self, args: List[str]) -> None:
        if not args:
            print("Usage: :digest <text-file> [--profile PATH] [--merge-mode replace|merge] [--categories a,b,c] [--no-pointers]")
            return
        positionals, options = split_option_args(args)
        if not positionals:
            print("Usage: :digest <text-file> [options]")
            return
        path = Path(positionals[0])
        encoding = self.config.get("input", {}).get("encoding", "utf-8")
        text = path.read_text(encoding=encoding)
        self._digest_text(text, source=str(path), options=options)

    def _cmd_digest_text(self, raw: str, args: List[str]) -> None:
        if not args:
            print("Usage: :digest-text [options] -- <literal text>")
            return
        marker = ":digest-text"
        payload = raw[len(marker):].lstrip() if raw.startswith(marker) else " ".join(args)
        options: Dict[str, Any] = {}
        text = payload
        delimiter = re.search(r"(^|\s)--(\s|$)", payload) if payload.startswith("--") else None
        if delimiter:
            option_text = payload[:delimiter.start()].strip()
            text = payload[delimiter.end():]
            if option_text:
                positionals, options = split_option_args(shlex.split(option_text))
                if positionals:
                    raise ValueError("digest-text options must precede -- and cannot include positional values")
        if not text:
            print("Usage: :digest-text [options] -- <literal text>")
            return
        self._digest_text(text, source="<repl-text>", options=options)

    def _digest_text(self, text: str, source: str, options: Dict[str, Any]) -> None:
        format_module, _compose_module = load_format_compose_modules()
        profile_path = options.get("profile")
        profile = format_module.load_format_profile(Path(profile_path) if profile_path else None)
        apply_digest_options(profile, options)
        tensor_config = copy.deepcopy(self.config)
        for dotted, value in options.get("set_tensor_config", []) or []:
            set_path(tensor_config, dotted, parse_json_value(value))
        incoming_native, segments = format_module.create_workspace(text, profile, tensor_config)
        incoming = Workspace.from_dict(incoming_native.to_dict(include_meta=True))
        mode = str(options.get("merge_mode", self.config.get("input", {}).get("merge_mode", "replace")))
        if mode not in {"replace", "merge"}:
            raise ValueError("digest --merge-mode must be replace or merge")
        self._snapshot()
        merge_workspace(self.ws, incoming, mode)
        print(f"digested {source}: segments={len(segments)} mode={mode} stats={incoming.stats()}")

    def _cmd_compose(self, args: List[str]) -> None:
        if not args:
            print("Usage: :compose <file|-> [format] [--config PATH] [--category CAT] [--source-mode MODE] ...")
            return
        positionals, options = split_option_args(args)
        if not positionals:
            print("Usage: :compose <file|-> [format] [options]")
            return
        output_path = positionals[0]
        output_format = positionals[1] if len(positionals) >= 2 else options.get("format")
        _format_module, compose_module = load_format_compose_modules()
        compose_config_path = options.get("config")
        compose_config = compose_module.load_compose_config(Path(compose_config_path) if compose_config_path else None)
        namespace = compose_namespace_from_options(options, "" if output_path == "-" else output_path, output_format)
        compose_config = compose_module.apply_cli_overrides(compose_config, namespace)
        if options.get("pointer_unique"):
            compose_config.setdefault("source", {}).setdefault("pointer", {})["unique"] = True
        tensor_config = copy.deepcopy(self.config)
        workspace = compose_module.workspace_from_dict(self._materialized().to_dict(include_meta=True))
        workspace = compose_module.infer_missing_metadata(workspace, compose_config, tensor_config)
        workspace = compose_module.run_plugins(workspace, compose_config, "before_outputs")
        outputs = compose_config.get("outputs", []) or [{"format": output_format or "custom", "path": "" if output_path == "-" else output_path}]
        encoding = tensor_config.get("output", {}).get("encoding", "utf-8")
        emitted = 0
        for output_cfg in outputs:
            if output_path == "-" and len(outputs) == 1:
                output_cfg = copy.deepcopy(output_cfg)
                output_cfg["path"] = ""
            rendered = compose_module.render_output(workspace, compose_config, tensor_config, output_cfg)
            compose_module.write_text(str(output_cfg.get("path", "")), rendered, encoding=encoding)
            emitted += 1
        destination = "stdout" if output_path == "-" else output_path
        print(f"composed {emitted} output(s) to {destination}")

    def _cmd_show(self, args: List[str]) -> None:
        fmt = args[1] if len(args) >= 2 else (args[0] if len(args) == 1 and args[0] in self._formats_out() else None)
        if len(args) >= 1 and args[0] not in self._formats_out():
            bank_id = canonical_id(args[0], self.config)
            bank = self.ws.get_bank(bank_id)
            if not bank:
                print(f"bank not found: {args[0]}")
                return
            tmp = Workspace(banks={bank_id: copy.deepcopy(bank)}, current_bank_id=bank_id, dirty=self.ws.dirty)
            print(self.renderer.render(apply_pipeline(tmp, self.config), fmt), end="")
        else:
            print(self.renderer.render(self._materialized(), fmt), end="")

    def _cmd_open(self, args: List[str]) -> None:
        if not args:
            print("Usage: :open <bank_id>")
            return
        bank_id = canonical_id(args[0], self.config)
        if bank_id not in self.ws.banks:
            self._snapshot()
            self.ws.create_bank(bank_id, raw_id=args[0])
            print(f"created bank {bank_id}")
        self.ws.current_bank_id = bank_id
        print(f"current_bank_id={bank_id}")

    def _cmd_ls(self) -> None:
        if not self.ws.banks:
            print("no banks loaded")
            return
        for bank_id in sorted(self.ws.banks, key=natural_id_key):
            bank = self.ws.banks[bank_id]
            current = "*" if bank_id == self.ws.current_bank_id else " "
            print(f"{current} {bank_id}\t{bank.title}\tregisters={len(bank.registers)} entries={sum(len(r) for r in bank.registers.values())}")

    def _cmd_get(self, args: List[str]) -> None:
        if not args:
            print("Usage: :get <ref>")
            return
        b, r, a = parse_ref(args[0], self.config, self.ws.current_bank_id)
        val = self.ws.get_value(b, r, a)
        print("[missing]" if val is None else val)

    def _cmd_set(self, raw: str, args: List[str]) -> None:
        if len(args) < 2:
            print("Usage: :set <ref> <value>")
            return
        # Preserve spaces in value by splitting the raw command at the second shell token approximately.
        ref = args[0]
        prefix = f":set {ref}"
        value = raw[len(prefix):].lstrip() if raw.startswith(prefix) else " ".join(args[1:])
        b, r, a = parse_ref(ref, self.config, self.ws.current_bank_id)
        if not self.config.get("id", {}).get("allow_duplicate_values", True):
            for e in self.ws.entries(sort=False):
                if e.value == value and e.ref() != f"{b}.{r}.{a}":
                    print("duplicate value not allowed")
                    return
        self._snapshot()
        self.ws.set_value(b, r, a, value)
        print(f"set {b}.{r}.{a}")

    def _cmd_del(self, args: List[str]) -> None:
        if not args:
            print("Usage: :del <ref>")
            return
        b, r, a = parse_ref(args[0], self.config, self.ws.current_bank_id)
        self._snapshot()
        print("deleted" if self.ws.delete_value(b, r, a) else "not found")

    def _cmd_resolve(self, raw: str, args: List[str]) -> None:
        if not args:
            print("Usage: :resolve <ref-or-text>")
            return
        text = raw.split(" ", 1)[1]
        resolver = TensorResolver(self.ws, self.config)
        try:
            b, r, a = parse_ref(text, self.config, self.ws.current_bank_id)
            val = self.ws.get_value(b, r, a)
            if val is not None:
                print(resolver.resolve_value(val, b, r))
                return
        except Exception:
            pass
        print(resolver.resolve_value(text, self.ws.current_bank_id, self.config.get("input", {}).get("default_register_id", "1")))

    def _cmd_search(self, query: str) -> None:
        results = search_workspace(self.ws, query)
        if not results:
            print("no matches")
            return
        for e in results[:200]:
            title = self.ws.banks[e.bank].title
            print(f"{e.ref()}\t{title}\t{e.value}")
        if len(results) > 200:
            print(f"... {len(results) - 200} more")

    def _cmd_pipeline(self, raw: str, args: List[str]) -> None:
        if not args or args[0] == "show":
            print(json.dumps(self.config.get("processing", {}).get("pipeline", []), indent=2, ensure_ascii=False))
        elif args[0] == "clear":
            self.config.setdefault("processing", {})["pipeline"] = []
            print("pipeline cleared")
        elif args[0] == "add" and len(args) >= 2:
            rest = raw.split(" ", 3)
            op = args[1]
            if len(rest) >= 4:
                extra = rest[3].strip()
                if extra.startswith("{"):
                    obj = json.loads(extra)
                    obj.setdefault("op", op)
                    item: Any = obj
                else:
                    item = op
            else:
                item = op
            self.config.setdefault("processing", {}).setdefault("pipeline", []).append(item)
            print(f"pipeline added: {item}")
        else:
            print("Usage: :pipeline show|add|clear")

    def _cmd_export(self, args: List[str]) -> None:
        if not args:
            print("Usage: :export <file> [format]")
            return
        path = args[0]
        fmt = args[1] if len(args) >= 2 else self.config.get("output", {}).get("format", "json")
        data = self.renderer.render(self._materialized(), fmt)
        Path(path).write_text(data, encoding=self.config.get("output", {}).get("encoding", "utf-8"))
        print(f"exported {path} ({fmt})")

    def _formats_out(self) -> set[str]:
        return {"json", "jsonl", "csv", "markdown", "tensor_text", "databank_text", "summary", "dot"}


# ----------------------------- Noninteractive entrypoint -----------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Configurable tensor parser/resolver/exporter. Tensor.txt is one possible input format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python tensor.py --input Tensor.txt --output tensor.json --format json
          python tensor.py --config config-id.json --input Tensor.txt --output resolved.md --format markdown --reading-mode resolve
          python tensor.py --ui
        """),
    )
    p.add_argument("--config", default=None, help="config-id.json path")
    p.add_argument("--save-default-config", metavar="PATH", help="write default config JSON and exit")
    p.add_argument("--input", action="append", default=[], help="input file; can be repeated")
    p.add_argument("--input-format", default=None, help="override config input.format_id")
    p.add_argument("--merge-mode", choices=["replace", "merge"], default=None, help="input merge mode")
    p.add_argument("--output", default=None, help="output file; omit to print to stdout")
    p.add_argument("--format", default=None, help="output format: json,jsonl,csv,markdown,tensor_text,databank_text,summary,dot")
    p.add_argument("--reading-mode", choices=["raw", "resolve"], default=None, help="raw or resolve")
    p.add_argument("--pipeline", action="append", default=[], help="append pipeline op name or JSON object")
    p.add_argument("--ui", action="store_true", help="start interactive CLI/UI")
    p.add_argument("--run", action="append", default=[], help="run one CLI command before optional UI; can be repeated")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.save_default_config:
        save_config(DEFAULT_CONFIG, args.save_default_config)
        print(f"saved default config: {args.save_default_config}")
        return 0

    config = load_config(args.config)
    if args.merge_mode:
        config.setdefault("input", {})["merge_mode"] = args.merge_mode
    if args.format:
        config.setdefault("output", {})["format"] = args.format
    if args.reading_mode:
        config.setdefault("references", {})["reading_mode"] = args.reading_mode
    for item in args.pipeline:
        parsed = parse_json_value(item)
        config.setdefault("processing", {}).setdefault("pipeline", []).append(parsed)

    parser = TensorParser(config)
    ws = Workspace()
    for path in args.input:
        incoming = parser.parse_file(path, args.input_format)
        merge_workspace(ws, incoming, config.get("input", {}).get("merge_mode", "replace"))
    ws.dirty = False

    cli = TensorCLI(config, ws)
    for command in args.run:
        if not command.startswith(":"):
            command = ":" + command
        cli.execute(command)

    if args.ui or (not args.input and not args.output and not args.run):
        cli.run()
        return 0

    if args.input or args.output:
        renderer = TensorRenderer(config)
        materialized = cli._materialized()
        data = renderer.render(materialized, args.format or config.get("output", {}).get("format", "json"))
        if args.output:
            Path(args.output).write_text(data, encoding=config.get("output", {}).get("encoding", "utf-8"))
        else:
            print(data, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
