import re
import asyncio
from context import ProjectContext

class PromptResolver:
    """
    Asynchronous regex resolver leveraging structured concurrency.
    Separates SYSTEM (recursive) and USER (single-pass) workflows.
    """

    # Matches <@file:src/app.ts> or <@file:src/app.ts:10-20>
    PATTERN = re.compile(
        r"(<@(file|dir|type|ext):([^>:]+?)(?::([a-zA-Z0-9\-\#\ ]+))?>|\[@project\])"
    )

    def __init__(self, context: ProjectContext):
        self.context = context

    async def resolve_system(self, text: str) -> str:
        """Fully recursive resolution for legacy configs and templates."""
        return await self._resolve_pass(text, recursive=True)

    async def resolve_user(self, text: str) -> str:
        """Single-pass resolution for user text. Prevents recursive injection loops."""
        return await self._resolve_pass(text, recursive=False)

    async def _resolve_pass(self, text: str, recursive: bool, visited: set[str] | None = None) -> str:
        if visited is None:
            visited = set()

        while True:
            matches = list(self.PATTERN.finditer(text))
            if not matches:
                break

            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(self._process_match(m, visited)) for m in matches]

            replacements = [t.result() for t in tasks]

            # Reconstruct string
            parts = []
            last_idx = 0
            for m, repl in zip(matches, replacements):
                parts.append(text[last_idx:m.start()])
                parts.append(repl)
                last_idx = m.end()
            parts.append(text[last_idx:])

            text = "".join(parts)

            if not recursive:
                break

        return text

    async def _process_match(self, match: re.Match, visited: set[str]) -> str:
        full_match = match.group(0)

        if full_match == "[@project]":
            if full_match in visited:
                return f"<!-- Loop detected: {full_match} -->"
            visited.add(full_match)
            return self.context.generate_tree()

        call_type = match.group(2)
        query = match.group(3)
        range_str = match.group(4)

        # Build strict signature for loop detection
        call_sig = f"{call_type}:{query}:{range_str}"
        if call_sig in visited:
            return f"<!-- Loop detected: {call_sig} -->"

        visited.add(call_sig)

        if call_type == "file":
            return await self.context.get_file_content(query, range_str)
        elif call_type == "dir":
            return await self.context.get_dir_contents(query)
        elif call_type in ("type", "ext"):
            return await self.context.get_type_contents(query)

        return full_match
