#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

HEADER_RE = re.compile(r"^-\s*`([^`\n]+)`\s*$")
OPEN_FENCE_RE = re.compile(r"^```([A-Za-z0-9_.+-]*)$")
CLOSE_FENCE = "```"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    source_name: str
    line: int
    column: int

    def format(self) -> str:
        """Return the location using the requested line and column shape."""
        return f"{self.source_name}:{self.line}:{self.column}"


@dataclass(frozen=True, slots=True)
class FileBlock:
    path: str
    ext: str
    content: str
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class DuplicateBlockWarning:
    path: str
    first: SourceLocation
    duplicate: SourceLocation

    def format(self) -> str:
        """Return a human-readable duplicate warning message."""
        return (
            f"warning: duplicate mention output for '{self.path}' at "
            f"{self.duplicate.format()}; keeping first from {self.first.format()}"
        )


class ParseError(Exception):
    """Report malformed mention output blocks."""


def _line_text(line: str) -> str:
    """Strip one markdown line down to its visible text."""
    return line.rstrip("\r\n")


def _header_column(line: str) -> int:
    """Return the 1-based start column of the path inside one header line."""
    return line.index("`") + 2


def _normalize_path(raw_path: str) -> str:
    """Normalize a mention path into a stable slash-separated relative path."""
    return raw_path.replace("\\", "/").strip()


def _looks_like_supported_mention_path(raw_path: str) -> bool:
    """Return whether a header path matches file and dir mention output only."""
    path = _normalize_path(raw_path)
    if not path or ":" in path:
        return False
    if path.startswith("/") or re.match(r"^[A-Za-z]:/", path):
        return False
    return ".." not in Path(path).parts


def parse_markdown(text: str, source_name: str) -> list[FileBlock]:
    """Extract file and directory mention output blocks from markdown."""
    lines = text.splitlines(keepends=True)
    blocks: list[FileBlock] = []
    i = 0
    while i < len(lines):
        line = _line_text(lines[i])
        header = HEADER_RE.fullmatch(line)
        if header is None:
            i += 1
            continue

        file_path = _normalize_path(header.group(1))
        if not _looks_like_supported_mention_path(file_path):
            i += 1
            continue

        location = SourceLocation(
            source_name=source_name,
            line=i + 1,
            column=_header_column(line),
        )
        fence_index = i + 1
        while fence_index < len(lines) and _line_text(lines[fence_index]) == "":
            fence_index += 1

        if fence_index >= len(lines):
            i += 1
            continue

        opening = OPEN_FENCE_RE.fullmatch(_line_text(lines[fence_index]))
        if opening is None:
            i += 1
            continue

        ext = opening.group(1)
        content_index = fence_index + 1
        content: list[str] = []
        while content_index < len(lines):
            if _line_text(lines[content_index]) == CLOSE_FENCE:
                blocks.append(
                    FileBlock(
                        path=file_path,
                        ext=ext,
                        content="".join(content),
                        location=location,
                    )
                )
                i = content_index + 1
                break
            content.append(lines[content_index])
            content_index += 1
        else:
            raise ParseError(
                f"{location.format()}: missing closing fence ^```$ for {file_path}"
            )
    return blocks


def dedupe_blocks(
    blocks: list[FileBlock],
) -> tuple[list[FileBlock], list[DuplicateBlockWarning]]:
    """Keep the first copy of each file path and collect duplicate warnings."""
    unique: list[FileBlock] = []
    seen: dict[str, FileBlock] = {}
    warnings: list[DuplicateBlockWarning] = []
    for block in blocks:
        existing = seen.get(block.path)
        if existing is None:
            seen[block.path] = block
            unique.append(block)
            continue
        warnings.append(
            DuplicateBlockWarning(
                path=block.path,
                first=existing.location,
                duplicate=block.location,
            )
        )
    return unique, warnings


def safe_target_path(root: Path, raw_path: str) -> Path:
    """Resolve a safe output path inside the generated root directory."""
    normalized_path = _normalize_path(raw_path)
    if normalized_path.startswith("/") or re.match(r"^[A-Za-z]:/", normalized_path):
        raise ValueError(f"absolute paths are not allowed: {raw_path}")

    parts = Path(normalized_path).parts
    if ".." in parts:
        raise ValueError(f"path traversal is not allowed: {raw_path}")

    resolved_root = root.resolve()
    target = (resolved_root / normalized_path).resolve()
    if os.path.commonpath([resolved_root, target]) != str(resolved_root):
        raise ValueError(f"unsafe path: {raw_path}")
    return target


def prepare_output_root(output_root: Path) -> None:
    """Reset the generated output directory so the rebuild stays exact."""
    if output_root.is_dir():
        shutil.rmtree(output_root)
    elif output_root.exists():
        output_root.unlink()
    output_root.mkdir(parents=True, exist_ok=True)


def write_blocks(blocks: list[FileBlock], output_root: Path) -> None:
    """Write the extracted files into the generated output directory."""
    prepare_output_root(output_root)
    for block in blocks:
        target = safe_target_path(output_root, block.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(block.content, encoding="utf-8")


def parse_file(markdown_file: Path) -> None:
    """Parse one markdown prompt file into a sibling reconstructed directory."""
    if not markdown_file.is_file():
        raise FileNotFoundError(f"not a file: {markdown_file}")

    text = markdown_file.read_text(encoding="utf-8")
    blocks = parse_markdown(text, str(markdown_file))
    unique_blocks, warnings = dedupe_blocks(blocks)
    output_root = markdown_file.with_name(f"{markdown_file.stem}_res")
    write_blocks(unique_blocks, output_root)

    for warning in warnings:
        print(warning.format(), file=sys.stderr)

    print(f"{markdown_file} -> {output_root} ({len(unique_blocks)} file(s))")


def main(argv: list[str]) -> int:
    """Process one or more markdown files passed on the command line."""
    if len(argv) < 2:
        print("usage: python parse.py <filename> <filename> <filename>", file=sys.stderr)
        return 2

    ok = True
    for name in argv[1:]:
        try:
            parse_file(Path(name))
        except Exception as exc:
            ok = False
            print(f"error: {name}: {exc}", file=sys.stderr)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
