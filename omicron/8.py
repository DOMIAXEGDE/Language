"""
Graphical Codex CLI-REPL OS - Tkinter Edition

A pure-stdlib Tkinter kernel shell where services are controlled only through
commands submitted to the blue CLI engine. The interface keeps the Codex data
model from the graphical editor but converts the application into a general
purpose, kernel-based, API-routable REPL operating surface.

Run:
    python graphical_codex_cli_repl_os.py

Core rule:
    Only the REPL Console and the blue CLI engine are visible. Kernel services
    can only activate or execute through commands submitted to the blue engine.
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import itertools
import json
import os
import re
import shlex
import shutil
import subprocess
import tkinter as tk
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


INITIAL_CODEX_NODES = [
    {
        "id": "project.manifest",
        "label": "ProjectManifest",
        "type": "root",
        "status": "accepted",
        "description": "Top-level project control object: language targets, package layout, build commands, release rules, and CI gates.",
    },
    {
        "id": "policy.security",
        "label": "SecurityPolicy",
        "type": "policy",
        "status": "locked",
        "description": "Controls filesystem boundaries, shell access, dependency permissions, and unsafe operation rejection.",
    },
    {
        "id": "schema.layer",
        "label": "Schema Layer",
        "type": "schema",
        "status": "accepted",
        "description": "JSON schemas for characters, lines, blocks, files, patches, diagnostics, and runtime reports.",
    },
    {
        "id": "module.registry",
        "label": "Module Registry",
        "type": "module",
        "status": "accepted",
        "description": "Reusable character rules, line templates, block modules, class modules, methods, tests, and emit-ready files.",
    },
    {
        "id": "emitter.backend.cpp",
        "label": "C++ Emitter",
        "type": "emitter",
        "status": "warning",
        "description": "Deterministic JSON-to-C++ source compiler with formatting, include ordering, and hash reporting.",
    },
    {
        "id": "diagnostics.runtime",
        "label": "Diagnostics Runtime",
        "type": "diagnostic",
        "status": "error",
        "description": "Build, lint, test, static analysis, and runtime failures returned as DiagnosticManifest objects.",
    },
]

INITIAL_FILE_TREE = [
    {"path": "codex_project/project_manifest.json", "kind": "ProjectManifest", "state": "source-of-truth"},
    {"path": "codex_project/policies/security_policy.json", "kind": "SecurityPolicy", "state": "locked"},
    {"path": "codex_project/schemas/block_module.schema.json", "kind": "Schema", "state": "valid"},
    {"path": "codex_project/modules/classes/hardware_controller.block.json", "kind": "BlockModule", "state": "editable"},
    {"path": "codex_project/modules/files/main.file.json", "kind": "FileManifest", "state": "editable"},
    {"path": "codex_project/emitted/src/main.cpp", "kind": "Emitted Source", "state": "generated-only"},
    {"path": "codex_project/reports/diagnostic_manifest.json", "kind": "DiagnosticManifest", "state": "runtime-feedback"},
]

INITIAL_DIAGNOSTICS = [
    {
        "severity": "error",
        "target": "hardware_controller.block.json",
        "message": "Method start_device references undefined dependency DeviceBus.",
    },
    {
        "severity": "warning",
        "target": "main.file.json",
        "message": "Generated include order differs from current policy ordering rule.",
    },
    {
        "severity": "accepted",
        "target": "security_policy.json",
        "message": "Filesystem output restricted to ./emitted and ./reports.",
    },
]

MANIFEST_PREVIEW = {
    "id": "hardware_editor.project.v1",
    "type": "ProjectManifest",
    "project_name": "Graphical Codex CLI-REPL OS",
    "targets": ["cpp", "python", "verilog", "api"],
    "source_of_truth": "json_graphical_codex",
    "direct_source_editing": False,
    "activation_boundary": "blue_cli_repl_command_only",
    "kernel_model": {
        "service_manager": True,
        "api_gateway": True,
        "repl_bus": True,
        "event_log": True,
        "capability_gates": True,
        "linux_terminal": True,
        "powershell_7": True,
    },
    "control_surfaces": {
        "character_rules": True,
        "line_templates": True,
        "block_modules": True,
        "file_manifests": True,
        "patch_manifests": True,
        "diagnostics": True,
        "emitter_plugins": True,
        "api_routes": True,
        "kernel_services": True,
        "linux_terminal": True,
        "powershell_7": True,
    },
    "validation_gates": [
        "schema",
        "policy",
        "reference_integrity",
        "dependency_policy",
        "emission_hash",
        "service_activation_command",
    ],
}

STATUS_LABELS = {
    "accepted": "Accepted",
    "locked": "Locked",
    "warning": "Warning",
    "error": "Repair",
    "valid": "Valid",
    "editable": "Editable",
    "source-of-truth": "Source",
    "generated-only": "Generated",
    "runtime-feedback": "Feedback",
    "active": "Active",
    "dormant": "Dormant",
    "faulted": "Faulted",
}

TYPE_SYMBOLS = {
    "root": "[ROOT]",
    "policy": "[POLICY]",
    "schema": "[SCHEMA]",
    "module": "[MODULE]",
    "emitter": "[EMITTER]",
    "diagnostic": "[DIAG]",
}


CONFIGURE4_SERVICE_ID = "configure_4.authoring.fabric"
CONFIGURE4_LABEL = "Configure4AuthoringFabric"
CONFIGURE4_ALLOWED_MODES = ("manual", "semi_auto", "auto")
CONFIGURE4_ALLOWED_FLOW_TYPES = ("literal", "template", "cartesian", "repeat", "reverse", "service_scaffold")
CONFIGURE4_ALLOWED_PERSISTENCE_POLICIES = ("memory_only", "manifest", "manifest_and_export", "disabled")
CONFIGURE4_ALLOWED_FILE_POLICIES = ("none", "read_explicit", "write_explicit", "read_write_explicit", "manifest_only")
CONFIGURE4_ALLOWED_SIDE_EFFECT_POLICIES = ("none", "memory_only", "manifest_only", "explicit_filesystem", "runtime_registration")
CONFIGURE4_GENERIC_HANDLER_NAME = "generic_configure4_service_handler"
CONFIGURE4_GENERIC_API_HANDLER_NAME = "generic_configure4_api_handler"
CONFIGURE4_MAX_VARIANTS = 256
CONFIGURE4_MAX_DRAFTS = 128
CONFIGURE4_MAX_HISTORY = 500

QUADTREE_DESKTOP_SERVICE_ID = "quadtree.desktop"
QUADTREE_DESKTOP_LABEL = "QuadtreeDesktop"
QUADTREE_DESKTOP_ID = "qdt.desktop.main"
QUADTREE_DESKTOP_VERSION = "0.1.0"
QUADTREE_LAYER_TYPES = ("input", "processing", "output")
QUADTREE_QUADRANTS = ("nw", "ne", "sw", "se")
QUADTREE_VALIDATION_MODES = ("schema_only", "policy_only", "full", "preview_only")
QUADTREE_APPLY_MODES = ("stage", "apply", "apply_and_snapshot")
QUADTREE_MAX_DEPTH_LIMIT = 8
QUADTREE_EVENT_LIMIT = 500
QUADTREE_DEFAULT_MODULE_IDS = (
    "qdt.system.services",
    "qdt.system.api",
    "qdt.codex.graph",
    "qdt.codex.files",
    "qdt.codex.diagnostics",
    "qdt.codex.emission",
    "qdt.runtime.terminal",
    "qdt.runtime.memory",
    "qdt.configure4.authoring",
    "qdt.desktop.output",
)

CONFIGURE4_MODE_ALIASES = {
    "manual": "manual",
    "semi": "semi_auto",
    "semi-auto": "semi_auto",
    "semi_auto": "semi_auto",
    "semi-automatic": "semi_auto",
    "semiautomatic": "semi_auto",
    "auto": "auto",
    "automatic": "auto",
}

CONFIGURE4_FIELD_ALIASES = {
    "id": "identity.service_id",
    "service": "identity.service_id",
    "service_id": "identity.service_id",
    "name": "identity.label",
    "label": "identity.label",
    "aliases": "identity.aliases",
    "layer": "identity.layer",
    "state": "identity.state",
    "description": "identity.description",
    "version": "identity.version",
    "commands": "command_surface.verbs",
    "command_verbs": "command_surface.verbs",
    "verbs": "command_surface.verbs",
    "handler": "command_surface.handler_name",
    "handler_name": "command_surface.handler_name",
    "help": "command_surface.help_text",
    "help_text": "command_surface.help_text",
    "default_payload": "command_surface.default_payload",
    "api_routes": "api_surface.routes",
    "routes": "api_surface.routes",
    "api_handler": "api_surface.handler_name",
    "api_handler_name": "api_surface.handler_name",
    "payload_schema": "api_surface.payload_schema",
    "output_schema": "api_surface.output_schema",
    "activation_requirements": "execution_behavior.activation_requirements",
    "dependency_requirements": "execution_behavior.dependency_requirements",
    "dependencies": "execution_behavior.dependency_requirements",
    "allowed_modes": "execution_behavior.allowed_modes",
    "timeout_policy": "execution_behavior.timeout_policy",
    "file_access_policy": "execution_behavior.file_access_policy",
    "side_effect_policy": "execution_behavior.side_effect_policy",
    "can_register_immediately": "execution_behavior.can_register_immediately",
    "register_immediately": "execution_behavior.can_register_immediately",
    "validation_gates": "validation_rules.gates",
    "allow_command_collisions": "validation_rules.allow_command_collisions",
    "persistence_policy": "persistence_behavior.policy",
    "import_path": "persistence_behavior.import_path",
    "export_path": "persistence_behavior.export_path",
    "versioning_policy": "persistence_behavior.versioning_policy",
    "flow": "generated_code_plan.flow",
    "flow_type": "generated_code_plan.flow.type",
    "input_value": "generated_code_plan.flow.input_value",
    "input_width": "generated_code_plan.flow.input_width",
    "template": "generated_code_plan.flow.template",
    "output_target": "generated_code_plan.flow.output_target",
    "prefix": "generated_code_plan.flow.prefix",
    "suffix": "generated_code_plan.flow.suffix",
    "separator": "generated_code_plan.flow.separator",
}

CONFIGURE4_MANUAL_REQUIRED_PATHS = (
    "identity.service_id",
    "identity.label",
    "identity.aliases",
    "identity.layer",
    "identity.state",
    "identity.description",
    "identity.version",
    "command_surface.verbs",
    "command_surface.handler_name",
    "command_surface.help_text",
    "command_surface.default_payload",
    "api_surface.routes",
    "api_surface.handler_name",
    "api_surface.payload_schema",
    "api_surface.output_schema",
    "execution_behavior.activation_requirements",
    "execution_behavior.dependency_requirements",
    "execution_behavior.allowed_modes",
    "execution_behavior.timeout_policy",
    "execution_behavior.file_access_policy",
    "execution_behavior.side_effect_policy",
    "execution_behavior.can_register_immediately",
    "validation_rules.gates",
    "validation_rules.allow_command_collisions",
    "persistence_behavior.policy",
    "persistence_behavior.import_path",
    "persistence_behavior.export_path",
    "persistence_behavior.versioning_policy",
    "examples",
    "generated_code_plan.flow.type",
    "generated_code_plan.handler_name",
    "generated_code_plan.api_handler_name",
    "generated_code_plan.runtime_strategy",
    "metadata.owner",
    "object_graph",
)


def configure4_normalize_mode(value: object) -> str:
    key = str(value).strip().lower().replace(" ", "-")
    return CONFIGURE4_MODE_ALIASES.get(key, key)


def configure4_slug_words(text: object) -> list[str]:
    raw = str(text or "").lower()
    words = re.findall(r"[a-z0-9]+", raw)
    stop_words = {
        "a",
        "an",
        "and",
        "as",
        "build",
        "create",
        "for",
        "from",
        "make",
        "new",
        "service",
        "that",
        "the",
        "to",
        "with",
    }
    return [word for word in words if word not in stop_words]


def configure4_pascal_label(value: object) -> str:
    words = configure4_slug_words(value)
    if not words:
        return "GeneratedService"
    return "".join(word[:1].upper() + word[1:] for word in words)


def configure4_dotted_id(value: object, *, prefix: str = "codex") -> str:
    words = configure4_slug_words(value)
    if not words:
        words = ["generated", "service"]
    parts = [prefix] + words[:3]
    if parts[-1] != "service" and len(parts) < 4:
        parts.append("service")
    return ".".join(parts)


@dataclass
class Configure4FabricRecord:
    kind: str
    name: str
    role: str = ""
    value: object = ""
    links: list[str] = field(default_factory=list)
    state: str = "staged"

    @classmethod
    def from_dict(cls, payload: object) -> "Configure4FabricRecord":
        if not isinstance(payload, dict):
            return cls(kind="object", name="unnamed")
        return cls(
            kind=str(payload.get("kind", "object")),
            name=str(payload.get("name", "unnamed")),
            role=str(payload.get("role", "")),
            value=copy.deepcopy(payload.get("value", "")),
            links=[str(item) for item in payload.get("links", [])] if isinstance(payload.get("links", []), list) else [],
            state=str(payload.get("state", "staged")),
        )

    def to_dict(self) -> dict[str, object]:
        return copy.deepcopy(asdict(self))


@dataclass
class Configure4Spec:
    draft_id: str
    mode: str
    identity: dict[str, object] = field(default_factory=dict)
    command_surface: dict[str, object] = field(default_factory=dict)
    api_surface: dict[str, object] = field(default_factory=dict)
    execution_behavior: dict[str, object] = field(default_factory=dict)
    validation_rules: dict[str, object] = field(default_factory=dict)
    persistence_behavior: dict[str, object] = field(default_factory=dict)
    examples: list[object] = field(default_factory=list)
    generated_code_plan: dict[str, object] = field(default_factory=dict)
    diagnostics: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    object_graph: list[dict[str, object]] = field(default_factory=list)
    custom_fields: dict[str, object] = field(default_factory=dict)
    inferred_fields: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: object) -> "Configure4Spec":
        if not isinstance(payload, dict):
            payload = {}
        draft_id = str(payload.get("draft_id", "draft_000"))
        mode = configure4_normalize_mode(payload.get("mode", "manual"))
        object_graph = []
        for item in payload.get("object_graph", []):
            record = Configure4FabricRecord.from_dict(item)
            object_graph.append(record.to_dict())
        return cls(
            draft_id=draft_id,
            mode=mode if mode in CONFIGURE4_ALLOWED_MODES else "manual",
            identity=copy.deepcopy(payload.get("identity", {})) if isinstance(payload.get("identity", {}), dict) else {},
            command_surface=copy.deepcopy(payload.get("command_surface", {})) if isinstance(payload.get("command_surface", {}), dict) else {},
            api_surface=copy.deepcopy(payload.get("api_surface", {})) if isinstance(payload.get("api_surface", {}), dict) else {},
            execution_behavior=copy.deepcopy(payload.get("execution_behavior", {})) if isinstance(payload.get("execution_behavior", {}), dict) else {},
            validation_rules=copy.deepcopy(payload.get("validation_rules", {})) if isinstance(payload.get("validation_rules", {}), dict) else {},
            persistence_behavior=copy.deepcopy(payload.get("persistence_behavior", {})) if isinstance(payload.get("persistence_behavior", {}), dict) else {},
            examples=copy.deepcopy(payload.get("examples", [])) if isinstance(payload.get("examples", []), list) else [],
            generated_code_plan=copy.deepcopy(payload.get("generated_code_plan", {})) if isinstance(payload.get("generated_code_plan", {}), dict) else {},
            diagnostics=copy.deepcopy(payload.get("diagnostics", [])) if isinstance(payload.get("diagnostics", []), list) else [],
            metadata=copy.deepcopy(payload.get("metadata", {})) if isinstance(payload.get("metadata", {}), dict) else {},
            object_graph=object_graph,
            custom_fields=copy.deepcopy(payload.get("custom_fields", {})) if isinstance(payload.get("custom_fields", {}), dict) else {},
            inferred_fields=[str(item) for item in payload.get("inferred_fields", [])] if isinstance(payload.get("inferred_fields", []), list) else [],
        )

    def to_dict(self) -> dict[str, object]:
        return copy.deepcopy(asdict(self))


class Configure4Sink:
    name = "abstract"

    def write(self, text: str) -> bool:
        raise NotImplementedError

    def write_json(self, payload: object) -> bool:
        return self.write(json.dumps(payload, indent=2))

    def getvalue(self) -> str:
        return ""

    def close(self) -> None:
        return None


class Configure4MemorySink(Configure4Sink):
    name = "memory"

    def __init__(self) -> None:
        self.parts: list[str] = []

    def write(self, text: str) -> bool:
        self.parts.append(str(text))
        return True

    def getvalue(self) -> str:
        return "".join(self.parts)


class Configure4ConsoleSink(Configure4MemorySink):
    name = "console"

    def __init__(self, writer: object | None = None) -> None:
        super().__init__()
        self.writer = writer

    def write(self, text: str) -> bool:
        super().write(text)
        if callable(self.writer):
            self.writer(str(text))
        return True


class Configure4FilePreviewSink(Configure4MemorySink):
    name = "file-preview"

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path

    def preview(self) -> dict[str, str]:
        return {"target": self.path, "content": self.getvalue()}


class Configure4JsonSink(Configure4MemorySink):
    name = "json"

    def __init__(self) -> None:
        super().__init__()
        self.payloads: list[object] = []

    def write_json(self, payload: object) -> bool:
        self.payloads.append(copy.deepcopy(payload))
        return super().write_json(payload)

    def latest(self) -> object:
        return copy.deepcopy(self.payloads[-1]) if self.payloads else None


class Theme:
    bg = "#07070a"
    panel = "#101014"
    panel_2 = "#15151b"
    card = "#0b0b10"
    card_2 = "#181820"
    field = "#030306"
    border = "#2b2b34"
    border_active = "#d8d8e0"
    text = "#f4f4f7"
    muted = "#a9a9b4"
    faint = "#6f6f7c"
    blue = "#07118f"
    blue_2 = "#0b1caf"
    blue_3 = "#1027d7"
    blue_text = "#ffffff"
    green = "#8de0a5"
    yellow = "#f5d071"
    red = "#ff9ca3"
    purple = "#c9c3ff"
    cyan = "#85d8f5"


STATUS_COLORS = {
    "accepted": ("#11291c", Theme.green, "#245f39"),
    "locked": ("#1a2436", "#9bb7f4", "#344866"),
    "warning": ("#322710", Theme.yellow, "#6e541d"),
    "error": ("#351719", Theme.red, "#7b3037"),
    "valid": ("#11291c", Theme.green, "#245f39"),
    "editable": ("#202035", Theme.purple, "#565083"),
    "source-of-truth": ("#11252c", Theme.cyan, "#28596a"),
    "generated-only": ("#2b2032", "#e9b7ff", "#61456f"),
    "runtime-feedback": ("#351719", Theme.red, "#7b3037"),
    "active": ("#102d1b", Theme.green, "#2e7a48"),
    "dormant": ("#17171d", Theme.muted, "#383844"),
    "faulted": ("#351719", Theme.red, "#7b3037"),
}


class ScrollFrame(tk.Frame):
    def __init__(self, parent: tk.Widget, *, background: str = Theme.panel, **kwargs) -> None:
        super().__init__(parent, bg=background, **kwargs)
        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=background)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel_windows)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux)

    def _on_frame_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel_windows(self, event: tk.Event) -> None:
        if self.winfo_containing(event.x_root, event.y_root) is not None:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event: tk.Event) -> None:
        if self.winfo_containing(event.x_root, event.y_root) is None:
            return
        direction = -1 if event.num == 4 else 1
        self.canvas.yview_scroll(direction, "units")


class GraphicalCodexCliReplOS(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Graphical Codex CLI-REPL OS - Console Only")
        self.geometry("1180x760")
        self.minsize(760, 420)
        self.configure(bg=Theme.bg)

        self.nodes = copy.deepcopy(INITIAL_CODEX_NODES)
        self.files = copy.deepcopy(INITIAL_FILE_TREE)
        self.diagnostics = copy.deepcopy(INITIAL_DIAGNOSTICS)
        self.manifest = copy.deepcopy(MANIFEST_PREVIEW)
        self.versions: list[dict[str, str]] = []
        self.vars: dict[str, str] = {}
        self.history: list[str] = []
        self.history_index: int | None = None
        self.event_log: list[dict[str, str]] = []
        self.terminal_cwd = Path.cwd()
        self.terminal_timeout_seconds = 30
        self.linux_shell = shutil.which("bash") or shutil.which("sh") or ""
        self.pwsh_executable = shutil.which("pwsh") or shutil.which("pwsh.exe") or ""
        self.selected_service_id = "blue.cli.engine"
        self.selected_node_id = self.nodes[0]["id"]
        self.configure4_state = self._create_configure4_state()
        self.quadtreeDesktop_state = self._create_quadtree_desktop_state()
        self.shell_frame: tk.Frame | None = None
        self.console_card: tk.Frame | None = None
        self.quadtree_desktop_frame: tk.Frame | None = None
        self.quadtree_canvas: tk.Canvas | None = None
        self.quadtree_inspector_text: ScrolledText | None = None
        self.quadtree_module_text: ScrolledText | None = None
        self.quadtree_batch_text: ScrolledText | None = None
        self.quadtree_preview_text: ScrolledText | None = None
        self.quadtree_layer_var: tk.StringVar | None = None
        self.command_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Booting blue CLI engine...")
        self.clock_var = tk.StringVar(value="")

        self._setup_fonts()
        self._setup_styles()
        self.services = self._create_services()
        self.api_routes = self._create_api_routes()
        self._build_ui()
        self._render_all()
        self._boot_console()
        self._tick_clock()

    def _setup_fonts(self) -> None:
        self.font_title = ("Segoe UI", 24, "bold")
        self.font_h2 = ("Segoe UI", 14, "bold")
        self.font_h3 = ("Segoe UI", 10, "bold")
        self.font_body = ("Segoe UI", 10)
        self.font_small = ("Segoe UI", 9)
        self.font_micro = ("Segoe UI", 8, "bold")
        self.font_mono = ("Consolas", 10)
        self.font_prompt = ("Consolas", 12, "bold")

    def _setup_styles(self) -> None:
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure(
            "Vertical.TScrollbar",
            background=Theme.card_2,
            troughcolor=Theme.panel,
            bordercolor=Theme.panel,
            arrowcolor=Theme.muted,
            relief="flat",
        )
        self.style.map("Vertical.TScrollbar", background=[("active", Theme.blue_2)])
        self.style.configure(
            "Kernel.TCombobox",
            fieldbackground=Theme.field,
            background=Theme.field,
            foreground=Theme.text,
            arrowcolor=Theme.text,
            bordercolor=Theme.border,
        )

    def _create_services(self) -> dict[str, dict[str, object]]:
        specs = [
            (
                "blue.cli.engine",
                "repl",
                "active",
                "The command gate. It is the only execution path that may activate or execute kernel services.",
                ["help", "service.activate api.gateway", "service.list"],
            ),
            (
                "kernel.clock",
                "kernel",
                "dormant",
                "Provides monotonic timestamps and wall-clock metadata to API and diagnostic reports.",
                ["service.activate kernel.clock", "service.exec kernel.clock now"],
            ),
            (
                "kernel.memory",
                "kernel",
                "dormant",
                "Stores REPL variables, staged values, and small JSON payloads for later API calls.",
                ["service.activate kernel.memory", "set build_mode debug", "get build_mode"],
            ),
            (
                "kernel.fs",
                "kernel",
                "dormant",
                "Persists and loads manifest snapshots through explicit REPL commands.",
                ["service.activate kernel.fs", "manifest.save", "manifest.load"],
            ),
            (
                "kernel.terminal.linux",
                "kernel",
                "dormant",
                "Inherited Linux terminal service. Executes host shell commands only after REPL activation.",
                ["service.activate kernel.terminal.linux", "linux pwd", "linux ls -la", "terminal.cwd"],
            ),
            (
                "kernel.terminal.powershell7",
                "kernel",
                "dormant",
                "Inherited PowerShell 7 service. Executes pwsh commands only after REPL activation, when pwsh is installed.",
                ["service.activate kernel.terminal.powershell7", "pwsh $PSVersionTable.PSVersion", "pwsh Get-ChildItem", "terminal.cwd"],
            ),
            (
                "api.gateway",
                "api",
                "dormant",
                "Routes REPL-submitted API calls to activated services through local endpoints.",
                ["service.activate api.gateway", "api.list", "api.call /kernel/services"],
            ),
            (
                "codex.manifest",
                "codex",
                "dormant",
                "Owns the source-of-truth project manifest and exported JSON graph state.",
                ["service.activate codex.manifest", "manifest.show", "api.call /codex/manifest"],
            ),
            (
                "codex.graph",
                "codex",
                "dormant",
                "Manages graphical codex nodes, file objects, selections, and object creation.",
                ["service.activate codex.graph", "node.list", "node.select project.manifest"],
            ),
            (
                "codex.validator",
                "codex",
                "dormant",
                "Runs schema, policy, reference, dependency, and emission-hash gates.",
                ["service.activate codex.validator", "node.validate all", "api.call /codex/validate"],
            ),
            (
                "codex.emitter",
                "codex",
                "dormant",
                "Emits deterministic source previews from accepted JSON graphical objects.",
                ["service.activate codex.emitter", "emit.preview", "api.call /codex/emit"],
            ),
            (
                "codex.builder",
                "codex",
                "dormant",
                "Builds from emitted state and returns build reports as REPL text and API JSON.",
                ["service.activate codex.builder", "build.run", "api.call /codex/build"],
            ),
            (
                "diagnostics.runtime",
                "runtime",
                "dormant",
                "Converts build, lint, static analysis, and runtime failures into repair diagnostics.",
                ["service.activate diagnostics.runtime", "diagnostics.list", "diagnostics.patch"],
            ),
            (
                "version.ledger",
                "runtime",
                "dormant",
                "Captures immutable snapshots of the current kernel, API, and codex state.",
                ["service.activate version.ledger", "version.snapshot", "version.list"],
            ),
            (
                CONFIGURE4_SERVICE_ID,
                "kernel/codex-authoring",
                "dormant",
                "Authors, validates, previews, registers, exports, imports, and persists new services for start.py through blue CLI commands only.",
                [
                    f"service.activate {CONFIGURE4_SERVICE_ID}",
                    "configure4.help",
                    "configure4.sample",
                    "configure4.status",
                ],
            ),
            (
                QUADTREE_DESKTOP_SERVICE_ID,
                "kernel/codex-graphical",
                "dormant",
                "Maps start.py services, routes, manifest objects, diagnostics, Configure4 drafts, batches, and outputs onto a programmable quadtree desktop.",
                [
                    f"service.activate {QUADTREE_DESKTOP_SERVICE_ID}",
                    "quadtree.desktop.status",
                    "quadtree.desktop.show",
                    "quadtree.desktop.module.list",
                ],
            ),
        ]
        services: dict[str, dict[str, object]] = {}
        for service_id, layer, state, description, examples in specs:
            services[service_id] = {
                "id": service_id,
                "layer": layer,
                "state": state,
                "description": description,
                "examples": examples,
                "activated_at": "boot" if state == "active" else "",
                "last_result": "",
                "calls": 0,
            }
        if CONFIGURE4_SERVICE_ID in services:
            services[CONFIGURE4_SERVICE_ID]["label"] = CONFIGURE4_LABEL
        if QUADTREE_DESKTOP_SERVICE_ID in services:
            services[QUADTREE_DESKTOP_SERVICE_ID]["label"] = QUADTREE_DESKTOP_LABEL
        if "kernel.terminal.linux" in services:
            services["kernel.terminal.linux"]["executable"] = self.linux_shell or "<missing bash/sh>"
            services["kernel.terminal.linux"]["available"] = bool(self.linux_shell)
        if "kernel.terminal.powershell7" in services:
            services["kernel.terminal.powershell7"]["executable"] = self.pwsh_executable or "<missing pwsh>"
            services["kernel.terminal.powershell7"]["available"] = bool(self.pwsh_executable)
        return services

    def _create_api_routes(self) -> dict[str, dict[str, object]]:
        return {
            "/kernel/status": {"service": "blue.cli.engine", "description": "Return high-level REPL OS status.", "handler": self.api_kernel_status},
            "/kernel/services": {"service": "blue.cli.engine", "description": "Return every service and activation state.", "handler": self.api_kernel_services},
            "/kernel/events": {"service": "blue.cli.engine", "description": "Return recent REPL event log entries.", "handler": self.api_kernel_events},
            "/terminal/linux": {"service": "kernel.terminal.linux", "description": "Execute a Linux shell command through the inherited terminal service.", "handler": self.api_terminal_linux},
            "/terminal/powershell7": {"service": "kernel.terminal.powershell7", "description": "Execute a PowerShell 7 command through the inherited pwsh service.", "handler": self.api_terminal_powershell7},
            "/codex/manifest": {"service": "codex.manifest", "description": "Return the manifest and selected mode.", "handler": self.api_codex_manifest},
            "/codex/nodes": {"service": "codex.graph", "description": "Return graphical codex nodes.", "handler": self.api_codex_nodes},
            "/codex/files": {"service": "codex.graph", "description": "Return file configuration records.", "handler": self.api_codex_files},
            "/codex/diagnostics": {"service": "diagnostics.runtime", "description": "Return diagnostic manifest items.", "handler": self.api_diagnostics},
            "/codex/validate": {"service": "codex.validator", "description": "Run project validation and return a report.", "handler": self.api_validate},
            "/codex/emit": {"service": "codex.emitter", "description": "Return deterministic emitted source preview.", "handler": self.api_emit},
            "/codex/build": {"service": "codex.builder", "description": "Run build report generation.", "handler": self.api_build},
            "/version/snapshot": {"service": "version.ledger", "description": "Create and return a version snapshot.", "handler": self.api_version_snapshot},
            "/configure4/status": {"service": CONFIGURE4_SERVICE_ID, "description": "Return configure_4 authoring fabric status.", "handler": self.api_configure4_status},
            "/configure4/specs": {"service": CONFIGURE4_SERVICE_ID, "description": "Return configure_4 staged service specifications.", "handler": self.api_configure4_specs},
            "/configure4/validate": {"service": CONFIGURE4_SERVICE_ID, "description": "Validate a configure_4 draft or all drafts.", "handler": self.api_configure4_validate},
            "/configure4/preview": {"service": CONFIGURE4_SERVICE_ID, "description": "Preview a configure_4 integration plan.", "handler": self.api_configure4_preview},
            "/configure4/register": {"service": CONFIGURE4_SERVICE_ID, "description": "Register a configure_4 draft when runtime-safe.", "handler": self.api_configure4_register},
            "/quadtreeDesktop/status": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Return quadtree desktop status.", "handler": self.api_quadtree_desktop_status},
            "/quadtreeDesktop/modules": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Return quadtree desktop modules.", "handler": self.api_quadtree_desktop_modules},
            "/quadtreeDesktop/modules/<module-id>": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Return one quadtree module by payload module_id.", "handler": self.api_quadtree_desktop_module},
            "/quadtreeDesktop/layers/<module-id>/<layer-type>": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Return one quadtree layer by payload module_id and layer_type.", "handler": self.api_quadtree_desktop_layer},
            "/quadtreeDesktop/cells/<cell-address>": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Return one quadtree cell by payload address.", "handler": self.api_quadtree_desktop_cell},
            "/quadtreeDesktop/selection": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Return or set quadtree selection.", "handler": self.api_quadtree_desktop_selection},
            "/quadtreeDesktop/batches": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Return quadtree batch registry.", "handler": self.api_quadtree_desktop_batches},
            "/quadtreeDesktop/validate": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Validate quadtree desktop state or patch payload.", "handler": self.api_quadtree_desktop_validate},
            "/quadtreeDesktop/preview": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Preview a quadtree desktop operation.", "handler": self.api_quadtree_desktop_preview},
            "/quadtreeDesktop/apply": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Apply a validated quadtree desktop operation.", "handler": self.api_quadtree_desktop_apply},
            "/quadtreeDesktop/export": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Export quadtree desktop manifest data.", "handler": self.api_quadtree_desktop_export},
            "/quadtreeDesktop/import": {"service": QUADTREE_DESKTOP_SERVICE_ID, "description": "Import quadtree desktop manifest data.", "handler": self.api_quadtree_desktop_import},
        }

    def _build_ui(self) -> None:
        """Build the locked console-only surface.

        The shell intentionally exposes only two visual surfaces:
        1. the REPL Console, where all inspection/results appear, and
        2. the blue CLI engine, the only command submission/activation gate.
        No service panels, route panels, quick-command palettes, dialogs, or
        status bars are mounted in the visible interface.
        """
        shell = tk.Frame(self, bg=Theme.bg, padx=14, pady=14)
        shell.pack(fill="both", expand=True)
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        self.shell_frame = shell

        console_card = self.card(shell, padx=12, pady=12)
        console_card.grid(row=0, column=0, sticky="nsew")
        console_card.rowconfigure(1, weight=1)
        console_card.columnconfigure(0, weight=1)
        self.console_card = console_card

        console_head = tk.Frame(console_card, bg=Theme.panel)
        console_head.grid(row=0, column=0, sticky="ew")
        console_head.columnconfigure(0, weight=1)
        tk.Label(
            console_head,
            text="REPL CONSOLE",
            bg=Theme.panel,
            fg=Theme.muted,
            font=self.font_micro,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.command_gate_label = tk.Label(
            console_head,
            text="blue.cli.engine: ACTIVE",
            bg=Theme.panel,
            fg=Theme.green,
            font=self.font_micro,
            anchor="e",
        )
        self.command_gate_label.grid(row=0, column=1, sticky="e")

        self.console = ScrolledText(
            console_card,
            bg="#000000",
            fg=Theme.text,
            insertbackground=Theme.text,
            relief="flat",
            font=self.font_mono,
            wrap="word",
            padx=12,
            pady=12,
            height=28,
        )
        self.console.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        self.console.tag_configure("cmd", foreground=Theme.cyan)
        self.console.tag_configure("ok", foreground=Theme.green)
        self.console.tag_configure("warn", foreground=Theme.yellow)
        self.console.tag_configure("err", foreground=Theme.red)
        self.console.tag_configure("json", foreground=Theme.purple)
        self.console.tag_configure("muted", foreground=Theme.muted)
        self.console.configure(state="disabled")

        self._build_blue_cli_engine(console_card)

    def _build_header(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=0)
        title_block = tk.Frame(parent, bg=Theme.panel_2)
        title_block.grid(row=0, column=0, sticky="ew")

        tk.Label(
            title_block,
            text="KERNEL + API CONTROL SURFACE  |  all services activate by blue CLI REPL command only",
            bg=Theme.panel_2,
            fg=Theme.cyan,
            font=self.font_micro,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="Graphical Codex CLI-REPL OS",
            bg=Theme.panel_2,
            fg=Theme.text,
            font=self.font_title,
            anchor="w",
        ).pack(anchor="w", pady=(4, 3))
        tk.Label(
            title_block,
            text=(
                "A general purpose local REPL operating shell with a kernel service registry, local API gateway, "
                "Codex object graph, manifest persistence, diagnostics, emission, build reports, and version snapshots. "
                "The surrounding UI can inspect and stage commands, but the blue CLI engine is the only execution path."
            ),
            bg=Theme.panel_2,
            fg=Theme.muted,
            font=self.font_small,
            wraplength=880,
            justify="left",
            anchor="w",
        ).pack(anchor="w")

        indicators = self.card(parent, bg=Theme.card, padx=12, pady=10)
        indicators.grid(row=0, column=1, sticky="ne", padx=(18, 0))
        tk.Label(indicators, text="BOOT STATE", bg=Theme.card, fg=Theme.faint, font=self.font_micro).pack(anchor="w")
        self.active_count_label = tk.Label(indicators, bg=Theme.card, fg=Theme.green, font=self.font_h2, anchor="w")
        self.active_count_label.pack(fill="x", pady=(5, 0))
        tk.Label(indicators, textvariable=self.clock_var, bg=Theme.card, fg=Theme.muted, font=self.font_small, anchor="w").pack(fill="x")

    def _build_left_panel(self, parent: tk.Frame) -> None:
        top = tk.Frame(parent, bg=Theme.panel)
        top.pack(fill="x")
        tk.Label(top, text="KERNEL SERVICES", bg=Theme.panel, fg=Theme.muted, font=self.font_micro).pack(side="left")
        tk.Label(top, text="inspect only", bg=Theme.panel, fg=Theme.faint, font=self.font_small).pack(side="right")

        self.service_filter_var = tk.StringVar(value="")
        filter_box = tk.Frame(parent, bg=Theme.field, bd=1, relief="solid")
        filter_box.pack(fill="x", pady=(10, 8))
        tk.Label(filter_box, text="filter", bg=Theme.field, fg=Theme.faint, font=self.font_small, padx=8).pack(side="left")
        tk.Entry(
            filter_box,
            textvariable=self.service_filter_var,
            bg=Theme.field,
            fg=Theme.text,
            insertbackground=Theme.text,
            relief="flat",
            font=self.font_small,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8), pady=8)
        self.service_filter_var.trace_add("write", lambda *_: self.render_service_list())

        self.service_list = ScrollFrame(parent, background=Theme.panel)
        self.service_list.pack(fill="both", expand=True)

        note = self.card(parent, bg=Theme.card, padx=10, pady=10)
        note.pack(fill="x", pady=(10, 0))
        tk.Label(note, text="COMMAND BOUNDARY", bg=Theme.card, fg=Theme.cyan, font=self.font_micro).pack(anchor="w")
        tk.Label(
            note,
            text="Selecting a service only inspects it. Activation requires a command such as service.activate codex.graph submitted in the blue CLI engine.",
            bg=Theme.card,
            fg=Theme.muted,
            font=self.font_small,
            wraplength=265,
            justify="left",
        ).pack(anchor="w", pady=(5, 0))

    def _build_center_panel(self, parent: tk.Frame) -> None:
        console_card = self.card(parent, padx=12, pady=12)
        console_card.grid(row=0, column=0, sticky="nsew")
        console_card.rowconfigure(1, weight=1)
        console_card.columnconfigure(0, weight=1)

        console_head = tk.Frame(console_card, bg=Theme.panel)
        console_head.grid(row=0, column=0, sticky="ew")
        console_head.columnconfigure(0, weight=1)
        tk.Label(
            console_head,
            text="REPL CONSOLE",
            bg=Theme.panel,
            fg=Theme.muted,
            font=self.font_micro,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.command_gate_label = tk.Label(
            console_head,
            text="blue.cli.engine: ACTIVE",
            bg=Theme.panel,
            fg=Theme.green,
            font=self.font_micro,
            anchor="e",
        )
        self.command_gate_label.grid(row=0, column=1, sticky="e")

        self.console = ScrolledText(
            console_card,
            bg="#000000",
            fg=Theme.text,
            insertbackground=Theme.text,
            relief="flat",
            font=self.font_mono,
            wrap="word",
            padx=12,
            pady=12,
            height=24,
        )
        self.console.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        self.console.tag_configure("cmd", foreground=Theme.cyan)
        self.console.tag_configure("ok", foreground=Theme.green)
        self.console.tag_configure("warn", foreground=Theme.yellow)
        self.console.tag_configure("err", foreground=Theme.red)
        self.console.tag_configure("json", foreground=Theme.purple)
        self.console.tag_configure("muted", foreground=Theme.muted)
        self.console.configure(state="disabled")

        self._build_blue_cli_engine(console_card)
        self._build_command_palette(console_card)

    def _build_blue_cli_engine(self, parent: tk.Frame) -> None:
        engine = tk.Frame(parent, bg=Theme.blue, height=74, padx=12, pady=12, bd=0)
        engine.grid(row=2, column=0, sticky="ew")
        engine.grid_propagate(False)
        engine.columnconfigure(1, weight=1)

        prompt = tk.Label(
            engine,
            text="BLUE CLI ENGINE >",
            bg=Theme.blue,
            fg=Theme.blue_text,
            font=self.font_prompt,
            padx=5,
        )
        prompt.grid(row=0, column=0, sticky="w")
        self.command_entry = tk.Entry(
            engine,
            textvariable=self.command_var,
            bg=Theme.blue_2,
            fg=Theme.blue_text,
            insertbackground=Theme.blue_text,
            relief="flat",
            font=self.font_prompt,
            bd=0,
        )
        self.command_entry.grid(row=0, column=1, sticky="ew", ipady=9, padx=(10, 10))
        self.command_entry.bind("<Return>", lambda _event: self.execute_current_command())
        self.command_entry.bind("<Up>", self.history_up)
        self.command_entry.bind("<Down>", self.history_down)
        self.command_entry.bind("<Control-l>", lambda _event: self.run_command("clear"))
        self.command_entry.focus_set()
        run_button = tk.Button(
            engine,
            text="RUN",
            command=self.execute_current_command,
            bg=Theme.blue_text,
            fg=Theme.blue,
            activebackground="#dfe4ff",
            activeforeground=Theme.blue,
            relief="flat",
            bd=0,
            padx=18,
            pady=8,
            font=self.font_prompt,
            cursor="hand2",
        )
        run_button.grid(row=0, column=2, sticky="e")

    def _build_command_palette(self, parent: tk.Frame) -> None:
        palette = self.card(parent, bg=Theme.card, padx=10, pady=10)
        palette.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        palette.columnconfigure(0, weight=1)
        tk.Label(
            palette,
            text="QUICK COMMANDS - buttons stage text only; press Enter in the blue CLI engine to execute",
            bg=Theme.card,
            fg=Theme.faint,
            font=self.font_micro,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", columnspan=6, pady=(0, 7))
        commands = [
            "help",
            "service.list",
            "service.activate api.gateway",
            "api.list",
            "service.activate all",
            "node.list",
            "diagnostics.list",
            "diagnostics.patch",
            "node.validate all",
            "emit.preview",
            "build.run",
            "version.snapshot",
        ]
        for index, command in enumerate(commands):
            btn = tk.Button(
                palette,
                text=command,
                command=lambda value=command: self.stage_command(value),
                bg=Theme.card_2,
                fg=Theme.text,
                activebackground=Theme.blue_2,
                activeforeground=Theme.blue_text,
                relief="flat",
                bd=0,
                padx=8,
                pady=6,
                font=self.font_small,
                cursor="hand2",
            )
            btn.grid(row=1 + index // 3, column=index % 3, sticky="ew", padx=4, pady=4)
        for col in range(3):
            palette.columnconfigure(col, weight=1)

    def _build_right_panel(self, parent: tk.Frame) -> None:
        self.service_detail_card = self.card(parent, padx=12, pady=12)
        self.service_detail_card.pack(fill="x")
        tk.Label(
            self.service_detail_card,
            text="SELECTED SERVICE",
            bg=Theme.panel,
            fg=Theme.muted,
            font=self.font_micro,
        ).pack(anchor="w")
        self.service_detail = tk.Frame(self.service_detail_card, bg=Theme.panel)
        self.service_detail.pack(fill="x", pady=(8, 0))

        self.api_card = self.card(parent, padx=12, pady=12)
        self.api_card.pack(fill="x", pady=(12, 0))
        tk.Label(self.api_card, text="API ROUTES", bg=Theme.panel, fg=Theme.muted, font=self.font_micro).pack(anchor="w")
        self.api_list_frame = tk.Frame(self.api_card, bg=Theme.panel)
        self.api_list_frame.pack(fill="x", pady=(8, 0))

        self.state_card = self.card(parent, padx=12, pady=12)
        self.state_card.pack(fill="x", pady=(12, 0))
        tk.Label(self.state_card, text="KERNEL STATE", bg=Theme.panel, fg=Theme.muted, font=self.font_micro).pack(anchor="w")
        self.state_text = ScrolledText(
            self.state_card,
            height=13,
            bg="#000000",
            fg=Theme.muted,
            insertbackground=Theme.text,
            relief="flat",
            font=("Consolas", 9),
            wrap="word",
            padx=10,
            pady=10,
        )
        self.state_text.pack(fill="x", pady=(8, 0))
        self.state_text.configure(state="disabled")

        self.cheat_card = self.card(parent, padx=12, pady=12)
        self.cheat_card.pack(fill="x", pady=(12, 0))
        tk.Label(self.cheat_card, text="COMMAND CHEATSHEET", bg=Theme.panel, fg=Theme.muted, font=self.font_micro).pack(anchor="w")
        cheat = [
            "service.activate <name|all>",
            "service.deactivate <name|all>",
            "service.exec <name> [payload]",
            "api.call <route> [json]",
            "node.add {json}",
            "node.select <id>",
            "manifest.save [path]",
            "set <key> <value>",
            "get <key>",
        ]
        for line in cheat:
            label = tk.Label(
                self.cheat_card,
                text=line,
                bg=Theme.card,
                fg=Theme.cyan,
                font=self.font_small,
                anchor="w",
                padx=8,
                pady=5,
                cursor="hand2",
            )
            label.pack(fill="x", pady=(6, 0))
            label.bind("<Button-1>", lambda _event, value=line: self.stage_command(value))

    def _render_all(self) -> None:
        """Console-only mode has no side panels to refresh."""
        if hasattr(self, "command_gate_label"):
            self.command_gate_label.configure(text="blue.cli.engine: ACTIVE")

    def render_header_counts(self) -> None:
        active = sum(1 for svc in self.services.values() if svc["state"] == "active")
        total = len(self.services)
        self.active_count_label.configure(text=f"{active}/{total} services active")

    def render_service_list(self) -> None:
        for child in self.service_list.inner.winfo_children():
            child.destroy()
        query = self.service_filter_var.get().strip().lower() if hasattr(self, "service_filter_var") else ""
        for service_id, svc in self.services.items():
            haystack = f"{service_id} {svc['layer']} {svc['state']} {svc['description']}".lower()
            if query and query not in haystack:
                continue
            selected = service_id == self.selected_service_id
            bg = Theme.card_2 if selected else Theme.card
            border = Theme.border_active if selected else Theme.border
            row = self.card(self.service_list.inner, bg=bg, border=border, padx=10, pady=9)
            row.pack(fill="x", pady=4)
            row.bind("<Button-1>", lambda _event, sid=service_id: self.select_service(sid))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda _event, sid=service_id: self.select_service(sid))
            top = tk.Frame(row, bg=bg)
            top.pack(fill="x")
            tk.Label(top, text=service_id, bg=bg, fg=Theme.text, font=self.font_h3, anchor="w").pack(side="left", fill="x", expand=True)
            self.badge(top, str(svc["state"])).pack(side="right")
            tk.Label(row, text=str(svc["layer"]).upper(), bg=bg, fg=Theme.faint, font=self.font_micro, anchor="w").pack(fill="x", pady=(4, 0))

    def render_service_detail(self) -> None:
        for child in self.service_detail.winfo_children():
            child.destroy()
        svc = self.services[self.selected_service_id]
        body = self.card(self.service_detail, bg=Theme.card, padx=10, pady=10)
        body.pack(fill="x")
        top = tk.Frame(body, bg=Theme.card)
        top.pack(fill="x")
        tk.Label(top, text=str(svc["id"]), bg=Theme.card, fg=Theme.text, font=self.font_h3).pack(side="left", fill="x", expand=True)
        self.badge(top, str(svc["state"])).pack(side="right")
        tk.Label(
            body,
            text=str(svc["description"]),
            bg=Theme.card,
            fg=Theme.muted,
            font=self.font_small,
            wraplength=330,
            justify="left",
        ).pack(anchor="w", pady=(8, 8))
        facts = [
            f"layer: {svc['layer']}",
            f"calls: {svc['calls']}",
            f"activated_at: {svc['activated_at'] or 'not active'}",
        ]
        for fact in facts:
            tk.Label(body, text=fact, bg=Theme.card, fg=Theme.faint, font=self.font_small).pack(anchor="w")
        tk.Label(body, text="stage examples", bg=Theme.card, fg=Theme.cyan, font=self.font_micro).pack(anchor="w", pady=(10, 2))
        for command in svc["examples"]:
            btn = tk.Button(
                body,
                text=str(command),
                command=lambda value=str(command): self.stage_command(value),
                bg=Theme.card_2,
                fg=Theme.text,
                activebackground=Theme.blue_2,
                activeforeground=Theme.blue_text,
                relief="flat",
                bd=0,
                font=self.font_small,
                anchor="w",
                padx=8,
                pady=5,
                cursor="hand2",
            )
            btn.pack(fill="x", pady=3)
        if svc["last_result"]:
            tk.Label(body, text="last result", bg=Theme.card, fg=Theme.cyan, font=self.font_micro).pack(anchor="w", pady=(10, 2))
            tk.Label(
                body,
                text=str(svc["last_result"]),
                bg=Theme.card,
                fg=Theme.muted,
                font=self.font_small,
                wraplength=330,
                justify="left",
            ).pack(anchor="w")

    def render_api_routes(self) -> None:
        for child in self.api_list_frame.winfo_children():
            child.destroy()
        for route, spec in self.api_routes.items():
            service_id = str(spec["service"])
            state = self.services.get(service_id, {}).get("state", "dormant")
            row = self.card(self.api_list_frame, bg=Theme.card, padx=8, pady=7)
            row.pack(fill="x", pady=4)
            row.bind("<Button-1>", lambda _event, value=f"api.call {route}": self.stage_command(value))
            top = tk.Frame(row, bg=Theme.card)
            top.pack(fill="x")
            tk.Label(top, text=route, bg=Theme.card, fg=Theme.text, font=self.font_small).pack(side="left", fill="x", expand=True)
            self.badge(top, str(state)).pack(side="right")
            tk.Label(row, text=f"service: {service_id}", bg=Theme.card, fg=Theme.faint, font=self.font_small).pack(anchor="w", pady=(3, 0))

    def render_kernel_state(self) -> None:
        payload = {
            "selected_service": self.selected_service_id,
            "selected_node": self.selected_node_id,
            "vars": self.vars,
            "history_size": len(self.history),
            "event_count": len(self.event_log),
            "active_services": [sid for sid, svc in self.services.items() if svc["state"] == "active"],
            "diagnostic_counts": self._diagnostic_counts(),
        }
        text = json.dumps(payload, indent=2)
        self.state_text.configure(state="normal")
        self.state_text.delete("1.0", "end")
        self.state_text.insert("1.0", text)
        self.state_text.configure(state="disabled")

    def _boot_console(self) -> None:
        self.write_console("BOOT", "Blue CLI engine online. Kernel services are dormant until activated by REPL command.", "ok")
        self.write_console("BOOT", "Type help, then activate services explicitly. Terminal examples: service.activate kernel.terminal.linux; linux pwd; service.activate kernel.terminal.powershell7; pwsh $PSVersionTable.PSVersion", "muted")
        self.status_var.set("Ready. Submit commands through the blue CLI engine.")

    def _tick_clock(self) -> None:
        self.clock_var.set(_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.after(1000, self._tick_clock)

    def select_service(self, service_id: str) -> None:
        self.selected_service_id = service_id
        self.render_service_list()
        self.render_service_detail()
        self.render_kernel_state()
        self.status_var.set(f"Selected {service_id}. Selection does not activate it.")

    def stage_command(self, command: str) -> None:
        self.command_var.set(command)
        self.command_entry.focus_set()
        self.command_entry.icursor("end")
        self.status_var.set("Command staged. Press Enter in the blue CLI engine to execute.")

    def execute_current_command(self) -> None:
        command = self.command_var.get().strip()
        if not command:
            return
        self.command_var.set("")
        self.run_command(command, from_entry=True)

    def history_up(self, _event: tk.Event) -> str:
        if not self.history:
            return "break"
        if self.history_index is None:
            self.history_index = len(self.history) - 1
        else:
            self.history_index = max(0, self.history_index - 1)
        self.command_var.set(self.history[self.history_index])
        self.command_entry.icursor("end")
        return "break"

    def history_down(self, _event: tk.Event) -> str:
        if not self.history:
            return "break"
        if self.history_index is None:
            return "break"
        self.history_index += 1
        if self.history_index >= len(self.history):
            self.history_index = None
            self.command_var.set("")
        else:
            self.command_var.set(self.history[self.history_index])
        self.command_entry.icursor("end")
        return "break"

    def run_command(self, command: str, *, from_entry: bool = False) -> None:
        command = command.strip()
        if not command:
            return
        if from_entry:
            self.history.append(command)
            self.history_index = None
        self.write_console("BLUE>", command, "cmd")
        self._record_event("command", command)
        try:
            output, tag = self.dispatch_command(command)
        except Exception as exc:  # Defensive UI shell; command errors should not crash the OS.
            output, tag = f"Unhandled command fault: {exc}", "err"
        if output:
            self.write_console("OS", output, tag)
        self._render_all()
        self.status_var.set("Command completed." if tag != "err" else "Command failed. See console output.")

    def dispatch_command(self, command: str) -> tuple[str, str]:
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            return f"Parse error: {exc}", "err"
        if not tokens:
            return "", "muted"
        cmd = tokens[0].lower()
        args = tokens[1:]
        raw_after_cmd = command.split(maxsplit=1)[1] if len(command.split(maxsplit=1)) > 1 else ""

        if cmd in {"help", "?"}:
            return self.help_text(), "ok"
        if cmd == "clear":
            self.clear_console()
            return "Console cleared.", "ok"
        if cmd == "history":
            return "\n".join(f"{i + 1}: {item}" for i, item in enumerate(self.history[-40:])) or "No command history yet.", "muted"
        if cmd == "blue.engine":
            return "blue.cli.engine is the command-only activation boundary. UI buttons can stage commands, but service activation occurs only when the blue engine executes a REPL command.", "ok"
        if cmd == "terminal.cwd":
            return str(self.terminal_cwd), "muted"
        if cmd == "terminal.cd":
            target = raw_after_cmd.strip() or "~"
            return self.command_terminal_cd(target)
        if cmd == "terminal.timeout":
            if not args:
                return f"terminal timeout = {self.terminal_timeout_seconds}s", "muted"
            return self.command_terminal_timeout(args[0])
        if cmd in {"linux", "bash", "sh"}:
            return self.execute_linux_terminal(raw_after_cmd)
        if cmd in {"pwsh", "powershell", "powershell7"}:
            return self.execute_powershell7_terminal(raw_after_cmd)

        if cmd == "service.list":
            return self.command_service_list(), "json"
        if cmd == "service.status":
            target = args[0] if args else "all"
            return self.command_service_status(target), "json"
        if cmd == "service.activate":
            if not args:
                return "Usage: service.activate <name|all>", "err"
            return self.command_service_activate(args[0]), "ok"
        if cmd == "service.deactivate":
            if not args:
                return "Usage: service.deactivate <name|all>", "err"
            return self.command_service_deactivate(args[0]), "warn"
        if cmd == "service.restart":
            if not args:
                return "Usage: service.restart <name|all>", "err"
            self.command_service_deactivate(args[0])
            return self.command_service_activate(args[0]), "ok"
        if cmd == "service.exec":
            if not args:
                return "Usage: service.exec <name> [payload]", "err"
            service_id = args[0]
            payload_raw = raw_after_cmd.split(maxsplit=1)[1] if len(raw_after_cmd.split(maxsplit=1)) > 1 else ""
            return self.execute_service(service_id, payload_raw)

        if cmd == "api.list":
            return self.command_api_list(), "json"
        if cmd == "api.call":
            if not args:
                return "Usage: api.call <route> [json-payload]", "err"
            route = args[0]
            payload_raw = raw_after_cmd.split(maxsplit=1)[1] if len(raw_after_cmd.split(maxsplit=1)) > 1 else ""
            payload_raw = payload_raw.split(maxsplit=1)[1] if payload_raw.startswith(route) and len(payload_raw.split(maxsplit=1)) > 1 else ""
            return self.command_api_call(route, payload_raw)
        if cmd == "api.register":
            return self.command_api_register(args, raw_after_cmd)

        if cmd == "kernel.info":
            return self.format_json(self.api_kernel_status({})), "json"
        if cmd == "set":
            if len(args) < 2:
                return "Usage: set <key> <value>", "err"
            return self.command_set(args[0], " ".join(args[1:])), "ok"
        if cmd == "get":
            if not args:
                return self.format_json(self.vars), "json"
            return self.vars.get(args[0], "<unset>"), "muted"
        if cmd == "vars":
            return self.format_json(self.vars), "json"

        if cmd.startswith("quadtree.desktop."):
            return self.dispatch_quadtree_desktop_command(cmd, args, raw_after_cmd)

        if cmd.startswith("configure4."):
            return self.dispatch_configure4_command(cmd, args, raw_after_cmd)

        if cmd == "manifest.show":
            return self.command_manifest_show(), "json"
        if cmd == "manifest.save":
            path = args[0] if args else ""
            return self.command_manifest_save(path), "ok"
        if cmd == "manifest.load":
            path = args[0] if args else ""
            return self.command_manifest_load(path)

        if cmd == "node.list":
            return self.command_node_list(), "json"
        if cmd == "node.select":
            if not args:
                return "Usage: node.select <node-id>", "err"
            return self.command_node_select(args[0])
        if cmd == "node.add":
            payload_raw = raw_after_cmd
            return self.command_node_add(payload_raw)
        if cmd == "node.patch":
            target = args[0] if args else self.selected_node_id
            return self.command_node_patch(target)
        if cmd == "node.validate":
            target = args[0] if args else self.selected_node_id
            return self.command_node_validate(target)

        if cmd == "file.search":
            query = " ".join(args)
            return self.command_file_search(query), "json"
        if cmd == "diagnostics.list":
            return self.command_diagnostics_list(), "json"
        if cmd == "diagnostics.patch":
            return self.command_diagnostics_patch()
        if cmd == "emit.preview":
            return self.command_emit_preview(), "muted"
        if cmd == "build.run":
            return self.command_build_run()
        if cmd == "version.snapshot":
            return self.command_version_snapshot(), "json"
        if cmd == "version.list":
            return self.format_json(self.versions), "json"
        if cmd == "reboot":
            return self.command_reboot(), "warn"

        dynamic_result = self.dispatch_configure4_runtime_command(cmd, raw_after_cmd)
        if dynamic_result is not None:
            return dynamic_result

        return f"Unknown command: {cmd}. Type help for available commands.", "err"

    def help_text(self) -> str:
        return """
