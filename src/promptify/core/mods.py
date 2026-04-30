"""Mention modifiers and resolution plugins"""

import re
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TYPE_CHECKING
from prompt_toolkit.completion import Completion
from rapidfuzz import process, utils as fuzz_utils

from .matching import (
    build_path_display_map,
    normalize_match_path,
    rank_path_candidates,
)
from .settings import APP_SETTINGS

if TYPE_CHECKING:
    from .context import ProjectContext
    from .indexer import ProjectIndexer
    from .models import FileMeta


def fuzzy_complete(
    partial: str,
    candidates: list[str],
    prefix: str = "",
    suffix: str = ">",
    limit: int | None = None,
) -> Iterable[Completion]:
    """
    Provide fast, case-insensitive fuzzy completions.

    Args:
        `partial` (str): Currently typed text to match.
        `candidates` (list[str]): All available lookup targets.
        `prefix` (str): Prefix formatting attached on output.
        `suffix` (str): Suffix attached formatting to close out selection payload.
        `limit` (int | None): Optional size limiter for rendered completion lines.

    Yields:
        `Completion`: Processed payload prompt-toolkit completion object.
    """
    size_limit = len(candidates) if limit is None else limit

    if not partial:
        for c in sorted(candidates)[:size_limit]:
            yield Completion(prefix + c + suffix, start_position=0, display=prefix + c)
        return

    results = process.extract(
        partial,
        candidates,
        limit=size_limit,
        processor=fuzz_utils.default_process,
    )
    matched_items = [
        res[0]
        for res in results
        if res[1] > APP_SETTINGS.matching.completion_fuzzy_score_cutoff
    ] or [res[0] for res in results]
    for c in matched_items:
        yield Completion(
            prefix + c + suffix, start_position=-len(partial), display=prefix + c
        )


def build_path_completions(
    partial: str,
    candidates: list[str],
    *,
    close_suffix: str = ">",
    exact_suffixes: tuple[str, ...] = (),
    meta_candidates: set[str] | None = None,
) -> Iterable[Completion]:
    """Yield path completions with compact, disambiguated display labels"""
    normalized_partial = normalize_match_path(partial)
    ranked = rank_path_candidates(normalized_partial, candidates)
    display_map = build_path_display_map(ranked)
    start_position = -len(partial)

    for candidate in ranked:
        label, meta = display_map[candidate]
        display_meta = (
            meta if meta_candidates is None or candidate in meta_candidates else ""
        )
        if candidate == normalized_partial:
            yield Completion(
                candidate + close_suffix,
                start_position=start_position,
                display=label + close_suffix,
                display_meta="",
            )
            for suffix in exact_suffixes:
                yield Completion(
                    candidate + suffix,
                    start_position=start_position,
                    display=label + suffix,
                    display_meta="",
                )
        else:
            yield Completion(
                candidate,
                start_position=start_position,
                display=label,
                display_meta=display_meta,
            )


def build_file_path_completions(
    partial: str, indexer: "ProjectIndexer"
) -> Iterable[Completion]:
    """Yield file path completions using the standard display rules"""
    yield from build_path_completions(
        partial,
        list(indexer.files_by_rel.keys()),
        close_suffix=">",
        exact_suffixes=(":",),
        meta_candidates=set(indexer.files_by_rel),
    )


def _yield_numeric_suffix_completions(
    values: Iterable[int],
    partial: str,
    *,
    suffix: str,
) -> Iterable[Completion]:
    """Yield numeric completions matching the current partial input"""
    for value in values:
        text = str(value)
        if text.startswith(partial):
            yield Completion(
                text + suffix,
                start_position=-len(partial),
                display=text + suffix,
            )


