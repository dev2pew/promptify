"""
Project context management providing asynchronous, sandboxed I/O access
to source files, directories, and AST symbols.
"""

import asyncio
import aiofiles
from pathlib import Path

from .config import CaseConfig
from .indexer import ProjectIndexer
from .models import FileMeta, CachedContent
from .settings import MAX_FILE_SIZE, MAX_CONCURRENT_READS
from ..utils.i18n import strings


class ProjectContext:
    """Provides sandboxed, asynchronous, size-limited access to project resources."""

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
        Initializes the context linking the project path to the indexer.

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

    def is_sandboxed(self, path: Path) -> bool:
        """
        Enforces absolute sandboxing to the target directory.

        Args:
            path (Path): Path to verify.

        Returns:
            bool: True if the file resides within the target_dir.
        """
        return path.resolve().is_relative_to(self.target_dir.resolve())

    async def get_file_content(self, query: str, range_str: str | None = None) -> str:
        """
        Retrieves formatted file content with optional line slicing.

        Args:
            query (str): File path or fuzzy search string.
            range_str (str | None): Slicing rules (e.g., "10-20", "last 50").

        Returns:
            str: Markdown-formatted file content.
        """
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
        """
        Retrieves all project files matching specific extensions.

        Args:
            exts_str (str): Comma-separated list of extensions (e.g., "py,md").

        Returns:
            str: Markdown-formatted list of file contents.
        """
        exts = list(dict.fromkeys(e.strip() for e in exts_str.split(",")))
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
        """
        Retrieves all files contained within a specific directory.

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
            return strings["err_dir_empty"].format(query=dir_query)

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._read_and_format(meta, None)) for meta in matches
            ]

        results = [t.result() for t in tasks]
        return "\n".join(results)

    async def get_tree_contents(self, dir_query: str) -> str:
        """
        Retrieves a formatted tree directory structure mapping.

        Args:
            dir_query (str): The relative directory path.

        Returns:
            str: Visual tree representation.
        """
        clean_dir = dir_query.lstrip("/\\")
        target = (self.target_dir / clean_dir).resolve()

        if not target.is_relative_to(self.target_dir.resolve()):
            return strings.get("err_access_denied", "<!-- access denied -->").format(
                path=clean_dir
            )

        rel_target = str(target.relative_to(self.target_dir)).replace("\\", "/")
        if rel_target == ".":
            rel_target = ""

        if rel_target and rel_target not in self.indexer.dirs:
            return strings["err_dir_empty"].format(query=dir_query)

        return self.generate_tree(rel_target)

    async def get_symbol_content(self, query: str, symbol_name: str) -> str:
        """
        Retrieves a specifically requested AST symbol from a file.

        Args:
            query (str): The file containing the symbol.
            symbol_name (str): The name of the class/method/function.

        Returns:
            str: Formatted symbol block.
        """
        if not symbol_name:
            return f"<!-- error: no symbol provided for {query} -->"

        matches = self.indexer.find_matches(query)
        if not matches:
            return strings["err_file_not_found"].format(query=query)

        meta = matches[0]
        if meta.size > self.MAX_FILE_SIZE:
            return strings["err_file_too_large"].format(path=meta.rel_path)

        content = await self._read_cached(meta)

        from .extractor import SymbolExtractor

        try:
            extractor = SymbolExtractor(content, meta.path.name)
            extracted = extractor.extract(symbol_name)
            if not extracted:
                return strings.get(
                    "symbol_not_found",
                    "<!-- error: symbol '{symbol}' not found in {path} -->",
                ).format(symbol=symbol_name, path=meta.rel_path)
            return f"- `{meta.rel_path}:{symbol_name}`\n\n```{meta.ext}\n{extracted}\n```\n"
        except ValueError as e:
            return strings.get("symbol_error", "<!-- error: {error} -->").format(
                error=e
            )

    async def get_git_diff(self, path: str | None = None) -> str:
        """
        Retrieves the working tree differences for the project or specific file.

        Args:
            path (str | None): Target path to isolate the diff.

        Returns:
            str: Git diff output.
        """
        if not self.has_git:
            return "<!-- error: git not available -->"

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
            return strings.get(
                "git_diff_error", "<!-- git diff error: {error} -->"
            ).format(error=stderr.decode(errors="replace").strip())

        diff_text = stdout.decode(errors="replace")
        if not diff_text.strip():
            return strings.get("no_changes", "<!-- no changes -->")
        return f"```diff\n{diff_text}\n```\n"

    async def get_git_status(self) -> str:
        """
        Retrieves the working tree status.

        Returns:
            str: Git status output.
        """
        if not self.has_git:
            return "<!-- error: git not available -->"

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
            return strings.get(
                "git_status_error", "<!-- git status error: {error} -->"
            ).format(error=stderr.decode(errors="replace").strip())

        status_text = stdout.decode(errors="replace")
        if not status_text.strip():
            return strings.get("working_tree_clean", "<!-- working tree clean -->")
        return f"```log\n{status_text}\n```\n"

    async def _read_and_format(self, meta: FileMeta, range_str: str | None) -> str:
        """
        Core I/O process applying rules, limits, caching, and text formatting.

        Args:
            meta (FileMeta): Target file metadata.
            range_str (str | None): Slicing arguments.

        Returns:
            str: The evaluated final markdown block.
        """
        if meta.size > self.MAX_FILE_SIZE:
            return strings["err_file_too_large"].format(path=meta.rel_path)

        if not self.is_sandboxed(meta.path):
            return strings.get("err_access_denied", "<!-- access denied -->").format(
                path=meta.rel_path
            )

        content = await self._read_cached(meta)
        lines = content.splitlines(keepends=True)

        if range_str:
            lines, omitted = self._apply_range(lines, range_str)
            if omitted > 0:
                syntax = strings.get("comment_syntax", {}).get(meta.ext, ["// ", ""])
                prefix, suffix = syntax[0], syntax[1]
                notice = strings["truncation_notice"].format(
                    prefix=prefix, omitted=omitted, suffix=suffix
                )
                lines.append(notice)

        final_content = "".join(lines)
        return f"- `{meta.rel_path}`\n\n```{meta.ext}\n{final_content}\n```\n"

    async def _read_cached(self, meta: FileMeta) -> str:
        """
        Reads file content securely from disk, leveraging an mtime cache.

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
        Evaluates limits like 'first 200', 'last 100', '10-20', or '#L45'.

        Args:
            lines (list[str]): The original array of text lines.
            range_str (str): The rule determining the slice limit.

        Returns:
            tuple[list[str], int]: Processed lines and count of omitted lines.
        """
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

        return lines + [error_msg], 0

    def generate_tree(self, root_rel: str = "") -> str:
        # NORMALIZE THE STARTING PATH
        root_rel = root_rel.replace("\\", "/").strip("/")

        # DETERMINE THE FOLDER NAME FOR THE HEADER
        if not root_rel:
            header_name = self.target_dir.name
        else:
            # GET THE LAST PART OF THE PATH (THE FOLDER NAME)
            header_name = root_rel.split("/")[-1]

        tree_str = [
            strings["tree_header_1"],
            strings["tree_header_2"].format(name=header_name),
            strings["tree_header_3"],
        ]

        # ENSURE SEARCH_PREFIX IS EITHER EMPTY OR ENDS WITH A SINGLE SLASH
        search_prefix = root_rel + "/" if root_rel else ""

        def _build_tree(current_dir: str, prefix: str = ""):
            children = set()
            for p in self.indexer.files_by_rel:
                if p.startswith(current_dir):
                    # EXTRACT THE IMMEDIATE NEXT SEGMENT OF THE PATH
                    rel = p[len(current_dir) :]
                    parts = rel.split("/", 1)
                    if parts[0]:
                        children.add(parts[0])

            # SORT DIRECTORIES FIRST, THEN ALPHABETICALLY
            items = sorted(
                list(children),
                key=lambda x: (
                    # RECONSTRUCT RELATIVE PATH FOR INDEX CHECK (NO TRAILING SLASH)
                    (current_dir + x).rstrip("/") not in self.indexer.dirs,
                    x.lower(),
                ),
            )

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└───" if is_last else "├───"
                tree_str.append(f"{prefix}{connector}{item}")

                # RECURSE IF THE ITEM IS A DIRECTORY
                full_path = current_dir + item
                if full_path in self.indexer.dirs:
                    extension = "    " if is_last else "│   "
                    # ENSURE NEXT LEVEL STARTS WITH A CLEAN TRAILING SLASH
                    _build_tree(full_path + "/", prefix + extension)

        _build_tree(search_prefix)
        content = "\n".join(tree_str)
        return f"```log\n{content}\n\n```\n"
