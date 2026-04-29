"""
CUSTOM FORMATTED LOGGER FOR CLI OUTPUT USING PROMPT-TOOLKIT'S HTML STYLING.
"""

import sys
import datetime
from typing import Any
from prompt_toolkit import print_formatted_text, HTML
from prompt_toolkit.shortcuts import PromptSession

from ..core.settings import APP_SETTINGS
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
        self._print(
            APP_SETTINGS.logger.normal_prefix,
            APP_SETTINGS.logger.normal_color,
            message,
            **kwargs,
        )

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
            f"{timestamp}<{APP_SETTINGS.logger.input_prefix_color}>"
            f"{APP_SETTINGS.logger.input_prefix.replace('<', '&lt;').replace('>', '&gt;')}"
            f"</{APP_SETTINGS.logger.input_prefix_color}> "
            f"{safe_message} {APP_SETTINGS.logger.input_suffix.replace('<', '&lt;').replace('>', '&gt;')} "
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
        self._print(
            APP_SETTINGS.logger.error_prefix,
            APP_SETTINGS.logger.error_color,
            message,
            **kwargs,
        )

    def success(self, message: str, **kwargs: Any) -> None:
        """PRINTS SUCCESSFUL LOGIC CONCLUSION OUTPUTS CLEARLY MARKING PROGRESSION MARKERS MAPPING TARGETS SAFELY NATIVELY."""
        self._print(
            APP_SETTINGS.logger.success_prefix,
            APP_SETTINGS.logger.success_color,
            message,
            **kwargs,
        )

    def warning(self, message: str, **kwargs: Any) -> None:
        """PRINTS WARNING CONDITION EVALUATIONS PREVENTING EXECUTION FAULTS."""
        self._print(
            APP_SETTINGS.logger.warning_prefix,
            APP_SETTINGS.logger.warning_color,
            message,
            **kwargs,
        )

    def info(self, message: str, **kwargs: Any) -> None:
        """PRINTS INFORMATIONAL TRACE LOGIC MAPPING DEBUG STATE EVALUATION STRINGS."""
        self._print(
            APP_SETTINGS.logger.info_prefix,
            APP_SETTINGS.logger.info_color,
            message,
            **kwargs,
        )

    def notice(self, message: str, **kwargs: Any) -> None:
        """PRINTS PRIORITY HIGHLIGHT REPRESENTATIONS DIRECTING WORKFLOW ACTIONS STRICTLY CORRECTLY SAFELY."""
        self._print(
            APP_SETTINGS.logger.notice_prefix,
            APP_SETTINGS.logger.notice_color,
            message,
            **kwargs,
        )

    def verbose(self, message: str, level: int = 2, **kwargs: Any) -> None:
        """PRINTS HIGHLY GRANULAR LOGIC REPORTS STRICTLY ONLY TARGETING DETAILED DEBUG TRACE INSTANCES NATIVELY."""
        if self.verbosity >= level:
            self._print(
                APP_SETTINGS.logger.verbose_prefix,
                APP_SETTINGS.logger.verbose_color,
                message,
                **kwargs,
            )


log = Logger(
    verbosity=APP_SETTINGS.logger.verbosity,
    include_timestamp=APP_SETTINGS.logger.include_timestamp,
)
