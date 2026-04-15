"""
Mention modifiers and resolution engine plugins.
Defines how specific tags (like <@file:...> or <@git:...>) are parsed and resolved.
"""

import re
from abc import ABC, abstractmethod
from typing import Iterable, TYPE_CHECKING
from prompt_toolkit.completion import Completion
from rapidfuzz import process, utils as fuzz_utils

if TYPE_CHECKING:
    from .context import ProjectContext
    from .indexer import ProjectIndexer
    from .models import FileMeta


def fuzzy_complete(
    partial: str,
    candidates: list[str],
    prefix: str = "",
    suffix: str = ">",
    limit: int = 15,
) -> Iterable[Completion]:
    """
    Helper to provide fast, case-insensitive fuzzy completions.

    Args:
        partial (str): Currently typed text to match.
        candidates (list[str]): All available lookup targets.
        prefix (str): Prefix formatting attached on output.
        suffix (str): Suffix attached formatting to close out selection payload.
        limit (int): Size limiter for rendered completion lines.

    Yields:
        Completion: Processed payload prompt-toolkit completion object.
    """
    if not partial:
        for c in sorted(candidates)[:limit]:
            yield Completion(prefix + c + suffix, start_position=0, display=prefix + c)
        return

    results = process.extract(
        partial, candidates, limit=limit, processor=fuzz_utils.default_process
    )
    matched_items = [res[0] for res in results if res[1] > 40] or [
        res[0] for res in results
    ]
    for c in matched_items:
        yield Completion(
            prefix + c + suffix, start_position=-len(partial), display=prefix + c
        )


class MentionMod(ABC):
    """Base class for building customizable Mention Extensions (Mods)."""

    name: str
    pattern: str

    @abstractmethod
    async def resolve(self, full_match_text: str, context: "ProjectContext") -> str:
        """
        Resolves the raw mention string into its target content.

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
        Analyzes text state to yield context-aware completions.

        Args:
            text_before_cursor (str): Full line buffer snippet.
            indexer (ProjectIndexer): Direct fuzzy path querying.

        Yields:
            Completion: Active drop-down item for standard menus.
        """
        pass


class ModRegistry:
    """Central registry mapping dynamically loaded Mention Mods to the engine."""

    def __init__(self):
        """Initializes empty maps."""
        self.mods: list[MentionMod] = []
        self.pattern: re.Pattern | None = None

    def register(self, mod: MentionMod) -> None:
        """
        Pushes a new custom Mod implementation into standard queues.

        Args:
            mod (MentionMod): Object referencing the mod.
        """
        self.mods.append(mod)

    def register_defaults(self) -> None:
        """Loads the standard suite of built-in mentions."""
        self.register(ProjectMod())
        self.register(FileMod())
        self.register(DirMod())
        self.register(TreeMod())
        self.register(ExtMod())
        self.register(GitMod())
        self.register(SymbolMod())

    def build(self) -> None:
        """Compiles an O(N) multi-group Regex for ultra-fast single pass resolution."""
        parts = []
        for mod in self.mods:
            parts.append(f"(?P<{mod.name}>{mod.pattern})")
        self.pattern = re.compile("|".join(parts))

    def get_mod_and_text(self, match: re.Match) -> tuple[MentionMod, str]:
        """
        Translates match outputs into isolated modular operations.

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
        Delegates completion requests to mods, and handles base tags.

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
    """Parses and handles [@project] global directory tree output instructions."""

    name = "mod_project"
    pattern = r"\[@project\]"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        return context.generate_tree()

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        return []


class FileMod(MentionMod):
    """Processes <@file:path:range> structures resolving standard file requests."""

    name = "mod_file"
    pattern = r"<@file:([^>:]+?)(?::([^>]+))?>"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = re.match(self.pattern, text)
        return await context.get_file_content(m.group(1), m.group(2))

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_range = re.search(r"<@file:([^>:]+):([^><]*)$", text_before_cursor)
        if match_range:
            meta = indexer.files_by_rel.get(match_range.group(1))
            if meta:
                try:
                    with open(meta.path, "rb") as f:
                        lines = sum(1 for _ in f)
                    yield Completion(
                        "",
                        start_position=0,
                        display=f"[{lines} lines available]",
                    )
                except Exception:
                    pass
            return

        match_path = re.search(r"<@file:([^><]*)$", text_before_cursor)
        if match_path:
            yield from fuzzy_complete(
                match_path.group(1), list(indexer.files_by_rel.keys())
            )


class DirMod(MentionMod):
    """Attaches all internal recursive file resources contained in <@dir:path>."""

    name = "mod_dir"
    pattern = r"<@dir:([^>]+)>"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = re.match(self.pattern, text)
        return await context.get_dir_contents(m.group(1))

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_path = re.search(r"<@dir:([^><]*)$", text_before_cursor)
        if match_path:
            yield from fuzzy_complete(match_path.group(1), list(indexer.dirs))


class TreeMod(MentionMod):
    """Locates explicit specific path map mapping tree logic inside <@tree:path>."""

    name = "mod_tree"
    pattern = r"<@tree:([^>]+)>"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = re.match(self.pattern, text)
        return await context.get_tree_contents(m.group(1))

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_path = re.search(r"<@tree:([^><]*)$", text_before_cursor)
        if match_path:
            yield from fuzzy_complete(match_path.group(1), list(indexer.dirs))


class ExtMod(MentionMod):
    """Processes bulk format targeting operations via the <@ext:csv_list> instruction."""

    name = "mod_ext"
    pattern = r"<@(type|ext):([^>]+)>"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = re.match(self.pattern, text)
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
    """Fetches real-time status and working tree modifications natively using Git."""

    name = "mod_git"
    pattern = r"<@git:([^>:]+?)(?::([^>]+))?>"

    async def resolve(self, text: str, context: "ProjectContext") -> str:
        m = re.match(self.pattern, text)
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
            yield from fuzzy_complete(match_git_diff.group(1), candidates)
            return

        match_git = re.search(r"<@git:([^><:]*)$", text_before_cursor)
        if match_git:
            partial = match_git.group(1).lower()
            for c in ["diff>", "status>", "diff:"]:
                if c.startswith(partial):
                    yield Completion(c, start_position=-len(partial), display=c)


class SymbolMod(MentionMod):
    """Invokes AST extraction processes parsing nested references."""

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
        m = re.match(self.pattern, text)
        return await context.get_symbol_content(m.group(1), m.group(2))

    def get_completions(
        self, text_before_cursor: str, indexer: "ProjectIndexer"
    ) -> Iterable[Completion]:
        match_path = re.search(r"<@symbol:([^><]*)$", text_before_cursor)
        if match_path:
            parts = match_path.group(1).split(":", 1)
            if len(parts) == 1:
                yield from fuzzy_complete(
                    parts[0], list(indexer.files_by_rel.keys()), suffix=":"
                )
            elif len(parts) == 2:
                meta = indexer.files_by_rel.get(parts[0])
                if meta:
                    symbols = self._get_symbols_for_file(meta)
                    yield from fuzzy_complete(parts[1], symbols)
