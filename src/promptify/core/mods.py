"""
MENTION MODIFIERS AND RESOLUTION ENGINE PLUGINS.
DEFINES HOW SPECIFIC TAGS (LIKE <@FILE:...> OR <@GIT:...>) ARE PARSED AND RESOLVED.
"""

import re
from abc import ABC, abstractmethod
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
    HELPER TO PROVIDE FAST, CASE-INSENSITIVE FUZZY COMPLETIONS.

    Args:
        partial (str): Currently typed text to match.
        candidates (list[str]): All available lookup targets.
        prefix (str): Prefix formatting attached on output.
        suffix (str): Suffix attached formatting to close out selection payload.
        limit (int | None): Optional size limiter for rendered completion lines.

    Yields:
        Completion: Processed payload prompt-toolkit completion object.
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
    """YIELDS PATH COMPLETIONS WITH COMPACT, DISAMBIGUATED DISPLAY LABELS."""
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
    """YIELDS FILE PATH COMPLETIONS USING THE STANDARD DISPLAY RULES."""
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
    """YIELDS NUMERIC COMPLETIONS MATCHING THE CURRENT PARTIAL INPUT."""
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
    """YIELDS RANGE-SUFFIX COMPLETIONS FOR `<@file:path:...>` QUERIES."""
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
    SPLITS A FILE QUERY INTO ITS RELATIVE PATH AND OPTIONAL RANGE SEGMENT.

    ABSOLUTE PATHS ARE LEFT INTACT SO CALLERS CAN REJECT THEM CONSISTENTLY.
    """
    normalized = query.replace("\\", "/")
    if re.match(r"^[a-zA-Z]:/", normalized):
        return normalized, None

    parts = normalized.split(":", 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


class MentionMod(ABC):
    """BASE CLASS FOR BUILDING CUSTOMIZABLE MENTION EXTENSIONS (MODS)."""

    name: str
    pattern: str

    @abstractmethod
    async def resolve(self, full_match_text: str, context: "ProjectContext") -> str:
        """
        RESOLVES THE RAW MENTION STRING INTO ITS TARGET CONTENT.

        Args:
            full_match_text (str): Exact regex matched token.
            context (ProjectContext): Safe I/O reader.

        Returns:
            str: Materialized code snippet implementation formatting blocks.
        """
        pass

    @abstractmethod
    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        """
        ANALYZES TEXT STATE TO YIELD CONTEXT-AWARE COMPLETIONS.

        Args:
            text_before_cursor (str): Full line buffer snippet.
            indexer (ProjectIndexer): Direct fuzzy path querying.

        Yields:
            Completion: Active drop-down item for standard menus.
        """
        pass


def _must_match(pattern: str, text: str) -> re.Match[str]:
    """ASSERTS INTERNAL MOD REGEX INVARIANTS FOR TEXT ALREADY MATCHED BY THE REGISTRY."""
    match = re.match(pattern, text)
    if match is None:
        raise ValueError(f"pattern '{pattern}' did not match '{text}'")
    return match


class ModRegistry:
    """CENTRAL REGISTRY MAPPING DYNAMICALLY LOADED MENTION MODS TO THE ENGINE."""

    def __init__(self):
        """INITIALIZES EMPTY MAPS."""
        self.mods: list[MentionMod] = []
        self.pattern: re.Pattern | None = None

    def register(self, mod: MentionMod) -> None:
        """
        PUSHES A NEW CUSTOM MOD IMPLEMENTATION INTO STANDARD QUEUES.

        Args:
            mod (MentionMod): Object referencing the mod.
        """
        self.mods.append(mod)

    def register_defaults(self) -> None:
        """LOADS THE STANDARD SUITE OF BUILT-IN MENTIONS."""
        self.register(ProjectMod())
        self.register(FileMod())
        self.register(DirMod())
        self.register(TreeMod())
        self.register(ExtMod())
        self.register(GitMod())
        self.register(SymbolMod())

    def build(self) -> None:
        """COMPILES AN O(N) MULTI-GROUP REGEX FOR ULTRA-FAST SINGLE PASS RESOLUTION."""
        parts = []
        for mod in self.mods:
            parts.append(f"(?P<{mod.name}>{mod.pattern})")
        self.pattern = re.compile("|".join(parts))

    def get_mod_and_text(self, match: re.Match) -> tuple[MentionMod, str]:
        """
        TRANSLATES MATCH OUTPUTS INTO ISOLATED MODULAR OPERATIONS.

        Args:
            match (re.Match): Regex executed context window reference.

        Returns:
            tuple[MentionMod, str]: Bound reference for isolated mod mapping.
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
        DELEGATES COMPLETION REQUESTS TO MODS, AND HANDLES BASE TAGS.

        Args:
            text_before_cursor (str): Leftward buffer token window search target.
            indexer (ProjectIndexer): Path provider for logic mapping.

        Yields:
            Completion: Processed payload prompt-toolkit completion object.
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
    """PARSES AND HANDLES [@PROJECT] GLOBAL DIRECTORY TREE OUTPUT INSTRUCTIONS."""

    name = "mod_project"
    pattern = r"\[@project\]"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        return context.generate_tree()

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        return []


class FileMod(MentionMod):
    """PROCESSES <@FILE:PATH:RANGE> STRUCTURES RESOLVING STANDARD FILE REQUESTS."""

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
    """ATTACHES ALL INTERNAL RECURSIVE FILE RESOURCES CONTAINED IN <@DIR:PATH>."""

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
    """LOCATES EXPLICIT SPECIFIC PATH MAP MAPPING TREE LOGIC INSIDE <@TREE:PATH:LEVEL>."""

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
    """PROCESSES BULK FORMAT TARGETING OPERATIONS VIA THE <@EXT:CSV_LIST> INSTRUCTION."""

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
    """FETCHES REAL-TIME STATUS AND WORKING TREE MODIFICATIONS NATIVELY USING GIT."""

    name = "mod_git"
    pattern = r"<@git:([^>:]+?)(?::([^>]+))?>"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = _must_match(self.pattern, text)
        query = m.group(1)
        path = m.group(2)
        if query == "status":
            return await context.get_git_status()
        elif query == "diff":
            return await context.get_git_diff(path)
        return text

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_git_diff = re.search(r"<@git:diff:([^><]*)$", text_before_cursor)
        if match_git_diff:
            candidates = list(indexer.files_by_rel.keys()) + list(indexer.dirs)
            yield from build_path_completions(
                match_git_diff.group(1),
                candidates,
                meta_candidates=set(indexer.files_by_rel),
            )
            return

        match_git = re.search(r"<@git:([^><:]*)$", text_before_cursor)
        if match_git:
            partial = match_git.group(1).lower()
            for c in ["diff>", "status>", "diff:"]:
                if c.startswith(partial):
                    yield Completion(c, start_position=-len(partial), display=c)


class SymbolMod(MentionMod):
    """INVOKES AST EXTRACTION PROCESSES PARSING NESTED REFERENCES."""

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
