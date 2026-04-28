"""
CUSTOM FORMATTED LOGGER FOR CLI OUTPUT USING PROMPT-TOOLKIT'S HTML STYLING.
"""

import sys
import datetime
from typing import Any
from prompt_toolkit import print_formatted_text, HTML
from prompt_toolkit.shortcuts import PromptSession

from ..utils.i18n import get_string


class Logger:
    """PROVIDES CATEGORIZED CONSOLE OUTPUT WRAPPED IN HTML TAGS FOR CONSISTENT COLORS."""

    def __init__(self, verbosity: int = 1, include_timestamp: bool = False):
        """
        INITIALIZES CUSTOM PRINTING OUTPUT CONSTRAINTS.

        Args:
            verbosity (int): Sets reporting noise limits based on configurations.
            include_timestamp (bool): Appends execution timelines ahead of responses.
        """
        self.verbosity = verbosity
        self.include_timestamp = include_timestamp
        self._session: PromptSession[str] | None = None

    def _get_timestamp(self) -> str:
        """RETURNS THE FORMATTED CURRENT TIME STRUCTURE STRING IF REQUESTED NATIVELY."""
        if self.include_timestamp:
            return f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
        return ""

    def _print(self, prefix: str, color: str, message: str, **kwargs: Any) -> None:
        """
        GENERIC RENDERING ROUTINE FOR TRANSLATING RAW COMPONENTS TO HTML STRUCTURES.

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
        """PRINTS A STANDARD OUTPUT STATEMENT LOGIC MESSAGE."""
        self._print("[>]", "ansiblue", message, **kwargs)

    async def input_async(self, message: str) -> str:
        """
        HANDLES INTERACTIVE DATA CONSUMPTION OPERATIONS ASYNCHRONOUSLY WITHOUT BLOCKING EVENT LOOPS.

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
            self.warning(get_string("operation_cancelled", "operation cancelled"))
            sys.exit(0)

    def error(self, message: str, **kwargs: Any) -> None:
        """PRINTS ERROR STATE REPRESENTATIONS DIRECTLY UTILIZING FATAL INDICATORS."""
        self._print("[e]", "ansired", message, **kwargs)

    def success(self, message: str, **kwargs: Any) -> None:
        """PRINTS SUCCESSFUL LOGIC CONCLUSION OUTPUTS CLEARLY MARKING PROGRESSION MARKERS MAPPING TARGETS SAFELY NATIVELY."""
        self._print("[+]", "ansigreen", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """PRINTS WARNING CONDITION EVALUATIONS PREVENTING EXECUTION FAULTS."""
        self._print("[w]", "ansiyellow", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """PRINTS INFORMATIONAL TRACE LOGIC MAPPING DEBUG STATE EVALUATION STRINGS."""
        self._print("[i]", "ansiblue", message, **kwargs)

    def notice(self, message: str, **kwargs: Any) -> None:
        """PRINTS PRIORITY HIGHLIGHT REPRESENTATIONS DIRECTING WORKFLOW ACTIONS STRICTLY CORRECTLY SAFELY."""
        self._print("[*]", "ansimagenta", message, **kwargs)

    def verbose(self, message: str, level: int = 2, **kwargs: Any) -> None:
        """PRINTS HIGHLY GRANULAR LOGIC REPORTS STRICTLY ONLY TARGETING DETAILED DEBUG TRACE INSTANCES NATIVELY."""
        if self.verbosity >= level:
            self._print("[v]", "ansigray", message, **kwargs)


log = Logger()
