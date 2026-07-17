#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

# ---- CONFIG ----
TEXT_EXTENSIONS = {
    ".css", ".cmd", ".js", ".php", ".hpp", ".cpp", ".md", ".py", ".txt", ".ps1", ".html", ".h", ".json", ".c", ".fabric", ".facts", ".rules"
}
IMAGE_EXTENSIONS = {".png"}

SPECIAL_FILENAMES = {".env", ".gitignore", ".htaccess"}  # extensionless-but-important

IGNORE_DIRS = {
    ".git", ".svn", ".hg",
    "node_modules", "vendor",
    "venv", ".venv", "__pycache__",
    "dist", "build", "doc_export",
    ".idea", ".vscode", "testbench",
    "doc", ".runtime",  # prevent bundling the bundle output folder itself
}

MAX_TEXT_FILE_BYTES = 5_000_000  # 5MB cap for *text* files


# ---- HELPERS ----
def is_probably_binary(path: Path, sample_size: int = 4096) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(sample_size)
        return b"\x00" in chunk
    except Exception:
        return True


def is_text_included(path: Path) -> bool:
    if path.name in SPECIAL_FILENAMES:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def is_png(path: Path) -> bool:
    return path.suffix.lower() == ".png"


def is_included_any(path: Path) -> bool:
    return is_text_included(path) or (path.suffix.lower() in IMAGE_EXTENSIONS)


def iter_included_paths(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # prune ignored dirs
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]

        for name in filenames:
            p = Path(dirpath) / name
            if p.is_file() and is_included_any(p):
                yield p


def read_text(path: Path) -> Tuple[str, str]:
    """
    Returns (content, note). note is "" when OK.
    """
    try:
        size = path.stat().st_size
        if size > MAX_TEXT_FILE_BYTES:
            return "", f"Skipped (too large): {size} bytes > {MAX_TEXT_FILE_BYTES}"
        if is_probably_binary(path):
            return "", "Skipped (binary detected)"
        return path.read_text(encoding="utf-8", errors="replace"), ""
    except Exception as e:
        return "", f"Error reading: {e}"


def detect_code_lang(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".json": "json",
        ".html": "html",
        ".css": "css",
        ".ps1": "powershell",
        ".cmd": "bat",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".php": "php",
        ".md": "markdown",
        ".txt": "text",
        "": "text",
    }.get(ext, "text")


def fenced_block(content: str, lang: str) -> str:
    """
    Create a fenced code block that won't break if the content contains ``` already.
    """
    # Find the longest run of backticks in the content
    runs = [len(m.group(0)) for m in re.finditer(r"`+", content)]
    fence_len = max(runs) + 1 if runs else 3
    fence = "`" * max(3, fence_len)
    return f"{fence}{lang}\n{content}\n{fence}\n"


def relpath_posix(from_dir: Path, to_path: Path) -> str:
    rel = os.path.relpath(to_path, start=from_dir)
    return Path(rel).as_posix()


def png_dimensions(path: Path) -> Optional[Tuple[int, int]]:
    """
    Parse PNG IHDR to get (width, height) without external dependencies.
    Returns None if unreadable/not PNG.
    """
    try:
        with path.open("rb") as f:
            header = f.read(24)
        if len(header) < 24:
            return None
        sig = header[:8]
        if sig != b"\x89PNG\r\n\x1a\n":
            return None
        chunk_type = header[12:16]
        if chunk_type != b"IHDR":
            return None
        w = int.from_bytes(header[16:20], "big")
        h = int.from_bytes(header[20:24], "big")
        return (w, h)
    except Exception:
        return None


# ---- TREE BUILD + RENDER ----
TreeNode = Dict[str, Union["TreeNode", None]]  # None means leaf file


def build_tree(relpaths: List[Path]) -> TreeNode:
    root: TreeNode = {}
    for rp in relpaths:
        cur = root
        parts = rp.parts
        for i, part in enumerate(parts):
            is_last = (i == len(parts) - 1)
            if is_last:
                cur.setdefault(part, None)
            else:
                nxt = cur.get(part)
                if nxt is None:
                    cur[part] = {}
                cur = cur[part]  # type: ignore[assignment]
    return root