Blue CLI REPL OS commands

Service control:
  service.list
  service.status <name|all>
  service.activate <name|all>
  service.deactivate <name|all>
  service.restart <name|all>
  service.exec <name> [payload]

API gateway:
  service.activate api.gateway
  api.list
  api.call <route> [json]
  api.register <route> <service-id>

Codex services:
  service.activate codex.graph
  node.list
  node.select <id>
  node.add {"id":"custom.object","label":"Custom Object","type":"module","description":"..."}
  node.patch [id]
  node.validate <id|all>
  file.search <query>

Manifest, diagnostics, emission, build, versioning:
  service.activate codex.manifest
  manifest.show
  manifest.save [path]
  manifest.load [path]
  service.activate diagnostics.runtime
  diagnostics.list
  diagnostics.patch
  service.activate codex.emitter
  emit.preview
  service.activate codex.builder
  build.run
  service.activate version.ledger
  version.snapshot
  version.list

Configure 4 authoring fabric:
  service.activate configure_4.authoring.fabric
  configure4.help
  configure4.help includes in-depth usage for text generation, pointer generation, and language-agnostic codebase planning.
  configure4.status
  configure4.mode <manual|semi_auto|auto>
  configure4.new {json}
  configure4.set <path> <value>
  configure4.get [path]
  configure4.validate [draft-id|all]
  configure4.preview [draft-id]
  configure4.register [draft-id]
  configure4.export <path>
  configure4.import <path>
  configure4.sample
  configure4.reset [draft-id|all]
  configure4.history
  configure4.list
  configure_4.authoring.fabric is dormant until activated with service.activate configure_4.authoring.fabric.

Quadtree desktop:
  service.activate quadtree.desktop
  quadtree.desktop.status
  quadtree.desktop.show
  quadtree.desktop.hide
  quadtree.desktop.module.list
  quadtree.desktop.module.create {json}
  quadtree.desktop.module.get {json}
  quadtree.desktop.module.patch {json}
  quadtree.desktop.layer.get {json}
  quadtree.desktop.layer.patch {json}
  quadtree.desktop.cell.get {json}
  quadtree.desktop.cell.set {json}
  quadtree.desktop.cell.patch {json}
  quadtree.desktop.cell.reset {json}
  quadtree.desktop.cell.subdivide {json}
  quadtree.desktop.cell.bind {json}
  quadtree.desktop.selection.set {json}
  quadtree.desktop.batch.create {json}
  quadtree.desktop.batch.select {json}
  quadtree.desktop.batch.patch {json}
  quadtree.desktop.batch.validate {json}
  quadtree.desktop.batch.preview {json}
  quadtree.desktop.batch.apply {json}
  quadtree.desktop.batch.rollback {json}
  quadtree.desktop.validate [json]
  quadtree.desktop.preview [json]
  quadtree.desktop.apply {json}
  quadtree.desktop.export.manifest [path]
  quadtree.desktop.export.image [path]
  quadtree.desktop.import.manifest <path|json>
  quadtree.desktop.snapshot
  quadtree.desktop remains dormant until activated; graphical actions stage or preview blue-CLI-compatible work.

Terminal kernel services:
  service.activate kernel.terminal.linux
  service.activate kernel.terminal.powershell7
  linux <command>
  pwsh <command>
  service.exec kernel.terminal.linux <command>
  service.exec kernel.terminal.powershell7 <command>
  api.call /terminal/linux {"command":"pwd"}
  api.call /terminal/powershell7 {"command":"Get-ChildItem"}
  terminal.cwd
  terminal.cd <path>
  terminal.timeout <seconds>

Kernel memory:
  service.activate kernel.memory
  set <key> <value>
  get <key>
  vars

Notes:
  Only the REPL Console and blue CLI engine are visible.
  Services activate or execute only after a command is submitted through the blue engine.
  API calls require api.gateway to be active. Route handlers also require their target service to be active.
