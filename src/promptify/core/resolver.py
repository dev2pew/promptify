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