def render_tree(tree: TreeNode, prefix: str = "") -> List[str]:
    """
    ASCII tree with deterministic ordering:
    directories first, then files, each group alphabetically.
    """
    lines: List[str] = []
    items = list(tree.items())

    def is_dir(item):
        _, v = item
        return isinstance(v, dict)

    dirs = sorted([it for it in items if is_dir(it)], key=lambda x: x[0].lower())
    files = sorted([it for it in items if not is_dir(it)], key=lambda x: x[0].lower())
    ordered = dirs + files

    for idx, (name, node) in enumerate(ordered):
        last = (idx == len(ordered) - 1)
        branch = "└── " if last else "├── "
        lines.append(prefix + branch + name)

        if isinstance(node, dict):
            extension = "    " if last else "│   "
            lines.extend(render_tree(node, prefix + extension))

    return lines


# ---- MAIN OUTPUT ----
def create_doc_md(root: Path, outpath: Path) -> Path:
    files = sorted(iter_included_paths(root), key=lambda p: p.relative_to(root).as_posix().lower())
    relpaths = [p.relative_to(root) for p in files]

    tree = build_tree(relpaths)
    tree_lines = [root.name or root.as_posix()] + render_tree(tree)

    outpath.parent.mkdir(parents=True, exist_ok=True)

    now = _dt.datetime.now().isoformat(timespec="seconds")

    with outpath.open("w", encoding="utf-8") as out:
        # Header
        out.write("# Documentation Bundle\n\n")
        out.write(f"- **Root:** `{root}`\n")
        out.write(f"- **Generated:** `{now}`\n")
        out.write(f"- **Included files:** `{len(files)}`\n")
        out.write(f"- **Max text file bytes:** `{MAX_TEXT_FILE_BYTES}`\n")
        out.write(f"- **Ignored dirs:** `{', '.join(sorted(IGNORE_DIRS))}`\n\n")

        # Tree view
        out.write("## Filesystem Tree (included paths)\n\n")
        out.write(fenced_block("\n".join(tree_lines), "text"))
        out.write("\n")

        # TOC
        out.write("## Table of Contents\n\n")
        for i, rp in enumerate(relpaths, start=1):
            out.write(f"{i}. [`{rp.as_posix()}`](#file-{i})\n")
        out.write("\n")

        # File contents
        out.write("## File Contents\n\n")
        for i, path in enumerate(files, start=1):
            rp = path.relative_to(root).as_posix()
            out.write(f'<a id="file-{i}"></a>\n')
            out.write(f"### [{i}] `{rp}`\n\n")

            size = path.stat().st_size
            out.write(f"- **Bytes:** `{size}`\n")

            if is_png(path):
                out.write("- **Type:** `png`\n")
                dims = png_dimensions(path)
                if dims:
                    out.write(f"- **Dimensions:** `{dims[0]}×{dims[1]}`\n")
                elif size == 0:
                    out.write("- **Dimensions:** `unknown (empty file)`\n")
                else:
                    out.write("- **Dimensions:** `unknown`\n")

                # Embed image (path relative to the markdown file location)
                md_rel = relpath_posix(outpath.parent, path)
                out.write(f"- **Path (from doc):** `{md_rel}`\n\n")
                out.write(f"![{rp}]({md_rel})\n\n")
                continue

            # Text file
            out.write("- **Type:** `text`\n")
            content, note = read_text(path)
            if note:
                out.write(f"- **NOTE:** {note}\n")
            out.write("\n")

            if content:
                lang = detect_code_lang(path)
                out.write(fenced_block(content, lang))
                out.write("\n")
            else:
                out.write("_No content (skipped or empty)._ \n\n")

    return outpath


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bundle repository documentation into doc/doc.md (including .png images)."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Root folder to scan (default: script directory).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output markdown path (default: <root>/doc/doc.md).",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    out = (args.out.resolve() if args.out else (root / "doc" / "doc.md"))

    outpath = create_doc_md(root, out)
    print(f"Documentation updated: Created '{outpath}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