""".strip()

    def resolve_service_id(self, service_id: str) -> str:
        aliases = {
            "linux": "kernel.terminal.linux",
            "bash": "kernel.terminal.linux",
            "sh": "kernel.terminal.linux",
            "linux.terminal": "kernel.terminal.linux",
            "terminal.linux": "kernel.terminal.linux",
            "pwsh": "kernel.terminal.powershell7",
            "powershell": "kernel.terminal.powershell7",
            "powershell7": "kernel.terminal.powershell7",
            "powershell.7": "kernel.terminal.powershell7",
            "terminal.pwsh": "kernel.terminal.powershell7",
            "terminal.powershell7": "kernel.terminal.powershell7",
            "configure4": CONFIGURE4_SERVICE_ID,
            "configure_4": CONFIGURE4_SERVICE_ID,
            "configure4.authoring": CONFIGURE4_SERVICE_ID,
            "authoring.fabric": CONFIGURE4_SERVICE_ID,
            "quadtree": QUADTREE_DESKTOP_SERVICE_ID,
            "quadtreeDesktop": QUADTREE_DESKTOP_SERVICE_ID,
            "quadtree.desktop": QUADTREE_DESKTOP_SERVICE_ID,
            "qdt": QUADTREE_DESKTOP_SERVICE_ID,
        }
        if service_id in aliases:
            return aliases[service_id]
        if hasattr(self, "configure4_state") and hasattr(self, "services"):
            for sid, svc in self.services.items():
                raw_aliases = svc.get("aliases", []) if isinstance(svc, dict) else []
                if isinstance(raw_aliases, list) and service_id in raw_aliases:
                    return sid
        return service_id

    def command_service_list(self) -> str:
        payload = []
        for sid, svc in self.services.items():
            item = {
                "id": sid,
                "layer": svc["layer"],
                "state": svc["state"],
                "calls": svc["calls"],
            }
            if sid.startswith("kernel.terminal."):
                item["available"] = svc.get("available", False)
                item["executable"] = svc.get("executable", "")
                item["cwd"] = str(self.terminal_cwd)
                item["timeout_seconds"] = self.terminal_timeout_seconds
            payload.append(item)
        return self.format_json(payload)

    def command_service_status(self, target: str) -> str:
        if target == "all":
            return self.command_service_list()
        resolved = self.resolve_service_id(target)
        svc = self.services.get(resolved)
        if not svc:
            return self.format_json({"error": f"Unknown service {target}"})
        payload = dict(svc)
        if resolved.startswith("kernel.terminal."):
            payload["cwd"] = str(self.terminal_cwd)
            payload["timeout_seconds"] = self.terminal_timeout_seconds
        return self.format_json(payload)

    def command_service_activate(self, target: str) -> str:
        targets = list(self.services) if target == "all" else [self.resolve_service_id(target)]
        activated = []
        warnings = []
        for service_id in targets:
            svc = self.services.get(service_id)
            if not svc:
                return f"Unknown service: {service_id}"
            if service_id == "blue.cli.engine":
                svc["state"] = "active"
            else:
                svc["state"] = "active"
                svc["activated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
            if service_id == "kernel.terminal.linux" and not self.linux_shell:
                warnings.append("linux terminal executable missing: expected bash or sh")
            if service_id == "kernel.terminal.powershell7" and not self.pwsh_executable:
                warnings.append("PowerShell 7 executable missing: expected pwsh")
            if service_id == QUADTREE_DESKTOP_SERVICE_ID:
                self.quadtreeDesktop_state["activation_state"] = "active"
                self._qdt_record_event("service.activate", service_id)
            activated.append(service_id)
            self._record_event("service.activate", service_id)
        suffix = "" if not warnings else "\nWarnings: " + "; ".join(warnings)
        return "Activated by REPL command: " + ", ".join(activated) + suffix

    def command_service_deactivate(self, target: str) -> str:
        targets = [sid for sid in self.services if sid != "blue.cli.engine"] if target == "all" else [self.resolve_service_id(target)]
        deactivated = []
        for service_id in targets:
            if service_id == "blue.cli.engine":
                return "blue.cli.engine cannot be deactivated; it is the execution boundary."
            svc = self.services.get(service_id)
            if not svc:
                return f"Unknown service: {service_id}"
            svc["state"] = "dormant"
            svc["activated_at"] = ""
            if service_id == QUADTREE_DESKTOP_SERVICE_ID:
                self.quadtreeDesktop_state["activation_state"] = "dormant"
                self.quadtreeDesktop_state["visible"] = False
                self._hide_quadtree_desktop()
                self._qdt_record_event("service.deactivate", service_id)
            deactivated.append(service_id)
            self._record_event("service.deactivate", service_id)
        return "Deactivated by REPL command: " + ", ".join(deactivated)

    def execute_service(self, service_id: str, payload_raw: str) -> tuple[str, str]:
        service_id = self.resolve_service_id(service_id)
        if service_id not in self.services:
            return f"Unknown service: {service_id}", "err"
        if not self.require_service(service_id):
            return f"Service {service_id} is dormant. Activate it first: service.activate {service_id}", "err"
        svc = self.services[service_id]
        svc["calls"] = int(svc["calls"]) + 1
        payload = self.parse_payload(payload_raw)
        if service_id == "blue.cli.engine":
            result = self.help_text()
            tag = "ok"
        elif service_id == "kernel.clock":
            result = self.format_json({"now": _dt.datetime.now().isoformat(timespec="seconds"), "payload": payload})
            tag = "json"
        elif service_id == "kernel.memory":
            result = self.format_json({"vars": self.vars, "payload": payload})
            tag = "json"
        elif service_id == "kernel.fs":
            result = "kernel.fs ready. Use manifest.save [path] or manifest.load [path]."
            tag = "ok"
        elif service_id == "kernel.terminal.linux":
            result, tag = self.execute_linux_terminal(payload_raw)
        elif service_id == "kernel.terminal.powershell7":
            result, tag = self.execute_powershell7_terminal(payload_raw)
        elif service_id == "api.gateway":
            result = self.command_api_list()
            tag = "json"
        elif service_id == "codex.manifest":
            result = self.command_manifest_show()
            tag = "json"
        elif service_id == "codex.graph":
            result = self.command_node_list()
            tag = "json"
        elif service_id == "codex.validator":
            result, tag = self.command_node_validate("all")
        elif service_id == "codex.emitter":
            result = self.command_emit_preview()
            tag = "muted"
        elif service_id == "codex.builder":
            result, tag = self.command_build_run()
        elif service_id == "diagnostics.runtime":
            result = self.command_diagnostics_list()
            tag = "json"
        elif service_id == "version.ledger":
            result = self.command_version_snapshot()
            tag = "json"
        elif service_id == CONFIGURE4_SERVICE_ID:
            result = self.command_configure4_status()
            tag = "json"
        elif service_id == QUADTREE_DESKTOP_SERVICE_ID:
            result = self.command_quadtree_desktop_status()
            tag = "json"
        else:
            result = self.format_json({"service": service_id, "payload": payload})
            tag = "json"
        svc["last_result"] = result[:260]
        self._record_event("service.exec", service_id)
        return result, tag

    def command_api_list(self) -> str:
        if not self.require_service("api.gateway"):
            return "api.gateway is dormant. Activate it first: service.activate api.gateway"
        payload = []
        for route, spec in self.api_routes.items():
            payload.append({"route": route, "service": spec["service"], "description": spec["description"]})
        return self.format_json(payload)

    def command_api_call(self, route: str, payload_raw: str) -> tuple[str, str]:
        if not self.require_service("api.gateway"):
            return "api.gateway is dormant. Activate it first: service.activate api.gateway", "err"
        spec = self.api_routes.get(route)
        if not spec:
            spec = self.resolve_dynamic_api_route(route)
        if not spec:
            return f"Unknown API route: {route}", "err"
        service_id = str(spec["service"])
        if not self.require_service(service_id):
            return f"Route {route} requires dormant service {service_id}. Activate it first: service.activate {service_id}", "err"
        payload = self.parse_payload(payload_raw)
        handler = spec["handler"]
        result = handler(payload)
        self.services["api.gateway"]["calls"] = int(self.services["api.gateway"]["calls"]) + 1
        self.services[service_id]["calls"] = int(self.services[service_id]["calls"]) + 1
        self.services["api.gateway"]["last_result"] = f"{route} -> {service_id}"
        self.services[service_id]["last_result"] = self.format_json(result)[:260]
        self._record_event("api.call", route)
        return self.format_json(result), "json"

    def command_api_register(self, args: list[str], raw_after_cmd: str) -> tuple[str, str]:
        if not self.require_service("api.gateway"):
            return "api.gateway is dormant. Activate it first: service.activate api.gateway", "err"
        if len(args) < 2:
            return "Usage: api.register <route> <service-id>", "err"
        route, service_id = args[0], self.resolve_service_id(args[1])
        if not route.startswith("/"):
            return "API routes must start with /", "err"
        if service_id not in self.services:
            return f"Unknown service: {service_id}", "err"
        self.api_routes[route] = {
            "service": service_id,
            "description": f"Custom route bound to {service_id}.",
            "handler": lambda payload, sid=service_id, rt=route: {
                "route": rt,
                "service": sid,
                "payload": payload,
                "note": "Custom API route reached. Bind real logic by extending _create_api_routes.",
            },
        }
        self._record_event("api.register", f"{route} -> {service_id}")
        return f"Registered {route} -> {service_id}", "ok"

    def resolve_dynamic_api_route(self, route: str) -> dict[str, object] | None:
        if not route.startswith("/quadtreeDesktop/"):
            return None
        dynamic_patterns = (
            ("/quadtreeDesktop/modules/", self.api_quadtree_desktop_module),
            ("/quadtreeDesktop/layers/", self.api_quadtree_desktop_layer),
            ("/quadtreeDesktop/cells/", self.api_quadtree_desktop_cell),
        )
        for prefix, handler in dynamic_patterns:
            if route.startswith(prefix):
                return {
                    "service": QUADTREE_DESKTOP_SERVICE_ID,
                    "description": f"Dynamic quadtreeDesktop route for {route}.",
                    "handler": lambda payload, rt=route, fn=handler: fn(self._qdt_payload_with_route(payload, rt)),
                }
        return None

    def _qdt_payload_with_route(self, payload: object, route: str) -> dict[str, object]:
        result = copy.deepcopy(payload) if isinstance(payload, dict) else {}
        result["_route"] = route
        return result

    def _create_quadtree_desktop_state(self) -> dict[str, object]:
        state: dict[str, object] = {
            "desktop_id": QUADTREE_DESKTOP_ID,
            "version": QUADTREE_DESKTOP_VERSION,
            "activation_state": "dormant",
            "visible": False,
            "selected_module_ids": ["qdt.system.services"],
            "selected_cell_paths": [],
            "selected_layer_type": "input",
            "root_bounds": {"x": 0, "y": 0, "width": 560, "height": 560},
            "maximum_depth": 4,
            "global_style_tokens": {
                "background": Theme.bg,
                "panel": Theme.panel,
                "cell_border": Theme.border,
                "selection": Theme.cyan,
                "active": Theme.green,
                "warning": Theme.yellow,
                "error": Theme.red,
            },
            "layer_registry": {},
            "module_registry": {},
            "batch_registry": {},
            "rollback_registry": {},
            "pending_operations": {},
            "event_log": [],
            "validation_reports": {},
            "render_cache": {},
            "persistence_metadata": {"policy": "manifest", "last_saved_at": "", "last_loaded_at": ""},
            "export_metadata": {"last_export_path": "", "last_export_hash": "", "last_snapshot_id": ""},
        }
        for module_id in QUADTREE_DEFAULT_MODULE_IDS:
            module = self._qdt_create_module_record(module_id, self._qdt_default_module_label(module_id), self._qdt_default_module_description(module_id))
            state["module_registry"][module_id] = module
            for layer_type in QUADTREE_LAYER_TYPES:
                state["layer_registry"][f"{module_id}:{layer_type}"] = module[f"{layer_type}_layer"]
        return state

    def _qdt_default_module_label(self, module_id: str) -> str:
        parts = [part for part in module_id.replace("qdt.", "").split(".") if part]
        return "Qdt" + "".join(part[:1].upper() + part[1:] for part in parts)

    def _qdt_default_module_description(self, module_id: str) -> str:
        descriptions = {
            "qdt.system.services": "Quadtree view over the kernel service registry.",
            "qdt.system.api": "Quadtree view over API gateway routes.",
            "qdt.codex.graph": "Quadtree view over Codex graph nodes.",
            "qdt.codex.files": "Quadtree view over file objects.",
            "qdt.codex.diagnostics": "Quadtree view over diagnostics.",
            "qdt.codex.emission": "Quadtree view over emitted previews and build-facing outputs.",
            "qdt.runtime.terminal": "Quadtree view over terminal session metadata.",
            "qdt.runtime.memory": "Quadtree view over kernel memory variables and command history.",
            "qdt.configure4.authoring": "Quadtree view over Configure4 authoring drafts and diagnostics.",
            "qdt.desktop.output": "Quadtree output module for desktop render, validation, and export reports.",
        }
        return descriptions.get(module_id, "Quadtree module.")

    def _qdt_default_binding(self, module_id: str) -> dict[str, object]:
        bindings = {
            "qdt.system.services": {"type": "service_registry", "target": "self.services"},
            "qdt.system.api": {"type": "api_route_registry", "target": "self.api_routes"},
            "qdt.codex.graph": {"type": "codex_nodes", "target": "self.nodes"},
            "qdt.codex.files": {"type": "file_objects", "target": "self.files"},
            "qdt.codex.diagnostics": {"type": "diagnostics", "target": "self.diagnostics"},
            "qdt.codex.emission": {"type": "emission", "target": "emit.preview"},
            "qdt.runtime.terminal": {"type": "terminal_session", "target": "self.terminal_cwd"},
            "qdt.runtime.memory": {"type": "kernel_memory", "target": "self.vars"},
            "qdt.configure4.authoring": {"type": "configure4_state", "target": "self.configure4_state"},
            "qdt.desktop.output": {"type": "quadtree_desktop_state", "target": "self.quadtreeDesktop_state"},
        }
        return copy.deepcopy(bindings.get(module_id, {"type": "custom", "target": module_id}))

    def _qdt_create_module_record(self, module_id: str, label: str, description: str) -> dict[str, object]:
        module = {
            "schema": "quadtree-module",
            "module_id": module_id,
            "label": label,
            "description": description,
            "status": "dormant",
            "bindings": {"root": self._qdt_default_binding(module_id)},
            "batch_profiles": {},
            "validation_gates": ["schema", "policy", "reference_integrity", "bounds", "batch_conflicts", "command_boundary"],
            "permissions": {
                "can_stage_commands": True,
                "can_apply_mutations": True,
                "can_execute_kernel_actions": False,
                "filesystem_writes": "explicit_only",
            },
            "persistence_policy": "manifest",
            "render_policy": {"visible": True, "canvas": "tkinter", "show_badges": True, "show_text": True},
        }
        for layer_type in QUADTREE_LAYER_TYPES:
            module[f"{layer_type}_layer"] = self._qdt_create_layer(module_id, layer_type)
        return module

    def _qdt_create_layer(self, module_id: str, layer_type: str) -> dict[str, object]:
        existing_state = self.__dict__.get("quadtreeDesktop_state", {})
        bounds = copy.deepcopy(existing_state.get("root_bounds", {"x": 0, "y": 0, "width": 560, "height": 560})) if isinstance(existing_state, dict) else {"x": 0, "y": 0, "width": 560, "height": 560}
        root_cell = self._qdt_create_cell(module_id, layer_type, "root", bounds=bounds, object_binding=self._qdt_default_binding(module_id))
        layer: dict[str, object] = {
            "layer_type": layer_type,
            "root_cell": root_cell["address"],
            "max_depth": 4,
            "root_size": bounds["width"],
            "cell_defaults": {
                "status": "dormant",
                "visible": True,
                "locked": False,
                "z_order": 0,
                "style_binding": {"token": "default"},
                "content_binding": {"text": ""},
            },
            "subdivision_policy": {"enabled": True, "max_depth": 4, "quadrants": list(QUADTREE_QUADRANTS)},
            "selection_policy": {"mode": "single_or_batch", "aliases": ["selected", "root"]},
            "mutation_policy": {"default_apply_mode": "stage", "requires_validation": True, "transactional_batches": True},
            "event_policy": {"record_input_events": True, "route_to_processing": True, "no_direct_kernel_execution": True},
            "command_policy": {"stage_only_by_default": True, "blue_cli_boundary": True},
            "render_policy": {"canvas": "tkinter", "rectangle": True, "text": True, "badge": True, "selection_outline": True},
            "persistence_policy": {"policy": "manifest", "include_cells": True},
            "style_policy": {"allow_color": True, "allow_badge": True, "allow_image_reference": True},
            "content_policy": {"allow_text": True, "allow_json": True, "allow_image_reference": True},
            "allowed_bindings": [
                "service",
                "api_route",
                "codex_node",
                "file_object",
                "diagnostic",
                "manifest_subtree",
                "configure4_draft",
                "terminal_cwd",
                "command_history",
                "event_log",
                "version_snapshot",
                "output_artifact",
            ],
            "cells": {"root": root_cell},
        }
        if layer_type == "input":
            layer.update(
                {
                    "max_depth": 4,
                    "root_size": bounds["width"],
                    "subdivision_enabled": True,
                    "context_menu_enabled": True,
                    "allowed_input_events": ["click", "right_click", "keyboard", "paste", "drag", "batch_edit", "api_payload", "terminal_text"],
                    "accepted_payload_types": ["text", "json", "image_reference", "file_reference", "clipboard_payload", "manifest_object"],
                    "clipboard_policy": "record_payload_then_route",
                    "file_input_policy": "explicit_reference_only",
                    "cell_customization_policy": "stage_patch_then_preview",
                    "export_intent_policy": "manifest_first_explicit_filesystem",
                }
            )
        return layer

    def _qdt_create_cell(
        self,
        module_id: str,
        layer_type: str,
        path: str,
        *,
        parent_id: str = "",
        quadrant: str = "root",
        depth: int = 0,
        bounds: dict[str, object] | None = None,
        object_binding: dict[str, object] | None = None,
    ) -> dict[str, object]:
        bounds = copy.deepcopy(bounds or {"x": 0, "y": 0, "width": 560, "height": 560})
        address = self._qdt_address(module_id, layer_type, path)
        return {
            "id": address,
            "address": address,
            "path": path,
            "module_id": module_id,
            "layer_type": layer_type,
            "parent_id": parent_id,
            "child_ids": [],
            "quadrant": quadrant,
            "depth": depth,
            "x": int(bounds.get("x", 0)),
            "y": int(bounds.get("y", 0)),
            "width": int(bounds.get("width", 0)),
            "height": int(bounds.get("height", 0)),
            "z_order": 0,
            "visible": True,
            "locked": False,
            "selected": False,
            "status": "dormant",
            "object_binding": copy.deepcopy(object_binding or {}),
            "command_binding": {},
            "api_route_binding": {},
            "service_binding": {},
            "style_binding": {"token": "default", "fill": "", "outline": ""},
            "content_binding": {"text": path, "image_reference": "", "json": {}},
            "validators": ["bounds", "depth", "permissions"],
            "event_handlers": {"click": "stage_selection", "right_click": "preview_context_actions"},
            "permissions": {"mutate": True, "bind": True, "subdivide": True, "execute": False},
            "tags": [],
            "last_mutation_record": {},
        }

    def _qdt_address(self, module_id: str, layer_type: str, path: str) -> str:
        return f"qdt://{QUADTREE_DESKTOP_ID}/{module_id}/{layer_type}/{path}"

    def _qdt_parse_address(self, address: str) -> dict[str, str] | None:
        prefix = f"qdt://{QUADTREE_DESKTOP_ID}/"
        if not isinstance(address, str) or not address.startswith(prefix):
            return None
        rest = address[len(prefix):]
        parts = rest.split("/", 2)
        if len(parts) != 3:
            return None
        return {"module_id": parts[0], "layer_type": parts[1], "path": parts[2]}

    def _qdt_require_service(self) -> tuple[bool, str]:
        if not self.require_service(QUADTREE_DESKTOP_SERVICE_ID):
            return False, f"{QUADTREE_DESKTOP_SERVICE_ID} is dormant. Activate it first: service.activate {QUADTREE_DESKTOP_SERVICE_ID}"
        return True, ""

    def dispatch_quadtree_desktop_command(self, cmd: str, args: list[str], raw_after_cmd: str) -> tuple[str, str]:
        ok, message = self._qdt_require_service()
        if not ok:
            return message, "err"
        action = cmd.removeprefix("quadtree.desktop.")
        payload = self._qdt_command_payload(args, raw_after_cmd)
        simple_json_actions = {
            "status": self.command_quadtree_desktop_status,
            "module.list": self.command_quadtree_desktop_module_list,
            "snapshot": self.command_quadtree_desktop_snapshot,
        }
        if action in simple_json_actions:
            return simple_json_actions[action](), "json"
        if action == "show":
            return self.command_quadtree_desktop_show(), "ok"
        if action == "hide":
            return self.command_quadtree_desktop_hide(), "ok"
        handler_map = {
            "module.create": self.command_quadtree_desktop_module_create,
            "module.get": self.command_quadtree_desktop_module_get,
            "module.patch": self.command_quadtree_desktop_module_patch,
            "layer.get": self.command_quadtree_desktop_layer_get,
            "layer.patch": self.command_quadtree_desktop_layer_patch,
            "cell.get": self.command_quadtree_desktop_cell_get,
            "cell.set": self.command_quadtree_desktop_cell_set,
            "cell.patch": self.command_quadtree_desktop_cell_patch,
            "cell.reset": self.command_quadtree_desktop_cell_reset,
            "cell.subdivide": self.command_quadtree_desktop_cell_subdivide,
            "cell.bind": self.command_quadtree_desktop_cell_bind,
            "selection.set": self.command_quadtree_desktop_selection_set,
            "batch.create": self.command_quadtree_desktop_batch_create,
            "batch.select": self.command_quadtree_desktop_batch_select,
            "batch.patch": self.command_quadtree_desktop_batch_patch,
            "batch.validate": self.command_quadtree_desktop_batch_validate,
            "batch.preview": self.command_quadtree_desktop_batch_preview,
            "batch.apply": self.command_quadtree_desktop_batch_apply,
            "batch.rollback": self.command_quadtree_desktop_batch_rollback,
            "validate": self.command_quadtree_desktop_validate,
            "preview": self.command_quadtree_desktop_preview,
            "apply": self.command_quadtree_desktop_apply,
            "export.manifest": self.command_quadtree_desktop_export_manifest,
            "export.image": self.command_quadtree_desktop_export_image,
            "import.manifest": self.command_quadtree_desktop_import_manifest,
        }
        handler = handler_map.get(action)
        if not handler:
            return f"Unknown quadtree desktop command: {cmd}", "err"
        result, tag = handler(payload)
        return self.format_json(result) if isinstance(result, (dict, list)) else str(result), tag

    def _qdt_command_payload(self, args: list[str], raw_after_cmd: str) -> object:
        raw = raw_after_cmd.strip()
        if raw.startswith("{") or raw.startswith("["):
            return self.parse_payload(raw)
        if raw:
            parsed = self.parse_payload(raw)
            if isinstance(parsed, dict) and parsed.get("raw") == raw and args:
                return {"path": args[0], "raw": raw, "args": args}
            return parsed
        return {}

    def command_quadtree_desktop_status(self) -> str:
        return self.format_json(self._qdt_status_payload())

    def _qdt_status_payload(self) -> dict[str, object]:
        modules = self.quadtreeDesktop_state.get("module_registry", {})
        batches = self.quadtreeDesktop_state.get("batch_registry", {})
        events = self.quadtreeDesktop_state.get("event_log", [])
        return {
            "service_id": QUADTREE_DESKTOP_SERVICE_ID,
            "label": QUADTREE_DESKTOP_LABEL,
            "desktop_id": self.quadtreeDesktop_state.get("desktop_id", QUADTREE_DESKTOP_ID),
            "version": self.quadtreeDesktop_state.get("version", QUADTREE_DESKTOP_VERSION),
            "activation_state": self.quadtreeDesktop_state.get("activation_state", "dormant"),
            "visible": self.quadtreeDesktop_state.get("visible", False),
            "module_count": len(modules) if isinstance(modules, dict) else 0,
            "batch_count": len(batches) if isinstance(batches, dict) else 0,
            "selected_module_ids": copy.deepcopy(self.quadtreeDesktop_state.get("selected_module_ids", [])),
            "selected_layer_type": self.quadtreeDesktop_state.get("selected_layer_type", "input"),
            "selected_cell_paths": copy.deepcopy(self.quadtreeDesktop_state.get("selected_cell_paths", [])),
            "latest_events": copy.deepcopy(events[-10:]) if isinstance(events, list) else [],
            "state_hash": self._qdt_state_hash(),
        }

    def command_quadtree_desktop_show(self) -> str:
        self.quadtreeDesktop_state["visible"] = True
        self.quadtreeDesktop_state["activation_state"] = "active"
        self._qdt_record_event("desktop.show", "Quadtree desktop requested through blue CLI.")
        self._show_quadtree_desktop()
        return "QuadtreeDesktop visible. Blue CLI remains the authoritative execution boundary."

    def command_quadtree_desktop_hide(self) -> str:
        self.quadtreeDesktop_state["visible"] = False
        self._qdt_record_event("desktop.hide", "Quadtree desktop hidden through blue CLI.")
        self._hide_quadtree_desktop()
        return "QuadtreeDesktop hidden. Service remains active until service.deactivate quadtree.desktop."

    def command_quadtree_desktop_module_list(self) -> str:
        modules = self.quadtreeDesktop_state.get("module_registry", {})
        rows = []
        if isinstance(modules, dict):
            for module_id, module in modules.items():
                rows.append(
                    {
                        "module_id": module_id,
                        "label": module.get("label", module_id),
                        "status": module.get("status", ""),
                        "layers": [layer for layer in QUADTREE_LAYER_TYPES if f"{layer}_layer" in module],
                    }
                )
        return self.format_json(rows)

    def command_quadtree_desktop_module_get(self, payload: object) -> tuple[dict[str, object], str]:
        module_id = self._qdt_payload_value(payload, "module_id", "")
        if not module_id and isinstance(payload, dict):
            module_id = self._qdt_module_from_target(payload)
        module = self._qdt_get_module(module_id)
        if not module:
            return {"accepted": False, "error": f"Unknown module: {module_id}"}, "err"
        return {"accepted": True, "module": copy.deepcopy(module)}, "json"

    def command_quadtree_desktop_module_create(self, payload: object) -> tuple[dict[str, object], str]:
        if not isinstance(payload, dict) or payload.get("parse_error"):
            return {"accepted": False, "error": "module.create requires a JSON object."}, "err"
        module_id = str(payload.get("module_id", "")).strip()
        if not self._qdt_valid_module_id(module_id):
            return {"accepted": False, "error": "module_id must be a stable dot-delimited id."}, "err"
        if module_id in self.quadtreeDesktop_state["module_registry"]:
            return {"accepted": False, "error": f"Module already exists: {module_id}"}, "err"
        module = self._qdt_create_module_record(module_id, str(payload.get("label", self._qdt_default_module_label(module_id))), str(payload.get("description", "Custom quadtree module.")))
        module = self._qdt_deep_merge(module, {key: copy.deepcopy(value) for key, value in payload.items() if key in {"status", "bindings", "batch_profiles", "validation_gates", "permissions", "persistence_policy", "render_policy"}})
        validation = self._qdt_validate_module(module)
        if not validation["accepted"]:
            return {"accepted": False, "validation": validation}, "err"
        self.quadtreeDesktop_state["module_registry"][module_id] = module
        for layer_type in QUADTREE_LAYER_TYPES:
            self.quadtreeDesktop_state["layer_registry"][f"{module_id}:{layer_type}"] = module[f"{layer_type}_layer"]
        self._qdt_record_event("module.create", module_id)
        self._render_quadtree_desktop()
        return {"accepted": True, "module_id": module_id, "module": module}, "json"

    def command_quadtree_desktop_module_patch(self, payload: object) -> tuple[dict[str, object], str]:
        return self._qdt_apply_target_patch(payload, target_type="module")

    def command_quadtree_desktop_layer_get(self, payload: object) -> tuple[dict[str, object], str]:
        module_id, layer_type = self._qdt_layer_ref(payload)
        layer = self._qdt_get_layer(module_id, layer_type)
        if not layer:
            return {"accepted": False, "error": f"Unknown layer: {module_id}/{layer_type}"}, "err"
        return {"accepted": True, "layer": copy.deepcopy(layer)}, "json"

    def command_quadtree_desktop_layer_patch(self, payload: object) -> tuple[dict[str, object], str]:
        return self._qdt_apply_target_patch(payload, target_type="layer")

    def command_quadtree_desktop_cell_get(self, payload: object) -> tuple[dict[str, object], str]:
        cell_ref = self._qdt_cell_ref(payload)
        cell = self._qdt_get_cell_by_ref(cell_ref)
        if not cell:
            return {"accepted": False, "error": f"Unknown cell: {cell_ref}"}, "err"
        return {"accepted": True, "cell": copy.deepcopy(cell)}, "json"

    def command_quadtree_desktop_cell_set(self, payload: object) -> tuple[dict[str, object], str]:
        if not isinstance(payload, dict):
            return {"accepted": False, "error": "cell.set requires JSON."}, "err"
        prop = str(payload.get("property", payload.get("path", ""))).strip()
        if not prop:
            return {"accepted": False, "error": "cell.set requires property or path."}, "err"
        patch: dict[str, object] = {}
        self._qdt_set_path(patch, prop.split("."), copy.deepcopy(payload.get("value", "")))
        rewritten = copy.deepcopy(payload)
        rewritten["patch"] = patch
        return self._qdt_apply_target_patch(rewritten, target_type="cell")

    def command_quadtree_desktop_cell_patch(self, payload: object) -> tuple[dict[str, object], str]:
        return self._qdt_apply_target_patch(payload, target_type="cell")

    def command_quadtree_desktop_cell_reset(self, payload: object) -> tuple[dict[str, object], str]:
        cell_ref = self._qdt_cell_ref(payload)
        parsed = self._qdt_resolve_cell_ref(cell_ref)
        if not parsed:
            return {"accepted": False, "error": f"Unknown cell: {cell_ref}"}, "err"
        module_id, layer_type, path = parsed
        cell = self._qdt_get_cell(module_id, layer_type, path)
        if not cell:
            return {"accepted": False, "error": f"Unknown cell: {cell_ref}"}, "err"
        replacement = self._qdt_create_cell(
            module_id,
            layer_type,
            path,
            parent_id=str(cell.get("parent_id", "")),
            quadrant=str(cell.get("quadrant", "root")),
            depth=int(cell.get("depth", 0)),
            bounds={"x": cell.get("x", 0), "y": cell.get("y", 0), "width": cell.get("width", 0), "height": cell.get("height", 0)},
            object_binding=copy.deepcopy(cell.get("object_binding", {})),
        )
        replacement["last_mutation_record"] = self._qdt_mutation_record("cell.reset")
        self._qdt_set_cell(module_id, layer_type, path, replacement)
        self._qdt_record_event("cell.reset", replacement["address"])
        self._render_quadtree_desktop()
        return {"accepted": True, "cell": replacement}, "json"

    def command_quadtree_desktop_cell_subdivide(self, payload: object) -> tuple[dict[str, object], str]:
        cell_ref = self._qdt_cell_ref(payload)
        parsed = self._qdt_resolve_cell_ref(cell_ref)
        if not parsed:
            return {"accepted": False, "error": f"Unknown cell: {cell_ref}"}, "err"
        result = self._qdt_subdivide_cell(parsed[0], parsed[1], parsed[2], mutate=True)
        self._render_quadtree_desktop()
        return result, "json" if result.get("accepted") else "err"

    def command_quadtree_desktop_cell_bind(self, payload: object) -> tuple[dict[str, object], str]:
        if not isinstance(payload, dict):
            return {"accepted": False, "error": "cell.bind requires JSON."}, "err"
        binding_type = str(payload.get("binding_type", payload.get("type", "object_binding")))
        binding = copy.deepcopy(payload.get("binding", {}))
        if not binding:
            binding = {key: copy.deepcopy(value) for key, value in payload.items() if key in {"service_id", "api_route", "object_type", "target", "command"}}
        target_field = {
            "object": "object_binding",
            "object_binding": "object_binding",
            "command": "command_binding",
            "command_binding": "command_binding",
            "api": "api_route_binding",
            "api_route": "api_route_binding",
            "api_route_binding": "api_route_binding",
            "service": "service_binding",
            "service_binding": "service_binding",
            "style": "style_binding",
            "content": "content_binding",
        }.get(binding_type, "object_binding")
        rewritten = copy.deepcopy(payload)
        rewritten["patch"] = {target_field: binding}
        return self._qdt_apply_target_patch(rewritten, target_type="cell")

    def command_quadtree_desktop_selection_set(self, payload: object) -> tuple[dict[str, object], str]:
        refs = self._qdt_selection_refs(payload)
        if not refs:
            return {"accepted": False, "error": "selection.set requires address, target, or addresses."}, "err"
        selected = []
        for ref in refs:
            parsed = self._qdt_resolve_cell_ref(ref)
            if not parsed:
                continue
            cell = self._qdt_get_cell(*parsed)
            if not cell:
                continue
            selected.append(cell["address"])
        self._qdt_set_selection(selected)
        self._qdt_record_event("selection.set", ", ".join(selected))
        self._render_quadtree_desktop()
        return {"accepted": True, "selected_cell_paths": selected}, "json"

    def command_quadtree_desktop_batch_create(self, payload: object) -> tuple[dict[str, object], str]:
        if not isinstance(payload, dict):
            return {"accepted": False, "error": "batch.create requires JSON."}, "err"
        batch_id = str(payload.get("batch_id", f"batch_{len(self.quadtreeDesktop_state['batch_registry']) + 1:03d}"))
        if batch_id in self.quadtreeDesktop_state["batch_registry"]:
            return {"accepted": False, "error": f"Batch already exists: {batch_id}"}, "err"
        batch = {
            "batch_id": batch_id,
            "label": str(payload.get("label", batch_id)),
            "selectors": copy.deepcopy(payload.get("selectors", payload.get("selection", {}))),
            "patch": copy.deepcopy(payload.get("patch", {})),
            "status": "staged",
            "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "last_preview": {},
            "last_apply": {},
        }
        self.quadtreeDesktop_state["batch_registry"][batch_id] = batch
        self.quadtreeDesktop_state["selected_batch_id"] = batch_id
        self._qdt_record_event("batch.create", batch_id)
        return {"accepted": True, "batch": batch}, "json"

    def command_quadtree_desktop_batch_select(self, payload: object) -> tuple[dict[str, object], str]:
        batch_id = self._qdt_payload_value(payload, "batch_id", "")
        if not batch_id or batch_id not in self.quadtreeDesktop_state["batch_registry"]:
            return {"accepted": False, "error": f"Unknown batch: {batch_id}"}, "err"
        self.quadtreeDesktop_state["selected_batch_id"] = batch_id
        self._qdt_record_event("batch.select", batch_id)
        self._render_quadtree_desktop()
        return {"accepted": True, "batch_id": batch_id}, "json"

    def command_quadtree_desktop_batch_patch(self, payload: object) -> tuple[dict[str, object], str]:
        batch_id = self._qdt_payload_value(payload, "batch_id", str(self.quadtreeDesktop_state.get("selected_batch_id", "")))
        batch = self.quadtreeDesktop_state["batch_registry"].get(batch_id)
        if not batch:
            return {"accepted": False, "error": f"Unknown batch: {batch_id}"}, "err"
        batch_patch = copy.deepcopy(payload.get("patch", payload)) if isinstance(payload, dict) else {}
        for key in ("batch_id", "raw", "args"):
            batch_patch.pop(key, None)
        batch.update(self._qdt_deep_merge(batch, batch_patch))
        self._qdt_record_event("batch.patch", batch_id)
        return {"accepted": True, "batch": batch}, "json"

    def command_quadtree_desktop_batch_validate(self, payload: object) -> tuple[dict[str, object], str]:
        batch = self._qdt_batch_from_payload(payload)
        if not batch:
            return {"accepted": False, "error": "Unknown batch."}, "err"
        report = self._qdt_preview_batch(batch, mutate=False)
        return report, "json" if report.get("accepted") else "err"

    def command_quadtree_desktop_batch_preview(self, payload: object) -> tuple[dict[str, object], str]:
        batch = self._qdt_batch_from_payload(payload)
        if not batch:
            return {"accepted": False, "error": "Unknown batch."}, "err"
        report = self._qdt_preview_batch(batch, mutate=False)
        batch["last_preview"] = report
        self._qdt_record_event("batch.preview", str(batch.get("batch_id", "")))
        return report, "json" if report.get("accepted") else "err"

    def command_quadtree_desktop_batch_apply(self, payload: object) -> tuple[dict[str, object], str]:
        batch = self._qdt_batch_from_payload(payload)
        if not batch:
            return {"accepted": False, "error": "Unknown batch."}, "err"
        report = self._qdt_preview_batch(batch, mutate=True)
        batch["last_apply"] = report
        self._qdt_record_event("batch.apply", str(batch.get("batch_id", "")))
        self._render_quadtree_desktop()
        return report, "json" if report.get("accepted") else "err"

    def command_quadtree_desktop_batch_rollback(self, payload: object) -> tuple[dict[str, object], str]:
        token = self._qdt_payload_value(payload, "rollback_token", self._qdt_payload_value(payload, "token", ""))
        rollback = self.quadtreeDesktop_state.get("rollback_registry", {}).get(token)
        if not rollback:
            return {"accepted": False, "error": f"Unknown rollback token: {token}"}, "err"
        self._restore_quadtree_desktop_state(rollback["before_state"])
        self._qdt_record_event("batch.rollback", token)
        self._render_quadtree_desktop()
        return {"accepted": True, "rollback_token": token}, "json"

    def command_quadtree_desktop_validate(self, payload: object) -> tuple[dict[str, object], str]:
        report = self._qdt_validate_state(self.quadtreeDesktop_state)
        self.quadtreeDesktop_state.setdefault("validation_reports", {})["latest"] = report
        self._qdt_record_event("desktop.validate", "accepted" if report["accepted"] else "failed")
        return report, "json" if report["accepted"] else "err"

    def command_quadtree_desktop_preview(self, payload: object) -> tuple[dict[str, object], str]:
        if isinstance(payload, dict) and "batch_id" in payload:
            return self.command_quadtree_desktop_batch_preview(payload)
        if isinstance(payload, dict) and "patch" in payload:
            return self._qdt_apply_target_patch(payload, target_type=str(payload.get("target_type", "cell")), force_stage=True)
        report = {
            "accepted": True,
            "state_hash": self._qdt_state_hash(),
            "selected": copy.deepcopy(self.quadtreeDesktop_state.get("selected_cell_paths", [])),
            "modules": list(self.quadtreeDesktop_state.get("module_registry", {})),
            "note": "Preview is manifest-safe and does not mutate desktop state.",
        }
        self._qdt_record_event("desktop.preview", "state")
        return report, "json"

    def command_quadtree_desktop_apply(self, payload: object) -> tuple[dict[str, object], str]:
        if isinstance(payload, dict) and "operation_token" in payload:
            op = self.quadtreeDesktop_state.get("pending_operations", {}).get(str(payload["operation_token"]))
            if not op:
                return {"accepted": False, "error": f"Unknown operation token: {payload['operation_token']}"}, "err"
            return self._qdt_apply_target_patch(op["payload"], target_type=str(op.get("target_type", "cell")), force_apply=True)
        if isinstance(payload, dict) and "batch_id" in payload:
            return self.command_quadtree_desktop_batch_apply(payload)
        return self._qdt_apply_target_patch(payload, target_type=str(payload.get("target_type", "cell")) if isinstance(payload, dict) else "cell", force_apply=True)

    def command_quadtree_desktop_export_manifest(self, payload: object) -> tuple[dict[str, object] | str, str]:
        path = ""
        if isinstance(payload, dict):
            path = str(payload.get("path", payload.get("raw", ""))).strip()
        export_payload = {"quadtreeDesktop_state": copy.deepcopy(self.quadtreeDesktop_state)}
        export_hash = self._qdt_hash(export_payload)
        self.quadtreeDesktop_state.setdefault("export_metadata", {})["last_export_hash"] = export_hash
        if path:
            if not self.require_service("kernel.fs"):
                return {"accepted": False, "error": "kernel.fs is dormant. Activate it first: service.activate kernel.fs"}, "err"
            output_path = Path(path).expanduser()
            if output_path.parent and str(output_path.parent) not in {"", "."}:
                output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(export_payload, handle, indent=2)
            self.quadtreeDesktop_state["export_metadata"]["last_export_path"] = str(output_path)
            self._qdt_record_event("export.manifest", str(output_path))
            return {"accepted": True, "path": str(output_path), "hash": export_hash}, "json"
        self._qdt_record_event("export.manifest", "console")
        return {"accepted": True, "hash": export_hash, "manifest": export_payload}, "json"

    def command_quadtree_desktop_export_image(self, payload: object) -> tuple[dict[str, object], str]:
        path = ""
        if isinstance(payload, dict):
            path = str(payload.get("path", payload.get("raw", ""))).strip()
        preview = {
            "accepted": True,
            "artifact_type": "tk_canvas_postscript",
            "note": "Pure-stdlib Tkinter can export the visible canvas as PostScript. PNG conversion is intentionally not performed without an explicit external tool.",
            "visible": bool(self.quadtreeDesktop_state.get("visible", False)),
            "path": path,
        }
        if not path:
            self._qdt_record_event("export.image.preview", "console")
            return preview, "json"
        if not self.require_service("kernel.fs"):
            return {"accepted": False, "error": "kernel.fs is dormant. Activate it first: service.activate kernel.fs"}, "err"
        if self.quadtree_canvas is None:
            return {"accepted": False, "error": "Quadtree canvas is not visible. Run quadtree.desktop.show first."}, "err"
        output_path = Path(path).expanduser()
        if output_path.suffix.lower() == ".png":
            return {"accepted": False, "error": "PNG export is not available in pure stdlib Tkinter. Use .ps or .eps, or export the manifest."}, "err"
        if output_path.parent and str(output_path.parent) not in {"", "."}:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        self.quadtree_canvas.postscript(file=str(output_path), colormode="color")
        preview["path"] = str(output_path)
        preview["hash"] = self._qdt_hash({"path": str(output_path), "state": self._qdt_state_hash()})[:16]
        self.quadtreeDesktop_state.setdefault("export_metadata", {})["last_image_export_path"] = str(output_path)
        self._qdt_record_event("export.image", str(output_path))
        return preview, "json"

    def command_quadtree_desktop_import_manifest(self, payload: object) -> tuple[dict[str, object], str]:
        source = ""
        if isinstance(payload, dict):
            source = str(payload.get("path", payload.get("raw", ""))).strip()
        if source and not source.startswith("{"):
            if not self.require_service("kernel.fs"):
                return {"accepted": False, "error": "kernel.fs is dormant. Activate it first: service.activate kernel.fs"}, "err"
            with open(Path(source).expanduser(), "r", encoding="utf-8") as handle:
                imported = json.load(handle)
        else:
            imported = payload
        state_payload = imported.get("quadtreeDesktop_state", imported) if isinstance(imported, dict) else {}
        validation = self._qdt_validate_state(state_payload)
        if not validation["accepted"]:
            return {"accepted": False, "validation": validation}, "err"
        self._restore_quadtree_desktop_state(state_payload)
        self.quadtreeDesktop_state.setdefault("persistence_metadata", {})["last_loaded_at"] = _dt.datetime.now().isoformat(timespec="seconds")
        self._qdt_record_event("import.manifest", source or "payload")
        self._render_quadtree_desktop()
        return {"accepted": True, "validation": validation, "state_hash": self._qdt_state_hash()}, "json"

    def command_quadtree_desktop_snapshot(self) -> str:
        snapshot = {
            "id": f"qdt-snap-{_dt.datetime.now().strftime('%Y%m%d.%H%M%S')}",
            "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "state_hash": self._qdt_state_hash(),
            "status": self._qdt_status_payload(),
        }
        self.quadtreeDesktop_state.setdefault("render_cache", {})["latest_snapshot"] = snapshot
        self.quadtreeDesktop_state.setdefault("export_metadata", {})["last_snapshot_id"] = snapshot["id"]
        self._qdt_record_event("desktop.snapshot", snapshot["id"])
        return self.format_json(snapshot)

    def _qdt_payload_value(self, payload: object, key: str, default: object = "") -> str:
        if isinstance(payload, dict):
            value = payload.get(key, default)
            if value == "" and key == "module_id":
                value = payload.get("id", default)
            return str(value)
        return str(default)

    def _qdt_valid_module_id(self, module_id: str) -> bool:
        return bool(re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", module_id or ""))

    def _qdt_module_from_target(self, payload: object) -> str:
        if not isinstance(payload, dict):
            return ""
        target = str(payload.get("target", payload.get("address", "")))
        parsed = self._qdt_parse_address(target)
        if parsed:
            return parsed["module_id"]
        return target if target in self.quadtreeDesktop_state.get("module_registry", {}) else ""

    def _qdt_layer_ref(self, payload: object) -> tuple[str, str]:
        if not isinstance(payload, dict):
            selected_modules = self.quadtreeDesktop_state.get("selected_module_ids", ["qdt.system.services"])
            return str(selected_modules[0]), str(self.quadtreeDesktop_state.get("selected_layer_type", "input"))
        address = str(payload.get("address", payload.get("target", "")))
        parsed = self._qdt_parse_address(address)
        if parsed:
            return parsed["module_id"], parsed["layer_type"]
        module_id = str(payload.get("module_id", self._qdt_module_from_target(payload) or ""))
        if not module_id:
            selected_modules = self.quadtreeDesktop_state.get("selected_module_ids", ["qdt.system.services"])
            module_id = str(selected_modules[0]) if selected_modules else "qdt.system.services"
        layer_type = str(payload.get("layer_type", payload.get("layer", self.quadtreeDesktop_state.get("selected_layer_type", "input"))))
        return module_id, layer_type

    def _qdt_cell_ref(self, payload: object) -> str:
        if isinstance(payload, str):
            return payload
        if not isinstance(payload, dict):
            selected = self.quadtreeDesktop_state.get("selected_cell_paths", [])
            return str(selected[0]) if selected else self._qdt_address("qdt.system.services", "input", "root")
        for key in ("address", "target", "id"):
            if payload.get(key):
                return str(payload[key])
        if payload.get("selection") == "selected" or payload.get("alias") == "selected":
            selected = self.quadtreeDesktop_state.get("selected_cell_paths", [])
            return str(selected[0]) if selected else ""
        module_id, layer_type = self._qdt_layer_ref(payload)
        path = str(payload.get("path", "root"))
        return self._qdt_address(module_id, layer_type, path)

    def _qdt_selection_refs(self, payload: object) -> list[str]:
        if isinstance(payload, dict):
            addresses = payload.get("addresses", payload.get("selection", []))
            if isinstance(addresses, list):
                return [str(item) for item in addresses]
            ref = self._qdt_cell_ref(payload)
            return [ref] if ref else []
        if isinstance(payload, list):
            return [str(item) for item in payload]
        return []

    def _qdt_resolve_cell_ref(self, ref: str) -> tuple[str, str, str] | None:
        if not ref:
            return None
        parsed = self._qdt_parse_address(ref)
        if parsed:
            return parsed["module_id"], parsed["layer_type"], parsed["path"]
        if ref == "selected":
            selected = self.quadtreeDesktop_state.get("selected_cell_paths", [])
            if selected:
                return self._qdt_resolve_cell_ref(str(selected[0]))
        parts = ref.split(":")
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        selected_modules = self.quadtreeDesktop_state.get("selected_module_ids", ["qdt.system.services"])
        module_id = str(selected_modules[0]) if selected_modules else "qdt.system.services"
        layer_type = str(self.quadtreeDesktop_state.get("selected_layer_type", "input"))
        return module_id, layer_type, ref

    def _qdt_get_module(self, module_id: str) -> dict[str, object] | None:
        modules = self.quadtreeDesktop_state.get("module_registry", {})
        return modules.get(module_id) if isinstance(modules, dict) else None

    def _qdt_get_layer(self, module_id: str, layer_type: str) -> dict[str, object] | None:
        module = self._qdt_get_module(module_id)
        if not module or layer_type not in QUADTREE_LAYER_TYPES:
            return None
        return module.get(f"{layer_type}_layer") if isinstance(module.get(f"{layer_type}_layer"), dict) else None

    def _qdt_get_cell(self, module_id: str, layer_type: str, path: str) -> dict[str, object] | None:
        layer = self._qdt_get_layer(module_id, layer_type)
        if not layer:
            return None
        cells = layer.get("cells", {})
        return cells.get(path) if isinstance(cells, dict) else None

    def _qdt_get_cell_by_ref(self, ref: str) -> dict[str, object] | None:
        parsed = self._qdt_resolve_cell_ref(ref)
        return self._qdt_get_cell(*parsed) if parsed else None

    def _qdt_set_cell(self, module_id: str, layer_type: str, path: str, cell: dict[str, object]) -> None:
        layer = self._qdt_get_layer(module_id, layer_type)
        if layer is None:
            return
        layer.setdefault("cells", {})[path] = cell
        self.quadtreeDesktop_state.setdefault("layer_registry", {})[f"{module_id}:{layer_type}"] = layer

    def _qdt_set_selection(self, addresses: list[str]) -> None:
        for module in self.quadtreeDesktop_state.get("module_registry", {}).values():
            if not isinstance(module, dict):
                continue
            for layer_type in QUADTREE_LAYER_TYPES:
                layer = module.get(f"{layer_type}_layer", {})
                for cell in layer.get("cells", {}).values() if isinstance(layer, dict) else []:
                    if isinstance(cell, dict):
                        cell["selected"] = False
        selected_modules: list[str] = []
        selected_layers: list[str] = []
        for address in addresses:
            parsed = self._qdt_resolve_cell_ref(address)
            if not parsed:
                continue
            cell = self._qdt_get_cell(*parsed)
            if not cell:
                continue
            cell["selected"] = True
            if parsed[0] not in selected_modules:
                selected_modules.append(parsed[0])
            if parsed[1] not in selected_layers:
                selected_layers.append(parsed[1])
        self.quadtreeDesktop_state["selected_cell_paths"] = addresses
        if selected_modules:
            self.quadtreeDesktop_state["selected_module_ids"] = selected_modules
        if selected_layers:
            self.quadtreeDesktop_state["selected_layer_type"] = selected_layers[0]

    def _qdt_apply_target_patch(self, payload: object, *, target_type: str, force_stage: bool = False, force_apply: bool = False) -> tuple[dict[str, object], str]:
        if not isinstance(payload, dict) or payload.get("parse_error"):
            return {"accepted": False, "error": f"{target_type}.patch requires a JSON object."}, "err"
        validation_mode = str(payload.get("validation_mode", "full"))
        apply_mode = str(payload.get("apply_mode", "stage"))
        if force_stage:
            apply_mode = "stage"
        if force_apply:
            apply_mode = "apply"
        if validation_mode not in QUADTREE_VALIDATION_MODES:
            return {"accepted": False, "error": f"Unsupported validation_mode: {validation_mode}"}, "err"
        if apply_mode not in QUADTREE_APPLY_MODES:
            return {"accepted": False, "error": f"Unsupported apply_mode: {apply_mode}"}, "err"
        patch = copy.deepcopy(payload.get("patch", {}))
        if not isinstance(patch, dict):
            return {"accepted": False, "error": "patch must be an object."}, "err"
        target = self._qdt_resolve_target(payload, target_type)
        if not target:
            return {"accepted": False, "error": f"Could not resolve {target_type} target."}, "err"
        before_hash = self._qdt_state_hash()
        working_state = copy.deepcopy(self.quadtreeDesktop_state)
        result = self._qdt_apply_patch_to_state(working_state, target_type, target, patch)
        if not result["accepted"]:
            return {**result, "before_hash": before_hash, "after_hash": before_hash, "mutated": False}, "err"
        validation = self._qdt_validate_state(working_state) if validation_mode in {"full", "schema_only", "policy_only"} else {"accepted": True, "mode": validation_mode}
        after_hash = self._qdt_hash(working_state)
        preview = {
            "accepted": bool(validation.get("accepted", False)),
            "target_type": target_type,
            "target": target,
            "validation_mode": validation_mode,
            "apply_mode": apply_mode,
            "validation": validation,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "mutated": False,
        }
        if not preview["accepted"] or apply_mode == "stage":
            token = self._qdt_operation_token(target_type, target, patch)
            self.quadtreeDesktop_state.setdefault("pending_operations", {})[token] = {
                "target_type": target_type,
                "target": target,
                "payload": copy.deepcopy(payload),
                "preview": preview,
                "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
            }
            preview["operation_token"] = token
            self._qdt_record_event(f"{target_type}.patch.stage", token)
            return preview, "json" if preview["accepted"] else "err"
        self.quadtreeDesktop_state = working_state
        self._qdt_refresh_layer_registry()
        if apply_mode == "apply_and_snapshot":
            self.command_quadtree_desktop_snapshot()
        self._qdt_record_event(f"{target_type}.patch.apply", str(target))
        self._render_quadtree_desktop()
        return {**preview, "mutated": True}, "json"

    def _qdt_resolve_target(self, payload: dict[str, object], target_type: str) -> dict[str, str] | None:
        if target_type == "cell":
            parsed = self._qdt_resolve_cell_ref(self._qdt_cell_ref(payload))
            if not parsed:
                return None
            return {"module_id": parsed[0], "layer_type": parsed[1], "path": parsed[2]}
        if target_type == "layer":
            module_id, layer_type = self._qdt_layer_ref(payload)
            return {"module_id": module_id, "layer_type": layer_type}
        if target_type == "module":
            module_id = str(payload.get("module_id", self._qdt_module_from_target(payload)))
            return {"module_id": module_id} if module_id else None
        return None

    def _qdt_apply_patch_to_state(self, state: dict[str, object], target_type: str, target: dict[str, str], patch: dict[str, object]) -> dict[str, object]:
        try:
            if target_type == "module":
                module = state["module_registry"][target["module_id"]]
                protected = {"module_id", "input_layer", "processing_layer", "output_layer"}
                safe_patch = {key: copy.deepcopy(value) for key, value in patch.items() if key not in protected}
                module.update(self._qdt_deep_merge(module, safe_patch))
            elif target_type == "layer":
                module = state["module_registry"][target["module_id"]]
                layer_key = f"{target['layer_type']}_layer"
                layer = module[layer_key]
                safe_patch = {key: copy.deepcopy(value) for key, value in patch.items() if key not in {"layer_type", "root_cell", "cells"}}
                layer.update(self._qdt_deep_merge(layer, safe_patch))
            elif target_type == "cell":
                module = state["module_registry"][target["module_id"]]
                layer = module[f"{target['layer_type']}_layer"]
                cell = layer["cells"][target["path"]]
                if cell.get("locked") and not patch.get("permissions", {}).get("mutate_locked"):
                    return {"accepted": False, "error": "Cell is locked."}
                protected = {"id", "address", "module_id", "layer_type", "path", "parent_id", "child_ids", "depth", "x", "y", "width", "height"}
                safe_patch = {key: copy.deepcopy(value) for key, value in patch.items() if key not in protected}
                merged = self._qdt_deep_merge(cell, safe_patch)
                merged["last_mutation_record"] = self._qdt_mutation_record("cell.patch")
                layer["cells"][target["path"]] = merged
            else:
                return {"accepted": False, "error": f"Unsupported target_type: {target_type}"}
        except KeyError as exc:
            return {"accepted": False, "error": f"Patch target not found: {exc}"}
        return {"accepted": True}

    def _qdt_subdivide_cell(self, module_id: str, layer_type: str, path: str, *, mutate: bool) -> dict[str, object]:
        state = self.quadtreeDesktop_state if mutate else copy.deepcopy(self.quadtreeDesktop_state)
        module = state.get("module_registry", {}).get(module_id)
        if not isinstance(module, dict):
            return {"accepted": False, "error": f"Unknown module: {module_id}"}
        layer = module.get(f"{layer_type}_layer")
        if not isinstance(layer, dict):
            return {"accepted": False, "error": f"Unknown layer: {layer_type}"}
        cell = layer.get("cells", {}).get(path)
        if not isinstance(cell, dict):
            return {"accepted": False, "error": f"Unknown cell path: {path}"}
        if cell.get("child_ids"):
            return {"accepted": False, "error": "Cell is already subdivided."}
        max_depth = int(layer.get("max_depth", layer.get("subdivision_policy", {}).get("max_depth", 4)))
        depth = int(cell.get("depth", 0))
        if depth >= max_depth or depth >= QUADTREE_MAX_DEPTH_LIMIT:
            return {"accepted": False, "error": "Max depth reached."}
        if not cell.get("permissions", {}).get("subdivide", True):
            return {"accepted": False, "error": "Cell does not allow subdivision."}
        x = int(cell.get("x", 0))
        y = int(cell.get("y", 0))
        width = max(int(cell.get("width", 0)) // 2, 1)
        height = max(int(cell.get("height", 0)) // 2, 1)
        child_specs = {
            "nw": {"x": x, "y": y, "width": width, "height": height},
            "ne": {"x": x + width, "y": y, "width": width, "height": height},
            "sw": {"x": x, "y": y + height, "width": width, "height": height},
            "se": {"x": x + width, "y": y + height, "width": width, "height": height},
        }
        child_ids = []
        for quadrant, bounds in child_specs.items():
            child_path = f"{path}.{quadrant}"
            child = self._qdt_create_cell(module_id, layer_type, child_path, parent_id=cell["address"], quadrant=quadrant, depth=depth + 1, bounds=bounds, object_binding=copy.deepcopy(cell.get("object_binding", {})))
            child["status"] = "editable"
            layer["cells"][child_path] = child
            child_ids.append(child["address"])
        cell["child_ids"] = child_ids
        cell["last_mutation_record"] = self._qdt_mutation_record("cell.subdivide")
        if mutate:
            self._qdt_refresh_layer_registry()
            self._qdt_record_event("cell.subdivide", cell["address"])
        return {"accepted": True, "cell": copy.deepcopy(cell), "children": child_ids}

    def _qdt_batch_from_payload(self, payload: object) -> dict[str, object] | None:
        if isinstance(payload, dict) and ("selectors" in payload or "patch" in payload) and "batch_id" not in payload:
            return {
                "batch_id": "ad_hoc",
                "selectors": copy.deepcopy(payload.get("selectors", payload.get("selection", {}))),
                "patch": copy.deepcopy(payload.get("patch", {})),
            }
        batch_id = self._qdt_payload_value(payload, "batch_id", str(self.quadtreeDesktop_state.get("selected_batch_id", "")))
        batch = self.quadtreeDesktop_state.get("batch_registry", {}).get(batch_id)
        return batch if isinstance(batch, dict) else None

    def _qdt_preview_batch(self, batch: dict[str, object], *, mutate: bool) -> dict[str, object]:
        selectors = batch.get("selectors", {})
        patch = batch.get("patch", {})
        if not isinstance(patch, dict):
            return {"accepted": False, "error": "Batch patch must be an object."}
        targets = self._qdt_select_cells(selectors)
        before_state = copy.deepcopy(self.quadtreeDesktop_state)
        before_hash = self._qdt_hash(before_state)
        working_state = copy.deepcopy(self.quadtreeDesktop_state)
        failures = []
        skipped = 0
        for address in targets:
            parsed = self._qdt_parse_address(address)
            if not parsed:
                skipped += 1
                continue
            result = self._qdt_apply_patch_to_state(working_state, "cell", parsed, patch)
            if not result["accepted"]:
                failures.append({"address": address, "error": result.get("error", "patch failed")})
        validation = self._qdt_validate_state(working_state)
        accepted = not failures and bool(validation.get("accepted", False))
        after_hash = self._qdt_hash(working_state) if accepted else before_hash
        token = self._qdt_hash({"batch": batch.get("batch_id", "ad_hoc"), "before": before_hash, "after": after_hash, "time": _dt.datetime.now().isoformat(timespec="seconds")})[:16]
        report = {
            "accepted": accepted,
            "batch_id": batch.get("batch_id", "ad_hoc"),
            "affected_cell_count": len(targets) if accepted else 0,
            "candidate_cell_count": len(targets),
            "skipped_cell_count": skipped,
            "validation_failures": failures + ([] if validation.get("accepted") else validation.get("errors", [])),
            "before_hash": before_hash,
            "after_hash": after_hash,
            "rollback_token": token if accepted and mutate else "",
            "mutated": False,
        }
        if accepted and mutate:
            self.quadtreeDesktop_state = working_state
            self.quadtreeDesktop_state.setdefault("rollback_registry", {})[token] = {"before_state": before_state, "after_hash": after_hash}
            self._qdt_refresh_layer_registry()
            report["mutated"] = True
        return report

    def _qdt_select_cells(self, selectors: object) -> list[str]:
        if isinstance(selectors, list):
            return [str(item) for item in selectors if self._qdt_get_cell_by_ref(str(item))]
        if not isinstance(selectors, dict):
            return copy.deepcopy(self.quadtreeDesktop_state.get("selected_cell_paths", []))
        explicit = selectors.get("addresses", selectors.get("cells", []))
        if isinstance(explicit, list) and explicit:
            return [str(item) for item in explicit if self._qdt_get_cell_by_ref(str(item))]
        results = []
        for module_id, module in self.quadtreeDesktop_state.get("module_registry", {}).items():
            if selectors.get("module_id") and selectors.get("module_id") != module_id:
                continue
            for layer_type in QUADTREE_LAYER_TYPES:
                if selectors.get("layer_type") and selectors.get("layer_type") != layer_type:
                    continue
                layer = module.get(f"{layer_type}_layer", {})
                for cell in layer.get("cells", {}).values() if isinstance(layer, dict) else []:
                    if not isinstance(cell, dict):
                        continue
                    if "depth" in selectors and int(cell.get("depth", -1)) != int(selectors["depth"]):
                        continue
                    if selectors.get("status") and selectors["status"] != cell.get("status"):
                        continue
                    if selectors.get("service_binding") and selectors["service_binding"] != cell.get("service_binding", {}).get("service_id"):
                        continue
                    if selectors.get("api_route_binding") and selectors["api_route_binding"] != cell.get("api_route_binding", {}).get("route"):
                        continue
                    if selectors.get("object_type") and selectors["object_type"] != cell.get("object_binding", {}).get("type"):
                        continue
                    if selectors.get("tag") and selectors["tag"] not in cell.get("tags", []):
                        continue
                    query = str(selectors.get("query", "")).lower()
                    if query and query not in json.dumps(cell, sort_keys=True).lower():
                        continue
                    results.append(str(cell["address"]))
        return results

    def _qdt_validate_state(self, state: object) -> dict[str, object]:
        errors: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        if not isinstance(state, dict):
            return {"accepted": False, "errors": [{"target": "state", "message": "State must be an object."}], "warnings": []}
        modules = state.get("module_registry", {})
        if not isinstance(modules, dict) or not modules:
            errors.append({"target": "module_registry", "message": "At least one module is required."})
        else:
            for module_id, module in modules.items():
                module_report = self._qdt_validate_module(module)
                for item in module_report.get("errors", []):
                    errors.append({"target": f"{module_id}:{item.get('target', '')}", "message": item.get("message", "")})
                warnings.extend(module_report.get("warnings", []))
        report = {
            "accepted": len(errors) == 0,
            "checked_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "errors": errors,
            "warnings": warnings,
            "state_hash": self._qdt_hash(state),
        }
        return report

    def _qdt_validate_module(self, module: object) -> dict[str, object]:
        errors: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        if not isinstance(module, dict):
            return {"accepted": False, "errors": [{"target": "module", "message": "Module must be an object."}], "warnings": []}
        module_id = str(module.get("module_id", ""))
        if not self._qdt_valid_module_id(module_id):
            errors.append({"target": "module_id", "message": "Invalid module_id."})
        if module.get("schema") != "quadtree-module":
            errors.append({"target": "schema", "message": "Module schema must be quadtree-module."})
        for field_name in ("label", "description", "status", "bindings", "batch_profiles", "validation_gates", "permissions", "persistence_policy", "render_policy"):
            if field_name not in module:
                errors.append({"target": field_name, "message": "Missing required module field."})
        for layer_type in QUADTREE_LAYER_TYPES:
            layer = module.get(f"{layer_type}_layer")
            if not isinstance(layer, dict):
                errors.append({"target": f"{layer_type}_layer", "message": "Missing required layer."})
                continue
            errors.extend(self._qdt_validate_layer(module_id, layer_type, layer))
        return {"accepted": len(errors) == 0, "errors": errors, "warnings": warnings}

    def _qdt_validate_layer(self, module_id: str, layer_type: str, layer: dict[str, object]) -> list[dict[str, object]]:
        errors: list[dict[str, object]] = []
        required = ("layer_type", "root_cell", "max_depth", "cell_defaults", "subdivision_policy", "selection_policy", "mutation_policy", "event_policy", "style_policy", "content_policy", "allowed_bindings", "cells")
        for field_name in required:
            if field_name not in layer:
                errors.append({"target": f"{layer_type}.{field_name}", "message": "Missing required layer field."})
        if layer.get("layer_type") != layer_type:
            errors.append({"target": f"{layer_type}.layer_type", "message": "Layer type mismatch."})
        try:
            max_depth = int(layer.get("max_depth", 0))
        except (TypeError, ValueError):
            max_depth = -1
        if max_depth < 0 or max_depth > QUADTREE_MAX_DEPTH_LIMIT:
            errors.append({"target": f"{layer_type}.max_depth", "message": f"max_depth must be 0..{QUADTREE_MAX_DEPTH_LIMIT}."})
        cells = layer.get("cells", {})
        if not isinstance(cells, dict) or "root" not in cells:
            errors.append({"target": f"{layer_type}.cells", "message": "Layer must contain root cell."})
            return errors
        for path, cell in cells.items():
            if not isinstance(cell, dict):
                errors.append({"target": f"{layer_type}.{path}", "message": "Cell must be an object."})
                continue
            expected = self._qdt_address(module_id, layer_type, path)
            if cell.get("address") != expected:
                errors.append({"target": expected, "message": "Cell address does not match module/layer/path."})
            if int(cell.get("depth", 0)) > max_depth:
                errors.append({"target": expected, "message": "Cell depth exceeds layer max_depth."})
            for field_name in ("parent_id", "child_ids", "quadrant", "x", "y", "width", "height", "z_order", "visible", "locked", "selected", "status", "object_binding", "command_binding", "api_route_binding", "service_binding", "style_binding", "content_binding", "validators", "event_handlers", "permissions", "last_mutation_record"):
                if field_name not in cell:
                    errors.append({"target": expected, "message": f"Missing cell field: {field_name}."})
            service_id = str(cell.get("service_binding", {}).get("service_id", ""))
            if service_id and service_id not in self.services:
                errors.append({"target": expected, "message": f"Unknown service binding: {service_id}."})
            route = str(cell.get("api_route_binding", {}).get("route", ""))
            if route and route not in self.api_routes:
                errors.append({"target": expected, "message": f"Unknown API route binding: {route}."})
            command_name = str(cell.get("command_binding", {}).get("command", ""))
            if command_name and command_name not in self._configure4_known_commands() and command_name not in self.configure4_state.get("registered_runtime_commands", {}):
                errors.append({"target": expected, "message": f"Unknown command binding: {command_name}."})
            if bool(cell.get("permissions", {}).get("execute", False)):
                errors.append({"target": expected, "message": "Cells may not directly execute kernel actions; they must stage commands."})
        return errors

    def _qdt_deep_merge(self, base: object, patch: object) -> object:
        if isinstance(base, dict) and isinstance(patch, dict):
            result = copy.deepcopy(base)
            for key, value in patch.items():
                result[key] = self._qdt_deep_merge(result.get(key), value) if key in result else copy.deepcopy(value)
            return result
        return copy.deepcopy(patch)

    def _qdt_get_path(self, root: object, parts: list[str]) -> tuple[bool, object]:
        current = root
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                return False, None
        return True, copy.deepcopy(current)

    def _qdt_set_path(self, root: dict[str, object], parts: list[str], value: object) -> None:
        current = root
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        if parts:
            current[parts[-1]] = copy.deepcopy(value)

    def _qdt_refresh_layer_registry(self) -> None:
        registry = {}
        for module_id, module in self.quadtreeDesktop_state.get("module_registry", {}).items():
            if not isinstance(module, dict):
                continue
            for layer_type in QUADTREE_LAYER_TYPES:
                layer = module.get(f"{layer_type}_layer")
                if isinstance(layer, dict):
                    registry[f"{module_id}:{layer_type}"] = layer
        self.quadtreeDesktop_state["layer_registry"] = registry

    def _qdt_mutation_record(self, kind: str) -> dict[str, str]:
        return {"kind": kind, "time": _dt.datetime.now().isoformat(timespec="seconds"), "boundary": "blue.cli.engine"}

    def _qdt_operation_token(self, target_type: str, target: dict[str, str], patch: dict[str, object]) -> str:
        return self._qdt_hash({"target_type": target_type, "target": target, "patch": patch, "time": _dt.datetime.now().isoformat(timespec="seconds")})[:16]

    def _qdt_hash(self, payload: object) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()

    def _qdt_state_hash(self) -> str:
        payload = copy.deepcopy(self.quadtreeDesktop_state)
        payload.pop("render_cache", None)
        return self._qdt_hash(payload)[:16]

    def _qdt_record_event(self, kind: str, detail: str) -> None:
        entry = {"time": _dt.datetime.now().isoformat(timespec="seconds"), "kind": kind, "detail": detail}
        self.quadtreeDesktop_state.setdefault("event_log", []).append(entry)
        if len(self.quadtreeDesktop_state["event_log"]) > QUADTREE_EVENT_LIMIT:
            self.quadtreeDesktop_state["event_log"] = self.quadtreeDesktop_state["event_log"][-QUADTREE_EVENT_LIMIT:]
        self._record_event(f"quadtree.{kind}", detail)

    def _restore_quadtree_desktop_state(self, payload: object) -> None:
        if not isinstance(payload, dict):
            self.quadtreeDesktop_state = self._create_quadtree_desktop_state()
            self._qdt_record_event("restore", "Malformed state reset to defaults.")
            return
        existing_state = self.__dict__.get("quadtreeDesktop_state", {})
        previous_visible = bool(existing_state.get("visible", False)) if isinstance(existing_state, dict) else False
        self.quadtreeDesktop_state = copy.deepcopy(payload)
        self.quadtreeDesktop_state.setdefault("desktop_id", QUADTREE_DESKTOP_ID)
        self.quadtreeDesktop_state.setdefault("version", QUADTREE_DESKTOP_VERSION)
        self.quadtreeDesktop_state.setdefault("activation_state", "dormant")
        self.quadtreeDesktop_state.setdefault("visible", previous_visible)
        self.quadtreeDesktop_state.setdefault("selected_module_ids", ["qdt.system.services"])
        self.quadtreeDesktop_state.setdefault("selected_layer_type", "input")
        self.quadtreeDesktop_state.setdefault("selected_cell_paths", [])
        self.quadtreeDesktop_state.setdefault("batch_registry", {})
        self.quadtreeDesktop_state.setdefault("rollback_registry", {})
        self.quadtreeDesktop_state.setdefault("pending_operations", {})
        self.quadtreeDesktop_state.setdefault("event_log", [])
        self.quadtreeDesktop_state.setdefault("validation_reports", {})
        self.quadtreeDesktop_state.setdefault("render_cache", {})
        self.quadtreeDesktop_state.setdefault("persistence_metadata", {"policy": "manifest"})
        self.quadtreeDesktop_state.setdefault("export_metadata", {})
        self._qdt_refresh_layer_registry()

    def _show_quadtree_desktop(self) -> None:
        if self.shell_frame is None or self.console_card is None:
            return
        shell = self.shell_frame
        shell.rowconfigure(0, weight=3)
        shell.rowconfigure(1, weight=2)
        self.console_card.grid_configure(row=1, column=0, sticky="nsew", pady=(10, 0))
        if self.quadtree_desktop_frame is None:
            self.quadtree_desktop_frame = self._build_quadtree_desktop_surface(shell)
        self.quadtree_desktop_frame.grid(row=0, column=0, sticky="nsew")
        self._render_quadtree_desktop()

    def _hide_quadtree_desktop(self) -> None:
        if self.quadtree_desktop_frame is not None:
            self.quadtree_desktop_frame.grid_remove()
        if self.shell_frame is not None and self.console_card is not None:
            self.shell_frame.rowconfigure(0, weight=1)
            self.shell_frame.rowconfigure(1, weight=0)
            self.console_card.grid_configure(row=0, column=0, sticky="nsew", pady=0)

    def _build_quadtree_desktop_surface(self, parent: tk.Widget) -> tk.Frame:
        frame = self.card(parent, padx=10, pady=10)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=2)
        header = tk.Frame(frame, bg=Theme.panel)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        header.columnconfigure(1, weight=1)
        tk.Label(header, text="QUADTREE DESKTOP", bg=Theme.panel, fg=Theme.cyan, font=self.font_micro).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="graphical actions stage/preview only; blue CLI remains authoritative",
            bg=Theme.panel,
            fg=Theme.muted,
            font=self.font_small,
        ).grid(row=0, column=1, sticky="w", padx=(12, 0))
        tk.Button(
            header,
            text="HIDE",
            command=lambda: self.stage_command("quadtree.desktop.hide"),
            bg=Theme.card_2,
            fg=Theme.text,
            activebackground=Theme.blue_2,
            activeforeground=Theme.blue_text,
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
            font=self.font_small,
        ).grid(row=0, column=2, sticky="e")

        left = tk.Frame(frame, bg=Theme.panel)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        layer_bar = tk.Frame(left, bg=Theme.panel)
        layer_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.quadtree_layer_var = tk.StringVar(value=str(self.quadtreeDesktop_state.get("selected_layer_type", "input")))
        for index, layer_type in enumerate(QUADTREE_LAYER_TYPES):
            tk.Button(
                layer_bar,
                text=layer_type.upper(),
                command=lambda value=layer_type: self._qdt_stage_layer_switch(value),
                bg=Theme.card_2,
                fg=Theme.text,
                activebackground=Theme.blue_2,
                activeforeground=Theme.blue_text,
                relief="flat",
                bd=0,
                padx=8,
                pady=5,
                font=self.font_small,
            ).grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 6, 0))
            layer_bar.columnconfigure(index, weight=1)
        self.quadtree_canvas = tk.Canvas(left, bg="#000000", highlightthickness=1, highlightbackground=Theme.border)
        self.quadtree_canvas.grid(row=1, column=0, sticky="nsew")
        self.quadtree_canvas.bind("<Button-1>", self._qdt_canvas_click)
        self.quadtree_canvas.bind("<Button-3>", self._qdt_canvas_right_click)

        right = tk.Frame(frame, bg=Theme.panel)
        right.grid(row=1, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)
        right.columnconfigure(0, weight=1)
        tk.Label(right, text="SELECTED CELL INSPECTOR", bg=Theme.panel, fg=Theme.muted, font=self.font_micro).grid(row=0, column=0, sticky="w")
        self.quadtree_inspector_text = ScrolledText(right, height=7, bg="#000000", fg=Theme.text, insertbackground=Theme.text, relief="flat", font=("Consolas", 9), wrap="word")
        self.quadtree_inspector_text.grid(row=1, column=0, sticky="nsew", pady=(4, 8))
        tk.Label(right, text="MODULE + BATCH INSPECTORS", bg=Theme.panel, fg=Theme.muted, font=self.font_micro).grid(row=2, column=0, sticky="w")
        inspectors = tk.Frame(right, bg=Theme.panel)
        inspectors.grid(row=3, column=0, sticky="nsew", pady=(4, 8))
        inspectors.columnconfigure(0, weight=1)
        inspectors.columnconfigure(1, weight=1)
        inspectors.rowconfigure(0, weight=1)
        self.quadtree_module_text = ScrolledText(inspectors, height=6, bg="#000000", fg=Theme.muted, insertbackground=Theme.text, relief="flat", font=("Consolas", 9), wrap="word")
        self.quadtree_module_text.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.quadtree_batch_text = ScrolledText(inspectors, height=6, bg="#000000", fg=Theme.muted, insertbackground=Theme.text, relief="flat", font=("Consolas", 9), wrap="word")
        self.quadtree_batch_text.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        tk.Label(right, text="COMMAND PREVIEW", bg=Theme.panel, fg=Theme.muted, font=self.font_micro).grid(row=4, column=0, sticky="w")
        self.quadtree_preview_text = ScrolledText(right, height=5, bg="#000000", fg=Theme.cyan, insertbackground=Theme.text, relief="flat", font=("Consolas", 9), wrap="word")
        self.quadtree_preview_text.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        for widget in (self.quadtree_inspector_text, self.quadtree_module_text, self.quadtree_batch_text, self.quadtree_preview_text):
            widget.configure(state="disabled")
        return frame

    def _qdt_stage_layer_switch(self, layer_type: str) -> None:
        self.quadtreeDesktop_state["selected_layer_type"] = layer_type
        self._qdt_record_event("layer.switch", layer_type)
        self.stage_command(f'quadtree.desktop.layer.get {{"module_id":"{self._qdt_current_module_id()}","layer_type":"{layer_type}"}}')
        self._render_quadtree_desktop()

    def _qdt_current_module_id(self) -> str:
        selected = self.quadtreeDesktop_state.get("selected_module_ids", ["qdt.system.services"])
        if isinstance(selected, list) and selected:
            return str(selected[0])
        return "qdt.system.services"

    def _render_quadtree_desktop(self) -> None:
        if self.quadtree_canvas is None or self.quadtree_desktop_frame is None or not bool(self.quadtreeDesktop_state.get("visible", False)):
            return
        module_id = self._qdt_current_module_id()
        layer_type = str(self.quadtreeDesktop_state.get("selected_layer_type", "input"))
        layer = self._qdt_get_layer(module_id, layer_type)
        if not layer:
            return
        self.quadtree_canvas.delete("all")
        width = max(int(self.quadtree_canvas.winfo_width() or 560), 200)
        height = max(int(self.quadtree_canvas.winfo_height() or 360), 200)
        root = layer.get("cells", {}).get("root", {})
        scale_x = width / max(int(root.get("width", 560)), 1)
        scale_y = height / max(int(root.get("height", 560)), 1)
        cells = sorted(layer.get("cells", {}).values(), key=lambda cell: (int(cell.get("depth", 0)), int(cell.get("z_order", 0))))
        for cell in cells:
            self._qdt_draw_cell(cell, scale_x, scale_y)
        self._qdt_refresh_inspectors()

    def _qdt_draw_cell(self, cell: dict[str, object], scale_x: float, scale_y: float) -> None:
        if self.quadtree_canvas is None or not cell.get("visible", True):
            return
        x0 = int(cell.get("x", 0) * scale_x)
        y0 = int(cell.get("y", 0) * scale_y)
        x1 = int((cell.get("x", 0) + cell.get("width", 0)) * scale_x)
        y1 = int((cell.get("y", 0) + cell.get("height", 0)) * scale_y)
        fill = str(cell.get("style_binding", {}).get("fill", ""))
        outline = str(cell.get("style_binding", {}).get("outline", ""))
        status = str(cell.get("status", "dormant"))
        status_bg, status_fg, status_border = STATUS_COLORS.get(status, (Theme.card_2, Theme.muted, Theme.border))
        fill = fill or status_bg
        outline = outline or (Theme.cyan if cell.get("selected") else status_border)
        width = 3 if cell.get("selected") else 1
        address = str(cell.get("address", ""))
        self.quadtree_canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=width, tags=("qdt-cell", address))
        text = str(cell.get("content_binding", {}).get("text", cell.get("path", "")))
        if int(cell.get("width", 0)) * scale_x > 42 and int(cell.get("height", 0)) * scale_y > 26:
            self.quadtree_canvas.create_text((x0 + x1) // 2, (y0 + y1) // 2, text=text[:28], fill=status_fg, font=("Consolas", 8), tags=("qdt-cell", address))

    def _qdt_refresh_inspectors(self) -> None:
        selected_addresses = self.quadtreeDesktop_state.get("selected_cell_paths", [])
        selected_cell = self._qdt_get_cell_by_ref(str(selected_addresses[0])) if selected_addresses else None
        module = self._qdt_get_module(self._qdt_current_module_id())
        batch_id = str(self.quadtreeDesktop_state.get("selected_batch_id", ""))
        batch = self.quadtreeDesktop_state.get("batch_registry", {}).get(batch_id, {}) if batch_id else {}
        preview = {
            "staged_command": f'quadtree.desktop.cell.get {{"address":"{selected_addresses[0]}"}}' if selected_addresses else "quadtree.desktop.module.list",
            "selected_layer": self.quadtreeDesktop_state.get("selected_layer_type", "input"),
            "note": "Canvas gestures record input events and stage blue CLI commands only.",
        }
        self._qdt_write_text_widget(self.quadtree_inspector_text, json.dumps(selected_cell or {"selected": None}, indent=2))
        self._qdt_write_text_widget(self.quadtree_module_text, json.dumps({"module_id": self._qdt_current_module_id(), "label": module.get("label", "") if module else ""}, indent=2))
        self._qdt_write_text_widget(self.quadtree_batch_text, json.dumps(batch or {"selected_batch_id": ""}, indent=2))
        self._qdt_write_text_widget(self.quadtree_preview_text, json.dumps(preview, indent=2))

    def _qdt_write_text_widget(self, widget: ScrolledText | None, text: str) -> None:
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _qdt_canvas_click(self, event: tk.Event) -> None:
        address = self._qdt_canvas_address_at(event)
        if not address:
            return
        self._qdt_set_selection([address])
        self._qdt_record_event("input.click", address)
        self.stage_command(f'quadtree.desktop.cell.get {{"address":"{address}"}}')
        self._render_quadtree_desktop()

    def _qdt_canvas_right_click(self, event: tk.Event) -> None:
        address = self._qdt_canvas_address_at(event)
        if not address:
            return
        self._qdt_set_selection([address])
        self._qdt_record_event("input.right_click", address)
        command = f'quadtree.desktop.preview {{"target":"{address}","context_actions":["inspect","subdivide","bind","patch","batch_select"]}}'
        self.stage_command(command)
        self._render_quadtree_desktop()

    def _qdt_canvas_address_at(self, event: tk.Event) -> str:
        if self.quadtree_canvas is None:
            return ""
        item = self.quadtree_canvas.find_withtag("current")
        if not item:
            item = self.quadtree_canvas.find_closest(event.x, event.y)
        if not item:
            return ""
        tags = self.quadtree_canvas.gettags(item[0])
        for tag in tags:
            if tag.startswith("qdt://"):
                return tag
        return ""

    def _create_configure4_state(self) -> dict[str, object]:
        return {
            "service_id": CONFIGURE4_SERVICE_ID,
            "label": CONFIGURE4_LABEL,
            "mode": "manual",
            "settings": {
                "default_sink": "memory",
                "max_variants": CONFIGURE4_MAX_VARIANTS,
                "max_drafts": CONFIGURE4_MAX_DRAFTS,
                "default_persistence_policy": "manifest",
                "default_file_access_policy": "none",
                "default_side_effect_policy": "memory_only",
                "registration_policy": "staged_by_default",
                "allow_custom_fields": True,
            },
            "drafts": {},
            "generated_service_drafts": {},
            "current_draft_id": "",
            "validation_reports": {},
            "registration_history": [],
            "diagnostics": [],
            "registered_runtime_services": {},
            "registered_runtime_commands": {},
            "registered_runtime_routes": {},
            "next_draft_index": 1,
        }

    def dispatch_configure4_command(self, cmd: str, args: list[str], raw_after_cmd: str) -> tuple[str, str]:
        if not self.require_service(CONFIGURE4_SERVICE_ID):
            return f"{CONFIGURE4_SERVICE_ID} is dormant. Activate it first: service.activate {CONFIGURE4_SERVICE_ID}", "err"
        action = cmd.split(".", 1)[1]
        if action == "help":
            return self.command_configure4_help(), "ok"
        if action == "status":
            return self.command_configure4_status(), "json"
        if action == "mode":
            return self.command_configure4_mode(args[0] if args else ""), "json"
        if action == "new":
            return self.command_configure4_new(raw_after_cmd)
        if action == "set":
            if not args:
                return "Usage: configure4.set <path> <value>", "err"
            value_raw = raw_after_cmd.split(maxsplit=1)[1] if len(raw_after_cmd.split(maxsplit=1)) > 1 else ""
            return self.command_configure4_set(args[0], value_raw)
        if action == "get":
            return self.command_configure4_get(args[0] if args else ""), "json"
        if action == "validate":
            return self.command_configure4_validate(args[0] if args else "all"), "json"
        if action == "preview":
            return self.command_configure4_preview(args[0] if args else ""), "json"
        if action == "register":
            return self.command_configure4_register(args[0] if args else ""), "json"
        if action == "export":
            if not args:
                return "Usage: configure4.export <path>", "err"
            return self.command_configure4_export(args[0])
        if action == "import":
            if not args:
                return "Usage: configure4.import <path>", "err"
            return self.command_configure4_import(args[0])
        if action == "sample":
            return self.command_configure4_sample(), "json"
        if action == "reset":
            return self.command_configure4_reset(args[0] if args else ""), "json"
        if action == "history":
            return self.command_configure4_history(), "json"
        if action == "list":
            return self.command_configure4_list(), "json"
        return f"Unknown configure4 command: {cmd}. Try configure4.help.", "err"

    def dispatch_configure4_runtime_command(self, cmd: str, raw_after_cmd: str) -> tuple[str, str] | None:
        commands = self.configure4_state.get("registered_runtime_commands", {})
        if not isinstance(commands, dict) or cmd not in commands:
            return None
        record = commands.get(cmd, {})
        if not isinstance(record, dict):
            return None
        service_id = str(record.get("service_id", ""))
        if not self.require_service(service_id):
            return f"Service {service_id} is dormant. Activate it first: service.activate {service_id}", "err"
        payload = self.parse_payload(raw_after_cmd)
        result = self.generic_configure4_service_handler(service_id, cmd, payload)
        return self.format_json(result), "json"

    def command_configure4_help(self) -> str:
        return self._configure4_help_text()

    def command_configure4_status(self) -> str:
        return self.format_json(self._configure4_status_payload())

    def command_configure4_mode(self, mode_text: str) -> str:
        if not mode_text:
            return self.format_json({"mode": self.configure4_state.get("mode", "manual"), "allowed": list(CONFIGURE4_ALLOWED_MODES)})
        mode = configure4_normalize_mode(mode_text)
        if mode not in CONFIGURE4_ALLOWED_MODES:
            diag = self._configure4_append_diagnostic(
                "error",
                "mode",
                f"Unsupported configure4 mode: {mode_text}",
                "Use manual, semi_auto, or auto.",
            )
            return self.format_json({"accepted": False, "diagnostic": diag, "allowed": list(CONFIGURE4_ALLOWED_MODES)})
        self.configure4_state["mode"] = mode
        self._record_event("configure4.mode", mode)
        return self.format_json({"accepted": True, "mode": mode})

    def command_configure4_new(self, payload_raw: str) -> tuple[str, str]:
        payload, error = self._configure4_parse_json_object(payload_raw)
        if error:
            diag = self._configure4_append_diagnostic("error", "configure4.new", error, "Submit a JSON object.")
            return self.format_json({"accepted": False, "diagnostics": [diag]}), "err"
        mode = configure4_normalize_mode(payload.get("mode", self.configure4_state.get("mode", "manual")))
        if mode not in CONFIGURE4_ALLOWED_MODES:
            diag = self._configure4_append_diagnostic("error", "configure4.new", f"Unsupported mode: {mode}", "Use configure4.mode first or include a valid mode.")
            return self.format_json({"accepted": False, "diagnostics": [diag]}), "err"
        if mode == "manual":
            spec, missing = self._configure4_manual_spec(payload)
            if missing:
                diag = self._configure4_append_diagnostic(
                    "error",
                    "configure4.new",
                    "Manual mode rejected an incomplete service specification.",
                    "Provide every required field or switch to semi_auto.",
                )
                return self.format_json({"accepted": False, "missing_required_fields": missing, "diagnostics": [diag]}), "err"
        elif mode == "semi_auto":
            spec = self._configure4_semi_auto_spec(payload)
        else:
            spec = self._configure4_auto_spec(payload)
            if spec is None:
                diag = self._configure4_append_diagnostic(
                    "error",
                    "configure4.new",
                    "Automatic mode requires an intent string.",
                    "Example: configure4.new {\"intent\":\"create a diagnostics summarizer service\"}",
                )
                return self.format_json({"accepted": False, "diagnostics": [diag]}), "err"

        max_drafts = int(self.configure4_state.get("settings", {}).get("max_drafts", CONFIGURE4_MAX_DRAFTS))
        drafts = self.configure4_state.setdefault("drafts", {})
        if isinstance(drafts, dict) and len(drafts) >= max_drafts:
            diag = self._configure4_append_diagnostic("error", "configure4.new", "Draft limit reached.", "Reset old drafts or raise settings.max_drafts.")
            return self.format_json({"accepted": False, "diagnostics": [diag]}), "err"
        if spec.draft_id in drafts:
            diag = self._configure4_append_diagnostic("error", spec.draft_id, "Draft id already exists.", "Use configure4.reset for the old draft or choose a new draft_id.")
            return self.format_json({"accepted": False, "diagnostics": [diag]}), "err"

        drafts[spec.draft_id] = spec.to_dict()
        self.configure4_state["current_draft_id"] = spec.draft_id
        if mode == "auto":
            self.configure4_state.setdefault("generated_service_drafts", {})[spec.draft_id] = spec.to_dict()
        report = self._configure4_validate_spec(spec, append=False)
        self.configure4_state.setdefault("validation_reports", {})[spec.draft_id] = report
        self._record_event("configure4.new", spec.draft_id)
        tag = "json" if report["accepted"] else "warn"
        return self.format_json({"accepted": True, "draft_id": spec.draft_id, "mode": mode, "spec_hash": report["spec_hash"], "validation": report}), tag

    def command_configure4_set(self, path: str, value_raw: str) -> tuple[str, str]:
        if not path or not value_raw:
            return "Usage: configure4.set <path> <value>", "err"
        value = self._configure4_parse_value(value_raw)
        target, parts, error = self._configure4_resolve_state_path(path, for_write=True)
        if error:
            diag = self._configure4_append_diagnostic("error", path, error)
            return self.format_json({"accepted": False, "diagnostics": [diag]}), "err"
        self._configure4_set_path(target, parts, value)
        draft_id = self._configure4_path_draft_id(path)
        if draft_id:
            draft = self.configure4_state["drafts"].get(draft_id)
            if isinstance(draft, dict):
                draft.setdefault("metadata", {})["updated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
                inferred = draft.get("inferred_fields", [])
                relative = ".".join(parts)
                if isinstance(inferred, list) and relative in inferred:
                    inferred.remove(relative)
        diag = self._configure4_append_diagnostic("accepted", path, "Field updated through blue CLI command.")
        self._record_event("configure4.set", path)
        return self.format_json({"accepted": True, "path": path, "value": value, "diagnostic": diag}), "json"

    def command_configure4_get(self, path: str) -> str:
        if not path:
            return self.format_json(copy.deepcopy(self.configure4_state))
        target, parts, error = self._configure4_resolve_state_path(path, for_write=False)
        if error:
            return self.format_json({"error": error, "path": path})
        found, value = self._configure4_get_path(target, parts)
        if not found:
            return self.format_json({"error": "path not found", "path": path})
        return self.format_json(value)

    def command_configure4_validate(self, target: str) -> str:
        return self.format_json(self._configure4_validate_target(target or "all", append=True))

    def command_configure4_preview(self, target: str) -> str:
        draft_id = self._configure4_default_draft_id(target)
        spec = self._configure4_get_spec(draft_id)
        if spec is None:
            return self.format_json({"accepted": False, "error": f"Unknown draft: {draft_id or '<none>'}"})
        preview = self._configure4_build_preview(spec, append_validation=True)
        self._record_event("configure4.preview", spec.draft_id)
        return self.format_json(preview)

    def command_configure4_register(self, target: str) -> str:
        draft_id = self._configure4_default_draft_id(target)
        result = self._configure4_register_draft(draft_id)
        return self.format_json(result)

    def command_configure4_export(self, path: str) -> tuple[str, str]:
        if not self.require_service("kernel.fs"):
            return "kernel.fs is dormant. Activate it first: service.activate kernel.fs", "err"
        output_path = Path(path).expanduser()
        if output_path.parent and str(output_path.parent) not in {"", "."}:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"configure4_state": copy.deepcopy(self.configure4_state)}
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        self.configure4_state.setdefault("settings", {})["last_export_path"] = str(output_path)
        self._configure4_append_diagnostic("accepted", "configure4.export", f"Exported configure4 state to {output_path}.")
        self._record_event("configure4.export", str(output_path))
        return f"Exported configure4 state to {output_path}", "ok"

    def command_configure4_import(self, path: str) -> tuple[str, str]:
        if not self.require_service("kernel.fs"):
            return "kernel.fs is dormant. Activate it first: service.activate kernel.fs", "err"
        input_path = Path(path).expanduser()
        with open(input_path, "r", encoding="utf-8") as handle:
            text = handle.read()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = self._configure4_parse_key_value_config(text)
        if isinstance(payload, dict) and "configure4_state" in payload:
            self._restore_configure4_state(payload["configure4_state"])
            imported = {"kind": "state", "drafts": len(self.configure4_state.get("drafts", {}))}
        elif isinstance(payload, dict):
            spec = self._configure4_semi_auto_spec(payload)
            self.configure4_state.setdefault("drafts", {})[spec.draft_id] = spec.to_dict()
            self.configure4_state["current_draft_id"] = spec.draft_id
            imported = {"kind": "draft", "draft_id": spec.draft_id}
        else:
            diag = self._configure4_append_diagnostic("error", "configure4.import", "Import payload is not a JSON object or key-value fabric config.")
            return self.format_json({"accepted": False, "diagnostics": [diag]}), "err"
        self.configure4_state.setdefault("settings", {})["last_import_path"] = str(input_path)
        self._configure4_append_diagnostic("accepted", "configure4.import", f"Imported configure4 payload from {input_path}.")
        self._record_event("configure4.import", str(input_path))
        return self.format_json({"accepted": True, "source": str(input_path), "imported": imported}), "json"

    def command_configure4_sample(self) -> str:
        return self.format_json(self._configure4_sample_payload())

    def command_configure4_reset(self, target: str) -> str:
        if target in {"", "all", "*"}:
            self._remove_configure4_runtime_registrations()
            self.configure4_state = self._create_configure4_state()
            self._record_event("configure4.reset", "all")
            return self.format_json({"accepted": True, "reset": "all"})
        drafts = self.configure4_state.setdefault("drafts", {})
        if not isinstance(drafts, dict) or target not in drafts:
            return self.format_json({"accepted": False, "error": f"Unknown draft: {target}"})
        self._remove_configure4_runtime_registrations(draft_id=target)
        drafts.pop(target, None)
        self.configure4_state.setdefault("generated_service_drafts", {}).pop(target, None)
        self.configure4_state.setdefault("validation_reports", {}).pop(target, None)
        if self.configure4_state.get("current_draft_id") == target:
            self.configure4_state["current_draft_id"] = next(iter(drafts), "")
        self._record_event("configure4.reset", target)
        return self.format_json({"accepted": True, "reset": target})

    def command_configure4_history(self) -> str:
        return self.format_json(
            {
                "diagnostics": copy.deepcopy(self.configure4_state.get("diagnostics", [])),
                "validation_reports": copy.deepcopy(self.configure4_state.get("validation_reports", {})),
                "registration_history": copy.deepcopy(self.configure4_state.get("registration_history", [])),
            }
        )

    def command_configure4_list(self) -> str:
        drafts = self.configure4_state.get("drafts", {})
        rows = []
        if isinstance(drafts, dict):
            for draft_id, payload in drafts.items():
                spec = Configure4Spec.from_dict(payload)
                rows.append(
                    {
                        "draft_id": draft_id,
                        "mode": spec.mode,
                        "service_id": spec.identity.get("service_id", ""),
                        "label": spec.identity.get("label", ""),
                        "hash": self._configure4_spec_hash(spec),
                        "current": draft_id == self.configure4_state.get("current_draft_id"),
                    }
                )
        return self.format_json(rows)

    def _configure4_help_text(self) -> str:
        return f"""
{CONFIGURE4_LABEL} ({CONFIGURE4_SERVICE_ID})

