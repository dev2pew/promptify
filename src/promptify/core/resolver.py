"""
ASYNCHRONOUS RESOLVER LEVERAGING STRUCTURED CONCURRENCY AND A DECOUPLED MOD SYSTEM.
SYSTEM MODE OPERATES RECURSIVELY WITH LOOP PROTECTION.
USER MODE OPERATES IN A STRICT SINGLE-PASS SANDBOX.
"""

import re
import asyncio

from .context import ProjectContext
from .mods import ModRegistry
from .mods import split_file_query_and_range
from ..utils.i18n import strings


class PromptResolver:
    """
    ASYNCHRONOUS RESOLVER LEVERAGING STRUCTURED CONCURRENCY AND A DECOUPLED MOD SYSTEM.
    SYSTEM MODE OPERATES RECURSIVELY WITH LOOP PROTECTION.
    USER MODE OPERATES IN A STRICT SINGLE-PASS SANDBOX.
    """

    def __init__(self, context: ProjectContext, registry: ModRegistry):
        self.context = context
        self.registry = registry
        if self.registry.pattern is None:
            self.registry.build()
        self._estimate_cache: dict[tuple[str, str, int], int] = {}
        self._git_estimate_cache: dict[str, tuple[float, int]] = {}

    def _estimate_tree_length(
        self, root_rel: str = "", max_depth: int | None = None
    ) -> int:
        """ESTIMATES TREE OUTPUT LENGTH USING INDEXED PATHS WITHOUT BUILDING THE STRING."""
        root_rel = root_rel.replace("\\", "/").strip("/")
        if not root_rel:
            header_name = self.context.target_dir.name
        else:
            header_name = root_rel.split("/")[-1]

        lines = [
            strings.get("tree_header_1", "TREE /F"),
            strings.get("tree_header_2", "Folder PATH for {name}").format(
                name=header_name
            ),
            strings.get("tree_header_3", "C:."),
        ]
        search_prefix = root_rel + "/" if root_rel else ""
        children: set[str] = set()

        for path in self.context.indexer.files_by_rel:
            if not path.startswith(search_prefix):
                continue
            rel = path[len(search_prefix) :]
            if not rel:
                continue
            parts = rel.split("/")
            depth = len(parts)
            if max_depth is not None and depth > max_depth:
                continue
            for idx in range(depth - 1):
                children.add("/".join(parts[: idx + 1]) + "/")
            children.add(rel)

        lines.extend(sorted(children))
        return sum(len(line) + 1 for line in lines) + 1

    async def _estimate_file_length(self, query: str, range_str: str | None) -> int:
        """ESTIMATES FILE MENTION EXPANSION LENGTH, USING EXACT CACHED CONTENT WHEN NEEDED."""
        matches = self.context.indexer.find_matches(query)
        if not matches:
            return len(
                strings.get("err_file_not_found", "file not found").format(query=query)
            )

        meta = matches[0]
        if not range_str:
            return meta.size

        cache_key = ("mod_file", f"{meta.rel_path}:{range_str}", int(meta.mtime))
        if cache_key in self._estimate_cache:
            return self._estimate_cache[cache_key]

        content = await self.context._read_cached(meta)
        lines = content.splitlines(keepends=True)
        lines, omitted = self.context._apply_range(lines, range_str)
        length = sum(len(line) for line in lines)
        if omitted > 0:
            syntax = strings.get("comment_syntax", {}).get(meta.ext, ["// ", ""])
            prefix, suffix = syntax[0], syntax[1]
            notice = strings.get("truncation_notice", "truncated").format(
                prefix=prefix, omitted=omitted, suffix=suffix
            )
            length += len(notice)

        self._estimate_cache[cache_key] = length
        return length

    async def estimate_tokens(self, text: str) -> int:
        """
        CALCULATES AN ULTRA-FAST ESTIMATION OF TOKENS BASED STRICTLY ON
        SIZES PROVIDED BY THE IN-MEMORY INDEXER AND CACHED RESOLUTIONS.
        """
        matches = list(self.registry.pattern.finditer(text))
        if not matches:
            return int(len(text) // 3.2)

        base_len = len(text)
        added_len = 0

        for m in matches:
            try:
                mod, match_text = self.registry.get_mod_and_text(m)
                revision = self.context.indexer.revision

                if mod.name == "mod_file":
                    match_text = match_text.removeprefix("<@file:").removesuffix(">")
                    query, range_str = split_file_query_and_range(match_text)
                    added_len += await self._estimate_file_length(query, range_str)
                elif mod.name == "mod_dir":
                    match_path = re.match(r"<@dir:([^>]+)>", match_text)
                    if match_path:
                        clean_dir = match_path.group(1).lstrip("/\\")
                        files = [
                            f
                            for p, f in self.context.indexer.files_by_rel.items()
                            if p.startswith(clean_dir)
                        ]
                        added_len += sum(f.size for f in files)
                elif mod.name == "mod_ext":
                    match_path = re.match(r"<@(type|ext):([^>]+)>", match_text)
                    if match_path:
                        exts = list(
                            dict.fromkeys(
                                e.strip().lstrip(".").lower()
                                for e in match_path.group(2).split(",")
                            )
                        )
                        files = self.context.indexer.get_by_extensions(exts)
                        added_len += sum(f.size for f in files)
                elif mod.name == "mod_tree":
                    match_path = re.match(r"<@tree:([^>:]+?)(?::([^>]+))?>", match_text)
                    if match_path:
                        depth = match_path.group(2)
                        depth_val = (
                            int(depth.strip())
                            if depth and depth.strip().isdigit()
                            else None
                        )
                        key = ("mod_tree", match_text, revision)
                        cached = self._estimate_cache.get(key)
                        if cached is None:
                            cached = self._estimate_tree_length(
                                match_path.group(1), depth_val
                            )
                            self._estimate_cache[key] = cached
                        added_len += cached
                elif mod.name == "mod_project":
                    key = ("mod_project", match_text, revision)
                    cached = self._estimate_cache.get(key)
                    if cached is None:
                        cached = self._estimate_tree_length()
                        self._estimate_cache[key] = cached
                    added_len += cached
                elif mod.name == "mod_symbol":
                    key = ("mod_symbol", match_text, revision)
                    cached = self._estimate_cache.get(key)
                    if cached is None:
                        match_path = re.match(
                            r"<@symbol:([^>:]+?)(?::([^>]+))?>", match_text
                        )
                        if match_path:
                            symbol_content = await self.context.get_symbol_content(
                                match_path.group(1), match_path.group(2)
                            )
                            cached = len(symbol_content)
                            self._estimate_cache[key] = cached
                        else:
                            cached = 0
                    added_len += cached
                elif mod.name == "mod_git":
                    now = asyncio.get_running_loop().time()
                    if match_text in self._git_estimate_cache:
                        cached_time, cached_len = self._git_estimate_cache[match_text]
                        if now - cached_time < 5.0:
                            added_len += cached_len
                            continue

                    git_content = await mod.resolve(match_text, self.context)
                    length = len(git_content)
                    self._git_estimate_cache[match_text] = (now, length)
                    added_len += length
            except Exception:
                pass

        return int((base_len + added_len) // 3.2)

    async def resolve_system(self, text: str, seen: set[str] | None = None) -> str:
        """RECURSIVE RESOLUTION FOR SYSTEM TEMPLATES, WITH LOOP PROTECTION."""
        if seen is None:
            seen = set()

        matches = list(self.registry.pattern.finditer(text))
        if not matches:
            return text

        async def _resolve_and_recurse(m: re.Match) -> str:
            full_match = m.group(0)
            if full_match in seen:
                return strings.get("loop_detected", "loop detected").format(
                    match=full_match
                )

            branch_seen = seen.copy()
            branch_seen.add(full_match)

            resolved_content = await self._process_match(m)
            return await self.resolve_system(resolved_content, branch_seen)

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(_resolve_and_recurse(m)) for m in matches]

        replacements = [t.result() for t in tasks]

        parts: list[str] = []
        last_idx = 0
        for m, repl in zip(matches, replacements):
            parts.append(text[last_idx : m.start()])
            parts.append(repl)
            last_idx = m.end()

        parts.append(text[last_idx:])
        return "".join(parts)

    async def resolve_user(self, text: str) -> str:
        """SINGLE-PASS RESOLUTION FOR USER TEXT (INTERACTIVE EDITOR)."""
        matches = list(self.registry.pattern.finditer(text))
        if not matches:
            return text

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(self._process_match(m)) for m in matches]

        replacements = [t.result() for t in tasks]

        parts: list[str] = []
        last_idx = 0
        for m, repl in zip(matches, replacements):
            parts.append(text[last_idx : m.start()])
            parts.append(repl)
            last_idx = m.end()

        parts.append(text[last_idx:])
        return "".join(parts)

    async def _process_match(self, match: re.Match) -> str:
        """DELEGATES RESOLUTION STRICTLY TO THE CORRESPONDING MOD."""
        try:
            mod, text = self.registry.get_mod_and_text(match)
            return await mod.resolve(text, self.context)
        except Exception:
            return match.group(0)
