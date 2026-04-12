import sys
import datetime
from typing import Any
from prompt_toolkit import print_formatted_text, HTML
from prompt_toolkit.shortcuts import PromptSession

from ..utils.i18n import strings


class Logger:
    def __init__(self, verbosity: int = 1, include_timestamp: bool = False):
        self.verbosity = verbosity
        self.include_timestamp = include_timestamp
        self._session: PromptSession[str] | None = None

    def _get_timestamp(self) -> str:
        if self.include_timestamp:
            return f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
        return ""

    def _print(self, prefix: str, color: str, message: str, **kwargs: Any) -> None:
        timestamp = self._get_timestamp()
        safe_message = str(message).replace("<", "&lt;").replace(">", "&gt;")
        formatted_text = HTML(f"{timestamp}<{color}>{prefix}</{color}> {safe_message}")

        try:
            print_formatted_text(formatted_text, **kwargs)
        except Exception:
            print(f"{timestamp}{prefix} {message}", **kwargs)

    def normal(self, message: str, **kwargs: Any) -> None:
        self._print("[>]", "ansiblue", message, **kwargs)

    async def input_async(self, message: str) -> str:
        timestamp = self._get_timestamp()
        safe_message = str(message).replace("<", "&lt;").replace(">", "&gt;")

        # AUTOMATICALLY APPEND ' >> ' TO ALL INPUT PROMPTS
        formatted_text = HTML(
            f"{timestamp}<ansicyan>[&lt;]</ansicyan> {safe_message} &gt;&gt; "
        )

        if self._session is None:
            self._session = PromptSession()

        try:
            return await self._session.prompt_async(formatted_text)
        except (EOFError, KeyboardInterrupt):
            print()
            self.warning(strings.get("operation_cancelled", "operation cancelled"))
            sys.exit(0)

    def error(self, message: str, **kwargs: Any) -> None:
        self._print("[e]", "ansired", message, **kwargs)

    def success(self, message: str, **kwargs: Any) -> None:
        self._print("[+]", "ansigreen", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._print("[w]", "ansiyellow", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._print("[i]", "ansiblue", message, **kwargs)

    def notice(self, message: str, **kwargs: Any) -> None:
        self._print("[*]", "ansimagenta", message, **kwargs)

    def verbose(self, message: str, level: int = 2, **kwargs: Any) -> None:
        if self.verbosity >= level:
            self._print("[v]", "ansigray", message, **kwargs)


log = Logger()