Purpose
  configure_4 is the internal authoring fabric for start.py services. It stages a
  service specification, validates it, previews the exact integration plan, and
  registers only runtime-safe service records. It never opens a visual editor and
  never executes generated code with eval or exec. All use happens through blue
  CLI commands and all results are printed to the REPL Console.

Activation
  service.activate {CONFIGURE4_SERVICE_ID}
  configure4.status
  configure4.sample

Core workflow
  1. Choose a mode:
       configure4.mode manual
       configure4.mode semi_auto
       configure4.mode auto
  2. Stage a draft:
       configure4.new {{json}}
  3. Inspect and patch fields:
       configure4.get
       configure4.get identity.service_id
       configure4.set execution_behavior.can_register_immediately true
  4. Validate:
       configure4.validate all
  5. Preview the exact start.py integration plan:
       configure4.preview <draft-id>
  6. Register only when the preview says the draft is runtime-safe:
       configure4.register <draft-id>
  7. Persist:
       service.activate kernel.fs
       service.activate codex.manifest
       manifest.save codex_project/configure4_manifest.json

Operating modes
  manual
    Every required field must be supplied. Missing service identity, command
    surface, API surface, execution behavior, validation, persistence, examples,
    object graph, and metadata fields are rejected with diagnostics. Use this
    when you want full deterministic control.

  semi_auto
    A partial service specification is accepted and safe defaults are inferred.
    Inferred fields are recorded in inferred_fields and can be reviewed or patched
    with configure4.set before validation or registration.

  auto
    A high-level intent string is expanded into a complete staged service spec.
    Automatic mode never silently registers a generated service. The draft must
    be reviewed with configure4.preview, patched if needed, validated, and then
    explicitly registered.

