"""
PROJECT CONTEXT MANAGEMENT PROVIDING ASYNCHRONOUS, SANDBOXED I/O ACCESS
TO SOURCE FILES, DIRECTORIES, AND AST SYMBOLS.
"""

import asyncio
import aiofiles
import re
from pathlib import Path

from .config import CaseConfig
from .indexer import ProjectIndexer
from .models import FileMeta, CachedContent
from .settings import MAX_FILE_SIZE, MAX_CONCURRENT_READS
from ..utils.i18n import strings


class ProjectContext:
    """PROVIDES SANDBOXED, ASYNCHRONOUS, SIZE-LIMITED ACCESS TO PROJECT RESOURCES."""

    IO_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_READS)
    MAX_FILE_SIZE = MAX_FILE_SIZE

    def __init__(
        self,
        target_dir: Path,
        case: CaseConfig,
        indexer: ProjectIndexer,
        has_git: bool = False,
    ):
        """
        INITIALIZES THE CONTEXT LINKING THE PROJECT PATH TO THE INDEXER.

        Args:
            target_dir (Path): The absolute root path of the project.
            case (CaseConfig): Configuration rules.
            indexer (ProjectIndexer): Live index of the project files.
            has_git (bool): Indicates if the directory contains a Git repository.
        """
        self.target_dir = target_dir
        self.case = case
        self.indexer = indexer
        self.cache: dict[str, CachedContent] = {}
        self.has_git = has_git

    def normalize_query_path(self, query: str) -> str:
        """NORMALIZES USER-INPUTTED PATHS TO THE INTERNAL PROJECT FORMAT."""
        return query.replace("\\", "/").strip()

    def is_safe_query_path(self, query: str) -> bool:
        """VALIDATES THAT A QUERY PATH STAYS INSIDE THE PROJECT ROOT."""
        normalized = self.normalize_query_path(query)
        if not normalized:
            return False
        if normalized.startswith(("/", "//")) or re.match(
            r"^[a-zA-Z]:[/\\]", normalized
        ):
            return False

        target = (self.target_dir / normalized).resolve()
        return target.is_relative_to(self.target_dir.resolve())

    def is_sandboxed(self, path: Path) -> bool:
        """
        ENFORCES ABSOLUTE SANDBOXING TO THE TARGET DIRECTORY.

        Args:
            path (Path): Path to verify.

        Returns:
            bool: True if the file resides within the target_dir.
        """
        return path.resolve().is_relative_to(self.target_dir.resolve())

    async def get_file_content(self, query: str, range_str: str | None = None) -> str:
        """
        RETRIEVES FORMATTED FILE CONTENT WITH OPTIONAL LINE SLICING.

        Args:
            query (str): File path or fuzzy search string.
            range_str (str | None): Slicing rules (e.g., "10-20", "last 50").

        Returns:
            str: Markdown-formatted file content.
        """
        matches = self.indexer.find_matches(query)
        if not matches:
            return strings.get("err_file_not_found", "file not found").format(
                query=query
            )

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._read_and_format(meta, range_str))
                for meta in matches
            ]

        results = [t.result() for t in tasks]
        return "\n".join(results)

    async def get_type_contents(self, exts_str: str) -> str:
        """
        RETRIEVES ALL PROJECT FILES MATCHING SPECIFIC EXTENSIONS.

        Args:
            exts_str (str): Comma-separated list of extensions (e.g., "py,md").

        Returns:
            str: Markdown-formatted list of file contents.
        """
        exts = list(dict.fromkeys(e.strip() for e in exts_str.split(",")))
        matches = self.indexer.get_by_extensions(exts)

        if not matches:
            return strings.get("err_type_not_found", "type not found").format(
                exts=exts_str
            )

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._read_and_format(meta, None)) for meta in matches
            ]

        results = [t.result() for t in tasks]
        return "\n".join(results)

    async def get_dir_contents(self, dir_query: str) -> str:
        """
        RETRIEVES ALL FILES CONTAINED WITHIN A SPECIFIC DIRECTORY.

        Args:
            dir_query (str): The relative directory path.

        Returns:
            str: Markdown-formatted list of file contents.
        """
        clean_dir = dir_query.lstrip("/\\")
        matches = [
            m for p, m in self.indexer.files_by_rel.items() if p.startswith(clean_dir)
        ]

        if not matches:
            return strings.get("err_dir_empty", "dir empty").format(query=dir_query)

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._read_and_format(meta, None)) for meta in matches
            ]

        results = [t.result() for t in tasks]
        return "\n".join(results)

    async def get_tree_contents(
        self, dir_query: str, depth_str: str | None = None
    ) -> str:
        """
        RETRIEVES A FORMATTED TREE DIRECTORY STRUCTURE MAPPING.

        Args:
            dir_query (str): The relative directory path.
            depth_str (str | None): Optional integer string limiting the recursive depth.

        Returns:
            str: Visual tree representation.
        """
        clean_dir = dir_query.lstrip("/\\")
        target = (self.target_dir / clean_dir).resolve()

        if not target.is_relative_to(self.target_dir.resolve()):
            return strings.get("err_access_denied", "access denied").format(
                path=clean_dir
            )

        rel_target = str(target.relative_to(self.target_dir)).replace("\\", "/")
        if rel_target == ".":
            rel_target = ""

        if rel_target and rel_target not in self.indexer.dirs:
            return strings.get("err_dir_empty", "dir empty").format(query=dir_query)

        max_depth = None
        if depth_str:
            try:
                max_depth = int(depth_str.strip())
            except ValueError:
                return strings.get("err_invalid_depth", "\n\n").format(depth=depth_str)

        return self.generate_tree(rel_target, max_depth)

    async def get_symbol_content(self, query: str, symbol_name: str) -> str:
        """
        RETRIEVES A SPECIFICALLY REQUESTED AST SYMBOL FROM A FILE.

        Args:
            query (str): The file containing the symbol.
            symbol_name (str): The name of the class/method/function.

        Returns:
            str: Formatted symbol block.
        """
        if not symbol_name:
            return ""

        matches = self.indexer.find_matches(query)
        if not matches:
            return strings.get("err_file_not_found", "file not found").format(
                query=query
            )

        meta = matches[0]
        if meta.size > self.MAX_FILE_SIZE:
            return strings.get("err_file_too_large", "file too large").format(
                path=meta.rel_path
            )

        content = await self._read_cached(meta)

        from .extractor import SymbolExtractor

        try:
            extractor = SymbolExtractor(content, meta.path.name)
            extracted = extractor.extract(symbol_name)
            if not extracted:
                return strings.get("symbol_not_found", "symbol not found").format(
                    symbol=symbol_name, path=meta.rel_path
                )
            return f"- `{meta.rel_path}:{symbol_name}`\n\n```{meta.ext}\n{extracted}\n```\n"
        except ValueError as e:
            return strings.get("symbol_error", "symbol error").format(error=e)

    async def get_git_diff(self, path: str | None = None) -> str:
        """
        RETRIEVES THE WORKING TREE DIFFERENCES FOR THE PROJECT OR SPECIFIC FILE.

        Args:
            path (str | None): Target path to isolate the diff.

        Returns:
            str: Git diff output.
        """
        if not self.has_git:
            return ""

        cmd = ["git", "diff"]
        if path:
            cmd.extend(["--", path])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.target_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return strings.get("git_diff_error", "git diff error").format(
                error=stderr.decode(errors="replace").strip()
            )

        diff_text = stdout.decode(errors="replace")
        if not diff_text.strip():
            return strings.get("no_changes", "no changes")
        return f"```diff\n{diff_text}\n```\n"

    async def get_git_status(self) -> str:
        """
        RETRIEVES THE WORKING TREE STATUS.

        Returns:
            str: Git status output.
        """
        if not self.has_git:
            return ""

        proc = await asyncio.create_subprocess_exec(
            "git",
            "status",
            "-s",
            cwd=self.target_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return strings.get("git_status_error", "git status error").format(
                error=stderr.decode(errors="replace").strip()
            )

        status_text = stdout.decode(errors="replace")
        if not status_text.strip():
            return strings.get("working_tree_clean", "clean tree")
        return f"```log\n{status_text}\n```\n"

    async def _read_and_format(self, meta: FileMeta, range_str: str | None) -> str:
        """
        CORE I/O PROCESS APPLYING RULES, LIMITS, CACHING, AND TEXT FORMATTING.

        Args:
            meta (FileMeta): Target file metadata.
            range_str (str | None): Slicing arguments.

        Returns:
            str: The evaluated final markdown block.
        """
        if meta.size > self.MAX_FILE_SIZE:
            return strings.get("err_file_too_large", "file too large").format(
                path=meta.rel_path
            )

        if not self.is_sandboxed(meta.path):
            return strings.get("err_access_denied", "access denied").format(
                path=meta.rel_path
            )

        content = await self._read_cached(meta)
        lines = content.splitlines(keepends=True)

        if range_str:
            lines, omitted = self._apply_range(lines, range_str)
            if omitted > 0:
                syntax = strings.get("comment_syntax", {}).get(meta.ext, ["// ", ""])
                prefix, suffix = syntax[0], syntax[1]
                notice = strings.get("truncation_notice", "truncated").format(
                    prefix=prefix, omitted=omitted, suffix=suffix
                )
                lines.append(notice)

        final_content = "".join(lines)
        return f"- `{meta.rel_path}`\n\n```{meta.ext}\n{final_content}\n```\n"

    async def _read_cached(self, meta: FileMeta) -> str:
        """
        READS FILE CONTENT SECURELY FROM DISK, LEVERAGING AN MTIME CACHE.

        Args:
            meta (FileMeta): Data object for the file to read.

        Returns:
            str: Unmodified text content.
        """
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
        """
        EVALUATES LIMITS LIKE 'FIRST 200', 'LAST 100', '10-20', OR '#L45'.

        Args:
            lines (list[str]): The original array of text lines.
            range_str (str): The rule determining the slice limit.

        Returns:
            tuple[list[str], int]: Processed lines and count of omitted lines.
        """
        range_str = range_str.strip().lower()
        total = len(lines)
        error_msg = strings.get("err_invalid_range", "invalid range").format(
            range=range_str
        )

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

        return lines + [error_msg], 0

    def generate_tree(self, root_rel: str = "", max_depth: int | None = None) -> str:
        """
        RECREATES THE CLASSIC WINDOWS 'TREE /F' COMMAND STYLE MAP OF THE INDEX.

        Args:
            root_rel (str): Starting point inside the project for tree evaluation.
            max_depth (int | None): Maximum recursive folder depth to crawl.

        Returns:
            str: ASCII format tree.
        """
        root_rel = root_rel.replace("\\", "/").strip("/")

        if not root_rel:
            header_name = self.target_dir.name
        else:
            header_name = root_rel.split("/")[-1]

        tree_str = [
            strings.get("tree_header_1", "TREE /F"),
            strings.get("tree_header_2", "Folder PATH for {name}").format(
                name=header_name
            ),
            strings.get("tree_header_3", "C:."),
        ]

        search_prefix = root_rel + "/" if root_rel else ""

        def _build_tree(current_dir: str, prefix: str = "", current_depth: int = 1):
            if max_depth is not None and current_depth > max_depth:
                return

            children = set()
            for p in self.indexer.files_by_rel:
                if p.startswith(current_dir):
                    rel = p[len(current_dir) :]
                    parts = rel.split("/", 1)
                    if parts[0]:
                        children.add(parts[0])

            items = sorted(
                list(children),
                key=lambda x: (
                    (current_dir + x).rstrip("/") not in self.indexer.dirs,
                    x.lower(),
                ),
            )

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└───" if is_last else "├───"
                tree_str.append(f"{prefix}{connector}{item}")

                full_path = current_dir + item
                if full_path in self.indexer.dirs:
                    extension = "    " if is_last else "│   "
                    _build_tree(full_path + "/", prefix + extension, current_depth + 1)

        _build_tree(search_prefix)
        content = "\n".join(tree_str)
        return f"```log\n{content}\n\n```\n"
