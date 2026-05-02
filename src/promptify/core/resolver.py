"""Asynchronous mention resolution built on structured concurrency"""

import re
import asyncio
from hashlib import blake2b

from .context import ProjectContext, get_comment_syntax
from .mods import ModRegistry
from .mods import split_file_query_and_range
from .settings import APP_SETTINGS
from .token_counter import AsyncTokenCounter
from ..utils.i18n import get_string


class PromptResolver:
    """
    Resolve `promptify` mentions through a decoupled mod system.

    System mode resolves recursively with loop protection. User mode resolves in
    a strict single pass.
    """

    def __init__(self, context: ProjectContext, registry: ModRegistry):
        self.context = context
        self.registry = registry
        if self.registry.pattern is None:
            self.registry.build()
        self._estimate_cache: dict[tuple[str, str, int], int] = {}
        self._git_estimate_cache: dict[str, tuple[float, int]] = {}
        self._advanced_count_cache: dict[tuple[bytes, int], int] = {}
        self._resolved_token_match_cache: dict[tuple[str, str, int], str] = {}
        self._token_counter = AsyncTokenCounter(
            APP_SETTINGS.resolver.advanced_tokenizer_enabled
        )

    def _get_registry_pattern(self) -> re.Pattern[str]:
        """Return the compiled mod regex, building it if needed"""
        if self.registry.pattern is None:
            self.registry.build()
        if self.registry.pattern is None:
            raise RuntimeError("mod registry pattern was not initialized")
        return self.registry.pattern

    def _estimate_tree_length(
        self, root_rel: str = "", max_depth: int | None = None
    ) -> int:
        """Estimate tree output length without building the full string"""
        root_rel = root_rel.replace("\\", "/").strip("/")
        if not root_rel:
            header_name = self.context.target_dir.name
        else:
            header_name = root_rel.split("/")[-1]

        lines = [
            get_string("tree_header_1", "TREE /F"),
            get_string("tree_header_2", "Folder PATH for {name}").format(
                name=header_name
            ),
            get_string("tree_header_3", "C:."),
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
        """Estimate file mention expansion length, using cached content when needed"""
        matches = self.context.indexer.find_matches(query)
        if not matches:
            return len(
                get_string("err_file_not_found", "file not found").format(query=query)
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
            prefix, suffix = get_comment_syntax(meta.ext)
            notice = get_string("truncation_notice", "truncated").format(
                prefix=prefix, omitted=omitted, suffix=suffix
            )
            length += len(notice)

        self._estimate_cache[cache_key] = length
        return length

    async def estimate_tokens(self, text: str) -> int:
        """Estimate token count from indexed sizes and cached resolutions"""
        matches = list(self._get_registry_pattern().finditer(text))
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
                        if (
                            now - cached_time
                            < APP_SETTINGS.resolver.git_estimate_cache_ttl
                        ):
                            added_len += cached_len
                            continue

                    git_content = await mod.resolve(match_text, self.context)
                    length = len(git_content)
                    self._git_estimate_cache[match_text] = (now, length)
                    added_len += length
            except Exception:
                pass

        return int((base_len + added_len) // 3.2)

    async def count_tokens(self, text: str) -> int:
        """Count tokens using the configured exact or heuristic strategy"""
        if not self._token_counter.is_enabled:
            return await self.estimate_tokens(text)

        revision = self.context.indexer.revision
        cache_key = (self._fingerprint_text(text), revision)
        cached = self._advanced_count_cache.get(cache_key)
        if cached is not None:
            return cached

        rendered = await self._resolve_matches_once(text)
        try:
            count = await self._token_counter.count(rendered)
        except RuntimeError:
            count = int(len(rendered) // 3.2)
        self._advanced_count_cache[cache_key] = count
        if len(self._advanced_count_cache) > 32:
            oldest = next(iter(self._advanced_count_cache))
            self._advanced_count_cache.pop(oldest, None)
        return count

    def _fingerprint_text(self, text: str) -> bytes:
        """Create a compact cache key for rendered-token counts"""
        return blake2b(text.encode("utf-8"), digest_size=16).digest()

    async def _resolve_matches_once(self, text: str) -> str:
        """Resolve a single user-facing pass for exact token counting"""
        matches = list(self._get_registry_pattern().finditer(text))
        if not matches:
            return text
        return await self._replace_matches(
            text, matches, self._process_match_for_tokens
        )

    async def _process_match_for_tokens(self, match: re.Match[str]) -> str:
        """Resolve token-count mentions through a cache for unchanged expansions"""
        try:
            mod, text = self.registry.get_mod_and_text(match)
        except Exception:
            return match.group(0)

        if mod.name == "mod_git":
            return await self._process_match(match)

        cache_key = (mod.name, text, self.context.indexer.revision)
        cached = self._resolved_token_match_cache.get(cache_key)
        if cached is not None:
            return cached

        resolved = await mod.resolve(text, self.context)
        self._resolved_token_match_cache[cache_key] = resolved
        if len(self._resolved_token_match_cache) > 128:
            oldest = next(iter(self._resolved_token_match_cache))
            self._resolved_token_match_cache.pop(oldest, None)
        return resolved

    async def _replace_matches(
        self,
        text: str,
        matches: list[re.Match[str]],
        resolver,
    ) -> str:
        """Resolve matches concurrently and stitch them back into the text"""
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(resolver(m)) for m in matches]

        replacements = [t.result() for t in tasks]
        return self._apply_replacements(text, matches, replacements)

    def _apply_replacements(
        self,
        text: str,
        matches: list[re.Match[str]],
        replacements: list[str],
    ) -> str:
        """Join replacement segments without rebuilding the matching logic"""
        parts: list[str] = []
        last_idx = 0
        for m, repl in zip(matches, replacements):
            parts.append(text[last_idx : m.start()])
            parts.append(repl)
            last_idx = m.end()

        parts.append(text[last_idx:])
        return "".join(parts)

    async def resolve_system(self, text: str, seen: set[str] | None = None) -> str:
        """Resolve system templates recursively with loop protection"""
        if seen is None:
            seen = set()

        matches = list(self._get_registry_pattern().finditer(text))
        if not matches:
            return text

        async def _resolve_and_recurse(m: re.Match) -> str:
            full_match = m.group(0)
            if full_match in seen:
                return get_string("loop_detected", "loop detected").format(
                    match=full_match
                )

            branch_seen = seen.copy()
            branch_seen.add(full_match)

            resolved_content = await self._process_match(m)
            return await self.resolve_system(resolved_content, branch_seen)

        return await self._replace_matches(text, matches, _resolve_and_recurse)

    async def resolve_user(self, text: str) -> str:
        """Resolve user text in a single pass"""
        return await self._resolve_matches_once(text)

    async def _process_match(self, match: re.Match) -> str:
        """Delegate a single regex match to the corresponding mod"""
        try:
            mod, text = self.registry.get_mod_and_text(match)
            return await mod.resolve(text, self.context)
        except Exception:
            return match.group(0)
