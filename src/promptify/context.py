import asyncio
import aiofiles
from pathlib import Path

from .config import CaseConfig
from .indexer import ProjectIndexer
from .models import FileMeta, CachedContent


class ProjectContext:
    """Provides sandboxed, asynchronous, size-limited access to project resources."""

    # Restrict concurrent I/O to avoid exhausting file descriptors
    IO_SEMAPHORE = asyncio.Semaphore(100)
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB limit for single file reads

    # Language aware commenting syntax mapping
    COMMENT_SYNTAX = {
        "python": ("# ", ""),
        "py": ("# ", ""),
        "bash": ("# ", ""),
        "sh": ("# ", ""),
        "yaml": ("# ", ""),
        "yml": ("# ", ""),
        "ruby": ("# ", ""),
        "rb": ("# ", ""),
        "javascript": ("// ", ""),
        "js": ("// ", ""),
        "typescript": ("// ", ""),
        "ts": ("// ", ""),
        "java": ("// ", ""),
        "c": ("// ", ""),
        "cpp": ("// ", ""),
        "csharp": ("// ", ""),
        "cs": ("// ", ""),
        "go": ("// ", ""),
        "rust": ("// ", ""),
        "rs": ("// ", ""),
        "swift": ("// ", ""),
        "php": ("// ", ""),
        "html": ("<!-- ", " -->"),
        "xml": ("<!-- ", " -->"),
        "markdown": ("<!-- ", " -->"),
        "md": ("<!-- ", " -->"),
        "css": ("/* ", " */"),
        "scss": ("/* ", " */"),
        "sql": ("-- ", ""),
        "lua": ("-- ", ""),
    }

    def __init__(self, target_dir: Path, case: CaseConfig, indexer: ProjectIndexer):
        self.target_dir = target_dir
        self.case = case
        self.indexer = indexer
        self.cache: dict[str, CachedContent] = {}

    def is_sandboxed(self, path: Path) -> bool:
        """Enforces absolute sandboxing to the target_dir."""
        try:
            path.resolve().relative_to(self.target_dir.resolve())
            return True
        except ValueError:
            return False

    async def get_file_content(self, query: str, range_str: str | None = None) -> str:
        matches = self.indexer.find_matches(query)
        if not matches:
            return f"<!-- error... no files matching '{query}' found -->\n"

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
            return f"<!-- no files found for types '{exts_str}' -->\n"

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._read_and_format(meta, None)) for meta in matches
            ]

        results = [t.result() for t in tasks]
        return "\n".join(results)

    async def get_dir_contents(self, dir_query: str) -> str:
        # Match all files starting with the directory path
        clean_dir = dir_query.lstrip("/\\")
        matches = [
            m for p, m in self.indexer.files_by_rel.items() if p.startswith(clean_dir)
        ]

        if not matches:
            return f"<!-- directory '{dir_query}' is empty or not found -->\n"

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._read_and_format(meta, None)) for meta in matches
            ]

        results = [t.result() for t in tasks]
        return "\n".join(results)

    async def _read_and_format(self, meta: FileMeta, range_str: str | None) -> str:
        if meta.size > self.MAX_FILE_SIZE:
            return f"<!-- error... '{meta.rel_path}' exceeds 5MB size limit -->\n"

        if not self.is_sandboxed(meta.path):
            return f"<!-- error... access denied to '{meta.rel_path}' -->\n"

        content = await self._read_cached(meta)
        lines = content.splitlines(keepends=True)

        if range_str:
            lines, omitted = self._apply_range(lines, range_str)
            if omitted > 0:
                prefix, suffix = self.COMMENT_SYNTAX.get(meta.ext, ("// ", ""))
                lines.append(
                    f"\n{prefix}... (truncated, {omitted} lines omitted){suffix}\n"
                )

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

        if range_str.startswith("first "):
            try:
                n = int(range_str.split()[1])
                return lines[:n], max(0, total - n)
            except ValueError:
                pass

        elif range_str.startswith("last "):
            try:
                n = int(range_str.split()[1])
                return lines[-n:], max(0, total - n)
            except ValueError:
                pass

        elif "-" in range_str:
            try:
                r = range_str.replace("#l", "").replace("l", "")
                s, e = map(int, r.split("-"))
                return lines[max(0, s - 1) : e], max(0, total - (e - max(0, s - 1)))
            except ValueError:
                pass

        elif range_str.startswith("#l"):
            try:
                n = int(range_str.replace("#l", ""))
                return lines[max(0, n - 1) : n], max(0, total - 1)
            except ValueError:
                pass

        return lines, 0

    def generate_tree(self) -> str:
        tree_str = ["TREE /F", f"Folder PATH listing for {self.target_dir.name}", "C:."]

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
                    not (current_dir.lstrip("/") + "/" + x).rstrip("/")
                    in self.indexer.dirs,
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
