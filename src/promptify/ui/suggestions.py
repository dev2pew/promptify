"""Shared prompt-toolkit auto-suggestion helpers for promptify UI surfaces"""

from collections.abc import Callable
from typing import Any

from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion

AUTO_SUGGESTION_STYLE = "#888888 bg:default noreverse noitalic nounderline noblink"


class PrefixSuggestion(AutoSuggest):
    """Show the remainder of a value while the current input stays on its prefix"""

    def __init__(self, value: str | Callable[[], str]):
        self._value = value

    def get_suggestion(self, buffer: Any, document: Any) -> Suggestion | None:
        """Return the unmatched suffix when the current input matches the prefix"""
        del buffer
        value = self._value() if callable(self._value) else self._value
        typed = document.text
        if not value or not value.startswith(typed):
            return None

        remainder = value[len(typed) :]
        if not remainder:
            return None
        return Suggestion(remainder)