Service specification map
  identity.service_id
    Stable lowercase dot-delimited id, such as codex.text.generator.
  identity.label
    User-facing label.
  identity.aliases
    Optional aliases for service.activate resolution.
  command_surface.verbs
    Blue CLI command tokens to expose after runtime registration.
  command_surface.handler_name
    Use generic_configure4_service_handler for runtime-safe registration.
  api_surface.routes
    Optional routes. Each must start with /. Routes are callable only through
    api.gateway and only when the generated service is active.
  api_surface.handler_name
    Use generic_configure4_api_handler for runtime-safe registration.
  execution_behavior.activation_requirements
    Must include blue.cli.engine. Existing activation checks are not weakened.
  execution_behavior.can_register_immediately
    false means the draft can be staged and previewed but registration returns a
    patch plan. true allows runtime registration when all other gates pass.
  persistence_behavior.policy
    memory_only, manifest, manifest_and_export, or disabled.
  generated_code_plan.flow
    The deterministic generation flow used by preview output.
  custom_fields
    Free-form developer metadata. Validation preserves custom_fields and does not
    reject unknown keys.

Generation flows
  literal
    Writes input_value once with optional prefix, suffix, and separator.

  template
    Replaces {{name}} placeholders in template using generated_code_plan.flow.values.
    This is the best flow for reusable text, file headers, CLI messages, source
    snippets, and pointer strings.

  cartesian
    Generates bounded combinations from input_value with input_width. This is
    useful for enumerating short symbolic names, test ids, route suffixes, enum
    variants, or pointer-like reference keys. The product is guarded by
    settings.max_variants.

  repeat
    Writes input_value input_width times, bounded by settings.max_variants.

  reverse
    Writes input_value reversed once.

  service_scaffold
    Generates a complete start.py service integration plan: service registry
    entry, command branches, API routes, handler skeletons, persistence notes,
    validation diagnostics, and a stable spec hash.

