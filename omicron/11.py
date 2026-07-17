#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


HEADER_RE = re.compile(
    r'^<a id="file-(?P<a_id>\d+)"></a>\s*\n'
    r'### \[(?P<num>\d+)\] `(?P<path>[^`\n]+)`\s*\n',
    re.MULTILINE,
)

TYPE_RE = re.compile(r'^- \*\*Type:\*\* `(?P<type>[^`]+)`\s*$', re.MULTILINE)
PATH_FROM_DOC_RE = re.compile(r'^- \*\*Path \(from doc\):\*\* `(?P<path>[^`]+)`\s*$', re.MULTILINE)
NOTE_RE = re.compile(r'^- \*\*NOTE:\*\* (?P<note>.+?)\s*$', re.MULTILINE)

NO_CONTENT_MARKER = "_No content (skipped or empty)._"


@dataclass(frozen=True)
class ExportedFile:
    index: int
    relative_path: str
    file_type: str
    target_path: Path
    status: str
    warning: Optional[str] = None


@dataclass(frozen=True)
class ParsedSection:
    index: int
    relative_path: str
    file_type: str
    body: str


def _normalise_relative_path(raw_path: str) -> Path:
    """
    Convert the POSIX relative paths emitted by bundle_documentation.py into a safe
    platform-local relative Path.

    Rejects absolute paths, drive paths, and any path containing '..' so a malicious
    or edited doc.md cannot write outside the selected export directory.
    """
    raw = raw_path.strip().replace("\\", "/")
    if not raw:
        raise ValueError("empty path")

    # Reject POSIX absolute and Windows drive / UNC forms before Path conversion.
    if raw.startswith("/") or raw.startswith("//") or re.match(r"^[A-Za-z]:/", raw):
        raise ValueError(f"unsafe absolute path: {raw_path!r}")

    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if not parts:
        raise ValueError(f"empty path after normalisation: {raw_path!r}")
    if any(part == ".." for part in parts):
        raise ValueError(f"unsafe parent-directory segment in path: {raw_path!r}")

    return Path(*parts)


def _find_code_fence(section_body: str) -> Optional[Tuple[str, str, int, int]]:
    """
    Return (fence, language, content_start, content_end) for the first fenced code
    block in a file section. The bundler selects a backtick fence longer than any
    run of backticks in the content, then writes:

        <fence><lang>
        <content>
        <fence>

    Therefore the exporter removes exactly one final line break before the closing
    fence to recover the original text content.
    """
    opening_re = re.compile(r"^(`{3,})([^\r\n`]*)\r?\n", re.MULTILINE)

    for opening in opening_re.finditer(section_body):
        fence = opening.group(1)
        language = opening.group(2).strip()
        closing_re = re.compile(rf"^{re.escape(fence)}[ \t]*\r?$", re.MULTILINE)
        closing = closing_re.search(section_body, opening.end())
        if closing:
            content_start = opening.end()
            content_end = closing.start()
            return fence, language, content_start, content_end

    return None


def _extract_text_content(section: ParsedSection) -> Tuple[str, Optional[str]]:
    """
    Extract text file contents from the bundled Markdown section.

    Returns (content, warning). Empty original files and skipped files both appear
    without a fenced block in doc.md. If a NOTE says the file was skipped, the
    exporter creates an empty file and reports a warning because the original bytes
    are not present in the bundle.
    """
    fence_info = _find_code_fence(section.body)
    note_match = NOTE_RE.search(section.body)
    note = note_match.group("note") if note_match else None

    if fence_info is None:
        warning = None
        if note:
            warning = f"{section.relative_path}: content was not embedded in doc.md ({note}); created empty file"
        elif NO_CONTENT_MARKER in section.body:
            warning = None  # Most commonly an originally empty file.
        else:
            warning = f"{section.relative_path}: no fenced content found; created empty file"
        return "", warning

    _, _, start, end = fence_info
    content = section.body[start:end]

    # bundle_documentation.py always writes one extra newline between the content
    # and the closing fence. Remove exactly that sentinel newline.
    if content.endswith("\r\n"):
        content = content[:-2]
    elif content.endswith("\n"):
        content = content[:-1]

    return content, None


def _try_copy_png(section: ParsedSection, doc_path: Path, output_path: Path, asset_root: Optional[Path]) -> Tuple[bool, Optional[str]]:
    """
    PNG files are linked by bundle_documentation.py, not embedded. Try to recover
    them from the linked path beside doc.md, then from --asset-root when provided.
    """
    candidates: List[Path] = []

    linked_match = PATH_FROM_DOC_RE.search(section.body)
    if linked_match:
        linked = linked_match.group("path")
        candidates.append((doc_path.parent / linked).resolve())

    if asset_root is not None:
        try:
            rel = _normalise_relative_path(section.relative_path)
            candidates.append((asset_root / rel).resolve())
        except ValueError:
            pass

    for candidate in candidates:
        if candidate.is_file():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, output_path)
            return True, None

    return False, (
        f"{section.relative_path}: PNG bytes are not embedded in doc.md and no source image was found; "
        "use --asset-root <original-project-root> if the original PNG files still exist"
    )


