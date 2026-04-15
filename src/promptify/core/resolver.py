import re
import asyncio

from .context import ProjectContext
from .mods import ModRegistry
from ..utils.i18n import strings


class PromptResolver:
    """
    Asynchronous resolver leveraging structured concurrency and a decoupled Mod System.
    System mode operates recursively with loop protection.
    User mode operates in a strict single-pass sandbox.
    """

    def __init__(self, context: ProjectContext, registry: ModRegistry):
        self.context = context
        self.registry = registry
        if self.registry.pattern is None:
            self.registry.build()

    async def estimate_tokens(self, text: str) -> int:
        """
        Calculates an ultra-fast estimation of tokens based strictly on
        sizes provided by the in-memory indexer without executing full file reads.
        """
        matches = list(self.registry.pattern.finditer(text))
        if not matches:
            return int(len(text) // 3.2)

        base_len = len(text)
        added_len = 0

        for m in matches:
            try:
                mod, _ = self.registry.get_mod_and_text(m)

                if mod.name == "mod_file":
                    match_path = re.match(r"<@file:([^>:]+)", m.group(0))
                    if match_path:
                        files = self.context.indexer.find_matches(match_path.group(1))
                        if files:
                            added_len += files[0].size
                elif mod.name == "mod_dir":
                    match_path = re.match(r"<@dir:([^>]+)>", m.group(0))
                    if match_path:
                        clean_dir = match_path.group(1).lstrip("/\\")
                        files = [
                            f
                            for p, f in self.context.indexer.files_by_rel.items()
                            if p.startswith(clean_dir)
                        ]
                        added_len += sum(f.size for f in files)
                elif mod.name == "mod_ext":
                    match_path = re.match(r"<@(type|ext):([^>]+)>", m.group(0))
                    if match_path:
                        exts = list(
                            dict.fromkeys(
                                e.strip().lstrip(".").lower()
                                for e in match_path.group(2).split(",")
                            )
                        )
                        files = self.context.indexer.get_by_extensions(exts)
                        added_len += sum(f.size for f in files)
                elif mod.name in ("mod_tree", "mod_project"):
                    added_len += len(self.context.indexer.files_by_rel) * 45
                elif mod.name == "mod_symbol":
                    match_path = re.match(r"<@symbol:([^>:]+)", m.group(0))
                    if match_path:
                        files = self.context.indexer.find_matches(match_path.group(1))
                        if files:
                            added_len += files[0].size // 4
            except Exception:
                pass

        return int((base_len + added_len) // 3.2)

    async def resolve_system(self, text: str, seen: set[str] | None = None) -> str:
        """Recursive resolution for system templates, with loop protection."""
        if seen is None:
            seen = set()

        matches = list(self.registry.pattern.finditer(text))
        if not matches:
            return text

        async def _resolve_and_recurse(m: re.Match) -> str:
            full_match = m.group(0)
            if full_match in seen:
                return strings["loop_detected"].format(match=full_match)

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
        """Single-pass resolution for user text (interactive editor)."""
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
        """Delegates resolution strictly to the corresponding Mod."""
        try:
            mod, text = self.registry.get_mod_and_text(match)
            return await mod.resolve(text, self.context)
        except Exception:
            return match.group(0)