def build_file_range_completions(
    partial: str,
    *,
    lines_count: int,
) -> Iterable[Completion]:
    """Yield range-suffix completions for `<@file:path:...>` queries"""
    if not partial:
        yield Completion("first ", start_position=0, display="first [n]")
        yield Completion("last ", start_position=0, display="last [n]")
        yield Completion("", start_position=0, display="[n]-[m]")
        yield Completion("#", start_position=0, display="#[n]")
        return

    if partial.startswith("first ") or partial.startswith("last "):
        prefix = "first " if partial.startswith("first ") else "last "
        yield from _yield_numeric_suffix_completions(
            range(1, lines_count + 1),
            partial[len(prefix) :],
            suffix=">",
        )
        return

    if partial.startswith("#"):
        yield from _yield_numeric_suffix_completions(
            range(1, lines_count + 1),
            partial[1:],
            suffix=">",
        )
        return

    if "-" in partial:
        start_num, _, num_part = partial.partition("-")
        try:
            start_idx = int(start_num)
        except ValueError:
            start_idx = 1
        yield from _yield_numeric_suffix_completions(
            range(start_idx, lines_count + 1),
            num_part,
            suffix=">",
        )
        return

    if partial.isdigit():
        yield from _yield_numeric_suffix_completions(
            range(1, lines_count + 1),
            partial,
            suffix="-",
        )
        return

    for completion, display in [("first ", "first [n]"), ("last ", "last [n]")]:
        if completion.startswith(partial):
            yield Completion(
                completion,
                start_position=-len(partial),
                display=display,
            )