def parse_bundle_doc(doc_text: str) -> List[ParsedSection]:
    matches = list(HEADER_RE.finditer(doc_text))
    sections: List[ParsedSection] = []

    for pos, match in enumerate(matches):
        start = match.end()
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(doc_text)
        body = doc_text[start:end]

        type_match = TYPE_RE.search(body)
        file_type = type_match.group("type").strip().lower() if type_match else "text"

        sections.append(
            ParsedSection(
                index=int(match.group("num")),
                relative_path=match.group("path"),
                file_type=file_type,
                body=body,
            )
        )

    return sections


def export_doc_md(
    doc_path: Path,
    output_dir: Path,
    *,
    asset_root: Optional[Path] = None,
    clean: bool = False,
    strict: bool = False,
) -> List[ExportedFile]:
    doc_path = doc_path.resolve()
    output_dir = output_dir.resolve()
    asset_root = asset_root.resolve() if asset_root is not None else None

    if not doc_path.is_file():
        raise FileNotFoundError(f"doc.md not found: {doc_path}")

    if clean and output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    doc_text = doc_path.read_text(encoding="utf-8", errors="replace")
    sections = parse_bundle_doc(doc_text)
    if not sections:
        raise ValueError("No bundled file sections were found. Expected headings like: ### [1] `relative/path`")

    exported: List[ExportedFile] = []
    warnings: List[str] = []

    for section in sections:
        try:
            rel_path = _normalise_relative_path(section.relative_path)
        except ValueError as exc:
            warning = f"{section.relative_path}: skipped unsafe path ({exc})"
            warnings.append(warning)
            exported.append(
                ExportedFile(
                    index=section.index,
                    relative_path=section.relative_path,
                    file_type=section.file_type,
                    target_path=output_dir,
                    status="skipped",
                    warning=warning,
                )
            )
            continue

        target_path = output_dir / rel_path

        if section.file_type == "png" or target_path.suffix.lower() == ".png":
            copied, warning = _try_copy_png(section, doc_path, target_path, asset_root)
            status = "copied" if copied else "missing-binary"
            if warning:
                warnings.append(warning)
            exported.append(
                ExportedFile(
                    index=section.index,
                    relative_path=section.relative_path,
                    file_type="png",
                    target_path=target_path,
                    status=status,
                    warning=warning,
                )
            )
            continue

        content, warning = _extract_text_content(section)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8", newline="")

        if warning:
            warnings.append(warning)

        exported.append(
            ExportedFile(
                index=section.index,
                relative_path=section.relative_path,
                file_type=section.file_type,
                target_path=target_path,
                status="written",
                warning=warning,
            )
        )

    if strict and warnings:
        warning_text = "\n".join(f"- {w}" for w in warnings)
        raise RuntimeError(f"Export completed with warnings under --strict:\n{warning_text}")

    return exported


def _default_doc_path() -> Path:
    """
    bundle_documentation.py defaults to <root>/doc/doc.md, but users sometimes copy
    doc.md beside the exporter. Support both without requiring flags.
    """
    cwd = Path.cwd()
    default_bundle_path = cwd / "doc" / "doc.md"
    if default_bundle_path.is_file():
        return default_bundle_path
    return cwd / "doc.md"


def _print_report(exported: Sequence[ExportedFile], output_dir: Path) -> None:
    written = sum(1 for item in exported if item.status == "written")
    copied = sum(1 for item in exported if item.status == "copied")
    missing = sum(1 for item in exported if item.status == "missing-binary")
    skipped = sum(1 for item in exported if item.status == "skipped")
    warnings = [item.warning for item in exported if item.warning]

    print(f"Export directory: {output_dir.resolve()}")
    print(f"Text files written: {written}")
    print(f"Binary/assets copied: {copied}")
    print(f"Missing binary/assets: {missing}")
    print(f"Skipped unsafe paths: {skipped}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild the file tree exported by bundle_documentation.py from its doc.md file. "
            "Text files are restored from fenced code blocks. PNG files are copied from their "
            "linked source path or from --asset-root because PNG bytes are not embedded in doc.md."
        )
    )
    parser.add_argument(
        "--doc",
        type=Path,
        default=None,
        help="Path to the bundled Markdown file. Default: ./doc/doc.md if present, otherwise ./doc.md.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("doc_export"),
        help="Target export directory. Default: ./doc_export.",
    )
    parser.add_argument(
        "--asset-root",
        type=Path,
        default=None,
        help="Optional original project root used to copy PNG assets by their bundled relative paths.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete the target export directory before rebuilding it.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code if any file cannot be fully recovered.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    doc_path = args.doc if args.doc is not None else _default_doc_path()

    try:
        exported = export_doc_md(
            doc_path=doc_path,
            output_dir=args.out,
            asset_root=args.asset_root,
            clean=args.clean,
            strict=args.strict,
        )
    except Exception as exc:
        print(f"export-doc-md.py: error: {exc}", file=sys.stderr)
        return 1

    _print_report(exported, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
