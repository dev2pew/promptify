import re
import asyncio
from context import ProjectContext

class PromptResolver:
    """
    Asynchronous resolver leveraging structured concurrency.
    Runs exactly ONE pass, preventing any internal code mentions
    from creating infinite loops or being unintentionally evaluated.
    """

    PATTERN = re.compile(
        r"(<@(file|dir|type|ext):([^>:]+?)(?::([a-zA-Z0-9\-\#\ ]+))?>|\[@project\])"
    )

    def __init__(self, context: ProjectContext):
        self.context = context

    async def resolve_system(self, text: str) -> str:
        return await self._resolve_pass(text)

    async def resolve_user(self, text: str) -> str:
        return await self._resolve_pass(text)

    async def _resolve_pass(self, text: str) -> str:
        """
        Executes a single pass over the string. Found tokens are replaced,
        and the content returned by context resolution is intentionally
        NOT re-scanned. This prevents infinite loops.
        """
        matches = list(self.PATTERN.finditer(text))
        if not matches:
            return text

        # Concurrently resolve all matches from this pass
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(self._process_match(m)) for m in matches]

        replacements = [t.result() for t in tasks]

        # Reconstruct the string linearly
        parts = []
        last_idx = 0
        for m, repl in zip(matches, replacements):
            parts.append(text[last_idx:m.start()])
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

        return full_match