Text generation
  configure_4 can stage text generators as services. Use literal for one-off
  content, template for structured text, repeat for fixed lists, reverse for
  transforms, and cartesian for bounded variants. Text output defaults to memory
  or console preview. Filesystem writes require explicit intent through kernel.fs
  style commands or an export path.

  Minimal text generator:
    configure4.mode semi_auto
    configure4.new {{"service_id":"codex.text.banner","label":"CodexTextBanner","description":"Generates release banner text.","verbs":["text.banner.run"],"flow_type":"template","template":"Project {{name}} targets {{language}}.","generated_code_plan":{{"flow":{{"type":"template","template":"Project {{name}} targets {{language}}.","values":{{"name":"demo","language":"Python"}},"output_target":"memory","separator":"\\n"}}}}}}
    configure4.preview <draft-id>

Pointer generation
  A pointer in configure_4 documentation means a stable textual reference: a file
  path, API route, service id, symbol id, object graph id, test id, or source
  location string. It is not a raw memory pointer and configure_4 does not
  dereference memory. Use pointer generation to create consistent names that can
  be consumed by another service or by a future code emitter.

  Pointer-style template:
    configure4.new {{"mode":"semi_auto","service_id":"codex.pointer.index","label":"CodexPointerIndex","description":"Generates stable symbol pointers.","verbs":["pointer.index.run"],"flow_type":"template","generated_code_plan":{{"flow":{{"type":"template","template":"{{root}}/{{module}}.py::{{symbol}}","values":{{"root":"src","module":"diagnostics","symbol":"summarize"}},"output_target":"memory","separator":"\\n"}}}}}}

  Bounded pointer variants:
    configure4.new {{"mode":"semi_auto","service_id":"codex.pointer.variants","label":"CodexPointerVariants","description":"Generates bounded pointer suffixes.","verbs":["pointer.variants.run"],"flow_type":"cartesian","input_value":"ab","input_width":3,"prefix":"route.","suffix":".handler","can_register_immediately":false}}

Creating codebases in any programming language
  configure_4 does not assume one language. Put language-specific decisions in
  custom_fields.codebase and keep generated_code_plan.flow.type as
  service_scaffold or template. This creates a deterministic service draft and
  previewable plan that can describe files, directories, package metadata, build
  commands, tests, linters, docs, and release steps for any language.

  Recommended codebase fields:
    custom_fields.codebase.language
    custom_fields.codebase.project_type
    custom_fields.codebase.package_manager
    custom_fields.codebase.files
    custom_fields.codebase.entrypoints
    custom_fields.codebase.build_commands
    custom_fields.codebase.test_commands
    custom_fields.codebase.quality_gates
    custom_fields.codebase.output_policy

  Language-agnostic codebase draft:
    configure4.mode auto
    configure4.new {{"mode":"auto","intent":"create a Rust command line codebase that validates JSON manifests","custom_fields":{{"codebase":{{"language":"Rust","project_type":"cli","package_manager":"cargo","files":[{{"path":"Cargo.toml","role":"package manifest"}},{{"path":"src/main.rs","role":"entrypoint"}},{{"path":"tests/manifest_validation.rs","role":"integration tests"}}],"build_commands":["cargo build"],"test_commands":["cargo test"],"quality_gates":["format","lint","tests"],"output_policy":"preview first, write files only after explicit filesystem command"}}}}}}
    configure4.validate all
    configure4.preview <draft-id>

  For another language, change only custom_fields.codebase.language, files,
  commands, and package metadata. Examples: Python with pyproject.toml, Go with
  go.mod, TypeScript with package.json, C with Makefile, Java with pom.xml or
  build.gradle, C# with .csproj, Zig with build.zig, or any custom toolchain.

Registration rules
  Runtime registration succeeds only when validation passes, the draft allows
  immediate registration, commands/routes do not collide, activation dependencies
  are valid, file behavior is safe, and the handlers can be represented by the
  existing generic handlers. If a draft names Python methods that do not already
  exist, configure4.register refuses to fake success and returns a patch plan.

API routes
  service.activate api.gateway
  service.activate {CONFIGURE4_SERVICE_ID}
  api.call /configure4/status
  api.call /configure4/specs
  api.call /configure4/validate {{"target":"all"}}
  api.call /configure4/preview {{"draft_id":"draft_001"}}
  api.call /configure4/register {{"draft_id":"draft_001"}}

Persistence and history
  configure4_state is included in current_project_payload, manifest.save,
  manifest.load, and version.snapshot. The saved state includes staged specs,
  generated service drafts, validation reports, registration history,
  diagnostics, settings, and runtime registration metadata.

Safety notes
  Only the REPL Console and blue CLI engine are visible.
  configure_4 does not create panels, dialogs, pop-ups, palettes, toolbars,
  secondary windows, or graphical editors.
  Defaults use memory/console sinks. File writes require explicit commands.
  eval and exec are never used.
  blue.cli.engine cannot be deactivated or bypassed.
