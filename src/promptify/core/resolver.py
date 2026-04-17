"""
ASYNCHRONOUS RESOLVER LEVERAGING STRUCTURED CONCURRENCY AND A DECOUPLED MOD SYSTEM.
SYSTEM MODE OPERATES RECURSIVELY WITH LOOP PROTECTION.
USER MODE OPERATES IN A STRICT SINGLE-PASS SANDBOX.
"""

import re
import asyncio

from .context import ProjectContext
from .mods import ModRegistry
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
        self._estimate_cache: dict[str, tuple[float, int]] = {}

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

                if mod.name == "mod_file":
                    match_path = re.match(r"<@file:([^>:]+?)(?::([^>]+))?>", match_text)
                    if match_path:
                        files = self.context.indexer.find_matches(match_path.group(1))
                        if files:
                            meta = files[0]
                            range_str = match_path.group(2)
                            if range_str:
                                content = await self.context._read_cached(meta)
                                lines = content.splitlines(keepends=True)
                                lines, _ = self.context._apply_range(lines, range_str)
                                added_len += sum(len(line) for line in lines)
                            else:
                                added_len += meta.size
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
                        tree_str = await self.context.get_tree_contents(
                            match_path.group(1), match_path.group(2)
                        )
                        added_len += len(tree_str)
                elif mod.name == "mod_project":
                    tree_str = self.context.generate_tree()
                    added_len += len(tree_str)
                elif mod.name == "mod_symbol":
                    match_path = re.match(
                        r"<@symbol:([^>:]+?)(?::([^>]+))?>", match_text
                    )
                    if match_path:
                        symbol_content = await self.context.get_symbol_content(
                            match_path.group(1), match_path.group(2)
                        )
                        added_len += len(symbol_content)
                elif mod.name == "mod_git":
                    now = asyncio.get_running_loop().time()
                    if match_text in self._estimate_cache:
                        cached_time, cached_len = self._estimate_cache[match_text]
                        if now - cached_time < 5.0:
                            added_len += cached_len
                            continue

                    git_content = await mod.resolve(match_text, self.context)
                    length = len(git_content)
                    self._estimate_cache[match_text] = (now, length)
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
