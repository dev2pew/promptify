"""Search, replace, and jump behavior for the interactive editor."""

from __future__ import annotations

import re

from ...shared.editor_state import SearchHighlightState, SearchMatch
from ...shared.editor_support import (
    build_jump_target,
    parse_jump_target,
    preserve_replacement_case,
)
from ._imports import Buffer, Document


class EditorSearchMixin:
    """Provide search, replace, jump, and token-count refresh behavior."""

    def _remember_search_query(self, query: str) -> None:
        """Keep a small in-memory history of search queries."""
        query = query.strip()
        if not query:
            return
        self._search_history = [item for item in self._search_history if item != query]
        self._search_history.insert(0, query)
        del self._search_history[self.SEARCH_HISTORY_LIMIT :]
        self._search_history_index = -1

    def cycle_search_history(self, direction: int) -> None:
        """Move backward or forward through recent search queries."""
        if not self._search_history:
            return
        if self._search_history_index < 0:
            self._search_history_draft = self.search_buffer.text
            self._search_history_index = 0 if direction < 0 else -1
        else:
            self._search_history_index -= direction

        if self._search_history_index < 0:
            self._search_history_index = -1
            query = self._search_history_draft
        elif self._search_history_index >= len(self._search_history):
            self._search_history_index = len(self._search_history) - 1
            query = self._search_history[self._search_history_index]
        else:
            query = self._search_history[self._search_history_index]

        self._search_history_navigation_active = True
        try:
            self.search_buffer.document = Document(query, cursor_position=len(query))
        finally:
            self._search_history_navigation_active = False

    def _handle_search_text_changed(self, _buffer: Buffer) -> None:
        """Clear stale search navigation state after query edits."""
        self._clear_search_message()
        self._reset_search_navigation()
        if not self._search_history_navigation_active:
            self._search_history_index = -1
        self.invalidate()

    def _handle_replace_text_changed(self, _buffer: Buffer) -> None:
        """Refresh the widget when replace content changes."""
        self.invalidate()

    def _handle_jump_text_changed(self, _buffer: Buffer) -> None:
        """Clear stale jump validation once the requested target changes."""
        self._clear_jump_message()
        self.invalidate()

    def _refresh_jump_suggestion(self) -> None:
        """Recompute the jump bar suggestion from the live main-editor cursor."""
        auto_suggest = self.jump_buffer.auto_suggest
        if auto_suggest is None:
            return
        self.jump_buffer.suggestion = auto_suggest.get_suggestion(
            self.jump_buffer,
            self.jump_buffer.document,
        )
        self.jump_buffer.on_suggestion_set.fire()

    def _invalidate_search_cache(self) -> None:
        """Drop cached search results after any search mode change."""
        self._search_cache_state = None
        self._search_cache_text_id = 0
        self._search_cache_cursor = -1
        self._search_cache_query = ""

    def _reset_search_navigation(self) -> None:
        """Clear the last explicit search step anchor."""
        self._search_last_query = ""
        self._search_last_direction = 1
        self._search_last_match = None
        self._invalidate_search_cache()

    def _set_search_option(self, name: str, value: bool) -> None:
        """Apply one search flag and clear stale search state."""
        if getattr(self.search_options, name) == value:
            return
        setattr(self.search_options, name, value)
        self._clear_search_message()
        self._reset_search_navigation()
        self.invalidate()

    def toggle_match_case(self) -> None:
        """Toggle case-sensitive search mode."""
        self._set_search_option("match_case", not self.search_options.match_case)

    def toggle_match_whole_word(self) -> None:
        """Toggle whole-word search mode."""
        self._set_search_option(
            "match_whole_word", not self.search_options.match_whole_word
        )

    def toggle_regex(self) -> None:
        """Toggle regex search mode."""
        self._set_search_option("regex", not self.search_options.regex)

    def toggle_preserve_case(self) -> None:
        """Toggle preserve-case replace mode."""
        self._set_search_option("preserve_case", not self.search_options.preserve_case)

    def _compile_search_pattern(self, query: str) -> re.Pattern[str] | None:
        """Compile the current search query into a reusable pattern."""
        if not query:
            return None
        body = query if self.search_options.regex else re.escape(query)
        if self.search_options.match_whole_word:
            body = rf"\b(?:{body})\b"
        flags = 0 if self.search_options.match_case else re.IGNORECASE
        return re.compile(body, flags)

    def _get_search_highlight_state(self) -> SearchHighlightState | None:
        """Return a cached search snapshot to avoid repeated full scans."""
        if not self.search_visible:
            return None

        query = self.search_buffer.text
        text = self.buffer.text
        cursor = self.buffer.cursor_position
        text_id = id(text)
        if (
            self._search_cache_state is not None
            and self._search_cache_text_id == text_id
            and self._search_cache_query == query
            and self._search_cache_cursor == cursor
            and self._search_cache_options == self.search_options
        ):
            return self._search_cache_state

        if not query:
            state = SearchHighlightState("", tuple(), None, 0)
        else:
            try:
                pattern = self._compile_search_pattern(query)
            except re.error as err:
                self._set_search_message(str(err))
                state = SearchHighlightState(query, tuple(), None, 0)
                self._search_cache_text_id = text_id
                self._search_cache_cursor = cursor
                self._search_cache_query = query
                self._search_cache_options = self.search_options.copy()
                self._search_cache_state = state
                return state

            matches = (
                tuple(
                    SearchMatch(match.start(), match.end())
                    for match in pattern.finditer(text)
                    if match.start() != match.end()
                )
                if pattern is not None
                else tuple()
            )
            active_match: SearchMatch | None = None
            active_ordinal = 0
            if matches:
                cursor_match = next(
                    (match for match in matches if match.start <= cursor < match.end),
                    None,
                )
                if cursor_match is not None:
                    active_match = cursor_match
                elif (
                    self._search_last_query == query
                    and self._search_last_match in matches
                ):
                    active_match = self._search_last_match
                else:
                    active_match = next(
                        (match for match in matches if match.start >= cursor),
                        matches[0],
                    )
                active_ordinal = matches.index(active_match) + 1

            state = SearchHighlightState(query, matches, active_match, active_ordinal)

        self._search_cache_text_id = text_id
        self._search_cache_cursor = cursor
        self._search_cache_query = query
        self._search_cache_options = self.search_options.copy()
        self._search_cache_state = state
        return state

    def _focus_search(self) -> None:
        """Move input focus into the search field if an app is active."""
        self._focus_target("search")

    def _focus_replace(self) -> None:
        """Move input focus into the replace field if replace is visible."""
        self._focus_target("replace")

    def _focus_main(self) -> None:
        """Restore input focus to the main editor buffer."""
        self._focus_target("main")

    def open_search(self) -> None:
        """Show the search bar and prepare it for immediate input."""
        self.note_user_activity()
        self.jump_visible = False
        self.jump_buffer.document = Document("", cursor_position=0)
        self._clear_jump_message()
        self.search_visible = True
        self._clear_search_message()
        self._invalidate_search_cache()
        if self.search_buffer.text:
            self.search_buffer.cursor_position = len(self.search_buffer.text)
        elif self._search_history:
            query = self._search_history[0]
            self.search_buffer.document = Document(query, cursor_position=len(query))
        self._focus_search()

    def close_search(self) -> None:
        """Hide the search bar and return focus to the editor."""
        self.search_visible = False
        self.replace_visible = False
        self._clear_search_message()
        self._reset_search_navigation()
        self._focus_target("main")

    def toggle_replace(self) -> None:
        """Toggle the replace row beneath the active search field."""
        self.open_search()
        self.replace_visible = not self.replace_visible
        if not self.replace_visible:
            self._focus_search()
            return
        self._focus_replace()

    def open_jump(self) -> None:
        """Show the jump bar and prepare it for a line or line:column target."""
        self.note_user_activity()
        self.search_visible = False
        self.replace_visible = False
        self._clear_search_message()
        self._reset_search_navigation()
        self.jump_visible = True
        self.jump_buffer.document = Document("", cursor_position=0)
        self._clear_jump_message()
        self._refresh_jump_suggestion()
        self._focus_target("jump")
        self.invalidate()

    def close_jump(self) -> None:
        """Hide the jump bar and return focus to the editor."""
        self.jump_visible = False
        self.jump_buffer.document = Document("", cursor_position=0)
        self._clear_jump_message()
        self._focus_target("main")

    def submit_jump(self) -> bool:
        """Jump to the requested line and optional character position."""
        raw_target = self._normalize_jump_target_text(self.jump_buffer.text)
        if not raw_target:
            raw_target = build_jump_target(
                self.buffer.document.cursor_position_row + 1,
                self.buffer.document.cursor_position_col + 1,
            )

        parsed = parse_jump_target(raw_target)
        if parsed is None:
            self._set_jump_message(
                self.get_text(
                    "editor_jump_invalid_format",
                    "use :line[:char] or :line,char",
                )
            )
            return False

        line, column = parsed
        document = self.buffer.document
        if line < 1 or line > document.line_count:
            self._set_jump_message(
                self.get_text("editor_jump_line_out_of_range", "line out of range")
            )
            return False

        line_text = document.lines[line - 1]
        max_column = len(line_text) + 1
        if column < 1 or column > max_column:
            self._set_jump_message(
                self.get_text(
                    "editor_jump_char_out_of_range",
                    "character out of range",
                )
            )
            return False

        self.buffer.cursor_position = document.translate_row_col_to_index(
            line - 1,
            column - 1,
        )
        self._search_cache_state = None
        self.close_jump()
        self.invalidate()
        return True

    def _find_search_match(
        self, matches: tuple[SearchMatch, ...], start: int, direction: int
    ) -> tuple[SearchMatch | None, bool]:
        """Search forward or backward across precomputed match spans."""
        if not matches:
            return None, False
        if direction > 0:
            for match in matches:
                if match.start >= start:
                    return match, False
            return matches[0], True

        for match in reversed(matches):
            if match.start <= start:
                return match, False
        return matches[-1], True

    def search_step(self, direction: int) -> bool:
        """Move to the next or previous search match while keeping search open."""
        query = self.search_buffer.text
        if not query:
            self._set_search_message(
                self.get_text("editor_search_enter_query", "enter a query")
            )
            return False

        try:
            state = self._get_search_highlight_state()
        except re.error as err:
            self._set_search_message(str(err))
            return False

        if state is None or not state.matches:
            self._set_search_message(
                self.get_text("editor_search_not_found", "not found")
            )
            return False

        repeated = (
            query == self._search_last_query
            and direction == self._search_last_direction
            and self._search_last_match is not None
            and self.buffer.cursor_position == self._search_last_match.start
        )
        start = self.buffer.cursor_position
        if direction > 0 and repeated and self._search_last_match is not None:
            start = self._search_last_match.end
        elif direction < 0:
            start -= 1

        match, wrapped = self._find_search_match(state.matches, start, direction)
        if match is None:
            self._set_search_message(
                self.get_text("editor_search_not_found", "not found")
            )
            return False

        self.buffer.cursor_position = match.start
        self._search_last_query = query
        self._search_last_direction = direction
        self._search_last_match = match
        self._invalidate_search_cache()
        self._remember_search_query(query)
        self._set_search_message(
            self.get_text("editor_search_wrapped", "wrapped") if wrapped else "",
            transient=wrapped,
        )
        return True

    def replace_current(self) -> bool:
        """Replace the active match and keep the replace widget open."""
        state = self._get_search_highlight_state()
        if state is None or not state.matches:
            self._set_search_message(
                self.get_text("editor_search_not_found", "not found")
            )
            return False

        match = state.active_match or state.matches[0]
        text = self.buffer.text
        source = text[match.start : match.end]
        replacement = self._expand_replacement(source, match)
        self.buffer.text = text[: match.start] + replacement + text[match.end :]
        self.buffer.cursor_position = match.start + len(replacement)
        self._remember_search_query(self.search_buffer.text)
        self._clear_search_message()
        self._reset_search_navigation()
        self.invalidate()
        return True

    def replace_all(self) -> int:
        """Replace every current match and return the replacement count."""
        query = self.search_buffer.text
        if not query:
            self._set_search_message(
                self.get_text("editor_search_enter_query", "enter a query")
            )
            return 0

        text = self.buffer.text
        try:
            pattern = self._compile_search_pattern(query)
        except re.error as err:
            self._set_search_message(str(err))
            return 0
        if pattern is None:
            return 0

        def _replace(match: re.Match[str]) -> str:
            source = match.group(0)
            replacement = (
                match.expand(self.replace_buffer.text)
                if self.search_options.regex
                else self.replace_buffer.text
            )
            if self.search_options.preserve_case:
                replacement = preserve_replacement_case(source, replacement)
            return replacement

        new_text, count = pattern.subn(_replace, text)
        if count <= 0:
            self._set_search_message(
                self.get_text("editor_search_not_found", "not found")
            )
            return 0

        self.buffer.text = new_text
        self.buffer.cursor_position = 0
        self._remember_search_query(query)
        self._clear_search_message()
        self._reset_search_navigation()
        self.invalidate()
        return count

    def _expand_replacement(self, source: str, match: SearchMatch) -> str:
        """Build the replacement text for one concrete match span."""
        replacement = self.replace_buffer.text
        if self.search_options.regex:
            pattern = self._compile_search_pattern(self.search_buffer.text)
            if pattern is not None:
                match_obj = pattern.search(self.buffer.text, match.start, match.end)
                if match_obj is not None:
                    replacement = match_obj.expand(replacement)
        if self.search_options.preserve_case:
            replacement = preserve_replacement_case(source, replacement)
        return replacement
