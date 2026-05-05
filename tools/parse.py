#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


HEADER_RE = re.compile(r"^-\s*`([^`\n]+)`\s*$")
OPEN_FENCE_RE = re.compile(r"^```([A-Za-z0-9_.+-]*)$")

CLOSE_FENCE = "```"


@dataclass(frozen=True)
class FileBlock:
    path: str
    ext: str
    content: str
    line: int


class ParseError(Exception):
    pass


def parse_markdown(text: str, source_name: str) -> list[FileBlock]:
    lines = text.splitlines(keepends=True)
    blocks: list[FileBlock] = []

    i = 0
    while i < len(lines):
        line_no = i + 1
        line = lines[i].rstrip("\r\n")

        header = HEADER_RE.fullmatch(line)
        if not header:
            i += 1
            continue

        file_path = header.group(1).strip()
        if not file_path:
            raise ParseError(f"{source_name}:{line_no}: empty file path")

        i += 1

        # Your standard is:
        #
        # - `path/to/file.ext`
        #
        # ```ext
        #
        # So this tolerates one or more blank lines after the path.
        while i < len(lines) and lines[i].rstrip("\r\n") == "":
            i += 1

        if i >= len(lines):
            raise ParseError(f"{source_name}:{line_no}: expected opening code fence after path")

        fence_line_no = i + 1
        fence_line = lines[i].rstrip("\r\n")

        opening = OPEN_FENCE_RE.fullmatch(fence_line)
        if not opening:
            raise ParseError(
                f"{source_name}:{fence_line_no}: expected opening fence like ```py"
            )

        ext = opening.group(1)
        i += 1

        content: list[str] = []

        while i < len(lines):
            current = lines[i].rstrip("\r\n")

            # Strict close rule:
            # only a line exactly equal to ``` closes the block.
            if current == CLOSE_FENCE:
                break

            content.append(lines[i])
            i += 1

        if i >= len(lines):
            raise ParseError(
                f"{source_name}:{fence_line_no}: missing closing fence ^```$ for {file_path}"
            )

        blocks.append(
            FileBlock(
                path=file_path,
                ext=ext,
                content="".join(content),
                line=line_no,
            )
        )

        # Skip closing fence.
        i += 1

    return blocks


def safe_target_path(root: Path, raw_path: str) -> Path:
    raw_path = raw_path.replace("\\", "/")

    if raw_path.startswith("/") or re.match(r"^[A-Za-z]:/", raw_path):
        raise ValueError(f"absolute paths are not allowed: {raw_path}")

    parts = Path(raw_path).parts
    if ".." in parts:
        raise ValueError(f"path traversal is not allowed: {raw_path}")

    root = root.resolve()
    target = (root / raw_path).resolve()

    if os.path.commonpath([root, target]) != str(root):
        raise ValueError(f"unsafe path: {raw_path}")

    return target


def write_blocks(blocks: list[FileBlock], output_root: Path) -> None:
    seen: set[str] = set()

    for block in blocks:
        normalized_path = block.path.replace("\\", "/")

        if normalized_path in seen:
            raise ValueError(f"duplicate file path in markdown: {block.path}")

        seen.add(normalized_path)

        target = safe_target_path(output_root, normalized_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(block.content, encoding="utf-8")


def parse_file(markdown_file: Path) -> None:
    if not markdown_file.is_file():
        raise FileNotFoundError(f"not a file: {markdown_file}")

    text = markdown_file.read_text(encoding="utf-8")
    blocks = parse_markdown(text, str(markdown_file))

    output_root = markdown_file.with_name(f"{markdown_file.stem}_res")
    write_blocks(blocks, output_root)

    print(f"{markdown_file} -> {output_root} ({len(blocks)} file(s))")


def main(argv: list[str]) -> int:
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
