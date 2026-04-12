import asyncio
import aiofiles
from pathlib import Path

from .config import CaseConfig
from .indexer import ProjectIndexer
from .models import FileMeta, CachedContent
from .constants import COMMENT_SYNTAX
from .settings import MAX_FILE_SIZE, MAX_CONCURRENT_READS
from .i18n import strings


class ProjectContext:
    """Provides sandboxed, asynchronous, size-limited access to project resources."""

    IO_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_READS)
    MAX_FILE_SIZE = MAX_FILE_SIZE

    def __init__(self, target_dir: Path, case: CaseConfig, indexer: ProjectIndexer):
        self.target_dir = target_dir
        self.case = case
        self.indexer = indexer
        self.cache: dict[str, CachedContent] = {}

    def is_sandboxed(self, path: Path) -> bool:
        """Enforces absolute sandboxing to the target_dir."""
        return path.resolve().is_relative_to(self.target_dir.resolve())

    async def get_file_content(self, query: str, range_str: str | None = None) -> str:
        matches = self.indexer.find_matches(query)
        if not matches:
            return strings["err_file_not_found"].format(query=query)

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._read_and_format(meta, range_str))
                for meta in matches
            ]

        results = [t.result() for t in tasks]
        return "\n".join(results)

    async def get_type_contents(self, exts_str: str) -> str:
        exts = [e for e in exts_str.split(",")]
        matches = self.indexer.get_by_extensions(exts)

        if not matches:
            return strings["err_type_not_found"].format(exts=exts_str)

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._read_and_format(meta, None)) for meta in matches
            ]

        results = [t.result() for t in tasks]
        return "\n".join(results)

    async def get_dir_contents(self, dir_query: str) -> str:
        clean_dir = dir_query.lstrip("/\\")
        matches = [
            m for p, m in self.indexer.files_by_rel.items() if p.startswith(clean_dir)
        ]

        if not matches:
            return strings["err_dir_empty"].format(query=dir_query)

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._read_and_format(meta, None)) for meta in matches
            ]

        results = [t.result() for t in tasks]
        return "\n".join(results)

    async def _read_and_format(self, meta: FileMeta, range_str: str | None) -> str:
        if meta.size > self.MAX_FILE_SIZE:
            # THIS IS THE LINE THAT WAS CAUSING THE TEST FAILURE
            return strings["err_file_too_large"].format(path=meta.rel_path)

        if not self.is_sandboxed(meta.path):
            return strings["err_access_denied"].format(path=meta.rel_path)

        content = await self._read_cached(meta)
        lines = content.splitlines(keepends=True)

        if range_str:
            lines, omitted = self._apply_range(lines, range_str)
            if omitted > 0:
                prefix, suffix = COMMENT_SYNTAX.get(meta.ext, ("// ", ""))
                notice = strings["truncation_notice"].format(
                    prefix=prefix, omitted=omitted, suffix=suffix
                )
                lines.append(notice)

        final_content = "".join(lines)
        return f"- `{meta.rel_path}`\n\n```{meta.ext}\n{final_content}\n```\n"

    async def _read_cached(self, meta: FileMeta) -> str:
        cached = self.cache.get(meta.rel_path)
        if cached and cached.mtime == meta.mtime:
            return cached.text

        async with self.IO_SEMAPHORE:
            async with aiofiles.open(
                meta.path, "r", encoding="utf-8", errors="replace"
            ) as f:
                content = await f.read()

        self.cache[meta.rel_path] = CachedContent(text=content, mtime=meta.mtime)
        return content

    def _apply_range(self, lines: list[str], range_str: str) -> tuple[list[str], int]:
        """Evaluates limits like 'first 200', 'last 100', '10-20', or '#L45'."""
        range_str = range_str.strip().lower()
        total = len(lines)
        error_msg = strings["err_invalid_range"].format(range=range_str)

        if range_str.startswith("first "):
            try:
                n = int(range_str.split()[1])
                return lines[:n], max(0, total - n)
            except ValueError:
                return lines + [error_msg], 0

        elif range_str.startswith("last "):
            try:
                n = int(range_str.split()[1])
                return lines[-n:], max(0, total - n)
            except ValueError:
                return lines + [error_msg], 0

        elif "-" in range_str:
            try:
                r = range_str.replace("#l", "").replace("l", "")
                s, e = map(int, r.split("-"))
                return lines[max(0, s - 1) : e], max(0, total - (e - max(0, s - 1)))
            except ValueError:
                return lines + [error_msg], 0

        elif range_str.startswith("#l"):
            try:
                n = int(range_str.replace("#l", ""))
                return lines[max(0, n - 1) : n], max(0, total - 1)
            except ValueError:
                return lines + [error_msg], 0

        return lines, 0

    def generate_tree(self) -> str:
        tree_str = [
            strings["tree_header_1"],
            strings["tree_header_2"].format(name=self.target_dir.name),
            strings["tree_header_3"],
        ]

        def _build_tree(current_dir: str, prefix: str = ""):
            children = set()
            for p in self.indexer.files_by_rel:
                if p.startswith(current_dir) and p != current_dir:
                    rel = p[len(current_dir) :].lstrip("/")
                    children.add(rel.split("/")[0])

            for d in self.indexer.dirs:
                if d.startswith(current_dir) and d != current_dir:
                    rel = d[len(current_dir) :].lstrip("/")
                    children.add(rel.split("/")[0])

            items = sorted(
                list(children),
                key=lambda x: (
                    (current_dir.lstrip("/") + "/" + x).rstrip("/")
                    not in self.indexer.dirs,
                    x.lower(),
                ),
            )

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└───" if is_last else "├───"
                tree_str.append(f"{prefix}{connector}{item}")

                full_path = (current_dir.lstrip("/") + "/" + item).strip("/")
                if full_path in self.indexer.dirs:
                    extension = "    " if is_last else "│   "
                    _build_tree(full_path + "/", prefix + extension)

        _build_tree("")
        return "\n".join(tree_str) + "\n"