def split_file_query_and_range(query: str) -> tuple[str, str | None]:
    """
    Split a file query into its relative path and optional range segment.

    Absolute paths are left intact so callers can reject them consistently.
    """
    normalized = query.replace("\\", "/")
    if re.match(r"^[a-zA-Z]:/", normalized):
        return normalized, None

    parts = normalized.split(":", 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


@dataclass(slots=True, frozen=True)
class GitMentionQuery:
    """Normalized representation of a `<@git:...>` mention"""

    branch: str | None
    command: str
    argument: str | None


GIT_BRANCH_PATTERN = r"\[(?:\\.|[^\]\\])+\]"
GIT_BRANCH_PREFIX_PATTERN = rf"(?:{GIT_BRANCH_PATTERN}:)?"
GIT_DEFAULT_LOG_LIMIT = 20
GIT_DEFAULT_HISTORY_LIMIT = 5
GIT_COMMAND_COMPLETIONS = (
    "diff>",
    "status>",
    "diff:",
    "log>",
    "log:",
    "history>",
    "history:",
)


def escape_git_branch_name(branch: str) -> str:
    """Escape branch characters that would break the mention grammar"""
    escaped: list[str] = []
    for char in branch:
        if char in {"\\", "]", ">"}:
            escaped.append("\\")
        escaped.append(char)
    return "".join(escaped)


def unescape_git_branch_name(branch: str) -> str:
    """Decode a branch name previously escaped for the Git mention grammar"""
    decoded: list[str] = []
    escaped = False
    for char in branch:
        if escaped:
            decoded.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        decoded.append(char)
    if escaped:
        decoded.append("\\")
    return "".join(decoded)


def split_git_branch_prefix(body: str) -> tuple[str | None, str | None, str] | None:
    """Split an optional bracketed branch prefix from a Git mention body"""
    if not body.startswith("["):
        return None, None, body

    branch_chars: list[str] = []
    raw_chars: list[str] = []
    escaped = False

    for index in range(1, len(body)):
        char = body[index]
        if escaped:
            branch_chars.append(char)
            raw_chars.extend(["\\", char])
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "]":
            if index + 1 >= len(body) or body[index + 1] != ":":
                return None
            return "".join(branch_chars), "".join(raw_chars), body[index + 2 :]
        branch_chars.append(char)
        raw_chars.append(char)

    return None


def parse_incomplete_git_branch_prefix(body: str) -> str | None:
    """Return the raw branch partial while the user is still typing `[branch`"""
    if not body.startswith("["):
        return None

    raw_chars: list[str] = []
    escaped = False
    for char in body[1:]:
        if escaped:
            raw_chars.extend(["\\", char])
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in {"]", ":"}:
            return None
        raw_chars.append(char)

    if escaped:
        raw_chars.append("\\")
    return "".join(raw_chars)


def parse_git_mention_query(body: str) -> GitMentionQuery | None:
    """Parse a Git mention body into branch, command, and argument parts"""
    branch, _, remainder = split_git_branch_prefix(body) or (None, None, body)
    if remainder == "status":
        return GitMentionQuery(branch=branch, command="status", argument=None)
    if remainder == "diff":
        return GitMentionQuery(branch=branch, command="diff", argument=None)
    if remainder.startswith("diff:") and remainder[5:]:
        return GitMentionQuery(branch=branch, command="diff", argument=remainder[5:])
    if remainder == "log":
        return GitMentionQuery(branch=branch, command="log", argument=None)
    if remainder.startswith("log:") and remainder[4:].isdigit():
        return GitMentionQuery(branch=branch, command="log", argument=remainder[4:])
    if remainder == "history":
        return GitMentionQuery(branch=branch, command="history", argument=None)
    if remainder.startswith("history:") and remainder[8:].isdigit():
        return GitMentionQuery(branch=branch, command="history", argument=remainder[8:])
    return None


class MentionMod(ABC):
    """Base class for customizable mention extensions"""

    name: str
    pattern: str

    @abstractmethod
    async def resolve(self, full_match_text: str, context: "ProjectContext") -> str:
        """
        Resolve a raw mention string into its target content.

        Args:
            `full_match_text` (str): Exact regex matched token.
            `context` (ProjectContext): Safe I/O reader.

        Returns:
            `str`: Materialized code snippet implementation formatting blocks.
        """
        pass

    @abstractmethod
    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        """
        Analyze text state and yield context-aware completions.

        Args:
            `text_before_cursor` (str): Full line buffer snippet.
            `indexer` (ProjectIndexer): Direct fuzzy path querying.

        Yields:
            `Completion`: Active drop-down item for standard menus.
        """
        pass


def _must_match(pattern: str, text: str) -> re.Match[str]:
    """Assert internal regex invariants for text already matched by the registry"""
    match = re.match(pattern, text)
    if match is None:
        raise ValueError(f"pattern '{pattern}' did not match '{text}'")
    return match


class ModRegistry:
    """Registry that maps loaded mention mods into the engine"""

    def __init__(self):
        """Initialize empty mod and pattern storage"""
        self.mods: list[MentionMod] = []
        self.pattern: re.Pattern | None = None

    def register(self, mod: MentionMod) -> None:
        """
        Register a new mod implementation.

        Args:
            `mod` (MentionMod): Object referencing the mod.
        """
        self.mods.append(mod)

    def register_defaults(self) -> None:
        """Load the standard suite of built-in mentions"""
        self.register(ProjectMod())
        self.register(FileMod())
        self.register(DirMod())
        self.register(TreeMod())
        self.register(ExtMod())
        self.register(GitMod())
        self.register(SymbolMod())

    def build(self) -> None:
        """Compile a multi-group regex for single-pass resolution"""
        parts = []
        for mod in self.mods:
            parts.append(f"(?P<{mod.name}>{mod.pattern})")
        self.pattern = re.compile("|".join(parts))

    def get_mod_and_text(self, match: re.Match) -> tuple[MentionMod, str]:
        """
        Translate a regex match into its corresponding mod and raw text.

        Args:
            `match` (re.Match): Regex executed context window reference.

        Returns:
            `tuple` [MentionMod, str]: Bound reference for isolated mod mapping.
        """
        for mod in self.mods:
            text = match.group(mod.name)
            if text is not None:
                return mod, text
        raise ValueError("No mod matched the given text.")

    def get_all_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        """
        Delegate completion requests to mods and handle base tags.

        Args:
            `text_before_cursor` (str): Leftward buffer token window search target.
            `indexer` (ProjectIndexer): Path provider for logic mapping.

        Yields:
            `Completion`: Processed payload prompt-toolkit completion object.
        """
        for mod in self.mods:
            yield from mod.get_completions(text_before_cursor, indexer)

        # BASE TAG COMPLETION
        match_tag = re.search(r"<@([^><:]*)$", text_before_cursor)
        if match_tag:
            partial = match_tag.group(1).lower()
            tags = [
                m.name.replace("mod_", "") + ":"
                for m in self.mods
                if m.name != "mod_project"
            ]
            for tag in tags:
                if tag.startswith(partial):
                    yield Completion(
                        tag, start_position=-len(partial), display=f"<@{tag}"
                    )

        # PROJECT COMPLETION
        match_proj = re.search(r"\[@([^\]\[]*)$", text_before_cursor)
        if match_proj:
            partial = match_proj.group(1).lower()
            if "project]".startswith(partial):
                yield Completion(
                    "project]", start_position=-len(partial), display="[@project]"
                )


# =============================================================================
# BUILT-IN MODS
# =============================================================================


class ProjectMod(MentionMod):
    """Handle `[@project]` mentions"""

    name = "mod_project"
    pattern = r"\[@project\]"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        return context.generate_tree()

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        return []


class FileMod(MentionMod):
    """Handle `<@file:path:range>` mentions"""

    name = "mod_file"
    pattern = r"<@file:([^>]+?)(?::([^>]+))?>"

    def __init__(self):
        self._lines_cache: dict[str, tuple[float, int]] = {}

    def _get_lines_count(self, meta: "FileMeta") -> int:
        cached = self._lines_cache.get(meta.rel_path)
        if cached and cached[0] == meta.mtime:
            return cached[1]
        try:
            with open(meta.path, "rb") as f:
                lines_count = sum(1 for _ in f)
            self._lines_cache[meta.rel_path] = (meta.mtime, lines_count)
            return lines_count
        except Exception:
            return 0

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = _must_match(self.pattern, text)
        return await context.get_file_content(m.group(1), m.group(2))

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_range = re.search(r"<@file:([^>:]+):([^><]*)$", text_before_cursor)
        if match_range:
            path = normalize_match_path(match_range.group(1))
            partial = match_range.group(2).lower()

            meta = indexer.files_by_rel.get(path)
            if not meta:
                return

            lines_count = self._get_lines_count(meta)
            if lines_count == 0:
                return

            yield from build_file_range_completions(partial, lines_count=lines_count)
            return

        match_path = re.search(r"<@file:([^><]*)$", text_before_cursor)
        if match_path:
            yield from build_file_path_completions(match_path.group(1), indexer)


class DirMod(MentionMod):
    """Handle `<@dir:path>` mentions"""

    name = "mod_dir"
    pattern = r"<@dir:([^>]+)>"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = _must_match(self.pattern, text)
        return await context.get_dir_contents(m.group(1))

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_path = re.search(r"<@dir:([^><]*)$", text_before_cursor)
        if match_path:
            yield from build_path_completions(
                match_path.group(1),
                list(indexer.dirs),
                meta_candidates=set(),
            )


class TreeMod(MentionMod):
    """Handle `<@tree:path:level>` mentions"""

    name = "mod_tree"
    pattern = r"<@tree:([^>:]+?)(?::([^>]+))?>"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = _must_match(self.pattern, text)
        return await context.get_tree_contents(m.group(1), m.group(2))

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_depth = re.search(r"<@tree:([^>:]+):([^><]*)$", text_before_cursor)
        if match_depth:
            path = match_depth.group(1)
            partial = match_depth.group(2)

            # IDENTIFY MAX AVAILABLE DEPTH FOR THE PATH IN REAL-TIME
            clean_dir = path.replace("\\", "/").strip("/")
            max_depth = 1
            for d in indexer.dirs:
                if d.startswith(clean_dir):
                    rel = d[len(clean_dir) :].strip("/")
                    if rel:
                        depth = rel.count("/") + 2
                        if depth > max_depth:
                            max_depth = depth

            candidates = [str(i) for i in range(1, max_depth + 1)]

            if not partial:
                for c in candidates:
                    yield Completion(c + ">", start_position=0, display=c)
                return

            yield from fuzzy_complete(partial, candidates, suffix=">")
            return

        match_path = re.search(r"<@tree:([^><]*)$", text_before_cursor)
        if match_path:
            partial = match_path.group(1)

            if not partial:
                yield from build_path_completions(
                    "",
                    list(indexer.dirs),
                    close_suffix=">",
                    exact_suffixes=(":",),
                    meta_candidates=set(),
                )
                return

            yield from build_path_completions(
                partial,
                list(indexer.dirs),
                close_suffix=">",
                exact_suffixes=(":",),
                meta_candidates=set(),
            )


class ExtMod(MentionMod):
    """Handle bulk extension queries such as `<@ext:csv_list>`"""

    name = "mod_ext"
    pattern = r"<@(type|ext):([^>]+)>"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = _must_match(self.pattern, text)
        return await context.get_type_contents(m.group(2))

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_path = re.search(r"<@(type|ext):([^><]*)$", text_before_cursor)
        if match_path:
            parts = match_path.group(2).split(",")
            current_val = parts[-1]
            added_exts = {p.strip().lower() for p in parts[:-1]}
            candidates = [
                c for c in indexer.get_all_extensions() if c.lower() not in added_exts
            ]
            yield from fuzzy_complete(current_val, candidates, suffix=",")


class GitMod(MentionMod):
    """Handle Git mentions for status, diff, log, and history views"""

    name = "mod_git"
    pattern = (
        rf"<@git:{GIT_BRANCH_PREFIX_PATTERN}"
        r"(?:status|diff(?:[:][^>]+)?|log(?:[:]\d+)?|history(?:[:]\d+)?)>"
    )

    def __init__(self) -> None:
        ttl = APP_SETTINGS.resolver.git_estimate_cache_ttl
        self._git_cache_ttl = max(0.5, ttl)
        self._branch_cache: dict[str, tuple[float, list[str]]] = {}
        self._commit_count_cache: dict[tuple[str, str | None], tuple[float, int]] = {}

    def _run_git_completion_command(
        self, repo_root: Path, *args: str
    ) -> tuple[int, str, str]:
        """Run a non-interactive Git command for completion data"""
        try:
            proc = subprocess.run(
                ["git", "--no-pager", *args],
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError:
            return 1, "", ""
        return proc.returncode, proc.stdout, proc.stderr.strip()

    def _read_git_branches(self, repo_root: Path) -> list[str]:
        """Return local branch names cached for a short TTL"""
        cache_key = str(repo_root.resolve())
        cached = self._branch_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._git_cache_ttl:
            return cached[1]

        returncode, stdout, _ = self._run_git_completion_command(
            repo_root,
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads",
        )
        branches = (
            sorted({line.strip() for line in stdout.splitlines() if line.strip()})
            if returncode == 0
            else []
        )
        self._branch_cache[cache_key] = (now, branches)
        return branches

    def _read_git_commit_count(self, repo_root: Path, branch: str | None) -> int:
        """Return the live commit count for `HEAD` or a provided branch"""
        cache_key = (str(repo_root.resolve()), branch)
        cached = self._commit_count_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._git_cache_ttl:
            return cached[1]

        target = branch or "HEAD"
        returncode, stdout, _ = self._run_git_completion_command(
            repo_root, "rev-list", "--count", target
        )
        try:
            count = int(stdout.strip()) if returncode == 0 else 0
        except ValueError:
            count = 0
        self._commit_count_cache[cache_key] = (now, count)
        return count

    def _yield_git_branch_placeholder(self, partial: str) -> Iterable[Completion]:
        """Suggest the branch placeholder before any command is chosen"""
        suggestion = "[branch]"
        if suggestion.startswith(partial.lower()):
            yield Completion("[", start_position=-len(partial), display=suggestion)

    def _yield_git_branch_completions(
        self, partial: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        """Suggest branch names after the user types `<@git:[`"""
        partial_decoded = unescape_git_branch_name(partial)
        for branch in self._read_git_branches(indexer.target_dir):
            if partial_decoded and partial_decoded not in branch:
                continue
            escaped_branch = escape_git_branch_name(branch)
            yield Completion(
                escaped_branch + "]:",
                start_position=-len(partial),
                display=f"[{branch}]",
            )

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        body = text.removeprefix("<@git:").removesuffix(">")
        query = parse_git_mention_query(body)
        if query is None:
            return text
        if query.command == "status":
            return await context.get_git_status(query.branch)
        if query.command == "diff":
            return await context.get_git_diff(query.argument, query.branch)
        if query.command == "log":
            limit = int(query.argument) if query.argument is not None else None
            return await context.get_git_log(limit=limit, branch=query.branch)
        if query.command == "history":
            limit = int(query.argument) if query.argument is not None else None
            return await context.get_git_history(limit=limit, branch=query.branch)
        return text

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_git_body = re.search(r"<@git:([^><]*)$", text_before_cursor)
        git_body = match_git_body.group(1) if match_git_body else None
        if git_body is not None:
            branch_partial = parse_incomplete_git_branch_prefix(git_body)
            if branch_partial is not None:
                yield from self._yield_git_branch_completions(branch_partial, indexer)
                return

        match_git_diff = re.search(
            rf"<@git:{GIT_BRANCH_PREFIX_PATTERN}diff:([^><]*)$", text_before_cursor
        )
        if match_git_diff:
            candidates = list(indexer.files_by_rel.keys()) + list(indexer.dirs)
            yield from build_path_completions(
                match_git_diff.group(1),
                candidates,
                meta_candidates=set(indexer.files_by_rel),
            )
            return

        match_git_log = re.search(
            rf"<@git:{GIT_BRANCH_PREFIX_PATTERN}(log|history):(\d*)$",
            text_before_cursor,
        )
        if match_git_log:
            body = text_before_cursor.split("<@git:", 1)[1]
            branch, _, _ = split_git_branch_prefix(body) or (None, None, body)
            commit_count = self._read_git_commit_count(indexer.target_dir, branch)
            yield from _yield_numeric_suffix_completions(
                range(1, commit_count + 1),
                match_git_log.group(2),
                suffix=">",
            )
            return

        if git_body is not None:
            partial = git_body.lower()
            if (
                ":" not in partial
                and parse_incomplete_git_branch_prefix(git_body) is None
            ):
                yield from self._yield_git_branch_placeholder(partial)

        match_git = re.search(
            rf"<@git:{GIT_BRANCH_PREFIX_PATTERN}([^><:]*)$", text_before_cursor
        )
        if match_git:
            partial = match_git.group(1).lower()
            for c in GIT_COMMAND_COMPLETIONS:
                if c.startswith(partial):
                    yield Completion(c, start_position=-len(partial), display=c)


class SymbolMod(MentionMod):
    """Handle symbol mentions by extracting nested references"""

    name = "mod_symbol"
    pattern = r"<@symbol:([^>:]+?)(?::([^>]+))?>"

    def __init__(self):
        self._symbol_cache: dict[str, tuple[float, list[str]]] = {}

    def _get_symbols_for_file(self, meta: "FileMeta") -> list[str]:
        cached = self._symbol_cache.get(meta.rel_path)
        if cached and cached[0] == meta.mtime:
            return cached[1]
        try:
            with open(meta.path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            from .extractor import SymbolExtractor

            extractor = SymbolExtractor(content, meta.path.name)
            symbols = list(extractor.symbols.keys())
            self._symbol_cache[meta.rel_path] = (meta.mtime, symbols)
            return symbols
        except Exception:
            return []

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = _must_match(self.pattern, text)
        return await context.get_symbol_content(m.group(1), m.group(2))

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_path = re.search(r"<@symbol:([^><]*)$", text_before_cursor)
        if match_path:
            parts = match_path.group(1).split(":", 1)
            if len(parts) == 1:
                yield from build_path_completions(
                    parts[0],
                    list(indexer.files_by_rel.keys()),
                    close_suffix=":",
                    meta_candidates=set(indexer.files_by_rel),
                )
            elif len(parts) == 2:
                meta = indexer.files_by_rel.get(normalize_match_path(parts[0]))
                if meta:
                    symbols = self._get_symbols_for_file(meta)
                    yield from fuzzy_complete(parts[1], symbols)
