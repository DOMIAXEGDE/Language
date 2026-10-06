#!/usr/bin/env python3
"""
mathematics_research_whiteboard_v8.py

A standalone multi-page A4 mathematics whiteboard.

Core contract
-------------
Every visible object placed on a page is represented as a JSON-persistent,
Python-programmable widget. Canvas items are only runtime renderings of those
widget records. Pages, widgets, plugin definitions, and sessions persist to
*.json files.

Version 8 adds the configurable png_image widget. Use Widget > Add PNG Image
to embed a PNG in the session, or set properties.path to link a PNG (relative
paths resolve beside the saved session, or against the working directory for
an unsaved session). Embedded data_base64 takes precedence over path; clear it
to use a linked file. Configure fit (contain/cover/stretch), anchor, padding,
background, border_color and border_width in Properties JSON. PNG rendering
requires Pillow (python -m pip install Pillow); PDF export also needs ReportLab.

Security note
-------------
This program executes Python code stored inside widgets and loaded plugin files.
Use it only with trusted session files and trusted plugin directories.
"""

from __future__ import annotations

import base64
import copy
import datetime as _dt
import hashlib
import importlib.util
import inspect
import io
import json
import math
import os
import random
import re
import string
import sys
import traceback
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except Exception as exc:  # pragma: no cover
    raise SystemExit("Tkinter is required to run mathematics_research_whiteboard_v8.py") from exc


APP_NAME = "Mathematics Whiteboard"
SCHEMA = "mathematics.whiteboard.session.v1"
SESSION_SCHEMA_VERSION = 1
PLUGIN_API_VERSION = "1.0.0"
PAGE_GENERATOR_API_VERSION = "1.0.0"
PROPERTY_SCHEMA_VERSION = 1
RECORD_SCHEMA_VERSION = 1
PAGE_DPI = 96
MM_PER_INCH = 25.4
A4_WIDTH_MM = 210
A4_HEIGHT_MM = 297
A4_WIDTH_PX = int(round(A4_WIDTH_MM / MM_PER_INCH * PAGE_DPI))
A4_HEIGHT_PX = int(round(A4_HEIGHT_MM / MM_PER_INCH * PAGE_DPI))
PAGE_PAD = 44
HANDLE_SIZE = 6
A4_PDF_WIDTH_PT = A4_WIDTH_MM / MM_PER_INCH * 72
A4_PDF_HEIGHT_PT = A4_HEIGHT_MM / MM_PER_INCH * 72
PDF_POINT_PER_PIXEL = 72 / PAGE_DPI

DEFAULT_EXPORT_SETTINGS = {
    "pdf": {
        "title": "",
        "author": "",
        "page_range": "all",
        "include_grid": True,
        "include_page_titles": False,
        "include_widget_bounds": False,
        "include_metadata": True,
        "exclude_hidden_widgets": True,
        "one_file_per_page": False,
        "native_vector_first": True,
        "image_fallback": False,
        "warning_log": True,
    }
}

WIDGET_HOOKS = ("draw", "action", "on_create", "on_resize", "validate", "migrate")
WIDGET_PROGRAM_CACHE: Dict[Tuple[str, str], Any] = {}

RUNTIME_API_METHOD_DOCS = {
    "describe": "describe(name=None) -> str. Return generated reference text for the drawing/runtime API or one named method.",
    "get_property": "get_property(name, default=None) -> Any. Read a JSON-persistent widget property without changing the widget.",
    "set_property": "set_property(name, value) -> None. Write a JSON-persistent widget property and validate it against the template schema when one exists.",
    "draw_image": "draw_image(x, y, path='', width=None, height=None, fit='contain', anchor='center', data_base64='', tags='image') -> int. Draw a PNG in a widget-local box, preserving alpha. Embedded base64 takes precedence; relative paths resolve beside the session (working directory before saving). fit is contain, cover or stretch; anchor chooses alignment/crop focus. Requires Pillow; supported on canvas and PDF.",
    "draw_text": "draw_text(x, y, text, font_size=16, fill='#111111', anchor='nw', font_family='Segoe UI', bold=False, italic=False, width=None, tags='text') -> int. Draw text at widget-local pixel coordinates; width wraps text when supported.",
    "draw_line": "draw_line(x1, y1, x2, y2, fill='#111111', width=2, arrow='none', smooth=False, tags='line') -> int. Draw a widget-local line; arrow may be none, first, last, or both.",
    "draw_polyline": "draw_polyline(points, fill='#111111', width=2, smooth=False, tags='polyline') -> Optional[int]. Draw connected widget-local points.",
    "draw_rectangle": "draw_rectangle(x1, y1, x2, y2, outline='#111111', fill='', width=2, tags='rectangle') -> int. Draw a rectangle in widget-local pixel coordinates.",
    "draw_oval": "draw_oval(x1, y1, x2, y2, outline='#111111', fill='', width=2, tags='oval') -> int. Draw an oval inside a widget-local bounding box.",
    "draw_polygon": "draw_polygon(points, outline='#111111', fill='', width=2, tags='polygon') -> Optional[int]. Draw a closed polygon from widget-local points.",
    "draw_grid": "draw_grid(step=20, fill='#eeeeee') -> None. Draw a rectangular grid covering the current widget bounds.",
    "draw_axes": "draw_axes(xmin, xmax, ymin, ymax, fill='#777777', width=1) -> None. Draw x/y axes for the mathematical range mapped into the widget bounds.",
    "plot_function": "plot_function(expression, xmin, xmax, ymin, ymax, samples=200, fill='#111111', width=2) -> None. Plot y=f(x) using math-safe evaluation and widget-local coordinates.",
    "plot_parametric": "plot_parametric(x_expression, y_expression, tmin, tmax, xmin, xmax, ymin, ymax, samples=240, fill='#111111', width=2) -> None. Plot a 2D parametric curve.",
    "plot_points": "plot_points(points, xmin, xmax, ymin, ymax, radius=3, outline='#111111', fill='#111111') -> None. Plot data points into the mathematical range.",
    "draw_vector": "draw_vector(x1, y1, x2, y2, fill='#111111', width=2, label='') -> int. Draw an arrowed vector with an optional label.",
    "widget_bounds": "widget_bounds() -> tuple[int, int, int, int]. Return x, y, width, and height from the widget record.",
    "create_page": "create_page(title='New page') -> dict. Create a page; during PDF export this mutating call is ignored.",
    "read_page": "read_page(page_id=None) -> Optional[dict]. Return a deep copy of a page record.",
    "update_page": "update_page(page_id, updates) -> bool. Update page fields except page_id and widgets; during PDF export this is ignored.",
    "delete_page": "delete_page(page_id) -> bool. Delete a page when the session has another page remaining; during PDF export this is ignored.",
    "list_pages": "list_pages() -> list[dict]. Return deep copies of all page records.",
    "create_widget": "create_widget(kind, x=80, y=80, page_id=None, overrides=None) -> dict. Create a widget from a registered template; during PDF export this is ignored.",
    "read_widget": "read_widget(widget_id) -> Optional[dict]. Return a deep copy of one widget record.",
    "update_widget": "update_widget(widget_id, updates) -> bool. Update a widget through schema validation and lifecycle hooks; during PDF export this is ignored.",
    "delete_widget": "delete_widget(widget_id) -> bool. Delete one widget; during PDF export this is ignored.",
    "list_widgets": "list_widgets(page_id=None) -> list[dict]. Return deep copies of widgets on a page ordered by z.",
    "list_templates": "list_templates() -> dict. Return JSON-persistent widget-template records keyed by kind.",
    "read_template": "read_template(kind) -> Optional[dict]. Return one widget-template record.",
    "create_template": "create_template(kind, name, width=300, height=180, properties=None, program='', description='', properties_schema=None) -> dict. Create or replace a session template; ignored during PDF export.",
    "update_template": "update_template(kind, updates) -> Optional[dict]. Update a template record; ignored during PDF export.",
    "delete_template": "delete_template(kind) -> bool. Delete a template record; ignored during PDF export.",
    "duplicate_template": "duplicate_template(kind, new_kind=None) -> dict. Copy a template under a new kind; ignored during PDF export.",
    "save_session": "save_session(path=None) -> str. Save the JSON session; ignored during PDF export.",
    "log": "log(message) -> None. Send a message to the runtime log or PDF warning log.",
}
RUNTIME_API_PROTOCOL_METHODS = tuple(RUNTIME_API_METHOD_DOCS)

REGISTRATION_API_METHOD_DOCS = {
    "describe": "describe(name=None) -> str. Return generated reference text for plugin authors or one named registration method.",
    "register_widget": "register_widget(kind, name, width=300, height=180, properties=None, program='', description='', properties_schema=None) -> None. Register a widget template. Plugin kinds without ':' are automatically namespaced with the plugin manifest id.",
}
REGISTRATION_API_PROTOCOL_METHODS = tuple(REGISTRATION_API_METHOD_DOCS)

PAGE_GENERATOR_API_METHOD_DOCS = {
    "describe": "describe(name=None) -> str. Return generated reference text for book/page generator authors or one named generator method.",
    "log": "log(message) -> None. Append a generator status message to the run summary and app log.",
    "reset_book": "reset_book(title='Generated mathematics book') -> dict. Replace the current session with a fresh book and return the first page.",
    "set_title": "set_title(title) -> None. Set the JSON session title.",
    "new_page": "new_page(title=None, background=None, grid=None) -> dict. Append an A4 page and make it current.",
    "current_page": "current_page() -> dict. Return the current mutable page record.",
    "configure_page": "configure_page(page=None, **updates) -> dict. Update page configuration fields such as title, background, or grid.",
    "add_widget": "add_widget(kind, x=80, y=80, page=None, width=None, height=None, name=None, properties=None, **updates) -> dict. Place any registered widget through kernel validation.",
    "update_widget": "update_widget(widget, **updates) -> bool. Update an existing widget by id or widget record through kernel validation.",
    "add_text": "add_text(text, x=80, y=80, page=None, width=520, height=90, **style) -> dict. Convenience wrapper for the built-in text widget.",
    "add_formula": "add_formula(formula, x=80, y=80, page=None, width=620, height=90, **style) -> dict. Convenience wrapper for the formula widget.",
    "add_png": "add_png(path, x=80, y=80, page=None, width=360, height=240, embed=True, **style) -> dict. Add a PNG image widget. Relative input paths resolve against the generator project path. Embed the image in JSON by default; embed=False stores an absolute linked path. Style controls fit, anchor, padding, background and border.",
    "add_wordsearch": "add_wordsearch(title, words, x=50, y=55, page=None, width=694, height=1010, **options) -> dict. Generate and place a word-search widget using the built-in CSS-style A4 word-search layout.",
    "add_crossword": "add_crossword(title, entries, x=55, y=70, page=None, width=690, height=870, **options) -> dict. Generate and place a crossword widget from word/clue pairs.",
    "add_multiple_choice_quiz": "add_multiple_choice_quiz(title, questions, x=55, y=70, page=None, width=690, height=870, **options) -> dict. Place a multiple-choice quiz widget.",
    "load_lines": "load_lines(path, encoding='utf-8') -> list[str]. Read non-empty lines from a file relative to the generator project path.",
    "load_sections": "load_sections(path, separator='...', encoding='utf-8') -> list[list[str]]. Read line sections split by a separator line.",
    "load_pairs": "load_pairs(path, separator=':', encoding='utf-8') -> list[tuple[str, str]]. Read word/clue or term/definition pairs.",
    "wordsearch_data": "wordsearch_data(words, size=20, seed=None) -> dict. Build grid, word bank, and solution positions without placing a widget.",
    "crossword_data": "crossword_data(entries, size=None) -> dict. Build compact grid, clue lists, and numbering without placing a widget.",
    "list_templates": "list_templates() -> dict. Return all available widget templates so generators can control existing and plugin widgets.",
    "read_template": "read_template(kind) -> Optional[dict]. Read one widget-template record.",
    "export_pdf": "export_pdf(path, page_ids=None, options=None) -> dict. Export the generated session through the existing PDF exporter.",
}
PAGE_GENERATOR_API_PROTOCOL_METHODS = tuple(PAGE_GENERATOR_API_METHOD_DOCS)


