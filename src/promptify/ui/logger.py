"""
Custom formatted logger for CLI output using prompt-toolkit's HTML styling.
"""

import sys
import datetime
from typing import Any
from prompt_toolkit import print_formatted_text, HTML
from prompt_toolkit.shortcuts import PromptSession

from ..utils.i18n import strings


class Logger:
    """Provides categorized console output wrapped in HTML tags for consistent colors."""

    def __init__(self, verbosity: int = 1, include_timestamp: bool = False):
        """
        Initializes custom printing output constraints.

        Args:
            verbosity (int): Sets reporting noise limits based on configurations.
            include_timestamp (bool): Appends execution timelines ahead of responses.
        """
        self.verbosity = verbosity
        self.include_timestamp = include_timestamp
        self._session: PromptSession[str] | None = None

    def _get_timestamp(self) -> str:
        """Returns the formatted current time structure string if requested natively."""
        if self.include_timestamp:
            return f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
        return ""

    def _print(self, prefix: str, color: str, message: str, **kwargs: Any) -> None:
        """
        Generic rendering routine for translating raw components to HTML structures.

        Args:
            prefix (str): Indicator tag shown pre-message sequence structure.
            color (str): Output string mapped reference code identifier HTML target.
            message (str): Final execution state reporting print object.
            **kwargs: Extra formatting logic passed internally toward stdout mechanisms.
        """
        timestamp = self._get_timestamp()
        safe_message = str(message).replace("<", "&lt;").replace(">", "&gt;")
        formatted_text = HTML(f"{timestamp}<{color}>{prefix}</{color}> {safe_message}")

        try:
            print_formatted_text(formatted_text, **kwargs)
        except Exception:
            print(f"{timestamp}{prefix} {message}", **kwargs)

    def normal(self, message: str, **kwargs: Any) -> None:
        """Prints a standard output statement logic message."""
        self._print("[>]", "ansiblue", message, **kwargs)

    async def input_async(self, message: str) -> str:
        """
        Handles interactive data consumption operations asynchronously without blocking event loops.

        Args:
            message (str): Instruction context outputting for prompting operation inputs.

        Returns:
            str: Supplied responses processed natively from keyboard inputs directly mapping UI interaction states.
        """
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
        """Prints error state representations directly utilizing fatal indicators."""
        self._print("[e]", "ansired", message, **kwargs)

    def success(self, message: str, **kwargs: Any) -> None:
        """Prints successful logic conclusion outputs clearly marking progression markers mapping targets safely natively."""
        self._print("[+]", "ansigreen", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Prints warning condition evaluations preventing execution faults."""
        self._print("[w]", "ansiyellow", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Prints informational trace logic mapping debug state evaluation strings."""
        self._print("[i]", "ansiblue", message, **kwargs)

    def notice(self, message: str, **kwargs: Any) -> None:
        """Prints priority highlight representations directing workflow actions strictly correctly safely."""
        self._print("[*]", "ansimagenta", message, **kwargs)

    def verbose(self, message: str, level: int = 2, **kwargs: Any) -> None:
        """Prints highly granular logic reports strictly only targeting detailed debug trace instances natively."""
        if self.verbosity >= level:
            self._print("[v]", "ansigray", message, **kwargs)


log = Logger()
