"""Project context helpers for sandboxed asynchronous file and Git access"""

import asyncio
import aiofiles
import re
from pathlib import Path
from typing import cast

from .mods import GIT_DEFAULT_HISTORY_LIMIT, GIT_DEFAULT_LOG_LIMIT
from .config import CaseConfig
from .indexer import ProjectIndexer
from .models import FileMeta, CachedContent
from .settings import MAX_FILE_SIZE, MAX_CONCURRENT_READS
from .terminal import APP_TERMINAL_PROFILE, TerminalProfile
from ..utils.i18n import get_string, strings


def get_comment_syntax(ext: str) -> tuple[str, str]:
    """Return comment delimiters for an extension with a safe fallback"""
    syntax_map = strings.get("comment_syntax")
    if isinstance(syntax_map, dict):
        syntax = syntax_map.get(ext)
        if (
            isinstance(syntax, list)
            and len(syntax) >= 2
            and isinstance(syntax[0], str)
            and isinstance(syntax[1], str)
        ):
            return cast(str, syntax[0]), cast(str, syntax[1])
    return "// ", ""


class ProjectContext:
    """Provide sandboxed, asynchronous, size-limited access to project resources"""

    IO_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_READS)
    MAX_FILE_SIZE = MAX_FILE_SIZE

    def __init__(
        self,
        target_dir: Path,
        case: CaseConfig,
        indexer: ProjectIndexer,
        has_git: bool = False,
        terminal_profile: TerminalProfile | None = None,
    ):
        """
        Initialize a context bound to a project path and index.

        Args:
            `target_dir` (Path): The absolute root path of the project.
            `case` (CaseConfig): Configuration rules.
            `indexer` (ProjectIndexer): Live index of the project files.
            `has_git` (bool): Indicates if the directory contains a Git repository.
        """
        self.target_dir = target_dir
        self.case = case
        self.indexer = indexer
        self.cache: dict[str, CachedContent] = {}
        self.has_git = has_git
        self.terminal_profile = terminal_profile or APP_TERMINAL_PROFILE

    async def _run_git_command(self, *args: str) -> tuple[int, str, str]:
        """Run a non-interactive Git command and return decoded output"""
        proc = await asyncio.create_subprocess_exec(
            "git",
            "--no-pager",
            *args,
            cwd=self.target_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        returncode = proc.returncode if proc.returncode is not None else 1
        return (
            returncode,
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace").strip(),
        )

    def _normalize_git_commit_limit(self, limit: int | None, default_limit: int) -> int:
        """Normalize an optional Git commit limit to a safe positive value"""
        if limit is None:
            return default_limit
        return max(1, limit)

    def normalize_query_path(self, query: str) -> str:
        """Normalize a user-provided path to the internal project format"""
        return query.replace("\\", "/").strip()

    def is_safe_query_path(self, query: str) -> bool:
        """Return whether a query path stays within the project root"""
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
        Return whether a path stays inside the target directory.

        Args:
            `path` (Path): Path to verify.

        Returns:
            `bool`: True if the file resides within the `target_dir`.
        """
        return path.resolve().is_relative_to(self.target_dir.resolve())

    async def get_file_content(self, query: str, range_str: str | None = None) -> str:
        """
        Return formatted file content with optional line slicing.

        Args:
            `query` (str): File path or fuzzy search string.
            `range_str` (str | None): Slicing rules (e.g., `10-20`, `last 50`).

        Returns:
            `str`: Markdown-formatted file content.
        """
        matches = self.indexer.find_matches(query)
        if not matches:
            return get_string("err_file_not_found", "file not found").format(
                query=query
            )
        return await self._format_matches(matches, range_str)

    async def get_type_contents(self, exts_str: str) -> str:
        """
        Return formatted content for all files matching the requested extensions.

        Args:
            `exts_str` (str): Comma-separated list of extensions (e.g., `py,md`).

        Returns:
            `str`: Markdown-formatted list of file contents.
        """
        exts = list(dict.fromkeys(e.strip() for e in exts_str.split(",")))
        matches = self.indexer.get_by_extensions(exts)

        if not matches:
            return get_string("err_type_not_found", "type not found").format(
                exts=exts_str
            )
        return await self._format_matches(matches, None)

    async def get_dir_contents(self, dir_query: str) -> str:
        """
        Return formatted content for all files within a directory.

        Args:
            `dir_query` (str): The relative directory path.

        Returns:
            `str`: Markdown-formatted list of file contents.
        """
        clean_dir = self.normalize_query_path(dir_query).strip("/")
        matches = [
            m for p, m in self.indexer.files_by_rel.items() if p.startswith(clean_dir)
        ]

        if not matches:
            return get_string("err_dir_empty", "dir empty").format(query=dir_query)
        return await self._format_matches(matches, None)

    async def get_tree_contents(
        self, dir_query: str, depth_str: str | None = None
    ) -> str:
        """
        Return a formatted tree view for a directory.

        Args:
            `dir_query` (str): The relative directory path.
            `depth_str` (str | None): Optional integer string limiting the recursive depth.

        Returns:
            `str`: Visual tree representation.
        """
        clean_dir = self.normalize_query_path(dir_query).strip("/")
        target = (self.target_dir / clean_dir).resolve()

        if not target.is_relative_to(self.target_dir.resolve()):
            return get_string("err_access_denied", "access denied").format(
                path=clean_dir
            )

        rel_target = str(target.relative_to(self.target_dir)).replace("\\", "/")
        if rel_target == ".":
            rel_target = ""

        if rel_target and rel_target not in self.indexer.dirs:
            return get_string("err_dir_empty", "dir empty").format(query=dir_query)

        max_depth = None
        if depth_str:
            try:
                max_depth = int(depth_str.strip())
            except ValueError:
                return get_string("err_invalid_depth", "\n\n").format(depth=depth_str)

        return self.generate_tree(rel_target, max_depth)

    async def get_symbol_content(self, query: str, symbol_name: str) -> str:
        """
        Return a formatted symbol snippet extracted from a file.

        Args:
            `query` (str): The file containing the symbol.
            `symbol_name` (str): The name of the class/method/function.

        Returns:
            `str`: Formatted symbol block.
        """
        if not symbol_name:
            return ""

        matches = self.indexer.find_matches(query)
        if not matches:
            return get_string("err_file_not_found", "file not found").format(
                query=query
            )

        meta = matches[0]
        if meta.size > self.MAX_FILE_SIZE:
            return get_string("err_file_too_large", "file too large").format(
                path=meta.rel_path
            )

        content = await self._read_cached(meta)

        from .extractor import SymbolExtractor

        try:
            extractor = SymbolExtractor(content, meta.path.name)
            extracted = extractor.extract(symbol_name)
            if not extracted:
                return get_string("symbol_not_found", "symbol not found").format(
                    symbol=symbol_name, path=meta.rel_path
                )
            return f"- `{meta.rel_path}:{symbol_name}`\n\n```{meta.ext}\n{extracted}\n```\n"
        except ValueError as err:
            return get_string("symbol_err", "symbol error").format(err=err)

    async def get_git_diff(
        self, path: str | None = None, branch: str | None = None
    ) -> str:
        """
        Return the working-tree diff for the project or a specific file.

        Args:
            `path` (str | None): Target path to isolate the diff.
            `branch` (str | None): Optional branch or ref to diff against.

        Returns:
            `str`: Git diff output.
        """
        if not self.has_git:
            return ""

        cmd = ["diff"]
        if branch:
            cmd.append(branch)
        if path:
            cmd.extend(["--", path])

        returncode, stdout, stderr = await self._run_git_command(*cmd)
        if returncode != 0:
            return get_string("git_diff_err", "git diff error").format(err=stderr)

        if not stdout.strip():
            return get_string("no_changes", "no changes")
        return f"```diff\n{stdout}\n```\n"

    async def get_git_status(self, branch: str | None = None) -> str:
        """
        Return the working-tree status. When a branch is provided, this returns a name-status comparison against that ref since `git status` does not accept revision arguments.

        Returns:
            `str`: Git status output.
        """
        if not self.has_git:
            return ""

        cmd = ["status", "-s"] if branch is None else ["diff", "--name-status", branch]
        returncode, stdout, stderr = await self._run_git_command(*cmd)
        if returncode != 0:
            return get_string("git_status_err", "git status error").format(err=stderr)

        if not stdout.strip():
            return get_string("working_tree_clean", "clean tree")
        return f"```log\n{stdout}\n```\n"

    async def get_git_log(
        self, limit: int | None = None, branch: str | None = None
    ) -> str:
        """Return the Git log for the current repository or a specific branch"""
        if not self.has_git:
            return ""

        effective_limit = self._normalize_git_commit_limit(limit, GIT_DEFAULT_LOG_LIMIT)
        cmd = ["log", "--no-color", "-n", str(effective_limit)]
        if branch:
            cmd.append(branch)

        returncode, stdout, stderr = await self._run_git_command(*cmd)
        if returncode != 0:
            return get_string("git_log_err", "git log error").format(err=stderr)

        if not stdout.strip():
            return get_string("no_changes", "no changes")
        return f"```log\n{stdout}\n```\n"

    async def get_git_history(
        self, limit: int | None = None, branch: str | None = None
    ) -> str:
        """Return recent commit history together with patches"""
        if not self.has_git:
            return ""

        effective_limit = self._normalize_git_commit_limit(
            limit, GIT_DEFAULT_HISTORY_LIMIT
        )
        cmd = [
            "log",
            "--no-color",
            "--pretty=fuller",
            "--stat",
            "--patch",
            "-n",
            str(effective_limit),
        ]
        if branch:
            cmd.append(branch)

        returncode, stdout, stderr = await self._run_git_command(*cmd)
        if returncode != 0:
            return get_string("git_history_err", "git history error").format(err=stderr)

        if not stdout.strip():
            return get_string("no_changes", "no changes")
        return f"```diff\n{stdout}\n```\n"

    async def _read_and_format(self, meta: FileMeta, range_str: str | None) -> str:
        """
        Read, validate, cache, and format a file match.

        Args:
            `meta` (FileMeta): Target file metadata.
            `range_str` (str | None): Slicing arguments.

        Returns:
            `str`: The evaluated final markdown block.
        """
        if meta.size > self.MAX_FILE_SIZE:
            return get_string("err_file_too_large", "file too large").format(
                path=meta.rel_path
            )

        if not self.is_sandboxed(meta.path):
            return get_string("err_access_denied", "access denied").format(
                path=meta.rel_path
            )

        content = await self._read_cached(meta)
        lines = content.splitlines(keepends=True)

        if range_str:
            lines, omitted = self._apply_range(lines, range_str)
            if omitted > 0:
                prefix, suffix = get_comment_syntax(meta.ext)
                notice = get_string("truncation_notice", "truncated").format(
                    prefix=prefix, omitted=omitted, suffix=suffix
                )
                lines.append(notice)

        final_content = "".join(lines)
        return f"- `{meta.rel_path}`\n\n```{meta.ext}\n{final_content}\n```\n"

    async def _format_matches(
        self,
        matches: list[FileMeta],
        range_str: str | None,
    ) -> str:
        """Read and format a list of matches through a shared task group"""
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._read_and_format(meta, range_str))
                for meta in matches
            ]

        return "\n".join(task.result() for task in tasks)

    async def _read_cached(self, meta: FileMeta) -> str:
        """
        Read file content from disk using an mtime-aware cache.

        Args:
            `meta` (FileMeta): Data object for the file to read.

        Returns:
            `str`: Unmodified text content.
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
        Apply range selectors such as `first 200`, `last 100`, `10-20`, or `#L45`.

        Args:
            `lines` (list[str]): The original array of text lines.
            `range_str` (str): The rule determining the slice limit.

        Returns:
            `tuple` [list[str], int]: Processed lines and count of omitted lines.
        """
        range_str = range_str.strip().lower()
        total = len(lines)
        err_msg = get_string("err_invalid_range", "invalid range").format(
            range=range_str
        )

        if range_str.startswith("first "):
            try:
                n = int(range_str.split()[1])
                return lines[:n], max(0, total - n)
            except ValueError:
                return lines + [err_msg], 0

        elif range_str.startswith("last "):
            try:
                n = int(range_str.split()[1])
                return lines[-n:], max(0, total - n)
            except ValueError:
                return lines + [err_msg], 0

        elif "-" in range_str:
            try:
                r = range_str.replace("#l", "").replace("l", "")
                s, e = map(int, r.split("-"))
                return lines[max(0, s - 1) : e], max(0, total - (e - max(0, s - 1)))
            except ValueError:
                return lines + [err_msg], 0

        elif range_str.startswith("#l"):
            try:
                n = int(range_str.replace("#l", ""))
                return lines[max(0, n - 1) : n], max(0, total - 1)
            except ValueError:
                return lines + [err_msg], 0

        return lines + [err_msg], 0

    def generate_tree(self, root_rel: str = "", max_depth: int | None = None) -> str:
        """
        Recreate a `TREE /F`-style view of the indexed project.

        Args:
            `root_rel` (str): Starting point inside the project for tree evaluation.
            `max_depth` (int | None): Maximum recursive folder depth to crawl.

        Returns:
            `str`: ASCII format tree.
        """
        root_rel = root_rel.replace("\\", "/").strip("/")

        if not root_rel:
            header_name = self.target_dir.name
        else:
            header_name = root_rel.split("/")[-1]

        header_root = "." if not root_rel else f"./{root_rel}"

        tree_str = [
            get_string("tree_header_1", "TREE /F"),
            get_string("tree_header_2", "Folder PATH for {name}").format(
                name=header_name
            ),
            get_string("tree_header_3", "{root}").format(root=header_root),
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
                connector = (
                    self.terminal_profile.tree.last_branch
                    if is_last
                    else self.terminal_profile.tree.branch
                )
                tree_str.append(f"{prefix}{connector}{item}")

                full_path = current_dir + item
                if full_path in self.indexer.dirs:
                    extension = (
                        self.terminal_profile.tree.spacer
                        if is_last
                        else self.terminal_profile.tree.vertical
                    )
                    _build_tree(full_path + "/", prefix + extension, current_depth + 1)

        _build_tree(search_prefix)
        content = "\n".join(tree_str)
        return f"```log\n{content}\n\n```\n"