def now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def deep_copy(value: Any) -> Any:
    return copy.deepcopy(value)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def as_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def ensure_json_object(text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
        raise ValueError("JSON root must be an object")
    except Exception as exc:
        raise ValueError(f"Invalid JSON object: {exc}") from exc


def merge_dicts(base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    result = deep_copy(base)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = deep_copy(value)
    return result


def load_png_image(path: str = "", data_base64: str = "", session_path: Optional[str] = None) -> Any:
    """Decode a detached RGBA image without storing Pillow objects in session data."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("PNG images require Pillow. Install it with: python -m pip install Pillow") from exc
    if data_base64:
        try:
            data = base64.b64decode(data_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("data_base64 must contain valid base64 PNG data") from exc
    else:
        if not path:
            raise ValueError("Choose a PNG image or set properties.path")
        source = Path(path).expanduser()
        if source.suffix.lower() != ".png":
            raise ValueError("Image path must have a .png extension")
        if not source.is_absolute():
            base = Path(session_path).resolve().parent if session_path else Path.cwd()
            source = base / source
        data = source.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Image data must be a PNG image")
    try:
        with Image.open(io.BytesIO(data), formats=("PNG",)) as source_image:
            return source_image.convert("RGBA")
    except Exception as exc:
        raise ValueError(f"Cannot decode PNG image: {exc}") from exc


def png_image_layout(
    image_size: Tuple[int, int], width: float, height: float,
    fit: str = "contain", anchor: str = "center",
) -> Tuple[float, float, float, float]:
    """Return the offset and scaled size inside a box, shared by Tk and PDF."""
    alignments = {
        "nw": (0, 0), "n": (0.5, 0), "ne": (1, 0),
        "w": (0, 0.5), "center": (0.5, 0.5), "e": (1, 0.5),
        "sw": (0, 1), "s": (0.5, 1), "se": (1, 1),
    }
    if fit not in {"contain", "cover", "stretch"}:
        raise ValueError("fit must be contain, cover or stretch")
    if anchor not in alignments:
        raise ValueError("anchor must be nw, n, ne, w, center, e, sw, s or se")
    iw, ih = image_size
    if any(not math.isfinite(v) or v <= 0 for v in (iw, ih, width, height)):
        raise ValueError("Image and box dimensions must be positive finite numbers")
    if fit == "stretch":
        return 0.0, 0.0, float(width), float(height)
    scale = (min if fit == "contain" else max)(width / iw, height / ih)
    dw, dh = iw * scale, ih * scale
    ax, ay = alignments[anchor]
    return (width - dw) * ax, (height - dh) * ay, dw, dh


def parse_page_range_spec(spec: str, page_count: int) -> List[int]:
    text = str(spec or "").strip().lower()
    if not text or text == "all":
        return list(range(page_count))
    result: List[int] = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
            start = int(left.strip())
            end = int(right.strip())
            if start > end:
                start, end = end, start
            for number in range(start, end + 1):
                if 1 <= number <= page_count and number - 1 not in result:
                    result.append(number - 1)
        else:
            number = int(part)
            if 1 <= number <= page_count and number - 1 not in result:
                result.append(number - 1)
    if not result:
        raise ValueError("The page range did not match any pages.")
    return result


def safe_file_stem(text: str, fallback: str = "mathematics_export") -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(text).strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or fallback


def default_page_model() -> Dict[str, Any]:
    return {
        "paper": "A4",
        "width_mm": A4_WIDTH_MM,
        "height_mm": A4_HEIGHT_MM,
        "dpi": PAGE_DPI,
        "width_px": A4_WIDTH_PX,
        "height_px": A4_HEIGHT_PX,
    }


def default_grid() -> Dict[str, Any]:
    return {"enabled": False, "spacing": 24, "fill": "#eeeeee"}


def default_source_record(kind: str = "session") -> Dict[str, Any]:
    return {"kind": kind, "label": kind}


def normalize_source_record(source: Any, default_kind: str = "session") -> Dict[str, Any]:
    if isinstance(source, dict):
        record = deep_copy(source)
    elif source in (None, ""):
        record = default_source_record(default_kind)
    else:
        text = str(source)
        if text == "builtin":
            record = {"kind": "builtin", "label": "builtin"}
        elif text == "session":
            record = {"kind": "session", "label": "session"}
        elif text == "plugin":
            record = {"kind": "session", "label": "legacy plugin"}
        else:
            record = {"kind": "plugin", "path": text, "label": Path(text).name or text}
    record.setdefault("kind", default_kind)
    if "label" not in record:
        manifest = record.get("manifest", {}) if isinstance(record.get("manifest"), dict) else {}
        record["label"] = str(manifest.get("id") or record.get("path") or record.get("kind"))
        if record.get("path"):
            record["label"] = Path(str(record["path"])).name
    return record


def source_label(source: Any) -> str:
    record = normalize_source_record(source)
    manifest = record.get("manifest", {}) if isinstance(record.get("manifest"), dict) else {}
    if manifest.get("id") and record.get("kind") == "plugin":
        return f"{manifest.get('id')} ({Path(str(record.get('path', 'plugin'))).name})"
    return str(record.get("label") or record.get("kind") or "session")


def source_identity(source: Any) -> str:
    record = normalize_source_record(source)
    manifest = record.get("manifest", {}) if isinstance(record.get("manifest"), dict) else {}
    return "|".join(
        str(part)
        for part in (
            record.get("kind", ""),
            manifest.get("id", ""),
            record.get("path", ""),
            record.get("label", ""),
        )
    )


def sanitize_plugin_id(value: Any, fallback: str = "plugin") -> str:
    text = str(value or "").strip().replace(" ", "_")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
    cleaned = "".join(ch for ch in text if ch in allowed).strip("._-")
    return cleaned or fallback


def semver_tuple(value: Any) -> Tuple[int, int, int]:
    parts = str(value or "0").strip().lstrip("v").split(".")
    numbers: List[int] = []
    for part in parts[:3]:
        digits = ""
        for char in part:
            if char.isdigit():
                digits += char
            else:
                break
        numbers.append(int(digits or 0))
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers[:3])  # type: ignore[return-value]


def api_requirement_satisfied(requirement: Any, current: str = PLUGIN_API_VERSION) -> bool:
    text = str(requirement or "").strip()
    if not text or text in {"*", "any"}:
        return True
    current_version = semver_tuple(current)
    for raw_part in text.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if part.endswith(".x"):
            prefix_parts = [item for item in part[:-2].split(".") if item]
            wanted = semver_tuple(part[:-2])
            width = max(1, min(3, len(prefix_parts)))
            if current_version[:width] != wanted[:width]:
                return False
            continue
        if part.endswith(".*"):
            wanted = semver_tuple(part[:-2])
            if current_version[0] != wanted[0]:
                return False
            continue
        op = "=="
        number = part
        for candidate in (">=", "<=", ">", "<", "==", "="):
            if part.startswith(candidate):
                op = "==" if candidate == "=" else candidate
                number = part[len(candidate):].strip()
                break
        if part.startswith("^"):
            base = semver_tuple(part[1:])
            if current_version[0] != base[0] or current_version < base:
                return False
            continue
        wanted = semver_tuple(number)
        if op == "==" and current_version != wanted:
            return False
        if op == ">=" and current_version < wanted:
            return False
        if op == "<=" and current_version > wanted:
            return False
        if op == ">" and current_version <= wanted:
            return False
        if op == "<" and current_version >= wanted:
            return False
    return True


def normalize_plugin_manifest(module: Any, path: Path) -> Dict[str, Any]:
    manifest: Dict[str, Any] = {}
    raw_manifest = getattr(module, "MANIFEST", None)
    if isinstance(raw_manifest, dict):
        manifest.update(deep_copy(raw_manifest))
    manifest_func = getattr(module, "manifest", None)
    if callable(manifest_func):
        value = manifest_func()
        if not isinstance(value, dict):
            raise ValueError("manifest() must return a dictionary")
        manifest.update(deep_copy(value))
    manifest.setdefault("id", getattr(module, "PLUGIN_ID", safe_file_stem(path.stem, "plugin")))
    manifest.setdefault("version", getattr(module, "VERSION", "0.0.0"))
    manifest.setdefault("author", getattr(module, "AUTHOR", ""))
    manifest.setdefault("requires_api", getattr(module, "REQUIRES_API", f">={PLUGIN_API_VERSION},<2.0.0"))
    manifest["id"] = sanitize_plugin_id(manifest.get("id"), fallback=safe_file_stem(path.stem, "plugin"))
    manifest["version"] = str(manifest.get("version", "0.0.0"))
    manifest["author"] = str(manifest.get("author", ""))
    manifest["requires_api"] = str(manifest.get("requires_api", ""))
    return manifest


def field_spec(type_name: str, default: Any = None, validator: Optional[Callable[[Any], Any]] = None) -> Dict[str, Any]:
    return {"type": type_name, "default": default, "validator": validator}


def record_default(value: Any) -> Any:
    return value() if callable(value) else deep_copy(value)


def coerce_value(value: Any, type_name: str, default: Any = None) -> Any:
    normalized = str(type_name or "any").lower()
    if normalized in {"any", "object"}:
        return value
    if normalized in {"str", "string"}:
        return "" if value is None else str(value)
    if normalized in {"int", "integer"}:
        return int(as_float(value, as_float(default, 0)))
    if normalized in {"float", "number"}:
        return float(as_float(value, as_float(default, 0.0)))
    if normalized in {"bool", "boolean"}:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if normalized in {"dict", "mapping"}:
        return deep_copy(value) if isinstance(value, dict) else record_default(default if default is not None else {})
    if normalized in {"list", "array"}:
        return deep_copy(value) if isinstance(value, list) else record_default(default if default is not None else [])
    return value


RECORD_SCHEMAS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "session": {
        "schema_version": field_spec("int", SESSION_SCHEMA_VERSION),
        "schema": field_spec("str", SCHEMA),
        "app": field_spec("str", APP_NAME),
        "session_id": field_spec("str", lambda: new_id("s")),
        "title": field_spec("str", "Untitled mathematics session"),
        "created_at": field_spec("str", now_iso),
        "modified_at": field_spec("str", now_iso),
        "page_model": field_spec("dict", default_page_model),
        "plugins": field_spec("dict", dict),
        "export_settings": field_spec("dict", lambda: deep_copy(DEFAULT_EXPORT_SETTINGS)),
        "widget_templates": field_spec("dict", dict),
        "pages": field_spec("list", list),
    },
    "page": {
        "schema_version": field_spec("int", RECORD_SCHEMA_VERSION),
        "page_id": field_spec("str", lambda: new_id("p")),
        "title": field_spec("str", "Page"),
        "width_mm": field_spec("float", A4_WIDTH_MM),
        "height_mm": field_spec("float", A4_HEIGHT_MM),
        "dpi": field_spec("int", PAGE_DPI),
        "width_px": field_spec("int", A4_WIDTH_PX, lambda v: max(16, int(v))),
        "height_px": field_spec("int", A4_HEIGHT_PX, lambda v: max(16, int(v))),
        "background": field_spec("str", "#ffffff"),
        "grid": field_spec("dict", default_grid),
        "widgets": field_spec("list", list),
        "created_at": field_spec("str", now_iso),
        "modified_at": field_spec("str", now_iso),
    },
    "widget": {
        "schema_version": field_spec("int", RECORD_SCHEMA_VERSION),
        "widget_id": field_spec("str", lambda: new_id("w")),
        "kind": field_spec("str", "free_program"),
        "name": field_spec("str", "Widget"),
        "x": field_spec("int", 80),
        "y": field_spec("int", 80),
        "width": field_spec("int", 240, lambda v: max(16, int(v))),
        "height": field_spec("int", 160, lambda v: max(16, int(v))),
        "z": field_spec("int", 0),
        "locked": field_spec("bool", False),
        "visible": field_spec("bool", True),
        "properties": field_spec("dict", dict),
        "program": field_spec("str", lambda: FREE_PROGRAM_WIDGET_PROGRAM),
        "template_source": field_spec("dict", lambda: default_source_record("session")),
        "template_version": field_spec("int", 1),
        "created_at": field_spec("str", now_iso),
        "modified_at": field_spec("str", now_iso),
    },
    "template": {
        "schema_version": field_spec("int", RECORD_SCHEMA_VERSION),
        "kind": field_spec("str", "free_program"),
        "name": field_spec("str", "Widget"),
        "width": field_spec("int", 300, lambda v: max(16, int(v))),
        "height": field_spec("int", 180, lambda v: max(16, int(v))),
        "properties": field_spec("dict", dict),
        "properties_schema": field_spec("dict", dict),
        "program": field_spec("str", lambda: FREE_PROGRAM_WIDGET_PROGRAM),
        "description": field_spec("str", ""),
        "source": field_spec("dict", lambda: default_source_record("session")),
        "template_version": field_spec("int", 1),
        "modified_at": field_spec("str", now_iso),
    },
    "export_settings": {
        "schema_version": field_spec("int", RECORD_SCHEMA_VERSION),
        "pdf": field_spec("dict", lambda: deep_copy(DEFAULT_EXPORT_SETTINGS["pdf"])),
    },
}
RECORD_MIGRATIONS: Dict[str, Dict[int, Callable[[Dict[str, Any]], Dict[str, Any]]]] = {
    "session": {},
    "page": {},
    "widget": {},
    "template": {},
    "export_settings": {},
}


def migrate_record(record: Dict[str, Any], schema_name: str) -> Dict[str, Any]:
    current = int(as_float(record.get("schema_version", 1), 1))
    migrations = RECORD_MIGRATIONS.get(schema_name, {})
    while current in migrations:
        record = migrations[current](record)
        current = int(as_float(record.get("schema_version", current + 1), current + 1))
    return record


def conform_record(record: Any, schema_name: str) -> Dict[str, Any]:
    schema = RECORD_SCHEMAS[schema_name]
    data = migrate_record(deep_copy(record) if isinstance(record, dict) else {}, schema_name)
    result = deep_copy(data)
    for name, spec in schema.items():
        default = record_default(spec.get("default"))
        if name in data:
            value = coerce_value(data[name], str(spec.get("type", "any")), default)
        else:
            value = default
        validator = spec.get("validator")
        if callable(validator):
            value = validator(value)
        result[name] = value
    result["schema_version"] = int(result.get("schema_version", RECORD_SCHEMA_VERSION))
    return result


def infer_property_descriptor(value: Any) -> Dict[str, Any]:
    if isinstance(value, bool):
        type_name = "boolean"
    elif isinstance(value, int) and not isinstance(value, bool):
        type_name = "integer"
    elif isinstance(value, float):
        type_name = "number"
    elif isinstance(value, dict):
        type_name = "object"
    elif isinstance(value, list):
        type_name = "array"
    elif value is None:
        type_name = "any"
    else:
        type_name = "string"
    return {
        "type": type_name,
        "default": deep_copy(value),
        "description": "",
        "schema_version": PROPERTY_SCHEMA_VERSION,
    }


def normalize_property_schema(properties_schema: Any, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    defaults = defaults if isinstance(defaults, dict) else {}
    normalized: Dict[str, Dict[str, Any]] = {}
    if isinstance(properties_schema, dict):
        for name, descriptor in properties_schema.items():
            if isinstance(descriptor, dict):
                item = deep_copy(descriptor)
            else:
                item = {"type": str(descriptor)}
            if "default" not in item and name in defaults:
                item["default"] = deep_copy(defaults[name])
            item.setdefault("type", infer_property_descriptor(item.get("default")).get("type", "any"))
            item.setdefault("description", "")
            item.setdefault("schema_version", PROPERTY_SCHEMA_VERSION)
            normalized[str(name)] = item
    for name, value in defaults.items():
        normalized.setdefault(str(name), infer_property_descriptor(value))
    return normalized


def coerce_property_value(name: str, value: Any, descriptor: Dict[str, Any]) -> Any:
    type_name = str(descriptor.get("type", "any"))
    default = descriptor.get("default")
    coerced = coerce_value(value, type_name, default)
    choices = descriptor.get("choices", descriptor.get("enum"))
    if isinstance(choices, list) and choices and coerced not in choices:
        raise ValueError(f"{name} must be one of {choices}")
    if str(type_name).lower() in {"int", "integer", "float", "number"}:
        if "min" in descriptor and coerced < descriptor["min"]:
            raise ValueError(f"{name} must be >= {descriptor['min']}")
        if "max" in descriptor and coerced > descriptor["max"]:
            raise ValueError(f"{name} must be <= {descriptor['max']}")
    return coerced


def conform_properties(
    properties: Any,
    properties_schema: Any,
    defaults: Optional[Dict[str, Any]] = None,
    keep_extra: bool = True,
) -> Dict[str, Any]:
    source = deep_copy(properties) if isinstance(properties, dict) else {}
    schema = normalize_property_schema(properties_schema, defaults)
    result: Dict[str, Any] = {}
    for name, descriptor in schema.items():
        if name in source:
            raw_value = source[name]
        elif "default" in descriptor:
            raw_value = deep_copy(descriptor["default"])
        else:
            continue
        result[name] = coerce_property_value(name, raw_value, descriptor)
    if keep_extra:
        for name, value in source.items():
            result.setdefault(name, deep_copy(value))
    return result


def get_compiled_widget_program(program: str, widget_id: str) -> Any:
    digest = hashlib.sha256(program.encode("utf-8")).hexdigest()
    key = (digest, str(widget_id))
    cached = WIDGET_PROGRAM_CACHE.get(key)
    if cached is not None:
        return cached
    filename = f"<widget {widget_id} {digest[:12]}>"
    code = compile(program, filename, "exec")
    WIDGET_PROGRAM_CACHE[key] = code
    return code


def build_widget_exec_environment(api: Any, widget: Dict[str, Any], page: Dict[str, Any], session: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "__builtins__": __builtins__,
        "api": api,
        "widget": widget,
        "page": page,
        "session": session,
        "math": math,
        "json": json,
        "uuid": uuid,
        "Path": Path,
        "datetime": _dt,
        "build_wordsearch_data": build_wordsearch_data,
        "build_crossword_data": build_crossword_data,
        "normalize_quiz_questions": normalize_quiz_questions,
    }


def execute_widget_hook(
    api: Any,
    widget: Dict[str, Any],
    page: Dict[str, Any],
    session: Dict[str, Any],
    mode: str = "draw",
) -> Tuple[bool, Any]:
    if mode not in WIDGET_HOOKS:
        raise ValueError(f"Unsupported widget hook: {mode}")
    program = str(widget.get("program", "") or "")
    env = build_widget_exec_environment(api, widget, page, session)
    exec(get_compiled_widget_program(program, str(widget.get("widget_id", "widget"))), env, env)
    target = env.get(mode)
    if callable(target):
        return True, target(api, widget, page, session)
    return False, None


def draw_missing_widget_placeholder(api: Any, widget: Dict[str, Any]) -> None:
    width = int(as_float(widget.get("width", 240), 240))
    height = int(as_float(widget.get("height", 140), 140))
    source = widget.get("template_source", {})
    api.draw_rectangle(0, 0, width, height, outline="#b00020", fill="#fff7f7", width=2)
    api.draw_text(8, 8, "Missing widget template", font_size=12, fill="#b00020", bold=True, width=max(24, width - 16))
    api.draw_text(8, 30, f"kind: {widget.get('kind', 'unknown')}", font_size=10, fill="#333333", width=max(24, width - 16))
    if source:
        api.draw_text(8, 48, f"source: {source_label(source)}", font_size=9, fill="#555555", width=max(24, width - 16))


def plugin_reference_for_method(name: str, docs: Dict[str, str], cls: Optional[type] = None) -> str:
    signature = ""
    if cls is not None and hasattr(cls, name):
        try:
            signature = str(inspect.signature(getattr(cls, name)))
        except Exception:
            signature = ""
    return f"### {name}{signature}\n\n{docs.get(name, '').strip()}\n"


def text_slug(text: Any, fallback: str = "item") -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()
    return slug or fallback


def normalize_puzzle_word(value: Any) -> str:
    replacements = {
        "π": "PI",
        "Π": "PI",
        "∞": "INFINITY",
        "∑": "SUM",
        "Σ": "SUM",
        "∫": "INTEGRAL",
        "√": "ROOT",
        "ℝ": "R",
        "ℤ": "Z",
        "ℚ": "Q",
        "ℕ": "N",
        "×": "X",
        "÷": "DIV",
    }
    text = str(value or "")
    for old, new in replacements.items():
        text = text.replace(old, new)
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    allowed = set(string.ascii_uppercase + string.digits)
    return "".join(ch for ch in normalized.upper() if ch in allowed)


def wordsearch_direction_offsets(direction: str) -> Tuple[int, int]:
    directions = {
        "H-R": (0, 1),
        "H-L": (0, -1),
        "V-D": (1, 0),
        "V-U": (-1, 0),
        "D-R": (1, 1),
        "D-L": (1, -1),
        "U-R": (-1, 1),
        "U-L": (-1, -1),
    }
    return directions.get(direction, (0, 1))


def wordsearch_can_place(grid: List[List[str]], word: str, row: int, col: int, direction: str) -> bool:
    size = len(grid)
    dr, dc = wordsearch_direction_offsets(direction)
    end_row = row + dr * (len(word) - 1)
    end_col = col + dc * (len(word) - 1)
    if not (0 <= row < size and 0 <= col < size and 0 <= end_row < size and 0 <= end_col < size):
        return False
    for index, char in enumerate(word):
        current = grid[row + dr * index][col + dc * index]
        if current not in ("", char):
            return False
    return True


def wordsearch_place(grid: List[List[str]], word: str, row: int, col: int, direction: str) -> List[List[int]]:
    dr, dc = wordsearch_direction_offsets(direction)
    positions: List[List[int]] = []
    for index, char in enumerate(word):
        r = row + dr * index
        c = col + dc * index
        grid[r][c] = char
        positions.append([r, c])
    return positions


ENGLISH_LETTER_WEIGHTS: Dict[str, float] = {
    "E": 12.7, "T": 9.1, "A": 8.2, "O": 7.5, "I": 7.0, "N": 6.7, "S": 6.3,
    "H": 6.1, "R": 6.0, "D": 4.3, "L": 4.0, "C": 2.8, "U": 2.8, "M": 2.4,
    "W": 2.4, "F": 2.2, "G": 2.0, "Y": 2.0, "P": 1.9, "B": 1.5, "V": 1.0,
    "K": 0.8, "J": 0.15, "X": 0.15, "Q": 0.1, "Z": 0.07,
}


def wordsearch_letter_counts(words: Iterable[str], alphabet: str) -> Dict[str, float]:
    counts: Dict[str, float] = {char: ENGLISH_LETTER_WEIGHTS.get(char, 1.0) for char in alphabet}
    for word in words:
        for char in str(word):
            if char in counts:
                counts[char] += 8.0
    return counts


def wordsearch_bigram_counts(words: Iterable[str]) -> Dict[str, float]:
    counts: Dict[str, float] = {}
    for word in words:
        text = str(word)
        for index in range(len(text) - 1):
            pair = text[index:index + 2]
            counts[pair] = counts.get(pair, 0.0) + 1.0
            counts[pair[::-1]] = counts.get(pair[::-1], 0.0) + 0.35
    return counts


def wordsearch_neighbor_letters(grid: List[List[str]], row: int, col: int) -> List[str]:
    size = len(grid)
    letters: List[str] = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            rr = row + dr
            cc = col + dc
            if 0 <= rr < size and 0 <= cc < size and grid[rr][cc]:
                letters.append(grid[rr][cc])
    return letters


def fill_wordsearch_grid_intelligently(
    grid: List[List[str]],
    words: Iterable[str],
    rng: random.Random,
    filler_alphabet: str = string.ascii_uppercase,
) -> None:
    alphabet = "".join(ch for ch in str(filler_alphabet or string.ascii_uppercase).upper() if ch in string.ascii_uppercase + string.digits)
    alphabet = "".join(dict.fromkeys(alphabet)) or string.ascii_uppercase
    source_words = [str(word) for word in words]
    letter_counts = wordsearch_letter_counts(source_words, alphabet)
    bigrams = wordsearch_bigram_counts(source_words)
    size = len(grid)
    empty_cells = [(row, col) for row in range(size) for col in range(size) if not grid[row][col]]
    while empty_cells:
        empty_cells.sort(key=lambda cell: (-len(wordsearch_neighbor_letters(grid, cell[0], cell[1])), cell[0] + cell[1], cell[0], cell[1]))
        row, col = empty_cells.pop(0)
        neighbors = wordsearch_neighbor_letters(grid, row, col)
        scored: List[Tuple[float, str]] = []
        for char in alphabet:
            score = letter_counts.get(char, 1.0)
            for neighbor in neighbors:
                score += bigrams.get(neighbor + char, 0.0) * 3.0
                score += bigrams.get(char + neighbor, 0.0) * 2.0
                if char == neighbor:
                    score *= 0.82
            scored.append((score + rng.random() * 0.001, char))
        scored.sort(reverse=True)
        top = scored[: max(3, min(9, len(scored)))]
        total = sum(max(score, 0.01) for score, _ in top)
        pick = rng.random() * total
        upto = 0.0
        chosen = top[0][1]
        for score, char in top:
            upto += max(score, 0.01)
            if upto >= pick:
                chosen = char
                break
        grid[row][col] = chosen


def wordsearch_candidate_fits(
    grid: List[List[str]],
    word: str,
    directions: Iterable[str],
) -> List[Tuple[int, float, int, int, str]]:
    size = len(grid)
    center = (size - 1) / 2
    candidates: List[Tuple[int, float, int, int, str]] = []
    for direction in directions:
        dr, dc = wordsearch_direction_offsets(direction)
        for row in range(size):
            for col in range(size):
                if not wordsearch_can_place(grid, word, row, col, direction):
                    continue
                overlap = 0
                for index, char in enumerate(word):
                    if grid[row + dr * index][col + dc * index] == char:
                        overlap += 1
                mid_row = row + dr * (len(word) - 1) / 2
                mid_col = col + dc * (len(word) - 1) / 2
                centrality = -((mid_row - center) ** 2 + (mid_col - center) ** 2)
                candidates.append((overlap, centrality, row, col, direction))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates


def build_wordsearch_data(
    words: Iterable[Any],
    size: int = 20,
    seed: Optional[Any] = None,
    max_size: Optional[int] = None,
    directions: Optional[Iterable[str]] = None,
    max_attempts: int = 16,
    filler_alphabet: str = string.ascii_uppercase,
) -> Dict[str, Any]:
    source_words = [str(word).strip() for word in words if str(word).strip()]
    clean_words: List[str] = []
    display_words: Dict[str, str] = {}
    for word in source_words:
        normalized = normalize_puzzle_word(word)
        if normalized and normalized not in clean_words:
            clean_words.append(normalized)
            display_words[normalized] = str(word).strip()
    allowed_directions = [direction for direction in (directions or ["H-R", "H-L", "V-D", "V-U", "D-R", "D-L", "U-R", "U-L"]) if direction in {"H-R", "H-L", "V-D", "V-U", "D-R", "D-L", "U-R", "U-L"}]
    if not allowed_directions:
        allowed_directions = ["H-R", "V-D"]
    effective_seed = seed if seed not in (None, "") else json.dumps([source_words, int(size), allowed_directions], ensure_ascii=False)
    rng = random.Random(effective_seed)
    longest = max((len(word) for word in clean_words), default=4)
    start_size = max(6, int(size), longest)
    ceiling = max(start_size, int(max_size or max(40, start_size + min(20, len(clean_words) + 8))))
    best: Optional[Dict[str, Any]] = None
    for grid_size in range(start_size, ceiling + 1):
        for attempt in range(max(1, int(max_attempts))):
            grid = [["" for _ in range(grid_size)] for _ in range(grid_size)]
            positions: Dict[str, List[List[int]]] = {}
            skipped: List[str] = []
            ordered_words = sorted(clean_words, key=lambda item: (-len(item), rng.random()))
            for word in ordered_words:
                candidates = wordsearch_candidate_fits(grid, word, allowed_directions)
                if not candidates:
                    skipped.append(word)
                    continue
                best_overlap = candidates[0][0]
                top_pool = [candidate for candidate in candidates[:24] if candidate[0] >= max(0, best_overlap - 1)]
                _, _, row, col, direction = rng.choice(top_pool or candidates[:1])
                positions[word] = wordsearch_place(grid, word, row, col, direction)
            score = (len(positions), -len(skipped), -grid_size)
            if best is None or score > best["score"]:
                best = {"score": score, "grid": grid, "grid_size": grid_size, "positions": positions, "skipped": skipped, "attempt": attempt + 1}
            if not skipped:
                break
        if best and not best["skipped"]:
            break
    if best is None:
        best = {"grid": [["" for _ in range(start_size)] for _ in range(start_size)], "grid_size": start_size, "positions": {}, "skipped": clean_words, "attempt": 0}
    grid = best["grid"]
    grid_size = best["grid_size"]
    fill_wordsearch_grid_intelligently(grid, clean_words, rng, filler_alphabet=filler_alphabet)
    return {
        "grid": ["".join(row) for row in grid],
        "grid_size": grid_size,
        "words": sorted(clean_words),
        "display_words": {word: display_words.get(word, word) for word in clean_words},
        "source_words": source_words,
        "word_positions": best["positions"],
        "skipped_words": best["skipped"],
        "generation": {
            "algorithm": "candidate-overlap-expanding-wordsearch",
            "seed": effective_seed,
            "requested_seed": seed,
            "directions": allowed_directions,
            "max_size": ceiling,
            "attempt": best.get("attempt", 0),
            "placed_count": len(best["positions"]),
            "word_count": len(clean_words),
            "filler_strategy": "intelligent-vocabulary-neighbor-weighted",
        },
    }


def normalize_crossword_direction(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"across", "horizontal", "h", "row", "rows"}:
        return "across"
    if text in {"down", "vertical", "v", "column", "columns", "col", "cols"}:
        return "down"
    return None


def normalize_crossword_entries(entries: Iterable[Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in entries:
        direction: Optional[str] = None
        if isinstance(item, dict):
            word = item.get("word", item.get("answer", item.get("term", "")))
            clue = item.get("clue", item.get("definition", item.get("question", "")))
            direction = normalize_crossword_direction(
                item.get("direction", item.get("orientation", item.get("preferred_direction", item.get("placement", ""))))
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            word, clue = item[0], item[1]
            direction = normalize_crossword_direction(item[2])
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            word, clue = item[0], item[1]
        elif isinstance(item, str) and ":" in item:
            parts = item.split(":", 2)
            first_direction = normalize_crossword_direction(parts[0])
            if len(parts) == 3 and first_direction:
                direction = first_direction
                word, clue = parts[1], parts[2]
            else:
                word, clue = item.split(":", 1)
        else:
            continue
        normalized = normalize_puzzle_word(word)
        if normalized:
            result.append({"word": normalized, "clue": str(clue).strip() or normalized.title(), "direction": direction})
    seen: Dict[str, Dict[str, Any]] = {}
    for entry in result:
        word = str(entry["word"])
        if word not in seen:
            seen[word] = entry
        elif not seen[word].get("direction") and entry.get("direction"):
            seen[word]["direction"] = entry.get("direction")
    return list(seen.values())


def crossword_offsets(direction: str) -> Tuple[int, int]:
    return (0, 1) if direction == "across" else (1, 0)


def crossword_can_place(grid: List[List[Optional[str]]], word: str, row: int, col: int, direction: str) -> bool:
    size = len(grid)
    dr, dc = crossword_offsets(direction)
    end_row = row + dr * (len(word) - 1)
    end_col = col + dc * (len(word) - 1)
    if not (0 <= row < size and 0 <= col < size and 0 <= end_row < size and 0 <= end_col < size):
        return False
    before_row, before_col = row - dr, col - dc
    after_row, after_col = end_row + dr, end_col + dc
    if 0 <= before_row < size and 0 <= before_col < size and grid[before_row][before_col] is not None:
        return False
    if 0 <= after_row < size and 0 <= after_col < size and grid[after_row][after_col] is not None:
        return False
    for index, char in enumerate(word):
        r = row + dr * index
        c = col + dc * index
        cell = grid[r][c]
        if cell is not None and cell != char:
            return False
        if cell is None:
            if direction == "across":
                if r > 0 and grid[r - 1][c] is not None:
                    return False
                if r < size - 1 and grid[r + 1][c] is not None:
                    return False
            else:
                if c > 0 and grid[r][c - 1] is not None:
                    return False
                if c < size - 1 and grid[r][c + 1] is not None:
                    return False
    return True


def crossword_place(grid: List[List[Optional[str]]], word: str, row: int, col: int, direction: str) -> None:
    dr, dc = crossword_offsets(direction)
    for index, char in enumerate(word):
        grid[row + dr * index][col + dc * index] = char


def crossword_intersections(grid: List[List[Optional[str]]], word: str, row: int, col: int, direction: str) -> int:
    dr, dc = crossword_offsets(direction)
    return sum(1 for index, char in enumerate(word) if grid[row + dr * index][col + dc * index] == char)


def crossword_find_best_fit(
    grid: List[List[Optional[str]]],
    word: str,
    directions: Optional[Iterable[Any]] = None,
) -> Optional[Tuple[int, int, str]]:
    fits = crossword_candidate_fits(grid, word, require_intersection=False, directions=directions)
    if not fits:
        return None
    return fits[0][2], fits[0][3], fits[0][4]


def crossword_candidate_fits(
    grid: List[List[Optional[str]]],
    word: str,
    require_intersection: bool = True,
    directions: Optional[Iterable[Any]] = None,
) -> List[Tuple[int, int, int, int, str]]:
    size = len(grid)
    center = (size - 1) / 2
    candidates: List[Tuple[int, int, int, int, str]] = []
    allowed_directions: List[str] = []
    for direction in directions or ("across", "down"):
        normalized = normalize_crossword_direction(direction)
        if normalized and normalized not in allowed_directions:
            allowed_directions.append(normalized)
    if not allowed_directions:
        allowed_directions = ["across", "down"]
    for row in range(size):
        for col in range(size):
            for direction in allowed_directions:
                if not crossword_can_place(grid, word, row, col, direction):
                    continue
                intersections = crossword_intersections(grid, word, row, col, direction)
                if require_intersection and intersections <= 0:
                    continue
                dr, dc = crossword_offsets(direction)
                end_row = row + dr * (len(word) - 1)
                end_col = col + dc * (len(word) - 1)
                mid_row = (row + end_row) / 2
                mid_col = (col + end_col) / 2
                centrality = -int(abs(mid_row - center) + abs(mid_col - center))
                score = intersections * 1000 + len(word) * 10 + centrality
                candidates.append((score, intersections, row, col, direction))
    candidates.sort(reverse=True)
    return candidates


def compact_crossword_grid(
    grid: List[List[Optional[str]]],
    positions: Dict[str, Dict[str, Any]],
) -> Tuple[List[List[str]], Dict[str, Dict[str, Any]]]:
    size = len(grid)
    used_rows = {row for row in range(size) if any(grid[row][col] is not None for col in range(size))}
    used_cols = {col for col in range(size) if any(grid[row][col] is not None for row in range(size))}
    if not used_rows or not used_cols:
        return [[]], {}
    min_row, max_row = min(used_rows), max(used_rows)
    min_col, max_col = min(used_cols), max(used_cols)
    compacted = [
        [grid[row][col] or "" for col in range(min_col, max_col + 1)]
        for row in range(min_row, max_row + 1)
    ]
    compacted_positions: Dict[str, Dict[str, Any]] = {}
    for word, data in positions.items():
        start = data.get("start", [0, 0])
        compacted_positions[word] = {
            **data,
            "start": [int(start[0]) - min_row, int(start[1]) - min_col],
        }
    return compacted, compacted_positions


def assign_crossword_numbers(positions: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, int], List[str], List[str]]:
    starts: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for word, data in positions.items():
        start = tuple(data.get("start", [0, 0]))  # type: ignore[arg-type]
        starts.setdefault((int(start[0]), int(start[1])), []).append({"word": word, **data})
    number_map: Dict[str, int] = {}
    across: List[str] = []
    down: List[str] = []
    for number, start in enumerate(sorted(starts), start=1):
        number_map[f"{start[0]},{start[1]}"] = number
        for item in sorted(starts[start], key=lambda data: str(data.get("direction"))):
            clue_text = f"{number}. {item.get('clue', item.get('word'))}"
            if item.get("direction") == "across":
                across.append(clue_text)
            else:
                down.append(clue_text)
    return number_map, across, down


def crossword_layout_attempt(
    entries: List[Dict[str, Any]],
    grid_size: int,
    rng: random.Random,
    allow_disconnected: bool = False,
) -> Dict[str, Any]:
    grid: List[List[Optional[str]]] = [[None for _ in range(grid_size)] for _ in range(grid_size)]
    positions: Dict[str, Dict[str, Any]] = {}
    ordered = sorted(entries, key=lambda item: (-len(str(item.get("word", ""))), rng.random()))
    first_entry = ordered[0]
    first = str(first_entry.get("word", ""))
    first_direction = normalize_crossword_direction(first_entry.get("direction")) or rng.choice(["across", "down"])
    if first_direction == "across":
        start_row = grid_size // 2
        start_col = max(0, (grid_size - len(first)) // 2)
    else:
        start_row = max(0, (grid_size - len(first)) // 2)
        start_col = grid_size // 2
    crossword_place(grid, first, start_row, start_col, first_direction)
    positions[first] = {"start": [start_row, start_col], "direction": first_direction, "clue": first_entry.get("clue", first.title())}
    remaining = ordered[1:]
    unplaced: List[str] = []
    total_intersections = 0
    while remaining:
        word_options: List[Tuple[int, int, Dict[str, Any], List[Tuple[int, int, int, int, str]]]] = []
        for entry in remaining:
            word = str(entry.get("word", ""))
            direction = normalize_crossword_direction(entry.get("direction"))
            direction_filter = [direction] if direction else None
            candidates = crossword_candidate_fits(grid, word, require_intersection=True, directions=direction_filter)
            if not candidates and allow_disconnected:
                candidates = crossword_candidate_fits(grid, word, require_intersection=False, directions=direction_filter)
            if candidates:
                word_options.append((candidates[0][0], len(candidates), entry, candidates[:16]))
        if not word_options:
            unplaced.extend(str(entry.get("word", "")) for entry in remaining)
            break
        word_options.sort(key=lambda item: (item[0], -item[1], len(str(item[2].get("word", "")))), reverse=True)
        top_word_options = word_options[: min(4, len(word_options))]
        _, _, entry, candidates = rng.choice(top_word_options)
        word = str(entry.get("word", ""))
        score, intersections, row, col, direction = rng.choice(candidates[: min(6, len(candidates))])
        del score
        crossword_place(grid, word, row, col, direction)
        positions[word] = {"start": [row, col], "direction": direction, "clue": entry.get("clue", word.title())}
        total_intersections += intersections
        remaining = [item for item in remaining if str(item.get("word", "")) != word]
    compacted, compacted_positions = compact_crossword_grid(grid, positions)
    area = len(compacted) * max((len(row) for row in compacted), default=0)
    return {
        "grid": compacted,
        "positions": compacted_positions,
        "unplaced": unplaced,
        "intersections": total_intersections,
        "area": area,
    }


def build_crossword_data(
    entries: Iterable[Any],
    size: Optional[int] = None,
    seed: Optional[Any] = None,
    max_size: Optional[int] = None,
    attempts: int = 120,
    allow_disconnected: bool = False,
) -> Dict[str, Any]:
    records = normalize_crossword_entries(entries)
    if not records:
        return {"grid": [[]], "number_map": {}, "across_clues": [], "down_clues": [], "entries": [], "unplaced": [], "source_entries": [], "generation": {"placed_count": 0, "entry_count": 0}}
    effective_seed = seed if seed not in (None, "") else json.dumps(records, ensure_ascii=False)
    rng = random.Random(effective_seed)
    records = sorted(records, key=lambda item: len(str(item.get("word", ""))), reverse=True)
    clues = {str(entry["word"]): str(entry.get("clue", str(entry["word"]).title())) for entry in records}
    preferred_directions = {str(entry["word"]): normalize_crossword_direction(entry.get("direction")) for entry in records}
    words = [str(entry["word"]) for entry in records]
    start_size = max(int(size or 0), max(len(word) for word in words) + 6, min(18, max(12, len(words) + 6)))
    ceiling = max(start_size, int(max_size or min(64, start_size + max(8, len(words)))))
    best: Optional[Dict[str, Any]] = None
    best_score: Optional[Tuple[int, int, int, int]] = None
    attempts_per_size = max(1, int(attempts))
    for grid_size in range(start_size, ceiling + 1):
        for _ in range(attempts_per_size):
            layout = crossword_layout_attempt(records, grid_size, rng, allow_disconnected=allow_disconnected)
            placed_count = len(layout["positions"])
            score = (placed_count, layout["intersections"], -len(layout["unplaced"]), -layout["area"])
            if best is None or best_score is None or score > best_score:
                best = {**layout, "grid_size": grid_size}
                best_score = score
            if placed_count == len(words):
                break
        if best and len(best["positions"]) == len(words):
            break
    assert best is not None
    compacted = best["grid"]
    compacted_positions = best["positions"]
    number_map, across_clues, down_clues = assign_crossword_numbers(compacted_positions)
    source_entries = []
    for word in words:
        source_entry: Dict[str, Any] = {"word": word, "clue": clues[word]}
        if preferred_directions.get(word):
            source_entry["direction"] = preferred_directions[word]
        source_entries.append(source_entry)
    return {
        "grid": compacted,
        "number_map": number_map,
        "across_clues": across_clues,
        "down_clues": down_clues,
        "entries": [
            {
                "word": word,
                "clue": clues[word],
                "preferred_direction": preferred_directions.get(word),
                "number": number_map.get(",".join(map(str, compacted_positions.get(word, {}).get("start", []))), None),
                **compacted_positions.get(word, {}),
            }
            for word in words
            if word in compacted_positions
        ],
        "source_entries": source_entries,
        "unplaced": best["unplaced"],
        "generation": {
            "algorithm": "direction-aware-multi-attempt-scored-crossword",
            "seed": effective_seed,
            "requested_seed": seed,
            "grid_size": best.get("grid_size"),
            "max_size": ceiling,
            "attempts_per_size": attempts_per_size,
            "placed_count": len(compacted_positions),
            "entry_count": len(words),
            "directed_entry_count": sum(1 for direction in preferred_directions.values() if direction),
            "intersections": best["intersections"],
            "allow_disconnected": bool(allow_disconnected),
            "placement_mode": "intelligent",
        },
    }


def normalize_quiz_choices(value: Any) -> List[str]:
    if isinstance(value, dict):
        raw = list(value.values())
    elif isinstance(value, str):
        separators = ["|", ";"]
        raw = [value]
        for separator in separators:
            if separator in value:
                raw = value.split(separator)
                break
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        raw = []
    choices: List[str] = []
    for item in raw:
        if isinstance(item, dict):
            text = item.get("text", item.get("choice", item.get("answer", item.get("label", ""))))
        else:
            text = item
        clean = str(text).strip()
        if clean and clean.lower() not in {choice.lower() for choice in choices}:
            choices.append(clean)
    return choices


def normalize_quiz_answer_index(answer: Any, choices: List[str], one_based: bool = False) -> int:
    if not choices:
        return 0
    if isinstance(answer, str):
        text = answer.strip()
        for index, choice in enumerate(choices):
            if text.lower() == choice.lower():
                return index
        if len(text) == 1 and text.upper() in string.ascii_uppercase:
            return max(0, min(len(choices) - 1, string.ascii_uppercase.index(text.upper())))
        if text.isdigit():
            number = int(text)
            if one_based:
                number -= 1
            return max(0, min(len(choices) - 1, number))
    number = int(as_float(answer, 0))
    if one_based:
        number -= 1
    return max(0, min(len(choices) - 1, number))


def normalize_quiz_questions(
    questions: Iterable[Any],
    shuffle_choices: bool = False,
    shuffle_questions: bool = False,
    seed: Optional[Any] = None,
    min_choices: int = 2,
) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(questions, start=1):
        one_based_answer = False
        if isinstance(item, dict):
            question = str(item.get("question", item.get("prompt", f"Question {index}"))).strip()
            choices = item.get("choices", item.get("options", []))
            answer = item.get("answer_index", item.get("correct_index", item.get("correct", item.get("answer", item.get("correct_answer", 0)))))
            one_based_answer = "answer_number" in item or "correct_number" in item
            if "answer_number" in item:
                answer = item.get("answer_number")
            if "correct_number" in item:
                answer = item.get("correct_number")
            distractors = normalize_quiz_choices(item.get("distractors", []))
            clean_choices = normalize_quiz_choices(choices)
            if not clean_choices and item.get("answer") is not None:
                clean_choices = [str(item.get("answer")).strip()]
            for distractor in distractors:
                if distractor and distractor.lower() not in {choice.lower() for choice in clean_choices}:
                    clean_choices.append(distractor)
            explanation = str(item.get("explanation", "")).strip()
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            question = str(item[0]).strip()
            clean_choices = normalize_quiz_choices(item[1])
            answer = item[2] if len(item) >= 3 else 0
            explanation = str(item[3]).strip() if len(item) >= 4 else ""
        elif isinstance(item, str) and "|" in item:
            parts = [part.strip() for part in item.split("|") if part.strip()]
            if len(parts) < 3:
                continue
            question = parts[0]
            answer = parts[1]
            clean_choices = [parts[1], *parts[2:]]
            explanation = ""
        else:
            continue
        if isinstance(answer, str):
            answer_text = answer.strip()
            looks_like_label = len(answer_text) == 1 and answer_text.upper() in string.ascii_uppercase
            looks_like_index = answer_text.isdigit()
            if answer_text and not looks_like_label and not looks_like_index and all(answer_text.lower() != choice.lower() for choice in clean_choices):
                clean_choices.insert(0, answer_text)
        if not question or len(clean_choices) < max(1, int(min_choices)):
            continue
        answer_index = normalize_quiz_answer_index(answer, clean_choices, one_based=one_based_answer)
        if shuffle_choices and len(clean_choices) > 1:
            correct_choice = clean_choices[answer_index]
            rng.shuffle(clean_choices)
            answer_index = clean_choices.index(correct_choice)
        normalized.append({
            "question": question,
            "choices": clean_choices,
            "answer_index": answer_index,
            "explanation": explanation,
        })
    if shuffle_questions and len(normalized) > 1:
        rng.shuffle(normalized)
    return normalized


@dataclass
class WidgetTemplate:
    kind: str
    name: str
    width: int
    height: int
    properties: Dict[str, Any] = field(default_factory=dict)
    properties_schema: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    program: str = ""
    description: str = ""
    template_version: int = 1

    def make_widget(self, x: int, y: int) -> Dict[str, Any]:
        return conform_record({
            "widget_id": new_id("w"),
            "kind": self.kind,
            "name": self.name,
            "x": int(x),
            "y": int(y),
            "width": int(self.width),
            "height": int(self.height),
            "z": 0,
            "locked": False,
            "visible": True,
            "properties": conform_properties(self.properties, self.properties_schema),
            "program": self.program,
            "template_version": int(self.template_version),
            "created_at": now_iso(),
            "modified_at": now_iso(),
        }, "widget")

    def to_record(self, source: Any = "session") -> Dict[str, Any]:
        return conform_record({
            "kind": self.kind,
            "name": self.name,
            "width": int(self.width),
            "height": int(self.height),
            "properties": conform_properties(self.properties, self.properties_schema),
            "properties_schema": normalize_property_schema(self.properties_schema, self.properties),
            "program": self.program,
            "description": self.description,
            "source": normalize_source_record(source),
            "template_version": int(self.template_version),
            "modified_at": now_iso(),
        }, "template")

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "WidgetTemplate":
        data = conform_record(record, "template")
        properties = deep_copy(data.get("properties", {})) if isinstance(data.get("properties"), dict) else {}
        properties_schema = normalize_property_schema(data.get("properties_schema", {}), properties)
        return cls(
            kind=str(data.get("kind", "free_program")).strip() or "free_program",
            name=str(data.get("name", data.get("kind", "Widget"))).strip() or "Widget",
            width=max(16, int(as_float(data.get("width", 300), 300))),
            height=max(16, int(as_float(data.get("height", 180), 180))),
            properties=conform_properties(properties, properties_schema),
            properties_schema=properties_schema,
            program=str(data.get("program", FREE_PROGRAM_WIDGET_PROGRAM)),
            description=str(data.get("description", "")),
            template_version=max(1, int(as_float(data.get("template_version", 1), 1))),
        )


class PluginRegistry:
    def __init__(self) -> None:
        self.templates: Dict[str, WidgetTemplate] = {}
        self.sources: Dict[str, Dict[str, Any]] = {}
        self.plugin_records: List[Dict[str, Any]] = []
        self.collision_events: List[Dict[str, Any]] = []
        self.register_builtins()

    def register(self, template: WidgetTemplate, source: Any = "builtin", collision_policy: str = "error") -> None:
        template.kind = self.validate_kind(template.kind)
        source_record = normalize_source_record(source)
        if template.kind in self.templates:
            event = {
                "kind": template.kind,
                "existing_source": normalize_source_record(self.sources.get(template.kind, "session")),
                "new_source": source_record,
                "at": now_iso(),
            }
            self.collision_events.append(event)
            if collision_policy != "replace":
                raise ValueError(
                    f"Template kind collision for {template.kind}: "
                    f"{source_label(event['existing_source'])} already registered it"
                )
        self.templates[template.kind] = template
        self.sources[template.kind] = source_record

    def register_widget(
        self,
        kind: str,
        name: str,
        width: int,
        height: int,
        properties: Optional[Dict[str, Any]] = None,
        properties_schema: Optional[Dict[str, Any]] = None,
        program: str = "",
        description: str = "",
        source: Any = "builtin",
        collision_policy: str = "replace",
    ) -> None:
        defaults = properties or {}
        self.register(
            WidgetTemplate(
                kind=kind,
                name=name,
                width=width,
                height=height,
                properties=defaults,
                properties_schema=normalize_property_schema(properties_schema or {}, defaults),
                program=program,
                description=description,
            ),
            source=source,
            collision_policy=collision_policy,
        )

    def names(self) -> List[str]:
        return sorted(self.templates)

    def get(self, kind: str) -> WidgetTemplate:
        return self.templates[kind]

    def validate_kind(self, kind: str) -> str:
        normalized = str(kind).strip()
        if not normalized:
            raise ValueError("Template kind cannot be empty")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.:")
        if any(ch not in allowed for ch in normalized):
            raise ValueError("Template kind may use letters, numbers, underscore, dash, dot, and colon only")
        return normalized

    def to_session_records(self) -> Dict[str, Dict[str, Any]]:
        return {
            kind: template.to_record(source=self.sources.get(kind, default_source_record("session")))
            for kind, template in sorted(self.templates.items())
        }

    def load_session_records(self, records: Dict[str, Any]) -> None:
        self.templates.clear()
        self.sources.clear()
        self.collision_events.clear()
        if not isinstance(records, dict) or not records:
            self.register_builtins()
            return
        for key, record in sorted(records.items()):
            if not isinstance(record, dict):
                continue
            data = deep_copy(record)
            data.setdefault("kind", key)
            data["kind"] = self.validate_kind(data["kind"])
            source = normalize_source_record(data.get("source", "session"))
            self.register(WidgetTemplate.from_record(data), source=source, collision_policy="replace")
        if not self.templates:
            self.register_builtins()
        elif "png_image" not in self.templates:
            # Older saved registries predate the image widget. Keep every saved
            # template (including user edits) while making the new kind available.
            self.register_png_image()

    def upsert_template(self, record: Dict[str, Any], source: Any = "session") -> WidgetTemplate:
        data = deep_copy(record)
        data["kind"] = self.validate_kind(data.get("kind", ""))
        template = WidgetTemplate.from_record(data)
        self.register(template, source=source, collision_policy="replace")
        return template

    def delete_template(self, kind: str) -> bool:
        kind = self.validate_kind(kind)
        if kind not in self.templates:
            return False
        del self.templates[kind]
        self.sources.pop(kind, None)
        return True

    def duplicate_template(self, kind: str, new_kind: Optional[str] = None) -> WidgetTemplate:
        kind = self.validate_kind(kind)
        if kind not in self.templates:
            raise KeyError(f"Unknown template kind: {kind}")
        base = self.templates[kind]
        candidate = new_kind or f"{kind}_copy"
        stem = candidate
        index = 2
        while candidate in self.templates:
            candidate = f"{stem}_{index}"
            index += 1
        record = base.to_record(source="session")
        record["kind"] = candidate
        record["name"] = f"{base.name} copy"
        return self.upsert_template(record, source="session")

    def register_builtins(self) -> None:
        self.register_png_image()
        self.register_widget(
            kind="text",
            name="Text",
            width=330,
            height=70,
            properties={
                "text": "Mathematics whiteboard",
                "font_size": 24,
                "fill": "#111111",
                "anchor": "nw",
            },
            program=TEXT_WIDGET_PROGRAM,
            description="Programmable text object.",
        )
        self.register_widget(
            kind="formula",
            name="Formula",
            width=470,
            height=92,
            properties={
                "formula": "∀x ∈ ℝ,  |x| ≥ 0",
                "font_size": 26,
                "fill": "#111111",
            },
            program=FORMULA_WIDGET_PROGRAM,
            description="Unicode mathematical formula object.",
        )
        self.register_widget(
            kind="graph2d",
            name="Function Graph",
            width=430,
            height=280,
            properties={
                "expression": "math.sin(x)",
                "xmin": -6.28318,
                "xmax": 6.28318,
                "ymin": -1.5,
                "ymax": 1.5,
                "samples": 240,
                "title": "y = sin(x)",
            },
            program=GRAPH_WIDGET_PROGRAM,
            description="Programmable two-dimensional function graph.",
        )
        self.register_widget(
            kind="3Dplot",
            name="3D Plot Layer / Superimpose",
            width=640,
            height=460,
            properties={
                "title": "Layered 3D mathematical plot",
                "projection": {"azimuth_deg": 45, "elevation_deg": 28, "scale": 1.0},
                "bounds": {"xmin": -3.14159, "xmax": 3.14159, "ymin": -3.14159, "ymax": 3.14159, "zmin": -2.0, "zmax": 2.0},
                "show_axes": True,
                "show_box": True,
                "show_grid_floor": True,
                "superimpose": True,
                "layer_strategy": "sort_by_layer",
                "structures": [
                    {
                        "id": "surface_1",
                        "type": "surface",
                        "enabled": True,
                        "layer": 0,
                        "label": "z = sin(x) cos(y)",
                        "z": "math.sin(x) * math.cos(y)",
                        "xmin": -3.14159,
                        "xmax": 3.14159,
                        "ymin": -3.14159,
                        "ymax": 3.14159,
                        "x_samples": 24,
                        "y_samples": 24,
                        "style": {"stroke": "#111111", "width": 1},
                    },
                    {
                        "id": "helix",
                        "type": "parametric_curve",
                        "enabled": True,
                        "layer": 1,
                        "label": "helix",
                        "x": "math.cos(t)",
                        "y": "math.sin(t)",
                        "z": "t / 3",
                        "tmin": -6.28318,
                        "tmax": 6.28318,
                        "samples": 220,
                        "style": {"stroke": "#0b63ce", "width": 2},
                    },
                    {
                        "id": "sample_points",
                        "type": "point_cloud",
                        "enabled": True,
                        "layer": 2,
                        "label": "sample points",
                        "points": [[-2, -2, 0], [0, 0, 1], [2, 1, -0.5], [1.5, -1.2, 1.2]],
                        "style": {"stroke": "#333333", "fill": "#ffffff", "radius": 3},
                    },
                ],
                "render_stats": {},
                "semantic_role": "figure",
            },
            program=PLOT3D_WIDGET_PROGRAM,
            description="Layered and superimposed 3D surface, curve, point-cloud, and vector-field plot widget using the shared drawing API.",
        )
        self.register_widget(
            kind="code-block",
            name="Code Block with Line Numbers",
            width=600,
            height=360,
            properties={
                "title": "Source code",
                "language": "python",
                "code": "def theorem_step(x):\n    return abs(x) >= 0",
                "start_line": 1,
                "show_line_numbers": True,
                "font_size": 11,
                "line_height": 16,
                "tab_size": 4,
                "background": "#ffffff",
                "gutter_fill": "#f4f4f4",
                "border_fill": "#111111",
                "text_fill": "#111111",
                "line_number_fill": "#777777",
                "wrap": False,
                "metadata": {},
                "semantic_role": "source-code",
            },
            program=CODE_BLOCK_WIDGET_PROGRAM,
            description="JSON-persistent code block widget with line numbering and code metadata.",
        )
        self.register_widget(
            kind="rectangle",
            name="Rectangle",
            width=220,
            height=120,
            properties={
                "outline": "#111111",
                "fill": "",
                "stroke_width": 2,
                "label": "set / region",
                "font_size": 16,
            },
            program=RECTANGLE_WIDGET_PROGRAM,
            description="Programmable rectangle object.",
        )
        self.register_widget(
            kind="line",
            name="Line",
            width=260,
            height=60,
            properties={
                "fill": "#111111",
                "stroke_width": 3,
                "arrow": "last",
                "label": "relation",
            },
            program=LINE_WIDGET_PROGRAM,
            description="Programmable line or arrow object.",
        )
        self.register_widget(
            kind="free_program",
            name="Free Program Widget",
            width=360,
            height=220,
            properties={
                "title": "custom widget",
            },
            program=FREE_PROGRAM_WIDGET_PROGRAM,
            description="Blank programmable widget with full drawing API access.",
        )
        self.register_widget(
            kind="table",
            name="Mathematical Table",
            width=410,
            height=260,
            properties={
                "rows": 5,
                "cols": 5,
                "cell_text": "i,j",
                "title": "operation table",
            },
            program=TABLE_WIDGET_PROGRAM,
            description="Programmable grid/table widget.",
        )
        self.register_widget(
            kind="wordsearch",
            name="Word Search Puzzle",
            width=694,
            height=1010,
            properties={
                "title": "Algebra word search",
                "subtitle": "Find each term in the grid.",
                "grid": [
                    "VECTORSMATH",
                    "ALGEBRAPRO",
                    "NUMBERLINE",
                    "MATRIXGRAPH",
                    "PROOFAXIOM",
                    "DOMAINRANGE",
                    "ANGLECURVE",
                    "LOGICSPACE",
                    "TENSORLIMIT",
                    "SERIESROOT",
                    "FUNCTIONSET",
                ],
                "grid_size": 11,
                "words": ["ALGEBRA", "AXIOM", "DOMAIN", "FUNCTION", "GRAPH", "LIMIT", "MATRIX", "PROOF", "VECTOR"],
                "display_words": {},
                "source_words": ["algebra", "matrix", "vector", "proof", "axiom", "function", "domain", "range"],
                "word_positions": {},
                "skipped_words": [],
                "directions": ["H-R", "H-L", "V-D", "V-U", "D-R", "D-L", "U-R", "U-L"],
                "seed": "",
                "max_grid_size": 40,
                "max_attempts": 16,
                "filler_alphabet": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                "auto_generate": True,
                "placement_mode": "intelligent",
                "generation": {},
                "show_word_bank": True,
                "show_solution": False,
                "style_source": "style.css",
                "background_fill": "#ffffff",
                "body_font_family": "Helvetica",
                "body_font_size": 12,
                "body_fill": "#333333",
                "header_align": "center",
                "header_border_fill": "#f0f0f0",
                "header_border_width": 2,
                "header_padding_bottom": 10,
                "header_margin_bottom": 20,
                "title_font_size": 12,
                "title_fill": "#111111",
                "subtitle_font_size": 11,
                "subtitle_fill": "#666666",
                "grid_fill": "#ffffff",
                "grid_border_fill": "#cccccc",
                "grid_border_width": 1,
                "grid_inner_lines": False,
                "grid_margin_bottom": 15,
                "grid_letter_font_family": "monospace",
                "grid_letter_font_size": 14,
                "grid_letter_fill": "#000000",
                "word_list_margin_top": 20,
                "word_list_columns": 4,
                "word_list_column_gap": 25,
                "word_list_font_size": 8,
                "word_list_fill": "#000000",
                "word_list_padding_bottom": 4,
                "word_list_uppercase": True,
                "show_word_list_label": False,
                "solution_highlight_fill": "#e0e0e0",
                "solution_letter_font_size": 6,
                "solution_compact_letters": False,
                "semantic_role": "puzzle",
            },
            properties_schema={
                "title": {"type": "string", "default": "Algebra word search", "description": "Puzzle title."},
                "subtitle": {"type": "string", "default": "Find each term in the grid.", "description": "Optional subtitle."},
                "grid": {"type": "array", "default": [], "description": "Rows of uppercase grid letters."},
                "grid_size": {"type": "integer", "default": 11, "min": 4, "max": 40, "description": "Square grid size."},
                "words": {"type": "array", "default": [], "description": "Word-bank entries."},
                "display_words": {"type": "object", "default": {}, "description": "Display labels keyed by normalized word."},
                "source_words": {"type": "array", "default": [], "description": "Original source words used when regenerating."},
                "word_positions": {"type": "object", "default": {}, "description": "Solution coordinates keyed by word."},
                "skipped_words": {"type": "array", "default": [], "description": "Words that could not be placed."},
                "directions": {"type": "array", "default": ["H-R", "H-L", "V-D", "V-U", "D-R", "D-L", "U-R", "U-L"], "description": "Allowed placement directions."},
                "seed": {"type": "any", "default": "", "description": "Optional deterministic generation seed."},
                "max_grid_size": {"type": "integer", "default": 40, "min": 4, "max": 80, "description": "Largest grid size to try when regenerating."},
                "max_attempts": {"type": "integer", "default": 16, "min": 1, "max": 500, "description": "Placement attempts per grid size."},
                "filler_alphabet": {"type": "string", "default": "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "description": "Characters used to fill empty cells."},
                "auto_generate": {"type": "boolean", "default": True, "description": "Automatically place words and intelligently fill letters from source_words."},
                "placement_mode": {"type": "string", "default": "intelligent", "choices": ["intelligent"], "description": "Wordsearch letter placement strategy. Wordsearch grids always use intelligent fill."},
                "generation": {"type": "object", "default": {}, "description": "Generation metadata."},
                "show_word_bank": {"type": "boolean", "default": True, "description": "Render the word bank."},
                "show_solution": {"type": "boolean", "default": False, "description": "Render solution cells."},
                "style_source": {"type": "string", "default": "style.css", "description": "Named source of the default visual styling."},
                "background_fill": {"type": "string", "default": "#ffffff", "description": "Widget/page background fill."},
                "body_font_family": {"type": "string", "default": "Helvetica", "description": "Base font family matching the CSS body rule."},
                "body_font_size": {"type": "integer", "default": 12, "min": 1, "max": 96, "description": "Base font size in points/pixels for body text."},
                "body_fill": {"type": "string", "default": "#333333", "description": "Base text colour matching the CSS body rule."},
                "header_align": {"type": "string", "default": "center", "choices": ["center", "left"], "description": "Header text alignment."},
                "header_border_fill": {"type": "string", "default": "#f0f0f0", "description": "Header bottom border colour."},
                "header_border_width": {"type": "integer", "default": 2, "min": 0, "max": 12, "description": "Header bottom border width."},
                "header_padding_bottom": {"type": "integer", "default": 10, "min": 0, "max": 80, "description": "Space below heading text before the header border."},
                "header_margin_bottom": {"type": "integer", "default": 20, "min": 0, "max": 120, "description": "Space below the header before the grid."},
                "title_font_size": {"type": "integer", "default": 12, "min": 1, "max": 96, "description": "h1 title size from the CSS."},
                "title_fill": {"type": "string", "default": "#111111", "description": "h1 title colour from the CSS."},
                "subtitle_font_size": {"type": "integer", "default": 11, "min": 1, "max": 96, "description": "h2 subtitle size from the CSS."},
                "subtitle_fill": {"type": "string", "default": "#666666", "description": "h2 subtitle colour from the CSS."},
                "grid_fill": {"type": "string", "default": "#ffffff", "description": "Word-search square background."},
                "grid_border_fill": {"type": "string", "default": "#cccccc", "description": "Word-search square border colour."},
                "grid_border_width": {"type": "integer", "default": 1, "min": 0, "max": 12, "description": "Word-search square border width."},
                "grid_inner_lines": {"type": "boolean", "default": False, "description": "Draw inner grid lines. The CSS default keeps them invisible."},
                "grid_margin_bottom": {"type": "integer", "default": 15, "min": 0, "max": 120, "description": "Space between the grid and the word list."},
                "grid_letter_font_family": {"type": "string", "default": "monospace", "description": "Grid-letter font family from the CSS."},
                "grid_letter_font_size": {"type": "integer", "default": 14, "min": 1, "max": 96, "description": "Grid-letter font size from the CSS."},
                "grid_letter_fill": {"type": "string", "default": "#000000", "description": "Grid-letter colour from the CSS."},
                "word_list_margin_top": {"type": "integer", "default": 20, "min": 0, "max": 120, "description": "Word-list top margin."},
                "word_list_columns": {"type": "integer", "default": 4, "min": 1, "max": 8, "description": "Word-list column count from the CSS."},
                "word_list_column_gap": {"type": "integer", "default": 25, "min": 0, "max": 120, "description": "Word-list column gap from the CSS."},
                "word_list_font_size": {"type": "integer", "default": 8, "min": 1, "max": 96, "description": "Word-list item font size from the CSS."},
                "word_list_fill": {"type": "string", "default": "#000000", "description": "Word-list item colour from the CSS."},
                "word_list_padding_bottom": {"type": "integer", "default": 4, "min": 0, "max": 80, "description": "Space after each word-list item."},
                "word_list_uppercase": {"type": "boolean", "default": True, "description": "Render word-list items in uppercase."},
                "show_word_list_label": {"type": "boolean", "default": False, "description": "Show a Word bank label above the word list."},
                "solution_highlight_fill": {"type": "string", "default": "#e0e0e0", "description": "Solution cell highlight background from the CSS."},
                "solution_letter_font_size": {"type": "integer", "default": 6, "min": 1, "max": 96, "description": "Compact solution-letter size from the CSS."},
                "solution_compact_letters": {"type": "boolean", "default": False, "description": "Use compact 6pt solution lettering. Useful for four-up solution pages."},
            },
            program=WORDSEARCH_WIDGET_PROGRAM,
            description="Programmatically populated word-search puzzle widget with grid, word bank, and optional solution overlay.",
        )
        self.register_widget(
            kind="crossword",
            name="Crossword Puzzle",
            width=690,
            height=870,
            properties={
                "title": "Mathematics crossword",
                "subtitle": "Use the clues to complete the grid.",
                "grid": [
                    ["A", "X", "I", "O", "M", ""],
                    ["", "", "", "", "A", ""],
                    ["P", "R", "O", "O", "F", ""],
                    ["", "", "", "", "R", ""],
                    ["G", "R", "A", "P", "H", ""],
                ],
                "number_map": {"0,0": 1, "2,0": 2, "4,0": 3},
                "across_clues": ["1. Statement accepted as true", "2. Logical argument", "3. Vertices joined by edges"],
                "down_clues": [],
                "entries": [],
                "source_entries": [
                    {"word": "axiom", "clue": "A statement accepted as true"},
                    {"word": "proof", "clue": "A logical argument"},
                    {"word": "matrix", "clue": "A rectangular array of entries"},
                ],
                "unplaced": [],
                "seed": "",
                "max_grid_size": 48,
                "attempts": 120,
                "allow_disconnected": False,
                "auto_generate": True,
                "placement_mode": "intelligent",
                "generation": {},
                "show_solution": False,
                "semantic_role": "puzzle",
            },
            properties_schema={
                "title": {"type": "string", "default": "Mathematics crossword", "description": "Puzzle title."},
                "subtitle": {"type": "string", "default": "Use the clues to complete the grid.", "description": "Optional subtitle."},
                "grid": {"type": "array", "default": [], "description": "Grid rows. Empty cells are empty strings."},
                "number_map": {"type": "object", "default": {}, "description": "Cell numbers keyed as row,col."},
                "across_clues": {"type": "array", "default": [], "description": "Across clue strings."},
                "down_clues": {"type": "array", "default": [], "description": "Down clue strings."},
                "entries": {"type": "array", "default": [], "description": "Placed word records."},
                "source_entries": {"type": "array", "default": [], "description": "Original word/clue records used when regenerating. Records may include direction: across or down."},
                "unplaced": {"type": "array", "default": [], "description": "Words that could not be placed."},
                "seed": {"type": "any", "default": "", "description": "Optional deterministic generation seed."},
                "max_grid_size": {"type": "integer", "default": 48, "min": 12, "max": 96, "description": "Largest grid size to try when regenerating."},
                "attempts": {"type": "integer", "default": 120, "min": 1, "max": 1000, "description": "Layout attempts per grid size."},
                "allow_disconnected": {"type": "boolean", "default": False, "description": "Allow isolated clusters when a connected placement cannot fit."},
                "auto_generate": {"type": "boolean", "default": True, "description": "Automatically place answer letters from source_entries."},
                "placement_mode": {"type": "string", "default": "intelligent", "choices": ["intelligent", "manual"], "description": "Crossword letter placement strategy."},
                "generation": {"type": "object", "default": {}, "description": "Generation metadata."},
                "show_solution": {"type": "boolean", "default": False, "description": "Render answer letters in cells."},
            },
            program=CROSSWORD_WIDGET_PROGRAM,
            description="Programmatically populated crossword puzzle widget with compact grid, numbering, clues, and optional solution letters.",
        )
        self.register_widget(
            kind="multiple_choice_quiz",
            name="Multiple Choice Quiz",
            width=690,
            height=870,
            properties={
                "title": "Mathematics quiz",
                "subtitle": "Choose the best answer.",
                "questions": [
                    {
                        "question": "Which object represents a directed quantity?",
                        "choices": ["Scalar", "Vector", "Set", "Sequence"],
                        "answer_index": 1,
                        "explanation": "A vector has magnitude and direction.",
                    },
                    {
                        "question": "What is the identity element for addition?",
                        "choices": ["0", "1", "-1", "x"],
                        "answer_index": 0,
                        "explanation": "Adding zero leaves a number unchanged.",
                    },
                ],
                "source_questions": [],
                "shuffle_choices": False,
                "shuffle_questions": False,
                "seed": "",
                "min_choices": 2,
                "show_answers": False,
                "columns": 1,
                "semantic_role": "quiz",
            },
            properties_schema={
                "title": {"type": "string", "default": "Mathematics quiz", "description": "Quiz title."},
                "subtitle": {"type": "string", "default": "Choose the best answer.", "description": "Optional subtitle."},
                "questions": {"type": "array", "default": [], "description": "Question records with choices and answer_index."},
                "source_questions": {"type": "array", "default": [], "description": "Original question records used when normalizing."},
                "shuffle_choices": {"type": "boolean", "default": False, "description": "Shuffle choices when normalizing."},
                "shuffle_questions": {"type": "boolean", "default": False, "description": "Shuffle question order when normalizing."},
                "seed": {"type": "any", "default": "", "description": "Optional deterministic quiz shuffle seed."},
                "min_choices": {"type": "integer", "default": 2, "min": 1, "max": 10, "description": "Minimum choices required for a question."},
                "show_answers": {"type": "boolean", "default": False, "description": "Render answer marks and explanations."},
                "columns": {"type": "integer", "default": 1, "min": 1, "max": 2, "description": "Question columns."},
            },
            program=MULTIPLE_CHOICE_QUIZ_WIDGET_PROGRAM,
            description="Programmatically populated multiple-choice quiz widget with optional answer key rendering.",
        )
        self.register_widget(
            kind="formal_math",
            name="Formal Definition / Theorem / Proof",
            width=560,
            height=360,
            properties={
                "record_type": "theorem",
                "title": "Non-negativity of absolute value",
                "statement": "For every real number x, the absolute value of x is greater than or equal to zero.",
                "hypotheses": ["x ∈ ℝ"],
                "dependencies": ["definition:absolute_value", "order:real_numbers"],
                "proof_status": "draft",
                "proof_body": "Split into the cases x ≥ 0 and x < 0, then apply the definition of absolute value.",
                "proof_steps": [
                    {"id": "s1", "kind": "case", "text": "If x ≥ 0, then |x| = x, hence |x| ≥ 0.", "depends_on": ["hypothesis:x ∈ ℝ"], "status": "checked"},
                    {"id": "s2", "kind": "case", "text": "If x < 0, then |x| = -x, and -x > 0.", "depends_on": ["definition:absolute_value"], "status": "checked"},
                    {"id": "s3", "kind": "conclusion", "text": "Both cases imply |x| ≥ 0.", "depends_on": ["s1", "s2"], "status": "checked"}
                ],
                "tags": ["analysis", "order", "example"],
                "references": [],
                "linked_widgets": [],
                "render_mode": "record",
                "semantic_role": "claim",
            },
            program=FORMAL_MATH_WIDGET_PROGRAM,
            description="Structured records for definitions, axioms, lemmas, theorems, corollaries, conjectures, examples, counterexamples, and proof steps.",
        )
        self.register_widget(
            kind="symbolic_algebra",
            name="Symbolic Algebra and Assumption Engine",
            width=560,
            height=340,
            properties={
                "source_expression": "(x**2 - 1)/(x - 1)",
                "variables": ["x"],
                "assumptions": {"x": {"real": True}},
                "operation": "simplify",
                "substitutions": {},
                "differentiate_by": "x",
                "integrate_by": "x",
                "limit": {"variable": "x", "point": "1", "direction": "+"},
                "series": {"variable": "x", "point": "0", "order": 6},
                "result_forms": {},
                "transformation_history": [],
                "notes": "Run the widget action to compute the selected symbolic operation.",
                "semantic_role": "computation",
            },
            program=SYMBOLIC_ALGEBRA_WIDGET_PROGRAM,
            description="SymPy-backed symbolic manipulation with graceful degradation when SymPy is not installed.",
        )
        self.register_widget(
            kind="geometry_construction",
            name="Geometric Construction and Diagram",
            width=560,
            height=380,
            properties={
                "title": "Construction logic",
                "objects": [
                    {"id": "A", "type": "point", "x": 90, "y": 260, "label": "A"},
                    {"id": "B", "type": "point", "x": 300, "y": 120, "label": "B"},
                    {"id": "C", "type": "point", "x": 420, "y": 280, "label": "C"},
                    {"id": "AB", "type": "segment", "p1": "A", "p2": "B", "label": "AB"},
                    {"id": "BC", "type": "segment", "p1": "B", "p2": "C", "label": "BC"},
                    {"id": "circ_A", "type": "circle", "center": "A", "through": "B", "label": "circle(A,B)"},
                    {"id": "v", "type": "vector", "from": "A", "to": "C", "label": "v"}
                ],
                "construction_steps": [
                    "Place point A.",
                    "Place point B.",
                    "Construct circle with center A through B.",
                    "Draw vector from A to C."
                ],
                "measurements": {},
                "constraints": [],
                "semantic_role": "figure",
            },
            program=GEOMETRY_CONSTRUCTION_WIDGET_PROGRAM,
            description="Geometry widget preserving construction records for points, lines, circles, polygons, vectors, intersections, measurements, and constraints.",
        )
        self.register_widget(
            kind="graph_network_category",
            name="Graph / Network / Category / Dependency",
            width=560,
            height=360,
            properties={
                "title": "Proof dependency map",
                "layout": "stored",
                "nodes": [
                    {"id": "D1", "label": "Definition", "x": 90, "y": 110, "type": "definition"},
                    {"id": "L1", "label": "Lemma", "x": 280, "y": 80, "type": "lemma"},
                    {"id": "T1", "label": "Theorem", "x": 450, "y": 190, "type": "theorem"}
                ],
                "edges": [
                    {"id": "e1", "source": "D1", "target": "L1", "label": "uses", "arrow": "last", "type": "dependency"},
                    {"id": "e2", "source": "L1", "target": "T1", "label": "proves", "arrow": "last", "type": "implication"}
                ],
                "validation_rules": ["Every edge source and target must exist."],
                "validation_report": [],
                "semantic_role": "diagram",
            },
            program=GRAPH_NETWORK_CATEGORY_WIDGET_PROGRAM,
            description="Typed node-arrow structures for dependency graphs, categories, commutative diagrams, state machines, implication graphs, and tensor-flow diagrams.",
        )
        self.register_widget(
            kind="applied_model_simulation",
            name="Applied Mathematics Model and Simulation",
            width=600,
            height=380,
            properties={
                "title": "Discrete logistic model",
                "model_type": "discrete",
                "variables": ["x"],
                "parameters": {"r": 3.2},
                "initial_conditions": {"x": 0.2},
                "update_rules": {"x": "r*x*(1-x)"},
                "equations": {},
                "steps": 80,
                "dt": 0.1,
                "solver": "explicit_euler",
                "outputs": [],
                "plot_variable": "x",
                "experiment_notes": "Run the widget action to simulate.",
                "semantic_role": "computation",
            },
            program=APPLIED_MODEL_SIMULATION_WIDGET_PROGRAM,
            description="Variables, parameters, equations, update rules, numerical methods, outputs, plots, and experiment notes.",
        )
        self.register_widget(
            kind="tensor_matrix_operator_lab",
            name="Tensor / Matrix / Table / Operator Laboratory",
            width=600,
            height=380,
            properties={
                "title": "Modulo operator table",
                "mode": "cayley",
                "rows": 6,
                "cols": 6,
                "entries": [[1, 0], [0, 1]],
                "modulus": 6,
                "operation": "addition",
                "row_labels": [],
                "col_labels": [],
                "computed_table": [],
                "computed_properties": {},
                "history": [],
                "semantic_role": "computation",
            },
            program=TENSOR_MATRIX_OPERATOR_LAB_WIDGET_PROGRAM,
            description="Matrices, tensors, basis objects, transformations, multiplication tables, Cayley tables, truth tables, tensor-index tables, and operator compositions.",
        )
        self.register_widget(
            kind="research_notebook",
            name="Research Notebook / Citation / Export Composition",
            width=600,
            height=420,
            properties={
                "title": "Research note",
                "author": "",
                "abstract": "A live A4 whiteboard page can be composed into a research document by classifying widgets as claims, proofs, computations, diagrams, figures, and notes.",
                "sections": [
                    {"heading": "Definitions", "body": "Collect formal definition widgets here."},
                    {"heading": "Results", "body": "Collect theorem and proof widgets here."},
                    {"heading": "Computations", "body": "Collect symbolic, numerical, and tensor widgets here."}
                ],
                "numbered_equations": [],
                "figure_captions": [],
                "references": [],
                "source_links": [],
                "page_inventory": [],
                "export_order": [],
                "semantic_role": "document",
            },
            program=RESEARCH_NOTEBOOK_WIDGET_PROGRAM,
            description="Document-ready title blocks, abstracts, sections, equation numbers, captions, references, metadata, and page-order export settings.",
        )
        self.register_widget(
            kind="document_export_controller",
            name="Document Export Controller",
            width=520,
            height=300,
            properties={
                "title": "Mathematics whiteboard export",
                "author": "",
                "page_range": "all",
                "page_order": [],
                "include_grid": True,
                "include_page_titles": False,
                "include_widget_bounds": False,
                "include_metadata": True,
                "exclude_hidden_widgets": True,
                "one_file_per_page": False,
                "theorem_numbering": "by-page",
                "figure_numbering": "by-page",
                "export_profile_name": "default",
                "semantic_role": "controller",
            },
            program=DOCUMENT_EXPORT_CONTROLLER_WIDGET_PROGRAM,
            description="Programmable PDF publishing controller that writes export preferences back into the JSON session.",
        )

    def register_png_image(self) -> None:
        self.register_widget(
            kind="png_image", name="PNG Image", width=360, height=240,
            properties={
                "path": "", "data_base64": "", "fit": "contain",
                "anchor": "center", "padding": 8, "background": "",
                "border_color": "#dddddd", "border_width": 1,
            },
            properties_schema={
                "path": {"type": "string", "description": "Linked .png path; relative to the saved session, or working directory before saving."},
                "data_base64": {"type": "string", "description": "Embedded PNG bytes encoded as base64. Takes precedence over path; clear to use a linked file."},
                "fit": {"type": "string", "choices": ["contain", "cover", "stretch"], "description": "Contain preserves the whole image; cover crops to fill; stretch changes proportions."},
                "anchor": {"type": "string", "choices": ["nw", "n", "ne", "w", "center", "e", "sw", "s", "se"], "description": "Image alignment and crop focus within its box."},
                "padding": {"type": "integer", "min": 0, "description": "Inset in pixels, clamped to leave room for the image when resized."},
                "background": {"type": "string", "description": "Background color; empty means transparent."},
                "border_color": {"type": "string", "description": "Border color; empty hides the border."},
                "border_width": {"type": "integer", "min": 0, "description": "Border thickness in pixels; zero hides the border."},
            },
            program=PNG_IMAGE_WIDGET_PROGRAM,
            description="Configurable PNG image with transparency, fitting, alignment and framing. Use Widget > Add PNG Image to embed a file, or edit properties.path for a linked image. Pillow required; supports PDF export.",
        )

    def load_directory(self, directory: str) -> Tuple[int, List[str]]:
        loaded = 0
        notices: List[str] = []
        root = Path(directory)
        if not root.exists():
            return 0, [f"Plugin directory does not exist: {directory}"]
        for path in sorted(root.glob("*.py")):
            plugin_record: Dict[str, Any] = {
                "file": str(path),
                "status": "failed",
                "manifest": {},
                "templates": [],
                "warnings": [],
                "error": "",
                "loaded_at": now_iso(),
            }
            try:
                module_name = f"mathematics_plugin_{path.stem}_{uuid.uuid4().hex[:8]}"
                spec = importlib.util.spec_from_file_location(module_name, str(path))
                if spec is None or spec.loader is None:
                    raise RuntimeError("Could not create import specification")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore[union-attr]
                manifest = normalize_plugin_manifest(module, path)
                plugin_record["manifest"] = manifest
                if not api_requirement_satisfied(manifest.get("requires_api")):
                    raise RuntimeError(
                        f"Plugin requires API {manifest.get('requires_api')}, "
                        f"but {APP_NAME} exposes {PLUGIN_API_VERSION}"
                    )
                if not hasattr(module, "register"):
                    raise RuntimeError("Plugin does not define register(api)")
                source = {
                    "kind": "plugin",
                    "path": str(path),
                    "manifest": manifest,
                    "api_version": PLUGIN_API_VERSION,
                    "loaded_at": plugin_record["loaded_at"],
                }
                api = PluginRegistrationAPI(self, source)
                module.register(api)
                plugin_record["templates"] = deep_copy(api.registered_templates)
                plugin_record["warnings"] = deep_copy(api.warnings)
                plugin_record["status"] = "loaded"
                loaded += 1
                if api.warnings:
                    notices.extend(f"{path.name}: {warning}" for warning in api.warnings)
            except Exception:
                plugin_record["error"] = traceback.format_exc()
                notices.append(f"{path.name}:\n{plugin_record['error']}")
            self.plugin_records.append(plugin_record)
        return loaded, notices


class PluginRegistrationAPI:
    def __init__(self, registry: PluginRegistry, source: Any) -> None:
        self.registry = registry
        self.source = normalize_source_record(source, default_kind="plugin")
        self.api_version = PLUGIN_API_VERSION
        self.manifest = deep_copy(self.source.get("manifest", {})) if isinstance(self.source.get("manifest"), dict) else {}
        self.namespace = sanitize_plugin_id(self.manifest.get("id") or Path(str(self.source.get("path", "plugin"))).stem)
        self.registered_templates: List[str] = []
        self.warnings: List[str] = []

    def describe(self, name: Optional[str] = None) -> str:
        return describe_registration_api(name)

    def register_widget(
        self,
        kind: str,
        name: str,
        width: int = 300,
        height: int = 180,
        properties: Optional[Dict[str, Any]] = None,
        properties_schema: Optional[Dict[str, Any]] = None,
        program: str = "",
        description: str = "",
    ) -> None:
        normalized_kind = self.registry.validate_kind(kind)
        if ":" not in normalized_kind:
            normalized_kind = f"{self.namespace}:{normalized_kind}"
            self.warnings.append(f"Template kind {kind!r} was registered as namespaced kind {normalized_kind!r}.")
        self.registry.register_widget(
            kind=normalized_kind,
            name=name,
            width=width,
            height=height,
            properties=properties or {},
            properties_schema=properties_schema or {},
            program=program,
            description=description,
            source=self.source,
            collision_policy="error",
        )
        self.registered_templates.append(normalized_kind)


class WhiteboardKernel:
    def __init__(self) -> None:
        self.registry = PluginRegistry()
        self.session_path: Optional[str] = None
        self.session = self.new_session_object()
        self.current_page_id: str = self.session["pages"][0]["page_id"]
        self.dirty = False

    def new_session_object(self) -> Dict[str, Any]:
        page = self.new_page_object("Page 1")
        return conform_record({
            "schema": SCHEMA,
            "schema_version": SESSION_SCHEMA_VERSION,
            "app": APP_NAME,
            "session_id": new_id("s"),
            "title": "Untitled mathematics session",
            "created_at": now_iso(),
            "modified_at": now_iso(),
            "page_model": default_page_model(),
            "plugins": {"api_version": PLUGIN_API_VERSION, "loaded": [], "templates": {}},
            "export_settings": deep_copy(DEFAULT_EXPORT_SETTINGS),
            "widget_templates": self.registry.to_session_records(),
            "pages": [page],
        }, "session")

    def reset(self) -> None:
        self.session_path = None
        self.session = self.new_session_object()
        self.current_page_id = self.session["pages"][0]["page_id"]
        self.dirty = False

    def touch(self) -> None:
        self.session["modified_at"] = now_iso()
        self.dirty = True

    def new_page_object(self, title: str) -> Dict[str, Any]:
        return conform_record({
            "page_id": new_id("p"),
            "title": title,
            "width_mm": A4_WIDTH_MM,
            "height_mm": A4_HEIGHT_MM,
            "dpi": PAGE_DPI,
            "width_px": A4_WIDTH_PX,
            "height_px": A4_HEIGHT_PX,
            "background": "#ffffff",
            "grid": {"enabled": False, "spacing": 24, "fill": "#eeeeee"},
            "widgets": [],
            "created_at": now_iso(),
            "modified_at": now_iso(),
        }, "page")

    def sync_templates_to_session(self, mark_dirty: bool = True) -> None:
        self.session["widget_templates"] = self.registry.to_session_records()
        self.session["plugins"] = {
            "api_version": PLUGIN_API_VERSION,
            "loaded": deep_copy(self.registry.plugin_records),
            "collisions": deep_copy(self.registry.collision_events),
            "templates": {
                kind: normalize_source_record(source)
                for kind, source in sorted(self.registry.sources.items())
                if normalize_source_record(source).get("kind") != "builtin"
            },
        }
        if mark_dirty:
            self.touch()

    def load_plugin_directory(self, directory: str) -> Tuple[int, List[str]]:
        loaded, errors = self.registry.load_directory(directory)
        if loaded or errors:
            self.sync_templates_to_session(mark_dirty=True)
        return loaded, errors

    def run_page_generator(
        self,
        program: str,
        project_path: Optional[str] = None,
        source: str = "generator",
        logger: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        api = PageGeneratorAPI(self, project_path=project_path, source=source, logger=logger)
        result = execute_page_generator_program(program, api)
        summary = api.summary()
        summary["result"] = deep_copy(result)
        summary["ran_at"] = now_iso()
        self.session.setdefault("generators", []).append(summary)
        self.touch()
        return summary

    def list_templates(self) -> Dict[str, Dict[str, Any]]:
        return self.registry.to_session_records()

    def get_template(self, kind: str) -> Optional[Dict[str, Any]]:
        if kind not in self.registry.templates:
            return None
        return self.registry.templates[kind].to_record(source=self.registry.sources.get(kind, "session"))

    def upsert_template(self, record: Dict[str, Any], source: Any = "session") -> Dict[str, Any]:
        template = self.registry.upsert_template(record, source=source)
        self.sync_templates_to_session(mark_dirty=True)
        return template.to_record(source=source)

    def delete_template(self, kind: str) -> bool:
        ok = self.registry.delete_template(kind)
        if ok:
            self.sync_templates_to_session(mark_dirty=True)
        return ok

    def duplicate_template(self, kind: str, new_kind: Optional[str] = None) -> Dict[str, Any]:
        template = self.registry.duplicate_template(kind, new_kind=new_kind)
        self.sync_templates_to_session(mark_dirty=True)
        return template.to_record(source="session")

    def list_pages(self) -> List[Dict[str, Any]]:
        return self.session["pages"]

    def current_page(self) -> Dict[str, Any]:
        page = self.get_page(self.current_page_id)
        if page is None:
            self.current_page_id = self.session["pages"][0]["page_id"]
            page = self.session["pages"][0]
        return page

    def get_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        for page in self.session["pages"]:
            if page.get("page_id") == page_id:
                return page
        return None

    def add_page(self, title: Optional[str] = None) -> Dict[str, Any]:
        title = title or f"Page {len(self.session['pages']) + 1}"
        page = self.new_page_object(title)
        self.session["pages"].append(page)
        self.current_page_id = page["page_id"]
        self.touch()
        return page

    def duplicate_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        page = self.get_page(page_id)
        if page is None:
            return None
        new_page = deep_copy(page)
        new_page["page_id"] = new_id("p")
        new_page["title"] = f"{page.get('title', 'Page')} copy"
        new_page["created_at"] = now_iso()
        new_page["modified_at"] = now_iso()
        for widget in new_page.get("widgets", []):
            widget["widget_id"] = new_id("w")
            widget["created_at"] = now_iso()
            widget["modified_at"] = now_iso()
        self.session["pages"].append(new_page)
        self.current_page_id = new_page["page_id"]
        self.touch()
        return new_page

    def delete_page(self, page_id: str) -> bool:
        pages = self.session["pages"]
        if len(pages) <= 1:
            return False
        index = next((i for i, p in enumerate(pages) if p.get("page_id") == page_id), None)
        if index is None:
            return False
        del pages[index]
        self.current_page_id = pages[max(0, index - 1)]["page_id"]
        self.touch()
        return True

    def rename_page(self, page_id: str, title: str) -> bool:
        page = self.get_page(page_id)
        if page is None:
            return False
        page["title"] = title
        page["modified_at"] = now_iso()
        self.touch()
        return True

    def get_widget(self, widget_id: str, page_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pages = [self.get_page(page_id)] if page_id else self.session["pages"]
        for page in pages:
            if not page:
                continue
            for widget in page.get("widgets", []):
                if widget.get("widget_id") == widget_id:
                    return widget
        return None

    def get_widget_page(self, widget_id: str) -> Optional[Dict[str, Any]]:
        for page in self.session["pages"]:
            for widget in page.get("widgets", []):
                if widget.get("widget_id") == widget_id:
                    return page
        return None

    def list_widgets(self, page_id: Optional[str] = None) -> List[Dict[str, Any]]:
        page = self.get_page(page_id or self.current_page_id)
        if page is None:
            return []
        return sorted(page.get("widgets", []), key=lambda w: int(w.get("z", 0)))

    def create_widget(
        self,
        kind: str,
        x: int = 80,
        y: int = 80,
        page_id: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        page = self.get_page(page_id or self.current_page_id)
        if page is None:
            raise KeyError("Page not found")
        if kind not in self.registry.templates:
            raise KeyError(f"Unknown widget kind: {kind}")
        template = self.registry.get(kind)
        widget = template.make_widget(x, y)
        widget["z"] = len(page.get("widgets", []))
        widget["template_source"] = normalize_source_record(self.registry.sources.get(kind, "session"))
        if overrides:
            for key, value in overrides.items():
                if key == "properties" and isinstance(value, dict):
                    widget.setdefault("properties", {}).update(value)
                else:
                    widget[key] = value
        self.conform_widget_properties(widget)
        page.setdefault("widgets", []).append(widget)
        try:
            self.execute_widget_lifecycle_hook(widget, page, "on_create")
        except Exception:
            page["widgets"].remove(widget)
            raise
        page["modified_at"] = now_iso()
        self.touch()
        return widget

    def update_widget(self, widget_id: str, updates: Dict[str, Any]) -> bool:
        widget = self.get_widget(widget_id)
        if widget is None:
            return False
        candidate = deep_copy(widget)
        for key, value in updates.items():
            if key in {"widget_id", "created_at"}:
                continue
            candidate[key] = value
        if "kind" in updates and candidate.get("kind") != widget.get("kind") and candidate.get("kind") not in self.registry.templates:
            raise KeyError(f"Unknown widget kind: {candidate.get('kind')}")
        self.conform_widget_properties(candidate)
        page = self.get_widget_page(widget_id)
        if page is None:
            return False
        found, result = self.execute_widget_lifecycle_hook(candidate, page, "validate")
        if found:
            if result is False:
                raise ValueError(f"Widget validation rejected {candidate.get('name', widget_id)}")
            if isinstance(result, str) and result.strip():
                raise ValueError(result)
        candidate["modified_at"] = now_iso()
        widget.clear()
        widget.update(candidate)
        if page:
            page["modified_at"] = now_iso()
        self.touch()
        return True

    def delete_widget(self, widget_id: str) -> bool:
        page = self.get_widget_page(widget_id)
        if page is None:
            return False
        widgets = page.get("widgets", [])
        before = len(widgets)
        page["widgets"] = [w for w in widgets if w.get("widget_id") != widget_id]
        if len(page["widgets"]) == before:
            return False
        self.normalize_z(page)
        page["modified_at"] = now_iso()
        self.touch()
        return True

    def duplicate_widget(self, widget_id: str) -> Optional[Dict[str, Any]]:
        page = self.get_widget_page(widget_id)
        widget = self.get_widget(widget_id)
        if page is None or widget is None:
            return None
        clone = deep_copy(widget)
        clone["widget_id"] = new_id("w")
        clone["name"] = f"{widget.get('name', 'Widget')} copy"
        clone["x"] = int(widget.get("x", 0)) + 24
        clone["y"] = int(widget.get("y", 0)) + 24
        clone["z"] = len(page.get("widgets", []))
        clone["created_at"] = now_iso()
        clone["modified_at"] = now_iso()
        page.setdefault("widgets", []).append(clone)
        page["modified_at"] = now_iso()
        self.touch()
        return clone

    def move_widget(self, widget_id: str, dx: float, dy: float) -> bool:
        widget = self.get_widget(widget_id)
        page = self.get_widget_page(widget_id)
        if widget is None or page is None or widget.get("locked"):
            return False
        width = as_float(widget.get("width"), 10)
        height = as_float(widget.get("height"), 10)
        widget["x"] = int(clamp(as_float(widget.get("x")) + dx, 0, page["width_px"] - width))
        widget["y"] = int(clamp(as_float(widget.get("y")) + dy, 0, page["height_px"] - height))
        widget["modified_at"] = now_iso()
        page["modified_at"] = now_iso()
        self.touch()
        return True

    def resize_widget(self, widget_id: str, width: float, height: float) -> bool:
        widget = self.get_widget(widget_id)
        page = self.get_widget_page(widget_id)
        if widget is None or page is None or widget.get("locked"):
            return False
        x = as_float(widget.get("x"))
        y = as_float(widget.get("y"))
        old_size = {"width": widget.get("width"), "height": widget.get("height")}
        widget["width"] = int(clamp(width, 16, page["width_px"] - x))
        widget["height"] = int(clamp(height, 16, page["height_px"] - y))
        self.execute_widget_lifecycle_hook(
            widget,
            page,
            "on_resize",
            event={**old_size, "new_width": widget["width"], "new_height": widget["height"]},
        )
        widget["modified_at"] = now_iso()
        page["modified_at"] = now_iso()
        self.touch()
        return True

    def conform_widget_properties(self, widget: Dict[str, Any]) -> None:
        kind = str(widget.get("kind", ""))
        if kind not in self.registry.templates:
            widget["properties"] = deep_copy(widget.get("properties", {})) if isinstance(widget.get("properties"), dict) else {}
            return
        template = self.registry.get(kind)
        widget["properties"] = conform_properties(
            widget.get("properties", {}),
            template.properties_schema,
            template.properties,
        )
        widget.setdefault("template_version", int(template.template_version))
        widget.setdefault("template_source", normalize_source_record(self.registry.sources.get(kind, "session")))

    def execute_widget_lifecycle_hook(
        self,
        widget: Dict[str, Any],
        page: Dict[str, Any],
        mode: str,
        event: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Any]:
        api = WidgetLifecycleAPI(self, page, widget, event=event)
        return execute_widget_hook(api, widget, page, self.session, mode)

    def migrate_session_widgets(self) -> None:
        for page in self.session.get("pages", []):
            for widget in page.get("widgets", []):
                kind = str(widget.get("kind", ""))
                if kind not in self.registry.templates:
                    continue
                template = self.registry.get(kind)
                self.conform_widget_properties(widget)
                recorded_version = int(as_float(widget.get("template_version", 0), 0))
                if recorded_version < int(template.template_version):
                    self.execute_widget_lifecycle_hook(
                        widget,
                        page,
                        "migrate",
                        event={"from_version": recorded_version, "to_version": int(template.template_version)},
                    )
                    widget["template_version"] = int(template.template_version)
                    widget["modified_at"] = now_iso()

    def normalize_z(self, page: Dict[str, Any]) -> None:
        for index, widget in enumerate(sorted(page.get("widgets", []), key=lambda w: int(w.get("z", 0)))):
            widget["z"] = index

    def bring_forward(self, widget_id: str) -> None:
        page = self.get_widget_page(widget_id)
        widget = self.get_widget(widget_id)
        if not page or not widget:
            return
        widget["z"] = int(widget.get("z", 0)) + 2
        self.normalize_z(page)
        self.touch()

    def send_backward(self, widget_id: str) -> None:
        page = self.get_widget_page(widget_id)
        widget = self.get_widget(widget_id)
        if not page or not widget:
            return
        widget["z"] = max(0, int(widget.get("z", 0)) - 2)
        self.normalize_z(page)
        self.touch()

    def validate_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(session, dict):
            raise ValueError("Session JSON root must be an object")
        session = conform_record(session, "session")
        session["schema"] = SCHEMA
        session["schema_version"] = SESSION_SCHEMA_VERSION
        if not isinstance(session.get("widget_templates"), dict) or not session["widget_templates"]:
            session["widget_templates"] = self.registry.to_session_records()
        session["plugins"] = deep_copy(session.get("plugins", {})) if isinstance(session.get("plugins"), dict) else {}
        session["export_settings"] = conform_record(merge_dicts(DEFAULT_EXPORT_SETTINGS, session.get("export_settings", {})), "export_settings")
        session["export_settings"]["pdf"] = merge_dicts(DEFAULT_EXPORT_SETTINGS.get("pdf", {}), session["export_settings"].get("pdf", {}))
        if not isinstance(session.get("pages"), list) or not session["pages"]:
            session["pages"] = [self.new_page_object("Page 1")]
        conformed_pages: List[Dict[str, Any]] = []
        for page_index, raw_page in enumerate(session["pages"], start=1):
            page = conform_record(raw_page if isinstance(raw_page, dict) else {}, "page")
            if not str(page.get("title", "")).strip():
                page["title"] = f"Page {page_index}"
            page["grid"] = merge_dicts(default_grid(), page.get("grid", {}))
            widgets: List[Dict[str, Any]] = []
            raw_widgets = page.get("widgets", []) if isinstance(page.get("widgets"), list) else []
            for widget_index, raw_widget in enumerate(raw_widgets):
                widget = conform_record(raw_widget if isinstance(raw_widget, dict) else {}, "widget")
                if not str(widget.get("name", "")).strip():
                    widget["name"] = f"Widget {widget_index + 1}"
                if not isinstance(widget.get("properties"), dict):
                    widget["properties"] = {}
                widgets.append(widget)
            page["widgets"] = widgets
            self.normalize_z(page)
            conformed_pages.append(page)
        session["pages"] = conformed_pages
        return session

    def save(self, path: Optional[str] = None) -> str:
        target = path or self.session_path
        if not target:
            raise ValueError("No session file path supplied")
        self.sync_templates_to_session(mark_dirty=False)
        self.session["modified_at"] = now_iso()
        data = json.dumps(self.session, indent=2, ensure_ascii=False)
        Path(target).write_text(data, encoding="utf-8")
        self.session_path = target
        self.dirty = False
        return target

    def load(self, path: str) -> None:
        session = json.loads(Path(path).read_text(encoding="utf-8"))
        self.session = self.validate_session(session)
        self.registry.load_session_records(self.session.get("widget_templates", {}))
        plugins = self.session.get("plugins", {}) if isinstance(self.session.get("plugins"), dict) else {}
        if isinstance(plugins.get("loaded"), list):
            self.registry.plugin_records = deep_copy(plugins.get("loaded", []))
        if isinstance(plugins.get("collisions"), list):
            self.registry.collision_events = deep_copy(plugins.get("collisions", []))
        self.migrate_session_widgets()
        self.sync_templates_to_session(mark_dirty=False)
        self.session_path = path
        self.current_page_id = self.session["pages"][0]["page_id"]
        self.dirty = False

    def export_pdf(
        self,
        path: str,
        page_ids: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        pdf_options = merge_dicts(DEFAULT_EXPORT_SETTINGS.get("pdf", {}), self.session.get("export_settings", {}).get("pdf", {}))
        pdf_options = merge_dicts(pdf_options, options or {})
        self.session.setdefault("export_settings", {})["pdf"] = deep_copy(pdf_options)
        self.touch()

        pages = self.session.get("pages", [])
        if page_ids is not None:
            wanted = set(page_ids)
            selected_pages = [page for page in pages if page.get("page_id") in wanted]
        else:
            selected_pages = list(pages)
        if not selected_pages:
            raise ValueError("No pages selected for PDF export")

        target = Path(path)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        target.parent.mkdir(parents=True, exist_ok=True)

        if pdf_options.get("one_file_per_page"):
            exported_paths: List[str] = []
            all_warnings: List[str] = []
            stem = target.stem
            for index, page in enumerate(selected_pages, start=1):
                page_stem = safe_file_stem(str(page.get("title") or f"page_{index}"), f"page_{index}")
                page_path = target.with_name(f"{stem}_{index:03d}_{page_stem}.pdf")
                result = self._export_pdf_file(str(page_path), [page], pdf_options)
                exported_paths.extend(result.get("paths", [str(page_path)]))
                all_warnings.extend(result.get("warnings", []))
            return {"paths": exported_paths, "pages": len(selected_pages), "warnings": all_warnings}

        return self._export_pdf_file(str(target), selected_pages, pdf_options)

    def _export_pdf_file(self, path: str, pages: List[Dict[str, Any]], options: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from reportlab.pdfgen import canvas as reportlab_canvas
        except Exception as exc:
            raise RuntimeError("PDF export requires ReportLab. Install it with: python -m pip install reportlab") from exc

        first_page = pages[0]
        first_size = self._pdf_page_size(first_page)
        pdf = reportlab_canvas.Canvas(path, pagesize=first_size)
        if options.get("title") or self.session.get("title"):
            pdf.setTitle(str(options.get("title") or self.session.get("title")))
        if options.get("author"):
            pdf.setAuthor(str(options.get("author")))
        warnings: List[str] = []

        for page_number, page in enumerate(pages, start=1):
            pdf.setPageSize(self._pdf_page_size(page))
            page_api = WidgetRuntimePDFAPI(
                pdf,
                self,
                page,
                {
                    "widget_id": f"page_{page_number}",
                    "x": 0,
                    "y": 0,
                    "width": page.get("width_px", A4_WIDTH_PX),
                    "height": page.get("height_px", A4_HEIGHT_PX),
                    "properties": {},
                },
                options=options,
                warnings=warnings,
            )
            page_api.draw_rectangle(
                0,
                0,
                float(page.get("width_px", A4_WIDTH_PX)),
                float(page.get("height_px", A4_HEIGHT_PX)),
                outline="",
                fill=str(page.get("background", "#ffffff")),
                width=0,
                tags="page_background",
            )

            grid = page.get("grid", {}) if isinstance(page.get("grid", {}), dict) else {}
            if bool(options.get("include_grid", True)) and grid.get("enabled"):
                step = max(4, int(as_float(grid.get("spacing", 24), 24)))
                fill = str(grid.get("fill", "#eeeeee"))
                page_api.draw_grid(step=step, fill=fill)

            if bool(options.get("include_page_titles", False)):
                page_api.draw_text(24, 24, f"{page_number}. {page.get('title', 'Page')}", font_size=14, fill="#555555")

            for widget in self.list_widgets(page.get("page_id")):
                visible = bool(widget.get("visible", True))
                if not visible and bool(options.get("exclude_hidden_widgets", True)):
                    continue
                api = WidgetRuntimePDFAPI(pdf, self, page, widget, options=options, warnings=warnings)
                if widget.get("kind") not in self.registry.templates:
                    draw_missing_widget_placeholder(api, widget)
                    warnings.append(f"{widget.get('name', widget.get('widget_id'))}: missing template kind {widget.get('kind')}")
                    continue
                try:
                    self._execute_widget_program_for_export(api, widget, page, mode="draw")
                except Exception as exc:
                    summary = f"{widget.get('name', widget.get('widget_id'))}: {exc}"
                    warnings.append(summary)
                    api.draw_rectangle(0, 0, widget.get("width", 240), widget.get("height", 100), outline="#b00020", fill="#fff5f5", width=2)
                    api.draw_text(8, 8, f"PDF export error:\n{exc}", font_size=10, fill="#b00020", width=int(widget.get("width", 240)) - 16)
                if bool(options.get("include_widget_bounds", False)):
                    api.draw_rectangle(0, 0, widget.get("width", 240), widget.get("height", 160), outline="#0b63ce", fill="", width=1, tags="widget_bounds")

            if bool(options.get("include_metadata", True)):
                metadata = f"{APP_NAME} | {self.session.get('title', 'Untitled')} | page {page_number} of {len(pages)} | exported {now_iso()}"
                page_api.draw_text(24, float(page.get("height_px", A4_HEIGHT_PX)) - 28, metadata, font_size=8, fill="#777777")

            pdf.showPage()
        pdf.save()
        return {"paths": [path], "pages": len(pages), "warnings": warnings}

    def _pdf_page_size(self, page: Dict[str, Any]) -> Tuple[float, float]:
        width_mm = as_float(page.get("width_mm", A4_WIDTH_MM), A4_WIDTH_MM)
        height_mm = as_float(page.get("height_mm", A4_HEIGHT_MM), A4_HEIGHT_MM)
        return (width_mm / MM_PER_INCH * 72, height_mm / MM_PER_INCH * 72)

    def _execute_widget_program_for_export(
        self,
        api: Any,
        widget: Dict[str, Any],
        page: Dict[str, Any],
        mode: str = "draw",
    ) -> None:
        found, _ = execute_widget_hook(api, widget, page, self.session, mode)
        if not found and mode == "draw":
            api.draw_rectangle(0, 0, widget.get("width", 160), widget.get("height", 80), outline="#aaaaaa", fill="")
            api.draw_text(8, 8, f"No draw() in {widget.get('name', 'widget')}", font_size=12, fill="#777777")


class WidgetLifecycleAPI:
    def __init__(
        self,
        kernel: WhiteboardKernel,
        page: Dict[str, Any],
        widget: Dict[str, Any],
        event: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.kernel = kernel
        self.page = page
        self.widget = widget
        self.event = event or {}
        self.messages: List[str] = []

    def describe(self, name: Optional[str] = None) -> str:
        return describe_runtime_api(name)

    def get_property(self, name: str, default: Any = None) -> Any:
        return self.widget.setdefault("properties", {}).get(name, default)

    def set_property(self, name: str, value: Any) -> None:
        properties = self.widget.setdefault("properties", {})
        old_exists = name in properties
        old_value = deep_copy(properties.get(name))
        properties[name] = value
        try:
            self.kernel.conform_widget_properties(self.widget)
        except Exception:
            if old_exists:
                properties[name] = old_value
            else:
                properties.pop(name, None)
            raise
        self.widget["modified_at"] = now_iso()
        self.kernel.touch()

    def read_page(self, page_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return deep_copy(self.kernel.get_page(page_id or self.page.get("page_id")))

    def list_pages(self) -> List[Dict[str, Any]]:
        return deep_copy(self.kernel.list_pages())

    def read_widget(self, widget_id: str) -> Optional[Dict[str, Any]]:
        widget = self.kernel.get_widget(widget_id)
        return deep_copy(widget) if widget else None

    def list_widgets(self, page_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return deep_copy(self.kernel.list_widgets(page_id or self.page.get("page_id")))

    def list_templates(self) -> Dict[str, Dict[str, Any]]:
        return deep_copy(self.kernel.list_templates())

    def read_template(self, kind: str) -> Optional[Dict[str, Any]]:
        template = self.kernel.get_template(kind)
        return deep_copy(template) if template else None

    def log(self, message: Any) -> None:
        self.messages.append(str(message))


class PageGeneratorAPI:
    def __init__(
        self,
        kernel: WhiteboardKernel,
        project_path: Optional[str] = None,
        source: str = "generator",
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.kernel = kernel
        self.project_path = str(project_path or Path.cwd())
        self.source = source
        self.logger = logger
        self.messages: List[str] = []
        self.created_pages: List[str] = []
        self.created_widgets: List[str] = []

    def describe(self, name: Optional[str] = None) -> str:
        return describe_page_generator_api(name)

    def log(self, message: Any) -> None:
        text = str(message)
        self.messages.append(text)
        if self.logger:
            self.logger(text)

    def reset_book(self, title: str = "Generated mathematics book") -> Dict[str, Any]:
        self.kernel.reset()
        self.kernel.session["title"] = str(title)
        self.kernel.session.setdefault("generators", [])
        self.kernel.touch()
        page = self.kernel.current_page()
        self.created_pages = [str(page.get("page_id"))]
        self.created_widgets = []
        self.log(f"Reset book: {title}")
        return page

    def set_title(self, title: str) -> None:
        self.kernel.session["title"] = str(title)
        self.kernel.touch()

    def new_page(
        self,
        title: Optional[str] = None,
        background: Optional[str] = None,
        grid: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        page = self.kernel.add_page(title or f"Page {len(self.kernel.session.get('pages', [])) + 1}")
        if background is not None:
            page["background"] = str(background)
        if isinstance(grid, dict):
            page["grid"] = merge_dicts(default_grid(), grid)
        self.created_pages.append(str(page.get("page_id")))
        return page

    def current_page(self) -> Dict[str, Any]:
        return self.kernel.current_page()

    def _resolve_page_id(self, page: Optional[Any] = None) -> str:
        if page is None:
            return self.kernel.current_page_id
        if isinstance(page, dict):
            return str(page.get("page_id") or self.kernel.current_page_id)
        return str(page)

    def configure_page(self, page: Optional[Any] = None, **updates: Any) -> Dict[str, Any]:
        page_id = self._resolve_page_id(page)
        target = self.kernel.get_page(page_id)
        if target is None:
            raise KeyError(f"Page not found: {page_id}")
        for key, value in updates.items():
            if key in {"page_id", "widgets"}:
                continue
            if key == "grid" and isinstance(value, dict):
                target[key] = merge_dicts(default_grid(), value)
            else:
                target[key] = deep_copy(value)
        target["modified_at"] = now_iso()
        self.kernel.touch()
        return target

    def add_widget(
        self,
        kind: str,
        x: int = 80,
        y: int = 80,
        page: Optional[Any] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        name: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        **updates: Any,
    ) -> Dict[str, Any]:
        overrides: Dict[str, Any] = {}
        if width is not None:
            overrides["width"] = int(width)
        if height is not None:
            overrides["height"] = int(height)
        if name is not None:
            overrides["name"] = str(name)
        if properties is not None:
            overrides["properties"] = deep_copy(properties)
        for key, value in updates.items():
            if value is not None:
                overrides[key] = deep_copy(value)
        widget = self.kernel.create_widget(kind, x=int(x), y=int(y), page_id=self._resolve_page_id(page), overrides=overrides)
        self.created_widgets.append(str(widget.get("widget_id")))
        return widget

    def update_widget(self, widget: Any, **updates: Any) -> bool:
        widget_id = str(widget.get("widget_id")) if isinstance(widget, dict) else str(widget)
        return self.kernel.update_widget(widget_id, updates)

    def add_text(
        self,
        text: Any,
        x: int = 80,
        y: int = 80,
        page: Optional[Any] = None,
        width: int = 520,
        height: int = 90,
        **style: Any,
    ) -> Dict[str, Any]:
        properties = {"text": str(text)}
        properties.update(style)
        return self.add_widget("text", x=x, y=y, page=page, width=width, height=height, properties=properties)

    def add_formula(
        self,
        formula: Any,
        x: int = 80,
        y: int = 80,
        page: Optional[Any] = None,
        width: int = 620,
        height: int = 90,
        **style: Any,
    ) -> Dict[str, Any]:
        properties = {"formula": str(formula)}
        properties.update(style)
        return self.add_widget("formula", x=x, y=y, page=page, width=width, height=height, properties=properties)

    def add_png(
        self, path: Any, x: int = 80, y: int = 80,
        page: Optional[Any] = None, width: int = 360, height: int = 240,
        embed: bool = True, **style: Any,
    ) -> Dict[str, Any]:
        source = Path(path).expanduser()
        if not source.is_absolute():
            source = Path(self.project_path) / source
        source = source.resolve()
        if source.suffix.lower() != ".png":
            raise ValueError("Image path must have a .png extension")
        data = base64.b64encode(source.read_bytes()).decode("ascii")
        load_png_image(data_base64=data).close()
        properties = dict(style)
        properties.update({"path": str(source), "data_base64": data if embed else ""})
        return self.add_widget("png_image", x=x, y=y, page=page, width=width, height=height, properties=properties)

    def add_wordsearch(
        self,
        title: str,
        words: Iterable[Any],
        x: int = 50,
        y: int = 55,
        page: Optional[Any] = None,
        width: int = 694,
        height: int = 1010,
        **options: Any,
    ) -> Dict[str, Any]:
        source_words = [str(word).strip() for word in words if str(word).strip()]
        data = build_wordsearch_data(
            source_words,
            size=int(options.pop("size", 20)),
            seed=options.pop("seed", None),
            max_size=options.pop("max_size", options.pop("max_grid_size", None)),
            directions=options.pop("directions", None),
            max_attempts=int(options.pop("max_attempts", 16)),
            filler_alphabet=str(options.pop("filler_alphabet", string.ascii_uppercase)),
        )
        properties = {"title": title, **data}
        properties.update(options)
        return self.add_widget("wordsearch", x=x, y=y, page=page, width=width, height=height, properties=properties)

    def add_crossword(
        self,
        title: str,
        entries: Iterable[Any],
        x: int = 55,
        y: int = 70,
        page: Optional[Any] = None,
        width: int = 690,
        height: int = 870,
        **options: Any,
    ) -> Dict[str, Any]:
        source_entries = list(entries)
        data = build_crossword_data(
            source_entries,
            size=options.pop("size", None),
            seed=options.pop("seed", None),
            max_size=options.pop("max_size", options.pop("max_grid_size", None)),
            attempts=int(options.pop("attempts", 120)),
            allow_disconnected=bool(options.pop("allow_disconnected", False)),
        )
        properties = {"title": title, **data}
        properties.update(options)
        return self.add_widget("crossword", x=x, y=y, page=page, width=width, height=height, properties=properties)

    def add_multiple_choice_quiz(
        self,
        title: str,
        questions: Iterable[Any],
        x: int = 55,
        y: int = 70,
        page: Optional[Any] = None,
        width: int = 690,
        height: int = 870,
        **options: Any,
    ) -> Dict[str, Any]:
        source_questions = list(questions)
        normalized_questions = normalize_quiz_questions(
            source_questions,
            shuffle_choices=bool(options.pop("shuffle_choices", False)),
            shuffle_questions=bool(options.pop("shuffle_questions", False)),
            seed=options.pop("seed", None),
            min_choices=int(options.pop("min_choices", 2)),
        )
        properties = {"title": title, "questions": normalized_questions, "source_questions": deep_copy(source_questions)}
        properties.update(options)
        return self.add_widget("multiple_choice_quiz", x=x, y=y, page=page, width=width, height=height, properties=properties)

    def _resolve_content_path(self, path: Any) -> Path:
        candidate = Path(str(path))
        if candidate.is_absolute():
            return candidate
        return Path(self.project_path) / candidate

    def load_lines(self, path: Any, encoding: str = "utf-8") -> List[str]:
        content_path = self._resolve_content_path(path)
        return [line.strip() for line in content_path.read_text(encoding=encoding).splitlines() if line.strip()]

    def load_sections(self, path: Any, separator: str = "...", encoding: str = "utf-8") -> List[List[str]]:
        sections: List[List[str]] = []
        current: List[str] = []
        for line in self.load_lines(path, encoding=encoding):
            if line == separator:
                if current:
                    sections.append(current)
                current = []
            else:
                current.append(line)
        if current:
            sections.append(current)
        return sections

    def load_pairs(self, path: Any, separator: str = ":", encoding: str = "utf-8") -> List[Tuple[str, str]]:
        pairs: List[Tuple[str, str]] = []
        for line in self.load_lines(path, encoding=encoding):
            if separator not in line:
                continue
            left, right = line.split(separator, 1)
            pairs.append((left.strip(), right.strip()))
        return pairs

    def wordsearch_data(self, words: Iterable[Any], size: int = 20, seed: Optional[Any] = None, **options: Any) -> Dict[str, Any]:
        return build_wordsearch_data(words, size=size, seed=seed, **options)

    def crossword_data(self, entries: Iterable[Any], size: Optional[int] = None, **options: Any) -> Dict[str, Any]:
        return build_crossword_data(entries, size=size, **options)

    def list_templates(self) -> Dict[str, Dict[str, Any]]:
        return deep_copy(self.kernel.list_templates())

    def read_template(self, kind: str) -> Optional[Dict[str, Any]]:
        template = self.kernel.get_template(kind)
        return deep_copy(template) if template else None

    def export_pdf(
        self,
        path: Any,
        page_ids: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.kernel.export_pdf(str(self._resolve_content_path(path)), page_ids=page_ids, options=options)

    def summary(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "project_path": self.project_path,
            "pages_created": len(self.created_pages),
            "widgets_created": len(self.created_widgets),
            "messages": deep_copy(self.messages),
        }


class WidgetRuntimeAPI:
    def __init__(
        self,
        app: "WhiteboardApp",
        kernel: WhiteboardKernel,
        page: Dict[str, Any],
        widget: Dict[str, Any],
        mode: str = "draw",
    ) -> None:
        self.app = app
        self.kernel = kernel
        self.page = page
        self.widget = widget
        self.mode = mode
        self.canvas = app.canvas
        self.widget_id = widget["widget_id"]
        self.origin_x = PAGE_PAD + int(widget.get("x", 0))
        self.origin_y = PAGE_PAD + int(widget.get("y", 0))

    def draw_image(
        self, x: float, y: float, path: str = "",
        width: Optional[float] = None, height: Optional[float] = None,
        fit: str = "contain", anchor: str = "center",
        data_base64: str = "", tags: str = "image",
    ) -> int:
        image = load_png_image(path, data_base64, self.kernel.session_path)
        from PIL import Image, ImageTk
        with image:
            bw = float(width if width is not None else image.width)
            bh = float(height if height is not None else image.height)
            ox, oy, dw, dh = png_image_layout(image.size, bw, bh, fit, anchor)
            if fit == "cover":
                # Crop the source before scaling: extreme aspect ratios should
                # not allocate an enormous intermediate image during dragging.
                sx, sy = image.width / dw, image.height / dh
                box = (max(0.0, -ox * sx), max(0.0, -oy * sy),
                       min(float(image.width), (bw - ox) * sx),
                       min(float(image.height), (bh - oy) * sy))
                raster = image.resize((max(1, round(bw)), max(1, round(bh))), Image.Resampling.LANCZOS, box=box)
                ox = oy = 0.0
            else:
                raster = image.resize((max(1, round(dw)), max(1, round(dh))), Image.Resampling.LANCZOS)
            with raster:
                photo = ImageTk.PhotoImage(raster, master=self.canvas)
        item = int(self.canvas.create_image(*self._xy(x + ox, y + oy), image=photo, anchor="nw", tags=self._tag(tags)))
        # Runtime API instances are temporary; Tk itself only holds the name.
        self.app._image_references.append(photo)
        return item

    def _tag(self, extra: str = "object") -> Tuple[str, str, str]:
        return ("widget", self.widget_id, extra)

    def _xy(self, x: float, y: float) -> Tuple[float, float]:
        return self.origin_x + x, self.origin_y + y

    def _coords(self, *coords: float) -> List[float]:
        result: List[float] = []
        for index, value in enumerate(coords):
            if index % 2 == 0:
                result.append(self.origin_x + value)
            else:
                result.append(self.origin_y + value)
        return result

    def describe(self, name: Optional[str] = None) -> str:
        return describe_runtime_api(name)

    def get_property(self, name: str, default: Any = None) -> Any:
        return self.widget.setdefault("properties", {}).get(name, default)

    def set_property(self, name: str, value: Any) -> None:
        properties = self.widget.setdefault("properties", {})
        old_exists = name in properties
        old_value = deep_copy(properties.get(name))
        properties[name] = value
        try:
            self.kernel.conform_widget_properties(self.widget)
        except Exception:
            if old_exists:
                properties[name] = old_value
            else:
                properties.pop(name, None)
            raise
        self.widget["modified_at"] = now_iso()
        self.kernel.touch()

    def draw_text(
        self,
        x: float,
        y: float,
        text: Any,
        font_size: int = 16,
        fill: str = "#111111",
        anchor: str = "nw",
        font_family: str = "Segoe UI",
        bold: bool = False,
        italic: bool = False,
        width: Optional[int] = None,
        tags: str = "text",
    ) -> int:
        font = (font_family, int(font_size), ("bold" if bold else "normal") + (" italic" if italic else ""))
        options: Dict[str, Any] = {
            "text": str(text),
            "fill": fill,
            "anchor": anchor,
            "font": font,
            "tags": self._tag(tags),
        }
        if width is not None:
            options["width"] = int(width)
        return int(self.canvas.create_text(*self._xy(x, y), **options))

    def draw_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        fill: str = "#111111",
        width: int = 2,
        arrow: str = "none",
        smooth: bool = False,
        tags: str = "line",
    ) -> int:
        arrow_value = tk.NONE
        if arrow == "first":
            arrow_value = tk.FIRST
        elif arrow == "last":
            arrow_value = tk.LAST
        elif arrow == "both":
            arrow_value = tk.BOTH
        return int(
            self.canvas.create_line(
                *self._coords(x1, y1, x2, y2),
                fill=fill,
                width=int(width),
                arrow=arrow_value,
                smooth=bool(smooth),
                tags=self._tag(tags),
            )
        )

    def draw_polyline(
        self,
        points: Iterable[Tuple[float, float]],
        fill: str = "#111111",
        width: int = 2,
        smooth: bool = False,
        tags: str = "polyline",
    ) -> Optional[int]:
        flat: List[float] = []
        for x, y in points:
            flat.extend(self._xy(x, y))
        if len(flat) < 4:
            return None
        return int(self.canvas.create_line(*flat, fill=fill, width=int(width), smooth=bool(smooth), tags=self._tag(tags)))

    def draw_rectangle(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        outline: str = "#111111",
        fill: str = "",
        width: int = 2,
        tags: str = "rectangle",
    ) -> int:
        return int(
            self.canvas.create_rectangle(
                *self._coords(x1, y1, x2, y2),
                outline=outline,
                fill=fill,
                width=int(width),
                tags=self._tag(tags),
            )
        )

    def draw_oval(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        outline: str = "#111111",
        fill: str = "",
        width: int = 2,
        tags: str = "oval",
    ) -> int:
        return int(
            self.canvas.create_oval(
                *self._coords(x1, y1, x2, y2),
                outline=outline,
                fill=fill,
                width=int(width),
                tags=self._tag(tags),
            )
        )

    def draw_polygon(
        self,
        points: Iterable[Tuple[float, float]],
        outline: str = "#111111",
        fill: str = "",
        width: int = 2,
        tags: str = "polygon",
    ) -> Optional[int]:
        flat: List[float] = []
        for x, y in points:
            flat.extend(self._xy(x, y))
        if len(flat) < 6:
            return None
        item = int(self.canvas.create_polygon(*flat, outline=outline, fill=fill, width=int(width), tags=self._tag(tags)))
        return item

    def draw_grid(self, step: int = 20, fill: str = "#eeeeee") -> None:
        w = int(self.widget.get("width", 100))
        h = int(self.widget.get("height", 100))
        for x in range(0, w + 1, max(1, int(step))):
            self.draw_line(x, 0, x, h, fill=fill, width=1, tags="grid")
        for y in range(0, h + 1, max(1, int(step))):
            self.draw_line(0, y, w, y, fill=fill, width=1, tags="grid")

    def draw_axes(
        self,
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        fill: str = "#777777",
        width: int = 1,
    ) -> None:
        w = float(self.widget.get("width", 100))
        h = float(self.widget.get("height", 100))
        def sx(x: float) -> float:
            return (x - xmin) / (xmax - xmin) * w
        def sy(y: float) -> float:
            return h - (y - ymin) / (ymax - ymin) * h
        if xmin <= 0 <= xmax:
            self.draw_line(sx(0), 0, sx(0), h, fill=fill, width=width, tags="axis")
        if ymin <= 0 <= ymax:
            self.draw_line(0, sy(0), w, sy(0), fill=fill, width=width, tags="axis")

    def plot_function(
        self,
        expression: str,
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        samples: int = 200,
        fill: str = "#111111",
        width: int = 2,
    ) -> None:
        samples = max(2, int(samples))
        w = float(self.widget.get("width", 100))
        h = float(self.widget.get("height", 100))
        safe_globals = {
            "__builtins__": {},
            "math": math,
            "abs": abs,
            "min": min,
            "max": max,
            "pow": pow,
            "round": round,
        }
        points: List[Tuple[float, float]] = []
        for i in range(samples):
            x = xmin + (xmax - xmin) * i / (samples - 1)
            try:
                y = eval(expression, safe_globals, {"x": x})
                y = float(y)
                if not math.isfinite(y):
                    if len(points) > 1:
                        self.draw_polyline(points, fill=fill, width=width, tags="function")
                    points = []
                    continue
                px = (x - xmin) / (xmax - xmin) * w
                py = h - (y - ymin) / (ymax - ymin) * h
                if -10_000 <= py <= 10_000:
                    points.append((px, py))
            except Exception:
                if len(points) > 1:
                    self.draw_polyline(points, fill=fill, width=width, tags="function")
                points = []
        if len(points) > 1:
            self.draw_polyline(points, fill=fill, width=width, tags="function")

    def plot_parametric(
        self,
        x_expression: str,
        y_expression: str,
        tmin: float,
        tmax: float,
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        samples: int = 240,
        fill: str = "#111111",
        width: int = 2,
    ) -> None:
        samples = max(2, int(samples))
        w = float(self.widget.get("width", 100))
        h = float(self.widget.get("height", 100))
        safe_globals = {
            "__builtins__": {},
            "math": math,
            "abs": abs,
            "min": min,
            "max": max,
            "pow": pow,
            "round": round,
        }
        points: List[Tuple[float, float]] = []
        for i in range(samples):
            t = tmin + (tmax - tmin) * i / (samples - 1)
            try:
                x = float(eval(x_expression, safe_globals, {"t": t}))
                y = float(eval(y_expression, safe_globals, {"t": t}))
                if not (math.isfinite(x) and math.isfinite(y)):
                    raise ValueError("non-finite point")
                px = (x - xmin) / (xmax - xmin) * w
                py = h - (y - ymin) / (ymax - ymin) * h
                points.append((px, py))
            except Exception:
                if len(points) > 1:
                    self.draw_polyline(points, fill=fill, width=width, tags="parametric")
                points = []
        if len(points) > 1:
            self.draw_polyline(points, fill=fill, width=width, tags="parametric")

    def plot_points(
        self,
        points: Iterable[Tuple[float, float]],
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        radius: int = 3,
        outline: str = "#111111",
        fill: str = "#111111",
    ) -> None:
        w = float(self.widget.get("width", 100))
        h = float(self.widget.get("height", 100))
        for x, y in points:
            px = (float(x) - xmin) / (xmax - xmin) * w
            py = h - (float(y) - ymin) / (ymax - ymin) * h
            self.draw_oval(px - radius, py - radius, px + radius, py + radius, outline=outline, fill=fill, width=1, tags="point")

    def draw_vector(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        fill: str = "#111111",
        width: int = 2,
        label: str = "",
    ) -> int:
        item = self.draw_line(x1, y1, x2, y2, fill=fill, width=width, arrow="last", tags="vector")
        if label:
            self.draw_text((x1 + x2) / 2 + 4, (y1 + y2) / 2 + 4, label, font_size=12, fill=fill, tags="vector_label")
        return item

    def widget_bounds(self) -> Tuple[int, int, int, int]:
        return (
            int(self.widget.get("x", 0)),
            int(self.widget.get("y", 0)),
            int(self.widget.get("width", 0)),
            int(self.widget.get("height", 0)),
        )

    def create_page(self, title: str = "New page") -> Dict[str, Any]:
        page = self.kernel.add_page(title)
        self.app.refresh_all()
        return page

    def read_page(self, page_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return deep_copy(self.kernel.get_page(page_id or self.page["page_id"]))

    def update_page(self, page_id: str, updates: Dict[str, Any]) -> bool:
        page = self.kernel.get_page(page_id)
        if page is None:
            return False
        for key, value in updates.items():
            if key in {"page_id", "widgets"}:
                continue
            page[key] = value
        page["modified_at"] = now_iso()
        self.kernel.touch()
        self.app.refresh_all()
        return True

    def delete_page(self, page_id: str) -> bool:
        ok = self.kernel.delete_page(page_id)
        self.app.refresh_all()
        return ok

    def list_pages(self) -> List[Dict[str, Any]]:
        return deep_copy(self.kernel.list_pages())

    def create_widget(
        self,
        kind: str,
        x: int = 80,
        y: int = 80,
        page_id: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        widget = self.kernel.create_widget(kind=kind, x=x, y=y, page_id=page_id or self.page["page_id"], overrides=overrides)
        self.app.refresh_all(select_widget_id=widget["widget_id"])
        return widget

    def read_widget(self, widget_id: str) -> Optional[Dict[str, Any]]:
        widget = self.kernel.get_widget(widget_id)
        return deep_copy(widget) if widget else None

    def update_widget(self, widget_id: str, updates: Dict[str, Any]) -> bool:
        ok = self.kernel.update_widget(widget_id, updates)
        self.app.refresh_all(select_widget_id=widget_id)
        return ok

    def delete_widget(self, widget_id: str) -> bool:
        ok = self.kernel.delete_widget(widget_id)
        self.app.refresh_all()
        return ok

    def list_widgets(self, page_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return deep_copy(self.kernel.list_widgets(page_id or self.page["page_id"]))

    def list_templates(self) -> Dict[str, Dict[str, Any]]:
        return deep_copy(self.kernel.list_templates())

    def read_template(self, kind: str) -> Optional[Dict[str, Any]]:
        template = self.kernel.get_template(kind)
        return deep_copy(template) if template else None

    def create_template(
        self,
        kind: str,
        name: str,
        width: int = 300,
        height: int = 180,
        properties: Optional[Dict[str, Any]] = None,
        program: str = "",
        description: str = "",
        properties_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = {
            "kind": kind,
            "name": name,
            "width": width,
            "height": height,
            "properties": properties or {},
            "properties_schema": properties_schema or {},
            "program": program,
            "description": description,
        }
        result = self.kernel.upsert_template(record, source="widget-api")
        self.app.refresh_all()
        return deep_copy(result)

    def update_template(self, kind: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = self.kernel.get_template(kind)
        if current is None:
            return None
        current.update(deep_copy(updates))
        current.setdefault("kind", kind)
        result = self.kernel.upsert_template(current, source=current.get("source", "widget-api"))
        self.app.refresh_all()
        return deep_copy(result)

    def delete_template(self, kind: str) -> bool:
        ok = self.kernel.delete_template(kind)
        self.app.refresh_all()
        return ok

    def duplicate_template(self, kind: str, new_kind: Optional[str] = None) -> Dict[str, Any]:
        result = self.kernel.duplicate_template(kind, new_kind=new_kind)
        self.app.refresh_all()
        return deep_copy(result)

    def save_session(self, path: Optional[str] = None) -> str:
        return self.kernel.save(path)

    def log(self, message: Any) -> None:
        self.app.log(str(message))


class WidgetRuntimePDFAPI:
    def __init__(
        self,
        pdf_canvas: Any,
        kernel: WhiteboardKernel,
        page: Dict[str, Any],
        widget: Dict[str, Any],
        mode: str = "draw",
        options: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None,
    ) -> None:
        self.pdf = pdf_canvas
        self.kernel = kernel
        self.page = page
        self.widget = widget
        self.mode = mode
        self.options = options or {}
        self.warnings = warnings if warnings is not None else []
        self.widget_id = str(widget.get("widget_id", "pdf_widget"))
        page_width_px = max(1.0, as_float(page.get("width_px", A4_WIDTH_PX), A4_WIDTH_PX))
        page_height_px = max(1.0, as_float(page.get("height_px", A4_HEIGHT_PX), A4_HEIGHT_PX))
        page_width_pt = as_float(page.get("width_mm", A4_WIDTH_MM), A4_WIDTH_MM) / MM_PER_INCH * 72
        page_height_pt = as_float(page.get("height_mm", A4_HEIGHT_MM), A4_HEIGHT_MM) / MM_PER_INCH * 72
        self.page_width_px = page_width_px
        self.page_height_px = page_height_px
        self.page_width_pt = page_width_pt
        self.page_height_pt = page_height_pt
        self.scale_x = page_width_pt / page_width_px
        self.scale_y = page_height_pt / page_height_px
        self.origin_x = as_float(widget.get("x", 0), 0)
        self.origin_y = as_float(widget.get("y", 0), 0)
        try:
            from reportlab.lib import colors
            from reportlab.lib.utils import simpleSplit
            self.colors = colors
            self.simple_split = simpleSplit
        except Exception:
            self.colors = None
            self.simple_split = None

    def draw_image(
        self, x: float, y: float, path: str = "",
        width: Optional[float] = None, height: Optional[float] = None,
        fit: str = "contain", anchor: str = "center",
        data_base64: str = "", tags: str = "image",
    ) -> int:
        from reportlab.lib.utils import ImageReader
        with load_png_image(path, data_base64, self.kernel.session_path) as image:
            bw = float(width if width is not None else image.width)
            bh = float(height if height is not None else image.height)
            ox, oy, dw, dh = png_image_layout(image.size, bw, bh, fit, anchor)
            self.pdf.saveState()
            try:
                if fit == "cover":
                    clip = self.pdf.beginPath()
                    cx, cy = self._xy(x, y + bh)
                    clip.rect(cx, cy, bw * self.scale_x, bh * self.scale_y)
                    self.pdf.clipPath(clip, stroke=0, fill=0)
                px, py = self._xy(x + ox, y + oy + dh)
                self.pdf.drawImage(ImageReader(image), px, py,
                                   width=dw * self.scale_x, height=dh * self.scale_y,
                                   mask="auto")
            finally:
                self.pdf.restoreState()
        return 0

    def _absolute(self, x: float, y: float) -> Tuple[float, float]:
        return self.origin_x + float(x), self.origin_y + float(y)

    def _pdf_point(self, x: float, y: float) -> Tuple[float, float]:
        px = float(x) * self.scale_x
        py = self.page_height_pt - float(y) * self.scale_y
        return px, py

    def _xy(self, x: float, y: float) -> Tuple[float, float]:
        return self._pdf_point(*self._absolute(x, y))

    def _coords(self, *coords: float) -> List[float]:
        result: List[float] = []
        for index in range(0, len(coords), 2):
            x, y = self._xy(coords[index], coords[index + 1])
            result.extend([x, y])
        return result

    def _avg_scale(self) -> float:
        return (self.scale_x + self.scale_y) / 2

    def _line_width(self, width: float) -> float:
        if float(width) <= 0:
            return 0
        return max(0.1, float(width) * self._avg_scale())

    def _color(self, value: str, fallback: str = "#111111") -> Any:
        if value is None or str(value) == "":
            return None
        text = str(value)
        try:
            if self.colors is not None:
                return self.colors.toColor(text)
        except Exception:
            pass
        try:
            if self.colors is not None:
                return self.colors.toColor(fallback)
        except Exception:
            return None
        return None

    def _set_pen(self, fill: str = "#111111", width: float = 1) -> None:
        color = self._color(fill)
        if color is not None:
            self.pdf.setStrokeColor(color)
        self.pdf.setLineWidth(self._line_width(width))

    def _set_fill(self, fill: str = "#111111") -> None:
        color = self._color(fill)
        if color is not None:
            self.pdf.setFillColor(color)

    def _font_name(self, bold: bool = False, italic: bool = False) -> str:
        if bold and italic:
            return "Helvetica-BoldOblique"
        if bold:
            return "Helvetica-Bold"
        if italic:
            return "Helvetica-Oblique"
        return "Helvetica"

    def describe(self, name: Optional[str] = None) -> str:
        return describe_runtime_api(name)

    def get_property(self, name: str, default: Any = None) -> Any:
        return self.widget.setdefault("properties", {}).get(name, default)

    def set_property(self, name: str, value: Any) -> None:
        properties = self.widget.setdefault("properties", {})
        old_exists = name in properties
        old_value = deep_copy(properties.get(name))
        properties[name] = value
        try:
            self.kernel.conform_widget_properties(self.widget)
        except Exception:
            if old_exists:
                properties[name] = old_value
            else:
                properties.pop(name, None)
            raise
        self.widget["modified_at"] = now_iso()
        self.kernel.touch()

    def draw_text(
        self,
        x: float,
        y: float,
        text: Any,
        font_size: int = 16,
        fill: str = "#111111",
        anchor: str = "nw",
        font_family: str = "Helvetica",
        bold: bool = False,
        italic: bool = False,
        width: Optional[int] = None,
        tags: str = "text",
    ) -> int:
        del font_family, tags
        value = str(text)
        font_name = self._font_name(bold=bold, italic=italic)
        font_size_pt = max(1.0, float(font_size))
        self._set_fill(fill)
        self.pdf.setFont(font_name, font_size_pt)
        x_pt, y_top_pt = self._xy(x, y)
        max_width_pt = None if width is None else max(6.0, float(width) * self.scale_x)
        lines: List[str] = []
        for raw_line in value.splitlines() or [""]:
            if max_width_pt and self.simple_split is not None:
                wrapped = self.simple_split(raw_line, font_name, font_size_pt, max_width_pt)
                lines.extend(wrapped if wrapped else [""])
            else:
                lines.append(raw_line)
        line_height = font_size_pt * 1.18
        anchor = str(anchor or "nw").lower()
        for index, line in enumerate(lines):
            y_baseline = y_top_pt - font_size_pt - index * line_height
            line_width = self.pdf.stringWidth(line, font_name, font_size_pt)
            draw_x = x_pt
            if anchor in {"n", "s", "center", "c"} or anchor.endswith("center"):
                draw_x = x_pt - line_width / 2
            elif "e" in anchor:
                draw_x = x_pt - line_width
            self.pdf.drawString(draw_x, y_baseline, line)
        return 0

    def draw_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        fill: str = "#111111",
        width: int = 2,
        arrow: str = "none",
        smooth: bool = False,
        tags: str = "line",
    ) -> int:
        del smooth, tags
        self._set_pen(fill, width)
        x1p, y1p = self._xy(x1, y1)
        x2p, y2p = self._xy(x2, y2)
        self.pdf.line(x1p, y1p, x2p, y2p)
        arrow = str(arrow or "none").lower()
        if arrow in {"last", "both"}:
            self._draw_arrowhead(x1p, y1p, x2p, y2p, fill, width)
        if arrow in {"first", "both"}:
            self._draw_arrowhead(x2p, y2p, x1p, y1p, fill, width)
        return 0

    def _draw_arrowhead(self, x1: float, y1: float, x2: float, y2: float, fill: str, width: float) -> None:
        angle = math.atan2(y2 - y1, x2 - x1)
        length = 8 + max(0, float(width)) * 2
        spread = math.radians(24)
        p1 = (x2 - length * math.cos(angle - spread), y2 - length * math.sin(angle - spread))
        p2 = (x2 - length * math.cos(angle + spread), y2 - length * math.sin(angle + spread))
        color = self._color(fill)
        if color is not None:
            self.pdf.setFillColor(color)
            self.pdf.setStrokeColor(color)
        path = self.pdf.beginPath()
        path.moveTo(x2, y2)
        path.lineTo(p1[0], p1[1])
        path.lineTo(p2[0], p2[1])
        path.close()
        self.pdf.drawPath(path, stroke=0, fill=1)

    def draw_polyline(
        self,
        points: Iterable[Tuple[float, float]],
        fill: str = "#111111",
        width: int = 2,
        smooth: bool = False,
        tags: str = "polyline",
    ) -> Optional[int]:
        del smooth, tags
        converted = [self._xy(x, y) for x, y in points]
        if len(converted) < 2:
            return None
        self._set_pen(fill, width)
        path = self.pdf.beginPath()
        path.moveTo(converted[0][0], converted[0][1])
        for x, y in converted[1:]:
            path.lineTo(x, y)
        self.pdf.drawPath(path, stroke=1, fill=0)
        return 0

    def draw_rectangle(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        outline: str = "#111111",
        fill: str = "",
        width: int = 2,
        tags: str = "rectangle",
    ) -> int:
        del tags
        x1p, y1p = self._xy(x1, y1)
        x2p, y2p = self._xy(x2, y2)
        left = min(x1p, x2p)
        bottom = min(y1p, y2p)
        rect_w = abs(x2p - x1p)
        rect_h = abs(y2p - y1p)
        stroke = 1 if outline else 0
        do_fill = 1 if fill else 0
        if outline:
            self._set_pen(outline, width)
        if fill:
            self._set_fill(fill)
        self.pdf.rect(left, bottom, rect_w, rect_h, stroke=stroke, fill=do_fill)
        return 0

    def draw_oval(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        outline: str = "#111111",
        fill: str = "",
        width: int = 2,
        tags: str = "oval",
    ) -> int:
        del tags
        x1p, y1p = self._xy(x1, y1)
        x2p, y2p = self._xy(x2, y2)
        left = min(x1p, x2p)
        bottom = min(y1p, y2p)
        oval_w = abs(x2p - x1p)
        oval_h = abs(y2p - y1p)
        stroke = 1 if outline else 0
        do_fill = 1 if fill else 0
        if outline:
            self._set_pen(outline, width)
        if fill:
            self._set_fill(fill)
        self.pdf.ellipse(left, bottom, left + oval_w, bottom + oval_h, stroke=stroke, fill=do_fill)
        return 0

    def draw_polygon(
        self,
        points: Iterable[Tuple[float, float]],
        outline: str = "#111111",
        fill: str = "",
        width: int = 2,
        tags: str = "polygon",
    ) -> Optional[int]:
        del tags
        converted = [self._xy(x, y) for x, y in points]
        if len(converted) < 3:
            return None
        if outline:
            self._set_pen(outline, width)
        if fill:
            self._set_fill(fill)
        path = self.pdf.beginPath()
        path.moveTo(converted[0][0], converted[0][1])
        for x, y in converted[1:]:
            path.lineTo(x, y)
        path.close()
        self.pdf.drawPath(path, stroke=1 if outline else 0, fill=1 if fill else 0)
        return 0

    def draw_grid(self, step: int = 20, fill: str = "#eeeeee") -> None:
        w = int(self.widget.get("width", self.page.get("width_px", A4_WIDTH_PX)))
        h = int(self.widget.get("height", self.page.get("height_px", A4_HEIGHT_PX)))
        for x in range(0, w + 1, max(1, int(step))):
            self.draw_line(x, 0, x, h, fill=fill, width=1, tags="grid")
        for y in range(0, h + 1, max(1, int(step))):
            self.draw_line(0, y, w, y, fill=fill, width=1, tags="grid")

    def draw_axes(
        self,
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        fill: str = "#777777",
        width: int = 1,
    ) -> None:
        w = float(self.widget.get("width", 100))
        h = float(self.widget.get("height", 100))
        def sx(x: float) -> float:
            return (x - xmin) / (xmax - xmin) * w
        def sy(y: float) -> float:
            return h - (y - ymin) / (ymax - ymin) * h
        if xmin <= 0 <= xmax:
            self.draw_line(sx(0), 0, sx(0), h, fill=fill, width=width, tags="axis")
        if ymin <= 0 <= ymax:
            self.draw_line(0, sy(0), w, sy(0), fill=fill, width=width, tags="axis")

    def plot_function(
        self,
        expression: str,
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        samples: int = 200,
        fill: str = "#111111",
        width: int = 2,
    ) -> None:
        samples = max(2, int(samples))
        w = float(self.widget.get("width", 100))
        h = float(self.widget.get("height", 100))
        safe_globals = {"__builtins__": {}, "math": math, "abs": abs, "min": min, "max": max, "pow": pow, "round": round}
        points: List[Tuple[float, float]] = []
        for i in range(samples):
            x = xmin + (xmax - xmin) * i / (samples - 1)
            try:
                y = eval(expression, safe_globals, {"x": x})
                y = float(y)
                if not math.isfinite(y):
                    if len(points) > 1:
                        self.draw_polyline(points, fill=fill, width=width, tags="function")
                    points = []
                    continue
                px = (x - xmin) / (xmax - xmin) * w
                py = h - (y - ymin) / (ymax - ymin) * h
                if -10_000 <= py <= 10_000:
                    points.append((px, py))
            except Exception:
                if len(points) > 1:
                    self.draw_polyline(points, fill=fill, width=width, tags="function")
                points = []
        if len(points) > 1:
            self.draw_polyline(points, fill=fill, width=width, tags="function")

    def plot_parametric(
        self,
        x_expression: str,
        y_expression: str,
        tmin: float,
        tmax: float,
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        samples: int = 240,
        fill: str = "#111111",
        width: int = 2,
    ) -> None:
        samples = max(2, int(samples))
        w = float(self.widget.get("width", 100))
        h = float(self.widget.get("height", 100))
        safe_globals = {"__builtins__": {}, "math": math, "abs": abs, "min": min, "max": max, "pow": pow, "round": round}
        points: List[Tuple[float, float]] = []
        for i in range(samples):
            t = tmin + (tmax - tmin) * i / (samples - 1)
            try:
                x = float(eval(x_expression, safe_globals, {"t": t}))
                y = float(eval(y_expression, safe_globals, {"t": t}))
                if not (math.isfinite(x) and math.isfinite(y)):
                    raise ValueError("non-finite point")
                px = (x - xmin) / (xmax - xmin) * w
                py = h - (y - ymin) / (ymax - ymin) * h
                points.append((px, py))
            except Exception:
                if len(points) > 1:
                    self.draw_polyline(points, fill=fill, width=width, tags="parametric")
                points = []
        if len(points) > 1:
            self.draw_polyline(points, fill=fill, width=width, tags="parametric")

    def plot_points(
        self,
        points: Iterable[Tuple[float, float]],
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        radius: int = 3,
        outline: str = "#111111",
        fill: str = "#111111",
    ) -> None:
        w = float(self.widget.get("width", 100))
        h = float(self.widget.get("height", 100))
        for x, y in points:
            px = (float(x) - xmin) / (xmax - xmin) * w
            py = h - (float(y) - ymin) / (ymax - ymin) * h
            self.draw_oval(px - radius, py - radius, px + radius, py + radius, outline=outline, fill=fill, width=1, tags="point")

    def draw_vector(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        fill: str = "#111111",
        width: int = 2,
        label: str = "",
    ) -> int:
        self.draw_line(x1, y1, x2, y2, fill=fill, width=width, arrow="last", tags="vector")
        if label:
            self.draw_text((x1 + x2) / 2 + 4, (y1 + y2) / 2 + 4, label, font_size=12, fill=fill, tags="vector_label")
        return 0

    def widget_bounds(self) -> Tuple[int, int, int, int]:
        return (
            int(self.widget.get("x", 0)),
            int(self.widget.get("y", 0)),
            int(self.widget.get("width", 0)),
            int(self.widget.get("height", 0)),
        )

    def _read_only(self, method: str) -> None:
        self.warnings.append(f"PDF export ignored mutating API call: {method}")

    def create_page(self, title: str = "New page") -> Dict[str, Any]:
        self._read_only("create_page")
        return {}

    def read_page(self, page_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return deep_copy(self.kernel.get_page(page_id or self.page.get("page_id")))

    def update_page(self, page_id: str, updates: Dict[str, Any]) -> bool:
        del page_id, updates
        self._read_only("update_page")
        return False

    def delete_page(self, page_id: str) -> bool:
        del page_id
        self._read_only("delete_page")
        return False

    def list_pages(self) -> List[Dict[str, Any]]:
        return deep_copy(self.kernel.list_pages())

    def create_widget(self, kind: str, x: int = 80, y: int = 80, page_id: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        del kind, x, y, page_id, overrides
        self._read_only("create_widget")
        return {}

    def read_widget(self, widget_id: str) -> Optional[Dict[str, Any]]:
        widget = self.kernel.get_widget(widget_id)
        return deep_copy(widget) if widget else None

    def update_widget(self, widget_id: str, updates: Dict[str, Any]) -> bool:
        del widget_id, updates
        self._read_only("update_widget")
        return False

    def delete_widget(self, widget_id: str) -> bool:
        del widget_id
        self._read_only("delete_widget")
        return False

    def list_widgets(self, page_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return deep_copy(self.kernel.list_widgets(page_id or self.page.get("page_id")))

    def list_templates(self) -> Dict[str, Dict[str, Any]]:
        return deep_copy(self.kernel.list_templates())

    def read_template(self, kind: str) -> Optional[Dict[str, Any]]:
        template = self.kernel.get_template(kind)
        return deep_copy(template) if template else None

    def create_template(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        del args, kwargs
        self._read_only("create_template")
        return {}

    def update_template(self, kind: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        del kind, updates
        self._read_only("update_template")
        return None

    def delete_template(self, kind: str) -> bool:
        del kind
        self._read_only("delete_template")
        return False

    def duplicate_template(self, kind: str, new_kind: Optional[str] = None) -> Dict[str, Any]:
        del kind, new_kind
        self._read_only("duplicate_template")
        return {}

    def save_session(self, path: Optional[str] = None) -> str:
        del path
        self._read_only("save_session")
        return ""

    def log(self, message: Any) -> None:
        self.warnings.append(str(message))


def execute_page_generator_program(program: str, api: PageGeneratorAPI) -> Any:
    text = str(program or "")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    filename = f"<page-generator {text_slug(api.source, 'generator')} {digest[:12]}>"
    env: Dict[str, Any] = {
        "__builtins__": __builtins__,
        "api": api,
        "project_path": api.project_path,
        "Path": Path,
        "datetime": _dt,
        "json": json,
        "math": math,
        "random": random,
        "re": re,
        "build_wordsearch_data": build_wordsearch_data,
        "build_crossword_data": build_crossword_data,
        "normalize_quiz_questions": normalize_quiz_questions,
    }
    exec(compile(text, filename, "exec"), env, env)
    target = env.get("generate")
    if callable(target):
        try:
            signature = inspect.signature(target)
            parameters = list(signature.parameters.values())
        except Exception:
            parameters = []
        if not parameters:
            return target()
        first_name = parameters[0].name.lower()
        if len(parameters) == 1:
            if first_name in {"project_path", "project", "path", "root"}:
                return target(api.project_path)
            return target(api)
        return target(api, api.project_path)
    return None


def describe_page_generator_api(name: Optional[str] = None) -> str:
    if name:
        if name not in PAGE_GENERATOR_API_METHOD_DOCS:
            names = ", ".join(PAGE_GENERATOR_API_PROTOCOL_METHODS)
            return f"Unknown page-generator API method {name!r}. Available methods: {names}"
        return plugin_reference_for_method(name, PAGE_GENERATOR_API_METHOD_DOCS, PageGeneratorAPI)
    return generate_page_generator_reference_markdown()


def describe_runtime_api(name: Optional[str] = None) -> str:
    if name:
        if name not in RUNTIME_API_METHOD_DOCS:
            names = ", ".join(RUNTIME_API_PROTOCOL_METHODS)
            return f"Unknown runtime API method {name!r}. Available methods: {names}"
        return plugin_reference_for_method(name, RUNTIME_API_METHOD_DOCS, WidgetRuntimeAPI)
    return generate_plugin_reference_markdown()


def describe_registration_api(name: Optional[str] = None) -> str:
    if name:
        if name not in REGISTRATION_API_METHOD_DOCS:
            names = ", ".join(REGISTRATION_API_PROTOCOL_METHODS)
            return f"Unknown registration API method {name!r}. Available methods: {names}"
        return plugin_reference_for_method(name, REGISTRATION_API_METHOD_DOCS, PluginRegistrationAPI)
    return generate_plugin_reference_markdown()


def install_api_docstrings() -> None:
    for cls in (WidgetRuntimeAPI, WidgetRuntimePDFAPI):
        for name, doc in RUNTIME_API_METHOD_DOCS.items():
            method = getattr(cls, name, None)
            if method is not None:
                method.__doc__ = doc
    for name, doc in REGISTRATION_API_METHOD_DOCS.items():
        method = getattr(PluginRegistrationAPI, name, None)
        if method is not None:
            method.__doc__ = doc
    for name, doc in PAGE_GENERATOR_API_METHOD_DOCS.items():
        method = getattr(PageGeneratorAPI, name, None)
        if method is not None:
            method.__doc__ = doc


def assert_runtime_api_protocol() -> None:
    missing: List[str] = []
    for cls in (WidgetRuntimeAPI, WidgetRuntimePDFAPI):
        for name in RUNTIME_API_PROTOCOL_METHODS:
            if not callable(getattr(cls, name, None)):
                missing.append(f"{cls.__name__}.{name}")
    for name in REGISTRATION_API_PROTOCOL_METHODS:
        if not callable(getattr(PluginRegistrationAPI, name, None)):
            missing.append(f"PluginRegistrationAPI.{name}")
    for name in PAGE_GENERATOR_API_PROTOCOL_METHODS:
        if not callable(getattr(PageGeneratorAPI, name, None)):
            missing.append(f"PageGeneratorAPI.{name}")
    if missing:
        raise RuntimeError("Runtime API protocol mismatch: " + ", ".join(missing))


def generate_plugin_reference_markdown() -> str:
    lines = [
        f"# {APP_NAME} Plugin Author Reference",
        "",
        f"Plugin API version: `{PLUGIN_API_VERSION}`",
        f"Session schema: `{SCHEMA}` version `{SESSION_SCHEMA_VERSION}`",
        "",
        "## Plugin Manifest",
        "",
        "Plugins may define `MANIFEST` or a `manifest()` function. Supported fields are `id`, `version`, `author`, and `requires_api`.",
        "A plugin kind without a colon is registered as `manifest_id:kind`, which prevents collisions with built-ins and other plugins.",
        "",
        "```python",
        "MANIFEST = {",
        '    "id": "vectors",',
        '    "version": "1.0.0",',
        '    "author": "Ada",',
        f'    "requires_api": ">={PLUGIN_API_VERSION},<2.0.0",',
        "}",
        "```",
        "",
        "## Lifecycle Hooks",
        "",
        "Widget programs may define these hook functions, each with `hook(api, widget, page, session)`:",
        "",
    ]
    for hook in WIDGET_HOOKS:
        lines.append(f"- `{hook}`")
    lines.extend([
        "",
        "`draw` renders. `action` runs on demand. `on_create`, `on_resize`, `validate`, and `migrate` run from kernel mutation paths.",
        "`validate` may return `False` or an error string to reject an update. `migrate` runs when a widget record trails its template version.",
        "",
        "## Property Schema Descriptors",
        "",
        "Template `properties_schema` is a mapping from property name to descriptor. Descriptors support `type`, `default`, `min`, `max`, `choices` or `enum`, and `description`.",
        "Valid types are `string`, `integer`, `number`, `boolean`, `object`, `array`, and `any`. Unknown properties are preserved for backwards compatibility.",
        "",
        "## Registration API",
        "",
    ])
    for name in REGISTRATION_API_PROTOCOL_METHODS:
        lines.append(plugin_reference_for_method(name, REGISTRATION_API_METHOD_DOCS, PluginRegistrationAPI))
    lines.extend(["", "## Runtime Drawing and CRUD API", ""])
    for name in RUNTIME_API_PROTOCOL_METHODS:
        lines.append(plugin_reference_for_method(name, RUNTIME_API_METHOD_DOCS, WidgetRuntimeAPI))
    lines.extend([
        "",
        "## Record Schemas",
        "",
    ])
    for record_name, schema in RECORD_SCHEMAS.items():
        fields = ", ".join(f"`{field}`" for field in schema)
        lines.append(f"- `{record_name}`: {fields}")
    return "\n".join(lines).strip() + "\n"


def generate_page_generator_reference_markdown() -> str:
    lines = [
        f"# {APP_NAME} Page Generator Reference",
        "",
        f"Page generator API version: `{PAGE_GENERATOR_API_VERSION}`",
        "",
        "Generator scripts run inside the app and mutate the JSON session through `api`. They can create pages, place any existing or plugin widget, and use convenience builders for word searches, crosswords, and multiple-choice quizzes.",
        "",
        "Supported `generate` shapes:",
        "",
        "```python",
        "def generate(api):",
        "    api.reset_book('Puzzle Book')",
        "```",
        "",
        "```python",
        "def generate(project_path):",
        "    api.reset_book('Puzzle Book')  # global api is also available",
        "```",
        "",
        "Top-level scripts may also call `api` directly.",
        "",
        "## Methods",
        "",
    ]
    for name in PAGE_GENERATOR_API_PROTOCOL_METHODS:
        lines.append(plugin_reference_for_method(name, PAGE_GENERATOR_API_METHOD_DOCS, PageGeneratorAPI))
    lines.extend([
        "",
        "## Widget Control",
        "",
        "`api.add_widget(kind, ...)` is the universal escape hatch. Pass `properties={...}` for any built-in, plugin, or session template. Convenience methods only prepare common records.",
        "",
        "## Content File Pattern",
        "",
        "`api.load_lines`, `api.load_sections`, and `api.load_pairs` resolve paths relative to the generator script directory, matching the project/content style used by external book generators.",
    ])
    return "\n".join(lines).strip() + "\n"


install_api_docstrings()
assert_runtime_api_protocol()


class WhiteboardApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.kernel = WhiteboardKernel()
        self.title(APP_NAME)
        self.geometry("1360x860")
        self.minsize(1050, 720)
        self.selected_widget_id: Optional[str] = None
        self.drag_start: Optional[Tuple[float, float]] = None
        self.resize_start: Optional[Tuple[float, float, float, float]] = None
        self._loading_inspector = False
        self._image_references: List[Any] = []
        self._build_ui()
        self._bind_shortcuts()
        self.refresh_all()

    def _build_ui(self) -> None:
        self._build_menu()
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self.toolbar = ttk.Frame(self)
        self.toolbar.grid(row=0, column=0, columnspan=3, sticky="ew")
        self._build_toolbar(self.toolbar)

        self.left = ttk.Frame(self, padding=6)
        self.left.grid(row=1, column=0, sticky="ns")
        self.left.rowconfigure(1, weight=1)
        self.left.rowconfigure(4, weight=1)

        ttk.Label(self.left, text="Pages").grid(row=0, column=0, sticky="w")
        self.pages_list = tk.Listbox(self.left, width=24, height=10, exportselection=False)
        self.pages_list.grid(row=1, column=0, sticky="nsew")
        self.pages_list.bind("<<ListboxSelect>>", self.on_page_select)

        page_buttons = ttk.Frame(self.left)
        page_buttons.grid(row=2, column=0, sticky="ew", pady=(4, 10))
        ttk.Button(page_buttons, text="Add", command=self.add_page).pack(side="left", fill="x", expand=True)
        ttk.Button(page_buttons, text="Copy", command=self.duplicate_page).pack(side="left", fill="x", expand=True)
        ttk.Button(page_buttons, text="Delete", command=self.delete_page).pack(side="left", fill="x", expand=True)

        ttk.Label(self.left, text="Widgets").grid(row=3, column=0, sticky="w")
        self.widgets_list = tk.Listbox(self.left, width=24, height=16, exportselection=False)
        self.widgets_list.grid(row=4, column=0, sticky="nsew")
        self.widgets_list.bind("<<ListboxSelect>>", self.on_widget_list_select)

        widget_buttons = ttk.Frame(self.left)
        widget_buttons.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(widget_buttons, text="Copy", command=self.duplicate_widget).pack(side="left", fill="x", expand=True)
        ttk.Button(widget_buttons, text="Delete", command=self.delete_widget).pack(side="left", fill="x", expand=True)

        self.center = ttk.Frame(self)
        self.center.grid(row=1, column=1, sticky="nsew")
        self.center.rowconfigure(0, weight=1)
        self.center.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.center, bg="#cfcfcf", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scroll = ttk.Scrollbar(self.center, orient="vertical", command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(self.center, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)

        self.right = ttk.Frame(self, padding=6)
        self.right.grid(row=1, column=2, sticky="nsew")
        self.right.rowconfigure(13, weight=1)
        self.right.rowconfigure(16, weight=2)
        self.right.columnconfigure(1, weight=1)

        self._build_inspector(self.right)

        self.status = ttk.Label(self, text="Ready", anchor="w")
        self.status.grid(row=2, column=0, columnspan=3, sticky="ew")

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="New Session", command=self.new_session, accelerator="Ctrl+N")
        file_menu.add_command(label="Open Session...", command=self.open_session, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_session, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self.save_session_as, accelerator="Ctrl+Shift+S")
        file_menu.add_command(label="Export PDF...", command=self.export_pdf_dialog, accelerator="Ctrl+E")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menu.add_cascade(label="File", menu=file_menu)

        page_menu = tk.Menu(menu, tearoff=False)
        page_menu.add_command(label="Add Page", command=self.add_page)
        page_menu.add_command(label="Duplicate Page", command=self.duplicate_page)
        page_menu.add_command(label="Rename Page", command=self.rename_page)
        page_menu.add_command(label="Configure Page JSON", command=self.configure_page)
        page_menu.add_command(label="Delete Page", command=self.delete_page)
        menu.add_cascade(label="Page", menu=page_menu)

        widget_menu = tk.Menu(menu, tearoff=False)
        widget_menu.add_command(label="Add Widget...", command=self.add_widget_dialog)
        widget_menu.add_command(label="Add PNG Image...", command=self.add_png_image)
        widget_menu.add_command(label="Replace Selected PNG Image...", command=self.replace_png_image)
        widget_menu.add_command(label="Duplicate Widget", command=self.duplicate_widget)
        widget_menu.add_command(label="Delete Widget", command=self.delete_widget)
        widget_menu.add_separator()
        widget_menu.add_command(label="Bring Forward", command=self.bring_widget_forward)
        widget_menu.add_command(label="Send Backward", command=self.send_widget_backward)
        widget_menu.add_separator()
        widget_menu.add_command(label="Run Selected Action", command=self.run_selected_widget_action)
        widget_menu.add_command(label="Run All Actions", command=self.run_all_widget_actions)
        menu.add_cascade(label="Widget", menu=widget_menu)

        plugin_menu = tk.Menu(menu, tearoff=False)
        plugin_menu.add_command(label="Template Manager...", command=self.manage_templates)
        plugin_menu.add_command(label="Load Plugin Directory...", command=self.load_plugins)
        plugin_menu.add_command(label="Show Plugin Template", command=self.show_plugin_template)
        menu.add_cascade(label="Plugins", menu=plugin_menu)

        generator_menu = tk.Menu(menu, tearoff=False)
        generator_menu.add_command(label="Run Generator Script...", command=self.run_generator_script)
        generator_menu.add_command(label="Show Generator Template", command=self.show_generator_template)
        generator_menu.add_command(label="Page Generator Reference", command=self.show_generator_reference)
        generator_menu.add_command(label="Export Generator Reference Markdown...", command=self.export_generator_reference)
        menu.add_cascade(label="Generators", menu=generator_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Session Contract", command=self.show_contract)
        help_menu.add_command(label="Plugin Author Reference", command=self.show_plugin_reference)
        help_menu.add_command(label="Export Plugin Reference Markdown...", command=self.export_plugin_reference)
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo(APP_NAME, "A4 JSON-persistent programmable mathematics whiteboard."))
        menu.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menu)

    def _build_toolbar(self, parent: ttk.Frame) -> None:
        for text, command in [
            ("New", self.new_session),
            ("Open", self.open_session),
            ("Save", self.save_session),
            ("Page+", self.add_page),
            ("Widget+", self.add_widget_dialog),
            ("Templates", self.manage_templates),
            ("PDF", self.export_pdf_dialog),
            ("Generator", self.run_generator_script),
            ("Page JSON", self.configure_page),
            ("Text", lambda: self.add_widget_kind("text")),
            ("Formula", lambda: self.add_widget_kind("formula")),
            ("Graph", lambda: self.add_widget_kind("graph2d")),
            ("3D", lambda: self.add_widget_kind("3Dplot")),
            ("Code", lambda: self.add_widget_kind("code-block")),
            ("Table", lambda: self.add_widget_kind("table")),
            ("Run", self.run_selected_widget_action),
            ("Apply Inspector", self.apply_inspector),
        ]:
            ttk.Button(parent, text=text, command=command).pack(side="left", padx=2, pady=3)

    def _build_inspector(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Widget Inspector").grid(row=0, column=0, columnspan=2, sticky="w")
        self.id_value = ttk.Label(parent, text="No widget selected", width=36)
        self.id_value.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        self.name_var = tk.StringVar()
        self.kind_var = tk.StringVar()
        self.x_var = tk.StringVar()
        self.y_var = tk.StringVar()
        self.w_var = tk.StringVar()
        self.h_var = tk.StringVar()
        self.visible_var = tk.BooleanVar(value=True)
        self.locked_var = tk.BooleanVar(value=False)

        rows = [
            ("Name", self.name_var),
            ("Kind", self.kind_var),
            ("X", self.x_var),
            ("Y", self.y_var),
            ("Width", self.w_var),
            ("Height", self.h_var),
        ]
        for i, (label, var) in enumerate(rows, start=2):
            ttk.Label(parent, text=label).grid(row=i, column=0, sticky="w")
            ttk.Entry(parent, textvariable=var).grid(row=i, column=1, sticky="ew")

        ttk.Checkbutton(parent, text="Visible", variable=self.visible_var).grid(row=8, column=0, sticky="w")
        ttk.Checkbutton(parent, text="Locked", variable=self.locked_var).grid(row=8, column=1, sticky="w")

        ttk.Label(parent, text="Properties JSON").grid(row=9, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.properties_text = tk.Text(parent, width=46, height=8, undo=True, wrap="none")
        self.properties_text.grid(row=10, column=0, columnspan=2, sticky="nsew")

        ttk.Label(parent, text="Widget Python Program").grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(parent, text="Define draw(api, widget, page, session) and optional action(...).", foreground="#555555").grid(row=12, column=0, columnspan=2, sticky="w")
        self.program_text = tk.Text(parent, width=46, height=18, undo=True, wrap="none")
        self.program_text.grid(row=13, column=0, columnspan=2, sticky="nsew")

        inspector_buttons = ttk.Frame(parent)
        inspector_buttons.grid(row=14, column=0, columnspan=2, sticky="ew", pady=(6, 6))
        ttk.Button(inspector_buttons, text="Apply", command=self.apply_inspector).pack(side="left", fill="x", expand=True)
        ttk.Button(inspector_buttons, text="Run Action", command=self.run_selected_widget_action).pack(side="left", fill="x", expand=True)
        ttk.Button(inspector_buttons, text="Revert", command=self.load_selected_into_inspector).pack(side="left", fill="x", expand=True)

        ttk.Label(parent, text="Runtime Log").grid(row=15, column=0, columnspan=2, sticky="w")
        self.log_text = tk.Text(parent, width=46, height=8, state="disabled", wrap="word")
        self.log_text.grid(row=16, column=0, columnspan=2, sticky="nsew")

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-n>", lambda e: self.new_session())
        self.bind("<Control-o>", lambda e: self.open_session())
        self.bind("<Control-s>", lambda e: self.save_session())
        self.bind("<Control-S>", lambda e: self.save_session_as())
        self.bind("<Control-e>", lambda e: self.export_pdf_dialog())
        self.bind("<Delete>", lambda e: self.delete_widget())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def log(self, message: str) -> None:
        timestamp = _dt.datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.status.configure(text=message[:180])

    def refresh_all(self, select_widget_id: Optional[str] = None) -> None:
        if select_widget_id is not None:
            self.selected_widget_id = select_widget_id
        self.refresh_pages_list()
        self.refresh_widgets_list()
        self.render_page()
        self.load_selected_into_inspector()
        self.update_title()

    def update_title(self) -> None:
        path = self.kernel.session_path or "Untitled"
        dirty = "*" if self.kernel.dirty else ""
        self.title(f"{APP_NAME} - {Path(path).name}{dirty}")

    def refresh_pages_list(self) -> None:
        self.pages_list.delete(0, "end")
        current = self.kernel.current_page_id
        for index, page in enumerate(self.kernel.list_pages(), start=1):
            self.pages_list.insert("end", f"{index}. {page.get('title', 'Page')}")
            if page.get("page_id") == current:
                self.pages_list.selection_set(index - 1)
                self.pages_list.see(index - 1)

    def refresh_widgets_list(self) -> None:
        self.widgets_list.delete(0, "end")
        widgets = self.kernel.list_widgets()
        for index, widget in enumerate(widgets, start=1):
            marker = "◉" if widget.get("widget_id") == self.selected_widget_id else " "
            self.widgets_list.insert("end", f"{marker} {index}. {widget.get('name', 'Widget')} [{widget.get('kind')}]")
            if widget.get("widget_id") == self.selected_widget_id:
                self.widgets_list.selection_set(index - 1)
                self.widgets_list.see(index - 1)

    def render_page(self) -> None:
        self.canvas.delete("all")
        self._image_references.clear()
        page = self.kernel.current_page()
        width = int(page.get("width_px", A4_WIDTH_PX))
        height = int(page.get("height_px", A4_HEIGHT_PX))
        self.canvas.configure(scrollregion=(0, 0, width + 2 * PAGE_PAD, height + 2 * PAGE_PAD))
        self.canvas.create_rectangle(
            PAGE_PAD - 2,
            PAGE_PAD - 2,
            PAGE_PAD + width + 2,
            PAGE_PAD + height + 2,
            fill="#b9b9b9",
            outline="",
        )
        self.canvas.create_rectangle(
            PAGE_PAD,
            PAGE_PAD,
            PAGE_PAD + width,
            PAGE_PAD + height,
            fill=page.get("background", "#ffffff"),
            outline="#777777",
            width=1,
            tags=("page", page.get("page_id")),
        )
        grid = page.get("grid", {})
        if grid.get("enabled"):
            step = max(4, int(grid.get("spacing", 24)))
            fill = grid.get("fill", "#eeeeee")
            for x in range(0, width + 1, step):
                self.canvas.create_line(PAGE_PAD + x, PAGE_PAD, PAGE_PAD + x, PAGE_PAD + height, fill=fill, tags=("page_grid",))
            for y in range(0, height + 1, step):
                self.canvas.create_line(PAGE_PAD, PAGE_PAD + y, PAGE_PAD + width, PAGE_PAD + y, fill=fill, tags=("page_grid",))
        for widget in self.kernel.list_widgets(page["page_id"]):
            if widget.get("visible", True):
                if widget.get("kind") not in self.kernel.registry.templates:
                    api = WidgetRuntimeAPI(self, self.kernel, page, widget, mode="draw")
                    draw_missing_widget_placeholder(api, widget)
                else:
                    self.execute_widget_program(widget, mode="draw", show_message=False)
            if widget.get("widget_id") == self.selected_widget_id:
                self.draw_selection(widget)

    def draw_selection(self, widget: Dict[str, Any]) -> None:
        x = PAGE_PAD + int(widget.get("x", 0))
        y = PAGE_PAD + int(widget.get("y", 0))
        w = int(widget.get("width", 0))
        h = int(widget.get("height", 0))
        self.canvas.create_rectangle(x, y, x + w, y + h, outline="#0b63ce", width=2, dash=(4, 2), tags=("selection",))
        self.canvas.create_rectangle(
            x + w - HANDLE_SIZE,
            y + h - HANDLE_SIZE,
            x + w + HANDLE_SIZE,
            y + h + HANDLE_SIZE,
            fill="#0b63ce",
            outline="#0b63ce",
            tags=("resize_handle", widget["widget_id"]),
        )

    def execute_widget_program(self, widget: Dict[str, Any], mode: str = "draw", show_message: bool = True) -> None:
        page = self.kernel.get_widget_page(widget["widget_id"])
        if page is None:
            return
        api = WidgetRuntimeAPI(self, self.kernel, page, widget, mode=mode)
        try:
            found, _ = execute_widget_hook(api, widget, page, self.kernel.session, mode)
            if found:
                if show_message:
                    self.log(f"Executed {mode} for {widget.get('name', widget.get('widget_id'))}")
            elif mode == "draw":
                api.draw_rectangle(0, 0, widget.get("width", 160), widget.get("height", 80), outline="#aaaaaa", fill="")
                api.draw_text(8, 8, f"No draw() in {widget.get('name', 'widget')}", font_size=12, fill="#777777")
            elif show_message:
                self.log(f"No {mode}() function defined for {widget.get('name', widget.get('widget_id'))}")
        except Exception as exc:
            error = traceback.format_exc()
            self.log(error)
            if mode == "draw":
                api.draw_rectangle(0, 0, widget.get("width", 220), widget.get("height", 80), outline="#b00020", fill="#fff5f5", width=2)
                api.draw_text(8, 8, f"Widget error:\n{exc}", font_size=12, fill="#b00020", width=int(widget.get("width", 220)) - 12)
            elif show_message:
                messagebox.showerror("Widget execution error", error)

    def selected_widget(self) -> Optional[Dict[str, Any]]:
        if not self.selected_widget_id:
            return None
        return self.kernel.get_widget(self.selected_widget_id)

    def load_selected_into_inspector(self) -> None:
        self._loading_inspector = True
        try:
            widget = self.selected_widget()
            if not widget:
                self.id_value.configure(text="No widget selected")
                for var in [self.name_var, self.kind_var, self.x_var, self.y_var, self.w_var, self.h_var]:
                    var.set("")
                self.visible_var.set(True)
                self.locked_var.set(False)
                self.properties_text.delete("1.0", "end")
                self.program_text.delete("1.0", "end")
                return
            self.id_value.configure(text=widget.get("widget_id", ""))
            self.name_var.set(str(widget.get("name", "")))
            self.kind_var.set(str(widget.get("kind", "")))
            self.x_var.set(str(widget.get("x", 0)))
            self.y_var.set(str(widget.get("y", 0)))
            self.w_var.set(str(widget.get("width", 0)))
            self.h_var.set(str(widget.get("height", 0)))
            self.visible_var.set(bool(widget.get("visible", True)))
            self.locked_var.set(bool(widget.get("locked", False)))
            self.properties_text.delete("1.0", "end")
            self.properties_text.insert("1.0", json.dumps(widget.get("properties", {}), indent=2, ensure_ascii=False))
            self.program_text.delete("1.0", "end")
            self.program_text.insert("1.0", widget.get("program", ""))
        finally:
            self._loading_inspector = False

    def apply_inspector(self) -> None:
        widget = self.selected_widget()
        if not widget:
            return
        try:
            props = ensure_json_object(self.properties_text.get("1.0", "end").strip() or "{}", {})
            updates = {
                "name": self.name_var.get().strip() or "Widget",
                "kind": self.kind_var.get().strip() or widget.get("kind", "free_program"),
                "x": int(float(self.x_var.get() or 0)),
                "y": int(float(self.y_var.get() or 0)),
                "width": max(16, int(float(self.w_var.get() or 16))),
                "height": max(16, int(float(self.h_var.get() or 16))),
                "visible": bool(self.visible_var.get()),
                "locked": bool(self.locked_var.get()),
                "properties": props,
                "program": self.program_text.get("1.0", "end-1c"),
            }
            self.kernel.update_widget(widget["widget_id"], updates)
            self.refresh_all(select_widget_id=widget["widget_id"])
            self.log("Inspector applied")
        except Exception as exc:
            messagebox.showerror("Inspector error", str(exc))

    def on_page_select(self, event: tk.Event) -> None:
        selection = self.pages_list.curselection()
        if not selection:
            return
        index = selection[0]
        pages = self.kernel.list_pages()
        if 0 <= index < len(pages):
            self.kernel.current_page_id = pages[index]["page_id"]
            self.selected_widget_id = None
            self.refresh_all()

    def on_widget_list_select(self, event: tk.Event) -> None:
        selection = self.widgets_list.curselection()
        if not selection:
            return
        widgets = self.kernel.list_widgets()
        index = selection[0]
        if 0 <= index < len(widgets):
            self.selected_widget_id = widgets[index]["widget_id"]
            self.refresh_all()

    def canvas_point(self, event: tk.Event) -> Tuple[float, float]:
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def widget_from_canvas_item(self, item: int) -> Optional[str]:
        tags = self.canvas.gettags(item)
        for tag in tags:
            if tag.startswith("w_"):
                return tag
        if len(tags) >= 2 and tags[0] == "widget":
            return tags[1]
        for tag in tags:
            if tag.startswith("w_"):
                return tag
        return None

    def hit_widget(self, x: float, y: float) -> Optional[str]:
        items = self.canvas.find_overlapping(x, y, x, y)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            if "selection" in tags or "page" in tags or "page_grid" in tags:
                continue
            for tag in tags:
                if tag.startswith("w_"):
                    return tag
            if len(tags) >= 2 and tags[0] == "widget":
                return tags[1]
        return None

    def on_canvas_press(self, event: tk.Event) -> None:
        x, y = self.canvas_point(event)
        widget_id = self.hit_widget(x, y)
        if widget_id:
            self.selected_widget_id = widget_id
            self.drag_start = (x, y)
            widget = self.kernel.get_widget(widget_id)
            if widget:
                wx = PAGE_PAD + int(widget.get("x", 0))
                wy = PAGE_PAD + int(widget.get("y", 0))
                ww = int(widget.get("width", 0))
                wh = int(widget.get("height", 0))
                if abs(x - (wx + ww)) <= HANDLE_SIZE * 2 and abs(y - (wy + wh)) <= HANDLE_SIZE * 2:
                    self.resize_start = (x, y, ww, wh)
                else:
                    self.resize_start = None
            self.refresh_all(select_widget_id=widget_id)
        else:
            self.selected_widget_id = None
            self.drag_start = None
            self.resize_start = None
            self.refresh_all()

    def on_canvas_drag(self, event: tk.Event) -> None:
        if not self.selected_widget_id or not self.drag_start:
            return
        x, y = self.canvas_point(event)
        widget = self.kernel.get_widget(self.selected_widget_id)
        if not widget or widget.get("locked"):
            return
        if self.resize_start:
            sx, sy, sw, sh = self.resize_start
            self.kernel.resize_widget(self.selected_widget_id, sw + (x - sx), sh + (y - sy))
        else:
            lx, ly = self.drag_start
            dx, dy = x - lx, y - ly
            self.kernel.move_widget(self.selected_widget_id, dx, dy)
            self.drag_start = (x, y)
        self.render_page()
        self.load_selected_into_inspector()
        self.update_title()

    def on_canvas_release(self, event: tk.Event) -> None:
        self.drag_start = None
        self.resize_start = None
        self.refresh_widgets_list()
        self.update_title()

    def on_canvas_double_click(self, event: tk.Event) -> None:
        x, y = self.canvas_point(event)
        page_x = int(x - PAGE_PAD)
        page_y = int(y - PAGE_PAD)
        page = self.kernel.current_page()
        if 0 <= page_x <= page["width_px"] and 0 <= page_y <= page["height_px"]:
            self.add_widget_dialog(default_x=page_x, default_y=page_y)

    def new_session(self) -> None:
        if not self.confirm_discard_changes():
            return
        self.kernel.reset()
        self.selected_widget_id = None
        self.refresh_all()
        self.log("New session created")

    def open_session(self) -> None:
        if not self.confirm_discard_changes():
            return
        path = filedialog.askopenfilename(
            title="Open mathematics session",
            filetypes=[("JSON session", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.kernel.load(path)
            self.selected_widget_id = None
            self.refresh_all()
            self.log(f"Opened {path}")
        except Exception as exc:
            messagebox.showerror("Open session", str(exc))

    def save_session(self) -> None:
        if not self.kernel.session_path:
            self.save_session_as()
            return
        try:
            path = self.kernel.save()
            self.update_title()
            self.log(f"Saved {path}")
        except Exception as exc:
            messagebox.showerror("Save session", str(exc))

    def save_session_as(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save mathematics session",
            defaultextension=".json",
            filetypes=[("JSON session", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            path = self.kernel.save(path)
            self.update_title()
            self.log(f"Saved {path}")
        except Exception as exc:
            messagebox.showerror("Save session", str(exc))

    def export_pdf_dialog(self) -> None:
        dialog = ExportPDFDialog(self)
        self.wait_window(dialog)

    def confirm_discard_changes(self) -> bool:
        if not self.kernel.dirty:
            return True
        result = messagebox.askyesnocancel("Unsaved changes", "Save the current session before continuing?")
        if result is None:
            return False
        if result:
            self.save_session()
            return not self.kernel.dirty
        return True

    def on_close(self) -> None:
        if self.confirm_discard_changes():
            self.destroy()

    def add_page(self) -> None:
        page = self.kernel.add_page()
        self.selected_widget_id = None
        self.refresh_all()
        self.log(f"Added {page.get('title')}")

    def duplicate_page(self) -> None:
        page = self.kernel.duplicate_page(self.kernel.current_page_id)
        if page:
            self.selected_widget_id = None
            self.refresh_all()
            self.log("Page duplicated")

    def rename_page(self) -> None:
        page = self.kernel.current_page()
        title = simpledialog.askstring("Rename page", "Page title:", initialvalue=page.get("title", "Page"))
        if title:
            self.kernel.rename_page(page["page_id"], title)
            self.refresh_all()

    def configure_page(self) -> None:
        dialog = PageConfigDialog(self)
        self.wait_window(dialog)

    def manage_templates(self) -> None:
        dialog = TemplateManagerDialog(self)
        self.wait_window(dialog)

    def delete_page(self) -> None:
        if len(self.kernel.list_pages()) <= 1:
            messagebox.showinfo("Delete page", "A session must contain at least one A4 page.")
            return
        if messagebox.askyesno("Delete page", "Delete the current page and all of its widgets?"):
            self.kernel.delete_page(self.kernel.current_page_id)
            self.selected_widget_id = None
            self.refresh_all()
            self.log("Page deleted")

    def add_widget_kind(self, kind: str, x: int = 80, y: int = 80) -> None:
        try:
            widget = self.kernel.create_widget(kind, x=x, y=y)
            self.refresh_all(select_widget_id=widget["widget_id"])
            self.log(f"Added widget {widget.get('name')}")
        except Exception as exc:
            messagebox.showerror("Add widget", str(exc))

    def _choose_png_properties(self) -> Optional[Dict[str, Any]]:
        path = filedialog.askopenfilename(
            parent=self, title="Choose PNG image",
            filetypes=[("PNG images", "*.png"), ("PNG images (uppercase)", "*.PNG")],
        )
        if not path:
            return None
        if Path(path).suffix.lower() != ".png":
            raise ValueError("Choose a file with a .png extension")
        data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        load_png_image(data_base64=data).close()
        return {"path": str(Path(path).resolve()), "data_base64": data}

    def add_png_image(self) -> None:
        try:
            properties = self._choose_png_properties()
            if properties is None:
                return
            widget = self.kernel.create_widget("png_image", overrides={
                "name": Path(properties["path"]).name, "properties": properties,
            })
            self.refresh_all(select_widget_id=widget["widget_id"])
            self.log("Added PNG image (embedded in session)")
        except Exception as exc:
            messagebox.showerror("Add PNG image", str(exc), parent=self)

    def replace_png_image(self) -> None:
        widget = self.selected_widget()
        if not widget or widget.get("kind") != "png_image":
            messagebox.showinfo("Replace PNG image", "Select a PNG image widget first.", parent=self)
            return
        try:
            selected = self._choose_png_properties()
            if selected is None:
                return
            properties = dict(widget.get("properties", {}))
            properties.update(selected)
            self.kernel.update_widget(widget["widget_id"], {"properties": properties})
            self.refresh_all(select_widget_id=widget["widget_id"])
            self.log("Replaced PNG image (embedded in session)")
        except Exception as exc:
            messagebox.showerror("Replace PNG image", str(exc), parent=self)

    def add_widget_dialog(self, default_x: int = 80, default_y: int = 80) -> None:
        dialog = WidgetChoiceDialog(self, self.kernel.registry.names())
        self.wait_window(dialog)
        if dialog.result:
            self.add_widget_kind(dialog.result, x=default_x, y=default_y)

    def duplicate_widget(self) -> None:
        widget = self.selected_widget()
        if not widget:
            return
        clone = self.kernel.duplicate_widget(widget["widget_id"])
        if clone:
            self.refresh_all(select_widget_id=clone["widget_id"])
            self.log("Widget duplicated")

    def delete_widget(self) -> None:
        widget = self.selected_widget()
        if not widget:
            return
        if messagebox.askyesno("Delete widget", f"Delete {widget.get('name', 'selected widget')}?"):
            self.kernel.delete_widget(widget["widget_id"])
            self.selected_widget_id = None
            self.refresh_all()
            self.log("Widget deleted")

    def bring_widget_forward(self) -> None:
        widget = self.selected_widget()
        if widget:
            self.kernel.bring_forward(widget["widget_id"])
            self.refresh_all(select_widget_id=widget["widget_id"])

    def send_widget_backward(self) -> None:
        widget = self.selected_widget()
        if widget:
            self.kernel.send_backward(widget["widget_id"])
            self.refresh_all(select_widget_id=widget["widget_id"])

    def run_selected_widget_action(self) -> None:
        self.apply_inspector()
        widget = self.selected_widget()
        if not widget:
            return
        self.execute_widget_program(widget, mode="action", show_message=True)
        self.refresh_all(select_widget_id=widget["widget_id"])

    def run_all_widget_actions(self) -> None:
        self.apply_inspector()
        page = self.kernel.current_page()
        for widget in self.kernel.list_widgets(page["page_id"]):
            self.execute_widget_program(widget, mode="action", show_message=True)
        self.refresh_all(select_widget_id=self.selected_widget_id)

    def load_plugins(self) -> None:
        directory = filedialog.askdirectory(title="Load mathematics widget plugin directory")
        if not directory:
            return
        loaded, errors = self.kernel.load_plugin_directory(directory)
        if errors:
            messagebox.showwarning("Plugin load warnings", f"Loaded {loaded} plugin file(s).\n\n" + "\n\n".join(errors[:3]))
        else:
            messagebox.showinfo("Plugins loaded", f"Loaded {loaded} plugin file(s).")
        self.log(f"Plugin directory loaded: {directory}")

    def run_generator_script(self) -> None:
        path = filedialog.askopenfilename(
            title="Run page generator script",
            filetypes=[("Python generator", "*.py"), ("All files", "*.*")],
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Run generator",
            "Run this generator script against the current session? It can create, update, or reset pages and widgets.",
            parent=self,
        ):
            return
        try:
            program = Path(path).read_text(encoding="utf-8")
            summary = self.kernel.run_page_generator(
                program,
                project_path=str(Path(path).parent),
                source=str(path),
                logger=self.log,
            )
            self.selected_widget_id = None
            self.refresh_all()
            self.log(
                f"Generator complete: {summary.get('pages_created', 0)} page(s), "
                f"{summary.get('widgets_created', 0)} widget(s)"
            )
            messagebox.showinfo(
                "Generator complete",
                f"Created {summary.get('pages_created', 0)} page(s) and {summary.get('widgets_created', 0)} widget(s).",
                parent=self,
            )
        except Exception as exc:
            error = traceback.format_exc()
            self.log(error)
            messagebox.showerror("Generator error", str(exc), parent=self)

    def show_generator_template(self) -> None:
        self.show_text_window("Page generator template", PAGE_GENERATOR_TEMPLATE, geometry="900x720")

    def show_generator_reference(self) -> None:
        self.show_text_window("Page generator reference", generate_page_generator_reference_markdown(), geometry="920x720")

    def export_generator_reference(self) -> None:
        default_dir = Path(self.kernel.session_path).parent if self.kernel.session_path else Path.cwd()
        path = filedialog.asksaveasfilename(
            title="Export page generator reference",
            defaultextension=".md",
            initialdir=str(default_dir),
            initialfile="mathematics_whiteboard_page_generator_reference.md",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(generate_page_generator_reference_markdown(), encoding="utf-8")
            self.log(f"Page generator reference exported: {path}")
        except Exception as exc:
            messagebox.showerror("Export generator reference", str(exc), parent=self)

    def show_plugin_template(self) -> None:
        self.show_text_window("Plugin template", PLUGIN_TEMPLATE, geometry="820x640")

    def show_plugin_reference(self) -> None:
        self.show_text_window("Plugin author reference", generate_plugin_reference_markdown(), geometry="920x720")

    def show_text_window(self, title: str, content: str, geometry: str = "780x560") -> None:
        top = tk.Toplevel(self)
        top.title(title)
        top.geometry(geometry)
        frame = ttk.Frame(top)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="none")
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text.insert("1.0", content)

    def export_plugin_reference(self) -> None:
        default_dir = Path(self.kernel.session_path).parent if self.kernel.session_path else Path.cwd()
        path = filedialog.asksaveasfilename(
            title="Export plugin reference",
            defaultextension=".md",
            initialdir=str(default_dir),
            initialfile="mathematics_whiteboard_plugin_reference.md",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(generate_plugin_reference_markdown(), encoding="utf-8")
            self.log(f"Plugin reference exported: {path}")
        except Exception as exc:
            messagebox.showerror("Export plugin reference", str(exc), parent=self)

    def show_contract(self) -> None:
        messagebox.showinfo(
            "Session contract",
            "The session is a JSON document. Each page is A4. Each visible canvas object is rendered by a widget. "
            "Each widget stores geometry, properties, and a Python program. Page configuration and widget templates are also JSON-persistent. "
            "The runtime canvas is disposable; the JSON session is the source of truth.",
        )


class ExportPDFDialog(tk.Toplevel):
    def __init__(self, master: WhiteboardApp) -> None:
        super().__init__(master)
        self.app = master
        self.title("Export A4 PDF")
        self.geometry("620x520")
        self.transient(master)
        self.grab_set()
        settings = merge_dicts(DEFAULT_EXPORT_SETTINGS.get("pdf", {}), master.kernel.session.get("export_settings", {}).get("pdf", {}))

        self.path_var = tk.StringVar(value=self.default_export_path())
        self.scope_var = tk.StringVar(value="all")
        self.range_var = tk.StringVar(value=str(settings.get("page_range", "all")))
        self.title_var = tk.StringVar(value=str(settings.get("title") or master.kernel.session.get("title", "")))
        self.author_var = tk.StringVar(value=str(settings.get("author", "")))
        self.include_grid_var = tk.BooleanVar(value=bool(settings.get("include_grid", True)))
        self.include_titles_var = tk.BooleanVar(value=bool(settings.get("include_page_titles", False)))
        self.include_bounds_var = tk.BooleanVar(value=bool(settings.get("include_widget_bounds", False)))
        self.include_metadata_var = tk.BooleanVar(value=bool(settings.get("include_metadata", True)))
        self.exclude_hidden_var = tk.BooleanVar(value=bool(settings.get("exclude_hidden_widgets", True)))
        self.one_file_var = tk.BooleanVar(value=bool(settings.get("one_file_per_page", False)))

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Output PDF path").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.path_var).grid(row=0, column=1, sticky="ew", padx=(8, 4))
        ttk.Button(frame, text="Browse", command=self.browse_path).grid(row=0, column=2, sticky="ew")

        ttk.Label(frame, text="Title").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.title_var).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Label(frame, text="Author").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.author_var).grid(row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0))

        scope = ttk.LabelFrame(frame, text="Pages")
        scope.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        ttk.Radiobutton(scope, text="Entire session", variable=self.scope_var, value="all").pack(anchor="w", padx=8, pady=2)
        ttk.Radiobutton(scope, text="Current page", variable=self.scope_var, value="current").pack(anchor="w", padx=8, pady=2)
        range_row = ttk.Frame(scope)
        range_row.pack(fill="x", padx=8, pady=2)
        ttk.Radiobutton(range_row, text="Selected page range", variable=self.scope_var, value="range").pack(side="left")
        ttk.Entry(range_row, textvariable=self.range_var, width=20).pack(side="left", padx=(8, 0))
        ttk.Label(range_row, text="Example: 1-3,5").pack(side="left", padx=(8, 0))

        options = ttk.LabelFrame(frame, text="Export options")
        options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        for row, (label, var) in enumerate([
            ("Include enabled page grids", self.include_grid_var),
            ("Include page titles", self.include_titles_var),
            ("Include widget bounding boxes", self.include_bounds_var),
            ("Include export metadata footer", self.include_metadata_var),
            ("Exclude hidden widgets", self.exclude_hidden_var),
            ("Create one PDF per page", self.one_file_var),
        ]):
            ttk.Checkbutton(options, text=label, variable=var).grid(row=row // 2, column=row % 2, sticky="w", padx=8, pady=4)

        note = (
            "The exporter replays each widget program through the PDF drawing API. "
            "Native vector output is used first; unsupported widget code is reported in the warning log."
        )
        ttk.Label(frame, text=note, wraplength=560, foreground="#555555").grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 8))

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="ew")
        ttk.Button(buttons, text="Export", command=self.export).pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", fill="x", expand=True)

    def default_export_path(self) -> str:
        base = self.app.kernel.session_path
        if base:
            return str(Path(base).with_suffix(".pdf"))
        stem = safe_file_stem(str(self.app.kernel.session.get("title", "mathematics_export")))
        return str(Path.cwd() / f"{stem}.pdf")

    def browse_path(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export mathematics PDF",
            defaultextension=".pdf",
            initialfile=Path(self.path_var.get()).name,
            filetypes=[("PDF file", "*.pdf"), ("All files", "*.*")],
            parent=self,
        )
        if path:
            self.path_var.set(path)

    def selected_page_ids(self) -> Optional[List[str]]:
        pages = self.app.kernel.list_pages()
        scope = self.scope_var.get()
        if scope == "all":
            return None
        if scope == "current":
            return [self.app.kernel.current_page_id]
        indexes = parse_page_range_spec(self.range_var.get(), len(pages))
        return [pages[i]["page_id"] for i in indexes]

    def export(self) -> None:
        path = self.path_var.get().strip()
        if not path:
            messagebox.showerror("Export PDF", "Choose an output PDF path.", parent=self)
            return
        options = {
            "title": self.title_var.get().strip(),
            "author": self.author_var.get().strip(),
            "page_range": self.range_var.get().strip() or "all",
            "include_grid": bool(self.include_grid_var.get()),
            "include_page_titles": bool(self.include_titles_var.get()),
            "include_widget_bounds": bool(self.include_bounds_var.get()),
            "include_metadata": bool(self.include_metadata_var.get()),
            "exclude_hidden_widgets": bool(self.exclude_hidden_var.get()),
            "one_file_per_page": bool(self.one_file_var.get()),
        }
        try:
            result = self.app.kernel.export_pdf(path, page_ids=self.selected_page_ids(), options=options)
            self.app.update_title()
            exported = ", ".join(result.get("paths", []))
            warning_count = len(result.get("warnings", []))
            if warning_count:
                preview = "\n".join(result.get("warnings", [])[:8])
                messagebox.showwarning("PDF exported with warnings", f"Exported {result.get('pages', 0)} page(s).\n\n{preview}", parent=self)
            else:
                messagebox.showinfo("PDF exported", f"Exported {result.get('pages', 0)} page(s).\n\n{exported}", parent=self)
            self.app.log(f"PDF exported: {exported or path} ({warning_count} warning(s))")
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Export PDF", str(exc), parent=self)


class PageConfigDialog(tk.Toplevel):
    def __init__(self, master: WhiteboardApp) -> None:
        super().__init__(master)
        self.app = master
        self.title("Configure current A4 page JSON")
        self.geometry("760x620")
        self.transient(master)
        self.grab_set()
        ttk.Label(
            self,
            text="Edit page configuration. The widgets array is preserved by the kernel and is not edited here.",
        ).pack(anchor="w", padx=10, pady=(10, 4))
        self.text = tk.Text(self, wrap="none", undo=True)
        self.text.pack(fill="both", expand=True, padx=10, pady=4)
        page = deep_copy(master.kernel.current_page())
        page.pop("widgets", None)
        self.text.insert("1.0", json.dumps(page, indent=2, ensure_ascii=False))
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=10)
        ttk.Button(buttons, text="Apply", command=self.apply).pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="left", fill="x", expand=True)

    def apply(self) -> None:
        try:
            updates = ensure_json_object(self.text.get("1.0", "end").strip() or "{}", {})
            page = self.app.kernel.current_page()
            updates.pop("page_id", None)
            updates.pop("widgets", None)
            for key, value in updates.items():
                page[key] = value
            page["modified_at"] = now_iso()
            self.app.kernel.touch()
            self.app.refresh_all()
            self.app.log("Page JSON configuration applied")
        except Exception as exc:
            messagebox.showerror("Page configuration error", str(exc), parent=self)


class TemplateManagerDialog(tk.Toplevel):
    def __init__(self, master: WhiteboardApp) -> None:
        super().__init__(master)
        self.app = master
        self.title("Persistent widget-template manager")
        self.geometry("980x720")
        self.transient(master)
        self.grab_set()
        self.selected_kind: Optional[str] = None
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, padding=8)
        left.grid(row=0, column=0, sticky="ns")
        ttk.Label(left, text="Templates").pack(anchor="w")
        self.listbox = tk.Listbox(left, width=28, exportselection=False)
        self.listbox.pack(fill="both", expand=True, pady=4)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        left_buttons = ttk.Frame(left)
        left_buttons.pack(fill="x")
        ttk.Button(left_buttons, text="New", command=self.new_template).pack(side="left", fill="x", expand=True)
        ttk.Button(left_buttons, text="Copy", command=self.duplicate_template).pack(side="left", fill="x", expand=True)
        ttk.Button(left_buttons, text="Delete", command=self.delete_template).pack(side="left", fill="x", expand=True)

        right = ttk.Frame(self, padding=8)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)
        right.rowconfigure(7, weight=1)
        right.rowconfigure(9, weight=1)
        right.rowconfigure(11, weight=2)

        self.kind_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.width_var = tk.StringVar()
        self.height_var = tk.StringVar()
        self.source_var = tk.StringVar()
        rows = [
            ("Kind", self.kind_var),
            ("Name", self.name_var),
            ("Width", self.width_var),
            ("Height", self.height_var),
            ("Source", self.source_var),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(right, text=label).grid(row=i, column=0, sticky="w")
            state = "readonly" if label == "Source" else "normal"
            ttk.Entry(right, textvariable=var, state=state).grid(row=i, column=1, sticky="ew", pady=2)

        ttk.Label(right, text="Description").grid(row=5, column=0, sticky="nw")
        self.description_text = tk.Text(right, height=3, wrap="word", undo=True)
        self.description_text.grid(row=5, column=1, sticky="nsew", pady=2)

        ttk.Label(right, text="Default properties JSON").grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.properties_text = tk.Text(right, height=9, wrap="none", undo=True)
        self.properties_text.grid(row=7, column=0, columnspan=2, sticky="nsew")

        ttk.Label(right, text="Property schema JSON").grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.properties_schema_text = tk.Text(right, height=7, wrap="none", undo=True)
        self.properties_schema_text.grid(row=9, column=0, columnspan=2, sticky="nsew")

        ttk.Label(right, text="Default Python program").grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.program_text = tk.Text(right, height=16, wrap="none", undo=True)
        self.program_text.grid(row=11, column=0, columnspan=2, sticky="nsew")

        buttons = ttk.Frame(right)
        buttons.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Apply Template", command=self.apply_template).pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="Add Widget From Template", command=self.add_widget_from_template).pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="left", fill="x", expand=True)

        self.refresh_list()

    def refresh_list(self) -> None:
        current = self.selected_kind
        self.listbox.delete(0, "end")
        kinds = self.app.kernel.registry.names()
        for index, kind in enumerate(kinds):
            source = source_label(self.app.kernel.registry.sources.get(kind, "session"))
            self.listbox.insert("end", f"{kind}  [{source}]")
            if kind == current:
                self.listbox.selection_set(index)
        if kinds and self.listbox.curselection():
            self.load_kind(kinds[self.listbox.curselection()[0]])
        elif kinds:
            self.listbox.selection_set(0)
            self.load_kind(kinds[0])
        else:
            self.new_template()

    def current_list_kind(self) -> Optional[str]:
        selection = self.listbox.curselection()
        if not selection:
            return None
        kinds = self.app.kernel.registry.names()
        index = selection[0]
        if 0 <= index < len(kinds):
            return kinds[index]
        return None

    def on_select(self, event: tk.Event) -> None:
        kind = self.current_list_kind()
        if kind:
            self.load_kind(kind)

    def load_kind(self, kind: str) -> None:
        record = self.app.kernel.get_template(kind)
        if not record:
            return
        self.selected_kind = kind
        self.kind_var.set(str(record.get("kind", kind)))
        self.name_var.set(str(record.get("name", kind)))
        self.width_var.set(str(record.get("width", 300)))
        self.height_var.set(str(record.get("height", 180)))
        self.source_var.set(source_label(record.get("source", "session")))
        self.description_text.delete("1.0", "end")
        self.description_text.insert("1.0", str(record.get("description", "")))
        self.properties_text.delete("1.0", "end")
        self.properties_text.insert("1.0", json.dumps(record.get("properties", {}), indent=2, ensure_ascii=False))
        self.properties_schema_text.delete("1.0", "end")
        self.properties_schema_text.insert("1.0", json.dumps(record.get("properties_schema", {}), indent=2, ensure_ascii=False))
        self.program_text.delete("1.0", "end")
        self.program_text.insert("1.0", str(record.get("program", FREE_PROGRAM_WIDGET_PROGRAM)))

    def new_template(self) -> None:
        base = "custom_math_widget"
        candidate = base
        index = 2
        while candidate in self.app.kernel.registry.templates:
            candidate = f"{base}_{index}"
            index += 1
        self.selected_kind = None
        self.kind_var.set(candidate)
        self.name_var.set("Custom Mathematics Widget")
        self.width_var.set("360")
        self.height_var.set("220")
        self.source_var.set("session")
        self.description_text.delete("1.0", "end")
        self.description_text.insert("1.0", "Session-persistent programmable mathematics widget template.")
        self.properties_text.delete("1.0", "end")
        self.properties_text.insert("1.0", json.dumps({"title": "formal mathematics widget"}, indent=2))
        self.properties_schema_text.delete("1.0", "end")
        self.properties_schema_text.insert("1.0", json.dumps({
            "title": {"type": "string", "default": "formal mathematics widget", "description": "Widget title text."}
        }, indent=2))
        self.program_text.delete("1.0", "end")
        self.program_text.insert("1.0", FREE_PROGRAM_WIDGET_PROGRAM)

    def record_from_fields(self) -> Dict[str, Any]:
        return {
            "kind": self.kind_var.get().strip(),
            "name": self.name_var.get().strip() or "Widget",
            "width": max(16, int(float(self.width_var.get() or 300))),
            "height": max(16, int(float(self.height_var.get() or 180))),
            "properties": ensure_json_object(self.properties_text.get("1.0", "end").strip() or "{}", {}),
            "properties_schema": ensure_json_object(self.properties_schema_text.get("1.0", "end").strip() or "{}", {}),
            "program": self.program_text.get("1.0", "end-1c"),
            "description": self.description_text.get("1.0", "end-1c"),
        }

    def apply_template(self) -> None:
        try:
            record = self.record_from_fields()
            new_kind = record["kind"]
            if self.selected_kind and self.selected_kind != new_kind:
                self.app.kernel.delete_template(self.selected_kind)
            self.app.kernel.upsert_template(record, source="session")
            self.selected_kind = new_kind
            self.app.refresh_all()
            self.refresh_list()
            self.app.log(f"Template applied: {new_kind}")
        except Exception as exc:
            messagebox.showerror("Template error", str(exc), parent=self)

    def duplicate_template(self) -> None:
        kind = self.current_list_kind() or self.selected_kind
        if not kind:
            return
        try:
            record = self.app.kernel.duplicate_template(kind)
            self.selected_kind = str(record.get("kind"))
            self.app.refresh_all()
            self.refresh_list()
        except Exception as exc:
            messagebox.showerror("Duplicate template", str(exc), parent=self)

    def delete_template(self) -> None:
        kind = self.current_list_kind() or self.selected_kind
        if not kind:
            return
        if not messagebox.askyesno("Delete template", f"Delete template {kind}? Existing widgets remain in the session.", parent=self):
            return
        self.app.kernel.delete_template(kind)
        self.selected_kind = None
        self.app.refresh_all()
        self.refresh_list()

    def add_widget_from_template(self) -> None:
        try:
            self.apply_template()
            kind = self.kind_var.get().strip()
            widget = self.app.kernel.create_widget(kind, x=80, y=80)
            self.app.refresh_all(select_widget_id=widget["widget_id"])
            self.app.log(f"Added widget from template: {kind}")
        except Exception as exc:
            messagebox.showerror("Add widget from template", str(exc), parent=self)


class WidgetChoiceDialog(tk.Toplevel):
    def __init__(self, master: WhiteboardApp, kinds: List[str]) -> None:
        super().__init__(master)
        self.title("Add widget")
        self.geometry("340x420")
        self.result: Optional[str] = None
        self.transient(master)
        self.grab_set()
        ttk.Label(self, text="Select a widget template").pack(anchor="w", padx=10, pady=(10, 4))
        self.listbox = tk.Listbox(self, exportselection=False)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=4)
        for kind in kinds:
            self.listbox.insert("end", kind)
        if kinds:
            self.listbox.selection_set(0)
        self.listbox.bind("<Double-Button-1>", lambda e: self.accept())
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=10)
        ttk.Button(buttons, text="Add", command=self.accept).pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", fill="x", expand=True)

    def accept(self) -> None:
        selection = self.listbox.curselection()
        if selection:
            self.result = str(self.listbox.get(selection[0]))
        self.destroy()


FORMAL_MATH_WIDGET_PROGRAM = r'''def _wrap(value, width=70):
    words = str(value or "").replace("\n", " \n ").split()
    lines = []
    current = ""
    for word in words:
        if word == "\n":
            if current:
                lines.append(current)
                current = ""
            continue
        if len(current) + len(word) + 1 > width:
            if current:
                lines.append(current)
            current = word
        else:
            current = word if not current else current + " " + word
    if current:
        lines.append(current)
    return lines or [""]


def _props(widget):
    p = widget.setdefault("properties", {})
    p.setdefault("record_type", "theorem")
    p.setdefault("title", "Formal mathematical record")
    p.setdefault("statement", "State the definition, proposition, lemma, theorem, corollary, conjecture, example, or counterexample here.")
    p.setdefault("hypotheses", [])
    p.setdefault("dependencies", [])
    p.setdefault("proof_status", "draft")
    p.setdefault("proof_body", "")
    p.setdefault("proof_steps", [])
    p.setdefault("tags", [])
    p.setdefault("references", [])
    p.setdefault("linked_widgets", [])
    p.setdefault("render_mode", "record")
    return p


def draw(api, widget, page, session):
    p = _props(widget)
    w = int(widget.get("width", 560))
    h = int(widget.get("height", 360))
    mode = str(p.get("render_mode", "record"))
    status = str(p.get("proof_status", "draft"))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    header = f"{str(p.get('record_type', 'theorem')).upper()}: {p.get('title', '')}"
    api.draw_rectangle(0, 0, w, 38, outline="#111111", fill="#f3f3f3", width=1)
    api.draw_text(10, 9, header, font_size=15, fill="#111111", bold=True, width=w - 20)
    api.draw_text(w - 116, 10, f"status: {status}", font_size=9, fill="#555555")

    if mode == "dependency_graph":
        deps = list(p.get("dependencies", []))
        cx = w / 2
        cy = h / 2 + 20
        api.draw_oval(cx - 58, cy - 28, cx + 58, cy + 28, outline="#111111", fill="#ffffff", width=2)
        api.draw_text(cx, cy - 6, p.get("record_type", "record"), font_size=11, anchor="center", bold=True)
        radius = min(w, h) / 2 - 70
        for index, dep in enumerate(deps or ["no dependencies"]):
            angle = 2 * math.pi * index / max(1, len(deps or [1]))
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius
            api.draw_oval(x - 46, y - 20, x + 46, y + 20, outline="#777777", fill="#fafafa", width=1)
            api.draw_line(x, y, cx, cy, fill="#777777", width=1, arrow="last")
            api.draw_text(x, y - 6, dep, font_size=8, anchor="center", width=82)
        return

    y = 50
    api.draw_text(10, y, "Statement", font_size=11, bold=True)
    y += 18
    for line in _wrap(p.get("statement", ""), 78):
        api.draw_text(16, y, line, font_size=10, width=w - 30)
        y += 14
    y += 4
    if p.get("hypotheses"):
        api.draw_text(10, y, "Hypotheses", font_size=11, bold=True)
        y += 17
        for item in p.get("hypotheses", [])[:5]:
            api.draw_text(18, y, f"• {item}", font_size=9, width=w - 32)
            y += 13
    if p.get("dependencies"):
        api.draw_text(10, y, "Dependencies", font_size=11, bold=True)
        y += 17
        api.draw_text(18, y, ", ".join(map(str, p.get("dependencies", []))), font_size=9, fill="#444444", width=w - 32)
        y += 26

    steps = list(p.get("proof_steps", []))
    if mode == "proof_tree":
        api.draw_text(10, y, "Proof tree", font_size=11, bold=True)
        y += 20
        node_w = min(160, max(120, (w - 40) / max(1, min(3, len(steps) or 1))))
        for index, step in enumerate(steps[:9]):
            col = index % 3
            row = index // 3
            x = 16 + col * (node_w + 16)
            box_y = y + row * 70
            api.draw_rectangle(x, box_y, x + node_w, box_y + 50, outline="#333333", fill="#ffffff", width=1)
            api.draw_text(x + 6, box_y + 5, f"{step.get('id', index + 1)} · {step.get('kind', 'step')}", font_size=8, bold=True, width=int(node_w) - 12)
            api.draw_text(x + 6, box_y + 19, step.get("text", ""), font_size=7, width=int(node_w) - 12)
        return

    api.draw_text(10, y, "Proof steps", font_size=11, bold=True)
    y += 18
    if not steps:
        api.draw_text(18, y, "No proof steps yet. Run action to create a first step or edit JSON directly.", font_size=9, fill="#777777", width=w - 36)
    for index, step in enumerate(steps[:8], start=1):
        label = f"{index}. [{step.get('status', 'draft')}] {step.get('kind', 'step')}"
        api.draw_text(16, y, label, font_size=9, bold=True, width=w - 32)
        y += 13
        api.draw_text(28, y, step.get("text", ""), font_size=8, fill="#333333", width=w - 44)
        y += 25
    tags = ", ".join(map(str, p.get("tags", [])))
    if tags:
        api.draw_text(10, h - 22, f"tags: {tags}", font_size=8, fill="#666666", width=w - 20)


def action(api, widget, page, session):
    p = _props(widget)
    if not p.get("proof_steps"):
        p["proof_steps"] = [{"id": "s1", "kind": "proof-step", "text": "Write the first proof step here.", "depends_on": [], "status": "draft"}]
    checked = sum(1 for step in p.get("proof_steps", []) if str(step.get("status", "")).lower() in {"checked", "proved", "complete"})
    total = len(p.get("proof_steps", []))
    p["proof_summary"] = {"checked_steps": checked, "total_steps": total, "updated_at": datetime.datetime.now().replace(microsecond=0).isoformat()}
    widget["modified_at"] = p["proof_summary"]["updated_at"]
    api.log(f"Formal record checked: {checked}/{total} proof steps marked checked.")
'''

SYMBOLIC_ALGEBRA_WIDGET_PROGRAM = r'''def _props(widget):
    p = widget.setdefault("properties", {})
    p.setdefault("source_expression", "x**2")
    p.setdefault("variables", ["x"])
    p.setdefault("assumptions", {})
    p.setdefault("operation", "simplify")
    p.setdefault("result_forms", {})
    p.setdefault("transformation_history", [])
    return p


def draw(api, widget, page, session):
    p = _props(widget)
    w = int(widget.get("width", 560))
    h = int(widget.get("height", 340))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    api.draw_rectangle(0, 0, w, 36, outline="#111111", fill="#f4f4f4", width=1)
    api.draw_text(10, 9, "Symbolic Algebra and Assumption Engine", font_size=14, bold=True)
    y = 50
    api.draw_text(12, y, "source", font_size=10, bold=True)
    api.draw_text(90, y, p.get("source_expression", ""), font_size=11, width=w - 105)
    y += 30
    api.draw_text(12, y, "operation", font_size=10, bold=True)
    api.draw_text(90, y, p.get("operation", "simplify"), font_size=11)
    y += 24
    api.draw_text(12, y, "variables", font_size=10, bold=True)
    api.draw_text(90, y, ", ".join(map(str, p.get("variables", []))), font_size=10, width=w - 105)
    y += 24
    api.draw_text(12, y, "assumptions", font_size=10, bold=True)
    api.draw_text(90, y, json.dumps(p.get("assumptions", {}), ensure_ascii=False), font_size=8, width=w - 105)
    y += 34
    result = p.get("result_forms", {}) if isinstance(p.get("result_forms", {}), dict) else {}
    api.draw_rectangle(12, y, w - 12, min(h - 78, y + 88), outline="#dddddd", fill="#fbfbfb", width=1)
    api.draw_text(20, y + 8, "result", font_size=10, bold=True)
    api.draw_text(82, y + 8, result.get("result", "Run action to compute."), font_size=11, width=w - 100)
    if result.get("latex"):
        api.draw_text(82, y + 36, "LaTeX: " + result.get("latex", ""), font_size=8, fill="#555555", width=w - 100)
    y = h - 62
    history = p.get("transformation_history", [])[-3:]
    api.draw_text(12, y, "history", font_size=10, bold=True)
    y += 14
    for item in history:
        api.draw_text(20, y, f"• {item.get('operation', '')} → {item.get('result', '')}", font_size=8, fill="#555555", width=w - 30)
        y += 12


def action(api, widget, page, session):
    p = _props(widget)
    timestamp = datetime.datetime.now().replace(microsecond=0).isoformat()
    try:
        import sympy as sp
    except Exception as exc:
        p["result_forms"] = {"operation": p.get("operation", "simplify"), "result": "SymPy is not installed.", "error": str(exc)}
        api.log("SymPy unavailable. Install sympy for symbolic computation.")
        return
    variables = p.get("variables", ["x"])
    assumptions = p.get("assumptions", {}) if isinstance(p.get("assumptions", {}), dict) else {}
    local = {}
    for name in variables:
        name = str(name)
        kwargs = assumptions.get(name, {}) if isinstance(assumptions.get(name, {}), dict) else {}
        local[name] = sp.symbols(name, **kwargs)
    source = str(p.get("source_expression", "0"))
    operation = str(p.get("operation", "simplify")).lower()
    expr = sp.sympify(source, locals=local)
    result = expr
    if operation == "simplify":
        result = sp.simplify(expr)
    elif operation == "expand":
        result = sp.expand(expr)
    elif operation == "factor":
        result = sp.factor(expr)
    elif operation in {"differentiate", "derivative", "diff"}:
        var = local.get(str(p.get("differentiate_by", variables[0] if variables else "x")))
        result = sp.diff(expr, var)
    elif operation in {"integrate", "integral"}:
        var = local.get(str(p.get("integrate_by", variables[0] if variables else "x")))
        result = sp.integrate(expr, var)
    elif operation == "limit":
        lim = p.get("limit", {}) if isinstance(p.get("limit", {}), dict) else {}
        var = local.get(str(lim.get("variable", variables[0] if variables else "x")))
        point = sp.sympify(str(lim.get("point", "0")), locals=local)
        direction = str(lim.get("direction", "+"))
        result = sp.limit(expr, var, point, dir=direction)
    elif operation == "series":
        ser = p.get("series", {}) if isinstance(p.get("series", {}), dict) else {}
        var = local.get(str(ser.get("variable", variables[0] if variables else "x")))
        point = sp.sympify(str(ser.get("point", "0")), locals=local)
        order = int(ser.get("order", 6))
        result = sp.series(expr, var, point, order)
    elif operation == "substitute":
        substitutions = p.get("substitutions", {}) if isinstance(p.get("substitutions", {}), dict) else {}
        sub_pairs = {local.get(str(k), sp.Symbol(str(k))): sp.sympify(str(v), locals=local) for k, v in substitutions.items()}
        result = expr.subs(sub_pairs)
    elif operation == "solve":
        result = sp.solve(expr, list(local.values()))
    else:
        result = sp.simplify(expr)
    forms = {"operation": operation, "source": source, "result": str(result), "latex": sp.latex(result), "computed_at": timestamp}
    p["result_forms"] = forms
    history = p.setdefault("transformation_history", [])
    history.append({"operation": operation, "source": source, "result": str(result), "computed_at": timestamp})
    p["transformation_history"] = history[-50:]
    widget["modified_at"] = timestamp
    api.log(f"Symbolic operation computed: {operation} -> {result}")
'''

GEOMETRY_CONSTRUCTION_WIDGET_PROGRAM = r'''def _point_map(objects):
    points = {}
    for obj in objects:
        if obj.get("type") == "point" and "x" in obj and "y" in obj:
            points[obj.get("id")] = (float(obj.get("x", 0)), float(obj.get("y", 0)))
    return points


def _object_map(objects):
    return {obj.get("id"): obj for obj in objects if obj.get("id")}


def _line_points(obj, points):
    p1 = points.get(obj.get("p1")) or points.get(obj.get("from"))
    p2 = points.get(obj.get("p2")) or points.get(obj.get("to"))
    return p1, p2


def _line_intersection(a, b, points):
    p = _line_points(a, points)
    q = _line_points(b, points)
    if not p[0] or not p[1] or not q[0] or not q[1]:
        return None
    x1, y1 = p[0]
    x2, y2 = p[1]
    x3, y3 = q[0]
    x4, y4 = q[1]
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    px = ((x1*y2 - y1*x2) * (x3 - x4) - (x1 - x2) * (x3*y4 - y3*x4)) / den
    py = ((x1*y2 - y1*x2) * (y3 - y4) - (y1 - y2) * (x3*y4 - y3*x4)) / den
    return px, py


def draw(api, widget, page, session):
    props = widget.setdefault("properties", {})
    objects = list(props.get("objects", []))
    points = _point_map(objects)
    objmap = _object_map(objects)
    w = int(widget.get("width", 560))
    h = int(widget.get("height", 380))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    api.draw_text(10, 8, props.get("title", "Geometric construction"), font_size=14, bold=True)
    api.draw_grid(step=40, fill="#f0f0f0")
    for obj in objects:
        typ = obj.get("type")
        if typ == "intersection":
            sources = obj.get("sources", [])
            if len(sources) >= 2:
                hit = _line_intersection(objmap.get(sources[0], {}), objmap.get(sources[1], {}), points)
                if hit:
                    points[obj.get("id")] = hit
        elif typ == "circle":
            center = points.get(obj.get("center"))
            if center:
                if obj.get("through") in points:
                    tx, ty = points[obj.get("through")]
                    r = math.hypot(tx - center[0], ty - center[1])
                else:
                    r = float(obj.get("radius", 40))
                api.draw_oval(center[0] - r, center[1] - r, center[0] + r, center[1] + r, outline=obj.get("outline", "#555555"), fill="", width=int(obj.get("width", 1)))
                if obj.get("label"):
                    api.draw_text(center[0] + r + 5, center[1], obj.get("label"), font_size=8, fill="#555555")
        elif typ in {"segment", "line", "ray"}:
            p1, p2 = _line_points(obj, points)
            if p1 and p2:
                x1, y1 = p1
                x2, y2 = p2
                if typ == "line":
                    dx, dy = x2 - x1, y2 - y1
                    length = math.hypot(dx, dy) or 1
                    x1 -= dx / length * 1000
                    y1 -= dy / length * 1000
                    x2 += dx / length * 1000
                    y2 += dy / length * 1000
                arrow = "last" if typ == "ray" else "none"
                api.draw_line(x1, y1, x2, y2, fill=obj.get("fill", "#111111"), width=int(obj.get("width", 2)), arrow=arrow)
                if obj.get("label"):
                    api.draw_text((x1 + x2) / 2 + 4, (y1 + y2) / 2 + 4, obj.get("label"), font_size=9)
        elif typ == "vector":
            p1, p2 = points.get(obj.get("from")), points.get(obj.get("to"))
            if p1 and p2:
                api.draw_vector(p1[0], p1[1], p2[0], p2[1], fill=obj.get("fill", "#111111"), width=int(obj.get("width", 2)), label=obj.get("label", ""))
        elif typ == "polygon":
            pts = [points.get(pid) for pid in obj.get("points", [])]
            pts = [p for p in pts if p]
            if len(pts) >= 3:
                api.draw_polygon(pts, outline=obj.get("outline", "#111111"), fill=obj.get("fill", ""), width=int(obj.get("width", 2)))
    for pid, (x, y) in points.items():
        api.draw_oval(x - 4, y - 4, x + 4, y + 4, outline="#111111", fill="#111111", width=1)
        api.draw_text(x + 7, y - 10, pid, font_size=9)
    steps = props.get("construction_steps", [])
    if steps:
        api.draw_rectangle(w - 190, 40, w - 10, h - 10, outline="#dddddd", fill="#fbfbfb", width=1)
        api.draw_text(w - 182, 48, "construction", font_size=10, bold=True)
        y = 66
        for index, step in enumerate(steps[:14], start=1):
            api.draw_text(w - 182, y, f"{index}. {step}", font_size=7, width=165)
            y += 18


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    objects = props.setdefault("objects", [])
    points = _point_map(objects)
    objmap = _object_map(objects)
    measurements = {}
    for obj in objects:
        if obj.get("type") == "segment":
            p1, p2 = _line_points(obj, points)
            if p1 and p2:
                measurements[obj.get("id", "segment")] = {"length": math.hypot(p2[0] - p1[0], p2[1] - p1[1])}
        if obj.get("type") == "intersection":
            sources = obj.get("sources", [])
            if len(sources) >= 2:
                hit = _line_intersection(objmap.get(sources[0], {}), objmap.get(sources[1], {}), points)
                if hit:
                    obj["x"], obj["y"] = hit
                    obj["computed_from"] = sources
                    points[obj.get("id")] = hit
    props["measurements"] = measurements
    props["validated_at"] = datetime.datetime.now().replace(microsecond=0).isoformat()
    api.log(f"Geometry construction validated with {len(objects)} object(s) and {len(measurements)} measurement(s).")
'''

GRAPH_NETWORK_CATEGORY_WIDGET_PROGRAM = r'''def _node_map(nodes):
    return {node.get("id"): node for node in nodes if node.get("id")}


def draw(api, widget, page, session):
    props = widget.setdefault("properties", {})
    nodes = props.setdefault("nodes", [])
    edges = props.setdefault("edges", [])
    w = int(widget.get("width", 560))
    h = int(widget.get("height", 360))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    api.draw_text(10, 8, props.get("title", "Graph / network / category diagram"), font_size=14, bold=True)
    lookup = _node_map(nodes)
    for edge in edges:
        src = lookup.get(edge.get("source"))
        dst = lookup.get(edge.get("target"))
        if not src or not dst:
            continue
        x1, y1 = float(src.get("x", 0)), float(src.get("y", 0))
        x2, y2 = float(dst.get("x", 0)), float(dst.get("y", 0))
        api.draw_line(x1, y1, x2, y2, fill=edge.get("fill", "#555555"), width=int(edge.get("width", 2)), arrow=edge.get("arrow", "last"))
        if edge.get("label"):
            api.draw_text((x1 + x2) / 2 + 5, (y1 + y2) / 2 + 5, edge.get("label"), font_size=8, fill="#555555")
    for node in nodes:
        x, y = float(node.get("x", 0)), float(node.get("y", 0))
        rx = float(node.get("rx", 42))
        ry = float(node.get("ry", 24))
        api.draw_oval(x - rx, y - ry, x + rx, y + ry, outline=node.get("outline", "#111111"), fill=node.get("fill", "#ffffff"), width=int(node.get("width", 2)))
        api.draw_text(x, y - 8, node.get("label", node.get("id", "node")), font_size=9, anchor="center", bold=True, width=int(rx * 1.8))
        if node.get("type"):
            api.draw_text(x, y + 6, node.get("type"), font_size=7, anchor="center", fill="#777777")
    report = props.get("validation_report", [])
    if report:
        api.draw_text(10, h - 28, "validation: " + "; ".join(map(str, report[-2:])), font_size=8, fill="#777777", width=w - 20)


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    nodes = props.setdefault("nodes", [])
    edges = props.setdefault("edges", [])
    w = int(widget.get("width", 560))
    h = int(widget.get("height", 360))
    if str(props.get("layout", "stored")) == "circular" or any("x" not in node or "y" not in node for node in nodes):
        cx, cy = w / 2, h / 2 + 10
        radius = min(w, h) / 2 - 60
        for index, node in enumerate(nodes):
            angle = 2 * math.pi * index / max(1, len(nodes))
            node["x"] = cx + math.cos(angle) * radius
            node["y"] = cy + math.sin(angle) * radius
    ids = {node.get("id") for node in nodes}
    report = []
    for edge in edges:
        if edge.get("source") not in ids:
            report.append(f"missing source {edge.get('source')}")
        if edge.get("target") not in ids:
            report.append(f"missing target {edge.get('target')}")
    if not report:
        report.append("all edge endpoints valid")
    props["validation_report"] = report
    props["validated_at"] = datetime.datetime.now().replace(microsecond=0).isoformat()
    api.log("Graph/category widget validated: " + "; ".join(report))
'''

APPLIED_MODEL_SIMULATION_WIDGET_PROGRAM = r'''def _safe_env(parameters, state, t, step):
    env = {"math": math, "abs": abs, "min": min, "max": max, "pow": pow, "round": round, "t": t, "step": step}
    env.update(parameters)
    env.update(state)
    return env


def draw(api, widget, page, session):
    props = widget.setdefault("properties", {})
    w = int(widget.get("width", 600))
    h = int(widget.get("height", 380))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    api.draw_text(10, 8, props.get("title", "Applied model and simulation"), font_size=14, bold=True)
    api.draw_text(10, 30, f"type: {props.get('model_type', 'discrete')}   solver: {props.get('solver', 'explicit_euler')}", font_size=9, fill="#555555")
    outputs = props.get("outputs", []) if isinstance(props.get("outputs", []), list) else []
    plot_var = props.get("plot_variable", (props.get("variables") or ["x"])[0])
    plot_x, plot_y, plot_w, plot_h = 54, 70, w - 80, h - 125
    api.draw_rectangle(plot_x, plot_y, plot_x + plot_w, plot_y + plot_h, outline="#dddddd", fill="#fbfbfb", width=1)
    if outputs:
        series = []
        for item in outputs:
            vals = item.get("values", {}) if isinstance(item, dict) else {}
            if plot_var in vals:
                series.append((float(item.get("t", item.get("step", len(series)))), float(vals[plot_var])))
        if series:
            xs = [a for a, b in series]
            ys = [b for a, b in series]
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            if abs(xmax - xmin) < 1e-12:
                xmax = xmin + 1
            if abs(ymax - ymin) < 1e-12:
                ymax = ymin + 1
            pad = (ymax - ymin) * 0.08
            ymin -= pad
            ymax += pad
            points = []
            for x, y in series:
                px = plot_x + (x - xmin) / (xmax - xmin) * plot_w
                py = plot_y + plot_h - (y - ymin) / (ymax - ymin) * plot_h
                points.append((px, py))
            api.draw_polyline(points, fill="#111111", width=2)
            api.draw_text(plot_x, plot_y + plot_h + 8, f"{plot_var}: min={min(ys):.4g}, max={max(ys):.4g}, n={len(series)}", font_size=8, fill="#555555")
    else:
        api.draw_text(plot_x + 12, plot_y + 16, "Run action to simulate and store outputs.", font_size=10, fill="#777777")
    y = h - 45
    api.draw_text(10, y, "parameters: " + json.dumps(props.get("parameters", {}), ensure_ascii=False), font_size=8, fill="#555555", width=w - 20)
    api.draw_text(10, y + 15, "notes: " + str(props.get("experiment_notes", "")), font_size=8, fill="#555555", width=w - 20)


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    model_type = str(props.get("model_type", "discrete")).lower()
    variables = list(props.get("variables", ["x"]))
    parameters = props.get("parameters", {}) if isinstance(props.get("parameters", {}), dict) else {}
    state = {name: float(props.get("initial_conditions", {}).get(name, 0.0)) for name in variables}
    steps = max(1, int(props.get("steps", 80)))
    dt = float(props.get("dt", 0.1))
    outputs = []
    for step in range(steps + 1):
        t = step * dt
        outputs.append({"step": step, "t": t, "values": dict(state)})
        if step == steps:
            break
        env = _safe_env(parameters, state, t, step)
        if model_type in {"ode", "ode_euler", "continuous"}:
            equations = props.get("equations", {}) if isinstance(props.get("equations", {}), dict) else {}
            next_state = dict(state)
            for name in variables:
                rhs = str(equations.get(name, "0"))
                next_state[name] = float(state[name]) + dt * float(eval(rhs, {"__builtins__": {}}, env))
            state = next_state
        else:
            rules = props.get("update_rules", {}) if isinstance(props.get("update_rules", {}), dict) else {}
            next_state = dict(state)
            for name in variables:
                rhs = str(rules.get(name, name))
                next_state[name] = float(eval(rhs, {"__builtins__": {}}, env))
            state = next_state
    props["outputs"] = outputs
    props["simulated_at"] = datetime.datetime.now().replace(microsecond=0).isoformat()
    api.log(f"Simulation completed with {len(outputs)} stored state(s).")
'''

TENSOR_MATRIX_OPERATOR_LAB_WIDGET_PROGRAM = r'''def _cayley(modulus, operation):
    values = list(range(int(modulus)))
    table = []
    for a in values:
        row = []
        for b in values:
            if operation in {"multiplication", "multiply", "mul", "*"}:
                row.append((a * b) % modulus)
            elif operation in {"subtraction", "subtract", "-"}:
                row.append((a - b) % modulus)
            else:
                row.append((a + b) % modulus)
        table.append(row)
    return values, values, table


def draw(api, widget, page, session):
    props = widget.setdefault("properties", {})
    w = int(widget.get("width", 600))
    h = int(widget.get("height", 380))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    api.draw_text(10, 8, props.get("title", "Tensor / matrix / operator lab"), font_size=14, bold=True)
    mode = str(props.get("mode", "matrix"))
    api.draw_text(10, 30, f"mode: {mode}   operation: {props.get('operation', '')}", font_size=9, fill="#555555")
    if mode == "cayley":
        rows = props.get("row_labels") or list(range(int(props.get("modulus", 6))))
        cols = props.get("col_labels") or list(range(int(props.get("modulus", 6))))
        table = props.get("computed_table") or _cayley(int(props.get("modulus", 6)), str(props.get("operation", "addition")))[2]
    else:
        table = props.get("entries", [[1, 0], [0, 1]])
        rows = props.get("row_labels") or list(range(len(table)))
        cols = props.get("col_labels") or list(range(len(table[0]) if table else 0))
    table = table or [[""]]
    nrows = len(table)
    ncols = max(1, max(len(row) for row in table))
    left, top = 40, 60
    cell_w = min(70, max(28, (w - 80) / (ncols + 1)))
    cell_h = min(34, max(20, (h - 130) / (nrows + 1)))
    api.draw_rectangle(left, top, left + cell_w * (ncols + 1), top + cell_h * (nrows + 1), outline="#aaaaaa", fill="", width=1)
    for r in range(nrows + 2):
        y = top + r * cell_h
        api.draw_line(left, y, left + cell_w * (ncols + 1), y, fill="#dddddd", width=1)
    for c in range(ncols + 2):
        x = left + c * cell_w
        api.draw_line(x, top, x, top + cell_h * (nrows + 1), fill="#dddddd", width=1)
    for c in range(ncols):
        api.draw_text(left + (c + 1) * cell_w + 5, top + 5, str(cols[c] if c < len(cols) else c), font_size=8, bold=True)
    for r, row in enumerate(table):
        api.draw_text(left + 5, top + (r + 1) * cell_h + 5, str(rows[r] if r < len(rows) else r), font_size=8, bold=True)
        for c in range(ncols):
            value = row[c] if c < len(row) else ""
            api.draw_text(left + (c + 1) * cell_w + 5, top + (r + 1) * cell_h + 5, str(value), font_size=8)
    computed = props.get("computed_properties", {})
    api.draw_text(10, h - 48, "computed: " + json.dumps(computed, ensure_ascii=False), font_size=8, fill="#555555", width=w - 20)


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    mode = str(props.get("mode", "matrix")).lower()
    computed = {}
    if mode == "cayley":
        modulus = int(props.get("modulus", 6))
        rows, cols, table = _cayley(modulus, str(props.get("operation", "addition")))
        props["row_labels"] = rows
        props["col_labels"] = cols
        props["computed_table"] = table
        computed = {"modulus": modulus, "closed": all(0 <= int(v) < modulus for row in table for v in row), "size": [len(table), len(table[0]) if table else 0]}
    else:
        entries = props.get("entries", [[1, 0], [0, 1]])
        try:
            import sympy as sp
            matrix = sp.Matrix(entries)
            computed = {"shape": [matrix.rows, matrix.cols], "rank": int(matrix.rank())}
            if matrix.rows == matrix.cols:
                computed["determinant"] = str(matrix.det())
                computed["eigenvalues"] = {str(k): int(v) for k, v in matrix.eigenvals().items()}
        except Exception as exc:
            computed = {"shape": [len(entries), len(entries[0]) if entries else 0], "note": "Install sympy for determinant, rank, and eigenvalues.", "error": str(exc)}
    props["computed_properties"] = computed
    props.setdefault("history", []).append({"mode": mode, "computed": computed, "computed_at": datetime.datetime.now().replace(microsecond=0).isoformat()})
    props["history"] = props["history"][-50:]
    api.log("Tensor/matrix/operator lab computed: " + json.dumps(computed, ensure_ascii=False))
'''

RESEARCH_NOTEBOOK_WIDGET_PROGRAM = r'''def draw(api, widget, page, session):
    props = widget.setdefault("properties", {})
    w = int(widget.get("width", 600))
    h = int(widget.get("height", 420))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    api.draw_text(16, 12, props.get("title", "Research notebook"), font_size=18, bold=True, width=w - 32)
    if props.get("author"):
        api.draw_text(16, 38, "by " + str(props.get("author")), font_size=10, fill="#555555")
    y = 64
    api.draw_text(16, y, "Abstract", font_size=12, bold=True)
    y += 18
    api.draw_text(24, y, props.get("abstract", ""), font_size=9, width=w - 48)
    y += 60
    for section in props.get("sections", [])[:5]:
        api.draw_text(16, y, section.get("heading", "Section"), font_size=12, bold=True)
        y += 16
        api.draw_text(24, y, section.get("body", ""), font_size=9, width=w - 48)
        y += 46
        if y > h - 90:
            break
    refs = props.get("references", [])
    if refs:
        api.draw_text(16, h - 64, "References", font_size=11, bold=True)
        api.draw_text(24, h - 46, "; ".join(map(str, refs[:4])), font_size=8, fill="#555555", width=w - 48)
    inv = props.get("page_inventory", [])
    if inv:
        total_widgets = sum(len(item.get("widgets", [])) for item in inv if isinstance(item, dict))
        api.draw_text(16, h - 22, f"inventory: {len(inv)} page(s), {total_widgets} widget record(s)", font_size=8, fill="#777777")


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    inventory = []
    for p in session.get("pages", []):
        record = {"page_id": p.get("page_id"), "title": p.get("title"), "widgets": []}
        for w in p.get("widgets", []):
            wprops = w.get("properties", {}) if isinstance(w.get("properties", {}), dict) else {}
            record["widgets"].append({
                "widget_id": w.get("widget_id"),
                "name": w.get("name"),
                "kind": w.get("kind"),
                "semantic_role": wprops.get("semantic_role", "object"),
                "visible": w.get("visible", True),
            })
        inventory.append(record)
    props["page_inventory"] = inventory
    props["indexed_at"] = datetime.datetime.now().replace(microsecond=0).isoformat()
    api.log(f"Research notebook indexed {len(inventory)} page(s).")
'''

DOCUMENT_EXPORT_CONTROLLER_WIDGET_PROGRAM = r'''def draw(api, widget, page, session):
    props = widget.setdefault("properties", {})
    w = int(widget.get("width", 520))
    h = int(widget.get("height", 300))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    api.draw_rectangle(0, 0, w, 38, outline="#111111", fill="#f4f4f4", width=1)
    api.draw_text(12, 10, "Document Export Controller", font_size=14, bold=True)
    y = 56
    rows = [
        ("title", props.get("title", "")),
        ("author", props.get("author", "")),
        ("page range", props.get("page_range", "all")),
        ("page order", props.get("page_order", [])),
        ("grid", props.get("include_grid", True)),
        ("titles", props.get("include_page_titles", False)),
        ("bounds", props.get("include_widget_bounds", False)),
        ("metadata", props.get("include_metadata", True)),
        ("exclude hidden", props.get("exclude_hidden_widgets", True)),
        ("one file/page", props.get("one_file_per_page", False)),
        ("theorem numbering", props.get("theorem_numbering", "by-page")),
        ("figure numbering", props.get("figure_numbering", "by-page")),
    ]
    for key, value in rows:
        api.draw_text(16, y, str(key), font_size=9, bold=True)
        api.draw_text(140, y, str(value), font_size=9, width=w - 155)
        y += 17
    api.draw_text(16, h - 22, "Run action to write these settings into session.export_settings.pdf.", font_size=8, fill="#777777", width=w - 32)


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    pdf = session.setdefault("export_settings", {}).setdefault("pdf", {})
    pdf.update({
        "title": props.get("title", session.get("title", "")),
        "author": props.get("author", ""),
        "page_range": props.get("page_range", "all"),
        "include_grid": bool(props.get("include_grid", True)),
        "include_page_titles": bool(props.get("include_page_titles", False)),
        "include_widget_bounds": bool(props.get("include_widget_bounds", False)),
        "include_metadata": bool(props.get("include_metadata", True)),
        "exclude_hidden_widgets": bool(props.get("exclude_hidden_widgets", True)),
        "one_file_per_page": bool(props.get("one_file_per_page", False)),
        "native_vector_first": True,
        "image_fallback": bool(props.get("image_fallback", False)),
        "warning_log": True,
    })
    session["title"] = props.get("title", session.get("title", "Untitled mathematics session")) or session.get("title", "Untitled mathematics session")
    props["last_applied_at"] = datetime.datetime.now().replace(microsecond=0).isoformat()
    api.log("Document export settings written to session.export_settings.pdf.")
'''


PLOT3D_WIDGET_PROGRAM = r'''def _float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_eval(expression, local):
    safe_globals = {
        "__builtins__": {},
        "math": math,
        "abs": abs,
        "min": min,
        "max": max,
        "pow": pow,
        "round": round,
    }
    return float(eval(str(expression), safe_globals, local))


def _props(widget):
    p = widget.setdefault("properties", {})
    p.setdefault("title", "Layered 3D mathematical plot")
    p.setdefault("projection", {"azimuth_deg": 45, "elevation_deg": 28, "scale": 1.0})
    p.setdefault("bounds", {"xmin": -1, "xmax": 1, "ymin": -1, "ymax": 1, "zmin": -1, "zmax": 1})
    p.setdefault("structures", [])
    p.setdefault("superimpose", True)
    p.setdefault("layer_strategy", "sort_by_layer")
    p.setdefault("show_axes", True)
    p.setdefault("show_box", True)
    p.setdefault("show_grid_floor", True)
    p.setdefault("render_stats", {})
    return p


def _bounds(p):
    b = p.get("bounds", {}) if isinstance(p.get("bounds", {}), dict) else {}
    xmin = _float(b.get("xmin", -1), -1)
    xmax = _float(b.get("xmax", 1), 1)
    ymin = _float(b.get("ymin", -1), -1)
    ymax = _float(b.get("ymax", 1), 1)
    zmin = _float(b.get("zmin", -1), -1)
    zmax = _float(b.get("zmax", 1), 1)
    if xmax == xmin:
        xmax = xmin + 1
    if ymax == ymin:
        ymax = ymin + 1
    if zmax == zmin:
        zmax = zmin + 1
    return xmin, xmax, ymin, ymax, zmin, zmax


def _projector(widget, p):
    w = int(widget.get("width", 640))
    h = int(widget.get("height", 460))
    xmin, xmax, ymin, ymax, zmin, zmax = _bounds(p)
    cx0 = (xmin + xmax) / 2
    cy0 = (ymin + ymax) / 2
    cz0 = (zmin + zmax) / 2
    span = max(abs(xmax - xmin), abs(ymax - ymin), abs(zmax - zmin), 1e-9)
    proj = p.get("projection", {}) if isinstance(p.get("projection", {}), dict) else {}
    az = math.radians(_float(proj.get("azimuth_deg", 45), 45))
    el = math.radians(_float(proj.get("elevation_deg", 28), 28))
    scale = min(max(60, w - 90), max(60, h - 105)) * _float(proj.get("scale", 1.0), 1.0)
    center_x = w / 2
    center_y = h / 2 + 20

    def project(x, y, z):
        nx = (float(x) - cx0) / span
        ny = (float(y) - cy0) / span
        nz = (float(z) - cz0) / span
        rx = nx * math.cos(az) - ny * math.sin(az)
        ry = nx * math.sin(az) + ny * math.cos(az)
        rz = nz
        ry2 = ry * math.cos(el) - rz * math.sin(el)
        rz2 = ry * math.sin(el) + rz * math.cos(el)
        return center_x + rx * scale, center_y - ry2 * scale, rz2

    return project


def _draw_header(api, widget, p):
    w = int(widget.get("width", 640))
    h = int(widget.get("height", 460))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    api.draw_rectangle(0, 0, w, 38, outline="#111111", fill="#f4f4f4", width=1)
    api.draw_text(12, 10, p.get("title", "3D plot"), font_size=14, bold=True, width=w - 24)
    state = "superimposed" if p.get("superimpose", True) else "layered"
    api.draw_text(12, h - 22, f"3Dplot · {state} · structures: {len(p.get('structures', []))}", font_size=8, fill="#666666", width=w - 24)


def _draw_frame(api, widget, p, project):
    xmin, xmax, ymin, ymax, zmin, zmax = _bounds(p)
    corners = {
        "000": (xmin, ymin, zmin), "100": (xmax, ymin, zmin), "010": (xmin, ymax, zmin), "110": (xmax, ymax, zmin),
        "001": (xmin, ymin, zmax), "101": (xmax, ymin, zmax), "011": (xmin, ymax, zmax), "111": (xmax, ymax, zmax),
    }
    if p.get("show_grid_floor", True):
        steps = 6
        for i in range(steps + 1):
            x = xmin + (xmax - xmin) * i / steps
            a = project(x, ymin, zmin)
            b = project(x, ymax, zmin)
            api.draw_line(a[0], a[1], b[0], b[1], fill="#e3e3e3", width=1)
            y = ymin + (ymax - ymin) * i / steps
            a = project(xmin, y, zmin)
            b = project(xmax, y, zmin)
            api.draw_line(a[0], a[1], b[0], b[1], fill="#e3e3e3", width=1)
    if p.get("show_box", True):
        for a, b in [("000", "100"), ("000", "010"), ("100", "110"), ("010", "110"), ("001", "101"), ("001", "011"), ("101", "111"), ("011", "111"), ("000", "001"), ("100", "101"), ("010", "011"), ("110", "111")]:
            pa = project(*corners[a])
            pb = project(*corners[b])
            api.draw_line(pa[0], pa[1], pb[0], pb[1], fill="#cccccc", width=1)
    if p.get("show_axes", True):
        y0 = 0 if ymin <= 0 <= ymax else (ymin + ymax) / 2
        z0 = 0 if zmin <= 0 <= zmax else (zmin + zmax) / 2
        x0 = 0 if xmin <= 0 <= xmax else (xmin + xmax) / 2
        axes = [((xmin, y0, z0), (xmax, y0, z0), "x"), ((x0, ymin, z0), (x0, ymax, z0), "y"), ((x0, y0, zmin), (x0, y0, zmax), "z")]
        for start, end, label in axes:
            a = project(*start)
            b = project(*end)
            api.draw_line(a[0], a[1], b[0], b[1], fill="#777777", width=1, arrow="last")
            api.draw_text(b[0] + 4, b[1] + 4, label, font_size=10, fill="#555555")


def _draw_surface(api, structure, project):
    xmin = _float(structure.get("xmin", -1), -1)
    xmax = _float(structure.get("xmax", 1), 1)
    ymin = _float(structure.get("ymin", -1), -1)
    ymax = _float(structure.get("ymax", 1), 1)
    xs = max(2, min(80, _int(structure.get("x_samples", 18), 18)))
    ys = max(2, min(80, _int(structure.get("y_samples", 18), 18)))
    expr = structure.get("z", "0")
    style = structure.get("style", {}) if isinstance(structure.get("style", {}), dict) else {}
    stroke = style.get("stroke", "#111111")
    width = _int(style.get("width", 1), 1)
    points = []
    for i in range(xs):
        row = []
        x = xmin + (xmax - xmin) * i / (xs - 1)
        for j in range(ys):
            y = ymin + (ymax - ymin) * j / (ys - 1)
            try:
                z = _safe_eval(expr, {"x": x, "y": y})
                if math.isfinite(z):
                    row.append(project(x, y, z))
                else:
                    row.append(None)
            except Exception:
                row.append(None)
        points.append(row)
    for row in points:
        segment = []
        for item in row:
            if item is None:
                if len(segment) > 1:
                    api.draw_polyline([(a[0], a[1]) for a in segment], fill=stroke, width=width)
                segment = []
            else:
                segment.append(item)
        if len(segment) > 1:
            api.draw_polyline([(a[0], a[1]) for a in segment], fill=stroke, width=width)
    for j in range(ys):
        segment = []
        for i in range(xs):
            item = points[i][j]
            if item is None:
                if len(segment) > 1:
                    api.draw_polyline([(a[0], a[1]) for a in segment], fill=stroke, width=width)
                segment = []
            else:
                segment.append(item)
        if len(segment) > 1:
            api.draw_polyline([(a[0], a[1]) for a in segment], fill=stroke, width=width)
    return xs * ys


def _draw_curve(api, structure, project):
    tmin = _float(structure.get("tmin", 0), 0)
    tmax = _float(structure.get("tmax", 1), 1)
    samples = max(2, min(5000, _int(structure.get("samples", 200), 200)))
    ex = structure.get("x", "t")
    ey = structure.get("y", "0")
    ez = structure.get("z", "0")
    style = structure.get("style", {}) if isinstance(structure.get("style", {}), dict) else {}
    stroke = style.get("stroke", "#111111")
    width = _int(style.get("width", 2), 2)
    segment = []
    count = 0
    for i in range(samples):
        t = tmin + (tmax - tmin) * i / (samples - 1)
        try:
            x = _safe_eval(ex, {"t": t})
            y = _safe_eval(ey, {"t": t})
            z = _safe_eval(ez, {"t": t})
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                raise ValueError("non-finite point")
            px, py, depth = project(x, y, z)
            segment.append((px, py))
            count += 1
        except Exception:
            if len(segment) > 1:
                api.draw_polyline(segment, fill=stroke, width=width, smooth=True)
            segment = []
    if len(segment) > 1:
        api.draw_polyline(segment, fill=stroke, width=width, smooth=True)
    return count


def _draw_points(api, structure, project):
    points = structure.get("points", [])
    style = structure.get("style", {}) if isinstance(structure.get("style", {}), dict) else {}
    stroke = style.get("stroke", "#111111")
    fill = style.get("fill", "#ffffff")
    radius = max(1, _int(style.get("radius", 3), 3))
    count = 0
    for p in points:
        try:
            x, y, z = p[0], p[1], p[2]
            px, py, depth = project(x, y, z)
            api.draw_oval(px - radius, py - radius, px + radius, py + radius, outline=stroke, fill=fill, width=1)
            count += 1
        except Exception:
            continue
    return count


def _draw_vector_field(api, structure, project):
    xmin = _float(structure.get("xmin", -1), -1)
    xmax = _float(structure.get("xmax", 1), 1)
    ymin = _float(structure.get("ymin", -1), -1)
    ymax = _float(structure.get("ymax", 1), 1)
    zmin = _float(structure.get("zmin", 0), 0)
    zmax = _float(structure.get("zmax", 0), 0)
    xs = max(1, min(12, _int(structure.get("x_samples", 4), 4)))
    ys = max(1, min(12, _int(structure.get("y_samples", 4), 4)))
    zs = max(1, min(8, _int(structure.get("z_samples", 1), 1)))
    ex = structure.get("u", "0")
    ey = structure.get("v", "0")
    ez = structure.get("w", "0")
    vector_scale = _float(structure.get("vector_scale", 0.25), 0.25)
    style = structure.get("style", {}) if isinstance(structure.get("style", {}), dict) else {}
    stroke = style.get("stroke", "#444444")
    width = _int(style.get("width", 1), 1)
    count = 0
    for i in range(xs):
        x = xmin + (xmax - xmin) * (i / max(1, xs - 1))
        for j in range(ys):
            y = ymin + (ymax - ymin) * (j / max(1, ys - 1))
            for k in range(zs):
                z = zmin + (zmax - zmin) * (k / max(1, zs - 1))
                try:
                    u = _safe_eval(ex, {"x": x, "y": y, "z": z})
                    v = _safe_eval(ey, {"x": x, "y": y, "z": z})
                    q = _safe_eval(ez, {"x": x, "y": y, "z": z})
                    a = project(x, y, z)
                    b = project(x + u * vector_scale, y + v * vector_scale, z + q * vector_scale)
                    api.draw_line(a[0], a[1], b[0], b[1], fill=stroke, width=width, arrow="last")
                    count += 1
                except Exception:
                    continue
    return count


def draw(api, widget, page, session):
    p = _props(widget)
    _draw_header(api, widget, p)
    project = _projector(widget, p)
    _draw_frame(api, widget, p, project)
    structures = list(p.get("structures", []))
    if p.get("layer_strategy", "sort_by_layer") == "sort_by_layer":
        structures.sort(key=lambda item: (int(item.get("layer", 0)), str(item.get("id", ""))))
    stats = {"drawn_structures": 0, "sampled_items": 0, "types": {}}
    legend_y = 44
    for structure in structures:
        if not isinstance(structure, dict) or not structure.get("enabled", True):
            continue
        stype = str(structure.get("type", "surface")).lower()
        count = 0
        if stype == "surface":
            count = _draw_surface(api, structure, project)
        elif stype in {"parametric_curve", "curve"}:
            count = _draw_curve(api, structure, project)
        elif stype in {"point_cloud", "points"}:
            count = _draw_points(api, structure, project)
        elif stype == "vector_field":
            count = _draw_vector_field(api, structure, project)
        else:
            continue
        stats["drawn_structures"] += 1
        stats["sampled_items"] += count
        stats["types"][stype] = stats["types"].get(stype, 0) + 1
        label = structure.get("label") or structure.get("id") or stype
        layer = structure.get("layer", 0)
        api.draw_text(12, legend_y, f"L{layer} · {label}", font_size=8, fill="#555555", width=int(widget.get("width", 640)) - 24)
        legend_y += 12
    p["render_stats"] = stats


def action(api, widget, page, session):
    p = _props(widget)
    structures = [s for s in p.get("structures", []) if isinstance(s, dict)]
    report = []
    for structure in structures:
        stype = str(structure.get("type", "surface")).lower()
        report.append({
            "id": structure.get("id", "unnamed"),
            "type": stype,
            "enabled": bool(structure.get("enabled", True)),
            "layer": int(structure.get("layer", 0)),
        })
    p["validation_report"] = report
    p["render_stats"] = {
        "structure_count": len(structures),
        "enabled_count": sum(1 for s in structures if s.get("enabled", True)),
        "layers": sorted({int(s.get("layer", 0)) for s in structures}),
        "updated_at": datetime.datetime.now().replace(microsecond=0).isoformat(),
    }
    api.log(f"3Dplot validated {p['render_stats']['enabled_count']} enabled structure(s) across {len(p['render_stats']['layers'])} layer(s).")
'''

CODE_BLOCK_WIDGET_PROGRAM = r'''def _props(widget):
    p = widget.setdefault("properties", {})
    p.setdefault("title", "Source code")
    p.setdefault("language", "text")
    p.setdefault("code", "")
    p.setdefault("start_line", 1)
    p.setdefault("show_line_numbers", True)
    p.setdefault("font_size", 11)
    p.setdefault("line_height", 16)
    p.setdefault("tab_size", 4)
    p.setdefault("background", "#ffffff")
    p.setdefault("gutter_fill", "#f4f4f4")
    p.setdefault("border_fill", "#111111")
    p.setdefault("text_fill", "#111111")
    p.setdefault("line_number_fill", "#777777")
    p.setdefault("wrap", False)
    p.setdefault("metadata", {})
    return p


def _visible_lines(code, width_chars, wrap):
    raw_lines = str(code or "").splitlines() or [""]
    if not wrap:
        return raw_lines
    output = []
    width_chars = max(8, int(width_chars))
    for line in raw_lines:
        expanded = line
        while len(expanded) > width_chars:
            output.append(expanded[:width_chars])
            expanded = "    " + expanded[width_chars:]
        output.append(expanded)
    return output


def draw(api, widget, page, session):
    p = _props(widget)
    w = int(widget.get("width", 600))
    h = int(widget.get("height", 360))
    font_size = int(p.get("font_size", 11))
    line_height = max(font_size + 3, int(p.get("line_height", 16)))
    title_h = 34
    footer_h = 18
    show_numbers = bool(p.get("show_line_numbers", True))
    start_line = int(p.get("start_line", 1))
    tab_size = max(1, int(p.get("tab_size", 4)))
    code = str(p.get("code", "")).replace("	", " " * tab_size)
    gutter_w = 58 if show_numbers else 10
    api.draw_rectangle(0, 0, w, h, outline=p.get("border_fill", "#111111"), fill=p.get("background", "#ffffff"), width=2)
    api.draw_rectangle(0, 0, w, title_h, outline=p.get("border_fill", "#111111"), fill="#f4f4f4", width=1)
    api.draw_text(10, 9, p.get("title", "Source code"), font_size=13, bold=True, width=w - 20)
    api.draw_text(w - 110, 10, str(p.get("language", "text")), font_size=9, fill="#555555")
    body_top = title_h
    body_bottom = h - footer_h
    if show_numbers:
        api.draw_rectangle(0, body_top, gutter_w, body_bottom, outline="", fill=p.get("gutter_fill", "#f4f4f4"), width=0)
        api.draw_line(gutter_w, body_top, gutter_w, body_bottom, fill="#dddddd", width=1)
    approx_chars = max(12, int((w - gutter_w - 14) / max(6, font_size * 0.58)))
    lines = _visible_lines(code, approx_chars, bool(p.get("wrap", False)))
    max_lines = max(1, int((body_bottom - body_top - 8) / line_height))
    y = body_top + 7
    for index, line in enumerate(lines[:max_lines]):
        number = start_line + index
        if show_numbers:
            api.draw_text(6, y, str(number).rjust(4), font_size=font_size, fill=p.get("line_number_fill", "#777777"), font_family="Consolas")
        api.draw_text(gutter_w + 8, y, line, font_size=font_size, fill=p.get("text_fill", "#111111"), font_family="Consolas", width=w - gutter_w - 14)
        y += line_height
    hidden = max(0, len(lines) - max_lines)
    footer = f"{len(str(code).splitlines() or [''])} line(s)"
    if hidden:
        footer += f" · {hidden} hidden below widget height"
    api.draw_text(10, h - 15, footer, font_size=8, fill="#777777", width=w - 20)


def action(api, widget, page, session):
    p = _props(widget)
    code = str(p.get("code", ""))
    p["metadata"] = {
        "language": p.get("language", "text"),
        "line_count": len(code.splitlines() or [""]),
        "character_count": len(code),
        "updated_at": datetime.datetime.now().replace(microsecond=0).isoformat(),
    }
    api.log(f"Code block indexed {p['metadata']['line_count']} line(s).")
'''

PNG_IMAGE_WIDGET_PROGRAM = r'''def draw(api, widget, page, session):
    props = widget.get("properties", {})
    w = max(1, int(widget.get("width", 360)))
    h = max(1, int(widget.get("height", 240)))
    padding = min(max(0, int(props.get("padding", 8))), (min(w, h) - 1) // 2)
    background = str(props.get("background", ""))
    if background:
        api.draw_rectangle(0, 0, w, h, fill=background, outline="", width=0)
    path = str(props.get("path", ""))
    data = str(props.get("data_base64", ""))
    if path or data:
        api.draw_image(padding, padding, path=path, width=w - 2 * padding, height=h - 2 * padding,
                       fit=str(props.get("fit", "contain")), anchor=str(props.get("anchor", "center")),
                       data_base64=data)
    else:
        api.draw_text(padding + 4, padding + 4,
                      "PNG Image\nUse Widget > Replace Selected PNG Image, or set properties.path.",
                      font_size=12, fill="#777777", width=max(1, w - 2 * padding - 8))
    border = str(props.get("border_color", "#dddddd"))
    border_width = max(0, int(props.get("border_width", 1)))
    if border and border_width:
        api.draw_rectangle(0, 0, w, h, fill="", outline=border, width=border_width)


def action(api, widget, page, session):
    api.log("PNG Image: use Widget > Replace Selected PNG Image to embed a file. "
            "Set path and clear data_base64 to link a file. Configure fit (contain/cover/stretch), "
            "anchor, padding, background, border_color and border_width in Properties JSON.")
'''


TEXT_WIDGET_PROGRAM = r'''def draw(api, widget, page, session):
    props = widget.get("properties", {})
    text = props.get("text", "Text")
    font_size = int(props.get("font_size", 24))
    fill = props.get("fill", "#111111")
    anchor = props.get("anchor", "nw")
    api.draw_text(0, 0, text, font_size=font_size, fill=fill, anchor=anchor, width=int(widget.get("width", 300)))


def action(api, widget, page, session):
    api.log("Text widget action executed. Edit properties.text to change the object.")
'''

FORMULA_WIDGET_PROGRAM = r'''def draw(api, widget, page, session):
    props = widget.get("properties", {})
    formula = props.get("formula", "∀x ∈ ℝ, |x| ≥ 0")
    font_size = int(props.get("font_size", 26))
    fill = props.get("fill", "#111111")
    api.draw_rectangle(0, 0, widget.get("width", 420), widget.get("height", 80), outline="#dddddd", fill="")
    api.draw_text(12, 12, formula, font_size=font_size, fill=fill, width=int(widget.get("width", 420)) - 24)


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    props["formula"] = props.get("formula", "∀x ∈ ℝ, |x| ≥ 0")
    api.log("Formula widget action checked the formula property.")
'''

GRAPH_WIDGET_PROGRAM = r'''def draw(api, widget, page, session):
    props = widget.get("properties", {})
    expression = props.get("expression", "math.sin(x)")
    xmin = float(props.get("xmin", -6.28318))
    xmax = float(props.get("xmax", 6.28318))
    ymin = float(props.get("ymin", -1.5))
    ymax = float(props.get("ymax", 1.5))
    samples = int(props.get("samples", 240))
    title = props.get("title", f"y = {expression}")
    api.draw_rectangle(0, 0, widget.get("width", 430), widget.get("height", 280), outline="#111111", fill="")
    api.draw_grid(step=40, fill="#eeeeee")
    api.draw_axes(xmin, xmax, ymin, ymax, fill="#777777", width=1)
    api.plot_function(expression, xmin, xmax, ymin, ymax, samples=samples, fill="#111111", width=2)
    api.draw_text(8, 8, title, font_size=13, fill="#111111")


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    old = props.get("expression", "math.sin(x)")
    props["expression"] = old
    api.log(f"Graph expression is {old}")
'''

RECTANGLE_WIDGET_PROGRAM = r'''def draw(api, widget, page, session):
    props = widget.get("properties", {})
    outline = props.get("outline", "#111111")
    fill = props.get("fill", "")
    stroke_width = int(props.get("stroke_width", 2))
    label = props.get("label", "")
    font_size = int(props.get("font_size", 16))
    api.draw_rectangle(0, 0, widget.get("width", 220), widget.get("height", 120), outline=outline, fill=fill, width=stroke_width)
    if label:
        api.draw_text(10, 10, label, font_size=font_size, fill=outline, width=int(widget.get("width", 220)) - 20)


def action(api, widget, page, session):
    api.log("Rectangle widget action executed.")
'''

LINE_WIDGET_PROGRAM = r'''def draw(api, widget, page, session):
    props = widget.get("properties", {})
    fill = props.get("fill", "#111111")
    stroke_width = int(props.get("stroke_width", 3))
    arrow = props.get("arrow", "last")
    label = props.get("label", "")
    w = int(widget.get("width", 260))
    h = int(widget.get("height", 60))
    api.draw_line(0, h / 2, w, h / 2, fill=fill, width=stroke_width, arrow=arrow)
    if label:
        api.draw_text(8, 2, label, font_size=13, fill=fill)


def action(api, widget, page, session):
    api.log("Line widget action executed.")
'''

FREE_PROGRAM_WIDGET_PROGRAM = r'''def draw(api, widget, page, session):
    w = int(widget.get("width", 360))
    h = int(widget.get("height", 220))
    title = widget.get("properties", {}).get("title", "custom widget")
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="")
    api.draw_text(10, 10, title, font_size=18, fill="#111111")
    api.draw_text(10, 42, "Edit this widget program to draw any mathematical object.", font_size=12, fill="#555555", width=w - 20)
    cx, cy = w / 2, h / 2 + 20
    r = min(w, h) / 5
    api.draw_oval(cx - r, cy - r, cx + r, cy + r, outline="#111111", width=2)
    api.draw_line(cx - r, cy, cx + r, cy, fill="#111111", width=1)
    api.draw_line(cx, cy - r, cx, cy + r, fill="#111111", width=1)


def action(api, widget, page, session):
    api.log("Free program widget action executed. Use api.create_widget, api.update_widget, and api.delete_widget for CRUD.")
'''

TABLE_WIDGET_PROGRAM = r'''def draw(api, widget, page, session):
    props = widget.get("properties", {})
    rows = max(1, int(props.get("rows", 5)))
    cols = max(1, int(props.get("cols", 5)))
    title = props.get("title", "operation table")
    w = int(widget.get("width", 410))
    h = int(widget.get("height", 260))
    title_h = 28
    cell_w = w / cols
    cell_h = (h - title_h) / rows
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="")
    api.draw_text(8, 5, title, font_size=14, fill="#111111")
    for r in range(rows + 1):
        y = title_h + r * cell_h
        api.draw_line(0, y, w, y, fill="#aaaaaa", width=1)
    for c in range(cols + 1):
        x = c * cell_w
        api.draw_line(x, title_h, x, h, fill="#aaaaaa", width=1)
    for r in range(rows):
        for c in range(cols):
            value = props.get("cell_text", "i,j")
            if value == "i,j":
                text = f"{r},{c}"
            elif value == "sum":
                text = str(r + c)
            elif value == "product":
                text = str(r * c)
            else:
                text = str(value)
            api.draw_text(c * cell_w + 5, title_h + r * cell_h + 4, text, font_size=10, fill="#111111")


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    props["cell_text"] = props.get("cell_text", "i,j")
    api.log("Table widget action checked cell_text. Try i,j, sum, or product.")
'''

WORDSEARCH_WIDGET_PROGRAM = r'''def _rows(props):
    grid = props.get("grid", [])
    rows = []
    for row in grid:
        if isinstance(row, str):
            rows.append(list(row.strip()))
        elif isinstance(row, list):
            rows.append([str(cell or " ")[:1].upper() for cell in row])
    return rows


def _int(props, name, default, low=None, high=None):
    try:
        value = int(float(props.get(name, default)))
    except Exception:
        value = int(default)
    if low is not None:
        value = max(int(low), value)
    if high is not None:
        value = min(int(high), value)
    return value


def _bool(props, name, default=False):
    value = props.get(name, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _text(props, name, default=""):
    value = props.get(name, default)
    return default if value is None else str(value)


def _column_words(words, columns):
    words = [str(word) for word in words if str(word).strip()]
    columns = max(1, int(columns or 1))
    per_column = max(1, (len(words) + columns - 1) // columns)
    return [words[index:index + per_column] for index in range(0, len(words), per_column)] or [[]]


def _has_blank_grid(props):
    rows = _rows(props)
    size = max(1, int(props.get("grid_size") or len(rows) or 1))
    if not rows:
        return True
    for row in range(size):
        if row >= len(rows):
            return True
        for col in range(size):
            if col >= len(rows[row]) or not str(rows[row][col]).strip():
                return True
    return False


def _regenerate(props):
    source = props.get("source_words") or props.get("words", [])
    data = build_wordsearch_data(
        source,
        size=int(props.get("grid_size", 20) or 20),
        seed=props.get("seed") or None,
        max_size=int(props.get("max_grid_size", 40) or 40),
        directions=props.get("directions", None),
        max_attempts=int(props.get("max_attempts", 16) or 16),
        filler_alphabet=str(props.get("filler_alphabet", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")),
    )
    for key, value in data.items():
        props[key] = value
    props["auto_generate"] = True
    props["placement_mode"] = "intelligent"
    return data


def _draw_header(api, props, w):
    body_font = _text(props, "body_font_family", "Helvetica")
    title_size = _int(props, "title_font_size", 12, 1, 96)
    subtitle_size = _int(props, "subtitle_font_size", 11, 1, 96)
    title = _text(props, "title", "Word search")
    subtitle = _text(props, "subtitle", "")
    align = _text(props, "header_align", "center").lower()
    if align == "left":
        x = 0
        anchor = "nw"
    else:
        x = w / 2
        anchor = "n"
    y = 0
    api.draw_text(x, y, title, font_size=title_size, fill=_text(props, "title_fill", "#111111"), anchor=anchor, font_family=body_font, bold=True, width=w)
    y += title_size + 4
    if subtitle:
        api.draw_text(x, y, subtitle, font_size=subtitle_size, fill=_text(props, "subtitle_fill", "#666666"), anchor=anchor, font_family=body_font, bold=False, width=w)
        y += subtitle_size + 4
    y += _int(props, "header_padding_bottom", 10, 0, 80)
    border_width = _int(props, "header_border_width", 2, 0, 12)
    if border_width:
        api.draw_line(0, y, w, y, fill=_text(props, "header_border_fill", "#f0f0f0"), width=border_width)
    return y + _int(props, "header_margin_bottom", 20, 0, 120)


def _draw_solution_highlights(api, props, gx, gy, cell):
    highlight = _text(props, "solution_highlight_fill", "#e0e0e0")
    seen = set()
    for positions in props.get("word_positions", {}).values():
        if not isinstance(positions, list):
            continue
        for position in positions:
            try:
                row = int(position[0])
                col = int(position[1])
            except Exception:
                continue
            key = (row, col)
            if key in seen:
                continue
            seen.add(key)
            inset = max(1, cell * 0.06)
            api.draw_rectangle(
                gx + col * cell + inset,
                gy + row * cell + inset,
                gx + (col + 1) * cell - inset,
                gy + (row + 1) * cell - inset,
                outline="",
                fill=highlight,
                width=0,
            )


def on_create(api, widget, page, session):
    _regenerate(widget.setdefault("properties", {}))


def validate(api, widget, page, session):
    props = widget.setdefault("properties", {})
    if props.get("auto_generate", True) or _has_blank_grid(props):
        _regenerate(props)
    props["placement_mode"] = "intelligent"
    return True


def draw(api, widget, page, session):
    props = widget.get("properties", {})
    w = int(widget.get("width", 694))
    h = int(widget.get("height", 1010))
    rows = _rows(props)
    size = max(1, int(props.get("grid_size") or len(rows) or 1))
    if rows:
        size = max(size, len(rows), max(len(row) for row in rows))

    api.draw_rectangle(0, 0, w, h, outline="", fill=_text(props, "background_fill", "#ffffff"), width=0)
    grid_top = _draw_header(api, props, w)

    bottom_reserved = 0
    if props.get("show_word_bank", True):
        display_words = props.get("display_words", {}) if isinstance(props.get("display_words", {}), dict) else {}
        bank_words = [display_words.get(str(word), str(word)) for word in props.get("words", [])]
        columns = _int(props, "word_list_columns", 4, 1, 8)
        lines_per_column = max(1, (len(bank_words) + columns - 1) // columns)
        word_font_size = _int(props, "word_list_font_size", 8, 1, 96)
        word_padding = _int(props, "word_list_padding_bottom", 4, 0, 80)
        bottom_reserved = lines_per_column * (word_font_size + word_padding + 2)
        if _bool(props, "show_word_list_label", False):
            bottom_reserved += word_font_size + 10
        bottom_reserved += _int(props, "grid_margin_bottom", 15, 0, 120) + _int(props, "word_list_margin_top", 20, 0, 120)

    available_w = max(16, w)
    available_h = max(16, h - grid_top - bottom_reserved)
    grid_w = min(available_w, available_h)
    cell = max(4, grid_w / size)
    grid_w = cell * size
    gx = (w - grid_w) / 2
    gy = grid_top

    api.draw_rectangle(gx, gy, gx + grid_w, gy + grid_w, outline=_text(props, "grid_border_fill", "#cccccc"), fill=_text(props, "grid_fill", "#ffffff"), width=_int(props, "grid_border_width", 1, 0, 12))

    if _bool(props, "grid_inner_lines", False):
        for i in range(size + 1):
            p = i * cell
            api.draw_line(gx + p, gy, gx + p, gy + grid_w, fill="#d0d0d0", width=1)
            api.draw_line(gx, gy + p, gx + grid_w, gy + p, fill="#d0d0d0", width=1)

    if props.get("show_solution", False):
        _draw_solution_highlights(api, props, gx, gy, cell)

    letter_font_size = _int(props, "grid_letter_font_size", 14, 1, 96)
    if props.get("show_solution", False) and _bool(props, "solution_compact_letters", False):
        letter_font_size = _int(props, "solution_letter_font_size", 6, 1, 96)
    for r in range(size):
        row = rows[r] if r < len(rows) else []
        for c in range(size):
            ch = row[c] if c < len(row) else ""
            api.draw_text(
                gx + c * cell + cell / 2,
                gy + r * cell + cell / 2 - letter_font_size * 0.45,
                ch,
                font_size=letter_font_size,
                fill=_text(props, "grid_letter_fill", "#000000"),
                anchor="center",
                font_family=_text(props, "grid_letter_font_family", "monospace"),
            )

    if props.get("show_word_bank", True):
        y = gy + grid_w + _int(props, "grid_margin_bottom", 15, 0, 120) + _int(props, "word_list_margin_top", 20, 0, 120)
        display_words = props.get("display_words", {}) if isinstance(props.get("display_words", {}), dict) else {}
        bank_words = [display_words.get(str(word), str(word)) for word in props.get("words", [])]
        if _bool(props, "word_list_uppercase", True):
            bank_words = [str(word).upper() for word in bank_words]
        columns = _int(props, "word_list_columns", 4, 1, 8)
        column_gap = _int(props, "word_list_column_gap", 25, 0, 120)
        side_pad = 0
        column_width = max(8, (w - side_pad * 2 - column_gap * (columns - 1)) / columns)
        word_font_size = _int(props, "word_list_font_size", 8, 1, 96)
        word_padding = _int(props, "word_list_padding_bottom", 4, 0, 80)
        body_font = _text(props, "body_font_family", "Helvetica")
        if _bool(props, "show_word_list_label", False):
            api.draw_text(w / 2, y, "Word bank", font_size=word_font_size, fill=_text(props, "body_fill", "#333333"), anchor="n", font_family=body_font, bold=True)
            y += word_font_size + 10
        for col_index, column in enumerate(_column_words(bank_words, columns)[:columns]):
            x = side_pad + col_index * (column_width + column_gap)
            yy = y
            for word in column:
                api.draw_text(x + column_width / 2, yy, word, font_size=word_font_size, fill=_text(props, "word_list_fill", "#000000"), anchor="n", font_family=body_font, width=int(column_width))
                yy += word_font_size + word_padding + 2
        skipped = props.get("skipped_words", [])
        if skipped:
            api.draw_text(0, h - 24, "Unplaced: " + ", ".join(map(str, skipped)), font_size=8, fill="#b00020", width=w)


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    _regenerate(props)
    api.log(f"Word search regenerated: {len(props.get('word_positions', {}))}/{len(props.get('words', []))} word(s) placed.")
'''

CROSSWORD_WIDGET_PROGRAM = r'''def _grid(props):
    raw = props.get("grid", [])
    rows = []
    for row in raw:
        if isinstance(row, str):
            rows.append([ch if ch != "." else "" for ch in row])
        elif isinstance(row, list):
            rows.append([str(cell or "").upper()[:1] for cell in row])
    return rows


def _draw_clue_list(api, title, clues, x, y, width, max_items=12):
    api.draw_text(x, y, title, font_size=11, bold=True)
    y += 17
    for clue in list(clues or [])[:max_items]:
        api.draw_text(x + 4, y, clue, font_size=8, width=width - 8)
        y += 24
    return y


def _regenerate(props):
    source = props.get("source_entries") or props.get("entries", [])
    data = build_crossword_data(
        source,
        size=None,
        seed=props.get("seed") or None,
        max_size=int(props.get("max_grid_size", 48) or 48),
        attempts=int(props.get("attempts", 120) or 120),
        allow_disconnected=bool(props.get("allow_disconnected", False)),
    )
    for key, value in data.items():
        props[key] = value
    props["placement_mode"] = "intelligent"
    return data


def on_create(api, widget, page, session):
    props = widget.setdefault("properties", {})
    if props.get("auto_generate", True) and props.get("placement_mode", "intelligent") != "manual":
        _regenerate(props)


def validate(api, widget, page, session):
    props = widget.setdefault("properties", {})
    if props.get("auto_generate", True) and props.get("placement_mode", "intelligent") != "manual":
        _regenerate(props)
    return True


def draw(api, widget, page, session):
    props = widget.get("properties", {})
    w = int(widget.get("width", 690))
    h = int(widget.get("height", 870))
    grid = _grid(props)
    rows = max(1, len(grid))
    cols = max(1, max((len(row) for row in grid), default=1))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    api.draw_text(18, 14, props.get("title", "Crossword"), font_size=20, bold=True, width=w - 36)
    subtitle = str(props.get("subtitle", ""))
    if subtitle:
        api.draw_text(18, 42, subtitle, font_size=11, fill="#555555", width=w - 36)
    top = 72
    grid_area_h = min(h * 0.54, h - 260)
    cell = max(10, min((w - 48) / cols, grid_area_h / rows))
    grid_w = cell * cols
    grid_h = cell * rows
    gx = (w - grid_w) / 2
    gy = top
    numbers = props.get("number_map", {}) if isinstance(props.get("number_map", {}), dict) else {}
    for r in range(rows):
        row = grid[r] if r < len(grid) else []
        for c in range(cols):
            ch = row[c] if c < len(row) else ""
            x = gx + c * cell
            y = gy + r * cell
            if ch:
                api.draw_rectangle(x, y, x + cell, y + cell, outline="#111111", fill="#ffffff", width=1)
                key = f"{r},{c}"
                if key in numbers:
                    api.draw_text(x + 2, y + 1, numbers[key], font_size=max(5, int(cell * 0.22)), fill="#555555")
                if props.get("show_solution", False):
                    api.draw_text(x + cell / 2, y + cell / 2 - 6, ch, font_size=max(8, int(cell * 0.44)), anchor="center", bold=True)
            else:
                api.draw_rectangle(x, y, x + cell, y + cell, outline="#111111", fill="#111111", width=1)
    clue_y = gy + grid_h + 18
    half = (w - 54) / 2
    _draw_clue_list(api, "Across", props.get("across_clues", []), 18, clue_y, half)
    _draw_clue_list(api, "Down", props.get("down_clues", []), 36 + half, clue_y, half)
    unplaced = props.get("unplaced", [])
    if unplaced:
        api.draw_text(18, h - 24, "Unplaced: " + ", ".join(map(str, unplaced)), font_size=8, fill="#b00020", width=w - 36)


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    _regenerate(props)
    props["auto_generate"] = True
    total = len(props.get("across_clues", [])) + len(props.get("down_clues", []))
    api.log(f"Crossword regenerated: {total} clue(s), {len(props.get('unplaced', []))} unplaced word(s).")
'''

MULTIPLE_CHOICE_QUIZ_WIDGET_PROGRAM = r'''def _wrap(text, width):
    words = str(text or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def draw(api, widget, page, session):
    props = widget.get("properties", {})
    w = int(widget.get("width", 690))
    h = int(widget.get("height", 870))
    questions = list(props.get("questions", []))
    columns = max(1, min(2, int(props.get("columns", 1))))
    show_answers = bool(props.get("show_answers", False))
    api.draw_rectangle(0, 0, w, h, outline="#111111", fill="#ffffff", width=2)
    api.draw_text(18, 14, props.get("title", "Multiple choice quiz"), font_size=20, bold=True, width=w - 36)
    subtitle = str(props.get("subtitle", ""))
    if subtitle:
        api.draw_text(18, 42, subtitle, font_size=11, fill="#555555", width=w - 36)
    col_w = (w - 42) / columns
    y_starts = [76 for _ in range(columns)]
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for index, question in enumerate(questions, start=1):
        col = (index - 1) % columns
        x = 18 + col * col_w
        y = y_starts[col]
        if y > h - 80:
            api.draw_text(x, h - 34, f"{len(questions) - index + 1} more question(s) continue beyond this widget.", font_size=8, fill="#b00020", width=col_w - 12)
            break
        qtext = question.get("question", f"Question {index}") if isinstance(question, dict) else str(question)
        answer_index = int(question.get("answer_index", 0)) if isinstance(question, dict) else 0
        choices = question.get("choices", []) if isinstance(question, dict) else []
        api.draw_text(x, y, f"{index}.", font_size=10, bold=True)
        line_y = y
        for line in _wrap(qtext, max(18, int((col_w - 34) / 6))):
            api.draw_text(x + 22, line_y, line, font_size=10, bold=True, width=col_w - 34)
            line_y += 14
        line_y += 3
        for choice_index, choice in enumerate(choices):
            prefix = labels[choice_index] if choice_index < len(labels) else str(choice_index + 1)
            marker = ""
            fill = "#111111"
            if show_answers and choice_index == answer_index:
                marker = " [answer]"
                fill = "#0b63ce"
            choice_text = f"{prefix}. {choice}{marker}"
            for line in _wrap(choice_text, max(18, int((col_w - 28) / 6))):
                api.draw_text(x + 18, line_y, line, font_size=9, fill=fill, width=col_w - 28)
                line_y += 13
        if show_answers and isinstance(question, dict) and question.get("explanation"):
            line_y += 2
            for line in _wrap("Explanation: " + str(question.get("explanation", "")), max(18, int((col_w - 28) / 6))):
                api.draw_text(x + 18, line_y, line, font_size=8, fill="#555555", width=col_w - 28)
                line_y += 12
        y_starts[col] = line_y + 12


def action(api, widget, page, session):
    props = widget.setdefault("properties", {})
    source = props.get("source_questions") or props.get("questions", [])
    props["questions"] = normalize_quiz_questions(
        source,
        shuffle_choices=bool(props.get("shuffle_choices", False)),
        shuffle_questions=bool(props.get("shuffle_questions", False)),
        seed=props.get("seed") or None,
        min_choices=int(props.get("min_choices", 2) or 2),
    )
    props["source_questions"] = source
    api.log(f"Quiz normalized: {len(props.get('questions', []))} question(s).")
'''

PAGE_GENERATOR_TEMPLATE = r"""# Save this as a .py file and run it with Generators > Run Generator Script.
# Paths in api.load_lines/load_sections/load_pairs are relative to this script's folder.

def get_info():
    return {
        "name": "Mathematics puzzle book generator",
        "version": "1.0.0",
        "required_content_files": [
            "content/word-lists.txt",
            "content/crossword-list.txt",
        ],
    }


def generate(api):
    api.reset_book("Generated mathematics puzzle book")

    cover = api.current_page()
    api.configure_page(cover, title="Cover")
    api.add_text(
        "Generated Mathematics Puzzle Book",
        x=80,
        y=120,
        width=640,
        height=120,
        font_size=30,
        fill="#111111",
    )
    api.add_text(
        "Created programmatically from a page generator script.",
        x=84,
        y=230,
        width=600,
        height=70,
        font_size=16,
        fill="#555555",
    )

    word_lists = [
        ["algebra", "matrix", "vector", "proof", "axiom", "function", "domain", "range"],
        ["limit", "series", "integral", "derivative", "tensor", "curve", "angle", "logic"],
    ]
    for index, words in enumerate(word_lists, start=1):
        page = api.new_page(f"Word Search {index}")
        api.add_wordsearch(
            f"Word Search {index}",
            words,
            page=page,
            seed=index,
            subtitle="Find each mathematics term.",
        )

    crossword_entries = [
        ("axiom", "A statement accepted as true"),
        ("proof", "A logical argument"),
        ("matrix", "A rectangular array of entries"),
        ("vector", "A quantity with magnitude and direction"),
        ("limit", "The value approached by a function or sequence"),
        ("graph", "A collection of vertices and edges"),
    ]
    page = api.new_page("Crossword")
    api.add_crossword("Mathematics Crossword", crossword_entries, page=page)

    questions = [
        {
            "question": "Which object has magnitude and direction?",
            "choices": ["Scalar", "Vector", "Set", "Table"],
            "answer_index": 1,
            "explanation": "A vector carries both size and direction.",
        },
        {
            "question": "What is the additive identity?",
            "choices": ["0", "1", "-1", "x"],
            "answer_index": 0,
            "explanation": "Adding 0 leaves a number unchanged.",
        },
        {
            "question": "Which word describes a logical argument for a claim?",
            "choices": ["Graph", "Proof", "Angle", "Range"],
            "answer_index": 1,
        },
    ]
    page = api.new_page("Quiz")
    api.add_multiple_choice_quiz("Mathematics Multiple Choice", questions, page=page)

    api.log("Puzzle book generated.")
"""

PLUGIN_TEMPLATE = r"""# Save this as a .py file inside a plugin directory.
# Load it with Plugins > Load Plugin Directory. Loaded templates become JSON-persistent.
# Kinds without ':' are automatically namespaced with MANIFEST["id"].
# Widget programs may use api.describe(), api.get_property(), drawing calls,
# and api.create_widget/read_widget/update_widget/delete_widget when not exporting.

MANIFEST = {
    "id": "unit_circle_demo",
    "version": "1.0.0",
    "author": "Your name",
    "requires_api": ">=1.0.0,<2.0.0",
}

def register(api):
    api.register_widget(
        kind="unit_circle",
        name="Unit Circle",
        width=280,
        height=280,
        properties={"label": "x² + y² = 1"},
        properties_schema={
            "label": {
                "type": "string",
                "default": "x² + y² = 1",
                "description": "Equation label drawn in the upper-left corner.",
            }
        },
        description="A programmable unit-circle widget.",
        program=r'''
def on_create(api, widget, page, session):
    api.set_property("label", api.get_property("label", "x² + y² = 1"))


def validate(api, widget, page, session):
    if not str(api.get_property("label", "")).strip():
        return "Unit circle label cannot be empty."
    return True


def draw(api, widget, page, session):
    w = int(widget.get("width", 280))
    h = int(widget.get("height", 280))
    r = min(w, h) / 2 - 18
    cx = w / 2
    cy = h / 2
    api.draw_rectangle(0, 0, w, h, outline="#dddddd", fill="")
    api.draw_line(cx - r, cy, cx + r, cy, fill="#777777", width=1, arrow="both")
    api.draw_line(cx, cy + r, cx, cy - r, fill="#777777", width=1, arrow="both")
    api.draw_oval(cx - r, cy - r, cx + r, cy + r, outline="#111111", width=2)
    api.draw_text(12, 12, widget.get("properties", {}).get("label", "x² + y² = 1"), font_size=16)

def action(api, widget, page, session):
    api.log("Unit circle plugin action executed.")
'''
    )
"""

def main() -> None:
    app = WhiteboardApp()
    app.mainloop()


if __name__ == "__main__":
    main()
