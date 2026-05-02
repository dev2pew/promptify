"""Formatted CLI logger built on prompt-toolkit HTML styling"""

import sys
import datetime
from typing import Any
from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit import print_formatted_text, HTML
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.styles import Style

from ..core.settings import APP_SETTINGS
from ..utils.i18n import get_string
from .suggestions import AUTO_SUGGESTION_STYLE, PrefixSuggestion

_AUTO_SUGGESTION_STYLE = AUTO_SUGGESTION_STYLE


class Logger:
    """Provide categorized console output with consistent HTML-based styling"""

    def __init__(self, verbosity: int = 1, include_timestamp: bool = False):
        """
        Initialize the logger.

        Args:
            `verbosity` (int): Sets reporting noise limits based on configurations.
            `include_timestamp` (bool): Appends execution timelines ahead of responses.
        """
        self.verbosity = verbosity
        self.include_timestamp = include_timestamp
        self._session: PromptSession[str] | None = None
        self._input_style = Style.from_dict({"auto-suggestion": AUTO_SUGGESTION_STYLE})
        self._input_bindings = self._build_input_bindings()

    def _build_input_bindings(self) -> KeyBindings:
        """Add prompt-only bindings for inline suggestion acceptance"""
        bindings = KeyBindings()

        @Condition
        def suggestion_available() -> bool:
            app = get_app()
            suggestion = app.current_buffer.suggestion
            return (
                suggestion is not None
                and len(suggestion.text) > 0
                and app.current_buffer.document.is_cursor_at_the_end
            )

        @bindings.add("tab", filter=suggestion_available)
        def _accept_suggestion(event: Any) -> None:
            suggestion = event.current_buffer.suggestion
            if suggestion:
                event.current_buffer.insert_text(suggestion.text)

        @Condition
        def empty_buffer_suggestion_available() -> bool:
            app = get_app()
            return suggestion_available() and app.current_buffer.text == ""

        @bindings.add("enter", filter=empty_buffer_suggestion_available)
        def _accept_empty_buffer_suggestion(event: Any) -> None:
            suggestion = event.current_buffer.suggestion
            if suggestion:
                event.current_buffer.insert_text(suggestion.text)
            event.current_buffer.validate_and_handle()

        return bindings

    def _prime_default_suggestion(self) -> None:
        """Trigger auto-suggestion rendering for untouched empty prompts"""
        buffer = self._session.default_buffer if self._session is not None else None
        if buffer is not None and not buffer.text:
            buffer.insert_text("")

    def _get_timestamp(self) -> str:
        """Return the formatted current time when timestamps are enabled"""
        if self.include_timestamp:
            return f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
        return ""

    def _print(self, prefix: str, color: str, message: str, **kwargs: Any) -> None:
        """
        Render a formatted message using the configured prefix and color.

        Args:
            `prefix` (str): Indicator tag shown pre-message sequence structure.
            `color` (str): Output string mapped reference code identifier HTML target.
            `message` (str): Final execution state reporting print object.
            `**kwargs`: Extra formatting logic passed internally toward stdout mechanisms.
        """
        timestamp = self._get_timestamp()
        safe_message = str(message).replace("<", "&lt;").replace(">", "&gt;")
        formatted_text = HTML(f"{timestamp}<{color}>{prefix}</{color}> {safe_message}")

        try:
            print_formatted_text(formatted_text, **kwargs)
        except Exception:
            print(f"{timestamp}{prefix} {message}", **kwargs)

    def normal(self, message: str, **kwargs: Any) -> None:
        """Print a standard log message"""
        self._print(
            APP_SETTINGS.logger.normal_prefix,
            APP_SETTINGS.logger.normal_color,
            message,
            **kwargs,
        )

    async def input_async(self, message: str, default: str = "") -> str:
        """
        Prompt for input asynchronously without blocking the event loop.

        Args:
            `message` (str): Instruction context outputting for prompting operation inputs.
            `default` (str): Suggested trailing text shown while the typed input stays on its prefix.

        Returns:
            `str`: Supplied responses processed natively from keyboard inputs directly mapping UI interaction states.
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
            return await self._session.prompt_async(
                formatted_text,
                auto_suggest=PrefixSuggestion(default),
                style=self._input_style,
                key_bindings=self._input_bindings,
                pre_run=self._prime_default_suggestion,
            )
        except (EOFError, KeyboardInterrupt):
            print()
            self.warn(get_string("operation_cancelled", "operation cancelled"))
            sys.exit(0)

    def err(self, message: str, **kwargs: Any) -> None:
        """Print an error message"""
        self._print(
            APP_SETTINGS.logger.err_prefix,
            APP_SETTINGS.logger.err_color,
            message,
            **kwargs,
        )

    def success(self, message: str, **kwargs: Any) -> None:
        """Print a success message"""
        self._print(
            APP_SETTINGS.logger.success_prefix,
            APP_SETTINGS.logger.success_color,
            message,
            **kwargs,
        )

    def warn(self, message: str, **kwargs: Any) -> None:
        """Print a warning message"""
        self._print(
            APP_SETTINGS.logger.warn_prefix,
            APP_SETTINGS.logger.warn_color,
            message,
            **kwargs,
        )

    def info(self, message: str, **kwargs: Any) -> None:
        """Print an informational message"""
        self._print(
            APP_SETTINGS.logger.info_prefix,
            APP_SETTINGS.logger.info_color,
            message,
            **kwargs,
        )

    def notice(self, message: str, **kwargs: Any) -> None:
        """Print a high-visibility notice message"""
        self._print(
            APP_SETTINGS.logger.notice_prefix,
            APP_SETTINGS.logger.notice_color,
            message,
            **kwargs,
        )

    def verbose(self, message: str, level: int = 2, **kwargs: Any) -> None:
        """Print a verbose message when the configured level allows it"""
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