""".strip()

    def _configure4_parse_json_object(self, payload_raw: str) -> tuple[dict[str, object], str]:
        raw = payload_raw.strip()
        if not raw:
            return {}, "Missing JSON object."
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {}, f"Malformed JSON: {exc}"
        if not isinstance(payload, dict):
            return {}, "configure4.new requires a JSON object."
        return payload, ""

    def _configure4_parse_value(self, value_raw: str) -> object:
        raw = value_raw.strip()
        if not raw:
            return ""
        if raw[0] in "[{\"" or raw in {"true", "false", "null"} or re.fullmatch(r"-?\d+(\.\d+)?", raw):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
        return raw

    def _configure4_next_draft_id(self) -> str:
        index = int(self.configure4_state.get("next_draft_index", 1))
        while True:
            draft_id = f"draft_{index:03d}"
            index += 1
            if draft_id not in self.configure4_state.get("drafts", {}):
                self.configure4_state["next_draft_index"] = index
                return draft_id

    def _configure4_manual_spec(self, payload: dict[str, object]) -> tuple[Configure4Spec, list[str]]:
        expanded = self._configure4_expand_aliases(payload)
        missing = [path for path in CONFIGURE4_MANUAL_REQUIRED_PATHS if not self._configure4_path_exists(expanded, path)]
        draft_id = str(expanded.get("draft_id") or payload.get("draft_id") or self._configure4_next_draft_id())
        expanded["draft_id"] = draft_id
        expanded["mode"] = "manual"
        expanded.setdefault("diagnostics", [])
        expanded.setdefault("inferred_fields", [])
        expanded.setdefault("custom_fields", {})
        metadata = expanded.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.setdefault("created_at", _dt.datetime.now().isoformat(timespec="seconds"))
            metadata.setdefault("updated_at", metadata["created_at"])
        return Configure4Spec.from_dict(expanded), missing

    def _configure4_semi_auto_spec(self, payload: dict[str, object]) -> Configure4Spec:
        expanded = self._configure4_expand_aliases(payload)
        draft_id = str(expanded.get("draft_id") or payload.get("draft_id") or self._configure4_next_draft_id())
        defaults = self._configure4_default_spec_payload(expanded, "semi_auto", intent=str(expanded.get("intent", "")), draft_id=draft_id)
        provided_paths = set(self._configure4_flat_paths(expanded))
        merged = self._configure4_deep_merge(defaults, expanded)
        merged["draft_id"] = draft_id
        merged["mode"] = "semi_auto"
        merged["inferred_fields"] = sorted(path for path in self._configure4_flat_paths(defaults) if path not in provided_paths and not path.startswith("metadata."))
        return Configure4Spec.from_dict(merged)

    def _configure4_auto_spec(self, payload: dict[str, object]) -> Configure4Spec | None:
        intent = str(payload.get("intent", "")).strip()
        if not intent:
            return None
        expanded = self._configure4_expand_aliases(payload)
        draft_id = str(expanded.get("draft_id") or payload.get("draft_id") or self._configure4_next_draft_id())
        defaults = self._configure4_default_spec_payload(expanded, "auto", intent=intent, draft_id=draft_id)
        generated_service_id = configure4_dotted_id(intent)
        service_slug = generated_service_id.replace(".", "-")
        command_prefix = ".".join(generated_service_id.split(".")[-2:])
        auto_payload = {
            "identity": {
                "service_id": generated_service_id,
                "label": configure4_pascal_label(intent),
                "aliases": [service_slug, generated_service_id.split(".")[-1]],
                "layer": "codex-authoring",
                "state": "dormant",
                "description": f"Synthesized from intent: {intent}",
                "version": "0.1.0",
            },
            "command_surface": {
                "verbs": [f"{command_prefix}.status", f"{command_prefix}.run", f"{command_prefix}.preview"],
                "handler_name": CONFIGURE4_GENERIC_HANDLER_NAME,
                "help_text": f"Generated service for intent: {intent}",
                "default_payload": {"intent": intent},
            },
            "api_surface": {
                "routes": [f"/configure4/generated/{service_slug}"],
                "handler_name": CONFIGURE4_GENERIC_API_HANDLER_NAME,
                "payload_schema": {"type": "object", "additionalProperties": True},
                "output_schema": {"type": "object", "required": ["service", "payload"]},
            },
            "execution_behavior": {
                "activation_requirements": ["blue.cli.engine"],
                "dependency_requirements": [],
                "allowed_modes": list(CONFIGURE4_ALLOWED_MODES),
                "timeout_policy": {"seconds": 30},
                "file_access_policy": "none",
                "side_effect_policy": "memory_only",
                "can_register_immediately": False,
            },
            "generated_code_plan": {
                "handler_name": CONFIGURE4_GENERIC_HANDLER_NAME,
                "api_handler_name": CONFIGURE4_GENERIC_API_HANDLER_NAME,
                "runtime_strategy": "generic_service_record",
                "flow": {
                    "type": "service_scaffold",
                    "input_value": intent,
                    "input_width": 1,
                    "output_target": "memory",
                    "prefix": "",
                    "suffix": "",
                    "separator": "\n",
                },
            },
            "metadata": {"intent": intent, "owner": "configure4.auto", "review_required": True},
        }
        provided_paths = set(self._configure4_flat_paths(expanded))
        merged = self._configure4_deep_merge(defaults, auto_payload)
        merged = self._configure4_deep_merge(merged, expanded)
        merged["draft_id"] = draft_id
        merged["mode"] = "auto"
        merged["inferred_fields"] = sorted(path for path in self._configure4_flat_paths(merged) if path not in provided_paths and path not in {"draft_id", "mode"})
        return Configure4Spec.from_dict(merged)

    def _configure4_default_spec_payload(self, seed: dict[str, object], mode: str, *, intent: str, draft_id: str) -> dict[str, object]:
        identity = seed.get("identity", {}) if isinstance(seed.get("identity", {}), dict) else {}
        service_id = str(identity.get("service_id", "") or configure4_dotted_id(intent or identity.get("label", draft_id)))
        label = str(identity.get("label", "") or configure4_pascal_label(service_id))
        short = ".".join(service_id.split(".")[-2:]) if "." in service_id else service_id
        now = _dt.datetime.now().isoformat(timespec="seconds")
        flow = {
            "type": "service_scaffold",
            "input_value": service_id,
            "input_width": 1,
            "output_target": "memory",
            "prefix": "",
            "suffix": "",
            "separator": "\n",
        }
        return {
            "draft_id": draft_id,
            "mode": mode,
            "identity": {
                "service_id": service_id,
                "label": label,
                "aliases": [service_id.split(".")[-1]],
                "layer": "codex-authoring",
                "state": "dormant",
                "description": str(identity.get("description", "Generated by configure_4.authoring.fabric.")),
                "version": "0.1.0",
            },
            "command_surface": {
                "verbs": [f"{short}.status", f"{short}.run"],
                "handler_name": CONFIGURE4_GENERIC_HANDLER_NAME,
                "help_text": f"{label} generated by configure_4.authoring.fabric.",
                "default_payload": {},
            },
            "api_surface": {
                "routes": [],
                "handler_name": CONFIGURE4_GENERIC_API_HANDLER_NAME,
                "payload_schema": {"type": "object", "additionalProperties": True},
                "output_schema": {"type": "object", "additionalProperties": True},
            },
            "execution_behavior": {
                "activation_requirements": ["blue.cli.engine"],
                "dependency_requirements": [],
                "allowed_modes": list(CONFIGURE4_ALLOWED_MODES),
                "timeout_policy": {"seconds": 30},
                "file_access_policy": "none",
                "side_effect_policy": "memory_only",
                "can_register_immediately": False,
            },
            "validation_rules": {
                "gates": [
                    "service_id",
                    "command_surface",
                    "api_surface",
                    "activation_dependencies",
                    "filesystem_policy",
                    "flow_bounds",
                    "handler_presence",
                ],
                "allow_command_collisions": False,
            },
            "persistence_behavior": {
                "policy": "manifest",
                "import_path": "",
                "export_path": "",
                "versioning_policy": "snapshot_in_manifest",
            },
            "examples": [f"service.activate {service_id}", f"{short}.status"],
            "generated_code_plan": {
                "handler_name": CONFIGURE4_GENERIC_HANDLER_NAME,
                "api_handler_name": CONFIGURE4_GENERIC_API_HANDLER_NAME,
                "runtime_strategy": "generic_service_record",
                "flow": flow,
            },
            "diagnostics": [],
            "metadata": {"created_at": now, "updated_at": now, "owner": "configure4", "review_required": True},
            "object_graph": self._configure4_default_object_graph(service_id, flow),
            "custom_fields": {},
        }

    def _configure4_default_object_graph(self, service_id: str, flow: dict[str, object]) -> list[dict[str, object]]:
        return [
            Configure4FabricRecord(kind="object", name=service_id, role="service", state="staged").to_dict(),
            Configure4FabricRecord(kind="input", name=f"{service_id}.payload", role="default_payload", state="staged").to_dict(),
            Configure4FabricRecord(kind="flow", name=str(flow.get("type", "service_scaffold")), role="generation", value=copy.deepcopy(flow), links=[service_id], state="staged").to_dict(),
            Configure4FabricRecord(kind="output", name=f"{service_id}.preview", role="integration_plan", links=[service_id], state="staged").to_dict(),
            Configure4FabricRecord(kind="lifecycle", name=f"{service_id}.lifecycle", role="stage_validate_preview_register", links=[service_id], state="staged").to_dict(),
        ]

    def _configure4_expand_aliases(self, payload: dict[str, object]) -> dict[str, object]:
        expanded: dict[str, object] = {}
        custom: dict[str, object] = {}
        section_names = {
            "draft_id",
            "mode",
            "intent",
            "identity",
            "command_surface",
            "api_surface",
            "execution_behavior",
            "validation_rules",
            "persistence_behavior",
            "examples",
            "generated_code_plan",
            "diagnostics",
            "metadata",
            "object_graph",
            "custom_fields",
            "inferred_fields",
        }
        for key, value in payload.items():
            if key in CONFIGURE4_FIELD_ALIASES:
                self._configure4_set_path(expanded, CONFIGURE4_FIELD_ALIASES[key].split("."), copy.deepcopy(value))
            elif key in section_names:
                expanded[key] = copy.deepcopy(value)
            else:
                custom[key] = copy.deepcopy(value)
        if custom:
            existing = expanded.get("custom_fields", {})
            if not isinstance(existing, dict):
                existing = {}
            existing.update(custom)
            expanded["custom_fields"] = existing
        return expanded

    def _configure4_deep_merge(self, base: object, overlay: object) -> object:
        if isinstance(base, dict) and isinstance(overlay, dict):
            result = copy.deepcopy(base)
            for key, value in overlay.items():
                if key in result:
                    result[key] = self._configure4_deep_merge(result[key], value)
                else:
                    result[key] = copy.deepcopy(value)
            return result
        return copy.deepcopy(overlay)

    def _configure4_flat_paths(self, payload: object, prefix: str = "") -> list[str]:
        if isinstance(payload, dict):
            paths: list[str] = []
            for key, value in payload.items():
                child = f"{prefix}.{key}" if prefix else str(key)
                paths.extend(self._configure4_flat_paths(value, child))
            return paths
        return [prefix] if prefix else []

    def _configure4_path_exists(self, payload: object, path: str) -> bool:
        found, _value = self._configure4_get_path(payload, path.split("."))
        return found

    def _configure4_get_path(self, root: object, parts: list[str]) -> tuple[bool, object]:
        current = root
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                return False, None
        return True, copy.deepcopy(current)

    def _configure4_set_path(self, root: object, parts: list[str], value: object) -> None:
        if not isinstance(root, dict) or not parts:
            return
        current = root
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = copy.deepcopy(value)

    def _configure4_resolve_state_path(self, path: str, *, for_write: bool) -> tuple[object, list[str], str]:
        parts = [part for part in path.split(".") if part]
        if not parts:
            return self.configure4_state, [], "Empty path."
        if parts[0] == "settings":
            return self.configure4_state, parts, ""
        if parts[0] == "drafts":
            if len(parts) < 2:
                return self.configure4_state, parts, ""
            if parts[1] not in self.configure4_state.get("drafts", {}):
                return self.configure4_state, parts, f"Unknown draft: {parts[1]}"
            return self.configure4_state["drafts"][parts[1]], parts[2:], ""
        drafts = self.configure4_state.get("drafts", {})
        if isinstance(drafts, dict) and parts[0] in drafts:
            return drafts[parts[0]], parts[1:], ""
        current = str(self.configure4_state.get("current_draft_id", ""))
        if current and isinstance(drafts, dict) and current in drafts:
            return drafts[current], parts, ""
        if for_write:
            return self.configure4_state, parts, "No current draft. Create a draft first or address settings.*."
        return self.configure4_state, parts, ""

    def _configure4_path_draft_id(self, path: str) -> str:
        parts = [part for part in path.split(".") if part]
        drafts = self.configure4_state.get("drafts", {})
        if parts[:1] == ["drafts"] and len(parts) > 1:
            return parts[1]
        if isinstance(drafts, dict) and parts and parts[0] in drafts:
            return parts[0]
        current = str(self.configure4_state.get("current_draft_id", ""))
        return current if current and parts and parts[0] != "settings" else ""

    def _configure4_default_draft_id(self, target: str) -> str:
        if target and target not in {"current", "."}:
            return target
        return str(self.configure4_state.get("current_draft_id", ""))

    def _configure4_get_spec(self, draft_id: str) -> Configure4Spec | None:
        drafts = self.configure4_state.get("drafts", {})
        if not draft_id or not isinstance(drafts, dict) or draft_id not in drafts:
            return None
        return Configure4Spec.from_dict(drafts[draft_id])

    def _configure4_validate_target(self, target: str, *, append: bool) -> dict[str, object]:
        drafts = self.configure4_state.get("drafts", {})
        if not isinstance(drafts, dict):
            return {"accepted": False, "error": "Draft store is unavailable."}
        if target in {"all", "*", ""}:
            reports = {}
            accepted = True
            for draft_id in sorted(drafts):
                spec = Configure4Spec.from_dict(drafts[draft_id])
                report = self._configure4_validate_spec(spec, append=append)
                reports[draft_id] = report
                accepted = accepted and bool(report.get("accepted"))
            return {"accepted": accepted, "reports": reports}
        spec = self._configure4_get_spec(target)
        if spec is None:
            return {"accepted": False, "error": f"Unknown draft: {target}"}
        return self._configure4_validate_spec(spec, append=append)

    def _configure4_validate_spec(self, spec: Configure4Spec, *, append: bool) -> dict[str, object]:
        errors: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        info: list[dict[str, object]] = []

        def issue(bucket: list[dict[str, object]], severity: str, target: str, message: str, recommendation: str = "") -> None:
            entry = {
                "severity": severity,
                "target": target,
                "message": message,
                "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
                "recommendation": recommendation,
            }
            bucket.append(entry)
            if append:
                self._configure4_append_diagnostic(severity, target, message, recommendation)

        service_id = str(spec.identity.get("service_id", ""))
        if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", service_id):
            issue(errors, "error", "identity.service_id", "Service id must be stable, lowercase, and dot-delimited.")
        if service_id in {"", "blue.cli.engine", CONFIGURE4_SERVICE_ID}:
            issue(errors, "error", "identity.service_id", "Reserved service id cannot be generated.")
        existing = self.services.get(service_id)
        registered = self.configure4_state.get("registered_runtime_services", {})
        if existing and service_id not in registered:
            issue(errors, "error", "identity.service_id", f"Service id already exists: {service_id}", "Choose another id.")

        state = str(spec.identity.get("state", "dormant"))
        if state == "active":
            issue(errors, "error", "identity.state", "Generated services may not start active.", "Use dormant; activate later through service.activate.")
        elif state not in {"dormant", "staged", "faulted"}:
            issue(warnings, "warning", "identity.state", f"Unusual service state: {state}", "Use dormant for services that can be registered.")

        aliases = spec.identity.get("aliases", [])
        if not isinstance(aliases, list):
            issue(errors, "error", "identity.aliases", "Aliases must be a list.")

        verbs = spec.command_surface.get("verbs", [])
        allow_collisions = bool(spec.validation_rules.get("allow_command_collisions", False))
        if not isinstance(verbs, list) or not verbs:
            issue(errors, "error", "command_surface.verbs", "At least one command verb is required.")
            verbs = []
        known_commands = self._configure4_known_commands()
        dynamic_commands = self.configure4_state.get("registered_runtime_commands", {})
        for verb_obj in verbs:
            verb = str(verb_obj).lower()
            if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)*", verb):
                issue(errors, "error", f"command:{verb}", "Command names must be lowercase CLI tokens.")
            if verb.startswith("configure4."):
                issue(errors, "error", f"command:{verb}", "configure4.* is reserved for the authoring fabric.")
            if not allow_collisions and (verb in known_commands or verb in dynamic_commands):
                issue(errors, "error", f"command:{verb}", "Command collides with an existing blue CLI command.", "Choose a unique command or explicitly allow collisions for review-only drafts.")

        routes = spec.api_surface.get("routes", [])
        if not isinstance(routes, list):
            issue(errors, "error", "api_surface.routes", "API routes must be a list.")
            routes = []
        registered_routes = self.configure4_state.get("registered_runtime_routes", {})
        for route_obj in routes:
            route = str(route_obj)
            if not route.startswith("/"):
                issue(errors, "error", f"api_route:{route}", "API routes must start with /.")
            if any(ch.isspace() for ch in route):
                issue(errors, "error", f"api_route:{route}", "API routes cannot contain whitespace.")
            if not allow_collisions and route in self.api_routes and route not in registered_routes:
                issue(errors, "error", f"api_route:{route}", "API route collides with an existing route.")

        handler_name = str(spec.generated_code_plan.get("handler_name", spec.command_surface.get("handler_name", "")))
        api_handler_name = str(spec.generated_code_plan.get("api_handler_name", spec.api_surface.get("handler_name", "")))
        if handler_name != CONFIGURE4_GENERIC_HANDLER_NAME and not hasattr(self, handler_name):
            issue(errors, "error", "generated_code_plan.handler_name", f"Missing command handler method: {handler_name}", "Use the generic handler or apply the preview patch plan.")
        if routes and api_handler_name != CONFIGURE4_GENERIC_API_HANDLER_NAME and not hasattr(self, api_handler_name):
            issue(errors, "error", "generated_code_plan.api_handler_name", f"Missing API handler method: {api_handler_name}", "Use the generic API handler or apply the preview patch plan.")

        flow = spec.generated_code_plan.get("flow", {})
        if not isinstance(flow, dict):
            issue(errors, "error", "generated_code_plan.flow", "Flow must be an object.")
            flow = {}
        flow_type = str(flow.get("type", spec.execution_behavior.get("flow_type", "service_scaffold")))
        if flow_type not in CONFIGURE4_ALLOWED_FLOW_TYPES:
            issue(errors, "error", "generated_code_plan.flow.type", f"Unsupported flow type: {flow_type}")
        else:
            bounded = self._configure4_check_flow_bounds(flow)
            if not bounded["ok"]:
                issue(errors, "error", "generated_code_plan.flow", str(bounded["message"]), "Reduce input_width, input values, or repeat count.")

        persistence_policy = str(spec.persistence_behavior.get("policy", "manifest"))
        if persistence_policy not in CONFIGURE4_ALLOWED_PERSISTENCE_POLICIES:
            issue(errors, "error", "persistence_behavior.policy", f"Unsupported persistence policy: {persistence_policy}")

        file_policy = str(spec.execution_behavior.get("file_access_policy", "none"))
        if file_policy not in CONFIGURE4_ALLOWED_FILE_POLICIES:
            issue(errors, "error", "execution_behavior.file_access_policy", f"Unsupported file access policy: {file_policy}")
        side_effect_policy = str(spec.execution_behavior.get("side_effect_policy", "memory_only"))
        if side_effect_policy not in CONFIGURE4_ALLOWED_SIDE_EFFECT_POLICIES:
            issue(errors, "error", "execution_behavior.side_effect_policy", f"Unsupported side-effect policy: {side_effect_policy}")
        output_target = str(flow.get("output_target", "memory"))
        filesystem_targets = {"stdout", "console", "memory", "json", "file-preview", ""}
        if output_target not in filesystem_targets and file_policy not in {"write_explicit", "read_write_explicit", "manifest_only"}:
            issue(errors, "error", "generated_code_plan.flow.output_target", "Filesystem output target requires an explicit file access policy.")

        allowed_modes = spec.execution_behavior.get("allowed_modes", list(CONFIGURE4_ALLOWED_MODES))
        if not isinstance(allowed_modes, list) or not all(configure4_normalize_mode(item) in CONFIGURE4_ALLOWED_MODES for item in allowed_modes):
            issue(errors, "error", "execution_behavior.allowed_modes", "allowed_modes must contain only manual, semi_auto, or auto.")

        timeout_policy = spec.execution_behavior.get("timeout_policy", {})
        if isinstance(timeout_policy, dict):
            seconds = timeout_policy.get("seconds", 30)
            if not isinstance(seconds, int) or seconds < 1 or seconds > 600:
                issue(errors, "error", "execution_behavior.timeout_policy", "Timeout seconds must be an integer from 1 to 600.")
        else:
            issue(errors, "error", "execution_behavior.timeout_policy", "timeout_policy must be an object.")

        activation_requirements = spec.execution_behavior.get("activation_requirements", [])
        dependency_requirements = spec.execution_behavior.get("dependency_requirements", [])
        if not isinstance(activation_requirements, list):
            issue(errors, "error", "execution_behavior.activation_requirements", "activation_requirements must be a list.")
            activation_requirements = []
        if "blue.cli.engine" not in activation_requirements:
            issue(errors, "error", "execution_behavior.activation_requirements", "blue.cli.engine must remain an activation requirement.")
        for dependency in list(activation_requirements) + (dependency_requirements if isinstance(dependency_requirements, list) else []):
            dep_id = self.resolve_service_id(str(dependency))
            if dep_id != service_id and dep_id not in self.services:
                issue(errors, "error", f"dependency:{dependency}", "Unknown activation or dependency requirement.")
        if not isinstance(dependency_requirements, list):
            issue(errors, "error", "execution_behavior.dependency_requirements", "dependency_requirements must be a list.")

        if spec.mode == "auto" and bool(spec.execution_behavior.get("can_register_immediately", False)):
            issue(warnings, "warning", "execution_behavior.can_register_immediately", "Automatic drafts should be reviewed before registration.")

        if not errors:
            issue(info, "accepted", spec.draft_id, "Validation accepted.")

        report = {
            "draft_id": spec.draft_id,
            "service_id": service_id,
            "accepted": len(errors) == 0,
            "spec_hash": self._configure4_spec_hash(spec),
            "checked_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "errors": errors,
            "warnings": warnings,
            "info": info,
        }
        self.configure4_state.setdefault("validation_reports", {})[spec.draft_id] = copy.deepcopy(report)
        drafts = self.configure4_state.get("drafts", {})
        if isinstance(drafts, dict) and spec.draft_id in drafts:
            drafts[spec.draft_id]["diagnostics"] = errors + warnings + info
        return report

    def _configure4_known_commands(self) -> set[str]:
        return {
            "help",
            "?",
            "clear",
            "history",
            "blue.engine",
            "terminal.cwd",
            "terminal.cd",
            "terminal.timeout",
            "linux",
            "bash",
            "sh",
            "pwsh",
            "powershell",
            "powershell7",
            "service.list",
            "service.status",
            "service.activate",
            "service.deactivate",
            "service.restart",
            "service.exec",
            "api.list",
            "api.call",
            "api.register",
            "kernel.info",
            "set",
            "get",
            "vars",
            "manifest.show",
            "manifest.save",
            "manifest.load",
            "node.list",
            "node.select",
            "node.add",
            "node.patch",
            "node.validate",
            "file.search",
            "diagnostics.list",
            "diagnostics.patch",
            "emit.preview",
            "build.run",
            "version.snapshot",
            "version.list",
            "reboot",
            "configure4.help",
            "configure4.status",
            "configure4.mode",
            "configure4.new",
            "configure4.set",
            "configure4.get",
            "configure4.validate",
            "configure4.preview",
            "configure4.register",
            "configure4.export",
            "configure4.import",
            "configure4.sample",
            "configure4.reset",
            "configure4.history",
            "configure4.list",
            "quadtree.desktop.status",
            "quadtree.desktop.show",
            "quadtree.desktop.hide",
            "quadtree.desktop.module.create",
            "quadtree.desktop.module.list",
            "quadtree.desktop.module.get",
            "quadtree.desktop.module.patch",
            "quadtree.desktop.layer.get",
            "quadtree.desktop.layer.patch",
            "quadtree.desktop.cell.get",
            "quadtree.desktop.cell.set",
            "quadtree.desktop.cell.patch",
            "quadtree.desktop.cell.reset",
            "quadtree.desktop.cell.subdivide",
            "quadtree.desktop.cell.bind",
            "quadtree.desktop.selection.set",
            "quadtree.desktop.batch.create",
            "quadtree.desktop.batch.select",
            "quadtree.desktop.batch.patch",
            "quadtree.desktop.batch.validate",
            "quadtree.desktop.batch.preview",
            "quadtree.desktop.batch.apply",
            "quadtree.desktop.batch.rollback",
            "quadtree.desktop.validate",
            "quadtree.desktop.preview",
            "quadtree.desktop.apply",
            "quadtree.desktop.export.manifest",
            "quadtree.desktop.export.image",
            "quadtree.desktop.import.manifest",
            "quadtree.desktop.snapshot",
        }

    def _configure4_check_flow_bounds(self, flow: dict[str, object]) -> dict[str, object]:
        flow_type = str(flow.get("type", "service_scaffold"))
        max_variants = int(self.configure4_state.get("settings", {}).get("max_variants", CONFIGURE4_MAX_VARIANTS))
        if flow_type == "cartesian":
            alphabet = str(flow.get("input_value", ""))
            try:
                width = int(flow.get("input_width", 1))
            except (TypeError, ValueError):
                return {"ok": False, "message": "input_width must be an integer."}
            count, ok = self._configure4_safe_power(len(alphabet), width, max_variants)
            if not ok:
                return {"ok": False, "message": f"Cartesian flow would exceed {max_variants} variants."}
            return {"ok": True, "count": count}
        if flow_type == "repeat":
            try:
                count = int(flow.get("input_width", 1))
            except (TypeError, ValueError):
                return {"ok": False, "message": "repeat input_width must be an integer."}
            if count < 0 or count > max_variants:
                return {"ok": False, "message": f"Repeat flow must be between 0 and {max_variants}."}
            return {"ok": True, "count": count}
        return {"ok": True, "count": 1}

    def _configure4_safe_power(self, base: int, exp: int, limit: int) -> tuple[int, bool]:
        if base <= 0 or exp < 0:
            return 0, False
        result = 1
        for _index in range(exp):
            if result > limit // max(base, 1):
                return result, False
            result *= base
        return result, result <= limit

    def _configure4_safe_product(self, values: list[int], limit: int) -> tuple[int, bool]:
        result = 1
        for value in values:
            if value < 0 or result > limit // max(value, 1):
                return result, False
            result *= value
        return result, result <= limit

    def _configure4_build_preview(self, spec: Configure4Spec, *, append_validation: bool) -> dict[str, object]:
        report = self._configure4_validate_spec(spec, append=append_validation)
        service_entry = self._configure4_service_entry_from_spec(spec)
        routes = self._configure4_api_route_entries_from_spec(spec)
        flow_sink = Configure4MemorySink()
        self._configure4_generate_flow(spec, flow_sink)
        preview = {
            "draft_id": spec.draft_id,
            "service_id": spec.identity.get("service_id", ""),
            "spec_hash": report["spec_hash"],
            "accepted": report["accepted"],
            "service_registry_entry": service_entry,
            "service_registry_tuple_for_create_services": self._configure4_registry_tuple_snippet(spec),
            "dispatch_command_branches": self._configure4_dispatch_branch_snippets(spec),
            "api_routes_for_create_api_routes": routes,
            "api_route_snippets": self._configure4_api_route_snippets(spec),
            "handler_method_skeletons": self._configure4_handler_skeletons(spec),
            "persistence_additions": [
                "current_project_payload includes configure4_state.",
                "manifest.save persists configure4_state through current_project_payload.",
                "manifest.load restores configure4_state through _restore_configure4_state.",
                "version.snapshot records configure4 draft and registration counts.",
            ],
            "help_text_additions": [str(spec.command_surface.get("help_text", ""))],
            "generated_flow_preview": flow_sink.getvalue(),
            "validation": report,
            "patch_plan_required": not report["accepted"] or self._configure4_requires_python_patch(spec),
        }
        return preview

    def _configure4_service_entry_from_spec(self, spec: Configure4Spec) -> dict[str, object]:
        service_id = str(spec.identity.get("service_id", ""))
        return {
            "id": service_id,
            "label": str(spec.identity.get("label", service_id)),
            "layer": str(spec.identity.get("layer", "codex-authoring")),
            "state": "dormant",
            "description": str(spec.identity.get("description", "Generated by configure_4.authoring.fabric.")),
            "examples": [str(item) for item in spec.examples],
            "aliases": [str(item) for item in spec.identity.get("aliases", [])] if isinstance(spec.identity.get("aliases", []), list) else [],
            "activated_at": "",
            "last_result": "",
            "calls": 0,
            "configure4_generated": True,
            "configure4_draft_id": spec.draft_id,
            "configure4_spec_hash": self._configure4_spec_hash(spec),
        }

    def _configure4_api_route_entries_from_spec(self, spec: Configure4Spec) -> dict[str, dict[str, object]]:
        routes = {}
        route_list = spec.api_surface.get("routes", [])
        if not isinstance(route_list, list):
            return routes
        service_id = str(spec.identity.get("service_id", ""))
        for route_obj in route_list:
            route = str(route_obj)
            routes[route] = {
                "service": service_id,
                "description": f"Generated route for {service_id}.",
                "handler": str(spec.generated_code_plan.get("api_handler_name", spec.api_surface.get("handler_name", CONFIGURE4_GENERIC_API_HANDLER_NAME))),
            }
        return routes

    def _configure4_registry_tuple_snippet(self, spec: Configure4Spec) -> str:
        return "\n".join(
            [
                "(",
                f"    {str(spec.identity.get('service_id', ''))!r},",
                f"    {str(spec.identity.get('layer', 'codex-authoring'))!r},",
                "    'dormant',",
                f"    {str(spec.identity.get('description', ''))!r},",
                f"    {[str(item) for item in spec.examples]!r},",
                "),",
            ]
        )

    def _configure4_dispatch_branch_snippets(self, spec: Configure4Spec) -> list[str]:
        snippets = []
        service_id = str(spec.identity.get("service_id", ""))
        verbs = spec.command_surface.get("verbs", [])
        if not isinstance(verbs, list):
            return snippets
        for verb in verbs:
            snippets.append(
                "\n".join(
                    [
                        f"if cmd == {str(verb)!r}:",
                        f"    if not self.require_service({service_id!r}):",
                        f"        return 'Service {service_id} is dormant. Activate it first: service.activate {service_id}', 'err'",
                        f"    return self.{CONFIGURE4_GENERIC_HANDLER_NAME}({service_id!r}, cmd, self.parse_payload(raw_after_cmd)), 'json'",
                    ]
                )
            )
        return snippets

    def _configure4_api_route_snippets(self, spec: Configure4Spec) -> list[str]:
        snippets = []
        service_id = str(spec.identity.get("service_id", ""))
        routes = spec.api_surface.get("routes", [])
        if not isinstance(routes, list):
            return snippets
        for route in routes:
            snippets.append(
                f"{str(route)!r}: {{'service': {service_id!r}, 'description': 'Generated route for {service_id}.', 'handler': self.{CONFIGURE4_GENERIC_API_HANDLER_NAME}}},"
            )
        return snippets

    def _configure4_handler_skeletons(self, spec: Configure4Spec) -> dict[str, str]:
        service_id = str(spec.identity.get("service_id", ""))
        handler_name = str(spec.generated_code_plan.get("handler_name", spec.command_surface.get("handler_name", CONFIGURE4_GENERIC_HANDLER_NAME)))
        api_handler_name = str(spec.generated_code_plan.get("api_handler_name", spec.api_surface.get("handler_name", CONFIGURE4_GENERIC_API_HANDLER_NAME)))
        return {
            handler_name: "\n".join(
                [
                    f"def {handler_name}(self, service_id: str, command: str, payload: object) -> dict[str, object]:",
                    f"    # Generated command handler skeleton for {service_id}.",
                    "    return {'service': service_id, 'command': command, 'payload': payload}",
                ]
            ),
            api_handler_name: "\n".join(
                [
                    f"def {api_handler_name}(self, service_id: str, route: str, payload: object) -> dict[str, object]:",
                    f"    # Generated API handler skeleton for {service_id}.",
                    "    return {'service': service_id, 'route': route, 'payload': payload}",
                ]
            ),
        }

    def _configure4_register_draft(self, draft_id: str) -> dict[str, object]:
        spec = self._configure4_get_spec(draft_id)
        if spec is None:
            return {"accepted": False, "error": f"Unknown draft: {draft_id or '<none>'}"}
        report = self._configure4_validate_spec(spec, append=True)
        if not report["accepted"]:
            self._configure4_append_diagnostic("error", spec.draft_id, "Registration refused because validation failed.", "Run configure4.preview for the patch plan.")
            return {"accepted": False, "reason": "validation_failed", "validation": report, "patch_plan": self._configure4_build_preview(spec, append_validation=False)}
        if not bool(spec.execution_behavior.get("can_register_immediately", False)):
            self._configure4_append_diagnostic(
                "warning",
                spec.draft_id,
                "Registration refused because the draft is staged for review only.",
                "Patch execution_behavior.can_register_immediately to true after review.",
            )
            return {"accepted": False, "reason": "staged_for_review", "validation": report, "patch_plan": self._configure4_build_preview(spec, append_validation=False)}
        if self._configure4_requires_python_patch(spec):
            self._configure4_append_diagnostic("error", spec.draft_id, "Registration requires Python methods that cannot be injected safely.", "Apply the preview patch plan to start.py.")
            return {"accepted": False, "reason": "python_patch_required", "validation": report, "patch_plan": self._configure4_build_preview(spec, append_validation=False)}

        service_id = str(spec.identity.get("service_id", ""))
        service_entry = self._configure4_service_entry_from_spec(spec)
        self.services[service_id] = service_entry
        self._configure4_bind_runtime_commands(spec)
        self._configure4_bind_runtime_routes(spec)
        event = {
            "time": _dt.datetime.now().isoformat(timespec="seconds"),
            "draft_id": spec.draft_id,
            "service_id": service_id,
            "spec_hash": report["spec_hash"],
            "commands": copy.deepcopy(spec.command_surface.get("verbs", [])),
            "routes": copy.deepcopy(spec.api_surface.get("routes", [])),
            "status": "registered",
        }
        self.configure4_state.setdefault("registration_history", []).append(event)
        self.configure4_state.setdefault("registered_runtime_services", {})[service_id] = {
            "draft_id": spec.draft_id,
            "service_id": service_id,
            "spec_hash": report["spec_hash"],
            "service": service_entry,
        }
        self._configure4_trim_history()
        self._configure4_append_diagnostic("accepted", spec.draft_id, f"Registered runtime service {service_id}.")
        self._record_event("configure4.register", service_id)
        return {"accepted": True, "registered": event, "service": service_entry}

    def _configure4_requires_python_patch(self, spec: Configure4Spec) -> bool:
        handler_name = str(spec.generated_code_plan.get("handler_name", spec.command_surface.get("handler_name", CONFIGURE4_GENERIC_HANDLER_NAME)))
        api_handler_name = str(spec.generated_code_plan.get("api_handler_name", spec.api_surface.get("handler_name", CONFIGURE4_GENERIC_API_HANDLER_NAME)))
        if handler_name != CONFIGURE4_GENERIC_HANDLER_NAME and not hasattr(self, handler_name):
            return True
        routes = spec.api_surface.get("routes", [])
        if routes and api_handler_name != CONFIGURE4_GENERIC_API_HANDLER_NAME and not hasattr(self, api_handler_name):
            return True
        return False

    def _configure4_bind_runtime_commands(self, spec: Configure4Spec) -> None:
        service_id = str(spec.identity.get("service_id", ""))
        commands = self.configure4_state.setdefault("registered_runtime_commands", {})
        verbs = spec.command_surface.get("verbs", [])
        if not isinstance(verbs, list):
            return
        for verb_obj in verbs:
            commands[str(verb_obj).lower()] = {
                "service_id": service_id,
                "draft_id": spec.draft_id,
                "spec_hash": self._configure4_spec_hash(spec),
            }

    def _configure4_bind_runtime_routes(self, spec: Configure4Spec) -> None:
        service_id = str(spec.identity.get("service_id", ""))
        routes = spec.api_surface.get("routes", [])
        if not isinstance(routes, list):
            return
        for route_obj in routes:
            route = str(route_obj)
            self.api_routes[route] = {
                "service": service_id,
                "description": f"Generated route for {service_id}.",
                "handler": lambda payload, sid=service_id, rt=route: self.generic_configure4_api_handler(sid, rt, payload),
            }
            self.configure4_state.setdefault("registered_runtime_routes", {})[route] = {
                "service_id": service_id,
                "draft_id": spec.draft_id,
                "spec_hash": self._configure4_spec_hash(spec),
            }

    def _remove_configure4_runtime_registrations(self, *, draft_id: str = "") -> None:
        services = self.configure4_state.get("registered_runtime_services", {})
        commands = self.configure4_state.get("registered_runtime_commands", {})
        routes = self.configure4_state.get("registered_runtime_routes", {})
        service_ids: set[str] = set()
        if isinstance(services, dict):
            for service_id, record in list(services.items()):
                if not draft_id or (isinstance(record, dict) and record.get("draft_id") == draft_id):
                    service_ids.add(service_id)
                    services.pop(service_id, None)
        if isinstance(commands, dict):
            for command, record in list(commands.items()):
                if not draft_id or (isinstance(record, dict) and record.get("draft_id") == draft_id):
                    commands.pop(command, None)
        if isinstance(routes, dict):
            for route, record in list(routes.items()):
                if not draft_id or (isinstance(record, dict) and record.get("draft_id") == draft_id):
                    self.api_routes.pop(route, None)
                    routes.pop(route, None)
        for service_id in service_ids:
            self.services.pop(service_id, None)

    def _configure4_rebind_registered_services(self) -> None:
        services = self.configure4_state.get("registered_runtime_services", {})
        drafts = self.configure4_state.get("drafts", {})
        if not isinstance(services, dict) or not isinstance(drafts, dict):
            return
        for service_id, record in list(services.items()):
            if not isinstance(record, dict):
                continue
            draft_id = str(record.get("draft_id", ""))
            if draft_id not in drafts:
                continue
            spec = Configure4Spec.from_dict(drafts[draft_id])
            service_entry = self._configure4_service_entry_from_spec(spec)
            service_entry["state"] = "dormant"
            self.services[service_id] = service_entry
            self._configure4_bind_runtime_commands(spec)
            self._configure4_bind_runtime_routes(spec)

    def generic_configure4_service_handler(self, service_id: str, command: str, payload: object) -> dict[str, object]:
        svc = self.services.get(service_id)
        if svc:
            svc["calls"] = int(svc.get("calls", 0)) + 1
            svc["last_result"] = f"{command} handled by {CONFIGURE4_GENERIC_HANDLER_NAME}"
        result = {
            "service": service_id,
            "command": command,
            "payload": payload,
            "handler": CONFIGURE4_GENERIC_HANDLER_NAME,
            "note": "Runtime-safe generated service command handled without executing generated code.",
        }
        self._record_event("configure4.generated.command", f"{service_id}:{command}")
        return result

    def generic_configure4_api_handler(self, service_id: str, route: str, payload: object) -> dict[str, object]:
        return {
            "service": service_id,
            "route": route,
            "payload": payload,
            "handler": CONFIGURE4_GENERIC_API_HANDLER_NAME,
            "note": "Runtime-safe generated API route handled without executing generated code.",
        }

    def _configure4_generate_flow(self, spec: Configure4Spec, sink: Configure4Sink) -> bool:
        flow = spec.generated_code_plan.get("flow", {})
        if not isinstance(flow, dict):
            return False
        flow_type = str(flow.get("type", "service_scaffold"))
        input_value = str(flow.get("input_value", ""))
        separator = str(flow.get("separator", "\n"))
        prefix = str(flow.get("prefix", ""))
        suffix = str(flow.get("suffix", ""))
        if flow_type == "literal":
            return sink.write(f"{prefix}{input_value}{suffix}{separator}")
        if flow_type == "template":
            template = str(flow.get("template", input_value))
            values = flow.get("values", {})
            if isinstance(values, dict):
                rendered = template
                for key, value in values.items():
                    rendered = rendered.replace("{{" + str(key) + "}}", str(value))
            else:
                rendered = template
            return sink.write(f"{prefix}{rendered}{suffix}{separator}")
        if flow_type == "repeat":
            count = int(flow.get("input_width", 1))
            for _index in range(count):
                if not sink.write(f"{prefix}{input_value}{suffix}{separator}"):
                    return False
            return True
        if flow_type == "reverse":
            return sink.write(f"{prefix}{input_value[::-1]}{suffix}{separator}")
        if flow_type == "cartesian":
            width = int(flow.get("input_width", 1))
            count, ok = self._configure4_safe_power(len(input_value), width, int(self.configure4_state.get("settings", {}).get("max_variants", CONFIGURE4_MAX_VARIANTS)))
            if not ok:
                return False
            for combo in itertools.product(input_value, repeat=width):
                if not sink.write(f"{prefix}{''.join(combo)}{suffix}{separator}"):
                    return False
            return count >= 0
        if flow_type == "service_scaffold":
            return sink.write_json(
                {
                    "service_id": spec.identity.get("service_id", ""),
                    "commands": spec.command_surface.get("verbs", []),
                    "routes": spec.api_surface.get("routes", []),
                    "handler": spec.generated_code_plan.get("handler_name", CONFIGURE4_GENERIC_HANDLER_NAME),
                    "api_handler": spec.generated_code_plan.get("api_handler_name", CONFIGURE4_GENERIC_API_HANDLER_NAME),
                    "persistence": spec.persistence_behavior,
                }
            )
        return False

    def _configure4_spec_hash(self, spec: Configure4Spec) -> str:
        payload = spec.to_dict()
        payload.pop("diagnostics", None)
        payload.pop("inferred_fields", None)
        metadata = payload.get("metadata", {})
        if isinstance(metadata, dict):
            metadata.pop("created_at", None)
            metadata.pop("updated_at", None)
        payload.pop("draft_id", None)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

    def _configure4_append_diagnostic(self, severity: str, target: str, message: str, recommendation: str = "", code: str = "") -> dict[str, object]:
        entry = {
            "severity": severity,
            "target": target,
            "message": message,
            "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
            "recommendation": recommendation,
        }
        if code:
            entry["code"] = code
        self.configure4_state.setdefault("diagnostics", []).append(entry)
        self._configure4_trim_history()
        return entry

    def _configure4_trim_history(self) -> None:
        for key in ("diagnostics", "registration_history"):
            items = self.configure4_state.get(key, [])
            if isinstance(items, list) and len(items) > CONFIGURE4_MAX_HISTORY:
                self.configure4_state[key] = items[-CONFIGURE4_MAX_HISTORY:]

    def _configure4_status_payload(self) -> dict[str, object]:
        drafts = self.configure4_state.get("drafts", {})
        registered = self.configure4_state.get("registered_runtime_services", {})
        diagnostics = self.configure4_state.get("diagnostics", [])
        return {
            "service_id": CONFIGURE4_SERVICE_ID,
            "label": CONFIGURE4_LABEL,
            "mode": self.configure4_state.get("mode", "manual"),
            "allowed_modes": list(CONFIGURE4_ALLOWED_MODES),
            "flow_types": list(CONFIGURE4_ALLOWED_FLOW_TYPES),
            "draft_count": len(drafts) if isinstance(drafts, dict) else 0,
            "current_draft_id": self.configure4_state.get("current_draft_id", ""),
            "registered_runtime_services": list(registered) if isinstance(registered, dict) else [],
            "settings": copy.deepcopy(self.configure4_state.get("settings", {})),
            "latest_diagnostics": copy.deepcopy(diagnostics[-10:]) if isinstance(diagnostics, list) else [],
        }

    def _configure4_sample_payload(self) -> dict[str, object]:
        manual = {
            "mode": "manual",
            "draft_id": "manual_diagnostics_echo",
            "identity": {
                "service_id": "codex.diagnostics.echo",
                "label": "CodexDiagnosticsEcho",
                "aliases": ["diagnostics.echo"],
                "layer": "codex-authoring",
                "state": "dormant",
                "description": "Echoes diagnostic payloads through a runtime-safe generated service.",
                "version": "1.0.0",
            },
            "command_surface": {
                "verbs": ["diagnostics.echo.status", "diagnostics.echo.run"],
                "handler_name": CONFIGURE4_GENERIC_HANDLER_NAME,
                "help_text": "Runtime-safe diagnostics echo service.",
                "default_payload": {"message": "hello"},
            },
            "api_surface": {
                "routes": ["/configure4/generated/codex-diagnostics-echo"],
                "handler_name": CONFIGURE4_GENERIC_API_HANDLER_NAME,
                "payload_schema": {"type": "object", "additionalProperties": True},
                "output_schema": {"type": "object", "required": ["service", "payload"]},
            },
            "execution_behavior": {
                "activation_requirements": ["blue.cli.engine"],
                "dependency_requirements": [],
                "allowed_modes": ["manual", "semi_auto", "auto"],
                "timeout_policy": {"seconds": 30},
                "file_access_policy": "none",
                "side_effect_policy": "memory_only",
                "can_register_immediately": True,
            },
            "validation_rules": {
                "gates": ["service_id", "command_surface", "api_surface", "activation_dependencies", "filesystem_policy", "flow_bounds", "handler_presence"],
                "allow_command_collisions": False,
            },
            "persistence_behavior": {
                "policy": "manifest",
                "import_path": "",
                "export_path": "",
                "versioning_policy": "snapshot_in_manifest",
            },
            "examples": ["service.activate codex.diagnostics.echo", "diagnostics.echo.run {\"message\":\"hello\"}"],
            "generated_code_plan": {
                "handler_name": CONFIGURE4_GENERIC_HANDLER_NAME,
                "api_handler_name": CONFIGURE4_GENERIC_API_HANDLER_NAME,
                "runtime_strategy": "generic_service_record",
                "flow": {
                    "type": "service_scaffold",
                    "input_value": "codex.diagnostics.echo",
                    "input_width": 1,
                    "output_target": "memory",
                    "prefix": "",
                    "suffix": "",
                    "separator": "\n",
                },
            },
            "metadata": {"owner": "developer", "review_required": False},
            "object_graph": self._configure4_default_object_graph("codex.diagnostics.echo", {"type": "service_scaffold"}),
            "custom_fields": {"domain": "diagnostics"},
        }
        semi = {
            "mode": "semi_auto",
            "service_id": "codex.summary.quick",
            "label": "CodexSummaryQuick",
            "description": "Summarizes short text payloads.",
            "verbs": ["summary.quick.run"],
            "flow_type": "literal",
            "input_value": "summary-ready",
            "can_register_immediately": False,
        }
        auto = {"mode": "auto", "intent": "create a diagnostics summarizer service"}
        text_generation = {
            "mode": "semi_auto",
            "service_id": "codex.text.banner",
            "label": "CodexTextBanner",
            "description": "Generates reusable release banner text from a template.",
            "verbs": ["text.banner.run"],
            "generated_code_plan": {
                "flow": {
                    "type": "template",
                    "template": "Project {{name}} targets {{language}}.",
                    "values": {"name": "demo", "language": "Python"},
                    "output_target": "memory",
                    "separator": "\n",
                }
            },
            "custom_fields": {
                "use_case": "text_generation",
                "notes": "Preview returns generated text without filesystem writes.",
            },
        }
        pointer_generation = {
            "mode": "semi_auto",
            "service_id": "codex.pointer.index",
            "label": "CodexPointerIndex",
            "description": "Generates stable textual pointers for files, symbols, routes, and object ids.",
            "verbs": ["pointer.index.run"],
            "generated_code_plan": {
                "flow": {
                    "type": "template",
                    "template": "{{root}}/{{module}}.py::{{symbol}}",
                    "values": {"root": "src", "module": "diagnostics", "symbol": "summarize"},
                    "output_target": "memory",
                    "separator": "\n",
                }
            },
            "custom_fields": {
                "use_case": "pointer_generation",
                "pointer_kind": "source_location_string",
                "memory_pointer": False,
            },
        }
        codebase_creation = {
            "mode": "auto",
            "intent": "create a Rust command line codebase that validates JSON manifests",
            "custom_fields": {
                "use_case": "codebase_creation",
                "codebase": {
                    "language": "Rust",
                    "project_type": "cli",
                    "package_manager": "cargo",
                    "files": [
                        {"path": "Cargo.toml", "role": "package manifest"},
                        {"path": "src/main.rs", "role": "entrypoint"},
                        {"path": "tests/manifest_validation.rs", "role": "integration tests"},
                    ],
                    "entrypoints": ["src/main.rs"],
                    "build_commands": ["cargo build"],
                    "test_commands": ["cargo test"],
                    "quality_gates": ["format", "lint", "tests"],
                    "output_policy": "preview first; write files only after explicit filesystem command",
                }
            },
        }
        return {
            "manual": manual,
            "semi_auto": semi,
            "auto": auto,
            "text_generation": text_generation,
            "pointer_generation": pointer_generation,
            "codebase_creation": codebase_creation,
            "safe_service_scaffold_flow": manual["generated_code_plan"]["flow"],
        }

    def _configure4_parse_key_value_config(self, text: str) -> dict[str, object]:
        payload: dict[str, object] = {}
        objects: list[dict[str, object]] = []
        current: dict[str, object] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower() == "end":
                if current:
                    objects.append(current)
                    current = {}
                continue
            if "=" in line:
                key, value = line.split("=", 1)
            else:
                parts = line.split(None, 1)
                key, value = parts[0], parts[1] if len(parts) > 1 else ""
            key = key.strip()
            value = value.strip().encode("utf-8").decode("unicode_escape")
            current[key] = value
        if current:
            objects.append(current)
        if objects:
            first = objects[0]
            payload.update(first)
            payload["object_graph"] = [
                Configure4FabricRecord(kind="object", name=str(item.get("object_name", item.get("name", f"object_{index}"))), value=copy.deepcopy(item)).to_dict()
                for index, item in enumerate(objects, start=1)
            ]
            payload["custom_fields"] = {"kv_objects": objects}
        return self._configure4_expand_aliases(payload)

    def _restore_configure4_state(self, payload: object) -> None:
        self._remove_configure4_runtime_registrations()
        fresh = self._create_configure4_state()
        if not isinstance(payload, dict):
            self.configure4_state = fresh
            self._configure4_append_diagnostic("error", "manifest.load", "configure4_state was malformed and has been reset.")
            return
        if isinstance(payload.get("settings", {}), dict):
            fresh["settings"].update(copy.deepcopy(payload["settings"]))
        mode = configure4_normalize_mode(payload.get("mode", fresh["mode"]))
        fresh["mode"] = mode if mode in CONFIGURE4_ALLOWED_MODES else "manual"
        for key in ("validation_reports", "registered_runtime_commands", "registered_runtime_routes"):
            if isinstance(payload.get(key), dict):
                fresh[key] = copy.deepcopy(payload[key])
        for key in ("registration_history", "diagnostics"):
            if isinstance(payload.get(key), list):
                fresh[key] = copy.deepcopy(payload[key])[-CONFIGURE4_MAX_HISTORY:]
        drafts = payload.get("drafts", {})
        if isinstance(drafts, dict):
            fresh["drafts"] = {str(draft_id): Configure4Spec.from_dict(draft).to_dict() for draft_id, draft in drafts.items()}
        generated = payload.get("generated_service_drafts", {})
        if isinstance(generated, dict):
            fresh["generated_service_drafts"] = {str(draft_id): Configure4Spec.from_dict(draft).to_dict() for draft_id, draft in generated.items()}
        registered_services = payload.get("registered_runtime_services", {})
        if isinstance(registered_services, dict):
            fresh["registered_runtime_services"] = copy.deepcopy(registered_services)
        current = str(payload.get("current_draft_id", ""))
        fresh["current_draft_id"] = current if current in fresh["drafts"] else next(iter(fresh["drafts"]), "")
        try:
            fresh["next_draft_index"] = max(int(payload.get("next_draft_index", 1)), 1)
        except (TypeError, ValueError):
            fresh["next_draft_index"] = 1
        self.configure4_state = fresh
        self._configure4_rebind_registered_services()

    def command_set(self, key: str, value: str) -> str:
        if not self.require_service("kernel.memory"):
            return "kernel.memory is dormant. Activate it first: service.activate kernel.memory"
        self.vars[key] = value
        self._record_event("set", key)
        return f"{key} = {value}"

    def command_terminal_timeout(self, seconds_text: str) -> tuple[str, str]:
        if not self.require_any_terminal_service():
            return "Activate a terminal service first: service.activate kernel.terminal.linux or service.activate kernel.terminal.powershell7", "err"
        try:
            seconds = int(seconds_text)
        except ValueError:
            return "Usage: terminal.timeout <seconds>", "err"
        if seconds < 1 or seconds > 600:
            return "Terminal timeout must be between 1 and 600 seconds.", "err"
        self.terminal_timeout_seconds = seconds
        self._record_event("terminal.timeout", str(seconds))
        return f"terminal timeout = {seconds}s", "ok"

    def command_terminal_cd(self, target: str) -> tuple[str, str]:
        if not self.require_any_terminal_service():
            return "Activate a terminal service first: service.activate kernel.terminal.linux or service.activate kernel.terminal.powershell7", "err"
        raw = target.strip() or "~"
        try:
            parts = shlex.split(raw)
        except ValueError:
            parts = [raw]
        path_text = parts[0] if parts else "~"
        new_path = Path(os.path.expanduser(os.path.expandvars(path_text)))
        if not new_path.is_absolute():
            new_path = self.terminal_cwd / new_path
        try:
            new_path = new_path.resolve()
        except OSError as exc:
            return f"Could not resolve path: {exc}", "err"
        if not new_path.exists():
            return f"Path does not exist: {new_path}", "err"
        if not new_path.is_dir():
            return f"Path is not a directory: {new_path}", "err"
        self.terminal_cwd = new_path
        self._record_event("terminal.cd", str(new_path))
        return f"terminal cwd = {new_path}", "ok"

    def require_any_terminal_service(self) -> bool:
        return self.require_service("kernel.terminal.linux") or self.require_service("kernel.terminal.powershell7")

    def execute_linux_terminal(self, command: str) -> tuple[str, str]:
        service_id = "kernel.terminal.linux"
        if not self.require_service(service_id):
            return f"Service {service_id} is dormant. Activate it first: service.activate {service_id}", "err"
        if not self.linux_shell:
            return "Linux terminal service is active, but no bash/sh executable was found on this host.", "err"
        command = command.strip()
        if not command:
            return self.format_json({
                "service": service_id,
                "available": True,
                "executable": self.linux_shell,
                "cwd": str(self.terminal_cwd),
                "usage": "linux <command> or service.exec kernel.terminal.linux <command>",
            }), "json"
        cd_result = self._maybe_handle_terminal_cd(command)
        if cd_result is not None:
            return cd_result
        return self._run_external_terminal(
            service_id=service_id,
            display_name="Linux terminal",
            executable=[self.linux_shell, "-lc", command],
            command=command,
        )

    def execute_powershell7_terminal(self, command: str) -> tuple[str, str]:
        service_id = "kernel.terminal.powershell7"
        if not self.require_service(service_id):
            return f"Service {service_id} is dormant. Activate it first: service.activate {service_id}", "err"
        if not self.pwsh_executable:
            return "PowerShell 7 service is active, but no pwsh executable was found on this host.", "err"
        command = command.strip()
        if not command:
            return self.format_json({
                "service": service_id,
                "available": True,
                "executable": self.pwsh_executable,
                "cwd": str(self.terminal_cwd),
                "usage": "pwsh <command> or service.exec kernel.terminal.powershell7 <command>",
            }), "json"
        cd_result = self._maybe_handle_terminal_cd(command)
        if cd_result is not None:
            return cd_result
        return self._run_external_terminal(
            service_id=service_id,
            display_name="PowerShell 7",
            executable=[self.pwsh_executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
            command=command,
        )

    def _maybe_handle_terminal_cd(self, command: str) -> tuple[str, str] | None:
        stripped = command.strip()
        lowered = stripped.lower()
        cd_prefixes = ("cd", "chdir", "set-location")
        for prefix in cd_prefixes:
            if lowered == prefix:
                return self.command_terminal_cd("~")
            if lowered.startswith(prefix + " "):
                return self.command_terminal_cd(stripped[len(prefix):].strip())
        return None

    def _run_external_terminal(self, *, service_id: str, display_name: str, executable: list[str], command: str) -> tuple[str, str]:
        svc = self.services[service_id]
        try:
            completed = subprocess.run(
                executable,
                cwd=str(self.terminal_cwd),
                env=os.environ.copy(),
                text=True,
                capture_output=True,
                timeout=self.terminal_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            self._record_event("terminal.timeout", f"{service_id}: {command}")
            partial_stdout = exc.stdout or ""
            partial_stderr = exc.stderr or ""
            output = [
                f"{display_name} timed out after {self.terminal_timeout_seconds}s",
                f"cwd: {self.terminal_cwd}",
                f"command: {command}",
            ]
            if partial_stdout:
                output.extend(["", "stdout:", partial_stdout.rstrip()])
            if partial_stderr:
                output.extend(["", "stderr:", partial_stderr.rstrip()])
            return "\n".join(output), "err"
        except OSError as exc:
            return f"{display_name} failed to start: {exc}", "err"

        svc["calls"] = int(svc["calls"]) + 1
        self._record_event("terminal.exec", f"{service_id}: {command}")
        stdout = completed.stdout.rstrip()
        stderr = completed.stderr.rstrip()
        lines = [
            f"{display_name} returncode={completed.returncode}",
            f"cwd: {self.terminal_cwd}",
            f"command: {command}",
        ]
        if stdout:
            lines.extend(["", "stdout:", stdout])
        if stderr:
            lines.extend(["", "stderr:", stderr])
        if not stdout and not stderr:
            lines.extend(["", "<no output>"])
        result = "\n".join(lines)
        svc["last_result"] = result[:260]
        return result, "ok" if completed.returncode == 0 else "err"

    def command_manifest_show(self) -> str:
        if not self.require_service("codex.manifest"):
            return "codex.manifest is dormant. Activate it first: service.activate codex.manifest"
        return self.format_json(self.current_project_payload())

    def command_manifest_save(self, path: str) -> str:
        if not self.require_service("kernel.fs"):
            return "kernel.fs is dormant. Activate it first: service.activate kernel.fs"
        if not self.require_service("codex.manifest"):
            return "codex.manifest is dormant. Activate it first: service.activate codex.manifest"
        if not path:
            return "Usage: manifest.save <path>. Console-only mode does not open file dialogs."
        output_path = Path(path).expanduser()
        if output_path.parent and str(output_path.parent) not in {"", "."}:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(self.current_project_payload(), handle, indent=2)
        self._record_event("manifest.save", str(output_path))
        return f"Saved manifest to {output_path}"

    def command_manifest_load(self, path: str) -> tuple[str, str]:
        if not self.require_service("kernel.fs"):
            return "kernel.fs is dormant. Activate it first: service.activate kernel.fs", "err"
        if not self.require_service("codex.manifest"):
            return "codex.manifest is dormant. Activate it first: service.activate codex.manifest", "err"
        if not path:
            return "Usage: manifest.load <path>. Console-only mode does not open file dialogs.", "err"
        input_path = Path(path).expanduser()
        with open(input_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.nodes = payload.get("nodes", self.nodes)
        self.files = payload.get("files", self.files)
        self.diagnostics = payload.get("diagnostics", self.diagnostics)
        self.versions = payload.get("version_ledger", self.versions)
        if "manifest" in payload:
            self.manifest = payload["manifest"]
        if "configure4_state" in payload:
            self._restore_configure4_state(payload["configure4_state"])
        elif "configure_4_state" in payload:
            self._restore_configure4_state(payload["configure_4_state"])
        if "quadtreeDesktop_state" in payload:
            self._restore_quadtree_desktop_state(payload["quadtreeDesktop_state"])
        elif "quadtree_desktop_state" in payload:
            self._restore_quadtree_desktop_state(payload["quadtree_desktop_state"])
        self._record_event("manifest.load", str(input_path))
        return f"Loaded manifest from {input_path}", "ok"

    def command_node_list(self) -> str:
        if not self.require_service("codex.graph"):
            return "codex.graph is dormant. Activate it first: service.activate codex.graph"
        return self.format_json(self.nodes)

    def command_node_select(self, node_id: str) -> tuple[str, str]:
        if not self.require_service("codex.graph"):
            return "codex.graph is dormant. Activate it first: service.activate codex.graph", "err"
        if not any(node["id"] == node_id for node in self.nodes):
            return f"Unknown node: {node_id}", "err"
        self.selected_node_id = node_id
        self._record_event("node.select", node_id)
        return f"Selected node {node_id}", "ok"

    def command_node_add(self, payload_raw: str) -> tuple[str, str]:
        if not self.require_service("codex.graph"):
            return "codex.graph is dormant. Activate it first: service.activate codex.graph", "err"
        payload = self.parse_payload(payload_raw)
        if not isinstance(payload, dict) or "id" not in payload:
            return "Usage: node.add {\"id\":\"custom.object\",\"label\":\"Custom Object\",\"type\":\"module\",\"description\":\"...\"}", "err"
        node_id = str(payload["id"])
        if any(node["id"] == node_id for node in self.nodes):
            return f"Node already exists: {node_id}", "err"
        node = {
            "id": node_id,
            "label": str(payload.get("label", node_id)),
            "type": str(payload.get("type", "module")),
            "status": str(payload.get("status", "editable")),
            "description": str(payload.get("description", "Created by blue CLI REPL command.")),
        }
        self.nodes.append(node)
        self.selected_node_id = node_id
        self.diagnostics.append({"severity": "accepted", "target": node_id, "message": "Created through blue CLI node.add command."})
        self._record_event("node.add", node_id)
        return self.format_json(node), "json"

    def command_node_patch(self, target: str) -> tuple[str, str]:
        if not self.require_service("diagnostics.runtime"):
            return "diagnostics.runtime is dormant. Activate it first: service.activate diagnostics.runtime", "err"
        if not self.require_service("codex.graph"):
            return "codex.graph is dormant. Activate it first: service.activate codex.graph", "err"
        patched_any = False
        for node in self.nodes:
            if node["id"] == target or target in {"all", "*"}:
                if node["status"] == "error":
                    node["status"] = "accepted"
                    patched_any = True
        for diag in self.diagnostics:
            if diag["severity"] == "error" and (target in {"all", "*", self.selected_node_id} or target in diag["target"]):
                diag["severity"] = "accepted"
                diag["message"] = "Patched by blue CLI diagnostics runtime. Missing dependency placeholder resolved."
                patched_any = True
        if not patched_any:
            self.diagnostics.append({"severity": "accepted", "target": target, "message": "Patch command ran; no repair item matched."})
        self._record_event("node.patch", target)
        return f"Patch flow completed for {target}.", "ok"

    def command_node_validate(self, target: str) -> tuple[str, str]:
        if not self.require_service("codex.validator"):
            return "codex.validator is dormant. Activate it first: service.activate codex.validator", "err"
        errors = [diag for diag in self.diagnostics if diag["severity"] == "error"]
        warnings = [diag for diag in self.diagnostics if diag["severity"] == "warning"]
        report = {
            "target": target,
            "errors": len(errors),
            "warnings": len(warnings),
            "accepted": len(errors) == 0,
            "gates": self.manifest.get("validation_gates", []),
        }
        if len(errors) == 0:
            for node in self.nodes:
                if target in {"all", "*"} or node["id"] == target:
                    if node["status"] not in {"locked", "accepted"}:
                        node["status"] = "accepted"
            self.diagnostics.append({"severity": "accepted", "target": target, "message": "Validation gates accepted through blue CLI command."})
        self._record_event("node.validate", target)
        return self.format_json(report), "json" if len(errors) == 0 else "warn"

    def command_file_search(self, query: str) -> str:
        if not self.require_service("codex.graph"):
            return "codex.graph is dormant. Activate it first: service.activate codex.graph"
        q = query.strip().lower()
        results = [item for item in self.files if not q or q in f"{item['path']} {item['kind']} {item['state']}".lower()]
        self._record_event("file.search", query)
        return self.format_json(results)

    def command_diagnostics_list(self) -> str:
        if not self.require_service("diagnostics.runtime"):
            return "diagnostics.runtime is dormant. Activate it first: service.activate diagnostics.runtime"
        return self.format_json(self.diagnostics)

    def command_diagnostics_patch(self) -> tuple[str, str]:
        return self.command_node_patch("all")

    def command_emit_preview(self) -> str:
        if not self.require_service("codex.emitter"):
            return "codex.emitter is dormant. Activate it first: service.activate codex.emitter"
        source = self.generate_emitted_source()
        self._record_event("emit.preview", "generated")
        return source

    def command_build_run(self) -> tuple[str, str]:
        if not self.require_service("codex.builder"):
            return "codex.builder is dormant. Activate it first: service.activate codex.builder", "err"
        errors = [diag for diag in self.diagnostics if diag["severity"] == "error"]
        warnings = [diag for diag in self.diagnostics if diag["severity"] == "warning"]
        accepted = len(errors) == 0
        report_lines = [
            "BUILD PASSED" if accepted else "BUILD FAILED",
            "",
            f"objects: {len(self.nodes)}",
            f"warnings: {len(warnings)}",
            f"errors: {len(errors)}",
            f"accepted: {accepted}",
            "",
            "diagnostics:",
        ]
        for diag in self.diagnostics:
            report_lines.append(f"- [{diag['severity'].upper()}] {diag['target']}: {diag['message']}")
        report = "\n".join(report_lines)
        self._record_event("build.run", "passed" if accepted else "failed")
        return report, "ok" if accepted else "warn"

    def command_version_snapshot(self) -> str:
        if not self.require_service("version.ledger"):
            return "version.ledger is dormant. Activate it first: service.activate version.ledger"
        entry = self.create_version_entry()
        return self.format_json(entry)

    def command_reboot(self) -> str:
        self.nodes = copy.deepcopy(INITIAL_CODEX_NODES)
        self.files = copy.deepcopy(INITIAL_FILE_TREE)
        self.diagnostics = copy.deepcopy(INITIAL_DIAGNOSTICS)
        self.manifest = copy.deepcopy(MANIFEST_PREVIEW)
        self.versions = []
        self.vars = {}
        self.event_log = []
        self.configure4_state = self._create_configure4_state()
        self.quadtreeDesktop_state = self._create_quadtree_desktop_state()
        self._hide_quadtree_desktop()
        self.services = self._create_services()
        self.api_routes = self._create_api_routes()
        self._record_event("reboot", "soft reset")
        return "Soft reboot complete. Blue CLI engine remains active; all other services are dormant."

    def api_kernel_status(self, _payload: object) -> dict[str, object]:
        return {
            "os": "Graphical Codex CLI-REPL OS",
            "rule": "services_activate_only_by_blue_cli_repl_command",
            "time": _dt.datetime.now().isoformat(timespec="seconds"),
            "active_services": [sid for sid, svc in self.services.items() if svc["state"] == "active"],
            "selected_service": self.selected_service_id,
            "selected_node": self.selected_node_id,
        }

    def api_kernel_services(self, _payload: object) -> list[dict[str, object]]:
        return [
            {
                "id": sid,
                "layer": svc["layer"],
                "state": svc["state"],
                "description": svc["description"],
                "calls": svc["calls"],
            }
            for sid, svc in self.services.items()
        ]

    def api_kernel_events(self, _payload: object) -> list[dict[str, str]]:
        return self.event_log[-50:]

    def api_terminal_linux(self, payload: object) -> dict[str, object]:
        command = ""
        if isinstance(payload, dict):
            command = str(payload.get("command", payload.get("raw", "")))
        result, tag = self.execute_linux_terminal(command)
        return {
            "ok": tag != "err",
            "service": "kernel.terminal.linux",
            "cwd": str(self.terminal_cwd),
            "result": result,
        }

    def api_terminal_powershell7(self, payload: object) -> dict[str, object]:
        command = ""
        if isinstance(payload, dict):
            command = str(payload.get("command", payload.get("raw", "")))
        result, tag = self.execute_powershell7_terminal(command)
        return {
            "ok": tag != "err",
            "service": "kernel.terminal.powershell7",
            "cwd": str(self.terminal_cwd),
            "result": result,
        }

    def api_codex_manifest(self, _payload: object) -> dict[str, object]:
        return self.current_project_payload()

    def api_codex_nodes(self, _payload: object) -> list[dict[str, str]]:
        return copy.deepcopy(self.nodes)

    def api_codex_files(self, _payload: object) -> list[dict[str, str]]:
        return copy.deepcopy(self.files)

    def api_diagnostics(self, _payload: object) -> list[dict[str, str]]:
        return copy.deepcopy(self.diagnostics)

    def api_validate(self, payload: object) -> dict[str, object]:
        target = "all"
        if isinstance(payload, dict):
            target = str(payload.get("target", "all"))
        result, _tag = self.command_node_validate(target)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"message": result}

    def api_emit(self, _payload: object) -> dict[str, object]:
        return {"language": "cpp", "source": self.generate_emitted_source()}

    def api_build(self, _payload: object) -> dict[str, object]:
        errors = [diag for diag in self.diagnostics if diag["severity"] == "error"]
        warnings = [diag for diag in self.diagnostics if diag["severity"] == "warning"]
        return {
            "accepted": len(errors) == 0,
            "objects": len(self.nodes),
            "warnings": len(warnings),
            "errors": len(errors),
            "diagnostics": copy.deepcopy(self.diagnostics),
        }

    def api_version_snapshot(self, _payload: object) -> dict[str, str]:
        return self.create_version_entry()

    def api_configure4_status(self, _payload: object) -> dict[str, object]:
        return self._configure4_status_payload()

    def api_configure4_specs(self, payload: object) -> dict[str, object]:
        draft_id = ""
        if isinstance(payload, dict):
            draft_id = str(payload.get("draft_id", payload.get("id", "")))
        if draft_id:
            spec = self._configure4_get_spec(draft_id)
            return {"accepted": spec is not None, "draft": spec.to_dict() if spec else None}
        return {"accepted": True, "drafts": copy.deepcopy(self.configure4_state.get("drafts", {}))}

    def api_configure4_validate(self, payload: object) -> dict[str, object]:
        target = "all"
        if isinstance(payload, dict):
            target = str(payload.get("draft_id", payload.get("target", "all")))
        return self._configure4_validate_target(target, append=True)

    def api_configure4_preview(self, payload: object) -> dict[str, object]:
        target = ""
        if isinstance(payload, dict):
            target = str(payload.get("draft_id", payload.get("target", "")))
        draft_id = self._configure4_default_draft_id(target)
        spec = self._configure4_get_spec(draft_id)
        if spec is None:
            return {"accepted": False, "error": f"Unknown draft: {draft_id or '<none>'}"}
        return self._configure4_build_preview(spec, append_validation=True)

    def api_configure4_register(self, payload: object) -> dict[str, object]:
        target = ""
        if isinstance(payload, dict):
            target = str(payload.get("draft_id", payload.get("target", "")))
        return self._configure4_register_draft(self._configure4_default_draft_id(target))

    def api_quadtree_desktop_status(self, _payload: object) -> dict[str, object]:
        return self._qdt_status_payload()

    def api_quadtree_desktop_modules(self, _payload: object) -> dict[str, object]:
        return {"accepted": True, "modules": copy.deepcopy(self.quadtreeDesktop_state.get("module_registry", {}))}

    def api_quadtree_desktop_module(self, payload: object) -> dict[str, object]:
        module_id = ""
        if isinstance(payload, dict):
            module_id = str(payload.get("module_id", ""))
            route = str(payload.get("_route", ""))
            if not module_id and route.startswith("/quadtreeDesktop/modules/"):
                module_id = route.removeprefix("/quadtreeDesktop/modules/")
        module = self._qdt_get_module(module_id)
        return {"accepted": module is not None, "module": copy.deepcopy(module) if module else None, "module_id": module_id}

    def api_quadtree_desktop_layer(self, payload: object) -> dict[str, object]:
        module_id = ""
        layer_type = ""
        if isinstance(payload, dict):
            module_id = str(payload.get("module_id", ""))
            layer_type = str(payload.get("layer_type", payload.get("layer", "")))
            route = str(payload.get("_route", ""))
            if route.startswith("/quadtreeDesktop/layers/"):
                parts = route.removeprefix("/quadtreeDesktop/layers/").split("/", 1)
                if len(parts) == 2:
                    module_id = module_id or parts[0]
                    layer_type = layer_type or parts[1]
        layer = self._qdt_get_layer(module_id, layer_type)
        return {"accepted": layer is not None, "layer": copy.deepcopy(layer) if layer else None, "module_id": module_id, "layer_type": layer_type}

    def api_quadtree_desktop_cell(self, payload: object) -> dict[str, object]:
        address = ""
        if isinstance(payload, dict):
            address = str(payload.get("address", payload.get("target", "")))
            route = str(payload.get("_route", ""))
            if not address and route.startswith("/quadtreeDesktop/cells/"):
                address = route.removeprefix("/quadtreeDesktop/cells/")
        cell = self._qdt_get_cell_by_ref(address)
        return {"accepted": cell is not None, "cell": copy.deepcopy(cell) if cell else None, "address": address}

    def api_quadtree_desktop_selection(self, payload: object) -> dict[str, object]:
        if isinstance(payload, dict) and any(key in payload for key in ("address", "addresses", "target", "selection")):
            result, _tag = self.command_quadtree_desktop_selection_set(payload)
            return result
        return {"accepted": True, "selected_cell_paths": copy.deepcopy(self.quadtreeDesktop_state.get("selected_cell_paths", []))}

    def api_quadtree_desktop_batches(self, _payload: object) -> dict[str, object]:
        return {"accepted": True, "batches": copy.deepcopy(self.quadtreeDesktop_state.get("batch_registry", {}))}

    def api_quadtree_desktop_validate(self, payload: object) -> dict[str, object]:
        if isinstance(payload, dict) and payload.get("batch_id"):
            result, _tag = self.command_quadtree_desktop_batch_validate(payload)
            return result
        result, _tag = self.command_quadtree_desktop_validate(payload)
        return result

    def api_quadtree_desktop_preview(self, payload: object) -> dict[str, object]:
        result, _tag = self.command_quadtree_desktop_preview(payload)
        return result

    def api_quadtree_desktop_apply(self, payload: object) -> dict[str, object]:
        result, _tag = self.command_quadtree_desktop_apply(payload)
        return result

    def api_quadtree_desktop_export(self, payload: object) -> dict[str, object]:
        result, _tag = self.command_quadtree_desktop_export_manifest(payload)
        return result if isinstance(result, dict) else {"accepted": True, "result": result}

    def api_quadtree_desktop_import(self, payload: object) -> dict[str, object]:
        result, _tag = self.command_quadtree_desktop_import_manifest(payload)
        return result

    def require_service(self, service_id: str) -> bool:
        service_id = self.resolve_service_id(service_id)
        svc = self.services.get(service_id)
        return bool(svc and svc["state"] == "active")

    def parse_payload(self, payload_raw: str) -> object:
        raw = payload_raw.strip()
        if not raw:
            return {}
        if raw.startswith("{") or raw.startswith("["):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw, "parse_error": "invalid json"}
        return {"raw": raw, "args": shlex.split(raw) if raw else []}

    def current_project_payload(self) -> dict[str, object]:
        return {
            "manifest": copy.deepcopy(self.manifest),
            "nodes": copy.deepcopy(self.nodes),
            "files": copy.deepcopy(self.files),
            "diagnostics": copy.deepcopy(self.diagnostics),
            "version_ledger": copy.deepcopy(self.versions),
            "services": {sid: {key: value for key, value in svc.items() if key != "examples"} for sid, svc in self.services.items()},
            "api_routes": {route: {"service": spec["service"], "description": spec["description"]} for route, spec in self.api_routes.items()},
            "vars": copy.deepcopy(self.vars),
            "configure4_state": copy.deepcopy(self.configure4_state),
            "quadtreeDesktop_state": copy.deepcopy(self.quadtreeDesktop_state),
        }

    def create_version_entry(self) -> dict[str, str]:
        now = _dt.datetime.now()
        accepted = sum(1 for node in self.nodes if node["status"] in {"accepted", "locked"})
        errors = sum(1 for diag in self.diagnostics if diag["severity"] == "error")
        active = sum(1 for svc in self.services.values() if svc["state"] == "active")
        configure4_drafts = len(self.configure4_state.get("drafts", {})) if isinstance(self.configure4_state.get("drafts", {}), dict) else 0
        configure4_registered = len(self.configure4_state.get("registered_runtime_services", {})) if isinstance(self.configure4_state.get("registered_runtime_services", {}), dict) else 0
        qdt_modules = len(self.quadtreeDesktop_state.get("module_registry", {})) if isinstance(self.quadtreeDesktop_state.get("module_registry", {}), dict) else 0
        qdt_batches = len(self.quadtreeDesktop_state.get("batch_registry", {})) if isinstance(self.quadtreeDesktop_state.get("batch_registry", {}), dict) else 0
        entry = {
            "id": f"v{len(self.versions) + 1}.{now.strftime('%Y%m%d.%H%M%S')}",
            "created_at": now.isoformat(timespec="seconds"),
            "summary": f"{accepted}/{len(self.nodes)} codex nodes accepted, {errors} repair item(s), {active}/{len(self.services)} services active, configure4 drafts={configure4_drafts}, registered={configure4_registered}, quadtree modules={qdt_modules}, batches={qdt_batches}",
            "configure4_drafts": str(configure4_drafts),
            "configure4_registered": str(configure4_registered),
            "quadtree_modules": str(qdt_modules),
            "quadtree_batches": str(qdt_batches),
        }
        self.versions.append(entry)
        self._record_event("version.snapshot", entry["id"])
        return entry

    def generate_emitted_source(self) -> str:
        accepted_count = sum(1 for node in self.nodes if node["status"] in {"accepted", "locked"})
        error_count = sum(1 for diag in self.diagnostics if diag["severity"] == "error")
        active_count = sum(1 for svc in self.services.values() if svc["state"] == "active")
        return "\n".join(
            [
                "// Emitted by Graphical Codex CLI-REPL OS",
                "// Kernel services were activated only through the blue CLI engine.",
                "",
                "#include <iostream>",
                "#include <string>",
                "",
                "struct KernelReport {",
                "    int activeServices;",
                "    int acceptedObjects;",
                "    int repairItems;",
                "};",
                "",
                "int main() {",
                f"    KernelReport report{{{active_count}, {accepted_count}, {error_count}}};",
                "    std::cout << \"Graphical Codex CLI-REPL OS emission complete\\n\";",
                "    std::cout << \"Active services: \" << report.activeServices << \"\\n\";",
                "    std::cout << \"Accepted objects: \" << report.acceptedObjects << \"\\n\";",
                "    std::cout << \"Repair items: \" << report.repairItems << \"\\n\";",
                "    return report.repairItems == 0 ? 0 : 1;",
                "}",
            ]
        )

    def _diagnostic_counts(self) -> dict[str, int]:
        counts = {"accepted": 0, "warning": 0, "error": 0}
        for diag in self.diagnostics:
            counts[diag["severity"]] = counts.get(diag["severity"], 0) + 1
        return counts

    def _record_event(self, kind: str, detail: str) -> None:
        self.event_log.append(
            {
                "time": _dt.datetime.now().isoformat(timespec="seconds"),
                "kind": kind,
                "detail": detail,
            }
        )
        if len(self.event_log) > 500:
            self.event_log = self.event_log[-500:]

    def write_console(self, prefix: str, text: str, tag: str = "muted") -> None:
        self.console.configure(state="normal")
        self.console.insert("end", f"{prefix} ", "cmd" if prefix == "BLUE>" else "muted")
        self.console.insert("end", text.rstrip() + "\n\n", tag)
        self.console.see("end")
        self.console.configure(state="disabled")

    def clear_console(self) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def show_text_window(self, title: str, text: str, language: str) -> None:
        """No pop-up windows are allowed in console-only mode."""
        self.write_console(title.upper(), text, "muted")

    def copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Copied output to clipboard.")

    def format_json(self, payload: object) -> str:
        return json.dumps(payload, indent=2)

    def card(
        self,
        parent: tk.Widget,
        *,
        bg: str = Theme.panel,
        border: str = Theme.border,
        padx: int = 0,
        pady: int = 0,
    ) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=bg,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=border,
            padx=padx,
            pady=pady,
        )

    def badge(self, parent: tk.Widget, status: str) -> tk.Label:
        bg, fg, border = STATUS_COLORS.get(status, (Theme.card_2, Theme.muted, Theme.border))
        return tk.Label(
            parent,
            text=STATUS_LABELS.get(status, status).upper(),
            bg=bg,
            fg=fg,
            padx=6,
            pady=2,
            font=self.font_micro,
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=border,
        )


def main() -> None:
    app = GraphicalCodexCliReplOS()
    app.mainloop()


if __name__ == "__main__":
    main()
