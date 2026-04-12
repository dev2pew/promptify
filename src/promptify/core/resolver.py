import re
import asyncio

from .core.context import ProjectContext
from .i18n import strings


class PromptResolver:
    """
    Asynchronous resolver leveraging structured concurrency.
    System mode operates recursively with loop protection.
    User mode operates in a strict single-pass sandbox.
    """

    PATTERN = re.compile(
        r"(<@(file|dir|type|ext|git|symbol):([^>:]+?)(?::([^>]+))?>|\[@project\])"
    )

    def __init__(self, context: ProjectContext):
        self.context = context

    async def resolve_system(self, text: str, seen: set[str] | None = None) -> str:
        """Recursive resolution for system templates, with loop protection."""
        if seen is None:
            seen = set()

        matches = list(self.PATTERN.finditer(text))
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
        matches = list(self.PATTERN.finditer(text))
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
        full_match = match.group(0)

        if full_match == "[@project]":
            return self.context.generate_tree()

        call_type = match.group(2)
        query = match.group(3)
        range_str = match.group(4)

        if call_type == "file":
            return await self.context.get_file_content(query, range_str)
        elif call_type == "dir":
            return await self.context.get_dir_contents(query)
        elif call_type in ("type", "ext"):
            return await self.context.get_type_contents(query)
        elif call_type == "git":
            if query == "status":
                return await self.context.get_git_status()
            elif query == "diff":
                return await self.context.get_git_diff(range_str)
        elif call_type == "symbol":
            return await self.context.get_symbol_content(query, range_str)

        return full_match
