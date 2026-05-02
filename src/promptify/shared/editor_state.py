"""Shared editor-neutral state objects used across the editor package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

FocusTarget = Literal["main", "search", "replace", "jump", "help", "error", "quit"]
OverlayName = Literal["none", "help", "error", "quit"]
SelectionSnapshot = Any


@dataclass(frozen=True)
class SearchMatch:
    """Store one resolved search span in the active document."""

    start: int
    end: int


@dataclass(frozen=True)
class SearchHighlightState:
    """Cached search snapshot used for highlighting and status rendering."""

    query: str
    matches: tuple[SearchMatch, ...]
    active_match: SearchMatch | None
    active_ordinal: int


@dataclass(frozen=True)
class MentionValidationResult:
    """Capture whether a mention is valid, malformed, or unresolved."""

    style: str | None
    message: str | None


@dataclass(frozen=True)
class EditorIssue:
    """Represent a navigable editor issue in the current document."""

    line: int
    column: int
    end_column: int
    style: str
    message: str
    fragment: str


@dataclass(frozen=True)
class EditorViewState:
    """Capture editor view state so overlays can restore it predictably."""

    focus: FocusTarget
    main_cursor: int
    search_cursor: int
    replace_cursor: int
    jump_cursor: int
    main_selection: SelectionSnapshot | None
    search_selection: SelectionSnapshot | None
    replace_selection: SelectionSnapshot | None
    jump_selection: SelectionSnapshot | None


@dataclass(slots=True)
class SearchOptions:
    """Track the live search and replace flags exposed by the widget."""

    match_case: bool = False
    match_whole_word: bool = False
    regex: bool = False
    preserve_case: bool = False

    def copy(self) -> SearchOptions:
        """Create a detached snapshot for cache comparisons."""
        return SearchOptions(
            match_case=self.match_case,
            match_whole_word=self.match_whole_word,
            regex=self.regex,
            preserve_case=self.preserve_case,
        )
